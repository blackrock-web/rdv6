"""
ROADAI Admin API v5.0 — MongoDB Cloud Edition
=============================================
Migration: Restructured for Asynchronous MongoDB Atlas operations.
"""
import json, time
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from backend.api.auth import require_admin, verify_token
from backend.db.database import get_db

router = APIRouter()

@router.get("/system-info")
async def system_info(_: dict=Depends(require_admin)):
    import platform, os
    try:
        import torch
        gpu_info = {"available": torch.cuda.is_available(),
                    "device_count": torch.cuda.device_count(),
                    "device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "N/A"}
    except: gpu_info = {"available": False, "note": "torch not installed"}
    return {"platform": platform.platform(), "python": platform.python_version(),
            "cpu_count": os.cpu_count(), "gpu": gpu_info,
            "models_dir": str(Path("models").absolute()),
            "uploads_dir": str(Path("uploads").absolute()),
            "timestamp": time.time()}

@router.get("/usage-stats")
async def usage_stats(_: dict=Depends(require_admin)):
    try:
        db = await get_db()
        total = await db.analyses.count_documents({})
        
        # Aggregate by type
        type_cursor = db.analyses.aggregate([{"$group": {"_id": "$input_type", "count": {"$sum": 1}}}])
        by_type = {entry["_id"]: entry["count"] async for entry in type_cursor}
        
        alerts = await db.alerts.count_documents({})
        
        # Aggregate jobs
        job_cursor = db.jobs.aggregate([{"$group": {"_id": "$status", "count": {"$sum": 1}}}])
        jobs = {entry["_id"]: entry["count"] async for entry in job_cursor}
        
        return {
            "total_analyses": total,
            "by_type": by_type,
            "total_alerts": alerts,
            "jobs": jobs
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/clear-uploads")
async def clear_uploads(_: dict=Depends(require_admin)):
    from pathlib import Path as P
    cnt = 0
    for f in P("uploads").glob("*"):
        if f.is_file() and not f.name.startswith("."):
            f.unlink(missing_ok=True); cnt += 1
    return {"deleted": cnt}

@router.get("/twilio-config")
async def get_twilio_config(_: dict=Depends(require_admin)):
    import os
    return {
        "account_sid": os.environ.get("TWILIO_ACCOUNT_SID", ""),
        "auth_token": os.environ.get("TWILIO_AUTH_TOKEN", ""),
        "phone_number": os.environ.get("TWILIO_PHONE_NUMBER", ""),
        "target_phone": os.environ.get("ALERT_TARGET_PHONE", "")
    }

@router.delete("/clear-history")
async def clear_history(_: dict=Depends(require_admin)):
    """Hard delete all analyses, geo events, and segments from MongoDB."""
    try:
        db = await get_db()
        # In MongoDB, we can just delete all documents
        res1 = await db.analyses.delete_many({})
        await db.jobs.delete_many({})
        await db.geo_events.delete_many({})
        await db.road_segments.delete_many({})
        
        return {
            "success": True, 
            "deleted": res1.deleted_count, 
            "message": "All history cleared from MongoDB Atlas"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear history: {str(e)}")

@router.delete("/clear-alerts")
async def clear_alerts(_: dict=Depends(require_admin)):
    """Hard delete all alert logs from MongoDB."""
    try:
        db = await get_db()
        res = await db.alerts.delete_many({})
        return {
            "success": True, 
            "deleted": res.deleted_count, 
            "message": "All alerts cleared from MongoDB"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear alerts: {str(e)}")

class AdminSettings(BaseModel):
    gps_tracking_enabled: bool

@router.get("/settings")
async def get_settings(_: dict=Depends(verify_token)):
    # Simple JSON settings persistence for non-critical config
    settings_path = Path("config/admin_settings.json")
    if not settings_path.exists():
        settings_path.parent.mkdir(exist_ok=True)
        settings_path.write_text(json.dumps({"gps_tracking_enabled": False}))
    return json.loads(settings_path.read_text())

@router.post("/settings")
async def update_settings(settings: AdminSettings, _: dict=Depends(require_admin)):
    settings_path = Path("config/admin_settings.json")
    settings_path.parent.mkdir(exist_ok=True)
    settings_path.write_text(json.dumps(settings.dict()))
    return {"success": True, "message": "Settings updated", "settings": settings.dict()}
