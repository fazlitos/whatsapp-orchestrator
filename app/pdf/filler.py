# app/pdf/filler.py
# ---------------------------------------------------------------------
# KG1-Füller (robust): Liest Widget-Rechtecke mit PyMuPDF (fitz),
# schreibt Text direkt in die Rechtecke (insert_textbox) und entfernt
# danach die Widgets -> statischer Text an exakt der Feldposition.
# ---------------------------------------------------------------------

from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple
import io
import re
import fitz  # PyMuPDF

BANNER = "📄 KG1 filler: PyMuPDF overlay mode (widgets->static text)"

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())

def _compose_address(fields: Dict[str, str]) -> str:
    street = fields.get("addr_street", "")
    plz = fields.get("addr_plz", "")
    city = fields.get("addr_city", "")
    parts = [p for p in [street, f"{plz} {city}".strip()] if p]
    return ", ".join(parts)

def _iban_compact(s: str) -> str:
    return re.sub(r"\s+", "", s or "")

def _text(v: Any) -> str:
    return "" if v is None else str(v)

def _collect_widgets(doc: fitz.Document) -> List[Tuple[int, fitz.Widget]]:
    """Alle Widgets (Formularfelder) sammeln, inkl. Page-Index."""
    out: List[Tuple[int, fitz.Widget]] = []
    for i in range(len(doc)):
        page = doc[i]
        for w in page.widgets() or []:
            out.append((i, w))
    return out

def _find_widget(widgets: List[Tuple[int, fitz.Widget]], needle: str) -> Optional[Tuple[int, fitz.Widget]]:
    """Widget per Teilstring des Feldnamens finden (case-insensitive)."""
    n = _norm(needle)
    best: Optional[Tuple[int, fitz.Widget]] = None
    for pidx, w in widgets:
        name = w.field_name or ""
        if n in _norm(name):
            best = (pidx, w)
            break
    return best

def _draw_text_in_widget_rect(
    page: fitz.Page,
    rect: fitz.Rect,
    text: str,
    fontsize: float = 10.0,
    pad: float = 1.5,
    bold: bool = False,
):
    """
    Text „sauber“ in die Rechteckbox schreiben.
    insert_textbox berücksichtigt Baseline/Umbruch selbst.
    """
    if not text:
        return
    r = fitz.Rect(rect)
    # leicht innen zeichnen
    r.x0 += pad
    r.x1 -= pad
    r.y0 += pad
    r.y1 -= pad
    fontname = "helv" if not bold else "helvB"
    page.insert_textbox(r, text, fontsize=fontsize, fontname=fontname, align=0)

def _draw_checkbox_mark(page: fitz.Page, rect: fitz.Rect, mark: str = "X", fontsize: float = 11.0):
    """
    Ein X/✓ mittig in die Checkbox-Box setzen (falls die Checkbox-Widgets
    selbst keine Appearance-Streams haben).
    """
    cx = (rect.x0 + rect.x1) / 2.0
    cy = (rect.y0 + rect.y1) / 2.0
    # Position leicht nach links/unten justieren
    page.insert_text((cx - fontsize * 0.35, cy + fontsize * 0.35), mark, fontsize=fontsize, fontname="helvB")

def _remove_all_widgets(doc: fitz.Document):
    """Alle Widgets aus dem Dokument entfernen (wir haben ja statischen Text gezeichnet)."""
    for i in range(len(doc)):
        page = doc[i]
        for w in list(page.widgets() or []):
            w.remove_from_page()

def _fill_page1(
    doc: fitz.Document,
    widgets: List[Tuple[int, fitz.Widget]],
    fields: Dict[str, Any],
):
    """
    Seite 1 (in deinem PDF ist es oft 'Seite1'): Name, Geburtsdatum, Staatsangehörigkeit,
    Familienstand, Anschrift, IBAN etc.
    Die Feldnamen stammen aus deiner Liste (topmostSubform[...]...Name-Antragsteller, etc.).
    Wir suchen fuzzy (per Teilstring) – robust gegen kleine Variationen.
    """
    # Name Antragsteller
    tgt = _find_widget(widgets, "Name-Antragsteller")
    if tgt:
        pidx, w = tgt
        page = doc[pidx]
        _draw_text_in_widget_rect(page, w.rect, _text(fields.get("full_name", "")), fontsize=10)

    # Geburtsdatum Antragsteller
    tgt = _find_widget(widgets, "Geburtsdatum-Antragsteller")
    if tgt:
        pidx, w = tgt
        doc[pidx].insert_textbox(w.rect, _text(fields.get("dob", "")), fontsize=10, fontname="helv")

    # Staatsangehörigkeit
    for key in ("Staatsangehörigkeit", "Staatsangehoerigkeit"):
        tgt = _find_widget(widgets, key)
        if tgt:
            pidx, w = tgt
            doc[pidx].insert_textbox(w.rect, _text(fields.get("citizenship", "")), fontsize=10, fontname="helv")
            break

    # Familienstand: ledig / verheiratet / geschieden / verwitwet
    marital = _norm(_text(fields.get("marital", "")))
    if marital:
        # Checkbox-Ziele suchen
        # Die Feldnamen in deinem PDF sahen in etwa so aus:
        # ...Familienstand[0].ledig[0], ...verheiratet[0], ...geschieden[0], ...verwitwet[0]
        opts = {
            "ledig": "ledig",
            "verheiratet": "verheiratet",
            "geschieden": "geschieden",
            "verwitwet": "verwitwet",
            "dauernd getrennt": "dauernd getrennt lebend",
        }
        chosen = None
        for k, label in opts.items():
            if k in marital:
                chosen = label
                break
        if chosen:
            tgt = _find_widget(widgets, chosen)
            if tgt:
                pidx, w = tgt
                _draw_checkbox_mark(doc[pidx], w.rect, "X", fontsize=11)

    # Anschrift (als eine Zeile im Feld „Anschrift-Antragsteller“)
    tgt = _find_widget(widgets, "Anschrift-Antragsteller")
    if tgt:
        pidx, w = tgt
        doc[pidx].insert_textbox(w.rect, _compose_address(fields), fontsize=10, fontname="helv")

    # IBAN (unter Zahlungsweg / Punkt 3)
    tgt = _find_widget(widgets, "IBAN")
    if tgt:
        pidx, w = tgt
        doc[pidx].insert_textbox(w.rect, _iban_compact(fields.get("iban", "")), fontsize=10, fontname="helv")

    # Steuer-ID (viele Felder sind in Kästchen aufgeteilt, wir schreiben einmal in die Gesamtbox,
    # wenn es sie gibt; ansonsten ignorieren wir die Kästchen – i.d.R. akzeptiert die Behörde beides)
    for needle in [
        "Steueridentifikationsnummer Antragsteller",
        "Steuer-ID-Antragsteller",
        "Steuer-ID Antragsteller",
    ]:
        tgt = _find_widget(widgets, needle)
        if tgt:
            pidx, w = tgt
            doc[pidx].insert_textbox(w.rect, _text(fields.get("taxid_parent", "")), fontsize=10, fontname="helv")
            break

def _fill_kids(
    doc: fitz.Document,
    widgets: List[Tuple[int, fitz.Widget]],
    kids: List[Dict[str, Any]],
):
    """
    Sehr einfache Variante: wir tragen (falls vorhanden) Kind #1 in die
    Felder „Vorname Kind“, „Geburtsdatum Kind“ ein (so wie sie im PDF heißen).
    Du kannst das Mapping leicht erweitern, wenn die exakten Feldnamen feststehen.
    """
    if not kids:
        return
    k = kids[0]
    # Name Kind
    for needle in ["Name des Kindes", "Name-Kind", "Vorname-Kind", "Vorname des Kindes"]:
        tgt = _find_widget(widgets, needle)
        if tgt:
            pidx, w = tgt
            doc[pidx].insert_textbox(w.rect, _text(k.get("kid_name", "")), fontsize=10, fontname="helv")
            break
    # Geburtsdatum Kind
    for needle in ["Geburtsdatum des Kindes", "Geburtsdatum-Kind"]:
        tgt = _find_widget(widgets, needle)
        if tgt:
            pidx, w = tgt
            doc[pidx].insert_textbox(w.rect, _text(k.get("kid_dob", "")), fontsize=10, fontname="helv")
            break

def fill_kindergeld(template_path: str, out_path: str, data: Dict[str, Any]) -> None:
    """
    Hauptfunktion, die dein /make-pdf aufruft.
    Erwartet payload-Struktur:
      {
        "fields": {...},
        "kids": [ {...}, ... ]
      }
    """
    print(BANNER)

    fields: Dict[str, Any] = (data or {}).get("fields", {}) or {}
    kids: List[Dict[str, Any]] = (data or {}).get("kids", []) or []

    doc = fitz.open(template_path)

    # 1) Alle Widgets einsammeln (Seite, Widget)
    widgets = _collect_widgets(doc)
    if not widgets:
        # Falls kein einziges Formularfeld existiert → kein Problem:
        # wir lassen das PDF unangetastet speichern (oder du würdest an dieser Stelle
        # alternativ eine ReportLab-Variante nutzen).
        doc.save(out_path, deflate=True, garbage=4)
        doc.close()
        return

    # 2) Formularfelder überlagern: Text direkt in deren Rechtecke setzen
    _fill_page1(doc, widgets, fields)
    _fill_kids(doc, widgets, kids)

    # 3) Widgets entfernen (flatten)
    _remove_all_widgets(doc)

    # 4) Speichern (deflate+garbage für kleine Größe)
    doc.save(out_path, deflate=True, garbage=4)
    doc.close()

def make_grid(template_path: str) -> bytes:
    """
    Optional: Debug-Raster. Hier minimalistischer Stub, damit
    app.main weiter importieren kann, falls du /pdf/debug/kg1 nutzt.
    (Du kannst es mit ReportLab ausbauen, wenn du willst.)
    """
    import reportlab.pdfgen.canvas as canvas  # type: ignore
    from reportlab.lib.pagesizes import A4  # type: ignore
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    c.setFont("Helvetica", 7)
    c.setStrokeGray(0.8)
    for x in range(0, int(w), 20):
        c.line(x, 0, x, h)
        c.drawString(x + 1, h - 12, str(x))
    for y in range(0, int(h), 20):
        c.line(0, y, w, y)
        c.drawString(2, y + 2, str(y))
    c.showPage()
    c.save()
    return buf.getvalue()
