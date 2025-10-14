# app/pdf/filler.py
"""
Kindergeld PDF Generator - Exakte Nachbildung des Original-Formulars
Mit Ehepartner-Sektion
"""
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.colors import black, HexColor
from typing import Dict, Any

# Farben wie im Original
FORM_GRAY = HexColor('#F0F0F0')
LINE_COLOR = HexColor('#333333')
HEADER_BG = HexColor('#E8E8E8')

def draw_box(c, x, y, width, height, label="", value="", font_size=8):
    """Zeichnet eine Box mit Label und Wert"""
    # Box-Rahmen
    c.setStrokeColor(LINE_COLOR)
    c.setLineWidth(0.5)
    c.rect(x, y, width, height)
    
    # Label (klein, grau) - BLEIBT OBEN
    if label:
        c.setFont("Helvetica", 7)
        c.setFillColorRGB(0.4, 0.4, 0.4)
        c.drawString(x + 2, y + height - 8, label)
    
    # Wert (eingetragener Text) - optimale Position
    if value:
        c.setFont("Helvetica", font_size)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(x + 2, y + height/2 - 9, str(value))  # perfekte Position

def draw_checkbox(c, x, y, size, checked=False, label=""):
    """Zeichnet eine Checkbox"""
    # Box
    c.setStrokeColor(LINE_COLOR)
    c.setLineWidth(0.5)
    c.rect(x, y, size, size)
    
    # Häkchen wenn checked
    if checked:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x + 2, y + 2, "✓")
    
    # Label rechts neben Box
    if label:
        c.setFont("Helvetica", 9)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(x + size + 5, y + 2, label)

def draw_section_header(c, x, y, width, number, title):
    """Zeichnet einen Sektion-Header"""
    # Hintergrund
    c.setFillColor(HEADER_BG)
    c.rect(x, y, width, 15, fill=1, stroke=0)
    
    # Nummer in Box
    c.setStrokeColor(LINE_COLOR)
    c.setLineWidth(0.5)
    c.rect(x + 5, y + 2, 12, 11)
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x + 9, y + 4, str(number))
    
    # Titel
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x + 25, y + 4, title)

def create_kindergeld_pdf(out_path: str, data: Dict[str, Any]) -> None:
    """
    Erstellt ein Kindergeld-PDF das wie das Original aussieht
    """
    fields = data.get("fields", {})
    kids = data.get("kids", [])
    
    c = canvas.Canvas(out_path, pagesize=A4)
    width, height = A4
    
    # === SEITE 1 ===
    
    # Logo-Bereich (oben rechts)
    c.setFont("Helvetica", 8)
    c.drawRightString(width - 40, height - 30, "Familienkasse")
    
    # Haupttitel
    c.setFont("Helvetica-Bold", 18)
    c.drawString(40, height - 60, "Antrag auf Kindergeld")
    
    c.setFont("Helvetica", 8)
    c.drawString(40, height - 75, "Beachten Sie bitte die anhängenden Hinweise und das Merkblatt Kindergeld.")
    
    # Kindergeld-Nummer (12 Felder)
    y_pos = height - 95
    c.setFont("Helvetica", 8)
    c.drawString(40, y_pos, "Kindergeld-Nr.:")
    
    # 12 kleine Boxen für KG-Nummer
    kg_nr = data.get("kg_parts", [])
    for i in range(12):
        x_box = 130 + (i * 18)
        val = kg_nr[i] if i < len(kg_nr) else ""
        draw_box(c, x_box, y_pos - 10, 15, 15, value=val)
    
    # Anzahl Anlagen
    c.drawString(width - 150, y_pos, "Anzahl der beigefügten")
    c.drawString(width - 150, y_pos - 10, '"Anlage Kind":')
    draw_box(c, width - 60, y_pos - 10, 20, 15, value=str(len(kids)))
    
    # === SEKTION 1: ANGABEN ZUR ANTRAGSTELLENDEN PERSON ===
    y_pos = height - 140
    draw_section_header(c, 40, y_pos, width - 80, 1, "Angaben zur antragstellenden Person")
    
    y_pos -= 25
    
    # Name aufteilen
    full_name = fields.get("full_name", "")
    name_parts = full_name.split(maxsplit=1)
    vorname = name_parts[0] if name_parts else ""
    nachname = name_parts[1] if len(name_parts) > 1 else ""
    
    # ZEILE 1: Familienname + Titel + Steuer-ID
    draw_box(c, 40, y_pos, 250, 20, "Familienname", nachname)
    draw_box(c, 295, y_pos, 80, 20, "Titel", "")
    draw_box(c, 380, y_pos, 175, 20, "Steuerliche Identifikationsnummer (zwingend ausfüllen)", 
             fields.get("taxid_parent", ""))
    
    y_pos -= 25
    
    # ZEILE 2: Vorname + Geburtsname
    draw_box(c, 40, y_pos, 250, 20, "Vorname", vorname)
    draw_box(c, 295, y_pos, 260, 20, "ggf. Geburtsname und Familienname aus früherer Ehe", "")
    
    y_pos -= 25
    
    # ZEILE 3: Geburtsdatum + Geschlecht + Geburtsort + Staatsangehörigkeit
    draw_box(c, 40, y_pos, 100, 20, "Geburtsdatum", fields.get("dob", ""))
    draw_box(c, 145, y_pos, 60, 20, "Geschlecht", "")
    draw_box(c, 210, y_pos, 160, 20, "Geburtsort", "")
    draw_box(c, 375, y_pos, 180, 20, "Staatsangehörigkeit", fields.get("citizenship", ""))
    
    y_pos -= 25
    
    # ZEILE 4: Anschrift (große Box)
    y_pos -= 24  # Box perfekt positioniert
    addr = f"{fields.get('addr_street', '')}, {fields.get('addr_plz', '')} {fields.get('addr_city', '')}"
    
    # Anschrift-Box manuell zeichnen
    c.setStrokeColor(LINE_COLOR)
    c.setLineWidth(0.5)
    c.rect(40, y_pos, 515, 45)  # Höhe 45
    
    # Label oben
    c.setFont("Helvetica", 7)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.drawString(42, y_pos + 32, "Anschrift (Straße/Platz, Hausnummer, Postleitzahl, Wohnort, Staat)")
    
    # Text mittig
    c.setFont("Helvetica", 8)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(42, y_pos + 18, addr)
    
    y_pos -= 55
    
    # Familienstand
    c.setFont("Helvetica", 9)
    c.drawString(40, y_pos, "Familienstand:")
    
    marital = fields.get('marital', '').lower()
    
    # Checkboxen horizontal
    cb_y = y_pos - 5
    draw_checkbox(c, 120, cb_y, 10, marital == 'ledig', "ledig")
    draw_checkbox(c, 180, cb_y, 10, marital == 'verheiratet', "verheiratet")
    draw_checkbox(c, 280, cb_y, 10, marital == 'verwitwet', "verwitwet")
    
    cb_y -= 12
    draw_checkbox(c, 180, cb_y, 10, marital == 'geschieden', "geschieden")
    draw_checkbox(c, 280, cb_y, 10, marital in ['getrennt', 'dauernd getrennt lebend'], "dauernd getrennt lebend")
    
    y_pos -= 50
    
    # === SEKTION 2: EHEPARTNER ===
    draw_section_header(c, 40, y_pos, width - 80, 2, 
                       "Angaben zum/zur Ehepartner(in) bzw. eingetragenen Lebenspartner(in)")
    
    y_pos -= 25
    
    # Ehepartner Name
    partner_name = fields.get("partner_name", "")
    if partner_name:
        # Name aufteilen
        partner_parts = partner_name.split(maxsplit=1)
        partner_vorname = partner_parts[0] if partner_parts else ""
        partner_nachname = partner_parts[1] if len(partner_parts) > 1 else ""
        
        # Familienname
        draw_box(c, 40, y_pos, 180, 20, "Familienname", partner_nachname)
        
        # Vorname
        draw_box(c, 225, y_pos, 180, 20, "Vorname", partner_vorname)
        
        # Titel
        draw_box(c, 410, y_pos, 145, 20, "Titel", "")
        
        y_pos -= 25
        
        # Geburtsdatum
        draw_box(c, 40, y_pos, 100, 20, "Geburtsdatum", fields.get("partner_dob", ""))
        
        # Staatsangehörigkeit
        draw_box(c, 145, y_pos, 160, 20, "Staatsangehörigkeit", fields.get("partner_citizenship", ""))
        
        # Geburtsname
        draw_box(c, 310, y_pos, 245, 20, "ggf. Geburtsname und Familienname aus früherer Ehe", "")
        
        y_pos -= 25
        
        # Anschrift (wenn abweichend)
        partner_addr = fields.get("partner_address", "")
        if partner_addr:
            draw_box(c, 40, y_pos, 515, 20, 
                    "Anschrift, wenn abweichend von antragstellender Person", 
                    partner_addr)
            y_pos -= 25
    else:
        # Keine Ehepartner-Daten
        c.setFont("Helvetica", 8)
        c.setFillColorRGB(0.5, 0.5, 0.5)
        c.drawString(45, y_pos, "(Keine Angaben zum Ehepartner)")
        y_pos -= 15
    
    y_pos -= 20
    
    # === SEKTION 3: ZAHLUNGSWEG ===
    draw_section_header(c, 40, y_pos, width - 80, 3, "Angaben zum Zahlungsweg")
    
    y_pos -= 25
    
    # IBAN
    iban = fields.get('iban', '')
    # IBAN formatieren
    if iban and len(iban) >= 4:
        iban_formatted = ' '.join([iban[i:i+4] for i in range(0, len(iban), 4)])
    else:
        iban_formatted = iban
    
    draw_box(c, 40, y_pos, 280, 20, "IBAN", iban_formatted)
    
    # BIC
    draw_box(c, 325, y_pos, 230, 20, "BIC", "")
    
    y_pos -= 25
    
    # Bank
    draw_box(c, 40, y_pos, 280, 20, "Bank, Finanzinstitut", "")
    
    # Kontoinhaber
    draw_box(c, 325, y_pos, 230, 20, "Kontoinhaber(in) ist", full_name)
    
    y_pos -= 30
    
    # Kontoinhaber-Checkboxen
    draw_checkbox(c, 40, y_pos, 10, True, "antragstellende Person wie unter 1")
    draw_checkbox(c, 40, y_pos - 15, 10, False, "nicht antragstellende Person, sondern")
    
    y_pos -= 50
    
    # Neue Seite wenn zu wenig Platz (unter 100 Punkte = ~3.5cm)
    if y_pos < 100:
        c.showPage()
        y_pos = height - 60
    
    # === SEKTION 4: BESCHEID-EMPFÄNGER (vereinfacht) ===
    draw_section_header(c, 40, y_pos, width - 80, 4, 
                       "Der Bescheid soll nicht mir, sondern folgender Person zugesandt werden")
    
    y_pos -= 30
    c.setFont("Helvetica", 8)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.drawString(45, y_pos, "(Optional)")
    
    # === SEITE 2: KINDER & UNTERSCHRIFTEN ===
    c.showPage()
    y_pos = height - 60
    
    # === SEKTION 5: ANGABEN ZU KINDERN (für die bereits KG bezogen wird) ===
    draw_section_header(c, 40, y_pos, width - 80, 5, "Angaben zu Kindern")
    
    y_pos -= 20
    c.setFont("Helvetica", 8)
    c.drawString(40, y_pos, "Für jedes Kind, für das Kindergeld beantragt wird, ist eine gesonderte \"Anlage Kind\" ausgefüllt einzureichen.")
    
    y_pos -= 15
    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y_pos, "Für folgende Kinder beziehe ich bereits Kindergeld:")
    
    y_pos -= 10
    c.setFont("Helvetica", 7)
    c.drawString(40, y_pos, "(auch in Fällen der abweichenden Kontoverbindung, Abzweigung und Erstattung):")
    
    y_pos -= 25
    
    # Tabelle für bereits Kindergeld-Kinder (5 Zeilen)
    table_headers = [
        ("Vorname des Kindes,\nggf. abweichender Familienname", 40, 160),
        ("Geburtsdatum", 200, 70),
        ("Geschlecht", 275, 55),
        ("Bei welcher Familienkasse\n(Kindergeldnummer, Personalnummer)?", 335, 220)
    ]
    
    # Header zeichnen
    c.setFont("Helvetica", 7)
    c.setStrokeColor(LINE_COLOR)
    c.setLineWidth(0.5)
    c.rect(40, y_pos, 515, 15)
    
    for header, x, w in table_headers:
        c.drawString(x + 2, y_pos + 8, header.replace('\n', ' '))
    
    y_pos -= 15
    
    # 5 Zeilen für Kinder-Einträge
    for i in range(5):
        c.rect(40, y_pos, 160, 15)
        c.rect(200, y_pos, 70, 15)
        c.rect(275, y_pos, 55, 15)
        c.rect(335, y_pos, 220, 15)
        y_pos -= 15
    
    y_pos -= 15
    
    # === SEKTION 6: ZÄHLKINDER ===
    draw_section_header(c, 40, y_pos, width - 80, 6, "Folgende Zählkinder sollen berücksichtigt werden:")
    
    y_pos -= 25
    
    # Tabelle für Zählkinder (5 Zeilen)
    table_headers2 = [
        ("Vorname des Kindes,\nggf. abweichender Familienname", 40, 160),
        ("Geburtsdatum", 200, 70),
        ("Geschlecht", 275, 55),
        ("Wer bezieht das Kindergeld\n(Name, Vorname)?", 335, 105),
        ("Bei welcher Familienkasse\n(Kindergeldnummer, Personalnummer)?", 445, 110)
    ]
    
    # Header zeichnen
    c.setFont("Helvetica", 7)
    c.rect(40, y_pos, 515, 15)
    
    for header, x, w in table_headers2:
        c.drawString(x + 2, y_pos + 8, header.replace('\n', ' '))
    
    y_pos -= 15
    
    # 5 Zeilen für Zählkinder
    for i in range(5):
        c.rect(40, y_pos, 160, 15)
        c.rect(200, y_pos, 70, 15)
        c.rect(275, y_pos, 55, 15)
        c.rect(335, y_pos, 105, 15)
        c.rect(445, y_pos, 110, 15)
        y_pos -= 15
    
    y_pos -= 20
    
    # === RECHTLICHE TEXTE ===
    c.setFont("Helvetica", 7)
    c.setFillColorRGB(0, 0, 0)
    
    text_lines = [
        "Ich versichere, dass alle Angaben (auch in den Anlagen) vollständig sind und der Wahrheit entsprechen. Mir ist bekannt, dass ich alle",
        "Änderungen, die für den Anspruch auf Kindergeld von Bedeutung sind, unverzüglich der Familienkasse mitzuteilen habe. Den Inhalt",
        "des Merkblattes Kindergeld (zu finden unter www.bzst.de oder www.familienkasse.de) habe ich zur Kenntnis genommen."
    ]
    
    for line in text_lines:
        c.drawString(40, y_pos, line)
        y_pos -= 10
    
    y_pos -= 10
    
    c.setFont("Helvetica-Bold", 8)
    c.drawString(40, y_pos, "Hinweis zum Datenschutz:")
    y_pos -= 10
    
    c.setFont("Helvetica", 7)
    datenschutz_lines = [
        "Ihre Daten werden gemäß der §§ 31, 62 bis 78 Einkommensteuergesetz und der Regelungen der Abgabenordnung bzw. aufgrund des",
        "Bundeskindergeldgesetzes und des Sozialgesetzbuches verarbeitet. Zweck der Verarbeitung der Daten ist die Prüfung Ihres Anspruchs auf",
        "Kindergeld. Nähere Informationen über die Verarbeitung Ihrer Daten durch die Familienkasse und zu Ihren Rechten nach Artikel 13 bis 22 der",
        "Datenschutz-Grundverordnung erhalten Sie im Internet auf der Seite Ihrer Familienkasse (zu finden unter",
        "www.arbeitsagentur.de/datenschutz-familienkasse), auf der auch die Kontaktdaten der/des Datenschutzbeauftragten bereitgestellt sind.",
        "Kindergeldakten werden in der Regel nach dem Ende der Kindergeldzahlung noch für 6 Jahre aufbewahrt."
    ]
    
    for line in datenschutz_lines:
        c.drawString(40, y_pos, line)
        y_pos -= 9
    
    y_pos -= 20
    
    # === UNTERSCHRIFTEN-BEREICH ===
    # Datum + Unterschrift Antragsteller
    c.setStrokeColor(LINE_COLOR)
    c.setLineWidth(0.5)
    c.rect(40, y_pos, 80, 20)
    
    c.setFont("Helvetica", 7)
    c.drawString(42, y_pos + 24, "Datum")
    
    c.drawString(280, y_pos + 10, "Unterschrift der antragstellenden Person bzw. der gesetzlichen Vertretung")
    c.line(280, y_pos + 5, 555, y_pos + 5)
    
    y_pos -= 35
    
    c.setFont("Helvetica", 8)
    c.drawString(40, y_pos, "Ich bin damit einverstanden, dass das Kindergeld zugunsten der antragstellenden Person festgesetzt bzw. bewilligt wird.")
    
    y_pos -= 25
    
    # Datum + Unterschrift Partner
    c.rect(40, y_pos, 80, 20)
    
    c.setFont("Helvetica", 7)
    c.drawString(42, y_pos + 24, "Datum")
    
    c.drawString(280, y_pos + 10, "Unterschrift der unter Punkt 2 genannten Person bzw. deren gesetzliche Vertretung")
    c.line(280, y_pos + 5, 555, y_pos + 5)
    
    # Footer
    c.setFont("Helvetica", 7)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.drawString(40, 30, "Erstellt mit Kindergeld-Bot • Blatt 2 von 4")
    c.drawRightString(width - 40, 30, "KGFAMKA-001-DE-FL")
    
    # Speichern
    c.save()


def fill_kindergeld(template_path: str, out_path: str, data: Dict[str, Any]) -> None:
    """Wrapper für Kompatibilität"""
    create_kindergeld_pdf(out_path, data)


def make_grid(template_path: str) -> bytes:
    """Grid für Debug"""
    import io
    from reportlab.lib.pagesizes import A4
    
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setFont("Helvetica", 12)
    c.drawString(100, 400, "Kindergeld PDF Generator")
    c.drawString(100, 380, "Kein Template nötig - PDF wird generiert")
    c.save()
    
    buffer.seek(0)
    return buffer.read()


if __name__ == "__main__":
    # Test
    test_data = {
        "fields": {
            "full_name": "Max Mustermann",
            "dob": "01.01.1990",
            "addr_street": "Teststraße 1",
            "addr_plz": "10115",
            "addr_city": "Berlin",
            "taxid_parent": "12345678901",
            "iban": "DE89370400440532013000",
            "marital": "verheiratet",
            "citizenship": "deutsch",
            "employment": "angestellt",
            "start_month": "01.2024",
            "partner_name": "Anna Mustermann",
            "partner_dob": "15.05.1992",
            "partner_citizenship": "deutsch"
        },
        "kids": [
            {
                "kid_name": "Mia Mustermann",
                "kid_dob": "15.06.2020",
                "kid_taxid": "98765432109",
                "kid_relation": "leiblich",
                "kid_cohab": True,
                "kid_status": "unter_6"
            }
        ],
        "kg_parts": list("123456789012")
    }
    
    create_kindergeld_pdf("/tmp/kindergeld_generated.pdf", test_data)
    print("✅ PDF erstellt: /tmp/kindergeld_generated.pdf")
