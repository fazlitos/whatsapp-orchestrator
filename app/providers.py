# app/providers.py
import os
import httpx
from time import sleep
from twilio.http.http_client import TwilioHttpClient
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

# -------------------- Twilio helpers --------------------
def _twilio_client():
    timeout = int(os.getenv("TWILIO_HTTP_TIMEOUT", "60"))  # seconds
    http_client = TwilioHttpClient(timeout=timeout)
    return Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"), http_client=http_client)

def _with_retries(callable_fn, max_retries=3, base_delay=1.5):
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            return callable_fn()
        except Exception as e:
            last_err = e
            sleep(base_delay * attempt)  # simple backoff
    raise last_err

# -------------------- Meta helper (optional Fallback) --------------------
def _meta_send(payload: dict):
    token = os.getenv("WHATSAPP_TOKEN", "")
    phone_id = os.getenv("WHATSAPP_PHONE_ID", "")
    if not (token and phone_id):
        print("WARN: Meta ENV fehlt - Meta-Send uebersprungen.")
        return
    url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=15) as c:
        r = c.post(url, headers=headers, json=payload)
        try:
            r.raise_for_status()
        except Exception as e:
            print("Meta send error:", e, r.text)

# -------------------- Public API --------------------
def send_twilio(to: str, text: str):
    """Text über Twilio-WhatsApp senden (mit Timeout & Retries)."""
    acc, tok, from_ = os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"), os.getenv("TWILIO_FROM")
    if not (acc and tok and from_):
        print("WARN: Twilio ENV fehlt - keine Nachricht gesendet.")
        return
    try:
        _with_retries(lambda: _twilio_client().messages.create(
            from_=f"whatsapp:{from_}",
            to=f"whatsapp:{to}",
            body=text[:1600]
        ))
    except TwilioRestException as e:
        print("Twilio text send error:", e)
        # Optionaler Fallback zu Meta bei 429 (Daily limit) – nur wenn EXPLIZIT erlaubt
        if e.status == 429 and os.getenv("ALLOW_FAILOVER_TO_META", "").lower() == "true":
            _meta_send({"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text[:4096]}})
        else:
            raise
    except Exception as e:
        print("Twilio text send exception:", e)
        raise

def send_twilio_document(to: str, media_url: str, caption: str = ""):
    """Dokument (PDF-URL) über Twilio-WhatsApp senden (mit Timeout & Retries)."""
    acc, tok, from_ = os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"), os.getenv("TWILIO_FROM")
    if not (acc and tok and from_):
        print("WARN: Twilio ENV fehlt - kein Dokumentversand.")
        return
    try:
        _with_retries(lambda: _twilio_client().messages.create(
            from_=f"whatsapp:{from_}",
            to=f"whatsapp:{to}",
            body=caption[:1024] if caption else None,
            media_url=[media_url]
        ))
    except TwilioRestException as e:
        print("Twilio doc send error:", e)
        if e.status == 429 and os.getenv("ALLOW_FAILOVER_TO_META", "").lower() == "true":
            _meta_send({
                "messaging_product": "whatsapp",
                "to": to,
                "type": "document",
                "document": {"link": media_url, "caption": caption or ""}
            })
        else:
            raise
    except Exception as e:
        print("Twilio doc send exception:", e)
        raise

def send_meta(to:_
