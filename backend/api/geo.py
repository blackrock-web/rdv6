"""ROADAI Geo API v4."""
from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import Optional
from backend.services.geo_service import get_all_events, get_all_segments, get_top_critical_segments, record_event
from backend.utils.logger import get_logger
logger = get_logger(__name__)
router = APIRouter()

class GeoRecord(BaseModel):
    analysis_result: dict; latitude: Optional[float]=None; longitude: Optional[float]=None
    location_label: str=""; source_type: str="image"; preprocessing_mode: str="auto"

@router.post("/record")
async def record_geo(req: GeoRecord):
    ev = await record_event(req.analysis_result,req.latitude,req.longitude,req.location_label,req.source_type,req.preprocessing_mode)
    return {"success":True,"event_id":ev.id,"segment_id":ev.segment_id,"is_simulated":ev.is_simulated}

@router.get("/events")
async def get_events(severity: Optional[str]=Query(None), source: Optional[str]=Query(None), limit: int=Query(200,le=500)):
    return {"events":await get_all_events(severity,source,limit)}

@router.get("/segments")
async def get_segments(min_urgency: Optional[str]=Query(None)):
    return {"segments":await get_all_segments(min_urgency)}

@router.get("/segments/critical")
async def critical_segs(n: int=Query(5,le=20)):
    return {"segments":await get_top_critical_segments(n)}
