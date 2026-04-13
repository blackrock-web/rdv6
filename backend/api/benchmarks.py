"""
ROADAI Benchmarks API v4.1 — PRD-Aligned
==========================================
Endpoints aligned with ARCDSS PRD v1.0 requirements.

New in v4.1:
  POST /benchmarks/run                — Run full benchmark (background task)
  GET  /benchmarks/status             — Is a benchmark running?
  GET  /benchmarks/results            — Latest benchmark results
  GET  /benchmarks/comparison         — Model comparison table with PRD flags
  POST /benchmarks/run-single/{id}    — Benchmark one model
  GET  /benchmarks/file-results       — Cached results from disk
  GET  /benchmarks/segment-simulation/{id}   — PRD §4.3 10-metre segment report
  GET  /benchmarks/edge-compatibility        — PRD NFR Jetson Orin Nano suitability
  GET  /benchmarks/calibration-info         — PRD §4.2 K-factor reference

Notes:
  • best.pt always remains the road-defect detection runtime.
  • yolov8n.pt always remains the object detection runtime.
  • Benchmark winner is tracked for reference only — it does NOT replace runtimes.
"""
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks, Query
from backend.api.auth import verify_token, require_admin
from backend.core.benchmark_engine import (
    BenchmarkEngine,
    PRD_K, PRD_K_SQUARED, PRD_FRAME_WIDTH_PX, PRD_REAL_WIDTH_M,
    PRD_MIN_FPS, PRD_SURVEY_SPEED_KMH, PRD_FRAMES_PER_SEGMENT,
    PRD_SEGMENT_LENGTH_M, PRD_VIDEO_FPS, PRD_SPEED_MS,
    RHS_SEVERITY_WEIGHTS, PRD_TARGET_CLASSES,
)
from backend.core.runtime_selector import RuntimeModelSelector
from backend.utils.logger import get_logger

logger  = get_logger(__name__)
router  = APIRouter()

BENCHMARK_RESULTS_PATH = Path("config/benchmark_results.json")
_running = False


# ── POST /run ─────────────────────────────────────────────────────────────────

@router.post("/run")
async def run_benchmarks(
    request: Request,
    background_tasks: BackgroundTasks,
    n_segments: int = Query(default=5, ge=1, le=50,
                            description="Number of 10-metre segments to simulate (PRD §4.3)"),
    token: dict = Depends(require_admin),
):
    """
    Run PRD-aligned benchmark for all registered models.
    Executes in background; poll /status to check completion.
    Simulates `n_segments` × 10-metre road stretches per model (PRD §4.3).
    """
    global _running
    if _running:
        return {"message": "Benchmark already running", "status": "running"}

    registry = request.app.state.registry
    selector = request.app.state.selector

    async def _run():
        global _running
        _running = True
        try:
            engine  = BenchmarkEngine(registry)
            results = engine.run_all(n_segments=n_segments)
            BENCHMARK_RESULTS_PATH.parent.mkdir(exist_ok=True)
            BENCHMARK_RESULTS_PATH.write_text(json.dumps(results, indent=2))
            deploy_result = selector.select_and_deploy_winner()
            logger.info(f"✅ Benchmarks v4.1 complete — winner tracked: {deploy_result}")
            logger.info("   NOTE: best.pt remains the pothole/crack detection runtime.")
        except Exception as e:
            logger.error(f"Benchmark run failed: {e}", exc_info=True)
        finally:
            _running = False

    background_tasks.add_task(_run)
    return {
        "message": "PRD-aligned benchmark started in background",
        "status": "running",
        "n_segments": n_segments,
        "prd_checks": [
            "FPS ≥ 15 compliance (PRD NFR)",
            f"Per-class recall/F1 for {PRD_TARGET_CLASSES} (PRD §3.2)",
            f"Camera calibration K-factor accuracy (PRD §4.2, K={PRD_K:.6f} m/px)",
            f"10-metre segment simulation @ {PRD_SURVEY_SPEED_KMH} km/h (PRD §4.3)",
            "RHS + RUL per segment (PRD §4.4)",
            "Jetson Orin Nano edge-device suitability (PRD NFR)",
        ],
        "note": "best.pt remains the defect detection runtime regardless of benchmark winner.",
    }


# ── GET /status ───────────────────────────────────────────────────────────────

@router.get("/status")
async def benchmark_status(token: dict = Depends(verify_token)):
    return {"running": _running}


# ── GET /results ──────────────────────────────────────────────────────────────

@router.get("/results")
async def get_results(request: Request, token: dict = Depends(verify_token)):
    """
    Return all benchmarked models with PRD-aligned metrics:
      • per_class_recall / per_class_f1 (PRD §3.2)
      • calibration_accuracy_pct (PRD §4.2)
      • avg_rhs, avg_rul_years, segment_simulation (PRD §4.3/§4.4)
      • prd_fps_compliant, jetson_orin_suitable (PRD NFR)
    """
    registry = request.app.state.registry
    models   = registry.get_all()
    # Return all models in the registry so the UI can show the full list
    benchmarked = models
    winner   = registry.get_benchmark_winner()

    for m in benchmarked:
        if m.get("runtime_role") is None:
            if m["id"] == "best_pt":
                m.update(runtime_role="defect_runtime", task="road_defect",
                         selected_runtime_role="🟢 Pothole/Crack Detection Runtime (best.pt)")
            elif m["id"] == "yolov8n":
                m.update(runtime_role="object_runtime", task="object_detection",
                         selected_runtime_role="🟢 Object Detection Runtime (yolov8n.pt)")
            else:
                m.update(runtime_role="benchmark_only", task="object_detection",
                         selected_runtime_role="📊 Benchmark Candidate Only")

    return {
        "results": benchmarked,
        "winner":      winner.id   if winner else None,
        "winner_name": winner.name if winner else "Not yet benchmarked",
        "running": _running,
        "prd_compliance_summary": {
            "target_classes":   PRD_TARGET_CLASSES,
            "min_fps_required": PRD_MIN_FPS,
            "survey_speed_kmh": PRD_SURVEY_SPEED_KMH,
            "calibration_k":    PRD_K,
            "segment_length_m": PRD_SEGMENT_LENGTH_M,
        },
        "note": (
            "Benchmark winner tracked for reference. "
            "best.pt is always the pothole/crack detection runtime. "
            "yolov8n.pt is always the object detection runtime."
        ),
    }


# ── GET /comparison ───────────────────────────────────────────────────────────

@router.get("/comparison")
async def get_comparison(request: Request, token: dict = Depends(verify_token)):
    """
    Full model comparison table including PRD NFR compliance flags
    (prd_fps_compliant, is_benchmark_winner) and runtime role assignments.
    """
    registry = request.app.state.registry
    engine   = BenchmarkEngine(registry)
    table    = engine.get_comparison_table()
    selector = request.app.state.selector

    return {
        "comparison_table": table,
        "runtime_assignment": {
            "defect_runtime": {
                "model": "best.pt",
                "task":  "road_defect_detection",
                "path":  selector.defect_model_path,
                "ready": selector._defect_ready,
            },
            "object_runtime": {
                "model": "yolov8n.pt",
                "task":  "general_object_detection",
                "path":  selector.object_model_path,
                "ready": selector._object_ready,
            },
        },
        "total_models":      len(table),
        "available_models":  sum(1 for r in table if r["availability"] == "available"),
        "benchmarked_models":sum(1 for r in table if r["benchmarked"]),
        "prd_compliant_models": sum(1 for r in table if r.get("prd_fps_compliant")),
    }


# ── POST /run-single/{model_id} ───────────────────────────────────────────────

@router.post("/run-single/{model_id}")
async def run_single(
    model_id: str,
    request: Request,
    n_segments: int = Query(default=5, ge=1, le=50),
    token: dict = Depends(require_admin),
):
    """Run PRD-aligned benchmark for a single model by ID."""
    registry = request.app.state.registry
    engine   = BenchmarkEngine(registry)
    result   = engine.run_single(model_id, n_segments=n_segments)
    if not result:
        raise HTTPException(404, f"Model '{model_id}' not found in registry")
    return result


# ── GET /file-results ─────────────────────────────────────────────────────────

@router.get("/file-results")
async def file_results(token: dict = Depends(verify_token)):
    """Return the last persisted benchmark results from disk."""
    if BENCHMARK_RESULTS_PATH.exists():
        try:
            return {
                "results": json.loads(BENCHMARK_RESULTS_PATH.read_text()),
                "source":  "file",
            }
        except Exception as e:
            raise HTTPException(500, f"Failed to read benchmark results: {e}")
    return {
        "results": [],
        "source": "none",
        "message": "No benchmark results yet. POST /benchmarks/run to start.",
    }


# ── GET /segment-simulation/{model_id} ───────────────────────────────────────

@router.get("/segment-simulation/{model_id}")
async def segment_simulation(
    model_id: str,
    request: Request,
    n_segments: int = Query(default=10, ge=1, le=100,
                            description="Number of 10-metre segments to simulate"),
    method: str = Query(default="constant_speed",
                        description="Segmentation method: 'constant_speed' or 'gps'"),
    token: dict = Depends(verify_token),
):
    """
    PRD §4.3 — 10-metre road segment simulation for a given model.

    Returns per-segment RHS, RUL, defect counts, area (m²), alert level,
    and the frame window that maps each segment (constant-speed method).

    Formulae applied (PRD §4.2 / §4.4):
      K  = Real_Width_m / Frame_Width_px = {PRD_REAL_WIDTH_M} / {PRD_FRAME_WIDTH_PX}
      Area_m² = Area_px × K²
      RHS = 100 − Σ(Area_class × W_class)
      RUL derived from RHS band × traffic factor
    """
    registry = request.app.state.registry
    engine   = BenchmarkEngine(registry)
    result   = engine.run_segment_simulation(model_id, n_segments=n_segments, method=method)
    if not result:
        raise HTTPException(404, f"Model '{model_id}' not found")
    return result


# ── GET /edge-compatibility ───────────────────────────────────────────────────

@router.get("/edge-compatibility")
async def edge_compatibility(request: Request, token: dict = Depends(verify_token)):
    """
    PRD NFR §5 — Evaluate all models for NVIDIA Jetson Orin Nano edge deployment.

    Checks:
      • FPS ≥ {PRD_MIN_FPS} at {PRD_SURVEY_SPEED_KMH} km/h survey speed
      • Model size ≤ 200 MB (flash storage constraint)
      • Estimated runtime memory ≤ 4096 MB (Orin Nano 4 GB module)

    Recommended workflow: trtexec → FP16 TensorRT engine → Docker container
    on Jetson Orin Nano for on-vehicle edge inference.
    """
    registry = request.app.state.registry
    engine   = BenchmarkEngine(registry)
    report   = engine.edge_compatibility_report()
    return report


# ── GET /calibration-info ────────────────────────────────────────────────────

@router.get("/calibration-info")
async def calibration_info(token: dict = Depends(verify_token)):
    """
    PRD §4.2 — Camera Calibration Factor (K) reference values used by
    the metric calculation engine to convert pixel area → physical area (m²).

    Formula:
      K = Real_World_Width_m / Frame_Width_px
      Area_m² = Area_px × K²

    Default assumption: 1920×1080 frame covers 3.0 m road width at frame bottom.
    Override via camera-specific calibration measurement on deployment.
    """
    return {
        "prd_section":        "§4.2 — Converting Pixels to Real-World Physical Area",
        "frame_width_px":     PRD_FRAME_WIDTH_PX,
        "real_world_width_m": PRD_REAL_WIDTH_M,
        "k_m_per_px":         round(PRD_K, 8),
        "k_squared_m2_per_px2": round(PRD_K_SQUARED, 12),
        "example": {
            "area_px":   10000,
            "area_m2":   round(10000 * PRD_K_SQUARED, 4),
            "formula":   "Area_m² = Area_px × K²",
        },
        "bbox_method": {
            "prd_ref": "§4.1 Method A — YOLOv8/v10 Detection",
            "formula": "Area_px = W_px × H_px",
        },
        "segmentation_method": {
            "prd_ref": "§4.1 Method B — YOLOv8-Seg Instance Segmentation",
            "formula": "Area_px = ½|Σ(x_i·y_{i+1} − x_{i+1}·y_i)| (Shoelace)",
        },
        "severity_weights": RHS_SEVERITY_WEIGHTS,
        "target_classes":   PRD_TARGET_CLASSES,
        "rhs_formula":      "RHS = 100 − Σ(Area_class_m² × Weight_class)",
        "segment_params": {
            "segment_length_m":   PRD_SEGMENT_LENGTH_M,
            "survey_speed_kmh":   PRD_SURVEY_SPEED_KMH,
            "video_fps":          PRD_VIDEO_FPS,
            "frames_per_segment": PRD_FRAMES_PER_SEGMENT,
            "time_per_segment_s": round(PRD_SEGMENT_LENGTH_M / PRD_SPEED_MS, 3),
        },
        "override_note": (
            "K is derived from a geometric assumption. "
            "For production: measure the actual road width in the frame bottom using a known reference. "
            "K = measured_width_m / frame_width_px."
        ),
    }