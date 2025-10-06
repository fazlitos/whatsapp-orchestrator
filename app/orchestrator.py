# app/orchestrator.py
import os
import re
import json
import uuid
import httpx
from pathlib import Path

from app.validators import normalize_value, is_complete
from app.state_manager import state_manager

# Optional: LLM-Extraktor (wenn kein Key vorhanden, fällt Code unten automatisch zurück)
try:
    from app.agents import extract_updates_from_text
    LLM_AVAILABLE = True
except Exception:
    LLM_AVAILABLE = False

# ---------- Artefakte (lokal) ----------
ART_DIR = Path("/tmp/artifacts")
ART_DIR.mkdir(exist_ok=True)

BASE = Path(__file__).resolve().parent


def _load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


# ---------- Mehrsprachige Prompts ----------
LOCALES = {
    "de": _load_json(BASE / "locales" / "de.json"),
    "en": _load_json(BASE / "locales" / "en.json"),
    "sq": _load_json(BASE / "locales" / "sq.json"),
}


def t(lang: str, key: str, **kw):
    return LOCALES.get(lang, LOCALES["de"]).get(key, key).format(**kw)


# ---------- Formulare ----------
def load_form(name: str):
    return _load_json(BASE / "forms" / f"{name}.json")


FORMS = {
    "kindergeld": load_form("kindergeld"),
    # weitere Formulare später hier registrieren
}


def ensure_state(user: str):
    """Lädt State aus Redis oder erstellt neuen."""
    existing = state_manager.get(user)
    if existing:
        return existing
    
    # Neuer State
    new_state = {
        "form": "kindergeld",
        "fields": {},
        "kids": [],
        "phase": "collect",
        "idx": 0,
        "lang": "de",
    }
    state_manager.set(user, new_state)
    return new_state


# ---------- Synonyme für Regex-Fallback ----------
TOP_SYNONYMS = {
    "full_name": [r"voller\s+name", r"^name$", r"vor-?\s*und\s*nachname"],
    "dob": [r"geburtsdatum", r"geburtstag", r"dob"],
    "addr_street": [r"(?:adresse|anschrift|straße|strasse|str\.)"],
    "addr_plz": [r"(?:plz|postleitzahl|postal\s*code)"],
    "addr_city": [r"(?:ort|stadt|city)"],
    "taxid_parent": [r"(?:steuer[-\s]?id|idnr\.?|idnr|steuerid)"],
    "iban": [r"iban"],
    "marital": [r"(?:familienstand|marital)"],
    "citizenship": [r"(?:staatsangeh(?:ö|oe)rigkeit|citizenship)"],
    "employment": [r"(?:besch(?:ä|a)ftigung|job|occupation|beruf)"],
    "start_month": [r"(?:beginn|start(?:monat)?|ab\s+monat|monat)"],
    "kid_count": [r"(?:kinderanzahl|anzahl\s+kinder|^kinder$)"],
}

KID_SYNONYMS = {
    "kid_name": [r"(?:name(?:\s*kind)?|voller\s+name)"],
    "kid_dob": [r"(?:geburtsdatum|geburtstag|dob)"],
    "kid_taxid": [r"(?:steuer[-\s]?id|idnr\.?|idnr|steuerid)"],
    "kid_relation": [r"(?:verwandtschaft|beziehung|relation)"],
    "kid_cohab": [r"(?:haushalt|wohnt\s*(?:mit)?|cohab)"],
    "kid_status": [r"(?:status|schule|ausbildung|studium|arbeitssuchend|unter_6)"],
    "kid_eu_benefit": [r"(?:eu-?leistung|eu\s*benefit|leistungen\s*im\s*ausland)"],
}


# ---------- Freitext → Updates (Regex-Fallback, robust) ----------
def parse_kv_updates(text: str, form_types: dict, current_kid_index: int | None = None):
    """Sucht in freiem Text nach 'Feld: Wert' Mustern. Ruft group() nur bei Match auf."""
    updates = {}
    s = text or ""

    def _extract(pattern: str):
        try:
            m = re.search(pattern, s, re.IGNORECASE)
        except re.error as e:
            print("regex error:", pattern, e)
            return None
        if not m:
            return None
        raw = (m.group(1) or "").strip()
        return raw or None

    for key, syns in TOP_SYNONYMS.items():
        vtype = form_types.get(key, "string")
        for syn in syns:
            pattern = rf"(?:{syn})\s*[:\-]?\s*([^\n;,]+)"
            raw = _extract(pattern)
            if raw is None:
                continue
            val = normalize_value(vtype, raw)
            if val is not None:
                updates[key] = val
                break

    if "iban" not in updates:
        m = re.search(r"\bDE[0-9 ]{20,}\b", s, re.IGNORECASE)
        if m:
            updates["iban"] = re.sub(r"\s+", "", m.group(0)).upper()
    if "addr_plz" not in updates:
        m = re.search(r"\b\d{5}\b", s)
        if m and normalize_value("plz", m.group(0)):
            updates["addr_plz"] = m.group(0)

    if current_kid_index is not None:
        kid_types = {
            "kid_name": "string",
            "kid_dob": "date",
            "kid_taxid": "taxid",
            "kid_relation": "enum_relation",
            "kid_cohab": "bool",
            "kid_status": "enum_kstatus",
            "kid_eu_benefit": "bool",
        }
        for key, syns in KID_SYNONYMS.items():
            vtype = kid_types[key]
            for syn in syns:
                pattern = rf"(?:{syn})\s*[:\-]?\s*([^\n;,]+)"
                raw = _extract(pattern)
                if raw is None:
                    continue
                val = normalize_value(vtype, raw)
                if val is not None:
                    updates[key] = val
                    break

    return updates


def _summary(st):
    f = st["fields"]
    kids = st.get("kids", [])
    lines = [
        f"Name: {f.get('full_name','-')}",
        f"Geburtsdatum: {f.get('dob','-')}",
        f"Adresse: {f.get('addr_street','-')}, {f.get('addr_plz','-')} {f.get('addr_city','-')}",
        f"Steuer-ID: {f.get('taxid_parent','-')}",
        f"IBAN: {f.get('iban','-')}",
        f"Familienstand: {f.get('marital','-')}",
        f"Staatsangehörigkeit: {f.get('citizenship','-')}",
        f"Beschäftigung: {f.get('employment','-')}",
        f"Beginn (MM.JJJJ): {f.get('start_month','-')}",
        f"Kinder: {f.get('kid_count','-')}",
    ]
    for i, k in enumerate(kids, 1):
        lines.append(
            f"  #{i} {k.get('kid_name','-')} | {k.get('kid_dob','-')} | Steuer-ID: {k.get('kid_taxid','-')}"
        )
    return "\n".join(lines)


# ---------- Hauptlogik ----------
def handle_message(user: str, text: str, lang: str = "de") -> str:
    st = ensure_state(user)
    st["lang"] = lang
    
    # Helper: State speichern und zurückgeben
    def save_and_return(msg):
        state_manager.set(user, st)
        return msg
    
    form = FORMS.get(st["form"], FORMS["kindergeld"])
    order = form["order"]
    types = form["types"]

    low = (text or "").strip().lower()

    # Befehle
    if low in {"reset", "neu", "start", "neustart"}:
        new_state = {
            "form": "kindergeld",
            "fields": {},
            "kids": [],
            "phase": "collect",
            "idx": 0,
            "lang": lang,
        }
        state_manager.set(user, new_state)
        return t(lang, "ask_" + order[0])

    if low in {"status", "zusammenfassung", "summary"}:
        return save_and_return(_summary(st))

    # --- LLM-Extraktion (mit Fallback auf Regex) ---
    current_kid_index = None
    if "kid_count" in st["fields"] and len(st["kids"]) < st["fields"]["kid_count"]:
        current_kid_index = len(st["kids"])

    # gezielter: welche Felder fehlen aktuell?
    _, missing_now = is_complete(st["form"], st["fields"], st.get("kids", []))

    top_updates = {}
    kids_updates = []

    if LLM_AVAILABLE and os.getenv("OPENAI_API_KEY"):
        try:
            out = extract_updates_from_text(
                text=text or "",
                known_fields=st["fields"],
                missing_fields=missing_now,
                current_kid_index=current_kid_index,
            )
            top_updates = out.get("top_updates") or {}
            kids_updates = out.get("kids_updates") or []
        except Exception as e:
            print("LLM extract error (using regex fallback):", e)

    # Fallback/Ergänzung via Regex
    regex_updates = parse_kv_updates(text, types, current_kid_index)
    for k, v in regex_updates.items():
        # nur füllen, wenn LLM nichts geliefert hat
        if k.startswith("kid_"):
            pass  # unten im Kids-Block
        else:
            top_updates.setdefault(k, v)

    # Top-Level Updates mergen (weiterhin validiert)
    for k, v in (top_updates or {}).items():
        norm = normalize_value(types.get(k, "string"), v)
        if norm is not None:
            st["fields"][k] = norm
            if k in order:
                st["idx"] = max(st["idx"], order.index(k) + 1)

    # Kids-Updates mergen (nur für aktuelles Kind sinnvoll)
    if current_kid_index is not None:
        if not st["kids"] or len(st["kids"]) <= current_kid_index:
            st["kids"].append({})
        kid = st["kids"][-1]

        # aus LLM
        for ku in (kids_updates or []):
            for k, v in ku.items():
                norm = normalize_value(
                    {
                        "kid_name": "string",
                        "kid_dob": "date",
                        "kid_taxid": "taxid",
                        "kid_relation": "enum_relation",
                        "kid_cohab": "bool",
                        "kid_status": "enum_kstatus",
                        "kid_eu_benefit": "bool",
                    }.get(k, "string"),
                    v,
                )
                if norm is not None:
                    kid[k] = norm

        # aus Regex
        for k, v in regex_updates.items():
            if not k.startswith("kid_"):
                continue
            norm = normalize_value(
                {
                    "kid_name": "string",
                    "kid_dob": "date",
                    "kid_taxid": "taxid",
                    "kid_relation": "enum_relation",
                    "kid_cohab": "bool",
                    "kid_status": "enum_kstatus",
                    "kid_eu_benefit": "bool",
                }.get(k, "string"),
                v,
            )
            if norm is not None:
                kid[k] = norm

    # Erstes Feld (Name) direkt konsumieren, falls noch leer
    if st["idx"] == 0 and "full_name" not in st["fields"]:
        name = (text or "").strip()
        bad = {"hallo", "hi", "hey", "hello", "servus", "moin"}
        if name and name.lower() not in bad and len(name.split()) >= 2:
            st["fields"]["full_name"] = name
            st["idx"] = 1
        else:
            return save_and_return(t(lang, "ask_full_name"))

    # Top-Level Felder in Reihenfolge abfragen
    while st["idx"] < len(order):
        field = order[st["idx"]]
        if field not in st["fields"]:
            ftype = types.get(field, "string")
            val = normalize_value(ftype, text or "")
            if val is None:
                return save_and_return(t(lang, "ask_" + field))
            st["fields"][field] = val
            st["idx"] += 1
            if st["idx"] < len(order):
                return save_and_return(t(lang, "ask_" + order[st["idx"]]))
        else:
            st["idx"] += 1

    # Kinder-Abschnitt (Kindergeld)
    if st["form"] == "kindergeld":
        if "kid_count" not in st["fields"]:
            v = normalize_value("int", text or "")
            if v is None:
                return save_and_return(t(lang, "ask_kid_count"))
            st["fields"]["kid_count"] = v
            return save_and_return(t(lang, "ask_kid_name", i=1))

        kid_fields = [
            "kid_name",
            "kid_dob",
            "kid_taxid",
            "kid_relation",
            "kid_cohab",
            "kid_status",
            "kid_eu_benefit",
        ]
        kid_types = ["string", "date", "taxid", "enum_relation", "bool", "enum_kstatus", "bool"]

        while len(st["kids"]) < st["fields"]["kid_count"]:
            # Neues Kind beginnen, wenn noch kein offenes Kind existiert
            if not st["kids"] or all(k in st["kids"][-1] for k in kid_fields):
                st["kids"].append({})
            i = len(st["kids"])  # 1-basiert
            kid = st["kids"][-1]

            for kf, kt in zip(kid_fields, kid_types):
                if kf not in kid:
                    val = normalize_value(kt, text or "")
                    if val is None:
                        return save_and_return(t(lang, "ask_" + kf, i=i))
                    kid[kf] = val
                    # nächstes fehlendes Feld oder nächstes Kind
                    for nf in kid_fields:
                        if nf not in kid:
                            return save_and_return(t(lang, "ask_" + nf, i=i))
                    if len(st["kids"]) < st["fields"]["kid_count"]:
                        return save_and_return(t(lang, "ask_kid_name", i=len(st["kids"]) + 1))

    # --------- Abschluss: prüfen, lokal "PDF" bauen, senden + Link ----------
    ready, missing = is_complete(st["form"], st["fields"], st.get("kids", []))
    if not ready:
        return save_and_return(t(lang, "ask_" + missing[0]))

    base = os.getenv("APP_BASE_URL", "").rstrip("/")
    if not base.startswith("http"):
        base = "https://" + base

    payload = {"form": st["form"], "data": {"fields": st["fields"], "kids": st.get("kids", [])}}

    # 1) Lokale Datei erzeugen (JSON-Platzhalter als .pdf)
    try:
        fid = f"{st['form']}-{uuid.uuid4().hex}.pdf"
        path = ART_DIR / fid
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        url = f"{base}/artifact/{fid}"
    except Exception as e:
        print("PDF build error (local):", e)
        return save_and_return("Ich konnte die Datei gerade nicht erzeugen. Versuch es bitte nochmal oder gib mir kurz Bescheid.")

    # 2) Warmup (optional)
    try:
        with httpx.Client(timeout=15) as c:
            _ = c.get(url, headers={"Connection": "keep-alive"})
    except Exception as w:
        print("Warmup warning:", w)

    # 3) Dokument senden; wenn das klemmt, schicken wir den Link im Text
    from app.providers import send_twilio_document

    doc_sent = False
    try:
        send_twilio_document(user, url, caption="Kindergeld-Antrag (Entwurf)")
        doc_sent = True
    except Exception as e:
        print("Doc send failed:", e)

    st["phase"] = "done"
    
    if doc_sent:
        return save_and_return(
            "Top, ich habe deinen Kindergeld-Antrag ausgefüllt und als PDF gesendet.\n"
            f"Falls der Anhang nicht angezeigt wird, nutze diesen Link: {url}"
        )
    else:
        return save_and_return(f"Ich habe deinen Kindergeld-Antrag erstellt. Hier ist der Download-Link: {url}")
