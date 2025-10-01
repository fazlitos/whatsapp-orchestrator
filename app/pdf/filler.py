# app/pdf/filler.py
import io
from typing import List, Dict, Any
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter  # nur Fallback, wir lesen echte Größe aus dem Template
from PyPDF2 import PdfReader, PdfWriter

# ---------- kleine Zeichen-Primitive ----------
def _make_overlay(page_sizes: List[tuple], instructions: List[Dict[str, Any]]) -> io.BytesIO:
    """
    Baut ein Mehrseiten-Overlay (eine PDF) mit allen Texten.
    page_sizes: [(w,h), ...] aus dem Template
    instructions: [{page:int, x:float, y:float, text:str, size:int}, ...]
    """
    buf = io.BytesIO()
    # Dummy-Startgröße; wechseln wir pro Seite auf echte Größe
    c = canvas.Canvas(buf, pagesize=page_sizes[0] if page_sizes else letter)
    # pro Seite zeichnen
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
        # vertikal (x)
        step = 20
        c.setFont("Helvetica", 6)
        for x in range(0, int(w), step):
            c.setStrokeColorRGB(0.85, 0.85, 0.85)
            c.line(x, 0, x, h)
            c.drawString(x + 1, h - 10, str(x))
        # horizontal (y)
        for y in range(0, int(h), step):
            c.line(0, y, w, y)
            c.drawString(2, y + 2, str(y))
        c.setFont("Helvetica", 10)
        c.setStrokeColorRGB(1, 0, 0)
        c.drawString(20, h - 20, f"Seite {pno+1} – Koordinatennetz (0,0 unten links, Einheiten: pt)")
        c.showPage()
    c.save()
    buf.seek(0)
    # überlagern
    return _merge(template_path, buf)

# ---------- Mapping & Fülllogik Kindergeld ----------
# HINWEIS: Koordinaten sind Platzhalter (A4 ~ 595 x 842 pt).
# Nutze /pdf/debug/kg1, um exakte Positionen zu finden und passe die Werte unten an.
KG1_MAP = {
    # page, x, y, fontsize
    "full_name":     {"page": 0, "x": 90,  "y": 770, "size": 11},
    "dob":           {"page": 0, "x": 420, "y": 770, "size": 11},
    "addr_street":   {"page": 0, "x": 90,  "y": 746, "size": 11},
    "addr_plz":      {"page": 0, "x": 420, "y": 746, "size": 11},
    "addr_city":     {"page": 0, "x": 470, "y": 746, "size": 11},
    "taxid_parent":  {"page": 0, "x": 90,  "y": 722, "size": 11},
    "iban":          {"page": 0, "x": 90,  "y": 698, "size": 11},
    "marital":       {"page": 0, "x": 420, "y": 722, "size": 11},
    "citizenship":   {"page": 0, "x": 420, "y": 698, "size": 11},
    "employment":    {"page": 0, "x": 90,  "y": 674, "size": 11},
    "start_month":   {"page": 0, "x": 420, "y": 674, "size": 11},

    # erstes Kind (nur als Beispiel – echte Positionen via Grid kalibrieren)
    "kid_name_1":    {"page": 0, "x": 90,  "y": 630, "size": 11},
    "kid_dob_1":     {"page": 0, "x": 420, "y": 630, "size": 11},
    "kid_taxid_1":   {"page": 0, "x": 90,  "y": 606, "size": 11},
    "kid_relation_1":{"page": 0, "x": 420, "y": 606, "size": 11},
}

def _fmt_date(d: str) -> str:
    # erwartet TT.MM.JJJJ; einfache Absicherung
    if not d:
        return ""
    d = str(d).replace("-", ".")
    return d

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
        instr.append({"page": m["page"], "x": m["x"], "y": m["y"], "text": str(text or ""), "size": m.get("size", 10)})

    put("full_name", f.get("full_name"))
    put("dob", _fmt_date(f.get("dob")))
    put("addr_street", f.get("addr_street"))
    put("addr_plz", f.get("addr_plz"))
    put("addr_city", f.get("addr_city"))
    put("taxid_parent", f.get("taxid_parent"))
    put("iban", f.get("iban"))
    put("marital", f.get("marital"))
    put("citizenship", f.get("citizenship"))
    put("employment", f.get("employment"))
    put("start_month", f.get("start_month"))

    if len(kids) >= 1:
        k = kids[0]
        put("kid_name_1", k.get("kid_name"))
        put("kid_dob_1", _fmt_date(k.get("kid_dob")))
        put("kid_taxid_1", k.get("kid_taxid"))
        put("kid_relation_1", k.get("kid_relation"))

    # 3) Overlay bauen & mergen
    overlay = _make_overlay(page_sizes, instr)
    pdf_bytes = _merge(template_path, overlay)

    # 4) schreiben
    with open(out_path, "wb") as f_out:
        f_out.write(pdf_bytes)
