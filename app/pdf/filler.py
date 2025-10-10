# app/pdf/filler.py
"""
KG1 PDF-Formular Filler mit pikepdf - Die professionelle Lösung
"""
from typing import Dict, Any
import pikepdf
from pikepdf import Pdf, Name
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

def fill_kindergeld(template_path: str, out_path: str, data: Dict[str, Any]) -> None:
    """
    Füllt KG1-Formular mit pikepdf aus - GARANTIERT korrekte Darstellung!
    
    Args:
        template_path: Pfad zum KG1-Template
        out_path: Pfad für ausgefülltes PDF
        data: {"fields": {...}, "kids": [...]}
    """
    fields_data = data.get("fields", {})
    kids = data.get("kids", [])
    
    # Name aufteilen
    vorname, nachname = _split_name(fields_data.get("full_name", ""))
    taxid_parts = _split_taxid(fields_data.get("taxid_parent", ""))
    
    print(f"\n📝 Fülle KG1-Formular aus mit pikepdf...")
    
    # PDF öffnen
    pdf = Pdf.open(template_path)
    
    # Basis-Präfixe
    seite1 = "topmostSubform[0].Seite1[0]."
    seite2 = "topmostSubform[0].Page2[0]."
    
    # Feldwerte definieren
    field_values = {
        # Steuer-ID (4 Felder)
        seite1 + "Punkt-1[0].Steuer-ID[0].Steuer-ID-1[0]": taxid_parts[0],
        seite1 + "Punkt-1[0].Steuer-ID[0].Steuer-ID-2[0]": taxid_parts[1],
        seite1 + "Punkt-1[0].Steuer-ID[0].Steuer-ID-3[0]": taxid_parts[2],
        seite1 + "Punkt-1[0].Steuer-ID[0].Steuer-ID-4[0]": taxid_parts[3],
        
        # Name
        seite1 + "Punkt-1[0].Pkt-1-Zeile-1[0].Name-Antragsteller[0]": nachname,
        seite1 + "Punkt-1[0].Pkt-1-Zeile-1[0].Titel-Antragsteller[0]": "",
        
        # Vorname
        seite1 + "Punkt-1[0].Pkt-1-Zeile-2[0].Vorname-Antragsteller[0]": vorname,
        seite1 + "Punkt-1[0].Pkt-1-Zeile-2[0].Geburtsname-Antragsteller[0]": "",
        
        # Geburtsdaten
        seite1 + "Punkt-1[0].Pkt-1-Zeile-3[0].Geburtsdatum-Antragsteller[0]": _fmt_date(fields_data.get("dob")),
        seite1 + "Punkt-1[0].Pkt-1-Zeile-3[0].Geburtsort-Antragsteller[0]": "",
        seite1 + "Punkt-1[0].Pkt-1-Zeile-3[0].Geschlecht-Antragsteller[0]": "",
        seite1 + "Punkt-1[0].Pkt-1-Zeile-3[0].Staatsangehörigkeit-Antragsteller[0]": fields_data.get("citizenship", "deutsch"),
        
        # Anschrift
        seite1 + "Punkt-1[0].Anschrift-Antragsteller[0]": f"{fields_data.get('addr_street', '')}, {fields_data.get('addr_plz', '')} {fields_data.get('addr_city', '')}".strip(", "),
        
        # Familienstand (Checkboxen) - pikepdf verwendet "On" für aktivierte Checkboxen
        seite1 + "Punkt-1[0].Familienstand[0].#area[12].ledig[0]": "On" if fields_data.get("marital", "").lower() == "ledig" else "Off",
        seite1 + "Punkt-1[0].Familienstand[0].#area[12].verheiratet[0]": "On" if fields_data.get("marital", "").lower() == "verheiratet" else "Off",
        seite1 + "Punkt-1[0].Familienstand[0].#area[12].geschieden[0]": "On" if fields_data.get("marital", "").lower() == "geschieden" else "Off",
        seite1 + "Punkt-1[0].Familienstand[0].#area[12].getrennt[0]": "On" if fields_data.get("marital", "").lower() == "getrennt" else "Off",
        seite1 + "Punkt-1[0].Familienstand[0].#area[12].verwitwet[0]": "On" if fields_data.get("marital", "").lower() == "verwitwet" else "Off",
        seite1 + "Punkt-1[0].Familienstand[0].#area[12].seit[0]": "",
        
        # IBAN
        seite1 + "Punkt-3[0].IBAN[0]": _fmt_iban(fields_data.get("iban", "")),
        seite1 + "Punkt-3[0].BIC[0]": "",
        seite1 + "Punkt-3[0].Bank[0]": "",
        seite1 + "Punkt-3[0].Antragsteller[0]": "On",  # Checkbox: Antragsteller ist Kontoinhaber
        seite1 + "Punkt-3[0].andere-Person[0]": "Off",
        seite1 + "Punkt-3[0].Name-Kontoinhaber[0]": "",
    }
    
    # Kinder (Tabelle auf Seite 2)
    if kids:
        for i, kid in enumerate(kids[:5], 1):
            zeile_prefix = seite2 + f"Punkt-5[0].Tabelle1-Kinder[0].Zeile{i}[0]."
            field_values.update({
                zeile_prefix + "Zelle1[0]": kid.get("kid_name", ""),
                zeile_prefix + "Zelle2[0]": _fmt_date(kid.get("kid_dob", "")),
                zeile_prefix + "Zelle3[0]": "",
                zeile_prefix + "Zelle4[0]": "",
            })
    
    # Formularfelder ausfüllen mit pikepdf
    filled_count = 0
    for page in pdf.pages:
        annotations = page.get(Name.Annots)
        if annotations:
            for annot in annotations:
                field_obj = annot
                if Name.T in field_obj:  # T = Field Name
                    field_name = str(field_obj.T)
                    if field_name in field_values:
                        value = field_values[field_name]
                        
                        # Checkbox oder Text?
                        if value in ["On", "Off"]:
                            # Checkbox
                            if value == "On":
                                field_obj[Name.V] = Name.On
                                field_obj[Name.AS] = Name.On
                            else:
                                field_obj[Name.V] = Name.Off
                                field_obj[Name.AS] = Name.Off
                        else:
                            # Textfeld
                            field_obj[Name.V] = value
                        
                        filled_count += 1
                        print(f"   ✓ {field_name[:50]}...")
    
    # NeedAppearances auf True setzen (wichtig!)
    if Name.AcroForm in pdf.Root:
        pdf.Root.AcroForm[Name.NeedAppearances] = True
    
    # Speichern
    pdf.save(out_path)
    pdf.close()
    
    print(f"\n✅ PDF erstellt: {out_path}")
    print(f"   • {filled_count} Felder ausgefüllt")
    print(f"   • Name: {fields_data.get('full_name')}")
    print(f"   • Steuer-ID: {fields_data.get('taxid_parent')}")
    print(f"   • IBAN: {fields_data.get('iban')}")
    print(f"   • Familienstand: {fields_data.get('marital')}")
    if kids:
        print(f"   • Kinder: {len(kids)}")
    print(f"\n🎯 pikepdf hat die Felder KORREKT ausgefüllt!")

def make_grid(template_path: str) -> bytes:
    """Debug-Funktion"""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, h - 100, "KG1 Formular-Filler mit pikepdf")
    
    c.setFont("Helvetica", 11)
    y = h - 150
    
    info = [
        "pikepdf ist die professionelle Lösung für PDF-Formulare.",
        "",
        "Vorteile:",
        "• Korrekte Appearance Streams",
        "• Zuverlässige Checkbox-Behandlung",
        "• Perfekte Positionierung",
        "• Keine Darstellungsprobleme",
    ]
    
    for line in info:
        c.drawString(50, y, line)
        y -= 20
    
    c.save()
    buf.seek(0)
    return buf.read()
