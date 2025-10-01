# app/orchestrator.py
import json, re, os, httpx
from pathlib import Path
from app.validators import normalize_value, is_complete

# --------- State (Demo) ---------
STATE = {}
BASE = Path(__file__).resolve().parent

def _load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))

# --------- Locales ---------
LOCALES = {
    "de": _load_json(BASE / "locales" / "de.json"),
    "en": _load_json(BASE / "locales" / "en.json"),
    "sq": _load_json(BASE / "locales" / "sq.json"),
}

# --------- Forms ---------
def load_form(name: str):
    return _load_json(BASE / "forms" / f"{name}.json")

FORMS = {
    "kindergeld": load_form("kindergeld"),
    # "wohngeld": load_form("wohngeld"),
}

def ensure_state(user: str):
    STATE.setdefault(user, {
        "form": "kindergeld",
        "fields": {},
        "kids": [],
        "phase": "collect",
        "idx": 0,
        "lang": "de",
    })
    return STATE[user]

def t(lang: str, key: str, **kw):
    return LOCALES.get(lang, LOCALES["de"]).get(key, key).format(**kw)

# --------- Synonyme für freie Angabe/Korrektur ---------
TOP_SYNONYMS = {
    "full_name":    [r"voller\s+name", r"^name$|vor-?\s*und\s*nachname"],
    "dob":          [r"geburtsdatum|geburtstag|dob"],
    "addr_street":  [r"adresse|anschrift|straße|strasse|str\."],
    "addr_plz":     [r"plz|postleitzahl|postal\s*code"],
    "addr_city":    [r"ort|stadt|city"],
    "taxid_parent": [r"steuer[-\s]?id|idnr\.?|idnr|steuerid"],
    "iban":         [r"iban"],
    "marital":      [r"familienstand|marital"],
    "citizenship":  [r"staatsangeh(?:ö|oe)rigkeit|citizenship"],
    "employment":   [r"besch(?:ä|a)ftigung|job|occupation|beruf"],
    "start_month":  [r"beginn|start(?:monat)?|ab\s+monat|monat"],
    "kid_count":    [r"kinderanzahl|anzahl\s+kinder|^kinder$"],
}
KID_SYNONYMS = {
    "kid_name":       [r"name(?:\s*kind)?|voller\s+name"],
    "kid_dob":        [r"geburtsdatum|geburtstag|dob"],
    "kid_taxid":      [r"steuer[-\s]?id|idnr\.?|idnr|steuerid"],
    "kid_relation":   [r"verwandtschaft|beziehung|relation"],
    "kid_cohab":      [r"haushalt|wohnt\s*(?:mit)?|cohab"],
    "kid_status":     [r"status|schule|ausbildung|studium|arbeitssuchend|unter_6"],
    "kid_eu_benefit": [r"eu-?leistung|eu\s*benefit|leistungen\s*im\s*ausland"],
}

def parse_kv_updates(text: str, form_types: dict, current_kid_index: int | None = None):
    updates = {}
    if not text:
        return updates

    # Top-Level
    for key, syns in TOP_SYNONYMS.items():
        for syn in syns:
            m = re.search(rf"\b{syn}\b\s*[:\-]?\s*([^\n;,]+)", text, re.IGNORECASE)
            if m:
                raw = m.group(1).strip()
                val = normalize_value(form_types.get(key, "string"), raw)
                if val is not None:
                    updates[key] = val
                    break

    # „Nackte“ Muster
    if "iban" not in updates:
        m = re.search(r"\bDE[0-9 ]{20,}\b", text, re.IGNORECASE)
        if m:
            updates["iban"] = re.sub(r"\s+", "", m.group(0)).upper()
    if "addr_plz" not in updates:
        m = re.search(r"\b\d{5}\b", text)
        if m and normalize_value("plz", m.group(0)):
            updates["addr_plz"] = m.group(0)

    # Aktuelles Kind
    if current_kid_index is not None:
        kid_types = {
            "kid_name":"string","kid_dob":"date","kid_taxid":"taxid",
            "kid_relation":"enum_relation","kid_cohab":"bool",
            "kid_status":"enum_kstatus","kid_eu_benefit":"bool"
        }
        for key, syns in KID_SYNONYMS.items():
            for syn in syns:
                m = re.search(rf"\b{syn}\b\s*[:\-]?\s*([^\n;,]+)", text, re.IGNORECASE)
                if m:
                    raw = m.group(1).strip()
                    val = normalize_value(kid_types[key], raw)
                    if val is not None:
                        updates[key] = val
                        break
    return updates

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
        f"Kinder: {f.get('kid_count','-')}",
    ]
    for i, k in enumerate(kids, 1):
        lines.append(f"  #{i} {k.get('kid_name','-')} | {k.get('kid_dob','-')} | Steuer-ID: {k.get('kid_taxid','-')}")
    return "\n".join(lines)

# --------- Hauptfunktion ---------
def handle_message(user: str, text: str, lang: str = "de") -> str:
    st = ensure_state(user)
    st["lang"] = lang
    form = FORMS.get(st["form"], FORMS["kindergeld"])
    order = form["order"]
    types = form["types"]

    low = (text or "").strip().lower()

    # Befehle
    if low in {"reset","neu","start","neustart"}:
        STATE[user] = {"form":"kindergeld","fields":{},"kids":[],"phase":"collect","idx":0,"lang":lang}
        return t(lang, "ask_" + order[0])
    if low in {"status","zusammenfassung","summary"}:
        return _summary(st)

    # Freie Korrekturen
    current_kid_index = None
    if "kid_count" in st["fields"] and len(st["kids"]) < st["fields"]["kid_count"]:
        current_kid_index = len(st["kids"])
    updates = parse_kv_updates(text or "", types, current_kid_index)
    for k, v in updates.items():
        if k.startswith("kid_"):
            if len(st["kids"]) == 0 or len(st["kids"]) <= current_kid_index:
                st["kids"].append({})
            st["kids"][-1][k] = v
        else:
            st["fields"][k] = v
            if k in order:
                st["idx"] = max(st["idx"], order.index(k) + 1)

    # Erstes Feld (Name) direkt verarbeiten
    if st["idx"] == 0 and "full_name" not in st["fields"]:
        name = (text or "").strip()
        bad = {"hallo","hi","hey","hello","servus","moin"}
        if name and name.lower() not in bad and len(name.split()) >= 2:
            st["fields"]["full_name"] = name
            st["idx"] = 1
        else:
            return t(lang, "ask_full_name")

    # Top-Level Felder abarbeiten
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
                return t(lang, "ask_" + order[st["idx"]])
        else:
            st["idx"] += 1

    # Kinder
    if st["form"] == "kindergeld":
        if "kid_count" not in st["fields"]:
            v = normalize_value("int", text or "")
            if v is None:
                return t(lang, "ask_kid_count")
            st["fields"]["kid_count"] = v
            return t(lang, "ask_kid_name", i=1)

        kid_fields = ["kid_name","kid_dob","kid_taxid","kid_relation","kid_cohab","kid_status","kid_eu_benefit"]
        kid_types  = ["string","date","taxid","enum_relation","bool","enum_kstatus","bool"]

        while len(st["kids"]) < st["fields"]["kid_count"]:
            if len(st["kids"]) == 0 or all(k in st["kids"][-1] for k in kid_fields):
                st["kids"].append({})
            i = len(st["kids"])
            kid = st["kids"][-1]
            for kf, kt in zip(kid_fields, kid_types):
                if kf not in kid:
                    val = normalize_value(kt, text or "")
                    if val is None:
                        return t(lang, "ask_"+kf, i=i)
                    kid[kf] = val
                    for nf in kid_fields:
                        if nf not in kid:
                            return t(lang, "ask_"+nf, i=i)
                    if len(st["kids"]) < st["fields"]["kid_count"]:
                        return t(lang, "ask_kid_name", i=len(st["kids"])+1)

        # --------- Abschluss: prüfen, PDF bauen, senden + Link zurückgeben ----------
    ready, missing = is_complete(st["form"], st["fields"], st.get("kids", []))
    if not ready:
        return t(lang, "ask_" + missing[0])

    base = os.getenv("APP_BASE_URL", "").rstrip("/")
    if not base.startswith("http"):
        base = "https://" + base

    payload = {"form": st["form"], "data": {"fields": st["fields"], "kids": st.get("kids", [])}}

    # 1) PDF bauen (nur dieser Schritt darf hart fehlschlagen)
    try:
        with httpx.Client(timeout=30) as c:
            res = c.post(f"{base}/make-pdf", json=payload)
            res.raise_for_status()
            url = res.json()["url"]
    except Exception as e:
        print("PDF build error:", e)
        return "Ich konnte die Datei gerade nicht erzeugen. Versuch es bitte nochmal oder gib mir kurz Bescheid."

    # 2) Datei „anwärmen“, damit Twilio sie schneller laden kann (Fehler ignorieren)
    try:
        with httpx.Client(timeout=30) as c:
            _ = c.get(url, headers={"Connection": "keep-alive"})
    except Exception as w:
        print("Warmup warning:", w)

    # 3) Anhang senden (Timeouts werden NICHT mehr nach außen gegeben)
    doc_sent = False
    try:
        from app.providers import send_twilio_document
        send_twilio_document(user, url, caption="Kindergeld-Antrag (Entwurf)")
        doc_sent = True
    except Exception as e:
        print("Doc send failed:", e)

    st["phase"] = "done"

    # 4) Immer Text-Antwort zurück – inkl. Link (falls Anhang klemmt, hat der Nutzer den Link)
    if doc_sent:
        return f"Top, ich habe deinen Kindergeld-Antrag ausgefüllt und als PDF hier im Chat gesendet.\nFalls der Anhang nicht angezeigt wird, nutze diesen Link: {url}"
    else:
        return f"Ich habe deinen Kindergeld-Antrag erstellt. Hier ist der Download-Link: {url}"
