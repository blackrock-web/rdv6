import os
from twilio.rest import Client
from backend.utils.logger import get_logger

logger = get_logger(__name__)

class AlertEngine:
    """
    Enterprise Alerting Engine.
    Routes critical maintenance alerts via Twilio (SMS/Voice).
    Synchronized with Admin Control panel settings.
    """
    def __init__(self):
        self._refresh_config()

    def _refresh_config(self):
        """Reload configuration from environment (which may be updated by Admin API)."""
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token  = os.getenv("TWILIO_AUTH_TOKEN")
        self.from_phone  = os.getenv("TWILIO_PHONE_NUMBER")
        self.target_phone = os.getenv("ALERT_TARGET_PHONE")
        self.client      = None
        
        if self.account_sid and self.auth_token:
            try:
                # Basic validation
                if len(self.account_sid) > 10 and len(self.auth_token) > 10:
                    self.client = Client(self.account_sid, self.auth_token)
                    logger.info("✅ Twilio Alert Engine initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Twilio client: {e}")

    def send_sms_alert(self, message: str, to_phone: str = None):
        """Send a critical infrastructure alert via SMS."""
        self._refresh_config() # Ensure we have latest admin settings
        
        target = to_phone or self.target_phone
        if not self.client or not target or not self.from_phone:
            logger.warning(f"Twilio not fully configured. Alert suppressed: {message}")
            return False
            
        try:
            msg = self.client.messages.create(
                body=f"🚨 ROADAI CRITICAL ALERT: {message}",
                from_=self.from_phone,
                to=target
            )
            logger.info(f"📲 SMS Alert sent to {target}: {msg.sid}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to send SMS alert: {e}")
            return False

    def check_and_alert(self, defect_type: str, health_score: float, segment_id: str):
        """Logic for automated critical alert escalation based on severity thresholds."""
        # Thresholds for enterprise-grade safety
        if health_score < 30 or defect_type.lower() == "critical_pothole":
            msg = (
                f"CRITICAL FAULT: {defect_type.upper()} "
                f"at Segment {segment_id}. Health: {health_score:.1f}%. "
                f"Immediate dispatch required."
            )
            logger.warning(f"⚠️ Escalating critical alert: {msg}")
            return self.send_sms_alert(msg)
        return False
