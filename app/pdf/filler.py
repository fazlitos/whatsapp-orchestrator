# app/pdf/filler.py
"""
KG1 PDF Filler – zeichnet Text direkt auf die Feldkoordinaten (Baseline-korrekt)
Voraussetzung: PyMuPDF (fitz)
    pip install PyMuPDF
"""

from __future__ import annotations
import re
from typing import Dict, Any, Iterable, Optional, Tuple

import fitz  # PyMuPDF


# ------------------------------------------------------------
# Hilfen für robustes Matching & Zeichnen
# ------------------------------------------------------------

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def _find_widget(
    widgets: Iterable[fitz.Widget],
    *needles: str,
    contains_all: bool = True
) -> Optional[fitz.Widget]:
    """
    Findet ein Widget, dessen Feldname alle (oder eines der) Teilstücke enthält.
    Vergleicht 'case-insensitive'.
    """
    needles = tuple(_norm(n) for n in needles if n)
    for w in widgets:
        name = _norm(getattr(w, "field_name", "") or "")
        if not name:
            continue
        if contains_all:
            if all(n in name for n in needles):
                return w
        else:
            if any(n in name for n in needles):
                return w
    return None


def _draw_in_rect(
    page: fitz.Page,
    rect: fitz.Rect,
    text: str,
    size: float = 10.0,
    font: str = "helv",
    pad_x: float = 2.0,
    color: Tuple[float, float, float] = (0, 0, 0),
):
    """
    Zeichnet Text baseline-korrekt in ein Formularrechteck.
    Baseline ≈ untere Kante minus ~Descent (0.22 * Schriftgröße).
    """
    if not text:
        return
    baseline_y = rect.y1 - max(2.0, 0.22 * size)
    x = rect.x0 + pad_x
    page.insert_text(
        fitz.Point(x, baseline_y),
        text,
        fontsize=size,
        fontname=font,
        color=color,
    )


def _draw_x_checkbox(
    page: fitz.Page,
    rect: fitz.Rect,
    size_factor: float = 0.75,
    color: Tuple[float, float, float] = (0, 0, 0),
    width: float = 1.0,
):
    """
    Zeichnet ein 'X' in eine Checkbox (ohne Formular-Widget zu verwenden).
    """
    w = rect.width * size_factor
    h = rect.height * size_factor
    cx = (rect.x0 + rect.x1) / 2
    cy = (rect.y0 + rect.y1) / 2
    r = fitz.Rect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)

    page.draw_line(fitz.Point(r.x0, r.y0), fitz.Point(r.x1, r.y1), color=color, width=width)
    page.draw_line(fitz.Point(r.x0, r.y1), fitz.Point(r.x1, r.y0), color=color, width=width)


def _outline_debug(page: fitz.Page, rect: fitz.Rect):
    """Optionales Debug – Umrandung + Baseline einzeichnen."""
    page.draw_rect(rect, color=(1, 0, 0), width=0.6)
    baseline_y = rect.y1 - 0.22 * 10
    page.draw_line(
        fitz.Point(rect.x0, baseline_y),
        fitz.Point(rect.x1, baseline_y),
        color=(0, 0, 1),
        width=0.4,
    )


# ------------------------------------------------------------
# Feld-Hinweise für KG1 (robust via substring matching)
# (Die Namen stammen aus deiner Feldliste, werden aber
# über contains-Matches gefunden, damit kleine Abweichungen
# nicht stören.)
# ------------------------------------------------------------

KG1_HINTS = {
    # Seite 2 (Antragsteller: Name/Adresse/DOB/Staatsangehörigkeit …)
    "full_name": (
        "seite1", "punkt-1", "pkt-1-zeile-1", "name-antragsteller"
    ),
    "familienname": (
        "seite1", "familienname", "antragsteller"
    ),
    "vorname": (
        "seite1", "vorname", "antragsteller"
    ),
    "dob": (
        "seite1", "geburtsdatum", "antragsteller"
    ),
    "geburtsort": (
        "seite1", "geburtsort", "antragsteller"
    ),
    "citizenship": (
        "seite1", "staatsangehörigkeit"
    ),
    "address": (
        "seite1", "anschrift", "antragsteller"
    ),
    "iban": (
        "seite1", "punkt-3", "iban"
    ),

    # Steuer-ID – einige Formulare haben mehrere Kästchen / Segmente
    # Wir sammeln beliebige Widgets mit 'steuer' innerhalb Seite1.
    "taxid_any": (
        "seite1", "steuer"
    ),

    # Familienstand – Checkboxen (ledig / verheiratet / geschieden / verwitwet / getrennt)
    "ms_ledig": (
        "seite1", "familienstand", "ledig"
    ),
    "ms_verheiratet": (
        "seite1", "familienstand", "verheiratet"
    ),
    "ms_geschieden": (
        "seite1", "familienstand", "geschieden"
    ),
    "ms_verwitwet": (
        "seite1", "familienstand", "verwitwet"
    ),
    "ms_getrennt": (
        "seite1", "familienstand", "dauernd", "getrennt"
    ),
    # ggf. eingetragene Lebenspartnerschaft:
    "ms_eingetragen": (
        "seite1", "eingetragener", "lebenspartnerschaft"
    ),
}

MARITAL_MAP = {
    "ledig": "ms_ledig",
    "verheiratet": "ms_verheiratet",
    "geschieden": "ms_geschieden",
    "verwitwet": "ms_verwitwet",
    "dauernd_getrennt": "ms_getrennt",
    "getrennt": "ms_getrennt",
    "eingetragen": "ms_eingetragen",
    "lebenspartnerschaft": "ms_eingetragen",
}


# ------------------------------------------------------------
# Öffentliche API
# ------------------------------------------------------------

def list_pdf_fields(template_path: str) -> Dict[str, Any]:
    """
    Gibt alle Formularfelder (Namen + Seite + Rect) zurück.
    Nützlich für Debug / Kontrolle.
    """
    out: Dict[str, Any] = {"pages": []}
    doc = fitz.open(template_path)
    try:
        for p in range(len(doc)):
            page = doc[p]
            arr = []
            for w in page.widgets():
                arr.append({
                    "name": w.field_name,
                    "type": getattr(w, "field_type", None),
                    "rect": [w.rect.x0, w.rect.y0, w.rect.x1, w.rect.y1],
                })
            out["pages"].append({"index": p, "widgets": arr})
    finally:
        doc.close()
    return out


def fill_kindergeld(
    template_path: str,
    output_path: str,
    payload: Dict[str, Any],
    *,
    debug_outline: bool = False
) -> None:
    """
    Füllt das KG1-PDF, indem Text baseline-korrekt auf die
    Koordinaten der Formularfelder gezeichnet wird.

    payload erwartet:
    {
      "fields": {
        "full_name": "...",
        "familienname": "...",      # optional
        "vorname": "...",           # optional
        "dob": "TT.MM.JJJJ",
        "geburtsort": "...",        # optional
        "citizenship": "deutsch",
        "addr_street": "...",
        "addr_plz": "...",
        "addr_city": "...",
        "taxid_parent": "11-stellig",
        "iban": "DE..."
        "marital": "ledig|verheiratet|geschieden|verwitwet|getrennt|eingetragen"
      }
    }
    """
    data = (payload or {}).get("fields", {}) or {}

    # Adresse zusammensetzen (einige KG1 haben 1 Feld für Anschrift)
    address = " ".join(
        s for s in [
            data.get("addr_street", ""),
            f"{data.get('addr_plz', '')} {data.get('addr_city', '')}".strip()
        ] if s
    ).strip()

    # Steuer-ID ggf. segmentieren (manche Formulare haben mehrere Kästchen)
    taxid = re.sub(r"\D+", "", data.get("taxid_parent", "") or "")

    doc = fitz.open(template_path)
    try:
        # Seite 2: Index 1 (0-basiert)
        page = doc[1]
        widgets = list(page.widgets())

        def put_by_hint(hint_key: str, text: str, size: float = 10.0):
            if not text:
                return
            needles = KG1_HINTS.get(hint_key)
            if not needles:
                return
            w = _find_widget(widgets, *needles, contains_all=True)
            if not w:
                return
            if debug_outline:
                _outline_debug(page, w.rect)
            _draw_in_rect(page, w.rect, text, size=size)

        # 1) Name – Variante A: ein kombiniertes Feld ("Name-Antragsteller")
        if data.get("full_name"):
            put_by_hint("full_name", data["full_name"], size=10.0)
        else:
            # Variante B: getrennte Felder (Familienname / Vorname)
            if data.get("familienname"):
                put_by_hint("familienname", data["familienname"], size=10.0)
            if data.get("vorname"):
                put_by_hint("vorname", data["vorname"], size=10.0)

        # 2) Geburtstag / Geburtsort / Staatsangehörigkeit
        put_by_hint("dob", data.get("dob", ""), size=10.0)
        put_by_hint("geburtsort", data.get("geburtsort", ""), size=10.0)
        put_by_hint("citizenship", data.get("citizenship", ""), size=10.0)

        # 3) Anschrift
        if address:
            put_by_hint("address", address, size=10.0)

        # 4) IBAN
        if data.get("iban"):
            put_by_hint("iban", data["iban"], size=10.0)

        # 5) Steuer-ID – versuche mehrere Felder zu füllen, falls vorhanden
        if taxid:
            # alle Widgets mit 'steuer' auf Seite 2
            steuer_widgets = [
                w for w in widgets
                if "steuer" in _norm(getattr(w, "field_name", ""))
            ]
            if steuer_widgets:
                # Wenn einzelne Kästchen, fülle von links nach rechts jeweils 1–3 Zeichen
                # (hier einfach 1 pro Feld – falls dein Formular Segmente à 2/3 Zeichen hat,
                # kannst du hier die Logik anpassen)
                for i, w in enumerate(sorted(steuer_widgets, key=lambda x: x.rect.x0)):
                    if i >= len(taxid):
                        break
                    if debug_outline:
                        _outline_debug(page, w.rect)
                    _draw_in_rect(page, w.rect, taxid[i], size=10.0)

        # 6) Familienstand – Checkboxen
        marital = (data.get("marital") or "").strip().lower()
        if marital:
            # Normalisieren
            key = "eingetragen" if "lebenspartner" in marital else marital.replace(" ", "_")
            hint = MARITAL_MAP.get(key)
            if hint:
                needles = KG1_HINTS.get(hint)
                cb = _find_widget(widgets, *needles, contains_all=True) if needles else None
                if cb:
                    if debug_outline:
                        _outline_debug(page, cb.rect)
                    _draw_x_checkbox(page, cb.rect, size_factor=0.7)

        # Tipp: Wenn Widgets störend sind (sichtbare Frames/Hintergründe),
        # kann man sie entfernen, nachdem der Text gezeichnet wurde:
        # for w in list(page.widgets()):
        #     page.delete_widget(w)

        doc.save(output_path)
    finally:
        doc.close()


# ------------------------------------------------------------
# Manuelle Kurztests (lokal ausführen, wenn gewünscht)
# ------------------------------------------------------------
if __name__ == "__main__":
    # Beispiel-Nutzung
    sample = {
        "fields": {
            "full_name": "Max Mustermann",
            # Alternativ:
            # "familienname": "Mustermann",
            # "vorname": "Max",
            "dob": "01.01.1990",
            "geburtsort": "Berlin",
            "citizenship": "deutsch",
            "addr_street": "Teststraße 1",
            "addr_plz": "10115",
            "addr_city": "Berlin",
            "taxid_parent": "12345678901",
            "iban": "DE89370400440532013000",
            "marital": "ledig",
        }
    }
    tpl = "app/pdf/templates/kg1.pdf"
    out = "/tmp/kg1-filled.pdf"
    fill_kindergeld(tpl, out, sample, debug_outline=False)
    print("✅ PDF erstellt:", out)
