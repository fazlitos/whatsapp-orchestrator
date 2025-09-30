# app/pdf/filler.py
import os, uuid
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

ART_DIR = os.environ.get("ART_DIR", "/tmp/artifacts")

def _line(txt, textobj):
    # Hilfsfunktion für automatische Zeilenumbrüche
    width = 90
    for i in range(0, len(txt), width):
        textobj.textLine(txt[i:i+width])

def create_kindergeld_pdf(fields: dict, kids: list):
    os.makedirs(ART_DIR, exist_ok=True)
    fid = f"kindergeld_{uuid.uuid4().hex}.pdf"
    path = os.path.join(ART_DIR, fid)

    c = canvas.Canvas(path, pagesize=A4)
    text = c.beginText(40, 800)
    text.setLeading(16)
    text.setFont("Helvetica-Bold", 14)
    text.textLine("Kindergeld-Antrag – Zusammenfassung")
    text.setFont("Helvetica", 11)
    text.textLine(f"Erstellt am: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    text.textLine("")

    # Antragsteller
    text.setFont("Helvetica-Bold", 12); text.textLine("Antragsteller")
    text.setFont("Helvetica", 11)
    for k, label in [
        ("full_name","Voller Name"),
        ("dob","Geburtsdatum"),
        ("addr_street","Straße & Hausnr."),
        ("addr_plz","PLZ"),
        ("addr_city","Ort"),
        ("taxid_parent","Steuer-ID"),
        ("iban","IBAN"),
        ("marital","Familienstand"),
        ("citizenship","Staatsangehörigkeit"),
        ("employment","Beschäftigungsstatus"),
        ("start_month","Beginn (Monat)")
    ]:
        _line(f"{label}: {fields.get(k,'')}", text)
    text.textLine("")

    # Kinder
    text.setFont("Helvetica-Bold", 12); text.textLine("Kinder")
    text.setFont("Helvetica", 11)
    for i, k in enumerate(kids, start=1):
        _line(f"#{i} Name: {k.get('kid_name','')}", text)
        _line(f"   Geburtsdatum: {k.get('kid_dob','')}", text)
        _line(f"   Steuer-ID: {k.get('kid_taxid','')}", text)
        _line(f"   Verwandtschaft: {k.get('kid_relation','')}", text)
        _line(f"   Haushalt: {k.get('kid_cohab','')}", text)
        _line(f"   Status: {k.get('kid_status','')}", text)
        _line(f"   EU-Leistung: {k.get('kid_eu_benefit','')}", text)
        text.textLine("")

    c.drawText(text)
    c.showPage()
    c.save()
    return fid, path
