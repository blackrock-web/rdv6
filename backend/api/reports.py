"""ROADAI Reports API v5.0 — Filtered list, summary stats, bulk-export."""
import io
import json
import time
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from backend.services.report_service import generate_report, list_reports
from backend.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


class ReportRequest(BaseModel):
    analysis_data: dict
    gps_lat: Optional[float] = None
    gps_lon: Optional[float] = None
    location_label: str = ""
    benchmark_winner: str = ""
    preprocessing_mode: str = "auto"


def _health_label(s: float) -> str:
    if s >= 85: return "Excellent"
    if s >= 70: return "Good"
    if s >= 55: return "Moderate"
    if s >= 40: return "Poor"
    return "Critical"


@router.post("/generate")
async def gen_report(req: ReportRequest):
    return generate_report(
        req.analysis_data,
        gps_lat=req.gps_lat, gps_lon=req.gps_lon,
        location_label=req.location_label,
        benchmark_winner=req.benchmark_winner,
        preprocessing_mode=req.preprocessing_mode,
    )


@router.get("/list")
async def list_reps(
    severity: Optional[str] = Query(None, description="Filter: critical | poor | moderate | good"),
    date_from: Optional[float] = Query(None, description="Unix timestamp start"),
    date_to: Optional[float] = Query(None, description="Unix timestamp end"),
    sort_by: str = Query("created_at", enum=["created_at", "health_score", "potholes"]),
    sort_dir: str = Query("desc", enum=["asc", "desc"]),
    limit: int = Query(100, le=500),
):
    all_reports = list_reports()

    # Filter by severity/health
    if severity:
        thresholds = {
            "critical": (0, 40), "poor": (40, 55), "moderate": (55, 70),
            "good": (70, 85), "excellent": (85, 101),
        }
        lo, hi = thresholds.get(severity, (0, 101))
        all_reports = [r for r in all_reports if lo <= (r.get("health_score") or 0) < hi]

    # Filter by date
    if date_from:
        all_reports = [r for r in all_reports if (r.get("generated_at") or 0) >= date_from]
    if date_to:
        all_reports = [r for r in all_reports if (r.get("generated_at") or 0) <= date_to]

    # Sort
    reverse = sort_dir == "desc"
    key_map = {"created_at": "generated_at", "health_score": "health_score", "potholes": "potholes"}
    sort_key = key_map.get(sort_by, "generated_at")
    all_reports.sort(key=lambda r: r.get(sort_key) or 0, reverse=reverse)

    return {"reports": all_reports[:limit], "total": len(all_reports)}


@router.get("/summary")
async def reports_summary():
    """Returns aggregate statistics across all reports."""
    all_reports = list_reports()
    if not all_reports:
        return {"total": 0, "avg_health": None, "total_potholes": 0, "total_cracks": 0, "worst_location": None}

    totals_p = sum(r.get("potholes") or 0 for r in all_reports)
    totals_c = sum(r.get("cracks") or 0 for r in all_reports)
    healthy = [r for r in all_reports if r.get("health_score") is not None]
    avg_h = round(sum(r["health_score"] for r in healthy) / len(healthy), 1) if healthy else None

    worst = min(all_reports, key=lambda r: r.get("health_score") or 100, default=None)
    severity_dist = {"excellent": 0, "good": 0, "moderate": 0, "poor": 0, "critical": 0}
    for r in all_reports:
        lbl = _health_label(r.get("health_score") or 100).lower()
        if lbl in severity_dist:
            severity_dist[lbl] += 1

    return {
        "total": len(all_reports),
        "avg_health": avg_h,
        "total_potholes": totals_p,
        "total_cracks": totals_c,
        "worst_location": worst.get("location") if worst else None,
        "worst_health": worst.get("health_score") if worst else None,
        "severity_distribution": severity_dist,
    }


@router.get("/download/{report_id}")
async def download_report(report_id: str, fmt: str = "pdf"):
    p = Path(f"outputs/reports/{report_id}.{fmt}")
    if not p.exists():
        # Maybe it's a newer analysis without a physical file yet? 
        # Check if it exists in DB. If so, return 404 with specific msg.
        raise HTTPException(404, "Report file not found. Run analysis first.")
    mt = "application/pdf" if fmt == "pdf" else "application/json"
    return FileResponse(str(p), media_type=mt, filename=p.name)

@router.get("/pdf/{report_id}")
async def download_pdf_report(report_id: str):
    return await download_report(report_id, fmt="pdf")

@router.get("/json/{report_id}")
async def download_json_report(report_id: str):
    return await download_report(report_id, fmt="json")


@router.post("/bulk-export")
async def bulk_export(
    severity: Optional[str] = Query(None),
    fmt: str = Query("json", enum=["json", "pdf"]),
    limit: int = Query(50, le=200),
):
    """Returns a ZIP archive of the requested reports."""
    all_reports = list_reports()
    if severity:
        thresholds = {"critical": (0, 40), "poor": (40, 55), "moderate": (55, 70), "good": (70, 101)}
        lo, hi = thresholds.get(severity, (0, 101))
        all_reports = [r for r in all_reports if lo <= (r.get("health_score") or 0) < hi]

    all_reports = all_reports[:limit]
    reports_dir = Path("outputs/reports")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for r in all_reports:
            rid = r.get("report_id", "unknown")
            f = reports_dir / f"{rid}.{fmt}"
            if f.exists():
                zf.write(str(f), arcname=f.name)
            else:
                # Fallback — embed the metadata JSON
                zf.writestr(f"{rid}.json", json.dumps(r, indent=2))

    buf.seek(0)
    ts = int(time.time())
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=roadai_reports_{ts}.zip"},
    )
