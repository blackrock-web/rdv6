"""
ROADAI Twilio SMS Service — SMS ONLY (no WhatsApp)
===================================================
Uses standard Twilio SMS API only.
Env vars required:
  TWILIO_ACCOUNT_SID
  TWILIO_AUTH_TOKEN
  TWILIO_PHONE_NUMBER   (your Twilio number, e.g. +15551234567)
  ALERT_TARGET_PHONE    (recipient number, e.g. +15559876543)
"""
import os
from backend.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_ALERT_MSG = (
    "Road defect alert: severe pothole/crack detected. "
    "Please inspect the flagged section. [ROADAI System]"
)


def _get_config():
    return {
        "account_sid":    os.environ.get("TWILIO_ACCOUNT_SID", "").strip(),
        "auth_token":     os.environ.get("TWILIO_AUTH_TOKEN", "").strip(),
        "from_number":    os.environ.get("TWILIO_PHONE_NUMBER", "").strip(),
        "to_number":      os.environ.get("ALERT_TARGET_PHONE", "").strip(),
    }


def check_twilio_config() -> dict:
    """Validate Twilio env vars. Returns status dict."""
    cfg = _get_config()
    missing = [k for k, v in cfg.items() if not v]
    if missing:
        return {
            "configured": False,
            "missing_vars": missing,
            "message": f"Missing Twilio env vars: {', '.join(missing)}",
        }
    return {"configured": True, "missing_vars": [], "message": "Twilio SMS configured"}


def send_sms(message: str = None, to_number: str = None) -> dict:
    """
    Send an SMS via Twilio.
    Falls back to DEFAULT_ALERT_MSG if message is empty.
    Returns {"success": bool, "sid": str, "error": str}
    """
    cfg = _get_config()

    check = check_twilio_config()
    if not check["configured"]:
        logger.warning(f"SMS not sent — {check['message']}")
        return {"success": False, "error": check["message"], "sid": None}

    body = (message or "").strip() or DEFAULT_ALERT_MSG
    recipient = (to_number or cfg["to_number"]).strip()

    if not recipient:
        return {"success": False, "error": "No recipient phone number configured (ALERT_TARGET_PHONE)", "sid": None}

    try:
        from twilio.rest import Client  # type: ignore
        client = Client(cfg["account_sid"], cfg["auth_token"])
        msg = client.messages.create(
            body=body,
            from_=cfg["from_number"],
            to=recipient,
        )
        logger.info(f"SMS sent to {recipient} — SID: {msg.sid}")
        return {"success": True, "sid": msg.sid, "error": None}
    except ImportError:
        err = "twilio package not installed. Run: pip install twilio"
        logger.error(err)
        return {"success": False, "error": err, "sid": None}
    except Exception as e:
        logger.error(f"SMS send failed: {e}")
        return {"success": False, "error": str(e), "sid": None}


def send_sms_alert(message: str, override_phone: str = None) -> bool:
    """
    Enterprise-ready wrapper for auth.py OTP logic.
    Accepts 'override_phone' and returns a simple boolean status.
    """
    res = send_sms(message=message, to_number=override_phone)
    return res.get("success", False)
