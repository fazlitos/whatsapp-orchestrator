# app/providers.py
import os, httpx, time
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from twilio.http.http_client import TwilioHttpClient

def _twilio_client():
    acc = os.getenv("TWILIO_ACCOUNT_SID")
    tok = os.getenv("TWILIO_AUTH_TOKEN")
    timeout = int(os.getenv("TWILIO_HTTP_TIMEOUT", "30"))  # sek
    http_client = TwilioHttpClient(timeout=timeout)
    return Client(acc, tok, http_client=http_client)

def send_twilio(to: str, text: str):
    acc, tok, from_ = os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"), os.getenv("TWILIO_FROM")
    if not (acc and tok and from_):
        print("WARN: Twilio ENV fehlt – keine Nachricht gesendet.")
        return
    try:
        _twilio_client().messages.create(
            from_=f"whatsapp:{from_}",
            to=f"whatsapp:{to}",
            body=text[:1600]
        )
    except TwilioRestException as e:
        print("Twilio text send error:", e)
        raise
    except Exception as e:
        print("Twilio text send exception:", e)
        raise

def send_twilio_document(to: str, media_url: str, caption: str = ""):
    acc, tok, from_ = os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"), os.getenv("TWILIO_FROM")
    if not (acc and tok and from_):
        print("WARN: Twilio ENV fehlt – kein Dokumentversand.")
        return
    try:
        _twilio_client().messages.create(
            from_=f"whatsapp:{from_}",
            to=f"whatsapp:{to}",
            body=caption[:1024] if caption else None,
            media_url=[media_url]
        )
    except TwilioRestException as e:
        print("Twilio doc send error:", e)
        raise
    except Exception as e:
        print("Twilio doc send exception:", e)
        raise

def send_meta(to: str, text: str):
    token, phone_id = os.getenv("WHATSAPP_TOKEN", ""), os.getenv("WHATSAPP_PHONE_ID", "")
    if not (token and phone_id):
        print("WARN: Meta ENV fehlt – keine Nachrich
