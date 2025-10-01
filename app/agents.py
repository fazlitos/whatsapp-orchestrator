# app/agents.py
import os, json
from typing import Dict, Any, List
from openai import OpenAI

# Modell & Client (funktioniert mit OpenAI oder kompatiblen Endpoints)
MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
BASE_URL = os.getenv("LLM_BASE_URL", None)  # optional für self-host/compat
API_KEY  = os.getenv("OPENAI_API_KEY", "")

_client_args = {}
if BASE_URL: _client_args["base_url"] = BASE_URL
if API_KEY:  _client_args["api_key"]  = API_KEY
client = OpenAI(**_client_args)

# Feldschema für Kindergeld (Schlüssel = eure internen Keys)
KG_FIELD_SPEC = {
    "top": {
        "full_name": "string",
        "dob": "date",                # TT.MM.JJJJ
        "addr_street": "string",
        "addr_plz": "plz",
        "addr_city": "string",
        "taxid_parent": "taxid",
        "iban": "iban",
        "marital": "enum:ledig,verheiratet,geschieden,verwitwet,lebenspartnerschaft",
        "citizenship": "string",
        "employment": "string",
        "start_month": "month",       # MM.JJJJ
        "kid_count": "int"
    },
    "kid": {
        "kid_name": "string",
        "kid_dob": "date",
        "kid_taxid": "taxid",
        "kid_relation": "enum:kind,pflegekind,stiefkind,adoptivkind,anderes",
        "kid_cohab": "bool",
        "kid_status": "enum:schule,ausbildung,studium,arbeitssuchend,unter_6,sonstiges",
        "kid_eu_benefit": "bool"
    }
}

SYSTEM_PROMPT = """Du bist ein präziser Formular-Assistent. 
Deine Aufgabe: Lies eine frei formulierte WhatsApp-Nachricht und extrahiere **nur** die Felder, 
die zum Formular 'Kindergeld' gehören. Antworte **ausschließlich** als kompaktes JSON-Objekt.

Konventionen:
- Keys sind die internen Feldnamen (z.B. "full_name", "addr_plz", "kid_name", "kid_dob").
- Datenformate:
  - date: TT.MM.JJJJ (führe ggf. Umwandlung durch)
  - month: MM.JJJJ
  - plz: 5-stellige Zahl als String
  - iban: DE… ohne Leerzeichen
  - bool: true/false
  - enum: exakt einer der erlaubten Werte
- Kinder-Werte gehören in ein Array `kids_updates`, jedes Element nur die in der Nachricht erkannten Felder.
- Nur Felder zurückgeben, die du **sicher** erkannt hast. Keine Halluzinationen, nichts erfinden.
- Beispiel-Antwort:
  {
    "top_updates": {"full_name":"Max Mustermann","addr_plz":"10115"},
    "kids_updates":[{"kid_name":"Mia Mustermann","kid_dob":"01.01.2019"}]
  }
"""

def _build_user_prompt(text: str, known: Dict[str, Any], missing: List[str], kid_index: int | None):
    return {
        "role": "user",
        "content": json.dumps({
            "message": text,
            "known_fields": known,
            "missing_fields": missing,
            "current_kid_index": kid_index
        }, ensure_ascii=False)
    }

def extract_updates_from_text(
    text: str,
    known_fields: Dict[str, Any],
    missing_fields: List[str],
    current_kid_index: int | None = None
) -> Dict[str, Any]:
    """
    Ruft das LLM auf und liefert Dict:
    { "top_updates": {...}, "kids_updates": [ {...}, ... ] }
    """
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "system", "content": f"Feldspezifikation: {json.dumps(KG_FIELD_SPEC, ensure_ascii=False)}"},
                _build_user_prompt(text, known_fields, missing_fields, current_kid_index),
            ],
            temperature=0.0,
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
        # Hardening: erwarte genau diese Struktur
        return {
            "top_updates":  data.get("top_updates")  or {},
            "kids_updates": data.get("kids_updates") or [],
        }
    except Exception as e:
        print("LLM extract error:", e)
        return {"top_updates": {}, "kids_updates": []}
