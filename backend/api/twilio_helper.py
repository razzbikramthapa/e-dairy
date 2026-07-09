import os
import logging
import requests
import datetime
from django.utils import timezone

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# NEPALOTP CONFIGURATION  (primary provider)
# ─────────────────────────────────────────────────────────────────────────────
NEPALOTP_API_KEY = os.environ.get("NEPALOTP_API_KEY")           # notp_sandbox_... or notp_live_...
NEPALOTP_BASE_URL = "https://api.nepalotp.com/v1"

# ─────────────────────────────────────────────────────────────────────────────
# TWILIO CONFIGURATION  (fallback provider)
# ─────────────────────────────────────────────────────────────────────────────
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_VERIFY_SERVICE_SID = os.environ.get("TWILIO_VERIFY_SERVICE_SID")
TWILIO_DEFAULT_COUNTRY_CODE = os.environ.get("TWILIO_DEFAULT_COUNTRY_CODE", "+977")


# ─────────────────────────────────────────────────────────────────────────────
# PROVIDER DETECTION
# ─────────────────────────────────────────────────────────────────────────────
def _is_nepalotp_configured():
    """Returns True when a real NepalOTP API key is present (sandbox or live)."""
    return bool(
        NEPALOTP_API_KEY and
        ("notp_sandbox_" in NEPALOTP_API_KEY or "notp_live_" in NEPALOTP_API_KEY)
    )

def _is_twilio_configured():
    """Returns True when real Twilio credentials are present."""
    return bool(
        TWILIO_ACCOUNT_SID and
        TWILIO_AUTH_TOKEN and
        TWILIO_VERIFY_SERVICE_SID and
        "your-" not in TWILIO_ACCOUNT_SID and
        "your-" not in TWILIO_AUTH_TOKEN and
        "your-" not in TWILIO_VERIFY_SERVICE_SID
    )

def is_twilio_configured():
    """Public alias kept for backward-compatibility with existing views."""
    return _is_twilio_configured()

def active_provider():
    """Return which SMS provider is active: 'nepalotp', 'twilio', or 'simulation'."""
    if _is_nepalotp_configured():
        return "nepalotp"
    if _is_twilio_configured():
        return "twilio"
    return "simulation"


# ─────────────────────────────────────────────────────────────────────────────
# PHONE FORMATTING
# ─────────────────────────────────────────────────────────────────────────────
def format_phone_e164(phone):
    """
    Convert a local Nepal number to E.164 for Twilio (e.g. +9779841234567).
    """
    phone = phone.strip()
    if phone.startswith("+"):
        return phone
    if phone.startswith("0") and len(phone) > 1:
        phone = phone[1:]
    return f"{TWILIO_DEFAULT_COUNTRY_CODE}{phone}"


def format_phone_nepalotp(phone):
    """
    NepalOTP expects a plain 10-digit Nepali number (no +977 prefix).
    """
    phone = phone.strip()
    # Remove +977 prefix if present
    if phone.startswith("+977"):
        phone = phone[4:]
    # Remove leading 0
    if phone.startswith("0") and len(phone) > 1:
        phone = phone[1:]
    return phone


# ─────────────────────────────────────────────────────────────────────────────
# OTP_ID CACHE  (needed for NepalOTP's two-step send → verify flow)
# Django's cache is used so the otp_id persists between the two API calls.
# ─────────────────────────────────────────────────────────────────────────────
def _cache_set(key, value, timeout=360):
    """Store a value in Django's cache (6-minute TTL by default)."""
    try:
        from django.core.cache import cache
        cache.set(key, value, timeout)
    except Exception as e:
        logger.warning(f"Cache set failed: {e}")

def _cache_get(key):
    """Retrieve a value from Django's cache."""
    try:
        from django.core.cache import cache
        return cache.get(key)
    except Exception:
        return None

def _otp_cache_key(phone):
    return f"nepalotp_otp_id_{phone}"


# ─────────────────────────────────────────────────────────────────────────────
# SEND OTP
# ─────────────────────────────────────────────────────────────────────────────
def send_otp(phone_number):
    """
    Send an OTP to the given phone number using the first configured provider.
    Priority: NepalOTP → Twilio → Simulation

    Returns a dict:
        {
            "status": "success" | "simulated",
            "message": "...",
            "code": "123456"   # only present in simulated mode
        }
    Raises ValueError on API errors.
    """
    provider = active_provider()
    logger.info(f"send_otp: using provider '{provider}' for {phone_number}")

    # ── NepalOTP ──────────────────────────────────────────────────────────────
    if provider == "nepalotp":
        formatted = format_phone_nepalotp(phone_number)
        try:
            resp = requests.post(
                f"{NEPALOTP_BASE_URL}/otp/send",
                json={"phone": formatted, "reference": f"edairy_{formatted}"},
                headers={
                    "Authorization": f"Bearer {NEPALOTP_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=10,
            )
            body = resp.json()
            if not body.get("success"):
                err = body.get("error", {})
                raise ValueError(f"NepalOTP error: {err.get('code')} – {err.get('message')}")

            otp_id = body["data"]["otp_id"]
            # Cache otp_id keyed by phone so we can use it in verify_otp()
            _cache_set(_otp_cache_key(formatted), otp_id)

            is_sandbox = "notp_sandbox_" in NEPALOTP_API_KEY
            result = {
                "status": "success",
                "message": "OTP sent via NepalOTP SMS.",
            }
            if is_sandbox:
                result["code"] = "123456"   # sandbox always returns this fixed code
            return result

        except requests.RequestException as e:
            raise ValueError(f"NepalOTP network error: {e}")

    # ── Twilio ────────────────────────────────────────────────────────────────
    if provider == "twilio":
        from twilio.rest import Client
        from twilio.base.exceptions import TwilioRestException
        formatted = format_phone_e164(phone_number)
        try:
            client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            verification = client.verify.v2.services(
                TWILIO_VERIFY_SERVICE_SID
            ).verifications.create(to=formatted, channel="sms")
            return {
                "status": "success",
                "message": "OTP sent via Twilio Verify SMS.",
            }
        except TwilioRestException as e:
            raise ValueError(f"Twilio error: {e.msg}")

    # ── Simulation ────────────────────────────────────────────────────────────
    logger.warning(f"No SMS provider configured — simulating OTP for {phone_number}")
    return {
        "status": "simulated",
        "code": "123456",
        "message": "No SMS provider configured. Use simulated code 123456.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# VERIFY OTP
# ─────────────────────────────────────────────────────────────────────────────
def verify_otp(phone_number, code):
    """
    Verify the OTP submitted by the user.
    Returns True if verified, False otherwise.
    """
    provider = active_provider()
    logger.info(f"verify_otp: using provider '{provider}' for {phone_number}")

    # ── NepalOTP ──────────────────────────────────────────────────────────────
    if provider == "nepalotp":
        formatted = format_phone_nepalotp(phone_number)
        otp_id = _cache_get(_otp_cache_key(formatted))

        if not otp_id:
            logger.warning(f"No otp_id cached for {formatted} — OTP may have expired or was never sent")
            # Sandbox fallback: allow 123456
            if "notp_sandbox_" in (NEPALOTP_API_KEY or ""):
                return code == "123456"
            return False

        try:
            resp = requests.post(
                f"{NEPALOTP_BASE_URL}/otp/verify",
                json={"otp_id": otp_id, "code": code},
                headers={
                    "Authorization": f"Bearer {NEPALOTP_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=10,
            )
            body = resp.json()
            verified = body.get("success") and body.get("data", {}).get("verified", False)
            if verified:
                # Clear cached otp_id after successful verification
                _cache_set(_otp_cache_key(formatted), None, timeout=1)
            return verified

        except requests.RequestException as e:
            logger.error(f"NepalOTP verify network error: {e}")
            return False

    # ── Twilio ────────────────────────────────────────────────────────────────
    if provider == "twilio":
        from twilio.rest import Client
        from twilio.base.exceptions import TwilioRestException
        formatted = format_phone_e164(phone_number)
        try:
            client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            check = client.verify.v2.services(
                TWILIO_VERIFY_SERVICE_SID
            ).verification_checks.create(to=formatted, code=code)
            return check.status == "approved"
        except TwilioRestException as e:
            logger.error(f"Twilio verify error: {e}")
            return False

    # ── Simulation ────────────────────────────────────────────────────────────
    return code == "123456"


# ─────────────────────────────────────────────────────────────────────────────
# SPARROW SMS SERVICE & SANDBOX (for demo notifications)
# ─────────────────────────────────────────────────────────────────────────────
SPARROW_SMS_TOKEN = os.environ.get("SPARROW_SMS_TOKEN")
SPARROW_SMS_SENDER = os.environ.get("SPARROW_SMS_SENDER", "Demo")

def send_sparrow_sms(phone, text):
    """
    Sends an SMS using Sparrow SMS API (Simulated sandbox if no token is configured).
    Also writes logs to a local file backend/sms_logs.txt for easy testing/verification.
    """
    phone = phone.strip()
    if phone.startswith("+977"):
        phone = phone[4:]
    if phone.startswith("0") and len(phone) > 1:
        phone = phone[1:]
        
    sms_log_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sms_logs.txt")
    log_entry = f"[{timezone.now()}] To: +977 {phone} | Msg: {text}\n"
    
    # Write to local test log file
    try:
        with open(sms_log_path, "a") as f:
            f.write(log_entry)
    except Exception as e:
        logger.error(f"Failed to write to local sms_logs.txt: {e}")
        
    if not SPARROW_SMS_TOKEN or "your-" in SPARROW_SMS_TOKEN:
        logger.info(f"[SMS SANDBOX] Sending Sparrow SMS to {phone}: {text}")
        return {
            "status": "simulated",
            "message": f"Simulated SMS written to sms_logs.txt.",
            "text": text
        }
        
    try:
        url = "http://api.sparrowspay.com/v2/sms/"
        params = {
            "token": SPARROW_SMS_TOKEN,
            "from": SPARROW_SMS_SENDER,
            "to": phone,
            "text": text
        }
        resp = requests.get(url, params=params, timeout=10)
        body = resp.json()
        logger.info(f"Sparrow SMS response: {body}")
        return {
            "status": "success",
            "message": "SMS sent successfully via Sparrow SMS.",
            "response": body
        }
    except Exception as e:
        logger.error(f"Sparrow SMS API failure: {e}")
        return {
            "status": "failed",
            "message": f"SMS failed to send: {str(e)}. Sandbox fallback logged.",
            "text": text
        }
