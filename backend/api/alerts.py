"""ROADAI Alerts API v4."""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from backend.core.twilio_sms_service import send_sms, check_twilio_config
from backend.services.alert_service import create_and_send_alert, get_alert_history, get_alert_stats
router = APIRouter()

class AlertTrigger(BaseModel):
    model_config = {"protected_namespaces": ()}
    severity: str; health_score: float; pothole_count: int=0; crack_count: int=0
    rul_estimate_years: float=10.0; model_used: str="unknown"; location_label: str=""
    custom_message: Optional[str]=None; auto_send: bool=True
    coordinates: Optional[dict]=None; preprocessing_mode: str="auto"; alert_threshold: str="high"

@router.get("/sms/config")
async def sms_config():
    return check_twilio_config()

@router.post("/sms/test")
async def test_sms():
    """Send a test SMS to verify Twilio is configured and working."""
    cfg = check_twilio_config()
    if not cfg["configured"]:
        return {"success": False, "error": cfg["message"]}
    result = send_sms("🧪 ROADAI Test Alert — Twilio SMS is configured and working correctly!")
    return result

@router.post("/sms/trigger")
async def trigger_alert(req: AlertTrigger):
    rec = create_and_send_alert(severity=req.severity,pothole_count=req.pothole_count,
        crack_count=req.crack_count,road_health_score=req.health_score,
        rul_estimate_years=req.rul_estimate_years,model_used=req.model_used,
        location_label=req.location_label,custom_message=req.custom_message,
        auto_send=req.auto_send,coordinates=req.coordinates,
        preprocessing_mode=req.preprocessing_mode,alert_threshold=req.alert_threshold,
        event_type="manual" if req.custom_message else "auto")
    return {"alert_id":rec.id,"sms_status":rec.sms_status,"message":rec.message,"error":rec.sms_error}

@router.get("/history")
async def history(limit: int=50, status: Optional[str]=None):
    return {"alerts": get_alert_history(limit=limit, status_filter=status)}

@router.get("/stats")
async def stats():
    return get_alert_stats()
