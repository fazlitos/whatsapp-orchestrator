# app/pdf/filler.py
"""
KG1 PDF-Formular Filler - KORREKTE Feldnamen für echtes KG1-Formular
"""
from PyPDF2 import PdfReader, PdfWriter
from typing import Dict, Any
import io

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
    """Formatiert IBAN mit Leerzeichen"""
    iban = str(iban).replace(" ", "").upper()
    if len(iban) == 22 and iban.startswith("DE"):
        return " ".join([iban[i:i+4] for i in range(0, len(iban), 4)])
    return iban

def map_data_to_kg1_fields(data: Dict[str, Any]) -> Dict[str, str]:
    """
    Mappt unsere Datenstruktur auf die EXAKTEN KG1-Formularfelder.
    """
    fields_data = data.get("fields", {})
    kids = data.get("kids", [])
    
    # Name aufteilen
    vorname, nachname = _split_name(fields_data.get("full_name", ""))
    
    # Steuer-ID aufteilen
    taxid_parts = _split_taxid(fields_data.get("taxid_parent", ""))
    
    # Basis-Präfixe
    seite1 = "topmostSubform[0].Seite1[0]."
    seite2 = "topmostSubform[0].Page2[0]."
    
    # PDF-Felder mit EXAKTEN Namen aus dem echten Formular
    pdf_fields = {}
    
    # ========== SEITE 1: Antragsteller ==========
    
    # Steuer-ID (4 separate Felder)
    pdf_fields.update({
        seite1 + "Punkt-1[0].Steuer-ID[0].Steuer-ID-1[0]": taxid_parts[0],
        seite1 + "Punkt-1[0].Steuer-ID[0].Steuer-ID-2[0]": taxid_parts[1],
        seite1 + "Punkt-1[0].Steuer-ID[0].Steuer-ID-3[0]": taxid_parts[2],
        seite1 + "Punkt-1[0].Steuer-ID[0].Steuer-ID-4[0]": taxid_parts[3],
    })
    
    # Name (Zeile 1)
    pdf_fields.update({
        seite1 + "Punkt-1[0].Pkt-1-Zeile-1[0].Name-Antragsteller[0]": nachname,
        seite1 + "Punkt-1[0].Pkt-1-Zeile-1[0].Titel-Antragsteller[0]": "",
    })
    
    # Vorname (Zeile 2)
    pdf_fields.update({
        seite1 + "Punkt-1[0].Pkt-1-Zeile-2[0].Vorname-Antragsteller[0]": vorname,
        seite1 + "Punkt-1[0].Pkt-1-Zeile-2[0].Geburtsname-Antragsteller[0]": "",
    })
    
    # Geburtsdaten (Zeile 3)
    pdf_fields.update({
        seite1 + "Punkt-1[0].Pkt-1-Zeile-3[0].Geburtsdatum-Antragsteller[0]": _fmt_date(fields_data.get("dob")),
        seite1 + "Punkt-1[0].Pkt-1-Zeile-3[0].Geburtsort-Antragsteller[0]": "",
        seite1 + "Punkt-1[0].Pkt-1-Zeile-3[0].Geschlecht-Antragsteller[0]": "",
        seite1 + "Punkt-1[0].Pkt-1-Zeile-3[0].Staatsangehörigkeit-Antragsteller[0]": fields_data.get("citizenship", "deutsch"),
    })
    
    # Anschrift (EIN Feld für die komplette Adresse!)
    anschrift = f"{fields_data.get('addr_street', '')}, {fields_data.get('addr_plz', '')} {fields_data.get('addr_city', '')}"
    pdf_fields[seite1 + "Punkt-1[0].Anschrift-Antragsteller[0]"] = anschrift.strip(", ")
    
    # Familienstand (Checkboxen)
    marital = str(fields_data.get("marital", "ledig")).lower()
    pdf_fields.update({
        seite1 + "Punkt-1[0].Familienstand[0].#area[12].ledig[0]": "X" if marital == "ledig" else "",
        seite1 + "Punkt-1[0].Familienstand[0].#area[12].verheiratet[0]": "X" if marital == "verheiratet" else "",
        seite1 + "Punkt-1[0].Familienstand[0].#area[12].geschieden[0]": "X" if marital == "geschieden" else "",
        seite1 + "Punkt-1[0].Familienstand[0].#area[12].getrennt[0]": "X" if marital == "getrennt" else "",
        seite1 + "Punkt-1[0].Familienstand[0].#area[12].verwitwet[0]": "X" if marital == "verwitwet" else "",
        seite1 + "Punkt-1[0].Familienstand[0].#area[12].aufgehoben[0]": "X" if marital == "aufgehoben" else "",
        seite1 + "Punkt-1[0].Familienstand[0].#area[12].Partner[0]": "X" if marital == "partner" else "",
        seite1 + "Punkt-1[0].Familienstand[0].#area[12].seit[0]": "",  # Datum haben wir nicht
    })
    
    # ========== PUNKT 3: Zahlungsweg ==========
    pdf_fields.update({
        seite1 + "Punkt-3[0].IBAN[0]": _fmt_iban(fields_data.get("iban", "")),
        seite1 + "Punkt-3[0].BIC[0]": "",
        seite1 + "Punkt-3[0].Bank[0]": "",
        seite1 + "Punkt-3[0].Antragsteller[0]": "X",  # Checkbox: Kontoinhaber ist Antragsteller
        seite1 + "Punkt-3[0].andere-Person[0]": "",
        seite1 + "Punkt-3[0].Name-Kontoinhaber[0]": "",
    })
    
    # ========== SEITE 2: Kinder ==========
    # Tabelle1-Kinder: Zeile1-5, jeweils Zelle1-4
    # Zelle1 = Name, Zelle2 = Geburtsdatum, Zelle3 = Geschlecht, Zelle4 = Kindergeldnummer
    
    if kids:
        for i, kid in enumerate(kids[:5], 1):  # Max 5 Kinder
            zeile_prefix = seite2 + f"Punkt-5[0].Tabelle1-Kinder[0].Zeile{i}[0]."
            pdf_fields.update({
                zeile_prefix + "Zelle1[0]": kid.get("kid_name", ""),
                zeile_prefix + "Zelle2[0]": _fmt_date(kid.get("kid_dob", "")),
                zeile_prefix + "Zelle3[0]": "",  # Geschlecht haben wir nicht
                zeile_prefix + "Zelle4[0]": "",  # Kindergeldnummer haben wir nicht
            })
    
    return pdf_fields

def fill_kindergeld(template_path: str, out_path: str, data: Dict[str, Any]) -> None:
    """
    Füllt KG1-Formular mit Daten aus - HYBRID mit ReportLab Overlay.
    
    Args:
        template_path: Pfad zum KG1-Template
        out_path: Pfad für ausgefülltes PDF
        data: {"fields": {...}, "kids": [...]}
    """
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import black
    
    fields_data = data.get("fields", {})
    kids = data.get("kids", [])
    
    # Name aufteilen
    vorname, nachname = _split_name(fields_data.get("full_name", ""))
    taxid_parts = _split_taxid(fields_data.get("taxid_parent", ""))
    
    # PDF-Größe vom Template holen
    reader = PdfReader(template_path)
    if reader.is_encrypted:
        reader.decrypt("")
    
    page = reader.pages[1]  # Seite 2 im PDF (Index 1)
    page_width = float(page.mediabox.width)
    page_height = float(page.mediabox.height)
    
    print(f"\n📝 Erstelle Overlay für KG1...")
    print(f"   PDF-Größe: {page_width} x {page_height}")
    
    # Overlay erstellen (nur für Seite 2 = Index 1)
    overlay_buf = io.BytesIO()
    c = canvas.Canvas(overlay_buf, pagesize=(page_width, page_height))
    
    # Leere erste Seite (damit Index stimmt)
    c.showPage()
    c.setPageSize((page_width, page_height))
    
    # KOORDINATEN (gemessen vom echten PDF)
    # Y-Koordinaten von UNTEN nach OBEN
    
    c.setFillColor(black)
    c.setFont("Helvetica", 10)
    
    # Seite 2: Steuer-ID Kästen (oben)
    c.drawString(120, 770, taxid_parts[0])   # Erste 2 Ziffern
    c.drawString(185, 770, taxid_parts[1])   # Nächste 3
    c.drawString(260, 770, taxid_parts[2])   # Nächste 3
    c.drawString(335, 770, taxid_parts[3])   # Letzte 3
    
    # Name
    c.drawString(105, 745, nachname)
    
    # Vorname
    c.drawString(105, 720, vorname)
    
    # Geburtsdatum
    c.drawString(105, 695, _fmt_date(fields_data.get("dob")))
    
    # Staatsangehörigkeit
    c.drawString(485, 695, fields_data.get("citizenship", "deutsch"))
    
    # Anschrift
    anschrift = f"{fields_data.get('addr_street', '')}, {fields_data.get('addr_plz', '')} {fields_data.get('addr_city', '')}"
    c.drawString(105, 665, anschrift.strip(", "))
    
    # Familienstand - X bei richtigem Feld
    marital = str(fields_data.get("marital", "ledig")).lower()
    c.setFont("Helvetica-Bold", 14)
    marital_positions = {
        "ledig": (78, 607),
        "verheiratet": (330, 629),
        "geschieden": (330, 607),
        "getrennt": (465, 607),
        "verwitwet": (330, 585),
    }
    if marital in marital_positions:
        x, y = marital_positions[marital]
        c.drawString(x, y, "☑")  # Checkbox Symbol
        print(f"   → Familienstand '{marital}' bei ({x}, {y})")
    c.setFont("Helvetica", 10)
    
    # IBAN (Punkt 3 - ganz unten)
    iban_formatted = _fmt_iban(fields_data.get("iban", ""))
    c.setFont("Helvetica", 9)
    c.drawString(90, 232, iban_formatted)  # IBAN Position
    print(f"   → IBAN: {iban_formatted}")
    c.setFont("Helvetica", 10)
    
    # Kontoinhaber = Antragsteller Checkbox
    c.setFont("Helvetica-Bold", 14)
    c.drawString(78, 250, "☑")
    
    c.save()
    overlay_buf.seek(0)
    
    # Zweites Overlay für Seite 3 (Kinder)
    overlay_buf2 = io.BytesIO()
    c2 = canvas.Canvas(overlay_buf2, pagesize=(page_width, page_height))
    
    # Zwei leere Seiten (damit wir bei Index 2 = Seite 3 sind)
    c2.showPage()
    c2.showPage()
    c2.setPageSize((page_width, page_height))
    c2.setFont("Helvetica", 9)
    
    # Kinder in Tabelle auf Seite 3
    if kids:
        kid_y_positions = [655, 630, 605, 580, 555]
        for i, kid in enumerate(kids[:5]):
            if i < len(kid_y_positions):
                y = kid_y_positions[i]
                c2.drawString(90, y, kid.get("kid_name", ""))
                c2.drawString(350, y, _fmt_date(kid.get("kid_dob", "")))
                print(f"   → Kind {i+1}: {kid.get('kid_name')}")
    
    c2.save()
    overlay_buf2.seek(0)
    
    # Overlays mit Template mergen
    overlay_reader = PdfReader(overlay_buf)
    overlay_reader2 = PdfReader(overlay_buf2)
    template_reader = PdfReader(template_path)
    
    writer = PdfWriter()
    
    for i, template_page in enumerate(template_reader.pages):
        # Overlay 1 für Seite 2 (Index 1)
        if i < len(overlay_reader.pages) and i == 1:
            template_page.merge_page(overlay_reader.pages[i])
        # Overlay 2 für Seite 3 (Index 2)
        if i < len(overlay_reader2.pages) and i == 2 and kids:
            template_page.merge_page(overlay_reader2.pages[i])
        writer.add_page(template_page)
    
    # Speichern
    with open(out_path, 'wb') as f:
        writer.write(f)
    
    print(f"✅ PDF erstellt: {out_path}")
    print(f"   • Name: {fields_data.get('full_name')}")
    print(f"   • Steuer-ID: {fields_data.get('taxid_parent')}")
    print(f"   • Adresse: {anschrift}")
    print(f"   • IBAN: {fields_data.get('iban')}")
    print(f"   • Familienstand: {fields_data.get('marital')}")
    if kids:
        print(f"   • Kinder: {len(kids)}")

def make_grid(template_path: str) -> bytes:
    """
    Debug-Funktion: Listet alle Formularfelder auf.
    """
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    
    reader = PdfReader(template_path)
    
    if reader.is_encrypted:
        reader.decrypt("")
    
    fields = {}
    
    if hasattr(reader, 'get_fields'):
        form_fields = reader.get_fields()
        if form_fields:
            fields = form_fields
    
    # Liste als PDF erstellen
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    
    c.setFont("Helvetica-Bold", 14)
    c.drawString(2*cm, h - 2*cm, f"KG1 Formularfelder ({len(fields)} gefunden)")
    
    c.setFont("Courier", 7)
    y = h - 3*cm
    
    for i, name in enumerate(sorted(fields.keys()), 1):
        if y < 2*cm:
            c.showPage()
            y = h - 2*cm
            c.setFont("Courier", 7)
        
        c.drawString(0.5*cm, y, f"{i}. {name}")
        y -= 0.35*cm
    
    c.save()
    buf.seek(0)
    return buf.read()
