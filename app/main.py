# app/main.py
from fastapi import FastAPI, Request, Form, Response
from fastapi.responses import FileResponse, JSONResponse
import os, uuid, json, pathlib, logging
from app.orchestrator import handle_message
from app.providers import send_whatsapp_text

app = FastAPI()
log = logging.getLogger("uvicorn")
ART_DIR = pathlib.Path("/tmp/artifacts"); ART_DIR.mkdir(exist_ok=True)

# ---------- Health ----------
@app.get("/health")
def health():
    return {"ok": True}

# ---------- Meta Webhook (optional, kann bleiben) ----------
@app.get("/webhook")
def verify(hub_mode: str = "", hub_challenge: str = "", hub_verify_token: str = ""):
    if hub_verify_token == os.getenv("WHATSAPP_VERIFY_TOKEN", ""):
        return hub_challenge
    return Response("forbidden", status_code=403)

@app.post("/webhook")
async def webhook(req: Request):
    body = await req.json()
    log.info({"meta_webhook": body})
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []):
                if msg.get("type") != "text":
                    continue
                user = msg.get("from")
                text = msg.get("text", {}).get("body", "")
                reply = handle_message(user=user, text=text, lang=detect_lang(text))
                send_whatsapp_text(user, reply)
    return {"status": "ok"}

# ---------- Twilio WhatsApp Webhook (wichtig) ----------
@app.post("/webhook/twilio")
async def webhook_twilio(From: str = Form(...), Body: str = Form(...)):
    user = (From or "").replace("whatsapp:", "")
    text = Body or ""
    log.info({"twilio_in": {"from": user, "body_
