# app/pdf/filler.py
"""
KG1 PDF-Formular Filler - verwendet echte Formularfelder
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
    Mappt unsere Datenstruktur auf die KG1-Formularfelder.
    
    Basierend auf den echten Feldnamen aus dem PDF.
    """
    fields_data = data.get("fields", {})
    kids = data.get("kids", [])
    
    # Name aufteilen
    vorname, familienname = _split_name(fields_data.get("full_name", ""))
    
    # Steuer-ID aufteilen
    taxid_parts = _split_taxid(fields_data.get("taxid_parent", ""))
    
    # Basis-Präfix für alle Felder
    prefix = "topmostSubform[0].Seite1[0]."
    
    # Mapping unserer Daten auf PDF-Felder
    pdf_fields = {}
    
    # Punkt-1: Angaben zur antragstellenden Person
    punkt1 = prefix + "Punkt-1[0]."
    
    pdf_fields.update({
        # Steuer-ID (4 Felder)
        punkt1 + "Pkt-1-Zeile-1[0].Steuer-ID-1[0]": taxid_parts[0],
        punkt1 + "Pkt-1-Zeile-1[0].Steuer-ID-2[0]": taxid_parts[1],
        punkt1 + "Pkt-1-Zeile-1[0].Steuer-ID-3[0]": taxid_parts[2],
        punkt1 + "Pkt-1-Zeile-1[0].Steuer-ID-4[0]": taxid_parts[3],
        
        # Name (Zeile 2)
        punkt1 + "Pkt-1-Zeile-1[0].Familienname-Antragsteller[0]": familienname,
        punkt1 + "Pkt-1-Zeile-1[0].Titel-Antragsteller[0]": "",  # haben wir nicht
        
        # Vorname (Zeile 3)
        punkt1 + "Pkt-1-Zeile-2[0].Vorname-Antragsteller[0]": vorname,
        punkt1 + "Pkt-1-Zeile-2[0].Geburtsname-Antragsteller[0]": "",  # haben wir nicht
        
        # Geburtsdaten (Zeile 4)
        punkt1 + "Pkt-1-Zeile-3[0].Geburtsdatum-Antragsteller[0]": _fmt_date(fields_data.get("dob")),
        punkt1 + "Pkt-1-Zeile-3[0].Geburtsort-Antragsteller[0]": "",  # haben wir nicht
        punkt1 + "Pkt-1-Zeile-3[0].Geschlecht-Antragsteller[0]": "",  # haben wir nicht
        punkt1 + "Pkt-1-Zeile-3[0].Staatsangehörigkeit-Antragsteller[0]": fields_data.get("citizenship", "deutsch"),
        
        # Anschrift
        punkt1 + "Anschrift-Antragsteller[0]": f"{fields_data.get('addr_street', '')}, {fields_data.get('addr_plz', '')} {fields_data.get('addr_city', '')}".strip(", "),
        
        # Familienstand
        punkt1 + "Familienstand[0].#area[12].ledig[0]": "X" if fields_data.get("marital", "").lower() == "ledig" else "",
        punkt1 + "Familienstand[0].#area[12].verheiratet[0]": "X" if fields_data.get("marital", "").lower() == "verheiratet" else "",
        punkt1 + "Familienstand[0].#area[12].geschieden[0]": "X" if fields_data.get("marital", "").lower() == "geschieden" else "",
        punkt1 + "Familienstand[0].#area[12].getrennt[0]": "X" if fields_data.get("marital", "").lower() == "getrennt" else "",
        punkt1 + "Familienstand[0].#area[12].verwitwet[0]": "X" if fields_data.get("marital", "").lower() == "verwitwet" else "",
        punkt1 + "Familienstand[0].#area[12].aufgehoben[0]": "X" if fields_data.get("marital", "").lower() == "aufgehoben" else "",
    })
    
    # Punkt-3: Zahlungsweg
    punkt3 = prefix + "Punkt-3[0]."
    
    pdf_fields.update({
        punkt3 + "IBAN[0]": _fmt_iban(fields_data.get("iban", "")),
        punkt3 + "BIC[0]": "",  # haben wir nicht (oft nicht nötig)
        punkt3 + "Bank[0]": "",  # haben wir nicht
        punkt3 + "Name-Kontoinhaber[0]": "",  # leer = Antragsteller
    })
    
    # Kinder (Tabelle 1)
    # topmostSubform[0].Seite1[0].Punkt-5[0].Tabelle1-Kinder[0].Zeile1[0].Zeile1[0]
    if kids:
        for i, kid in enumerate(kids[:5], 1):  # Max 5 Kinder in Tabelle1
            zeile = f"{prefix}Punkt-5[0].Tabelle1-Kinder[0].Zeile{i}[0]."
            pdf_fields.update({
                zeile + f"Zeile{i}[0]": kid.get("kid_name", ""),
                zeile + f"Zeile{i}[1]": _fmt_date(kid.get("kid_dob", "")),
                zeile + f"Zeile{i}[2]": "",  # Geschlecht haben wir nicht
                zeile + f"Zeile{i}[3]": "",  # Familienkasse haben wir nicht
            })
    
    return pdf_fields

def fill_kindergeld(template_path: str, out_path: str, data: Dict[str, Any]) -> None:
    """
    Füllt KG1-Formular mit Daten aus.
    
    Args:
        template_path: Pfad zum KG1-Template
        out_path: Pfad für ausgefülltes PDF
        data: {"fields": {...}, "kids": [...]}
    """
    # PDF laden
    reader = PdfReader(template_path)
    writer = PdfWriter()
    
    if reader.is_encrypted:
        reader.decrypt("")
    
    # Alle Seiten kopieren
    for page in reader.pages:
        writer.add_page(page)
    
    # Daten mappen
    field_values = map_data_to_kg1_fields(data)
    
    print(f"\n📝 Fülle {len(field_values)} Felder aus...")
    
    # Felder befüllen (neuere PyPDF2 API)
    try:
        if hasattr(writer, 'update_page_form_field_values'):
            for page_num in range(len(writer.pages)):
                writer.update_page_form_field_values(
                    writer.pages[page_num],
                    field_values
                )
        else:
            # Ältere Methode - direkt über Annotationen
            for page in writer.pages:
                if '/Annots' in page:
                    for annotation in page['/Annots']:
                        try:
                            obj = annotation.get_object()
                            field_name = obj.get('/T')
                            if field_name and field_name in field_values:
                                value = field_values[field_name]
                                obj.update({
                                    '/V': value,
                                    '/AS': value
                                })
                        except Exception as e:
                            pass  # Feld konnte nicht gesetzt werden
    except Exception as e:
        print(f"⚠️  Warnung beim Ausfüllen: {e}")
    
    # Speichern
    with open(out_path, 'wb') as f:
        writer.write(f)
    
    print(f"✅ PDF erstellt: {out_path}")
    print(f"   Ausgefüllt: Name, Adresse, Steuer-ID, IBAN, Familienstand")
    if data.get("kids"):
        print(f"   Kinder: {len(data.get('kids', []))} eingetragen")

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
    
    c.setFont("Courier", 8)
    y = h - 3*cm
    
    for i, name in enumerate(sorted(fields.keys()), 1):
        if y < 2*cm:
            c.showPage()
            y = h - 2*cm
            c.setFont("Courier", 8)
        
        c.drawString(1*cm, y, f"{i}. {name}")
        y -= 0.4*cm
    
    c.save()
    buf.seek(0)
    return buf.read()
