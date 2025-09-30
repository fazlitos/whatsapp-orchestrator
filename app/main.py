# app/main.py
from fastapi import FastAPI, Request, Form, Response
from fastapi.responses import FileResponse, JSONResponse
import os, uuid, json, pathlib, logging
from app.orchestrator import handle_message
from app.providers import send_whatsapp_text

app = FastAPI()
log = logging.getLogger("uvicorn")

ART_DIR = pathlib.Path("/tmp/artifacts")
ART_DIR.mkdir(exist_ok=True)

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

# ---------- Twilio WhatsApp Webhook ----------
@app.post("/webhook/twilio")
async def webhook_twilio(From: str = Form(...), Body: str = Form(...)):
    user = (From or "").replace("whatsapp:", "")
    text = Body or ""
    log.info({"twilio_in": {"from": user, "body": text}})
    reply = handle_message(user=user, text=text, lang=detect_lang(text))
    send_whatsapp_text(user, reply)
    return "OK"

# optional: trailing slash akzeptieren
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

# ---------- Artefakte & Platzhalter-PDF ----------
@app.post("/make-pdf")
async def make_pdf(payload: dict):
    """
    Erzeugt eine 'PDF'-Datei (derzeit JSON-Platzhalter).
    payload = {"form":"kindergeld","data":{"fields": {...}, "kids":[...]}}
    """
    fid = f"kindergeld-{uuid.uuid4().hex}.pdf"
    path = ART_DIR / fid
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    base = os.getenv("APP_BASE_URL", "").rstrip("/")
    if not base.startswith("http"):
        base = "https://" + base
    return {"id": fid, "url": f"{base}/artifact/{fid}"}

@app.get("/artifact/{fid}")
def get_artifact(fid: str):
    path = ART_DIR / fid
    return FileResponse(path, media_type="application/pdf", filename=fid)
