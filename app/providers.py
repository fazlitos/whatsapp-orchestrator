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
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    return Client(sid, token, http_client=http_client)

def _with_retries(fn, max_retries=3, base_delay=1.5):
    last = None
    for attempt in range(1, max_retries + 1):
        try:
            return fn()
        except Exception as e:
            last = e
            sleep(base_delay * attempt)  # simple backoff
    if last:
        raise last

# -------------------- Meta helper (optional Fallback) --------------------
def _meta_send(payload):
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
def send_twilio(to, text):
    """Text über Twilio-WhatsApp senden (mit Timeout & Retries)."""
    acc = os.getenv("TWILIO_ACCOUNT_SID")
    tok = os.getenv("TWILIO_AUTH_TOKEN")
    from_ = os.getenv("TWILIO_FROM")
    if not (acc and tok and from_):
        print("WARN: Twilio ENV fehlt - keine Nachricht gesendet.")
        return

    def _call():
        return _twilio_client().messages.create(
            from_=f"whatsapp:{from_}",
            to=f"whatsapp:{to}",
            body=str(text)[:1600]
        )

    try:
        _with_retries(_call)
    except TwilioRestException as e:
        print("Twilio text send error:", e)
        # Optionaler Fallback zu Meta bei 429 (Daily Limit), wenn erlaubt
        if e.status == 429 and os.getenv("ALLOW_FAILOVER_TO_META", "").lower() == "true":
            _meta_send({
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": str(text)[:4096]}
            })
        # NICHT raisen: Webhook soll nie 500 werden
        return
    except Exception as e:
        print("Twilio text send exception:", e)
        return

def send_twilio_document(to, media_url, caption=""):
    """Dokument (PDF-URL) über Twilio-WhatsApp senden (mit Timeout & Retries)."""
    acc = os.getenv("TWILIO_ACCOUNT_SID")
    tok = os.getenv("TWILIO_AUTH_TOKEN")
    from_ = os.getenv("TWILIO_FROM")
    if not (acc and tok and from_):
        print("WARN: Twilio ENV fehlt - kein Dokumentversand.")
        return

    def _call():
        return _twilio_client().messages.create(
            from_=f"whatsapp:{from_}",
            to=f"whatsapp:{to}",
            body=(caption or "")[:1024] or None,
            media_url=[media_url]
        )

    try:
        _with_retries(_call)
    except TwilioRestException as e:
        print("Twilio doc send error:", e)
        if e.status == 429 and os.getenv("ALLOW_FAILOVER_TO_META", "").lower() == "true":
            _meta_send({
                "messaging_product": "whatsapp",
                "to": to,
                "type": "document",
                "document": {"link": media_url, "caption": caption or ""}
            })
        return
    except Exception as e:
        print("Twilio doc send exception:", e)
        return

def send_meta(to, text):
    """Fallback: Meta Cloud API (nur genutzt, wenn PROVIDER != twilio)."""
    _meta_send({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": str(text)[:4096]}
    })

def send_whatsapp_text(to, text):
    """Router: nutzt Twilio oder Meta je nach PROVIDER."""
    provider = (os.getenv("PROVIDER", "meta") or "meta").lower()
    if provider == "twilio":
        return send_twilio(to, text)
    return send_meta(to, text)
