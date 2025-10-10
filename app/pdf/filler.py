# app/pdf/filler.py
# -*- coding: utf-8 -*-
"""
KG1 PDF-Filler über Widget-Rechtecke mit MuPDF (fitz).
- Schreibt mit insert_textbox direkt INS Rechteck (kein Baseline-Versatz).
- Optionaler Debug-Overlay zeichnet die Widget-Rechtecke + Namen.
"""

from typing import Dict, Any
import io
import fitz  # PyMuPDF


def _safe(val: Any, default: str = "") -> str:
    return "" if val is None else str(val)


def _iban_grouped(iban: str) -> str:
    s = "".join(ch for ch in _safe(iban) if ch.isalnum())
    return " ".join(s[i:i + 4] for i in range(0, len(s), 4))


def make_debug_overlay(template_path: str, page_index: int = 1) -> bytes:
    """
    Rendert eine einzelne Seite mit gelben Rechtecken um alle Widgets und
    dem Feldnamen als Label. Hilft bei der visuellen Kontrolle.
    """
    doc = fitz.open(template_path)
    mem = io.BytesIO()

    d2 = fitz.open()
    d2.insert_pdf(doc, from_page=page_index, to_page=page_index)
    p = d2[0]

    for w in p.widgets():
        rect = w.rect
        p.draw_rect(rect, color=(1, 1, 0), width=0.7)
        p.insert_text((rect.x0 + 2, rect.y0 - 2), w.field_name[:80],
                      fontsize=7, color=(0.8, 0.2, 0.2))

    d2.save(mem)
    d2.close()
    doc.close()
    return mem.getvalue()


def fill_kindergeld(template_path: str, out_path: str, data: Dict[str, Any],
                    debug_overlay: bool = False) -> None:
    """
    Befüllt die wichtigsten Felder des KG1:
    - Familienname / Vorname / Geburtsdatum / Staatsangehörigkeit
    - Anschrift-Zeile
    - Familienstand (Checkbox)
    - IBAN
    Schreiben erfolgt mit insert_textbox in das Widget-Rechteck.
    """
    fields_in = data.get("fields", {}) or {}
    full_name = _safe(fields_in.get("full_name"))
    dob = _safe(fields_in.get("dob"))
    street = _safe(fields_in.get("addr_street"))
    plz = _safe(fields_in.get("addr_plz"))
    city = _safe(fields_in.get("addr_city"))
    taxid = _safe(fields_in.get("taxid_parent"))
    iban = _iban_grouped(_safe(fields_in.get("iban")))
    marital = (_safe(fields_in.get("marital")).lower() or "")
    citizen = _safe(fields_in.get("citizenship")) or "deutsch"

    last_name, first_name = full_name, ""
    if " " in full_name:
        parts = full_name.split()
        last_name = parts[-1]
        first_name = " ".join(parts[:-1])

    doc = fitz.open(template_path)
    page = doc[1]  # Seite 2 (0-basiert)

    widgets = {w.field_name: w for w in page.widgets()}

    wanted: Dict[str, str] = {
        # Achtung: Feldnamen ggf. mit /pdf/debug/fields prüfen und anpassen
        "topmostSubform[0].Seite1[0].Punkt-1[0].Pkt-1-Zeile-1[0].Name-Antragsteller[0]": last_name,
        "topmostSubform[0].Seite1[0].Punkt-1[0].Pkt-1-Zeile-1[0].Vorname-Antragsteller[0]": first_name,
        "topmostSubform[0].Seite1[0].Punkt-1[0].Pkt-1-Zeile-2[0].Geburtsdatum[0]": dob,
        "topmostSubform[0].Seite1[0].Punkt-1[0].Pkt-1-Zeile-2[0].Staatsangehoerigkeit[0]": citizen,
        "topmostSubform[0].Seite1[0].Punkt-1[0].Pkt-1-Zeile-5[0].Anschrift-Antragsteller[0]":
            f"{street}, {plz} {city}",
        "topmostSubform[0].Seite1[0].#area[0].IdNr[0].IdNr-1[0]": taxid[0:3],
        "topmostSubform[0].Seite1[0].#area[0].IdNr[0].IdNr-2[0]": taxid[3:6],
        "topmostSubform[0].Seite1[0].#area[0].IdNr[0].IdNr-3[0]": taxid[6:9],
        "topmostSubform[0].Seite1[0].#area[0].IdNr[0].IdNr-4[0]": taxid[9:11],
        "topmostSubform[0].Seite1[0].Punkt-3[0].IBAN[0]": iban,
    }

    marital_map = {
        "ledig":       "topmostSubform[0].Seite1[0].Punkt-1[0].Familienstand-Gruppe[0].ledig[0]",
        "verheiratet": "topmostSubform[0].Seite1[0].Punkt-1[0].Familienstand-Gruppe[0].verheiratet[0]",
        "geschieden":  "topmostSubform[0].Seite1[0].Punkt-1[0].Familienstand-Gruppe[0].geschieden[0]",
        "verwitwet":   "topmostSubform[0].Seite1[0].Punkt-1[0].Familienstand-Gruppe[0].verwitwet[0]",
        "getrennt":    "topmostSubform[0].Seite1[0].Punkt-1[0].Familienstand-Gruppe[0].getrennt[0]",
    }
    marital_field = marital_map.get(marital)

    def pad(rect: fitz.Rect, l=1.5, t=0.8, r=1.5, b=0.8) -> fitz.Rect:
        rr = fitz.Rect(rect)
        rr.x0 += l; rr.y0 += t; rr.x1 -= r; rr.y1 -= b
        return rr

    # Text INS Rechteck (kein Baseline-Versatz)
    for fname, text in wanted.items():
        w = widgets.get(fname)
        if not w or not text:
            continue
        rect = pad(w.rect)
        page.insert_textbox(rect, text, fontname="helv", fontsize=9.5,
                            color=(0, 0, 0), align=fitz.TEXT_ALIGN_LEFT)

    # Checkbox robust „ankreuzen“ (☑ mittig zeichnen)
    if marital_field and marital_field in widgets:
        r = widgets[marital_field].rect
        page.insert_text((r.x0 + r.width / 2 - 3, r.y0 + r.height - 2), "☑",
                         fontname="helv", fontsize=10, color=(0, 0, 0))

    if debug_overlay:
        for w in page.widgets():
            page.draw_rect(w.rect, color=(1, 1, 0), width=0.7)
            page.insert_text((w.rect.x0 + 2, w.rect.y0 - 2), w.field_name[:80],
                             fontsize=7, color=(0.8, 0.2, 0.2))

    # Inhalte säubern (flatten-ähnlich, verhindert spätere Verschiebungen)
    page.clean_contents()

    doc.save(out_path)
    doc.close()
