# app/pdf/filler.py
import io
import os
from typing import List, Dict, Any
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from PyPDF2 import PdfReader, PdfWriter

DEBUG_MODE = os.getenv("PDF_DEBUG", "").lower() == "true"

# ========== KORRIGIERTE KOORDINATEN FÜR KG1 ==========
# Basierend auf Standard-KG1 Formular (A4, 595x842 Punkte)
# Y-Koordinaten gemessen von UNTEN nach OBEN

KG1_MAP = {
    # Seite 2: Hauptformular (page=1, da 0-basiert)
    # Block 1: Angaben zur antragstellenden Person
    
    # Steuer-ID (aufgeteilt in 4 Felder mit je 2-3 Ziffern)
    "taxid_1": {"page": 1, "x": 100, "y": 770, "size": 10},   # 2 Ziffern
    "taxid_2": {"page": 1, "x": 155, "y": 770, "size": 10},   # 3 Ziffern  
    "taxid_3": {"page": 1, "x": 230, "y": 770, "size": 10},   # 3 Ziffern
    "taxid_4": {"page": 1, "x": 305, "y": 770, "size": 10},   # 3 Ziffern
    
    # Name
    "nachname": {"page": 1, "x": 100, "y": 745, "size": 10},
    "titel": {"page": 1, "x": 480, "y": 745, "size": 10},
    
    # Vorname
    "vorname": {"page": 1, "x": 100, "y": 720, "size": 10},
    "geburtsname": {"page": 1, "x": 350, "y": 720, "size": 9},
    
    # Geburtsdaten
    "dob": {"page": 1, "x": 100, "y": 695, "size": 10},
    "geburtsort": {"page": 1, "x": 220, "y": 695, "size": 10},
    "geschlecht": {"page": 1, "x": 400, "y": 695, "size": 10},
    "staatsangehoerigkeit": {"page": 1, "x": 480, "y": 695, "size": 9},
    
    # Anschrift (eine Zeile)
    "anschrift": {"page": 1, "x": 100, "y": 665, "size": 9},
    
    # Block: Familienstand (Y ca. 635-610)
    "cb_ledig": {"page": 1, "x": 85, "y": 630, "size": 12},
    "marital_seit": {"page": 1, "x": 200, "y": 630, "size": 9},
    
    "cb_verheiratet": {"page": 1, "x": 280, "y": 630, "size": 12},
    "cb_lebenspartner": {"page": 1, "x": 430, "y": 630, "size": 12},
    
    "cb_geschieden": {"page": 1, "x": 280, "y": 615, "size": 12},
    "cb_aufgehoben": {"page": 1, "x": 430, "y": 615, "size": 12},
    
    "cb_verwitwet": {"page": 1, "x": 280, "y": 600, "size": 12},
    "cb_getrennt": {"page": 1, "x": 430, "y": 600, "size": 12},
    
    # Block 2: Ehepartner (Y ca. 570-520)
    "partner_taxid_1": {"page": 1, "x": 100, "y": 555, "size": 10},
    "partner_taxid_2": {"page": 1, "x": 155, "y": 555, "size": 10},
    "partner_taxid_3": {"page": 1, "x": 230, "y": 555, "size": 10},
    "partner_taxid_4": {"page": 1, "x": 305, "y": 555, "size": 10},
    
    "partner_nachname": {"page": 1, "x": 100, "y": 530, "size": 10},
    "partner_vorname": {"page": 1, "x": 280, "y": 530, "size": 10},
    "partner_titel": {"page": 1, "x": 480, "y": 530, "size": 10},
    
    # Block 3: Zahlungsweg (Y ca. 480-440)
    "iban": {"page": 1, "x": 100, "y": 465, "size": 9},
    "bic": {"page": 1, "x": 100, "y": 445, "size": 9},
    "bank": {"page": 1, "x": 270, "y": 445, "size": 9},
    
    # Kontoinhaberkennzeichen
    "cb_kontoinhaber_antragsteller": {"page": 1, "x": 85, "y": 425, "size": 12},
    "cb_kontoinhaber_andere": {"page": 1, "x": 85, "y": 410, "size": 12},
    "kontoinhaber_name": {"page": 1, "x": 280, "y": 410, "size": 9},
}

# ========== HELPER FUNKTIONEN ==========

def _split_name(full_name: str) -> tuple:
    """Teilt 'Vorname Nachname' auf."""
    parts = str(full_name).strip().split(maxsplit=1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return full_name, ""

def _split_taxid(taxid: str) -> tuple:
    """Teilt Steuer-ID: 12 345 678 901"""
    taxid = str(taxid).replace(" ", "").replace("-", "")
    if len(taxid) != 11:
        return "", "", "", ""
    return taxid[0:2], taxid[2:5], taxid[5:8], taxid[8:11]

def _fmt_date(d: str) -> str:
    """Formatiert Datum zu TT.MM.JJJJ"""
    if not d:
        return ""
    return str(d).replace("-", ".")

def _fmt_iban(iban: str) -> str:
    """Formatiert IBAN mit Leerzeichen: DE12 3456 7890 1234 5678 90"""
    iban = str(iban).replace(" ", "").upper()
    if len(iban) == 22 and iban.startswith("DE"):
        return " ".join([iban[i:i+4] for i in range(0, len(iban), 4)])
    return iban

def _get_marital_checkbox(marital: str) -> str:
    """Gibt Checkbox-Key für Familienstand zurück"""
    mapping = {
        "ledig": "cb_ledig",
        "verheiratet": "cb_verheiratet",
        "geschieden": "cb_geschieden",
        "verwitwet": "cb_verwitwet",
        "lebenspartnerschaft": "cb_lebenspartner",
        "getrennt": "cb_getrennt",
    }
    return mapping.get(str(marital).lower(), "cb_ledig")

# ========== OVERLAY FUNKTIONEN ==========

def _make_overlay(page_sizes: List[tuple], instructions: List[Dict[str, Any]], debug: bool = False) -> io.BytesIO:
    """Baut Mehrseiten-Overlay."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=page_sizes[0] if page_sizes else A4)
    
    by_page: Dict[int, List[Dict[str, Any]]] = {}
    for ins in instructions:
        by_page.setdefault(ins["page"], []).append(ins)

    for pno, (w, h) in enumerate(page_sizes):
        c.setPageSize((w, h))
        
        for ins in by_page.get(pno, []):
            x = float(ins["x"])
            y = float(ins["y"])
            text = str(ins.get("text", ""))
            size = int(ins.get("size", 10))
            
            if debug:
                # Debug: Zeige Labels + Koordinaten
                c.setFillColorRGB(1, 0, 0)
                c.setFont("Helvetica-Bold", 7)
                label = ins.get("label", "?")
                c.drawString(x, y + 12, f"{label}")
                c.drawString(x, y + 4, f"({int(x)},{int(y)})")
                
                # Markierung
                c.setStrokeColorRGB(0, 0, 1)
                c.setLineWidth(1)
                c.circle(x, y, 3, fill=0)
                
                # Text in Blau
                c.setFillColorRGB(0, 0, 1)
                c.setFont("Helvetica", size)
                c.drawString(x, y, text)
            else:
                # Normal: Nur schwarzer Text
                c.setFillColorRGB(0, 0, 0)
                c.setFont("Helvetica", size)
                c.drawString(x, y, text)
        
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

# ========== GRID FÜR KOORDINATENMESSUNG ==========

def make_grid(template_path: str) -> bytes:
    """Erzeugt Grid-PDF mit 20px Raster."""
    tpl = PdfReader(template_path)
    page_sizes = [(float(p.mediabox.width), float(p.mediabox.height)) for p in tpl.pages]

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=page_sizes[0] if page_sizes else A4)
    
    for pno, (w, h) in enumerate(page_sizes):
        c.setPageSize((w, h))
        step = 50  # Raster 50px für bessere Lesbarkeit
        
        # Graues Raster
        c.setStrokeColorRGB(0.85, 0.85, 0.85)
        c.setFont("Helvetica", 7)
        
        # Vertikale Linien
        for x in range(0, int(w), step):
            c.line(x, 0, x, h)
            if x % 100 == 0:
                c.setStrokeColorRGB(0.6, 0.6, 0.6)
                c.line(x, 0, x, h)
                c.setStrokeColorRGB(0.85, 0.85, 0.85)
            c.drawString(x + 2, h - 12, str(x))
        
        # Horizontale Linien
        for y in range(0, int(h), step):
            c.line(0, y, w, y)
            if y % 100 == 0:
                c.setStrokeColorRGB(0.6, 0.6, 0.6)
                c.line(0, y, w, y)
                c.setStrokeColorRGB(0.85, 0.85, 0.85)
            c.drawString(5, y + 2, str(y))
        
        # Info
        c.setFont("Helvetica-Bold", 12)
        c.setFillColorRGB(1, 0, 0)
        c.drawString(20, h - 30, f"Seite {pno+1}/{len(page_sizes)} | Koordinaten-Grid")
        c.drawString(20, h - 50, f"A4: {int(w)}x{int(h)}pt | 0,0 = UNTEN LINKS")
        
        c.showPage()
    
    c.save()
    buf.seek(0)
    return _merge(template_path, buf)

# ========== HAUPTFUNKTION ==========

def fill_kindergeld(template_path: str, out_path: str, data: Dict[str, Any]) -> None:
    """
    Füllt KG1-Formular mit Daten.
    
    Args:
        template_path: Pfad zum Template
        out_path: Ausgabepfad
        data: {"fields": {...}, "kids": [...]}
    """
    # Seitengrößen lesen
    tpl = PdfReader(template_path)
    page_sizes = [(float(p.mediabox.width), float(p.mediabox.height)) for p in tpl.pages]
    
    f = data.get("fields", {})
    instr: List[Dict[str, Any]] = []
    
    def put(key: str, text: str, label: str = None):
        """Fügt Text an Koordinate hinzu."""
        m = KG1_MAP.get(key)
        if not m:
            print(f"⚠️  Feld '{key}' nicht in KG1_MAP")
            return
        
        instr.append({
            "page": m["page"],
            "x": m["x"],
            "y": m["y"],
            "text": str(text or ""),
            "size": m.get("size", 10),
            "label": label or key
        })
    
    # Name aufteilen
    vorname, nachname = _split_name(f.get("full_name", ""))
    put("vorname", vorname, "Vorname")
    put("nachname", nachname, "Nachname")
    
    # Geburtsdatum
    put("dob", _fmt_date(f.get("dob")), "Geburtsdatum")
    
    # Staatsangehörigkeit
    put("staatsangehoerigkeit", f.get("citizenship", "deutsch"), "Staatsangehörigkeit")
    
    # Anschrift (kombiniert)
    anschrift = f"{f.get('addr_street', '')}, {f.get('addr_plz', '')} {f.get('addr_city', '')}"
    put("anschrift", anschrift.strip(", "), "Anschrift")
    
    # Steuer-ID aufteilen
    t1, t2, t3, t4 = _split_taxid(f.get("taxid_parent", ""))
    put("taxid_1", t1, "TaxID-1")
    put("taxid_2", t2, "TaxID-2")
    put("taxid_3", t3, "TaxID-3")
    put("taxid_4", t4, "TaxID-4")
    
    # Familienstand (Checkbox)
    marital = str(f.get("marital", "ledig")).lower()
    cb_key = _get_marital_checkbox(marital)
    put(cb_key, "X", f"Checkbox-{marital}")
    
    # IBAN
    put("iban", _fmt_iban(f.get("iban", "")), "IBAN")
    
    # Kontoinhaber-Checkbox (immer Antragsteller)
    put("cb_kontoinhaber_antragsteller", "X", "Kontoinhaber")
    
    # Overlay bauen
    debug = DEBUG_MODE or os.getenv("PDF_DEBUG_ONCE", "").lower() == "true"
    overlay = _make_overlay(page_sizes, instr, debug=debug)
    pdf_bytes = _merge(template_path, overlay)
    
    # Speichern
    with open(out_path, "wb") as f_out:
        f_out.write(pdf_bytes)
    
    if debug:
        print(f"🔍 DEBUG-PDF: {out_path}")
        print(f"   → Labels zeigen Feldnamen + Koordinaten")
        print(f"   → Blaue Punkte = Position")
        print(f"   → Blauer Text = Ausgefüllte Werte")
    else:
        print(f"✅ PDF erstellt: {out_path}")
