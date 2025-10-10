# -*- coding: utf-8 -*-
"""
PDF Filler für KG1 (Formular 442.pdf)
Funktionen:
- dump_widgets(pdf_path) -> Liste aller Felder mit Name/Typ/Seite/Rect
- make_debug_overlay(pdf_path, out_path) -> zeigt jede Widget-Position mit Label
- fill_442(pdf_path, out_path, data) -> Felder setzen, Appearance erzeugen, flatten
Erfordert: PyMuPDF (fitz)
"""
from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from typing import Dict, List, Any, Optional
import fitz  # PyMuPDF


# ---------- Datentypen ----------

@dataclass
class WidgetInfo:
    name: str
    field_type: str
    page: int
    rect: List[float]  # [x0, y0, x1, y1]


# ---------- Widget-Tools ----------

def _widget_type(w: fitz.Widget) -> str:
    t = w.field_type
    # 0: unknown, 1: button, 2: text, 3: checkbox, 4: combobox, 5: listbox, 6: signature, 7: radio
    mapping = {
        1: "button",
        2: "text",
        3: "checkbox",
        4: "combobox",
        5: "listbox",
        6: "signature",
        7: "radio",
    }
    return mapping.get(t, str(t))


def dump_widgets(pdf_path: str) -> List[WidgetInfo]:
    """Liest alle Widgets/Felder aus und liefert strukturierte Infos."""
    doc = fitz.open(pdf_path)
    out: List[WidgetInfo] = []
    for pno in range(len(doc)):
        page = doc[pno]
        for w in page.widgets():
            name = w.field_name or f"unnamed_{pno}_{int(w.rect.x0)}_{int(w.rect.y0)}"
            out.append(WidgetInfo(
                name=name,
                field_type=_widget_type(w),
                page=pno,
                rect=[w.rect.x0, w.rect.y0, w.rect.x1, w.rect.y1],
            ))
    doc.close()
    return out


def save_widgets_json(pdf_path: str, json_path: str) -> None:
    data = [asdict(w) for w in dump_widgets(pdf_path)]
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------- Debug-Overlay ----------

def make_debug_overlay(pdf_path: str, out_path: str) -> None:
    """
    Erzeugt ein PDF, in dem jedes Feld mit Rahmen & Label (Name, Typ, Seite) markiert ist.
    Super schnell, um die richtigen Feldnamen zu identifizieren.
    """
    doc = fitz.open(pdf_path)
    label_font = "helv"
    for pno in range(len(doc)):
        page = doc[pno]
        for w in page.widgets():
            name = w.field_name or "(unnamed)"
            wtype = _widget_type(w)
            r = w.rect
            # halbtransparente Fläche
            shape = page.new_shape()
            shape.draw_rect(r)
            shape.finish(color=(1, 0, 0), fill=(1, 0.9, 0.9), fill_opacity=0.2, width=0.6)
            shape.commit()

            # Label oberhalb links
            label = f"{name}\n({wtype}) p{pno}"
            page.insert_text(
                fitz.Point(r.x0, max(0, r.y0 - 3)),
                label,
                fontname=label_font,
                fontsize=6.5,
                color=(0.1, 0.1, 0.1),
            )
    doc.save(out_path, deflate=True)
    doc.close()


# ---------- Formular befüllen ----------

def _set_text(w: fitz.Widget, value: str) -> None:
    w.field_value = value
    w.update()  # erzeugt Appearance


def _set_checkbox(w: fitz.Widget, checked: bool) -> None:
    # PyMuPDF: für Checkboxen reicht field_value auf "Yes"/"Off"
    w.field_value = "Yes" if checked else "Off"
    w.update()


def _flatten(doc: fitz.Document) -> None:
    """
    'Formularfelder' visuell festschreiben:
    - Widgets werden in statischen Inhalt gerendert (Appearance beachten)
    - Danach Widgets löschen -> kein Verschieben/Rendering-Bug mehr möglich
    """
    for pno in range(len(doc)):
        page = doc[pno]
        for w in list(page.widgets()):
            # Falls ein Widget keine Appearance hat, erzeugen:
            try:
                w.update()
            except Exception:
                pass
        # Jetzt alle Widgets löschen (Inhalt bleibt durch Appearance erhalten)
        for w in list(page.widgets()):
            try:
                page.delete_widget(w)
            except Exception:
                pass


def _first(doc: fitz.Document, field_name: str) -> Optional[fitz.Widget]:
    """Hilfsfunktion: erstes Widget mit exakt diesem Namen auf allen Seiten finden."""
    for pno in range(len(doc)):
        for w in doc[pno].widgets():
            if (w.field_name or "") == field_name:
                return w
    return None


def fill_442(pdf_path: str, out_path: str, data: Dict[str, Any]) -> None:
    """
    Befüllt das Formular 442.pdf.
    `data` hat die logischen Felder. Mapping unten ordnet sie echten Widget-Namen zu.
    """
    # --------------------------
    # 1) Mapping: LOGISCH -> WIDGET-NAME
    # Die Namen unten stammen aus deiner Feldliste (Beispiele, Seite 1/2).
    # Wenn etwas um 1–2 Felder versetzt ist: einmal Overlay erzeugen und Namen anpassen.
    # --------------------------
    MAP: Dict[str, str] = {
        # Seite 1 – Kopf / Person
        "kgnr_teil1": "TEXTFIELD.p0.x24.y15",     # Kindergeld-Nr. (links)
        "kgnr_teil2": "TEXTFIELD.p0.x22.y27",
        "kgnr_teil3": "TEXTFIELD.p0.x28.y27",
        "kgnr_teil4": "TEXTFIELD.p0.x38.y27",
        "kgnr_teil5": "TEXTFIELD.p0.x44.y27",
        "kgnr_teil6": "TEXTFIELD.p0.x50.y27",
        "kgnr_teil7": "TEXTFIELD.p0.x60.y27",
        "kgnr_teil8": "TEXTFIELD.p0.x66.y27",
        "kgnr_teil9": "TEXTFIELD.p0.x72.y27",
        "kgnr_teil10": "TEXTFIELD.p0.x82.y27",
        "kgnr_teil11": "TEXTFIELD.p0.x88.y27",
        "kgnr_teil12": "TEXTFIELD.p0.x94.y27",

        # Anzahl Anlagen Kind:
        "anz_anlagen": "TEXTFIELD.p0.x140.y43",

        # Antragsteller*in (Familienname / Vorname – erfahrungsgemäß zwei Zeilen darunter)
        "familienname": "TEXTFIELD.p0.x22.y103",
        "vorname":     "TEXTFIELD.p0.x22.y113",

        # Geburtsdatum / Geburtsort:
        "geburtsdatum": "TEXTFIELD.p0.x22.y125",
        "geburtsort":   "TEXTFIELD.p0.x112.y125",

        # Staatsangehörigkeit (rechts neben Geschlecht):
        "staatsang": "TEXTFIELD.p0.x140.y125",

        # Anschrift (Fließtextblock):
        "anschrift": "TEXTFIELD.p0.x22.y171",

        # Familienstand (Checkboxen-Blöcke, können leicht variieren)
        "fs_ledig":        "CHECKBOX.p0.x42.y146",
        "fs_verheiratet":  "CHECKBOX.p0.x94.y146",
        "fs_geschieden":   "CHECKBOX.p0.x120.y146",
        "fs_aufgehoben":   "CHECKBOX.p0.x94.y152",
        "fs_getrennt":     "CHECKBOX.p0.x154.y152",
        "fs_verwitwet":    "CHECKBOX.p0.x120.y152",

        # Zahlungsweg (Seite 2, IBAN + Bank)
        "iban": "TEXTFIELD.p1.x22.y221",
        "bic":  "TEXTFIELD.p1.x108.y220",
        "bank": "TEXTFIELD.p1.x22.y251",
        "kontoinhaber": "TEXTFIELD.p1.x108.y250",

        # Kontoinhaber ist antragstellende Person (Checkbox links Seite 2)
        "kh_ist_antragsteller": "CHECKBOX.p0.x20.y233",
        # …und "nicht antragstellende Person, sondern …":
        "kh_andere_person":     "CHECKBOX.p0.x20.y239",
        "kh_andere_name":       "TEXTFIELD.p0.x90.y239",
    }

    # --------------------------
    # 2) Logische Daten übernehmen
    # Erwartete 'data'-Struktur (Beispiel):
    # {
    #   "last_name": "Muster",
    #   "first_name": "Max",
    #   "birth_date": "01.01.1990",
    #   "birth_place": "Berlin",
    #   "citizenship": "deutsch",
    #   "address": "Teststraße 1, 10115 Berlin",
    #   "marital": "ledig" | "verheiratet" | "geschieden" | "verwitwet" | "aufgehoben" | "getrennt",
    #   "iban": "DE...",
    #   "bic": "BIC...",
    #   "bank": "Bankname",
    #   "kh": "antragsteller" | "andere",
    #   "kh_name": "…" (falls kh=andere)
    #   "kg_parts": ["1","2",...,"12"]  # optional: die 12 Segmente der KG-Nr.
    #   "anz_anlagen": "1"
    # }
    # --------------------------
    last_name   = data.get("last_name", "")
    first_name  = data.get("first_name", "")
    birth_date  = data.get("birth_date", "")
    birth_place = data.get("birth_place", "")
    citizenship = data.get("citizenship", "")
    address     = data.get("address", "")
    marital     = (data.get("marital", "") or "").lower()
    iban        = data.get("iban", "")
    bic         = data.get("bic", "")
    bank        = data.get("bank", "")
    kh          = (data.get("kh", "antragsteller") or "").lower()   # kontoinhaber
    kh_name     = data.get("kh_name", "")
    kg_parts    = data.get("kg_parts", [])
    anz_anlagen = data.get("anz_anlagen", "")

    doc = fitz.open(pdf_path)

    # 2.1 KG-Nr. (12 Teilfelder – wenn mitgegeben)
    if kg_parts and len(kg_parts) == 12:
        for i, part in enumerate(kg_parts, start=1):
            w = _first(doc, MAP[f"kgnr_teil{i}"])
            if w: _set_text(w, part)

    # 2.2 Anzahl "Anlage Kind"
    if anz_anlagen:
        w = _first(doc, MAP["anz_anlagen"])
        if w: _set_text(w, anz_anlagen)

    # 2.3 Basisdaten
    mapping_text = {
        "familienname": last_name,
        "vorname": first_name,
        "geburtsdatum": birth_date,
        "geburtsort": birth_place,
        "staatsang": citizenship,
        "anschrift": address,
        "iban": iban,
        "bic": bic,
        "bank": bank,
        "kontoinhaber": (first_name + " " + last_name).strip() if kh == "antragsteller" else kh_name,
        "kh_andere_name": kh_name,
    }
    for key, value in mapping_text.items():
        if not value:
            continue
        fname = MAP.get(key)
        if not fname:
            continue
        w = _first(doc, fname)
        if w and _widget_type(w) in ("text", "combobox", "listbox"):
            _set_text(w, value)

    # 2.4 Familienstand – Checkboxen
    cb_map = {
        "ledig":       "fs_ledig",
        "verheiratet": "fs_verheiratet",
        "geschieden":  "fs_geschieden",
        "verwitwet":   "fs_verwitwet",
        "aufgehoben":  "fs_aufgehoben",
        "getrennt":    "fs_getrennt",
        "dauernd getrennt": "fs_getrennt",
        "dauernd getrennt lebend": "fs_getrennt",
    }
    target_cb = cb_map.get(marital, "")
    for label, fname_key in cb_map.items():
        fname = MAP.get(fname_key)
        w = _first(doc, fname) if fname else None
        if w and _widget_type(w) == "checkbox":
            _set_checkbox(w, fname_key == target_cb)

    # 2.5 Kontoinhaber-Logik
    if kh == "antragsteller":
        w = _first(doc, MAP["kh_ist_antragsteller"])
        if w: _set_checkbox(w, True)
        w = _first(doc, MAP["kh_andere_person"])
        if w: _set_checkbox(w, False)
    else:
        w = _first(doc, MAP["kh_ist_antragsteller"])
        if w: _set_checkbox(w, False)
        w = _first(doc, MAP["kh_andere_person"])
        if w: _set_checkbox(w, True)
        # Name der anderen Person wurde oben in mapping_text gesetzt

    # 3) Flatten → Erscheinungsbilder festschreiben & Widgets entfernen
    _flatten(doc)
    doc.save(out_path, deflate=True)
    doc.close()


# ---------- Wrapper für Orchestrator-Kompatibilität ----------

def fill_kindergeld(template_path: str, out_path: str, data: Dict[str, Any]) -> None:
    """
    Kompatibilitäts-Wrapper für den Orchestrator.
    Konvertiert das Orchestrator-Format zu fill_442-Format.
    """
    fields = data.get("fields", {})
    kids = data.get("kids", [])
    
    # Name splitten
    full_name = fields.get("full_name", "")
    name_parts = full_name.split(maxsplit=1)
    first_name = name_parts[0] if name_parts else ""
    last_name = name_parts[1] if len(name_parts) > 1 else ""
    
    # Adresse zusammenbauen
    address = f"{fields.get('addr_street', '')}, {fields.get('addr_plz', '')} {fields.get('addr_city', '')}".strip(", ")
    
    # fill_442 Datenstruktur
    pdf_data = {
        "first_name": first_name,
        "last_name": last_name,
        "birth_date": fields.get("dob", ""),
        "birth_place": "",  # nicht im Orchestrator
        "citizenship": fields.get("citizenship", ""),
        "address": address,
        "marital": fields.get("marital", ""),
        "iban": fields.get("iban", ""),
        "bic": "",  # nicht im Orchestrator
        "bank": "",  # nicht im Orchestrator
        "kh": "antragsteller",
        "anz_anlagen": str(len(kids)),
    }
    
    fill_442(template_path, out_path, pdf_data)


def make_grid(template_path: str) -> bytes:
    """Grid-Funktion für Debug-Endpoint"""
    import io
    out_path = "/tmp/grid_temp.pdf"
    make_debug_overlay(template_path, out_path)
    with open(out_path, "rb") as f:
        return f.read()


# ---------- Mini-CLI-Test ----------

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="KG1 (442.pdf) Debug/Fill")
    ap.add_argument("--pdf", default="app/pdf/templates/442.pdf", help="Pfad zur 442.pdf")
    ap.add_argument("--out", default="/tmp/kg1_out.pdf", help="Ausgabedatei")
    ap.add_argument("--mode", choices=["dump", "overlay", "fill"], default="overlay")
    ap.add_argument("--data", default="", help="JSON mit logischen Feldern (bei mode=fill)")
    args = ap.parse_args()

    if args.mode == "dump":
        save_widgets_json(args.pdf, args.out)
        print(f"Widgets -> {args.out}")
    elif args.mode == "overlay":
        make_debug_overlay(args.pdf, args.out)
        print(f"Overlay -> {args.out}")
    else:
        payload = json.loads(args.data) if args.data else {
            "last_name": "Mustermann",
            "first_name": "Max",
            "birth_date": "01.01.1990",
            "birth_place": "Berlin",
            "citizenship": "deutsch",
            "address": "Teststraße 1, 10115 Berlin",
            "marital": "ledig",
            "iban": "DE89370400440532013000",
            "bic": "GENODEF1S10",
            "bank": "Musterbank",
            "kh": "antragsteller",
            "kg_parts": list("123456789012"),
            "anz_anlagen": "1",
        }
        fill_442(args.pdf, args.out, payload)
        print(f"Gefüllt -> {args.out}")
