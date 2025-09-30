import json, re
from pathlib import Path
from app.validators import normalize_value, is_complete

# In-Memory State (für Tests). In Produktion: Redis/DB verwenden.
STATE = {}

def _load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))

BASE = Path(__file__).resolve().parent

LOCALES = {
    "de": _load_json(BASE / "locales" / "de.json"),
    "en": _load_json(BASE / "locales" / "en.json"),
    "sq": _load_json(BASE / "locales" / "sq.json"),
}

def load_form(name: str):
    return _load_json(BASE / "forms" / f"{name}.json")

FORMS = {
    "kindergeld": load_form("kindergeld"),
    # weitere Formulare einfach ergänzen:
    # "wohngeld": load_form("wohngeld"),
}

def ensure_state(user: str):
    STATE.setdefault(user, {
        "form": "kindergeld",
        "fields": {},
        "kids": [],
        "phase": "consent",
        "idx": 0,
        "kid_idx": 0,
        "lang": "de"
    })
    return STATE[user]

def t(lang: str, key: str, **kw):
    return LOCALES.get(lang, LOCALES["de"]).get(key, key).format(**kw)

def handle_message(user: str, text: str, lang: str = "de") -> str:
    st = ensure_state(user)
    st["lang"] = lang

    low = (text or "").lower()
    # Formular-Wechsel per Keyword
    if "wohngeld" in low:
        st.update({"form":"wohngeld","fields":{}, "kids":[], "idx":0, "kid_idx":0, "phase": "consent"})
        return t(lang, "switched_form", form="Wohngeld")

    form = FORMS.get(st["form"], FORMS["kindergeld"])

    # 1) Einwilligung
    if st["phase"] == "consent":
        v = normalize_value("bool", text)
        if v is True:
            st["phase"] = "collect"
        elif v is False:
            return t(lang, "consent_required")
        else:
            return t(lang, "consent")

    # 2) Top-Level Felder (fixe Reihenfolge)
    order = form["order"]  # z. B. ["full_name","dob",...,"start_month"]
    # Falls neu begonnen wird, frage das erste Feld:
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

    # 3) Kind(er) für Kindergeld
    if st["form"] == "kindergeld":
        if "kid_count" not in st["fields"]:
            v = normalize_value("int", text)
            if v is None:
                return t(lang, "ask_kid_count")
            st["fields"]["kid_count"] = v
            st["kid_idx"] = 0
            return t(lang, "ask_kid_name", i=1)

        # aktuelles Kind füllen
        kid_fields = ["kid_name","kid_dob","kid_taxid","kid_relation","kid_cohab","kid_status","kid_eu_benefit"]
        kid_types  = ["string","date","taxid","enum_relation","bool","enum_kstatus","bool"]

        i = len(st["kids"]) + 1
        if len(st["kids"]) < st["fields"]["kid_count"]:
            # stelle sicher, dass ein dict für das aktuelle Kind existiert
            if len(st["kids"]) == 0 or len(st["kids"]) < i:
                st["kids"].append({})

            # herausfinden, welches Feld beim aktuellen Kind noch fehlt
            for kfield, ktype in zip(kid_fields, kid_types):
                if kfield not in st["kids"][-1]:
                    val = normalize_value(ktype, text)
                    if val is None:
                        return t(lang, "ask_" + kfield, i=i)
                    st["kids"][-1][kfield] = val
                    # nächstes Feld oder nächstes Kind
                    # prüfe, ob noch ein Feld fehlt
                    for next_field in kid_fields:
                        if next_field not in st["kids"][-1]:
                            return t(lang, "ask_" + next_field, i=i)
                    # Kind komplett → ggf. nächstes Kind starten
                    if len(st["kids"]) < st["fields"]["kid_count"]:
                        return t(lang, "ask_kid_name", i=len(st["kids"])+1)

    # 4) Abschlussprüfung
    ready, missing = is_complete(st["form"], st["fields"], st.get("kids", []))
    if ready:
        st["phase"] = "ready"
        return t(lang, "ready_submit")
    else:
        # frage das erste fehlende Feld erneut
        return t(lang, "ask_" + missing[0])
