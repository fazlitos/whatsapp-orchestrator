from fastapi import FastAPI, Request, Form, Response
import os, logging
from app.orchestrator import handle_message
from app.providers import send_whatsapp_text  # <-- neu
from fastapi.responses import FileResponse
import pathlib


app = FastAPI()
ART_DIR = os.environ.get("ART_DIR", "/tmp/artifacts")
pathlib.Path(ART_DIR).mkdir(parents=True, exist_ok=True)
log = logging.getLogger("uvicorn")

@app.get("/health")
def health():
    return {"ok": True}

# ----- Meta (kann bleiben, falls du später Meta nutzt) -----
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

# ----- Twilio WhatsApp: genau dieser Endpoint fehlte -----
@app.post("/webhook/twilio")
async def webhook_twilio(From: str = Form(...), Body: str = Form(...)):
    user = (From or "").replace("whatsapp:", "")  # 'whatsapp:+49...' -> '+49...'
    text = Body or ""
    log.info({"twilio_in": {"from": user, "body": text}})
    reply = handle_message(user=user, text=text, lang=detect_lang(text))
    send_whatsapp_text(user, reply)
    return "OK"

# optional: Variante mit trailing slash zulassen
@app.post("/webhook/twilio/")
async def webhook_twilio_trailing(From: str = Form(...), Body: str = Form(...)):
    return await webhook_twilio(From, Body)

def detect_lang(text: str) -> str:
    low = (text or "").lower()
    if any(w in low for w in ["hello", "yes", "no", "child benefit"]): return "en"
    if any(w in low for w in ["përshëndetje","pershendetje","faleminderit","po","jo"]): return "sq"
    return "de"
@app.get("/artifact/{filename}")
def get_artifact(filename: str):
    path = os.path.join(ART_DIR, filename)
    return FileResponse(path, filename=filename, media_type="application/pdf")
