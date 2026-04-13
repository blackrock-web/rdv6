"""
ROADAI Analytics API v5.1 — MongoDB Cloud Edition
=================================================
Migration: Restructured for Asynchronous MongoDB Atlas operations.
"""
import time
import math
from typing import Optional, List
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
import asyncio
from backend.db.database import get_db, docs_to_list
from backend.utils.logger import get_logger
from backend.core.redis_client import redis_cache

logger = get_logger(__name__)
router = APIRouter()

# ── WebSockets Manager ──────────────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

ws_manager = ConnectionManager()

def _linear_forecast(scores: list, days: int = 30) -> list:
    """Simple least-squares linear regression for health score forecasting."""
    n = len(scores)
    if n < 2:
        last = scores[-1] if scores else 80.0
        return [{"day": i + 1, "forecast": round(max(0.0, min(100.0, last)), 1)} for i in range(days)]

    xs = list(range(n))
    x_mean = sum(xs) / n
    y_mean = sum(scores) / n
    num = sum((xs[i] - x_mean) * (scores[i] - y_mean) for i in range(n))
    den = sum((xs[i] - x_mean) ** 2 for i in range(n))
    slope = num / den if den != 0 else 0.0
    intercept = y_mean - slope * x_mean

    result = []
    for i in range(days):
        x = n + i
        val = round(max(0.0, min(100.0, slope * x + intercept)), 1)
        result.append({"day": i + 1, "forecast": val, "lower": round(max(0, val - 5), 1), "upper": round(min(100, val + 5), 1)})
    return result

@router.get("/kpi")
async def get_kpi(days: int = Query(30, ge=1, le=365)):
    """Returns aggregated KPIs for the last N days (Cached for 15s)"""
    cache_key = f"analytics:kpi:{days}"
    cached = await redis_cache.get(cache_key)
    if cached: return cached

    cutoff = time.time() - (days * 86400)
    prev_cutoff = cutoff - (days * 86400)
    
    try:
        db = await get_db()
        
        # Current period analyses
        cursor = db.analyses.find({"created_at": {"$gte": cutoff}}).sort("created_at", -1)
        rows = docs_to_list(await cursor.to_list(length=1000))

        # Previous period for delta comparison
        prev_cursor = db.analyses.find({"created_at": {"$gte": prev_cutoff, "$lt": cutoff}})
        prev_rows = docs_to_list(await prev_cursor.to_list(length=1000))

        # Alert counts
        alerts_cursor = db.alerts.find({"created_at": {"$gte": cutoff}})
        alerts = docs_to_list(await alerts_cursor.to_list(length=1000))

        # Geo events count
        geo_cnt = await db.geo_events.count_documents({"created_at": {"$gte": cutoff}})

        total = len(rows)
        healthy = [r for r in rows if r.get("road_health_score") is not None]
        avg_health = round(sum(r["road_health_score"] for r in healthy) / len(healthy), 1) if healthy else 100.0
        avg_rul = round(sum(r.get("rul_estimate_years", 10) or 10 for r in healthy) / len(healthy), 2) if healthy else 10.0
        total_potholes = sum(r.get("pothole_count", 0) or 0 for r in rows)
        total_cracks = sum(r.get("crack_count", 0) or 0 for r in rows)
        total_damage = total_potholes + total_cracks
        critical_count = len([r for r in rows if r.get("road_health_score", 100) < 40])

        # Previous period deltas
        prev_health_list = [r["road_health_score"] for r in prev_rows if r.get("road_health_score") is not None]
        prev_health = round(sum(prev_health_list) / len(prev_health_list), 1) if prev_health_list else avg_health
        health_delta = round(avg_health - prev_health, 1)

        prev_potholes = sum(r.get("pothole_count", 0) or 0 for r in prev_rows)
        prev_cracks = sum(r.get("crack_count", 0) or 0 for r in prev_rows)

        # Alert stats
        alert_by_sev = {}
        for a in alerts:
            s = a.get("severity", "low")
            alert_by_sev[s] = alert_by_sev.get(s, 0) + 1

        # Weather & Model breakdown
        weather_dist = {}
        model_usage = {}
        for r in rows:
            w = r.get("weather_condition", "unknown") or "unknown"
            weather_dist[w] = weather_dist.get(w, 0) + 1
            m = r.get("model_used", "best.pt") or "best.pt"
            model_usage[m] = model_usage.get(m, 0) + 1

        # Health distribution buckets
        health_dist = {"excellent": 0, "good": 0, "moderate": 0, "poor": 0, "critical": 0}
        for r in healthy:
            s = r["road_health_score"]
            if s >= 85: health_dist["excellent"] += 1
            elif s >= 70: health_dist["good"] += 1
            elif s >= 55: health_dist["moderate"] += 1
            elif s >= 40: health_dist["poor"] += 1
            else: health_dist["critical"] += 1

        # AI insight bullets
        insights = []
        if total == 0:
            insights.append("No analyses recorded yet. Upload a road image or video to get started.")
        else:
            if avg_health >= 75: insights.append(f"Road network is healthy (avg. {avg_health}/100).")
            elif avg_health >= 55: insights.append(f"Road network shows moderate wear (avg. {avg_health}/100).")
            else: insights.append(f"⚠️ Road health is critical at {avg_health}/100.")
            if total_potholes > 0: insights.append(f"{total_potholes} potholes detected.")
            if critical_count > 0: insights.append(f"{critical_count} segments are critical (Health < 40).")

        res = {
            "period_days": days,
            "total_analyses": total,
            "avg_health_score": avg_health,
            "avg_rul_years": avg_rul,
            "total_potholes": total_potholes,
            "total_cracks": total_cracks,
            "total_damage": total_damage,
            "critical_segments": critical_count,
            "geo_events": geo_cnt,
            "alerts": alert_by_sev,
            "health_delta_vs_prev": health_delta,
            "pothole_delta_vs_prev": total_potholes - prev_potholes,
            "crack_delta_vs_prev": total_cracks - prev_cracks,
            "health_distribution": health_dist,
            "weather_distribution": weather_dist,
            "model_usage": model_usage,
            "ai_insights": insights,
        }
        await redis_cache.set(cache_key, res, ex=15)
        return res
    except Exception as e:
        logger.error(f"KPI error: {e}")
        return {"error": str(e), "total_analyses": 0, "avg_health_score": 100, "ai_insights": []}

@router.get("/segments")
async def get_segment_analytics(limit: int = Query(20, le=100)):
    """Returns per-segment health summary sorted by urgency. (Cached 60s)"""
    cache_key = f"analytics:segments:{limit}"
    cached = await redis_cache.get(cache_key)
    if cached: return cached
    
    try:
        from backend.services.geo_service import get_all_segments
        segs = await get_all_segments()
        segs = sorted(segs, key=lambda s: s.get("avg_health", 100))[:limit]
        
        for s in segs:
            h = s.get("avg_health", 100)
            s["health_label"] = "Critical" if h < 40 else "Poor" if h < 55 else "Moderate" if h < 70 else "Good"

        res = {"segments": segs, "total": len(segs)}
        await redis_cache.set(cache_key, res, ex=60)
        return res
    except Exception as e:
        logger.error(f"Segments error: {e}")
        return {"segments": [], "total": 0}

@router.get("/forecast")
async def get_health_forecast(days: int = Query(30, ge=7, le=90)):
    """Returns a health score forecast for the next N days."""
    try:
        db = await get_db()
        cursor = db.analyses.find({"road_health_score": {"$ne": None}}).sort("created_at", 1).limit(60)
        rows = docs_to_list(await cursor.to_list(length=60))
        
        scores = [r["road_health_score"] for r in rows]
        forecast = _linear_forecast(scores, days)
        current = round(scores[-1], 1) if scores else 80.0
        projected = forecast[-1]["forecast"] if forecast else current
        trend = "declining" if projected < current - 3 else "improving" if projected > current + 3 else "stable"
        
        return {
            "current_health": current,
            "projected_health": projected,
            "trend": trend,
            "forecast_days": days,
            "data": forecast,
        }
    except Exception as e:
        logger.error(f"Forecast error: {e}")
        return {"current_health": 80, "projected_health": 80, "trend": "stable", "data": []}

@router.get("/heatmap")
async def get_heatmap(limit: int = Query(500, le=2000)):
    """Returns defect density points for map heat-layer visualization."""
    try:
        db = await get_db()
        cursor = db.geo_events.find({"latitude": {"$ne": None}}).sort("created_at", -1).limit(limit)
        rows = docs_to_list(await cursor.to_list(length=limit))
        
        points = []
        for r in rows:
            intensity = 1.0 - min(1.0, max(0.0, (r.get("road_health_score", 100) or 100) / 100.0))
            defects = (r.get("pothole_count", 0) or 0) + (r.get("crack_count", 0) or 0)
            intensity = min(1.0, intensity + defects * 0.05)
            points.append({
                "lat": r["latitude"], "lng": r["longitude"],
                "intensity": round(intensity, 2),
                "severity": r.get("severity", "low"),
            })
        return {"points": points, "total": len(points)}
    except Exception as e:
        logger.error(f"Heatmap error: {e}")
        return {"points": [], "total": 0}

@router.get("/trends")
async def get_weekly_trends(weeks: int = Query(12, ge=4, le=52)):
    """Returns weekly aggregated health score trend for the last N weeks. (Cached 5m)"""
    cache_key = f"analytics:trends:{weeks}"
    cached = await redis_cache.get(cache_key)
    if cached: return cached
    
    try:
        db = await get_db()
        week_data = []
        now = time.time()
        for w in range(weeks, 0, -1):
            start = now - w * 7 * 86400
            end = now - (w - 1) * 7 * 86400
            cursor = db.analyses.find({"created_at": {"$gte": start, "$lt": end}})
            rows = docs_to_list(await cursor.to_list(length=1000))
            
            valid = [r for r in rows if r.get("road_health_score") is not None]
            avg_h = round(sum(r["road_health_score"] for r in valid) / len(valid), 1) if valid else None
            week_data.append({
                "week": f"W-{w}",
                "analyses": len(rows),
                "avg_health": avg_h,
                "potholes": sum(r.get("pothole_count", 0) or 0 for r in rows),
                "cracks": sum(r.get("crack_count", 0) or 0 for r in rows),
            })
        res = {"weeks": weeks, "data": week_data}
        await redis_cache.set(cache_key, res, ex=300)
        return res
    except Exception as e:
        logger.error(f"Trends error: {e}")
        return {"weeks": weeks, "data": []}

# ── WebSocket Loop ──────────────────────────────────────────────────────────────

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        initial_kpis = await get_kpi(days=30)
        await websocket.send_json({"type": "kpi_update", "data": initial_kpis})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"WebSocket Error: {e}")
        ws_manager.disconnect(websocket)

async def broadcast_kpi_loop():
    while True:
        try:
            if ws_manager.active_connections:
                kpis = await get_kpi(days=30)
                await ws_manager.broadcast({"type": "kpi_update", "data": kpis})
        except Exception as e:
            logger.error(f"Broadcaster error: {e}")
        await asyncio.sleep(15)

# Safe startup Task
_loop_started = False
@router.on_event("startup")
async def start_broadcaster():
    global _loop_started
    if not _loop_started:
        asyncio.create_task(broadcast_kpi_loop())
        _loop_started = True
