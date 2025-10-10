# app/pdf/filler.py
"""
KG1 PDF-Formular Filler mit PyMuPDF
"""
from typing import Dict, Any
import fitz  # PyMuPDF

def _split_name(full_name: str) -> tuple:
    parts = str(full_name).strip().split(maxsplit=1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return full_name, ""

def _split_taxid(taxid: str) -> tuple:
    taxid = str(taxid).replace(" ", "").replace("-", "")
    if len(taxid) != 11:
        return "", "", "", ""
    return taxid[0:2], taxid[2:5], taxid[5:8], taxid[8:11]

def _fmt_date(d: str) -> str:
    if not d:
        return ""
    return str(d).replace("-", ".")

def _fmt_iban(iban: str) -> str:
    iban = str(iban).replace(" ", "").upper()
    if len(iban) == 22 and iban.startswith("DE"):
        return " ".join([iban[i:i+4] for i in range(0, len(iban), 4)])
    return iban

def fill_kindergeld(template_path: str, out_path: str, data: Dict[str, Any]) -> None:
    """Füllt KG1 aus - EINFACHE VERSION"""
    print(f"✅ fill_kindergeld aufgerufen!")
    print(f"   Template: {template_path}")
    print(f"   Output: {out_path}")
    
    # Temporär: Kopiere einfach nur das Template
    import shutil
    shutil.copy(template_path, out_path)
    print(f"✅ PDF erstellt (Kopie für Test)")

def make_grid(template_path: str) -> bytes:
    """Grid-Funktion"""
    import io
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 100), "Test Grid", fontsize=12)
    buf = io.BytesIO(doc.tobytes())
    doc.close()
    return buf.getvalue()
