import os
import logging
import requests

logger = logging.getLogger(__name__)


# TWILIO CONFIGURATION

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_VERIFY_SERVICE_SID = os.environ.get("TWILIO_VERIFY_SERVICE_SID")
TWILIO_DEFAULT_COUNTRY_CODE = os.environ.get("TWILIO_DEFAULT_COUNTRY_CODE", "+977")


# PROVIDER DETECTION

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
    """Return which SMS provider is active: 'twilio' or 'simulation'."""
    if _is_twilio_configured():
        return "twilio"
    return "simulation"


# PHONE FORMATTING

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


# SEND OTP

def send_otp(phone_number):
    """
    Send an OTP to the given phone number using the first configured provider.
    Priority: Twilio → Simulation

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

    # Twilio
    if provider == "twilio":
        from twilio.rest import Client
        from twilio.base.exceptions import TwilioRestException
        formatted = format_phone_e164(phone_number)
        try:
            client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            client.verify.v2.services(
                TWILIO_VERIFY_SERVICE_SID
            ).verifications.create(to=formatted, channel="sms")
            return {
                "status": "success",
                "message": "OTP sent via Twilio Verify SMS.",
            }
        except TwilioRestException as e:
            raise ValueError(f"Twilio error: {e.msg}")

    # Simulation
    logger.warning(f"No SMS provider configured — simulating OTP for {phone_number}")
    return {
        "status": "simulated",
        "code": "123456",
        "message": "No SMS provider configured. Use simulated code 123456.",
    }


# VERIFY OTP

def verify_otp(phone_number, code):
    """
    Verify the OTP submitted by the user.
    Returns True if verified, False otherwise.
    """
    provider = active_provider()
    logger.info(f"verify_otp: using provider '{provider}' for {phone_number}")

    # Twilio
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

    # Simulation
    return code == "123456"
