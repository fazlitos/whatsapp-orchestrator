# app/pdf/filler.py
import io
from typing import List, Dict, Any
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from PyPDF2 import PdfReader, PdfWriter

# ---------- Koordinaten-Mapping (gemessen mit Tool) ----------
KG1_MAP = {
    "full_name": {"page": 1, "x": 98, "y": 814, "size": 10},  # Familienname
    "vorname": {"page": 1, "x": 96, "y": 767, "size": 10},  # Vorname
    "dob": {"page": 1, "x": 95, "y": 719, "size": 10},  # Geburtsdatum
    "geburtsort": {"page": 1, "x": 209, "y": 719, "size": 10},  # Geburtsort
    "geschlecht": {"page": 1, "x": 486, "y": 719, "size": 10},  # Geschlecht
    "staatsangehoerigkeit": {"page": 1, "x": 567, "y": 720, "size": 10},  # Staatsangehörigkeit
    "anschrift": {"page": 1, "x": 98, "y": 639, "size": 10},  # Anschrift (komplette Zeile)
    "taxid_1": {"page": 1, "x": 98, "y": 863, "size": 10},  # Steuer-ID Feld 1 (2 Ziffern)
    "taxid_2": {"page": 1, "x": 161, "y": 863, "size": 10},  # Steuer-ID Feld 2 (3 Ziffern)
    "taxid_3": {"page": 1, "x": 250, "y": 864, "size": 10},  # Steuer-ID Feld 3 (3 Ziffern)
    "taxid_4": {"page": 1, "x": 340, "y": 864, "size": 10},  # Steuer-ID Feld 4 (3 Ziffern)
    "marital_ledig": {"page": 1, "x": 98, "y": 566, "size": 10},  # Familienstand: Checkbox LEDIG
    "marital_verheiratet": {"page": 1, "x": 383, "y": 588, "size": 10},  # Familienstand: Checkbox VERHEIRATET
    "marital_geschieden": {"page": 1, "x": 383, "y": 566, "size": 10},  # Familienstand: Checkbox GESCHIEDEN
    "marital_verwitwet": {"page": 1, "x": 383, "y": 545, "size": 10},  # Familienstand: Checkbox VERWITWET
    "marital_lebenspartner": {"page": 1, "x": 531, "y": 589, "size": 10},  # Familienstand: Checkbox LEBENSPARTNER
    "marital_aufgehoben": {"page": 1, "x": 531, "y": 567, "size": 10},  # Familienstand: Checkbox AUFGEHOBEN
    "marital_seit": {"page": 1, "x": 238, "y": 568, "size": 10},  # Familienstand: SEIT (Datum)
    "iban": {"page": 1, "x": 99, "y": 188, "size": 10},  # IBAN (komplette Zeile)
    "bic": {"page": 1, "x": 100, "y": 143, "size": 10},  # BIC (falls Feld vorhanden)
}

# ---------- Helper-Funktionen ----------
def _split_taxid(taxid: str) -> tuple:
    """Teilt Steuer-ID in 4 Teile: 12-345-678-901"""
    taxid = str(taxid).replace(" ", "").replace("-", "")
    if len(taxid) != 11:
        return "", "", "", ""
    return taxid[0:2], taxid[2:5], taxid[5:8], taxid[8:11]

def _get_marital_checkbox(marital: str) -> str:
    """Gibt den Key der richtigen Checkbox zurück"""
    mapping = {
        "ledig": "marital_ledig",
        "verheiratet": "marital_verheiratet",
        "geschieden": "marital_geschieden",
        "verwitwet": "marital_verwitwet",
        "lebenspartnerschaft": "marital_lebenspartner",
        "getrennt": "marital_aufgehoben"
    }
    return mapping.get(str(marital).lower(), "marital_ledig")

def _fmt_date(d: str) -> str:
    """Formatiert Datum zu TT.MM.JJJJ"""
    if not d:
        return ""
    d = str(d).replace("-", ".")
    return d

def _split_name(full_name: str) -> tuple:
    """Teilt 'Vorname Nachname' auf."""
    parts = str(full_name).strip().split()
    if len(parts) >= 2:
        vorname = parts[0]
        nachname = " ".join(parts[1:])
        return vorname, nachname
    return full_name, ""

# ---------- PDF-Overlay-Funktionen ----------
def _make_overlay(page_sizes: List[tuple], instructions: List[Dict[str, Any]]) -> io.BytesIO:
    """Baut ein Mehrseiten-Overlay mit allen Texten."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=page_sizes[0] if page_sizes else letter)
    
    by_page: Dict[int, List[Dict[str, Any]]] = {}
    for ins in instructions:
        by_page.setdefault(ins["page"], []).append(ins)

    for pno, (w, h) in enumerate(page_sizes):
        c.setPageSize((w, h))
        c.setFont("Helvetica", 10)
        for ins in by_page.get(pno, []):
            size = int(ins.get("size", 10))
            c.setFont("Helvetica", size)
            c.drawString(float(ins["x"]), float(ins["y"]), str(ins.get("text", "")))
        c.showPage()
    c.save()
    buf.seek(0)
    return buf

def _merge(template_path: str, overlay_pdf: io.BytesIO) -> bytes:
    """Merged Template mit Overlay."""
    tpl = PdfReader(template_path)
    ovl = PdfReader(overlay_pdf)
    out = PdfWriter()
    for i, page in enumerate(tpl.pages):
        if i < len(ovl.pages):
            page.merge_page(ovl.pages[i])
        out.add_page(page)
    obuf = io.BytesIO()
    out.write(obuf)
    obuf.seek(0)
    return obuf.read()

# ---------- Debug: Grid ----------
def make_grid(template_path: str) -> bytes:
    """Erzeugt Grid-PDF für Koordinaten-Messung."""
    tpl = PdfReader(template_path)
    page_sizes = []
    for p in tpl.pages:
        w = float(p.mediabox.width)
        h = float(p.mediabox.height)
        page_sizes.append((w, h))

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=page_sizes[0])
    for pno, (w, h) in enumerate(page_sizes):
        c.setPageSize((w, h))
        step = 20
        c.setFont("Helvetica", 6)
        for x in range(0, int(w), step):
            c.setStrokeColorRGB(0.85, 0.85, 0.85)
            c.line(x, 0, x, h)
            c.drawString(x + 1, h - 10, str(x))
        for y in range(0, int(h), step):
            c.line(0, y, w, y)
            c.drawString(2, y + 2, str(y))
        c.setFont("Helvetica", 10)
        c.setStrokeColorRGB(1, 0, 0)
        c.drawString(20, h - 20, f"Seite {pno+1} – Koordinatennetz (0,0 unten links)")
        c.showPage()
    c.save()
    buf.seek(0)
    return _merge(template_path, buf)

# ---------- Hauptfunktion: KG1 ausfüllen ----------
def fill_kindergeld(template_path: str, out_path: str, data: Dict[str, Any]) -> None:
    """
    Füllt KG1-Formular mit Daten aus.
    
    Args:
        template_path: Pfad zum KG1-Template
        out_path: Pfad für ausgefülltes PDF
        data: {"fields": {...}, "kids": [...]}
    """
    # 1) Seitengrößen lesen
    tpl = PdfReader(template_path)
    page_sizes = []
    for p in tpl.pages:
        page_sizes.append((float(p.mediabox.width), float(p.mediabox.height)))

    # 2) Instruktionen zusammenstellen
    f = data.get("fields", {})
    instr: List[Dict[str, Any]] = []

    def put(key, text):
        """Fügt Text an Koordinate hinzu."""
        m = KG1_MAP.get(key)
        if not m:
            print(f"DEBUG: Key '{key}' nicht in KG1_MAP")
            return
        instr.append({
            "page": m["page"],
            "x": m["x"],
            "y": m["y"],
            "text": str(text or ""),
            "size": m.get("size", 10)
        })

    # Name (aufteilen falls zusammen)
    full_name = f.get("full_name", "")
    vorname, nachname = _split_name(full_name)
    
    put("full_name", nachname)
    put("vorname", vorname)
    
    # Geburtsdatum
    put("dob", _fmt_date(f.get("dob")))
    
    # Optional: Geburtsort, Geschlecht, Staatsangehörigkeit (falls im Bot gesammelt)
    put("geburtsort", f.get("geburtsort", ""))
    put("geschlecht", f.get("geschlecht", ""))
    put("staatsangehoerigkeit", f.get("citizenship", "deutsch"))
    
    # Anschrift (zusammengesetzt)
    anschrift = f"{f.get('addr_street', '')}, {f.get('addr_plz', '')} {f.get('addr_city', '')}"
    put("anschrift", anschrift.strip(", "))
    
    # Steuer-ID (aufgeteilt)
    taxid_parts = _split_taxid(f.get("taxid_parent", ""))
    put("taxid_1", taxid_parts[0])
    put("taxid_2", taxid_parts[1])
    put("taxid_3", taxid_parts[2])
    put("taxid_4", taxid_parts[3])
    
    # Familienstand (Checkbox + Datum)
    marital = f.get("marital", "ledig")
    checkbox_key = _get_marital_checkbox(marital)
    put(checkbox_key, "X")  # Checkbox ankreuzen
    
    # "seit"-Datum (nur wenn nicht ledig)
    if checkbox_key != "marital_ledig":
        # Falls "marital_seit" in Daten vorhanden, nutze das; sonst leer lassen
        seit = f.get("marital_seit", "")
        if seit:
            put("marital_seit", seit)
    
    # IBAN & BIC
    iban = f.get("iban", "")
    put("iban", iban)
    
    # BIC optional (oft nicht nötig bei deutscher IBAN)
    bic = f.get("bic", "")
    if bic:
        put("bic", bic)
    
    # 3) Overlay bauen & mergen
    overlay = _make_overlay(page_sizes, instr)
    pdf_bytes = _merge(template_path, overlay)

    # 4) Schreiben
    with open(out_path, "wb") as f_out:
        f_out.write(pdf_bytes)
    
    print(f"✅ PDF erstellt: {out_path}")
