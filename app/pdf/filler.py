from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, BooleanObject
from pathlib import Path
import json, os, re, tempfile

ROOT = Path(__file__).resolve().parent
TEMPLATES = ROOT / "templates"
MAPPING_DIR = ROOT / "mapping"
MAPPING_DIR.mkdir(parents=True, exist_ok=True)

def template_path(name="kg1"):
    return str(TEMPLATES / "kg1-antrag.pdf")

def list_fields(pdf_path: str):
    reader = PdfReader(pdf_path)
    fields = reader.get_form_text_fields() or {}
    # pypdf liefert nur Textfelder; Checkboxes etc. sind nicht immer gelistet.
    return sorted(fields.keys())

def _split_taxid(taxid: str):
    # 11 Ziffern -> 4-3-4 (wie im Vordruck segmentiert)
    digits = re.sub(r"\D","", taxid or "")
    return [digits[0:4], digits[4:7], digits[7:11], ""] if len(digits) == 11 else ["","","",""]

def _split_name(full: str):
    full = (full or "").strip()
    if not full: return {"Vorname":"", "Familienname":""}
    parts = full.split()
    return {"Vorname": " ".join(parts[:-1]) or parts[0], "Familienname": parts[-1]}

def load_mapping():
    p = MAPPING_DIR / "kg1.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    # erste Vorlage (Passe Feldnamen später nach /pdf/fields an!)
    mapping = {
        "person": {
            "taxid_parts": ["TaxID_T1","TaxID_T2","TaxID_T3","TaxID_T4"],
            "vorname": "Vorname",
            "nachname": "Familienname",
            "geburtsdatum": "Geburtsdatum",
            "geburtsort": "Geburtsort",
            "staatsangehoerigkeit": "Staatsangehoerigkeit",
            "anschrift": "Anschrift"
        },
        "bank": {
            "iban": "IBAN",
            "kontoinhaber_checkbox": "Konto_Inhaber_Antragsteller"  # Checkbox
        },
        "meta": {
            "anzahl_anlage_kind": "Anzahl_Anlage_Kind"
        }
    }
    p.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    return mapping

def fill_kindergeld(fields: dict, kids: list, out_dir: str = None) -> str:
    """
    fields: deine gesammelten Top-Level Felder
    kids:   Liste mit Kinder-Dictionaries (wir tragen vorerst nur die Anzahl ein)
    returns: Pfad zur erzeugten PDF
    """
    pdf_in = template_path()
    reader = PdfReader(pdf_in)
    writer = PdfWriter()

    # alle Seiten übernehmen
    for p in reader.pages:
        writer.add_page(p)

    # NeedAppearances setzen, damit Viewer die Einträge anzeigen
    if "/AcroForm" in writer._root_object:
        writer._root_object["/AcroForm"].update(
            {NameObject("/NeedAppearances"): BooleanObject(True)}
        )
    else:
        writer._root_object.update({
            NameObject("/AcroForm"): reader.trailer["/Root"]["/AcroForm"],
        })
        writer._root_object["/AcroForm"].update(
            {NameObject("/NeedAppearances"): BooleanObject(True)}
        )

    mp = load_mapping()

    # ---- Werte vorbereiten
    # Name
    nm = _split_name(fields.get("full_name",""))
    # Tax-ID
    t1,t2,t3,t4 = _split_taxid(fields.get("taxid_parent",""))
    # Adresse als ein Feld (falls Formular Einzelfelder hat, bitte in mapping aufsplitten)
    anschrift = f"{fields.get('addr_street','')}, {fields.get('addr_plz','')} {fields.get('addr_city','')}"

    values = {
        mp["person"]["vorname"]: nm["Vorname"],
        mp["person"]["nachname"]: nm["Familienname"],
        mp["person"]["geburtsdatum"]: fields.get("dob",""),
        mp["person"]["geburtsort"]: fields.get("birthplace",""),
        mp["person"]["staatsangehoerigkeit"]: fields.get("citizenship",""),
        mp["person"]["anschrift"]: anschrift,
        mp["bank"]["iban"]: fields.get("iban",""),
        mp["meta"]["anzahl_anlage_kind"]: str(fields.get("kid_count", len(kids) or "")),
    }

    tax_targets = mp["person"]["taxid_parts"]
    for part, val in zip(tax_targets, [t1,t2,t3,t4]):
        if part: values[part] = val

    # ---- Felder auf jeder Seite aktualisieren
    for page in writer.pages:
        try:
            writer.update_page_form_field_values(page, values)
        except Exception:
            pass

    # (Optional) Checkbox „Kontoinhaber ist Antragsteller“ setzen
    # Manche PDFs erwarten '/Yes' oder '/On'; pypdf setzt Textfelder leichter als Checkboxen.
    # Wenn dein Feldname korrekt ist, reicht oft "Yes".
    try:
        writer.update_page_form_field_values(writer.pages[0], {mp["bank"]["kontoinhaber_checkbox"]: "Yes"})
    except Exception:
        pass

    # Ausgabe
    if not out_dir:
        out_dir = tempfile.gettempdir()
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    out_path = str(Path(out_dir) / f"kg1-{os.urandom(6).hex()}.pdf")
    with open(out_path, "wb") as fp:
        writer.write(fp)
    return out_path
