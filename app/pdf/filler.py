# app/pdf/filler.py
import io
from typing import List, Dict, Any
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from PyPDF2 import PdfReader, PdfWriter

# ---------- Kleine Zeichen-Primitive ----------
def _make_overlay(page_sizes: List[tuple], instructions: List[Dict[str, Any]]) -> io.BytesIO:
    """
    Baut ein Mehrseiten-Overlay (eine PDF) mit allen Texten.
    page_sizes: [(w,h), ...] aus dem Template
    instructions: [{page:int, x:float, y:float, text:str, size:int}, ...]
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=page_sizes[0] if page_sizes else letter)
    
    # Pro Seite zeichnen
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

# ---------- Debug: Grid über Template legen ----------
def make_grid(template_path: str) -> bytes:
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
        c.drawString(20, h - 20, f"Seite {pno+1} – Koordinatennetz (0,0 unten links, Einheiten: pt)")
        c.showPage()
    c.save()
    buf.seek(0)
    return _merge(template_path, buf)

# ---------- Mapping & Fülllogik Kindergeld ----------
# Koordinaten basierend auf Grid-PDF (gemessen)
KG1_MAP = {
    # Seite 2 (page: 1) - Antragsteller
    "full_name":     {"page": 1, "x": 320, "y": 548, "size": 10},  # Familienname
    "vorname":       {"page": 1, "x": 320, "y": 604, "size": 10},  # Vorname (falls separiert)
    "dob":           {"page": 1, "x": 320, "y": 661, "size": 10},  # Geburtsdatum
    "geburtsort":    {"page": 1, "x": 545, "y": 661, "size": 10},  # Geburtsort
    "addr_street":   {"page": 1, "x": 320, "y": 757, "size": 10},  # Anschrift
    "marital":       {"page": 1, "x": 475, "y": 390, "size": 10},  # Familienstand (Checkbox-Bereich)
    "taxid_parent":  {"page": 1, "x": 520, "y": 320, "size": 10},  # Steuer-ID (falls separates Feld)
    "iban":          {"page": 1, "x": 475, "y": 125, "size": 10},  # IBAN
    "bic":           {"page": 1, "x": 475, "y": 90,  "size": 10},  # BIC
    
    # Seite 3 (page: 2) - Kind 1
    "kid_name_1":    {"page": 2, "x": 75,  "y": 715, "size": 10},  # Vorname Kind
    "kid_fname_1":   {"page": 2, "x": 480, "y": 715, "size": 10},  # Familienname Kind
    "kid_dob_1":     {"page": 2, "x": 220, "y": 715, "size": 10},  # Geburtsdatum Kind
    "kid_geschl_1":  {"page": 2, "x": 315, "y": 715, "size": 10},  # Geschlecht Kind
}

def _fmt_date(d: str) -> str:
    """Erwartet TT.MM.JJJJ; einfache Absicherung."""
    if not d:
        return ""
    d = str(d).replace("-", ".")
    return d

def _split_name(full_name: str) -> tuple:
    """Teilt 'Vorname Nachname' auf."""
    parts = full_name.strip().split()
    if len(parts) >= 2:
        vorname = parts[0]
        nachname = " ".join(parts[1:])
        return vorname, nachname
    return full_name, ""

def fill_kindergeld(template_path: str, out_path: str, data: Dict[str, Any]) -> None:
    """
    data = {"fields": {...}, "kids": [{...}, ...]}
    schreibt die ausgefüllte PDF an out_path.
    """
    # 1) Seitengrößen lesen
    tpl = PdfReader(template_path)
    page_sizes = []
    for p in tpl.pages:
        page_sizes.append((float(p.mediabox.width), float(p.mediabox.height)))

    # 2) Instruktionen zusammenstellen
    f = data.get("fields", {})
    kids = data.get("kids", []) or []
    instr: List[Dict[str, Any]] = []

    def put(key, text):
        m = KG1_MAP.get(key)
        if not m:
            return
        instr.append({
            "page": m["page"], 
            "x": m["x"], 
            "y": m["y"], 
            "text": str(text or ""), 
            "size": m.get("size", 10)
        })

    # Name aufteilen
    full_name = f.get("full_name", "")
    vorname, nachname = _split_name(full_name)
    
    put("full_name", nachname)  # Familienname
    put("vorname", vorname)     # Vorname
    put("dob", _fmt_date(f.get("dob")))
    put("addr_street", f.get("addr_street"))
    put("taxid_parent", f.get("taxid_parent"))
    put("iban", f.get("iban"))
    put("marital", f.get("marital"))

    # Kind 1
    if len(kids) >= 1:
        k = kids[0]
        kid_full_name = k.get("kid_name", "")
        kid_vorname, kid_nachname = _split_name(kid_full_name)
        
        put("kid_name_1", kid_vorname)
        put("kid_fname_1", kid_nachname)
        put("kid_dob_1", _fmt_date(k.get("kid_dob")))

    # 3) Overlay bauen & mergen
    overlay = _make_overlay(page_sizes, instr)
    pdf_bytes = _merge(template_path, overlay)

    # 4) Schreiben
    with open(out_path, "wb") as f_out:
        f_out.write(pdf_bytes)
