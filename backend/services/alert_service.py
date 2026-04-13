"""
ROADAI Alert Service — enriched alert logging with SMS history.
Persists to config/alert_history.json
"""
import json
import uuid
import time
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass, asdict, field

from backend.core.twilio_sms_service import send_sms, check_twilio_config
from backend.utils.logger import get_logger

logger = get_logger(__name__)

ALERT_HISTORY_PATH = Path("config/alert_history.json")


@dataclass
class AlertRecord:
    id: str
    timestamp: float
    event_type: str           # auto | manual | test
    severity: str
    pothole_count: int
    crack_count: int
    road_health_score: float
    rul_estimate_years: float
    location_label: str
    model_used: str
    message: str
    sms_status: str           # sent | failed | skipped | pending
    sms_sid: Optional[str]
    sms_error: Optional[str]
    auto_generated: bool
    coordinates: Optional[dict] = None  # {"lat": ..., "lon": ...}
    preprocessing_mode: str = "auto"
    alert_threshold_used: str = "high"


def _load_history() -> List[dict]:
    try:
        if ALERT_HISTORY_PATH.exists():
            return json.loads(ALERT_HISTORY_PATH.read_text())
    except Exception:
        pass
    return []


def _save_history(records: List[dict]):
    ALERT_HISTORY_PATH.parent.mkdir(exist_ok=True)
    ALERT_HISTORY_PATH.write_text(json.dumps(records, indent=2))


def create_and_send_alert(
    severity: str,
    pothole_count: int,
    crack_count: int,
    road_health_score: float,
    rul_estimate_years: float,
    model_used: str,
    location_label: str = "Unknown Location",
    custom_message: Optional[str] = None,
    auto_send: bool = True,
    coordinates: Optional[dict] = None,
    preprocessing_mode: str = "auto",
    alert_threshold: str = "high",
    event_type: str = "auto",
) -> AlertRecord:
    """Create an alert record and optionally send SMS."""
    sev_order = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
    threshold_val = sev_order.get(alert_threshold, 3)
    sev_val       = sev_order.get(severity, 0)
    should_send   = sev_val >= threshold_val and auto_send

    if custom_message:
        message = custom_message.strip()
    else:
        # ── Upgraded SMS Report Content (Report Style) ──
        h = int(road_health_score)
        risk = severity.upper()
        
        # Risk assessment based on both health and RUL
        if h < 35 or rul_estimate_years < 1:
            rec = "IMMEDIATE INTERVENTION REQUIRED"
        elif h < 60 or rul_estimate_years < 3:
            rec = "SCHEDULE REPAIR WITHIN 30 DAYS"
        else:
            rec = "ROUTINE MAINTENANCE RECOMMENDED"

        loc = f" @ {location_label}" if location_label != "Unknown Location" else ""
        coord = f" [{coordinates['lat']:.5f},{coordinates['lon']:.5f}]" if coordinates else ""
        
        message = (
            f"ROADAI HEALTH REPORT{loc}\n"
            f"Status: {risk} RISK\n"
            f"Health: {h}/100 | RUL: {rul_estimate_years:.1f} yrs\n"
            f"Defects: {pothole_count} Potholes, {crack_count} Cracks\n"
            f"Recommend: {rec}{coord}"
        )

    sms_status = "skipped"
    sms_sid    = None
    sms_error  = None

    if should_send:
        # Check if Twilio SID/Token are set before trying to send
        config = check_twilio_config()
        if not config["configured"]:
            sms_status = "failed"
            sms_error  = "Twilio credentials missing in ENV"
        else:
            result = send_sms(message=message)
            if result["success"]:
                sms_status = "sent"
                sms_sid    = result.get("sid")
            else:
                sms_status = "failed"
                sms_error  = result.get("error")
    elif not auto_send:
        sms_status = "skipped"
        sms_error  = "auto_send disabled"
    else:
        sms_status = "skipped"
        sms_error  = f"severity '{severity}' below threshold '{alert_threshold}'"

    record = AlertRecord(
        id=str(uuid.uuid4())[:8],
        timestamp=time.time(),
        event_type=event_type,
        severity=severity,
        pothole_count=pothole_count,
        crack_count=crack_count,
        road_health_score=road_health_score,
        rul_estimate_years=rul_estimate_years,
        location_label=location_label,
        model_used=model_used,
        message=message,
        sms_status=sms_status,
        sms_sid=sms_sid,
        sms_error=sms_error,
        auto_generated=(event_type == "auto"),
        coordinates=coordinates,
        preprocessing_mode=preprocessing_mode,
        alert_threshold_used=alert_threshold,
    )

    history = _load_history()
    history.append(asdict(record))
    _save_history(history)

    logger.info(f"Alert {record.id}: severity={severity} sms={sms_status}")
    return record


def get_alert_history(limit: int = 100, status_filter: Optional[str] = None) -> List[dict]:
    records = _load_history()
    if status_filter:
        records = [r for r in records if r.get("sms_status") == status_filter]
    return sorted(records, key=lambda r: r.get("timestamp", 0), reverse=True)[:limit]


def resend_alert(alert_id: str) -> dict:
    """Retry sending SMS for a failed alert."""
    records = _load_history()
    for i, r in enumerate(records):
        if r.get("id") == alert_id:
            result = send_sms(message=r["message"])
            records[i]["sms_status"] = "sent" if result["success"] else "failed"
            records[i]["sms_sid"]    = result.get("sid")
            records[i]["sms_error"]  = result.get("error")
            _save_history(records)
            return {"success": result["success"], "alert_id": alert_id, **result}
    return {"success": False, "error": "Alert not found"}


def get_alert_stats() -> dict:
    records = _load_history()
    return {
        "total": len(records),
        "sent":    sum(1 for r in records if r.get("sms_status") == "sent"),
        "failed":  sum(1 for r in records if r.get("sms_status") == "failed"),
        "skipped": sum(1 for r in records if r.get("sms_status") == "skipped"),
        "critical_count": sum(1 for r in records if r.get("severity") == "critical"),
        "twilio_configured": check_twilio_config()["configured"],
    }
