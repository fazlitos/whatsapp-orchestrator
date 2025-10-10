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
    
    # Felder befüllen
    try:
        if hasattr(writer, 'update_page_form_field_values'):
            # Neuere PyPDF2 API
            for page_num in range(len(writer.pages)):
                writer.update_page_form_field_values(
                    writer.pages[page_num],
                    field_values
                )
        else:
            # Ältere Methode - über Annotationen
            filled_count = 0
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
                                filled_count += 1
                        except Exception as e:
                            pass
            print(f"   → {filled_count} Felder erfolgreich gefüllt")
    except Exception as e:
        print(f"⚠️  Warnung: {e}")
    
    # WICHTIG: NeedAppearances Flag setzen (behebt Positionierungsprobleme)
    try:
        if '/AcroForm' in writer._root_object:
            writer._root_object['/AcroForm'].update({
                '/NeedAppearances': True
            })
    except Exception as e:
        print(f"⚠️  Konnte NeedAppearances nicht setzen: {e}")
    
    # Speichern
    with open(out_path, 'wb') as f:
        writer.write(f)
    
    print(f"✅ PDF erstellt: {out_path}")
    fields = data.get("fields", {})
    print(f"   Ausgefüllt:")
    print(f"   • Name: {fields.get('full_name')}")
    print(f"   • Geburtsdatum: {fields.get('dob')}")
    print(f"   • Adresse: {fields.get('addr_street')}, {fields.get('addr_plz')} {fields.get('addr_city')}")
    print(f"   • Steuer-ID: {fields.get('taxid_parent')}")
    print(f"   • IBAN: {fields.get('iban')}")
    print(f"   • Familienstand: {fields.get('marital')}")
    if data.get("kids"):
        print(f"   • Kinder: {len(data.get('kids', []))}")

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
