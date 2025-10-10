# app/pdf/filler.py
# ------------------------------------------------------------
# KG1 PDF-Filler (robust, viewer-unabhängig)
# - Liest Widget-Rechtecke (Formularfelder) aus
# - Schreibt Text direkt in die Feld-Rects (insert_textbox)
# - Zeichnet "X" in Checkbox-Rects
# - Entfernt danach die Formularfelder (AcroForm), damit Viewer
#   nichts „anders“ rendert (keine kaputten AP-Streams mehr)
# ------------------------------------------------------------

from __future__ import annotations
import os
from typing import Dict, Any, List, Tuple, Optional
import fitz  # PyMuPDF


# ---- Hilfen ------------------------------------------------

def _norm(s: str) -> str:
    return s.casefold().strip()


def _field_index(doc: fitz.Document) -> Dict[str, Tuple[int, fitz.Rect, str]]:
    """
    Erzeugt ein Index: feldname_lower -> (page_index, rect, original_name)
    """
    idx: Dict[str, Tuple[int, fitz.Rect, str]] = {}
    for p in range(len(doc)):
        page = doc[p]
        widgets = page.widgets() or []
        for w in widgets:
            # einige Widgets haben keinen Namen
            name = str(getattr(w, "field_name", "") or "")
            if not name:
                continue
            key = _norm(name)
            idx[key] = (p, w.rect, name)
    return idx


def _find_by_tokens(index: Dict[str, Tuple[int, fitz.Rect, str]],
                    tokens: List[str]) -> Optional[Tuple[int, fitz.Rect, str]]:
    """
    Sucht Feld, dessen Name *alle* tokens (case-insensitive) enthält.
    """
    toks = [_norm(t) for t in tokens if t]
    for key, triple in index.items():
        if all(t in key for t in toks):
            return triple
    return None


def _draw_text_in_rect(page: fitz.Page, rect: fitz.Rect, text: str,
                       fontsize: float = 10.0, hpad: float = 1.5, vpad: float = 1.0,
                       align: int = 0) -> None:
    """
    Zeichnet Text innerhalb des Rechtecks (links bündig als Default).
    align: 0=links, 1=zentriert, 2=rechts
    """
    if not text:
        return
    # leicht innen verschieben (Padding), damit Text nicht am Rand klebt
    r = fitz.Rect(rect.x0 + hpad, rect.y0 + vpad, rect.x1 - hpad, rect.y1 - vpad)
    # Helvetica ist überall verfügbar
    page.insert_textbox(r, text, fontsize=fontsize, fontname="helv",
                        color=(0, 0, 0), align=align, encoding=0)


def _draw_checkbox_x(page: fitz.Page, rect: fitz.Rect) -> None:
    """
    Setzt ein 'X' mittig in die Checkbox-Rect.
    """
    # Größe relativ zur Box
    size = max(10, min(rect.width, rect.height) * 0.9)
    cx = rect.x0 + rect.width / 2.0
    cy = rect.y0 + rect.height / 2.0
    # Ein kleines zentriertes X. (Font helv passt zuverlässig)
    page.insert_text((cx, cy), "X", fontsize=size, fontname="helv",
                     color=(0, 0, 0), render_mode=0, overlay=True, align=1)


def _remove_all_form_fields(doc: fitz.Document) -> None:
    """
    Entfernt alle Widgets und (best-effort) die AcroForm-Struktur.
    """
    for p in range(len(doc)):
        page = doc[p]
        widgets = list(page.widgets() or [])
        for w in widgets:
            page.delete_widget(w)

    # Best-effort: AcroForm im Katalog ausblenden (PyMuPDF high-level).
    # Nicht alle PDF haben /AcroForm explizit im Katalog – das ist ok.
    try:
        xref = doc._getXrefString(doc._catalog.xref)  # noqa
        # keine harte Manipulation – das Löschen der Widgets reicht
    except Exception:
        pass


# ---- Fülllogik --------------------------------------------

def fill_kindergeld(template_path: str, out_path: str, data: Dict[str, Any]) -> str:
    """
    Füllt das KG1-PDF robust aus:
      - ermittelt Widget-Rects
      - zeichnet Text direkt in die Felder
      - setzt X in Checkboxen (Familienstand)
      - entfernt Formularfelder
    Rückgabe: Pfad der erzeugten Datei
    """
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template not found: {template_path}")

    # Daten entpacken / normalisieren
    fields: Dict[str, Any] = (data or {}).get("fields", {}) or {}
    kids: List[Dict[str, Any]] = (data or {}).get("kids", []) or []

    full_name = str(fields.get("full_name", "")).strip()
    first_name = str(fields.get("first_name", "")).strip()
    if not first_name and full_name:
        # optional split: "Max Mustermann" -> first_name="Max"
        first_name = full_name.split(" ", 1)[0]
    dob = str(fields.get("dob", "")).strip()
    citizenship = str(fields.get("citizenship", "")).strip()
    taxid_parent = ''.join(c for c in str(fields.get("taxid_parent", "")).strip() if c.isdigit())
    street = str(fields.get("addr_street", "")).strip()
    plz = str(fields.get("addr_plz", "")).strip()
    city = str(fields.get("addr_city", "")).strip()
    address_line = ', '.join(x for x in [street, ' '.join([plz, city]).strip()] if x)
    iban = str(fields.get("iban", "")).strip().replace(" ", "")
    marital = _norm(str(fields.get("marital", "")))

    # Dokument öffnen
    doc = fitz.open(template_path)

    # Koordinaten-Index aller Felder
    idx = _field_index(doc)

    # --- Textfelder ---
    # Feldnamen anhand Tokens finden (entsprechend deinem Dump)
    # Seite 2 (Seite[1] im PDF) – Antragsteller
    targets = [
        # (Datenwert, Tokens in Feldname, optionale Schriftgröße)
        (full_name,     ["punkt-1", "pkt-1-zeile-1", "name-antragsteller"], 10.0),
        (first_name,    ["pkt-1-zeile-2", "vorname-antragsteller"],         10.0),
        (dob,           ["pkt-1-zeile-3", "geburtsdatum-antragsteller"],     10.0),
        (citizenship,   ["pkt-1-zeile-3", "staatsangehörigkeit-antragsteller"], 10.0),
        (address_line,  ["punkt-1", "anschrift-antragsteller"],              10.0),
        (iban,          ["punkt-3", "iban"],                                 11.0),
    ]

    for value, tokens, size in targets:
        if not value:
            continue
        hit = _find_by_tokens(idx, tokens)
        if not hit:
            continue
        p_idx, rect, _name = hit
        page = doc[p_idx]
        _draw_text_in_rect(page, rect, value, fontsize=size)

    # --- Steuer-ID (falls im Kopf/Boxes) ---
    # Dein Formular hat mehrere kleine Boxen – oft 11 Kästchen.
    # Wir verteilen die Ziffern über alle Widgets, deren Name „steuerliche identifikationsnummer“
    # und Zeilen-/Kästchenhinweis enthält. Um es robust zu halten, schreiben wir nur,
    # wenn passende Felder gefunden werden.
    if taxid_parent:
        # Sammle alle passenden Kästchen (sortiert nach x0)
        tax_boxes: List[Tuple[int, fitz.Rect, str]] = []
        for key, triple in idx.items():
            if ("steuerliche" in key and "identifikationsnummer" in key) or "st-id" in key:
                tax_boxes.append(triple)
        tax_boxes.sort(key=lambda t: (t[0], t[1].y0, t[1].x0))
        digits = list(taxid_parent)
        di = 0
        for p_idx, rect, _ in tax_boxes:
            if di >= len(digits):
                break
            page = doc[p_idx]
            _draw_text_in_rect(page, rect, digits[di], fontsize=11.0, align=1)
            di += 1

    # --- Familienstand (Checkboxen) ---
    # Wir suchen Checkbox-Rects über Tokens und setzen „X“ hinein.
    # Unterstützt: ledig / verheiratet / geschieden / verwitwet /
    #              in_eingetragener (Lebenspartnerschaft) /
    #              aufgehobene (Lebenspartnerschaft) /
    #              dauernd_getrennt
    def mark_by_tokens(tokens: List[str]) -> bool:
        hit = _find_by_tokens(idx, tokens)
        if not hit:
            return False
        p_idx, rect, _name = hit
        page = doc[p_idx]
        _draw_checkbox_x(page, rect)
        return True

    if marital:
        if "ledig" in marital:
            mark_by_tokens(["familienstand", "ledig"])
        elif "verheirat" in marital:
            mark_by_tokens(["familienstand", "verheiratet"])
        elif "geschied" in marital:
            mark_by_tokens(["familienstand", "geschieden"])
        elif "verwitw" in marital:
            mark_by_tokens(["familienstand", "verwitwet"])
        elif "eingetrag" in marital:
            mark_by_tokens(["lebenspartnerschaft", "eingetragen"])
        elif "aufgehoben" in marital:
            mark_by_tokens(["lebenspartnerschaft", "aufgehoben"])
        elif "getrennt" in marital:
            mark_by_tokens(["dauernd", "getrennt"])

    # --- (Optional) Kinder – hier nur ein Beispiel:
    # Viele KG1-Varianten führen Kinder separat in „Anlage Kind“ auf.
    # Falls Felder im Hauptformular existieren, entsprechende Tokens eintragen und zuordnen:
    # for i, kid in enumerate(kids[:2]):  # z. B. max. 2 Zeilen
    #     kid_name = str(kid.get("kid_name", "")).strip()
    #     kid_dob  = str(kid.get("kid_dob", "")).strip()
    #     if kid_name:
    #         hit = _find_by_tokens(idx, ["punkt-4", f"zeile-{i+1}", "name-kind"])
    #         if hit:
    #             p_idx, rect, _ = hit
    #             _draw_text_in_rect(doc[p_idx], rect, kid_name, fontsize=10.0)
    #     if kid_dob:
    #         hit = _find_by_tokens(idx, ["punkt-4", f"zeile-{i+1}", "geburtsdatum-kind"])
    #         if hit:
    #             p_idx, rect, _ = hit
    #             _draw_text_in_rect(doc[p_idx], rect, kid_dob, fontsize=10.0)

    # Formularfelder entfernen / flatten
    _remove_all_form_fields(doc)

    # speichern – garbage=4 räumt unbenutzte Objekte weg
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    doc.save(out_path, deflate=True, garbage=4)
    doc.close()
    return out_path


# ---- Grid-/Debug-Helfer (optional) ------------------------

def make_grid(template_path: str) -> bytes:
    """
    Erzeugt eine Grid-PDF (Debug): legt ein feines Raster über Seite 1,
    um Koordinaten visuell prüfen zu können. Optional zu Debug-Zwecken.
    """
    import io
    buf = io.BytesIO()
    doc = fitz.open(template_path)
    page = doc[0]
    w, h = page.rect.width, page.rect.height

    # Zeichne Raster
    for x in range(0, int(w), 20):
        page.draw_line((x, 0), (x, h), color=(0.8, 0.8, 0.8), width=0.2)
        page.insert_text((x + 2, 10), str(x), fontsize=6, color=(0.4, 0.4, 0.4))
    for y in range(0, int(h), 20):
        page.draw_line((0, y), (w, y), color=(0.8, 0.8, 0.8), width=0.2)
        page.insert_text((2, y + 8), str(y), fontsize=6, color=(0.4, 0.4, 0.4))

    # Widgets sichtbar machen
    widgets = page.widgets() or []
    for wdg in widgets:
        rect = wdg.rect
        page.draw_rect(rect, color=(0, 0, 1), width=0.6)
        page.insert_text((rect.x0 + 2, rect.y0 - 2),
                         wdg.field_name or "∅", fontsize=6, color=(0, 0, 1))

    doc.save(buf)
    doc.close()
    return buf.getvalue()


# ---- Standalone-Test --------------------------------------

if __name__ == "__main__":
    # Lokaler Test (ohne FastAPI), erzeugt out/test-kg1.pdf
    SAMPLE = {
        "fields": {
            "full_name": "Max Mustermann",
            "dob": "01.01.1990",
            "addr_street": "Teststraße 1",
            "addr_plz": "10115",
            "addr_city": "Berlin",
            "taxid_parent": "12345678901",
            "iban": "DE89370400440532013000",
            "marital": "ledig",
            "citizenship": "deutsch"
        }
    }
    tmpl = "app/pdf/templates/kg1.pdf"
    outp = "out/test-kg1.pdf"
    print("Schreibe:", fill_kindergeld(tmpl, outp, SAMPLE))
    print("Fertig.")
