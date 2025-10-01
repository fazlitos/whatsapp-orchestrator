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

# ---------- Health ----------
@app.get("/health")
def health():
    return {"ok": True}

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
