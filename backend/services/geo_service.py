"""
ROADAI Geo Service — GPS tagging, detection event storage, segment aggregation.
Migration to MongoDB Atlas (Async).
"""
import uuid
import time
from typing import List, Optional, Dict
from dataclasses import dataclass, asdict

from backend.utils.logger import get_logger
from backend.db.database import get_db, docs_to_list, doc_to_dict

logger = get_logger(__name__)

# Grid resolution for segment bucketing (degrees)
SEGMENT_GRID = 0.001  # ~111m per 0.001°

@dataclass
class GeoEvent:
    id: str
    timestamp: float
    latitude: Optional[float]
    longitude: Optional[float]
    location_label: str
    is_simulated: bool
    severity: str
    pothole_count: int
    crack_count: int
    road_health_score: float
    rul_estimate_years: float
    model_used: str
    source_type: str
    preprocessing_mode: str
    annotated_image_path: Optional[str]
    alert_sent: bool = False
    segment_id: Optional[str] = None

@dataclass
class RoadSegment:
    id: str
    lat_bucket: float
    lon_bucket: float
    label: str
    event_count: int = 0
    total_potholes: int = 0
    total_cracks: int = 0
    avg_health: float = 100.0
    worst_health: float = 100.0
    worst_severity: str = "none"
    avg_rul: float = 10.0
    last_observed: float = 0.0
    maintenance_urgency: str = "none"
    trend: str = "stable"

def _segment_id(lat: float, lon: float) -> str:
    blat = round(round(lat / SEGMENT_GRID) * SEGMENT_GRID, 6)
    blon = round(round(lon / SEGMENT_GRID) * SEGMENT_GRID, 6)
    return f"{blat:.6f}_{blon:.6f}"

def _urgency_from_health(health: float) -> str:
    if health >= 75: return "none"
    if health >= 55: return "low"
    if health >= 40: return "medium"
    if health >= 25: return "high"
    return "critical"

async def record_event(
    analysis_result: dict,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    location_label: str = "",
    source_type: str = "image",
    preprocessing_mode: str = "auto",
    annotated_image_path: Optional[str] = None,
) -> GeoEvent:
    """Record a detection event with optional GPS coordinates."""
    is_simulated = latitude is None or longitude is None

    if is_simulated:
        latitude  = 12.9716 + (hash(str(time.time())) % 1000) / 100000
        longitude = 77.5946 + (hash(str(time.time()) + "x") % 1000) / 100000
        if not location_label:
            location_label = "Simulated (GPS unavailable)"

    sev_dist = analysis_result.get("severity_distribution", {})
    severity = "none"
    for s in ["critical", "high", "medium", "low"]:
        if sev_dist.get(s, 0) > 0:
            severity = s
            break

    event = GeoEvent(
        id=str(uuid.uuid4())[:8],
        timestamp=time.time(),
        latitude=round(latitude, 6),
        longitude=round(longitude, 6),
        location_label=location_label or f"{latitude:.5f}, {longitude:.5f}",
        is_simulated=is_simulated,
        severity=severity,
        pothole_count=analysis_result.get("pothole_count", 0),
        crack_count=analysis_result.get("crack_count", 0),
        road_health_score=analysis_result.get("road_health_score", 100.0),
        rul_estimate_years=analysis_result.get("rul_estimate_years", 10.0),
        model_used=analysis_result.get("model_used", "unknown"),
        source_type=source_type,
        preprocessing_mode=preprocessing_mode,
        annotated_image_path=annotated_image_path,
        segment_id=_segment_id(latitude, longitude),
    )

    db = await get_db()
    # Save Event
    await db.geo_events.insert_one(asdict(event))
    
    # Update Segment
    await _update_segment(event)
    
    logger.info(f"GeoEvent saved to MongoDB: {event.id}")
    return event

async def _update_segment(event: GeoEvent):
    db = await get_db()
    sid = event.segment_id
    
    seg_doc = await db.road_segments.find_one({"id": sid})
    if not seg_doc:
        seg = asdict(RoadSegment(
            id=sid,
            lat_bucket=event.latitude,
            lon_bucket=event.longitude,
            label=event.location_label,
        ))
    else:
        seg = seg_doc

    n = seg.get("event_count", 0)
    seg["event_count"] = n + 1
    seg["total_potholes"] = seg.get("total_potholes", 0) + event.pothole_count
    seg["total_cracks"] = seg.get("total_cracks", 0) + event.crack_count
    seg["avg_health"] = round((seg.get("avg_health", 100) * n + event.road_health_score) / (n + 1), 1)
    seg["worst_health"] = min(seg.get("worst_health", 100), event.road_health_score)

    sev_order = ["none", "low", "medium", "high", "critical"]
    current_worst = seg.get("worst_severity", "none")
    if sev_order.index(event.severity) > sev_order.index(current_worst):
        seg["worst_severity"] = event.severity

    seg["avg_rul"] = round((seg.get("avg_rul", 10) * n + event.rul_estimate_years) / (n + 1), 1)
    seg["last_observed"] = event.timestamp
    seg["maintenance_urgency"] = _urgency_from_health(seg["worst_health"])

    # Basic trend analysis
    if n >= 1:
        cursor = db.geo_events.find({"segment_id": sid}).sort("timestamp", -1).limit(2)
        recent = await cursor.to_list(length=2)
        if len(recent) == 2:
            delta = recent[0]["road_health_score"] - recent[1]["road_health_score"]
            seg["trend"] = "improving" if delta > 3 else "worsening" if delta < -3 else "stable"

    # Save Segment (Upsert)
    if not seg_doc:
        await db.road_segments.insert_one(seg)
    else:
        await db.road_segments.replace_one({"id": sid}, seg)

async def get_all_events(
    severity_filter: Optional[str] = None,
    source_filter: Optional[str] = None,
    limit: int = 200,
) -> List[dict]:
    db = await get_db()
    query = {}
    if severity_filter: query["severity"] = severity_filter
    if source_filter: query["source_type"] = source_filter
    
    cursor = db.geo_events.find(query).sort("timestamp", -1).limit(limit)
    return docs_to_list(await cursor.to_list(length=limit))

async def get_all_segments(min_urgency: Optional[str] = None) -> List[dict]:
    db = await get_db()
    query = {}
    if min_urgency:
        urgency_order = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
        min_rank = urgency_order.get(min_urgency, 0)
        # Filter in Python for simplicity with the custom ordering or use MongoDB $expr if needed
        # We'll fetch all and filter for now as segment count is usually small
        cursor = db.road_segments.find()
        segs = docs_to_list(await cursor.to_list(length=1000))
        return [s for s in segs if urgency_order.get(s.get("maintenance_urgency", "none"), 0) >= min_rank]
    
    cursor = db.road_segments.find().sort("worst_health", 1)
    return docs_to_list(await cursor.to_list(length=500))

async def get_top_critical_segments(n: int = 5) -> List[dict]:
    segs = await get_all_segments()
    return segs[:n]

async def get_analysis_stats() -> dict:
    db = await get_db()
    total_events = await db.geo_events.count_documents({})
    total_segments = await db.road_segments.count_documents({})

    # Aggregate severities
    pipeline = [{"$group": {"_id": "$severity", "count": {"$sum": 1}}}]
    sev_cursor = db.geo_events.aggregate(pipeline)
    severity_count = {s: 0 for s in ["critical", "high", "medium", "low", "none"]}
    async for entry in sev_cursor:
        if entry["_id"] in severity_count:
            severity_count[entry["_id"]] = entry["count"]

    # Avg Health
    if total_events > 0:
        health_agg = await db.geo_events.aggregate([{"$group": {"_id": None, "avg": {"$avg": "$road_health_score"}}}]).to_list(1)
        avg_health = health_agg[0]["avg"] if health_agg else 100
    else:
        avg_health = 100

    critical_segments = await db.road_segments.count_documents({"maintenance_urgency": "critical"})

    return {
        "total_events": total_events,
        "total_segments": total_segments,
        "severity_distribution": severity_count,
        "average_health": round(avg_health, 2),
        "critical_segments": critical_segments
    }
