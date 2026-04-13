import os, time
from datetime import datetime
from fpdf     import FPDF
from backend.core.celery_app import celery_app
from backend.utils.logger    import get_logger

logger = get_logger(__name__)

@celery_app.task(name="generate_road_report")
def generate_road_report(report_id: str, data: dict):
    """
    Enterprise-grade PDF report generation.
    Includes branding, summary statistics, and defect breakdown.
    """
    try:
        logger.info(f"🚀 Generating PDF report: {report_id}")
        pdf = FPDF()
        pdf.add_page()
        
        # ── Branding & Header ───────────────────────────────────────────────
        pdf.set_font("helvetica", "B", 26)
        pdf.set_text_color(30, 58, 138) # Deep Blue
        pdf.cell(0, 20, "RoadAI Enterprise", ln=True, align="C")
        
        pdf.set_font("helvetica", "I", 10)
        pdf.set_text_color(107, 114, 128) # Gray
        pdf.cell(0, 5, f"Automated Infrastructure Audit | {datetime.now().strftime('%B %d, %Y %H:%M')}", ln=True, align="C")
        pdf.ln(15)
        
        # ── Executive Summary ───────────────────────────────────────────────
        pdf.set_font("helvetica", "B", 16)
        pdf.set_text_color(17, 24, 39) # Dark
        pdf.cell(0, 10, "1. Executive Summary", ln=True)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)
        
        pdf.set_font("helvetica", "", 12)
        health = data.get("avg_health", 100.0)
        status = "EXCELLENT" if health > 90 else "GOOD" if health > 75 else "FAIR" if health > 50 else "CRITICAL"
        
        pdf.cell(50, 10, "Status Index:", ln=0)
        pdf.set_font("helvetica", "B", 12)
        pdf.cell(0, 10, status, ln=1)
        
        pdf.set_font("helvetica", "", 12)
        pdf.cell(50, 10, "Health Score:", ln=0)
        pdf.cell(0, 10, f"{health:.2f}%", ln=1)
        
        pdf.cell(50, 10, "Total Defects:", ln=0)
        pdf.cell(0, 10, str(data.get("total_defects", 0)), ln=1)
        pdf.ln(10)
        
        # ── Defect Analysis ─────────────────────────────────────────────────
        pdf.set_font("helvetica", "B", 16)
        pdf.cell(0, 10, "2. Defect Analysis Breakdown", ln=True)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)
        
        pdf.set_font("helvetica", "", 11)
        breakdown = data.get("breakdown", {})
        if not breakdown:
            pdf.cell(0, 10, "No significant surface defects detected in the analyzed period.", ln=True)
        else:
            # Table Header
            pdf.set_fill_color(243, 244, 246)
            pdf.set_font("helvetica", "B", 11)
            pdf.cell(60, 10, "  Defect Type", 1, 0, 'L', True)
            pdf.cell(40, 10, "  Occurrence", 1, 1, 'C', True)
            
            pdf.set_font("helvetica", "", 11)
            for dtype, count in breakdown.items():
                pdf.cell(60, 10, f"  {dtype.capitalize()}", 1, 0, 'L')
                pdf.cell(40, 10, f"  {count}", 1, 1, 'C')
        
        pdf.ln(20)
        
        # ── Methodology ─────────────────────────────────────────────────────
        pdf.set_font("helvetica", "B", 14)
        pdf.cell(0, 10, "3. Methodology", ln=True)
        pdf.set_font("helvetica", "", 10)
        pdf.multi_cell(0, 5, (
            "This report was generated using the RoadAI v4.0 Computer Vision pipeline. "
            "Data is fused from real-time defect detection (YOLOv8), weather-compensation filtering, "
            "and segment-level health variance analytics."
        ))

        # ── Footer ──────────────────────────────────────────────────────────
        pdf.set_y(-25)
        pdf.set_font("helvetica", "I", 8)
        pdf.set_text_color(156, 163, 175)
        pdf.cell(0, 10, f"Document Hash: {report_id} | Proprietary & Confidential", align="L")
        pdf.set_x(-30)
        pdf.cell(0, 10, f"Page {pdf.page_no()}", align="R")

        # Save
        out_dir = "outputs/reports"
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{report_id}.pdf")
        pdf.output(out_path)
        
        logger.info(f"✅ Report generated successfully: {out_path}")
        return out_path

    except Exception as e:
        logger.error(f"❌ Report generation failed: {e}")
        raise
