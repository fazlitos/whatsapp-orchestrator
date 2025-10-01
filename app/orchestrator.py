# app/orchestrator.py
import json, re, os, httpx
from pathlib import Path
from app.validators import normalize_value, is_complete

# ---------- State (Demo: In-Memory) ----------
STATE = {}

BASE = Path(__file__).resolve().parent

def _load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))

# ---------- Mehrsprachige Prompts ----------
LOCALES = {
    "de": _load_json(BASE / "locales" / "de.json"),
    "en": _load_json(BASE / "locales" / "en.json"),
    "sq": _load_json(BASE / "locales" / "sq.json"),
}

# ---------- Formular-Registry ----------
def load_form(name: str):
    return _load_json(BASE / "forms" / f"{name}.json")

FORMS = {
    "kindergeld": load_form("kindergeld"),
    # weitere Formulare später:
    # "wohngeld": load_form("wohngeld"),
}

# ---------- Helpers ----------
def ensure_state(user: str):
    STATE.setdefault(user, {
        "form": "kindergeld",
        "fields": {},        # Top-Level Felder
        "kids": [],          # Liste pro Kind
        "phase": "collect",
        "idx": 0,            # Index in order[]
        "lang": "de"
    })
    return STATE[user]

def t(lang: str, key: str, **kw):
    return LOCALES.get(lang, LOCALES["de"]).get(key, key).format(**kw)

# Synonyme für freie Korrekturen / "Feld: Wert"
TOP_SYNONYMS = {
    "full_name":      [r"voller\s+name", r"name", r"vor-?\s*und\s*nachname"],
    "dob":            [r"geburtsdatum", r"dob", r"geburtstag"],
    "addr_street":    [r"(?:straße|strasse|str\.?|adresse|anschrift)"],
    "addr_plz":       [r"(?:plz|postleitzahl|postal\s*code)"],
    "addr_city":      [r"(?:ort|stadt|city)"],
    "taxid_parent":   [r"(?:steuer[-\s]?id|idnr\.?|idnr|steuerid)"],
    "iban":           [r"iban"],
    "marital":        [r"(?:familienstand|stand|marital)"],
    "citizenship":    [r"(?:staatsangeh(?:ö|oe)rigkeit|citizenship)"],
    "employment":     [r"(?:besch(?:ä|a)ftigung|job|occupation|beruf)"],
    "start_month":    [r"(?:beginn|start(?:monat)?|ab\s+monat|monat)"],
    "kid_count":      [r"(?:kinderanzahl|anzahl\s+kinder|kinder)"],
}

KID_SYNONYMS = {
    "kid_name":       [r"(?:name(?:\s*kind)?|voller\s+name)"],
    "kid_dob":        [r"(?:geburtsdatum|dob|geburtstag)"],
    "kid_taxid":      [r"(?:steuer[-\s]?id|idnr\.?|idnr|steuerid)"],
    "kid_relation":   [r"(?:verwandtschaft|beziehung|relation)"],
    "kid_cohab":      [r"(?:haushalt|wohnt\s*(?:mit)?|cohab)"],
    "kid_status":     [r"(?:status|schule|ausbildung|studium|arbeitssuchend|unter_6)"],
    "kid_eu_benefit": [r"(?:eu-?leistung|eu\s*benefit|leistungen\s*im\s*ausland)"],
}

def _lines(text: str):
    if not text: return []
    # split nach Zeilen, Strichpunkten oder Doppelpunkten (lässt "feld: wert" stehen)
    raw = re.split(r"[\n]+|(?<!https?):;|；", text)  # primär Zeilen
    # aber zusätzlich einzelne „feld: wert“-Paare herausziehen
    out = []
    for chunk in raw:
        parts = re.split(r"\s{2,}|\s\|\s", chunk.strip())  # harte Trennungen
        out += [p for p in parts if p]
    return out

def parse_kv_updates(text: str, form_types: dict, current_kid_index: int | None = None):
    """
    Sucht in freiem Text nach 'Feld: Wert' oder 'Feld Wert' Mustern und gibt aktualisierte Felder zurück.
    """
    updates = {}

    # 1) Allgemeine Top-Level Felder
    for key, syns in TOP_SYNONYMS.items():
        if key == "kid_count":  # separat sinnvoll
            syns_here = syns
        else:
            syns_here = syns
        for syn in syns_here:
            # Muster: "feld: wert" oder "feld wert"
            m = re.search(rf"\b{syn}\b\s*[:\-]?\s*([^\n;,]+)", text, re.IGNORECASE)
            if m:
                val_raw = m.group(1).strip()
                val = normalize_value(form_types.get(key, "string"), val_raw)
                if val is not None:
                    updates[key] = val
                    break

    # Spezialfälle ohne Schlüsselwort (IBAN/PLZ/TaxID als nackte Werte)
    if "iban" not in updates:
        m = re.search(r"\bDE\d{20}\b", text.replace(" ", "").upper())
        if m:
            updates["iban"] = m.group(0)
    if "addr_plz" not in updates:
        m = re.search(r"\b\d{5}\b", text)
        if m:
            if normalize_value("plz", m.group(0)):
                updates["addr_plz"] = m.group(0)

    # 2) Kinder-Felder (nur für das aktuell zu füllende Kind sinnvoll)
    if current_kid_index is not None:
        for key, syns in KID_SYNONYMS.items():
            for syn in syns:
                m = re.search(rf"\b{syn}\b\s*[:\-]?\s*([^\n;,]+)", text, re.IGNORECASE)
                if m:
                    val_raw = m.group(1).strip()
                    vtype = {
                        "kid_name":"string","kid_dob":"date","kid_taxid":"taxid",
                        "kid_relation":"enum_relation","kid_cohab":"bool",
                        "kid_status":"enum_kstatus","kid_eu_benefit":"bool"
                    }[key]
                    val = normalize_value(vtype, val_raw)
                    if val is not None:
                        updates[key] = val
                        break

    return updates

def _next_missing_top(order, fields):
    for f in order:
        if f not in fields:
            return f
    return None

def _summary(st):
    f = st["fields"]; kids = st.get("kids", [])
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
    ]
    if f.get("kid_count") is not None:
        lines.append(f"Kinder: {f['kid_count']}")
    for i, k in enumerate(kids, 1):
        lines.append(f"  #{i} {k.get('kid_name','-')} | {k.get('kid_dob','-')} | Steuer-ID: {k.get('kid_taxid','-')}")
    return "\n".join(lines)

# ---------- Hauptlogik ----------
def handle_message(user: str, text: str, lang: str = "de") -> str:
    st = ensure_state(user)
    st["lang"] = lang
    form = FORMS.get(st["form"], FORMS["kindergeld"])
    order = form["order"]
    types = form["types"]

    low = (text or "").strip().lower()

    # Befehle
    if low in {"reset", "neu", "start", "neustart"}:
        STATE[user] = {"form":"kindergeld","fields":{},"kids":[],"phase":"collect","idx":0,"lang":lang}
        return t(lang, "ask_" + order[0])
    if low in {"status","zusammenfassung","summary"}:
        return _summary(st)

    # 0) Freie Korrekturen / mehrere Angaben in einem Text (Top-Level + aktuelles Kind)
    current_kid_index = None
    if "kid_count" in st["fields"] and len(st["kids"]) < st["fields"]["kid_count"]:
        current_kid_index = len(st["kids"])  # 0-basiert

    updates = parse_kv_updates(text or "", types, current_kid_index=current_kid_index)
    # apply updates
    for k, v in updates.items():
        if k.startswith("kid_"):
            # stelle Kind-Dict sicher
            if len(st["kids"]) == 0 or len(st["kids"]) <= current_kid_index:
                st["kids"].append({})
            st["kids"][-1][k] = v
        else:
            st["fields"][k] = v
            # Index nachziehen, falls wir ein früheres Feld gesetzt haben
            if k in order:
                st["idx"] = max(st["idx"], order.index(k) + 1)

    # 1) Erster Durchgang: falls noch nichts erfasst wurde (Name), versuche direkten Wert
    if st["idx"] == 0 and "full_name" not in st["fields"]:
        name = (text or "").strip()
        bad = {"hallo","hi","hey","hello","servus","moin"}
        if name and name.lower() not in bad and len(name.split()) >= 2:
            st["fields"]["full_name"] = name
            st["idx"] = 1
        else:
            return t(lang, "ask_full_name")

    # 2) Top-Level Felder in Reihenfolge einsammeln
    while st["idx"] < len(order):
        field = order[st["idx"]]
        if field not in st["fields"]:
            ftype = types.get(field, "string")
            val = normalize_value(ftype, text or "")
            if val is None:
                return t(lang, "ask_" + field)
            st["fields"][field] = val
            st["idx"] += 1
            if st["idx"] < len(order):
                nxt = order[st["idx"]]
                return t(lang, "ask_" + nxt)
        else:
            st["idx"] += 1

    # 3) Kind(er) einsammeln
    if st["form"] == "kindergeld":
        if "kid_count" not in st["fields"]:
            v = normalize_value("int", text or "")
            if v is None:
                return t(lang, "ask_kid_count")
            st["fields"]["kid_count"] = v
            return t(lang, "ask_kid_name", i=1)

        kid_fields = ["kid_name","kid_dob","kid_taxid","kid_relation","kid_cohab","kid_status","kid_eu_benefit"]
        kid_types  = ["string","date","taxid","enum_relation","bool","enum_kstatus","bool"]

        # solange Kinder fehlen, arbeite aktuelles Kind ab
        while len(st["kids"]) < st["fields"]["kid_count"]:
            if len(st["kids"]) == 0 or len(st["kids"]) <= (len(st["kids"]) or 0):
                # falls der aktuelle dict fehlt
                if len(st["kids"]) == 0 or st["kids"] and all(k in st["kids"][-1] for k in kid_fields):
                    st["kids"].append({})

            i = len(st["kids"])  # 1-basiert
            kid = st["kids"][-1]

            for kfield, ktype in zip(kid_fields, kid_types):
                if kfield not in kid:
                    val = normalize_value(ktype, text or "")
                    if val is None:
                        return t(lang, "ask_"+kfield, i=i)
                    kid[kfield] = val
                    # nächstes noch fehlendes Feld?
                    for nf in kid_fields:
                        if nf not in kid:
                            return t(lang, "ask_"+nf, i=i)
                    # aktuelles Kind fertig → weiteres?
                    if len(st["kids"]) < st["fields"]["kid_count"]:
                        return t(lang, "ask_kid_name", i=len(st["kids"])+1)

# 4) Abschlussprüfung
ready, missing = is_complete(st["form"], st["fields"], st.get("kids", []))
if not ready:
    return t(lang, "ask_" + missing[0])

# 5) PDF erzeugen
base = os.getenv("APP_BASE_URL", "").rstrip("/")
if not base.startswith("http"):
    base = "https://" + base

payload = {"form": st["form"], "data": {"fields": st["fields"], "kids": st.get("kids", [])}}

try:
    # PDF bauen
    with httpx.Client(timeout=30) as c:
        res = c.post(f"{base}/make-pdf", json=payload)
        res.raise_for_status()
        url = res.json()["url"]

    # Warm-up: Datei einmal selbst abrufen (hält Render „wach“ & TLS warm)
    try:
        with httpx.Client(timeout=30) as c:
            _ = c.get(url, headers={"Connection": "keep-alive"})
    except Exception as e:
        print("Warmup fetch warning:", e)

    # Dokument senden
    from app.providers import send_twilio_document, send_whatsapp_text
    try:
        send_twilio_document(user, url, caption="Kindergeld-Antrag (Entwurf)")
    except Exception as e:
        # Fallback: Link als Text schicken (falls Twilio-Timeout)
        print("Doc send timeout/failure, sending link as text:", e)
        send_whatsapp_text(user, f"Hier ist dein PDF: {url}")

    st["phase"] = "done"
    return "Top, ich habe deinen Kindergeld-Antrag ausgefüllt und als PDF hier im Chat gesendet."
except Exception as e:
    print("PDF/Send error:", e)
    return "Ich konnte die Datei gerade nicht erzeugen/senden. Versuch es bitte nochmal oder gib mir kurz Bescheid."
