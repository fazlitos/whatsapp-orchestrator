# app/providers.py
import os, httpx
from twilio.rest import Client

def send_twilio(to: str, text: str):
    acc = os.getenv("TWILIO_ACCOUNT_SID")
    tok = os.getenv("TWILIO_AUTH_TOKEN")
    from_ = os.getenv("TWILIO_FROM")
    if not (acc and tok and from_):
        print("WARN: Twilio ENV fehlt – keine Nachricht gesendet.")
        return
    cli = Client(acc, tok)
    cli.messages.create(
        from_=f"whatsapp:{from_}",
        to=f"whatsapp:{to}",
        body=text[:1600]
    )

def send_meta(to: str, text: str):
    token = os.getenv("WHATSAPP_TOKEN", "")
    phone_id = os.getenv("WHATSAPP_PHONE_ID", "")
    if not (token and phone_id):
        print("WARN: Meta ENV fehlt – keine Nachricht gesendet.")
        return
    url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}"}
    data = {"messaging_product":"whatsapp","to":to,"type":"text","text":{"body":text[:4096]}}
    with httpx.Client(timeout=10) as c:
        r = c.post(url, headers=headers, json=data)
        try: r.raise_for_status()
        except Exception as e: print("Meta send error:", e, r.text)

def send_whatsapp_text(to: str, text: str):
    provider = (os.getenv("PROVIDER","meta") or "meta").lower()
    if provider == "twilio":
        return send_twilio(to, text)
    return send_meta(to, text)
