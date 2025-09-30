from fastapi import FastAPI, Request
import os
from app.orchestrator import handle_message

app = FastAPI()

@app.get("/health")
def health():
    return {"ok": True}

# WhatsApp Cloud API Webhook Verification
@app.get("/webhook")
def verify(hub_mode: str = "", hub_challenge: str = "", hub_verify_token: str = ""):
    if hub_verify_token == os.getenv("WHATSAPP_VERIFY_TOKEN", ""):
        # Meta erwartet den hub.challenge-String unverändert zurück
        return hub_challenge
    return "forbidden"

@app.post("/webhook")
async def webhook(req: Request):
    body = await req.json()
    # Erwartete Struktur: entry -> changes -> value -> messages[]
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            messages = value.get("messages", [])
            for msg in messages:
                if msg.get("type") != "text":
                    continue
                from_ = msg.get("from")
                text = msg.get("text", {}).get("body", "")
                lang = detect_lang(text)
                reply = handle_message(user=from_, text=text, lang=lang)
                send_whatsapp_text(to=from_, text=reply)
    return {"status": "ok"}

def detect_lang(text: str) -> str:
    low = (text or "").lower()
    if any(w in low for w in ["hello", "yes", "no", "child benefit"]):
        return "en"
    if any(w in low for w in ["përshëndetje", "pershendetje", "faleminderit", "po", "jo"]):
        return "sq"
    return "de"

import httpx
def send_whatsapp_text(to: str, text: str):
    token = os.getenv("WHATSAPP_TOKEN", "")
    phone_id = os.getenv("WHATSAPP_PHONE_ID", "")
    if not token or not phone_id:
        print("WARN: WHATSAPP_TOKEN/WHATSAPP_PHONE_ID fehlen – Nachricht nicht gesendet.")
        return
    url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}"}
    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text[:4096]}
    }
    with httpx.Client(timeout=10) as client:
        r = client.post(url, headers=headers, json=data)
        try:
            r.raise_for_status()
        except Exception as e:
            print("WhatsApp send error:", e, r.text)
