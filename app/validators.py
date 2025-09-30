import re, datetime as dt

def normalize_value(ftype: str, text: str):
    s = (text or "").strip()
    if ftype == "bool":
        t = s.lower()
        if t in ["ja","j","yes","y","po","true"]: return True
        if t in ["nein","n","no","jo","false"]: return False
        return None
    if ftype == "date":
        m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", s.replace(" ", ""))
        if not m: return None
        d, mo, y = map(int, m.groups())
        try: dt.date(y, mo, d)
        except: return None
        return f"{d:02d}.{mo:02d}.{y}"
    if ftype == "plz":
        v = re.sub(r"\D","", s)
        return v if re.fullmatch(r"\d{5}", v) else None
    if ftype == "iban":
        v = s.replace(" ","").upper()
        return v if re.fullmatch(r"DE\d{20}", v) else None
    if ftype == "taxid":
        v = re.sub(r"\D","", s)
        return v if re.fullmatch(r"\d{11}", v) else None
    if ftype == "int":
        return int(s) if s.isdigit() else None
    if ftype == "enum_relation":
        t = s.lower()
        return t if t in ["leiblich","adoptiert","pflegekind","stiefkind"] else None
    if ftype == "enum_kstatus":
        t = s.lower()
        return t if t in ["schulpflichtig","ausbildung","studium","arbeitssuchend","unter_6"] else None
    if ftype == "monat":
        m = re.match(r"^(0?[1-9]|1[0-2])\.(\d{4})$", s)
        return f"{int(m.group(1)):02d}.{m.group(2)}" if m else None
    return s if s else None

def is_complete(form: str, fields: dict, kids: list):
    if form == "kindergeld":
        required = ["full_name","dob","addr_street","addr_plz","addr_city",
                    "taxid_parent","iban","marital","citizenship","employment","start_month","kid_count"]
        missing = [f for f in required if f not in fields]
        if missing: return False, missing
        if len(kids) != fields["kid_count"]:
            return False, ["kid_name"]
        return True, []
    # default: alle in order müssen vorhanden sein
    return True, []
