# app/orchestrator.py
import json
from pathlib import Path
import os, httpx
from app.validators import normalize_value, is_complete

# In-Memory-State (für Tests). In Produktion: Redis/DB.
STATE = {}

BASE = Path(__file__).resolve().parent

def _load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))

# Mehrsprachige Prompts laden
LOCALES = {
    "de": _load_json(BASE / "locales" / "de.json"),
    "en": _load_json(BASE / "locales" / "en.json"),
    "sq": _load_json(BASE / "locales" / "sq.json"),
}

# Formular-Definitionen laden
def load_form(name: str):
    return _load_json(BASE / "forms" / f"{name}.json")

FORMS = {
    "kindergeld": load_form("kindergeld"),
    # weitere Formulare später:
    # "wohngeld": load_form("wohngeld"),
}

def ensure_state(user: str):
    STATE.setdefault(user, {
        "form": "kindergeld",
        "fields": {},
        "kids": [],
        "phase": "collect",
        "idx": 0,         # Index top-level order
        "kid_idx": 0,     # Index innerhalb eines Kindes
        "lang": "de"
    })
    return STATE[user]

def t(lang: str, key: str, **kw):
    return LOCALES.get(lang, LOCALES["de"]).get(key, key).format(**kw)

def handle_message(user: str, text: str, lang: str = "de") -> str:
    st = ensure_state(user)
    st["lang"] = lang

    # Formularwechsel via Keyword (später)
    low = (text or "").lower()
    if "wohngeld" in low:
        st.update({"form":"wohngeld","fields":{}, "kids":[], "idx":0, "kid_idx":0, "phase":"collect"})
        return t(lang, "switched_form", form="Wohngeld")

    form = FORMS.get(st["form"], FORMS["kindergeld"])

    # ---------- Top-Level Felder in der definierten Reihenfolge ----------
    order = form["order"]  # z.B. ["full_name","dob","addr_street",...,"start_month"]
    # erster Prompt, falls noch nichts vorhanden:
    if st["idx"] == 0 and not st["fields"].get(order[0]):
        return t(lang, "ask_" + order[0])

    while st["idx"] < len(order):
        field = order[st["idx"]]
        if field not in st["fields"]:
            ftype = form["types"].get(field, "string")
            val = normalize_value(ftype, text)
            if val is None:
                return t(lang, "ask_" + field)
            st["fields"][field] = val
            st["idx"] += 1
            if st["idx"] < len(order):
                nxt = order[st["idx"]]
                return t(lang, "ask_" + nxt)
        else:
            st["idx"] += 1

    # ---------- Kinder-Loop (Kindergeld-spezifisch) ----------
    if st["form"] == "kindergeld":
        # Anzahl Kinder?
        if "kid_count" not in st["fields"]:
            v = normalize_value("int", text)
            if v is None:
                return t(lang, "ask_kid_count")
            st["fields"]["kid_count"] = v
            st["kid_idx"] = 0
            return t(lang, "ask_kid_name", i=1)

        kid_fields = ["kid_name","kid_dob","kid_taxid","kid_relation","kid_cohab","kid_status","kid_eu_benefit"]
        kid_types  = ["string","date","taxid","enum_relation","bool","enum_kstatus","bool"]

        # weiteres Kind anlegen, wenn nötig
        i = len(st["kids"]) + 1
        if len(st["kids"]) < st["fields"]["kid_count"]:
            if len(st["kids"]) == 0 or len(st["kids"]) < i:
                st["kids"].append({})

            # fehlendes Feld beim aktuellen Kind finden
            for kfield, ktype in zip(kid_fields, kid_types):
                if kfield not in st["kids"][-1]:
                    val = normalize_value(ktype, text)
                    if val is None:
                        return t(lang, "ask_"+kfield, i=i)
                    st["kids"][-1][kfield] = val
                    # nächstes Feld?
                    for nf in kid_fields:
                        if nf not in st["kids"][-1]:
                            return t(lang, "ask_"+nf, i=i)
                    # Kind fertig → nächstes Kind?
                    if len(st["kids"]) < st["fields"]["kid_count"]:
                        return t(lang, "ask_kid_name", i=len(st["kids"])+1)

    # ---------- Abschluss: vollständig? Dann automatisch PDF bauen & senden ----------
    ready, missing = is_complete(st["form"], st["fields"], st.get("kids", []))
    if not ready:
        return t(lang, "ask_"+missing[0])

    # Alles vorhanden → PDF erzeugen und sofort via WhatsApp senden
    base = os.getenv("APP_BASE_URL", "").rstrip("/")
    if not base.startswith("http"):
        base = "https://" + base

    payload = {"form": st["form"], "data": {"fields": st["fields"], "kids": st.get("kids", [])}}

    try:
        with httpx.Client(timeout=30) as c:
            res = c.post(f"{base}/make-pdf", json=payload)
            res.raise_for_status()
            url = res.json()["url"]

        from app.providers import send_twilio_document
        send_twilio_document(user, url, caption="Kindergeld-Antrag (Entwurf)")

        st["phase"] = "done"
        return "Top, ich habe deinen Kindergeld-Antrag ausgefüllt und als PDF hier im Chat gesendet. Bitte prüfen und unterschreiben."
    except Exception as e:
        print("PDF/Send error:", e)
        return "Ich konnte die Datei gerade nicht erzeugen/senden. Versuch es bitte nochmal oder gib mir kurz Bescheid."
