# app/pdf/filler.py
"""
KG1 PDF-Formular Filler - ULTIMATE LÖSUNG
Liest Koordinaten aus Formularfeldern und zeichnet Text DIREKT drauf
"""
from typing import Dict, Any
import fitz  # PyMuPDF

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
    ULTIMATE LÖSUNG: Liest Feld-Koordinaten und zeichnet Text direkt.
    """
    fields_data = data.get("fields", {})
    kids = data.get("kids", [])
    
    # Name aufteilen
    vorname, nachname = _split_name(fields_data.get("full_name", ""))
    taxid_parts = _split_taxid(fields_data.get("taxid_parent", ""))
    
    print(f"\n📝 ULTIMATE Methode: Lese Feld-Koordinaten und zeichne Text direkt...")
    
    # PDF öffnen
    doc = fitz.open(template_path)
    
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
        
        # Vorname
        seite1 + "Punkt-1[0].Pkt-1-Zeile-2[0].Vorname-Antragsteller[0]": vorname,
        
        # Geburtsdaten
        seite1 + "Punkt-1[0].Pkt-1-Zeile-3[0].Geburtsdatum-Antragsteller[0]": _fmt_date(fields_data.get("dob")),
        seite1 + "Punkt-1[0].Pkt-1-Zeile-3[0].Staatsangehörigkeit-Antragsteller[0]": fields_data.get("citizenship", "deutsch"),
        
        # Anschrift
        seite1 + "Punkt-1[0].Anschrift-Antragsteller[0]": f"{fields_data.get('addr_street', '')}, {fields_data.get('addr_plz', '')} {fields_data.get('addr_city', '')}".strip(", "),
        
        # IBAN
        seite1 + "Punkt-3[0].IBAN[0]": _fmt_iban(fields_data.get("iban", "")),
    }
    
    # Familienstand Checkboxen
    familienstand_fields = {
        "ledig": seite1 + "Punkt-1[0].Familienstand[0].#area[12].ledig[0]",
        "verheiratet": seite1 + "Punkt-1[0].Familienstand[0].#area[12].verheiratet[0]",
        "geschieden": seite1 + "Punkt-1[0].Familienstand[0].#area[12].geschieden[0]",
    }
    
    # Kinder
    if kids:
        for i, kid in enumerate(kids[:5], 1):
            zeile_prefix = seite2 + f"Punkt-5[0].Tabelle1-Kinder[0].Zeile{i}[0]."
            field_values.update({
                zeile_prefix + "Zelle1[0]": kid.get("kid_name", ""),
                zeile_prefix + "Zelle2[0]": _fmt_date(kid.get("kid_dob", "")),
            })
    
    # === SCHRITT 1: Koordinaten sammeln ===
    field_coords = {}
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        
        for widget in page.widgets():
            field_name = widget.field_name
            rect = widget.rect  # (x0, y0, x1, y1)
            
            # Speichere Koordinaten
            field_coords[field_name] = {
                "page": page_num,
                "rect": rect,
                "type": widget.field_type,
                "font_size": widget.text_fontsize if widget.text_fontsize else 10
            }
    
    print(f"   → {len(field_coords)} Feld-Koordinaten gelesen")
    
    # === SCHRITT 2: Text an Koordinaten zeichnen ===
    filled_count = 0
    
    for field_name, value in field_values.items():
        if field_name in field_coords and value:
            coords = field_coords[field_name]
            page = doc[coords["page"]]
            rect = coords["rect"]
            font_size = coords["font_size"]
            
            # KRITISCH: Text muss IN der Box sein, nicht darüber!
            # Y-Koordinate: rect.y0 ist UNTEN, rect.y1 ist OBEN
            # Wir wollen den Text an der BASELINE positionieren
            
            # Berechne die richtige Y-Position (leicht über dem Boden der Box)
            baseline_y = rect.y0 + (font_size * 0.75)  # Baseline = 75% der Schriftgröße über dem Boden
            text_x = rect.x0 + 2  # Kleiner Abstand vom linken Rand
            
            try:
                # insert_text für präzise Positionierung
                page.insert_text(
                    (text_x, baseline_y),
                    str(value),
                    fontsize=font_size,
                    fontname="helv",
                    color=(0, 0, 0)
                )
                filled_count += 1
                print(f"   ✓ {field_name[:50]} @ ({int(text_x)}, {int(baseline_y)})")
            except Exception as e:
                print(f"   ✗ {field_name}: {e}")
    
    # === SCHRITT 3: Familienstand Checkbox ===
    marital = fields_data.get("marital", "ledig").lower()
    if marital in familienstand_fields:
        checkbox_field = familienstand_fields[marital]
        if checkbox_field in field_coords:
            coords = field_coords[checkbox_field]
            page = doc[coords["page"]]
            rect = coords["rect"]
            
            # Zeichne X oder Häkchen in die Checkbox
            try:
                # Zentriert in der Box
                center_x = (rect.x0 + rect.x1) / 2
                center_y = (rect.y0 + rect.y1) / 2
                
                # Einfaches X zeichnen
                page.insert_text(
                    (center_x - 4, center_y + 4),
                    "X",
                    fontsize=12,
                    fontname="hebo",  # Helvetica Bold
                    color=(0, 0, 0)
                )
                print(f"   ✓ Checkbox: {marital}")
            except Exception as e:
                print(f"   ✗ Checkbox {marital}: {e}")
    
    # === SCHRITT 4: Formularfelder entfernen ===
    print(f"\n🗑️  Entferne Formularfelder (nur gezeichneter Text bleibt)...")
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        
        # Entferne alle Widget-Annotationen
        annot = page.first_annot
        while annot:
            next_annot = annot.next
            if annot.type[0] == 10:  # Widget
                page.delete_annot(annot)
            annot = next_annot
    
    # Speichern
    doc.save(out_path, garbage=4, deflate=True, clean=True)
    doc.close()
    
    print(f"\n✅ PDF erstellt: {out_path}")
    print(f"   • {filled_count} Felder ausgefüllt")
    print(f"   • Formularfelder entfernt")
    print(f"   • Nur statischer Text verbleibt")
    print(f"   • Name: {fields_data.get('full_name')}")
    print(f"   • Steuer-ID: {fields_data.get('taxid_parent')}")
    print(f"   • IBAN: {fields_data.get('iban')}")
    print(f"   • Familienstand: {fields_data.get('marital')}")
    if kids:
        print(f"   • Kinder: {len(kids)}")
    print(f"\n🎯 Text wurde DIREKT an Feld-Koordinaten gezeichnet!")

def make_grid(template_path: str) -> bytes:
    """Debug: Zeigt Feld-Koordinaten"""
    import io
    
    doc = fitz.open(template_path)
    
    # Neue Seite für Debug-Info
    page = doc.new_page(width=595, height=842)
    
    text = "Formularfeld-Koordinaten:\n\n"
    
    for page_num in range(min(3, len(doc)-1)):
        p = doc[page_num]
        text += f"\nSeite {page_num + 1}:\n"
        
        for widget in p.widgets():
            rect = widget.rect
            text += f"  {widget.field_name[:40]}\n"
            text += f"    ({int(rect.x0)}, {int(rect.y0)}) → ({int(rect.x1)}, {int(rect.y1)})\n"
    
    page.insert_text((50, 50), text, fontsize=8)
    
    buf = io.BytesIO(doc.tobytes())
    doc.close()
    
    return buf.getvalue()
