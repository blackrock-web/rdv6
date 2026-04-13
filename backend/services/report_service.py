"""ROADAI Report Service v4 — PDF + JSON with full metrics."""
import json, time, uuid
from pathlib import Path
from typing import Optional, List, Any, cast

# Third-party imports at top for IDE resolution
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
import time as _t

# Local imports
from backend.utils.logger import get_logger
logger = get_logger(__name__)
REPORTS_DIR = Path("outputs/reports")

def _health_label(s):
    if s >= 75: return "Good"
    if s >= 55: return "Moderate"
    if s >= 35: return "Poor"
    return "Critical"

def generate_report(analysis_data: dict, report_id: Optional[str] = None, gps_lat=None, gps_lon=None,
                    location_label="", benchmark_winner="", preprocessing_mode="auto") -> dict:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    rid = report_id or str(uuid.uuid4())
    ts  = time.time()
    health   = analysis_data.get("road_health_score") or analysis_data.get("average_health_score") or 100.0
    potholes = analysis_data.get("pothole_count", 0)
    cracks   = analysis_data.get("crack_count", 0)
    rul      = analysis_data.get("rul_estimate_years", 10.0)
    model    = analysis_data.get("model_used", "unknown")
    risk     = analysis_data.get("formation_risk", "none")
    weather  = analysis_data.get("weather_condition", "unknown")
    sev_dist = analysis_data.get("severity_distribution", {})
    json_path = REPORTS_DIR / f"{rid}.json"
    report_data = {
        "report_id": rid, "generated_at": ts, "location": location_label,
        "gps": {"lat": gps_lat, "lon": gps_lon}, "health_score": health,
        "health_label": _health_label(health), "potholes": potholes, "cracks": cracks,
        "rul_years": rul, "model_used": model, "formation_risk": risk,
        "weather": weather, "severity_distribution": sev_dist,
        "benchmark_winner": benchmark_winner, "preprocessing_mode": preprocessing_mode,
        "recommendation": _recommendation(health, potholes, cracks, rul),
        "annotated_video_url": analysis_data.get("annotated_video_url"),
        "annotated_image": analysis_data.get("annotated_image"),
    }
    json_path.write_text(json.dumps(report_data, indent=2))
    pdf_path = None
    try:
        pdf_path = _make_pdf(rid, report_data)
    except Exception as e:
        logger.warning(f"PDF failed: {e}")
    return {"report_id": rid, "pdf_path": str(pdf_path) if pdf_path else None,
            "json_path": str(json_path), "success": True, "created_at": ts}

def _make_pdf(rid, d):
    pdf_path = REPORTS_DIR / f"{rid}.pdf"
    doc = SimpleDocTemplate(str(pdf_path), pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    title_s = ParagraphStyle("T", parent=styles["Title"], fontSize=20, textColor=colors.HexColor("#A855F7"), spaceAfter=4)
    h2_s    = ParagraphStyle("H", parent=styles["Heading2"], fontSize=13, textColor=colors.HexColor("#EC4899"), spaceBefore=12, spaceAfter=4)
    body_s  = ParagraphStyle("B", parent=styles["Normal"], fontSize=10, spaceAfter=3)
    crit_s  = ParagraphStyle("C", parent=styles["Normal"], fontSize=10, textColor=colors.HexColor("#EF4444"), spaceAfter=3)
    warn_s  = ParagraphStyle("W", parent=styles["Normal"], fontSize=10, textColor=colors.HexColor("#F59E0B"), spaceAfter=3)
    c = []
    c.append(Paragraph("ROADAI — Road Intelligence Report v4.0", title_s))
    c.append(Paragraph(f"Generated: {_t.strftime('%Y-%m-%d %H:%M:%S', _t.localtime(d['generated_at']))}", body_s))
    c.append(Paragraph(f"Report ID: {d['report_id']}", body_s))
    if d.get("location"): c.append(Paragraph(f"Location: {d['location']}", body_s))
    c.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#374151"), spaceAfter=8))
    c.append(Paragraph("Road Health Summary", h2_s))
    rows = [["Metric","Value","Status"],
            ["Health Score", f"{d['health_score']:.1f}/100", d["health_label"]],
            ["Potholes", str(d["potholes"]), "HIGH" if d["potholes"]>2 else "OK"],
            ["Cracks",   str(d["cracks"]),   "MON"  if d["cracks"]>3 else "OK"],
            ["RUL (yrs)",f"{d['rul_years']:.1f}", "LOW" if d["rul_years"]<2 else "OK"],
            ["Risk",     d["formation_risk"].upper(), ""],
            ["Weather",  d["weather"].replace("_"," ").title(), ""],
            ["Model",   (d["model_used"] or "")[:40], ""],]
    ts = TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#1E1B4B")),("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),9),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.HexColor("#0F172A"),colors.HexColor("#1E293B")]),
        ("TEXTCOLOR",(0,1),(-1,-1),colors.HexColor("#CBD5E1")),
        ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#374151")),
        ("ALIGN",(0,0),(-1,-1),"LEFT"),("PADDING",(0,0),(-1,-1),6),])
    t = Table(rows, colWidths=[5*cm,4*cm,6*cm]); t.setStyle(ts); c.append(t)
    c.append(Spacer(1,0.4*cm))

    # Add detection breakdowns
    if d.get("severity_distribution"):
        c.append(Paragraph("AI Detections Breakdown", h2_s))
        det_rows = [["Severity Level", "Count"]]
        for k, v in d["severity_distribution"].items():
            det_rows.append([k.upper(), str(v)])
        det_t = Table(det_rows, colWidths=[5*cm, 4*cm])
        det_ts = TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#A855F7")),("TEXTCOLOR",(0,0),(-1,0),colors.white),
            ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),9),
            ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#CBD5E1")),
            ("ALIGN",(0,0),(-1,-1),"LEFT"),("PADDING",(0,0),(-1,-1),6),
        ])
        det_t.setStyle(det_ts)
        c.append(det_t)
        c.append(Spacer(1,0.4*cm))

    c.append(Paragraph("Recommendation & Maintenance", h2_s))
    rec = d.get("recommendation","")
    st = crit_s if d["health_score"]<35 else (warn_s if d["health_score"]<60 else body_s)
    c.append(Paragraph(rec, st))
    c.append(Spacer(1,0.4*cm))
    c.append(HRFlowable(width="100%",thickness=1,color=colors.HexColor("#374151"),spaceAfter=4))
    c.append(Paragraph("Generated by ROADAI v4.0", body_s))
    doc.build(c)
    return pdf_path

def _recommendation(health, potholes, cracks, rul):
    if health>=75: return f"Road in good condition. Routine inspection in 12 months. RUL: {rul:.1f} years."
    if health>=55: return f"Moderate damage ({potholes} potholes, {cracks} cracks). Maintenance in 3-6 months. RUL: {rul:.1f} years."
    if health>=35: return f"Significant damage. Urgent maintenance in 1-3 months. {potholes} potholes, {cracks} cracks. RUL: {rul:.1f} years."
    return f"CRITICAL. Immediate repair recommended. {potholes} potholes, {cracks} cracks. RUL: {rul:.1f} years."

def list_reports():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    files: List[Path] = sorted(list(REPORTS_DIR.glob("*.json")), key=lambda x: x.stat().st_mtime, reverse=True)
    out = []
    for jf in cast(Any, files)[:50]:
        try:
            d = json.loads(jf.read_text())
            pdf = jf.with_suffix(".pdf")
            out.append({"report_id":d.get("report_id",jf.stem),"health_score":d.get("health_score"),
                        "health_label":d.get("health_label"),"potholes":d.get("potholes"),
                        "cracks":d.get("cracks"),"location":d.get("location",""),
                        "generated_at":d.get("generated_at"),"has_pdf":pdf.exists(),
                        "json_path":str(jf),"pdf_path":str(pdf) if pdf.exists() else None})
        except: pass
    return out
