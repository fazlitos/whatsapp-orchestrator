# app/pdf/filler.py
# -*- coding: utf-8 -*-
"""
KG1 PDF-Filler über Widget-Rechtecke mit MuPDF (fitz).
- Schreibt mit insert_textbox direkt INS Rechteck (kein Baseline-Versatz)
- Optionaler Debug-Overlay zeichnet die Widget-Rechtecke + Namen
"""

from typing import Dict, Any, List
import io
import fitz  # PyMuPDF

# --- kleine Helfer ---------------------------------------------------------

def _safe(val: Any, default: str = "") -> str:
    return "" if val is None else str(val)

def _iban_grouped(iban: str) -> str:
    s = "".join(ch for ch in _safe(iban) if ch.isalnum())
    return " ".join(s[i:i+4] for i in range(0, len(s), 4))

# --- Debug-Overlay: zeigt dir alle Felder mit Kästen -----------------------

def make_debug_overlay(template_path: str, page_index: int = 1) -> bytes:
    """
    Rendert eine PDF-Seite mit gelben Rechtecken um alle Widgets und
    dem Feldnamen als Label. Hilft bei der visuellen Kontrolle.
    """
    doc = fitz.open(template_path)
    page = doc[page_index]
    # wir erzeugen eine Kopie, damit Original sauber bleibt
    mem = io.BytesIO()
    d2 = fitz.open()  # leeres PDF
    d2.insert_pdf(doc, from_page=page_index, to_page=page_index)
    p = d2[0]

    for w in p.widgets():
        rect = w.rect
        p.draw_rect(rect, color=(1, 1, 0), width=0.7)         # gelber Rahmen
        p.insert_text((rect.x0 + 2, rect.y0 - 2),              # Label über dem Feld
                      w.field_name[:80],
                      fontsize=7, color=(0.8, 0.2, 0.2))

    d2.save(mem)
    d2.close()
    doc.close()
    return mem.getvalue()

# --- Kern: Felder befüllen -------------------------------------------------

def fill_kindergeld(template_path: str, out_path: str, data: Dict[str, Any],
                    debug_overlay: bool = False) -> None:
    """
    Befüllt die wichtigsten Felder des KG1:
    - Familienname / Vorname / Geburtsdatum / Staatsangehörigkeit
    - Anschrift-Zeile
    - Familienstand (ledig / verheiratet / geschieden / verwitwet / getrennt)
    - IBAN
    Schreiben erfolgt mit insert_textbox in das Widget-Rechteck.
    """
    fields_in = data.get("fields", {}) or {}
    full_name = _safe(fields_in.get("full_name"))
    dob       = _safe(fields_in.get("dob"))
    street    = _safe(fields_in.get("addr_street"))
    plz       = _safe(fields_in.get("addr_plz"))
    city      = _safe(fields_in.get("addr_city"))
    taxid     = _safe(fields_in.get("taxid_parent"))
    iban      = _iban_grouped(_safe(fields_in.get("iban")))
    marital   = (_safe(fields_in.get("marital")).lower() or "")
    citizen   = _safe(fields_in.get("citizenship")) or "deutsch"

    # versuche Familienname/Vorname zu splitten (fallback: alles in Nachname)
    last_name, first_name = full_name, ""
    if " " in full_name:
        parts = full_name.split()
        last_name = parts[-1]
        first_name = " ".join(parts[:-1])

    doc = fitz.open(template_path)
    # Seite 2 (0-basiert index = 1)
    page = doc[1]

    # alle Widgets einsammeln (Name -> Widget)
    widgets = {w.field_name: w for w in page.widgets()}

    # Mapping: echte Feldnamen -> gewünschter Text
    # (Die Namen hast du aus /pdf/debug/fields bzw. deiner Liste)
    wanted: Dict[str, str] = {
        # Name(n)
        "topmostSubform[0].Seite1[0].Punkt-1[0].Pkt-1-Zeile-1[0].Name-Antragsteller[0]": last_name,
        "topmostSubform[0].Seite1[0].Punkt-1[0].Pkt-1-Zeile-1[0].Vorname-Antragsteller[0]": first_name,

        # Geburtsdatum
        "topmostSubform[0].Seite1[0].Punkt-1[0].Pkt-1-Zeile-2[0].Geburtsdatum[0]": dob,

        # Staatsangehörigkeit
        "topmostSubform[0].Seite1[0].Punkt-1[0].Pkt-1-Zeile-2[0].Staatsangehoerigkeit[0]": citizen,

        # Anschrift (die Form hat meist eine EIN-Zeilen-Adresse)
        "topmostSubform[0].Seite1[0].Punkt-1[0].Pkt-1-Zeile-5[0].Anschrift-Antragsteller[0]":
            f"{street}, {plz} {city}",

        # Steuer-ID: einige Formulare haben vier Blöcke – hier ein Beispiel:
        "topmostSubform[0].Seite1[0].#area[0].IdNr[0].IdNr-1[0]": taxid[0:3],
        "topmostSubform[0].Seite1[0].#area[0].IdNr[0].IdNr-2[0]": taxid[3:6],
        "topmostSubform[0].Seite1[0].#area[0].IdNr[0].IdNr-3[0]": taxid[6:9],
        "topmostSubform[0].Seite1[0].#area[0].IdNr[0].IdNr-4[0]": taxid[9:11],

        # IBAN
        "topmostSubform[0].Seite1[0].Punkt-3[0].IBAN[0]": iban,
    }

    # Familienstand -> Checkbox-Feldname (je nach PDF-Version anpassen)
    marital_map = {
        "ledig":      "topmostSubform[0].Seite1[0].Punkt-1[0].Familienstand-Gruppe[0].ledig[0]",
        "verheiratet":"topmostSubform[0].Seite1[0].Punkt-1[0].Familienstand-Gruppe[0].verheiratet[0]",
        "geschieden": "topmostSubform[0].Seite1[0].Punkt-1[0].Familienstand-Gruppe[0].geschieden[0]",
        "verwitwet":  "topmostSubform[0].Seite1[0].Punkt-1[0].Familienstand-Gruppe[0].verwitwet[0]",
        "getrennt":   "topmostSubform[0].Seite1[0].Punkt-1[0].Familienstand-Gruppe[0].getrennt[0]",
    }
    marital_field = marital_map.get(marital)

    # Schreiben: **insert_textbox INS Rechteck** (kein Baseline-Rechnen!)
    # kleine Innenränder, damit der Text nicht am Rand klebt
    def pad(rect: fitz.Rect, pad_left=1.5, pad_top=0.8, pad_right=1.5, pad_bottom=0.8) -> fitz.Rect:
        r = fitz.Rect(rect)
        r.x0 += pad_left
        r.y0 += pad_top
        r.x1 -= pad_right
        r.y1 -= pad_bottom
        return r

    for fname, text in wanted.items():
        w = widgets.get(fname)
        if not w or not text:
            continue
        rect = pad(w.rect)
        # in die Box schreiben; fontsize=9…10 passt (abhängig vom Formular)
        page.insert_textbox(rect, text, fontname="helv", fontsize=9.5,
                            color=(0, 0, 0), align=fitz.TEXT_ALIGN_LEFT)

    # Checkbox setzen (Haken „☑“ mittig zeichnen – robust gegenüber Appearance-Problemen)
    if marital_field and marital_field in widgets:
        r = widgets[marital_field].rect
        page.insert_text((r.x0 + r.width / 2 - 3, r.y0 + r.height - 2), "☑", fontname="helv",
                         fontsize=10, color=(0, 0, 0))

    # Optional: Overlay mit gelben Kästen & Labels auf Seite 2 einblenden
    if debug_overlay:
        for w in page.widgets():
            page.draw_rect(w.rect, color=(1, 1, 0), width=0.7)
            page.insert_text((w.rect.x0 + 2, w.rect.y0 - 2), w.field_name[:80],
                             fontsize=7, color=(0.8, 0.2, 0.2))

    # Formularfelder entfernen/flatten, damit Viewer nichts „verschiebt“
    page.clean_contents()

    # Speichern
    doc.save(out_path)
    doc.close()
