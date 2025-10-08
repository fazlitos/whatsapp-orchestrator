# app/main.py
from fastapi import FastAPI, Request, Form, Response
from fastapi.responses import FileResponse
import os, uuid, json, pathlib, logging

from app.orchestrator import handle_message
from app.providers import send_whatsapp_text
from app.pdf.filler import fill_kindergeld, make_grid

app = FastAPI()
log = logging.getLogger("uvicorn")

ART_DIR = pathlib.Path("/tmp/artifacts")
ART_DIR.mkdir(exist_ok=True)

TEMPLATE_KG1 = "app/pdf/templates/kg1.pdf"  # Pfad zum Formular-Template

@app.get("/health")
def health():
    from app.state_manager import state_manager
    from app.storage import health_check as r2_health_check
    
    redis_health = state_manager.health()
    r2_health = r2_health_check()
    
    return {
        "ok": True,
        "redis": redis_health,
        "r2": r2_health
    }

# ---------- Meta Webhook (optional) ----------
@app.get("/webhook")
def verify(hub_mode: str = "", hub_challenge: str = "", hub_verify_token: str = ""):
    if hub_verify_token == os.getenv("WHATSAPP_VERIFY_TOKEN", ""):
        return hub_challenge
    return Response("forbidden", status_code=403)

@app.post("/webhook")
async def webhook(req: Request):
    try:
        body = await req.json()
        log.info({"meta_webhook": body})
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []) or []:
                    if msg.get("type") != "text":
                        continue
                    user = msg.get("from") or ""
                    text = (msg.get("text") or {}).get("body", "") or ""
                    try:
                        reply = handle_message(user=user, text=text, lang=detect_lang(text))
                    except Exception as e:
                        log.exception(f"handler error (meta): {e}")
                        reply = "Da ist etwas schiefgelaufen. Bitte schreib mir die letzte Nachricht noch einmal."
                    try:
                        send_whatsapp_text(user, reply)
                    except Exception as e:
                        log.error(f"send_whatsapp_text (meta) failed: {e}")
    except Exception as e:
        log.exception(f"meta webhook parse error: {e}")
    return {"status": "ok"}

# ====== PDF Debug Helpers ======
from fastapi.responses import JSONResponse, PlainTextResponse, FileResponse
from pathlib import Path
import os, uuid, logging
from PyPDF2 import PdfReader

log = logging.getLogger("uvicorn")

TEMPLATE_DIR = Path("app/pdf/templates")
TEMPLATE_KG1 = str(TEMPLATE_DIR / "kg1.pdf")

ART_DIR = Path("/tmp/artifacts")
ART_DIR.mkdir(exist_ok=True)

@app.get("/pdf/debug/list")
def pdf_debug_list():
    try:
        if not TEMPLATE_DIR.exists():
            return JSONResponse({"ok": False, "msg": f"Template dir not found: {TEMPLATE_DIR.as_posix()}"}, 404)
        files = []
        for p in TEMPLATE_DIR.iterdir():
            if p.is_file():
                files.append({"name": p.name, "size": p.stat().st_size})
        return {"ok": True, "dir": TEMPLATE_DIR.as_posix(), "files": files}
    except Exception as e:
        log.exception("debug list error")
        return JSONResponse({"ok": False, "error": str(e)}, 500)

@app.get("/pdf/debug/info")
def pdf_debug_info():
    try:
        if not os.path.exists(TEMPLATE_KG1):
            return PlainTextResponse(f"Template not found: {TEMPLATE_KG1}", status_code=404)
        r = PdfReader(TEMPLATE_KG1)
        info = {
            "encrypted": getattr(r, "is_encrypted", False),
            "pages": len(r.pages),
            "sizes": [{"w": float(p.mediabox.width), "h": float(p.mediabox.height)} for p in r.pages],
        }
        return info
    except Exception as e:
        log.exception("debug info error")
        return PlainTextResponse(f"pdf_debug_info error: {e}", status_code=500)

@app.get("/pdf/debug/kg1")
def pdf_debug_grid():
    try:
        if not os.path.exists(TEMPLATE_KG1):
            return PlainTextResponse(f"Template not found: {TEMPLATE_KG1}\nTipp: /pdf/debug/list prüfen.", 404)
        # das Grid erzeugen
        from app.pdf.filler import make_grid
        out_bytes = make_grid(TEMPLATE_KG1)
        tmp = ART_DIR / f"kg1-grid-{uuid.uuid4().hex}.pdf"
        tmp.write_bytes(out_bytes)
        return FileResponse(tmp, media_type="application/pdf", filename=tmp.name)
    except Exception as e:
        log.exception("debug kg1 error")
        return PlainTextResponse(f"pdf_debug_grid error: {e}", status_code=500)


# ---------- Twilio WhatsApp Webhook ----------
@app.post("/webhook/twilio")
async def webhook_twilio(From: str = Form(...), Body: str = Form(...)):
    user = (From or "").replace("whatsapp:", "")
    text = Body or ""
    log.info({"twilio_in": {"from": user, "body": text}})

    try:
        reply = handle_message(user=user, text=text, lang=detect_lang(text))
    except Exception as e:
        log.exception(f"handler error (twilio): {e}")
        reply = "Uups, bei mir ist gerade ein Fehler passiert. Bitte nochmal schicken."

    try:
        send_whatsapp_text(user, reply)
    except Exception as e:
        log.error(f"send_whatsapp_text (twilio) failed: {e}")

    return "OK"

@app.post("/webhook/twilio/")
async def webhook_twilio_trailing(From: str = Form(...), Body: str = Form(...)):
    return await webhook_twilio(From, Body)

# ---------- Session Management (NEU) ----------
@app.get("/sessions/active")
def sessions_active():
    """Zeigt aktive Sessions (für Monitoring)."""
    from app.state_manager import state_manager
    try:
        if state_manager.redis:
            keys = state_manager.redis.keys("session:*")
            return {"total": len(keys), "sessions": [k.replace("session:", "")[-4:] for k in keys[:10]]}
        return {"total": len(state_manager.fallback), "sessions": list(state_manager.fallback.keys())[:10]}
    except Exception as e:
        return {"error": str(e)}

@app.get("/sessions/{user_id}")
def session_info(user_id: str):
    """Zeigt Session-Info (anonymisiert)."""
    from app.state_manager import state_manager
    state = state_manager.get(user_id)
    if not state:
        return {"error": "Session not found"}
    return {
        "user": user_id[-4:],
        "phase": state.get("phase"),
        "form": state.get("form"),
        "fields_count": len(state.get("fields", {})),
        "kids_count": len(state.get("kids", [])),
        "updated": state.get("_updated")
    }

@app.delete("/sessions/{user_id}")
def session_delete(user_id: str):
    """Löscht Session manuell (Support)."""
    from app.state_manager import state_manager
    success = state_manager.delete(user_id)
    return {"deleted": success}

def detect_lang(text: str) -> str:
    low = (text or "").lower()
    if any(w in low for w in ["hello", "yes", "no", "child benefit"]):
        return "en"
    if any(w in low for w in ["përshëndetje", "pershendetje", "faleminderit", "po", "jo"]):
        return "sq"
    return "de"

# ---------- (NEU) Debug: Koordinaten-Netz über KG1 legen ----------
@app.get("/pdf/debug/kg1")
def pdf_debug_grid():
    if not os.path.exists(TEMPLATE_KG1):
        return {"error": f"Template not found: {TEMPLATE_KG1}"}
    out = make_grid(TEMPLATE_KG1)
    tmp = ART_DIR / f"kg1-grid-{uuid.uuid4().hex}.pdf"
    tmp.write_bytes(out)
    return FileResponse(tmp, media_type="application/pdf", filename=tmp.name)

# ---------- (NEU) Echte PDF erzeugen ----------
@app.post("/make-pdf")
async def make_pdf(payload: dict, request: Request):
    """
    payload = {"form":"kindergeld","data":{"fields": {...}, "kids":[...]}}
    """
    base = (os.getenv("APP_BASE_URL", "") or str(request.base_url)).rstrip("/")

    form = (payload.get("form") or "kindergeld").lower()
    data = payload.get("data") or {}

    if form != "kindergeld":
        return {"error": f"form '{form}' not supported yet"}

    if not os.path.exists(TEMPLATE_KG1):
        return {"error": f"Template not found: {TEMPLATE_KG1}"}

    fid = f"kindergeld-{uuid.uuid4().hex}.pdf"
    out_path = ART_DIR / fid

    try:
        fill_kindergeld(TEMPLATE_KG1, str(out_path), data)
    except Exception as e:
        log.exception(f"pdf fill error: {e}")
        return {"error": "pdf_fill_failed"}

    return {"id": fid, "url": f"{base}/artifact/{fid}"}

@app.get("/artifact/{fid}")
def get_artifact(fid: str):
    path = ART_DIR / fid
    return FileResponse(path, media_type="application/pdf", filename=fid)
# ---------- PDF Debug Endpoints ----------
@app.get("/pdf/debug/fields")
def pdf_debug_fields():
    """Zeigt alle Formularfelder im KG1-PDF an."""
    if not os.path.exists(TEMPLATE_KG1):
        return {"error": f"Template not found: {TEMPLATE_KG1}"}
    
    from PyPDF2 import PdfReader
    
    try:
        reader = PdfReader(TEMPLATE_KG1)
        
        if reader.is_encrypted:
            reader.decrypt("")
        
        fields = {}
        
        # Methode 1: get_fields()
        if hasattr(reader, 'get_fields'):
            form_fields = reader.get_fields()
            if form_fields:
                for name, field in form_fields.items():
                    fields[name] = {
                        "type": str(field.get('/FT', 'unknown')),
                        "value": str(field.get('/V', ''))
                    }
                return {"ok": True, "count": len(fields), "fields": fields}
        
        # Methode 2: Annotationen
        for page_num, page in enumerate(reader.pages):
            if '/Annots' in page:
                for annot in page['/Annots']:
                    obj = annot.get_object()
                    if obj.get('/T'):
                        name = obj.get('/T')
                        fields[name] = {
                            "type": str(obj.get('/FT', 'unknown')),
                            "page": page_num,
                            "value": str(obj.get('/V', ''))
                        }
        
        if not fields:
            return {"ok": False, "message": "Keine Formularfelder gefunden"}
        
        return {"ok": True, "count": len(fields), "fields": fields}
        
    except Exception as e:
        log.exception("fields debug error")
        return {"ok": False, "error": str(e)}
