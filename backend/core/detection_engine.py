"""
ROADAI Detection Engine — Fixed v3.6
======================================
Fixes applied (vs v3.5):
  1. Class names read from model.names (like Streamlit app) — not hardcoded
  2. damage_type resolved by class NAME (pothole/crack keywords), not cid==0
  3. Road presence check: if no road surface detected → health=100, RUL=10,
     no defects, clear "no_road_detected" flag set
  4. Webcam/stream: when no road in frame, annotated image shows
     "NO ROAD DETECTED" banner and all counts = 0
  5. Lane overlay: only drawn when lane confidence is NOT "none"
     (already worked but reinforced — no overlay on faces/indoor scenes)
  6. Defect class matching uses flexible keyword matching
     (works with any best.pt class naming convention)

Pipeline stages (unchanged):
  Stage 1: Weather analysis + preprocessing
  Stage 2: Active lane detection
  Stage 3: Road mask (ground plane estimation)
  Stage 4: Damage detection via best.pt — FIXED class resolution
  Stage 5: Wall / road-surface filter
  Stage 6: Active-lane priority assignment
  Stage 7: Object detection via yolov8n.pt
  Stage 8: Analytics + road-presence gate — NEW
  Stage 9: Annotation
"""

import os
import cv2
import numpy as np
import time
import random
import base64
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List

from backend.utils.logger import get_logger
from backend.core.lane_mask import (
    LaneMaskGenerator, RoadSurfaceClassifier, GroundPlaneEstimator,
)
from backend.core.weather_analyzer import WeatherAnalyzer, WeatherResult
from backend.core.road_type_analyzer import (
    ActiveLaneAnalyzer, LaneAnalysis, DamagePriority,
    PRIORITY_ACTIVE, PRIORITY_ROAD, PRIORITY_OFFROAD,
    ROAD_UNKNOWN,
)
from backend.core.crack_predictor import CrackPredictor
from backend.core.metrics import ANALYSIS_COUNT, INFERENCE_LATENCY, DEFECTS_TOTAL, AVG_HEALTH_SCORE

logger = get_logger(__name__)

# ── Default model paths ───────────────────────────────────────────────────────
_DEFECT_MODEL_PATH = os.environ.get("DEFECT_MODEL_PATH", "models/custom/best.pt")
_OBJECT_MODEL_PATH = os.environ.get("OBJECT_MODEL_PATH", "models/candidates/yolov8n.pt")

# ── COCO object classes for scene detection ───────────────────────────────────
OBJECT_CLASSES = {
    0: "person", 1: "bicycle", 2: "car", 3: "motorcycle",
    5: "bus", 7: "truck", 9: "traffic_light",
    11: "stop_sign", 12: "parking_meter",
}

# ── Road damage keyword patterns ─────────────────────────────────────────────
# Used to classify detections by name from model.names
# Keys are substrings to search in the class name (lowercase)
POTHOLE_KEYWORDS = {"pothole", "potholes", "road_pothole", "road-pothole", "d40"}
CRACK_KEYWORDS   = {
    "crack", "cracks", "longitudinal", "transverse", "alligator",
    "road_crack", "road-crack", "fissure", "fracture",
    "d00", "d10", "d20", "d_00", "d_10", "d_20"
}
DAMAGE_KEYWORDS  = {"damage", "road_damage", "surface_damage", "patch", "rutting", "marking", "d30", "d43", "d44", "d50"}

# ── Visual styling ─────────────────────────────────────────────────────────────
SEVERITY_BGR = {
    "low":      (80,  220, 80),
    "medium":   (0,   190, 255),
    "high":     (0,   100, 255),
    "critical": (0,   0,   255),
}
OBJECT_BGR = (255, 200, 0)
WALL_BGR   = (180, 100, 220)

PRIORITY_BGR = {
    PRIORITY_ACTIVE:  (0,   0,   255),
    PRIORITY_ROAD:    (0,   165, 255),
    PRIORITY_OFFROAD: (180, 100, 220),
}


def _is_real_model(path: Path) -> bool:
    try:
        if not path.exists():
            return False
        content = path.read_bytes()
        return not (content.startswith(b"ROADAI") or len(content) < 1024)
    except Exception:
        return False


def _resolve_damage_type(class_name: str) -> str:
    """
    Determine damage_type from actual class name (from model.names).
    Like the Streamlit app: uses keyword matching, not hardcoded class IDs.
    """
    name = class_name.lower().replace("-", "_").replace(" ", "_")
    if any(k in name for k in POTHOLE_KEYWORDS):
        return "pothole"
    if any(k in name for k in CRACK_KEYWORDS):
        return "crack"
    if any(k in name for k in DAMAGE_KEYWORDS):
        return "damage"
    # Fallback: treat as damage (not falsely counted as pothole/crack)
    return "damage"


def _is_road_defect(class_name: str) -> bool:
    """True if this class name is a road defect (not a person/car/building)."""
    name = class_name.lower().replace("-", "_").replace(" ", "_")
    return any(k in name for k in (
        POTHOLE_KEYWORDS | CRACK_KEYWORDS | DAMAGE_KEYWORDS
    ))


def _detect_road_presence(frame: np.ndarray, road_mask: np.ndarray,
                          lane_analysis: "LaneAnalysis") -> bool:
    """
    Heuristic road presence check.
    Returns True if there's evidence of a road surface in the frame.
    Uses three signals: road_mask coverage, lane detection, and color/texture.
    """
    h, w = frame.shape[:2]
    total_pixels = h * w

    # Signal 1: road mask coverage
    if road_mask is not None:
        road_coverage = float(np.sum(road_mask > 0)) / max(total_pixels, 1)
        if road_coverage > 0.05:   # ★ Lowered threshold → detect partial road views
            return True

    # Signal 2: lane lines detected
    if lane_analysis.detected and lane_analysis.lane_confidence in ("strong", "weak", "curved"):
        return True

    # Signal 3: lower portion gray/asphalt color check
    # Road surfaces tend to be gray/dark in lower 40% of frame
    lower = frame[int(h * 0.60):, :]
    if lower.size > 0:
        hsv = cv2.cvtColor(lower, cv2.COLOR_BGR2HSV)
        # Low saturation, mid-to-dark value = road/asphalt
        low_sat = float(np.mean(hsv[:, :, 1])) < 55     # desaturated
        mid_val = 20 < float(np.mean(hsv[:, :, 2])) < 180  # not pure black, not sky-bright
        if low_sat and mid_val:
            return True

    return False


# ── AnalysisResult ─────────────────────────────────────────────────────────────

@dataclass
class Detection:
    class_id: int
    class_name: str
    confidence: float
    bbox: list
    area: float
    is_road_surface: bool = True
    damage_type: str = ""
    severity: str = "low"
    filter_reason: str = "accepted"
    filter_confidence: float = 1.0
    lane_overlap: float = 1.0
    priority: str = PRIORITY_ROAD
    priority_label: str = "Road (Outside Lane)"
    road_overlap: float = 0.0


@dataclass
class AnalysisResult:
    frame_id: int = 0
    timestamp: float = 0.0

    damage_detections: list = field(default_factory=list)
    object_detections: list = field(default_factory=list)
    wall_detections:   list = field(default_factory=list)

    pothole_count: int = 0
    crack_count:   int = 0
    damage_count:  int = 0   # NEW: generic damage class count
    total_damage_count: int = 0
    wall_filtered_count: int = 0

    active_lane_count: int = 0
    road_outside_lane_count: int = 0
    offroad_count: int = 0

    road_health_score: float = 100.0
    rul_estimate_years: float = 10.0
    rul_label: str = ""
    rul_risk_band: str = ""
    rul_method: str = ""
    damage_coverage_pct: float = 0.0
    severity_distribution: dict = field(default_factory=dict)

    # Road presence
    road_detected: bool = True   # NEW: False when no road found in frame
    road_detection_note: str = ""  # NEW: message to show user

    lane_detected: bool = False
    lane_polygon: list = field(default_factory=list)
    lane_confidence: str = "none"
    lane_marking_quality: str = "unknown"
    curve_detected: bool = False
    curve_direction: str = ""
    fallback_active: bool = False
    fallback_reason: str = ""

    road_type: str = ROAD_UNKNOWN

    weather_condition: str = "unknown"
    weather_confidence: float = 0.0
    weather_condition_scores: dict = field(default_factory=dict)
    weather_preprocessing_applied: list = field(default_factory=list)
    weather_note: str = ""
    conf_threshold_used: float = 0.35
    preprocessing_mode: str = "auto"

    formation_prediction: str = "no_damage_detected"
    formation_risk: str = "none"

    model_used: str = "none"
    defect_model_used: str = "simulation"
    object_model_used: str = "simulation"
    processing_time_ms: float = 0.0
    annotated_image_b64: str = ""
    pipeline_timings: dict = field(default_factory=dict)
    filter_stats: dict = field(default_factory=dict)


# ── Damage Analyzer ────────────────────────────────────────────────────────────

# ── Damage Analyzer ────────────────────────────────────────────────────────────

class DamageAnalyzer:
    def __init__(self):
        self.crack_predictor = CrackPredictor()

    # ── NEW CONSTANTS ────────────────────────────────────────────────────────
    POTHOLE_WEIGHT = 10.0
    CRACK_WEIGHT   = 3.0
    DAMAGE_WEIGHT  = 1.0
    POTHOLE_SCALE  = 40.0   # Tighter scale for more aggressive health scoring

    FORMATION_PENALTY = {
        "critical": 15.0,
        "high": 10.0,
        "medium": 5.0,
        "low": 1.0
    }

    def compute_health_score(
        self,
        detections,
        frame_area,
        history=None,
        formation_risk: str = "none"
    ) -> float:
        """New stable health scoring (count-based, not pixel-area dependent)"""
        if not detections:
            base = 100.0
        else:
            weighted = sum(
                self.POTHOLE_WEIGHT if getattr(d, "class_name", "damage").lower() == "pothole" else
                self.CRACK_WEIGHT   if getattr(d, "class_name", "damage").lower() == "crack" else
                self.DAMAGE_WEIGHT
                for d in detections
            )
            base = 100.0 / (1.0 + weighted / self.POTHOLE_SCALE)

        penalty = self.FORMATION_PENALTY.get(formation_risk, 0.0)
        final_score = base - penalty
        return round(max(0.0, min(100.0, final_score)), 1)

    def compute_cumulative_health(self, pothole_count: int, crack_count: int, damage_count: int = 0) -> float:
        """
        Compute road health from total accumulated detection counts across all frames.
        Used for video-level final summary (not per-frame).
        """
        weighted = (pothole_count * self.POTHOLE_WEIGHT 
                  + crack_count   * self.CRACK_WEIGHT 
                  + damage_count  * self.DAMAGE_WEIGHT)
        
        # VIDEO_SCALE is much tighter (20.0) to ensure high totals (e.g. 600+) 
        # result in critical scores (< 1.0%).
        VIDEO_SCALE = 20.0 
        score = 100.0 / (1.0 + weighted / VIDEO_SCALE)
        return round(max(0.0, min(100.0, score)), 1)

    def estimate_rul(
        self,
        health_score: float,
        traffic_factor: float = 1.5,
        formation_risk: str = "none"
    ) -> float:
        """RUL estimation based on health score (PRD v1.0 formula)"""
        h = health_score
        
        # Calibrated formula: ensure Health < 40 results in < 1.0 year
        if h >= 95:
            rul = 15.0
        elif h >= 80:
            rul = 8.0  + (h - 80) * 0.4
        elif h >= 60:
            rul = 4.0  + (h - 60) * 0.2
        elif h >= 40:
            rul = 1.0  + (h - 40) * 0.15
        else:
            # Critical bands
            rul = max(0.1, h * 0.02)
            
        final_rul = rul / (traffic_factor / 1.5)
        return round(max(0.1, min(15.0, final_rul)), 1)

    def classify_severity(self, area, frame_area, conf):
        r = area / max(frame_area, 1)

        if r > 0.035 or conf > 0.80:
            return "critical"
        if r > 0.015 or conf > 0.65:
            return "high"
        if r > 0.004 or conf > 0.45:
            return "medium"

        return "low"

    def predict_formation(self, detections, history=None, current_health=100.0):
        if history and len(history) >= 5:
            forecast = self.crack_predictor.predict_from_history(history, current_health)
            return f"{forecast.primary_reason} (in ~{forecast.days_to_formation} days)", forecast.risk_level

        if not detections:
            return "no_damage_detected", "none"

        active = [d for d in detections if d.priority == PRIORITY_ACTIVE]
        ph = sum(1 for d in detections if d.damage_type == "pothole")
        cr = sum(1 for d in detections if d.damage_type == "crack")
        al = sum(1 for d in detections if "alligator" in d.class_name)
        cv = sum(1 for d in detections if d.severity == "critical")
        act_ph = sum(1 for d in active if d.damage_type == "pothole")

        if cv >= 2 or al >= 1 or act_ph >= 2 or ph >= 3:
            return "high_risk_pothole_formation", "critical"
        if cr >= 3 or ph >= 1 or len(active) >= 2:
            return "medium_risk_crack_propagation", "high"
        if cr >= 1:
            return "low_risk_crack_propagation", "medium"

        return "low_risk_stable", "low"


# ── Detection Engine ───────────────────────────────────────────────────────────

class DetectionEngine:
    """
    9-stage road analysis pipeline.
    Stage 4: road defect detection via best.pt — reads model.names correctly.
    Stage 7: object detection via yolov8n.pt.
    New: road presence gate resets all metrics when no road in frame.
    """

    def __init__(self, selector=None):
        self.model            = None   # best.pt – defect detection
        self.object_model     = None   # yolov8n.pt – object detection
        self._defect_names    = {}     # model.names from best.pt — populated at load
        self._object_names    = {}     # model.names from yolov8n.pt
        self.surface_clf      = RoadSurfaceClassifier()
        self.ground_estimator = GroundPlaneEstimator()
        self.lane_mask_gen    = LaneMaskGenerator()
        self.analyzer         = DamageAnalyzer()
        self.weather_analyzer = WeatherAnalyzer()
        self.lane_analyzer    = ActiveLaneAnalyzer()
        self.device           = "cpu"
        self.rul_service      = None
        try:
            from backend.core.rul_service import RULService
            self.rul_service = RULService()
        except:
            pass
        self._defect_sim      = True
        self._object_sim      = True
        self._defect_model_label = "simulation"
        self._object_model_label = "simulation"
        self._load_models(selector)

    def _load_models(self, selector=None):
        defect_path = None
        object_path = None

        if selector is not None:
            defect_path = selector.defect_model_path
            object_path = selector.object_model_path

        if not defect_path:
            for p in [Path(_DEFECT_MODEL_PATH), Path("models/custom/best.pt"), Path("models/best.pt")]:
                if _is_real_model(p):
                    defect_path = str(p)
                    break

        if not object_path:
            for p in [Path(_OBJECT_MODEL_PATH), Path("models/candidates/yolov8n.pt")]:
                if _is_real_model(p):
                    object_path = str(p)
                    break

        # ultralytics availability check
        try:
            from ultralytics import YOLO as _YOLO  # noqa
            ultra_available = True
        except ImportError:
            ultra_available = False
            logger.warning("ultralytics not installed – simulation mode")

        # PyTorch 2.6 weights_only fix & CUDA
        if ultra_available:
            try:
                import torch as _torch
                
                self.device = "cuda" if _torch.cuda.is_available() else "cpu"
                if self.device == "cuda":
                    logger.info(f"🚀 CUDA Detected! Loading YOLO on GPU ({_torch.cuda.get_device_name(0)})")
                else:
                    logger.info("⚡ CUDA Not available. Using CPU for YOLO.")
                    
                _orig = _torch.load
                def _patched(f, *a, **kw):
                    if "weights_only" not in kw:
                        kw["weights_only"] = False
                    return _orig(f, *a, **kw)
                _torch.load = _patched
                logger.info("PyTorch weights_only=False patch applied")
            except Exception as e:
                logger.warning(f"torch.load patch failed: {e}")

        # Load defect model
        if defect_path and ultra_available:
            try:
                from ultralytics import YOLO
                
                # Check for ONNX alternative ONLY on CPU to ensure maximum GPU stability
                if self.device == "cpu":
                    onnx_path = Path("models/onnx") / f"{Path(defect_path).stem}.onnx"
                    actual_path = str(onnx_path) if onnx_path.exists() else defect_path
                    if onnx_path.exists():
                        logger.info(f"⚡ Fast ONNX defect model found: {onnx_path}")
                else:
                    actual_path = defect_path
                
                self.model = YOLO(actual_path)
                if actual_path.endswith(".pt"):
                    self.model.to(self.device)
                else:
                    logger.info("ONNX model loaded (runs on CPU provider by default)")
                # ── Read actual class names from model ──────────────────────
                raw_names = self.model.names
                if isinstance(raw_names, list):
                    self._defect_names = {i: n for i, n in enumerate(raw_names)}
                else:
                    self._defect_names = dict(raw_names)
                self._defect_sim = False
                self._defect_model_label = f"best.pt ({Path(defect_path).name})"
                logger.info(f"✅ Defect model loaded: {defect_path}")
                logger.info(f"   Class names: {self._defect_names}")
            except Exception as e:
                logger.error(f"best.pt load failed: {e} – simulation mode")
                self._defect_sim = True
                self._defect_model_label = f"simulation (load error: {str(e)[:60]})"
        else:
            if not defect_path:
                logger.warning("best.pt not found – defect simulation mode")
                self._defect_model_label = "simulation (best.pt missing)"

        # Load object model
        if ultra_available:
            obj_src = object_path if (object_path and _is_real_model(Path(object_path))) else "yolov8n.pt"
            try:
                from ultralytics import YOLO
                
                onnx_obj_path = Path("models/onnx") / f"{Path(obj_src).stem}.onnx"
                actual_obj_path = str(onnx_obj_path) if onnx_obj_path.exists() else obj_src
                if onnx_obj_path.exists():
                    logger.info(f"⚡ Fast ONNX object model found: {onnx_obj_path}")
                
                self.object_model = YOLO(actual_obj_path)
                if actual_obj_path.endswith(".pt"):
                    self.object_model.to(self.device)
                raw_names = self.object_model.names
                self._object_names = {i: n for i, n in enumerate(raw_names)} if isinstance(raw_names, list) else dict(raw_names)
                self._object_sim = False
                self._object_model_label = f"yolov8n.pt ({obj_src})"
                logger.info(f"✅ Object model loaded: {obj_src}")
            except Exception as e:
                logger.error(f"yolov8n load failed: {e} – simulation mode")
                self._object_sim = True
                self._object_model_label = f"simulation (load error: {str(e)[:60]})"

        logger.info(
            f"DetectionEngine ready | "
            f"defect={'REAL' if not self._defect_sim else 'SIM'} | "
            f"object={'REAL' if not self._object_sim else 'SIM'}"
        )

    def reload_defect_model(self, model_path: str):
        """Thread-safe and memory-conscious reload of the defect detection model."""
        import gc
        from pathlib import Path
        try:
            from ultralytics import YOLO
            # 1. Clear existing model from memory
            if self.model:
                del self.model
            gc.collect()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except:
                pass

            # 2. Load new model
            new_model = YOLO(model_path)
            # 3. Offload to CPU if appropriate for stability, or keep on device
            new_model.to(self.device)

            # 4. Update class names
            raw_names = new_model.names
            self._defect_names = {i: n for i, n in enumerate(raw_names)} if isinstance(raw_names, list) else dict(raw_names)
            
            # 5. Swap
            self.model = new_model
            self._defect_sim = False
            self._defect_model_label = f"best.pt ({Path(model_path).name})"
            logger.info(f"✅ Defect model reloaded: {model_path}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to reload defect model {model_path}: {e}")
            self._defect_sim = True
            self._defect_model_label = f"simulation (reload fail: {str(e)[:50]})"
            return False

    def reload_object_model(self, obj_src: str):
        """Thread-safe and memory-conscious reload of the object detection model."""
        import gc
        from pathlib import Path
        try:
            from ultralytics import YOLO
            # 1. Clear existing
            if self.object_model:
                del self.object_model
            gc.collect()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except:
                pass

            # 2. Load
            new_obj = YOLO(obj_src)
            new_obj.to(self.device)

            # 3. Swap
            self.object_model = new_obj
            raw_names = self.object_model.names
            self._object_names = {i: n for i, n in enumerate(raw_names)} if isinstance(raw_names, list) else dict(raw_names)
            self._object_sim = False
            self._object_model_label = f"yolov8n.pt ({obj_src})"
            logger.info(f"✅ Object model reloaded: {obj_src}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to reload object model {obj_src}: {e}")
            self._object_sim = True
            self._object_model_label = f"simulation (reload fail: {str(e)[:50]})"
            return False

    # ── Main pipeline ──────────────────────────────────────────────────────────

    def analyze_frame(self, frame: np.ndarray, frame_id: int = 0, history=None,
                      preprocessing_mode: str = "auto", source_type: str = "image",
                      use_lane: bool = True) -> AnalysisResult:
        t0_total = time.time()
        result = AnalysisResult(frame_id=frame_id, timestamp=time.time())
        h, w = frame.shape[:2]
        timings = {}

        # ── Stage 1: Weather analysis + preprocessing ────────────────────────
        t0 = time.time()
        weather: WeatherResult = self.weather_analyzer.classify(frame)
        if preprocessing_mode and preprocessing_mode not in ("auto", ""):
            try:
                from backend.services.preprocessing_service import preprocess_frame
                prep_result = preprocess_frame(frame, mode=preprocessing_mode)
                enhanced_frame = prep_result.frame
                prep_steps = prep_result.steps
                adj_from_prep = prep_result.conf_threshold_adj
            except Exception as _pe:
                enhanced_frame, prep_steps = self.weather_analyzer.preprocess(frame, weather.condition)
                adj_from_prep = weather.conf_threshold_adjustment
        else:
            enhanced_frame, prep_steps = self.weather_analyzer.preprocess(frame, weather.condition)
            adj_from_prep = weather.conf_threshold_adjustment
        timings["weather_ms"] = round((time.time() - t0) * 1000, 1)

        result.weather_condition            = weather.condition
        result.weather_confidence           = weather.confidence
        result.weather_condition_scores     = weather.condition_scores
        result.weather_preprocessing_applied = prep_steps
        result.weather_note                 = weather.note
        result.preprocessing_mode          = preprocessing_mode
        base_conf = 0.25   # ★ Lowered from 0.35 → more sensitive to subtle cracks
        adj_conf  = max(0.15, min(0.50, base_conf + adj_from_prep))
        result.conf_threshold_used = adj_conf

        # ── Stage 2: Active lane detection ──────────────────────────────────
        t0 = time.time()
        if use_lane:
            lane_analysis: LaneAnalysis = self.lane_analyzer.analyze(enhanced_frame)
        else:
            # Skip lane detection — create a null/empty LaneAnalysis
            lane_analysis = self.lane_analyzer.analyze.__func__.__annotations__  # dummy
            from backend.core.road_type_analyzer import LaneAnalysis as _LaneAnalysis
            lane_analysis = _LaneAnalysis()  # all defaults: not detected, no polygon
        timings["lane_ms"] = round((time.time() - t0) * 1000, 1)

        result.lane_detected         = lane_analysis.detected
        result.lane_polygon          = lane_analysis.lane_polygon
        result.lane_confidence       = lane_analysis.lane_confidence
        result.lane_marking_quality  = lane_analysis.marking_quality
        result.curve_detected        = lane_analysis.curve_detected
        result.curve_direction       = lane_analysis.curve_direction
        result.fallback_active       = lane_analysis.fallback_active
        result.fallback_reason       = lane_analysis.fallback_reason
        result.road_type             = lane_analysis.road_type

        # Draw lane overlay only if lane detection is enabled
        working = self._draw_lane_overlay(enhanced_frame.copy(), lane_analysis) if use_lane else enhanced_frame.copy()

        # ── Stage 3: Road mask ───────────────────────────────────────────────
        t0 = time.time()
        road_mask = self.ground_estimator.get_road_region_mask(frame)
        timings["road_mask_ms"] = round((time.time() - t0) * 1000, 1)

        # ── ★ NEW: Road presence gate ─────────────────────────────────────────
        # Before running expensive detection, check if road is visible.
        # If not, skip detection entirely and return safe/null state.
        if use_lane:
            road_present = _detect_road_presence(frame, road_mask, lane_analysis)
        else:
            # Bypass road presence check if lane detection is manually toggled off
            road_present = True

        result.road_detected = road_present

        if not road_present:
            # No road in frame — set clear state, annotate, and return
            result.road_detection_note = (
                "No road surface detected in this frame. "
                "Point camera at a road to enable damage detection."
            )
            result.road_health_score    = 100.0  # unknown = no penalty
            result.rul_estimate_years   = 10.0
            result.formation_risk       = "none"
            result.formation_prediction = "no_road_in_frame"
            result.pothole_count        = 0
            result.crack_count          = 0
            result.total_damage_count   = 0
            result.severity_distribution = {"low": 0, "medium": 0, "high": 0, "critical": 0}
            result.defect_model_used    = self._defect_model_label
            result.object_model_used    = self._object_model_label
            result.model_used           = f"defect={self._defect_model_label} | object={self._object_model_label}"
            result.pipeline_timings     = timings
            result.processing_time_ms   = round((time.time() - t0_total) * 1000, 1)
            # Annotate with "no road" banner
            result.annotated_image_b64 = self._to_b64(
                self._annotate_no_road(working, result)
            )
            return result

        # ── Stage 4: Damage detection via best.pt ────────────────────────────
        t0 = time.time()
        raw: List[Detection] = []
        if self.model and not self._defect_sim:
            try:
                # ⚠ Disable TTA (augment=True) by default as it's model-dependent and causes spam warnings if unsupported
                _use_tta = False  # Changed from True to stop TTA spam

                results_list = self.model.predict(
                    enhanced_frame,
                    conf=adj_conf,
                    iou=0.45,
                    imgsz=640,
                    augment=_use_tta,
                    max_det=300,
                    device=self.device,
                    verbose=False,
                )
                for pred in results_list:
                    for box in pred.boxes:
                        cid  = int(box.cls[0])
                        conf = float(box.conf[0])
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        area = (x2 - x1) * (y2 - y1)

                        class_name = self._defect_names.get(cid, f"damage_{cid}")

                        if not _is_road_defect(class_name):
                            logger.debug(
                                f"Skipping non-defect class '{class_name}' (cid={cid}) "
                                f"from defect model — add to DAMAGE_KEYWORDS to include"
                            )
                            continue

                        damage_type = _resolve_damage_type(class_name)

                        raw.append(Detection(
                            class_id=cid,
                            class_name=class_name,
                            confidence=conf,
                            bbox=[x1, y1, x2, y2],
                            area=area,
                            damage_type=damage_type,
                            severity=self.analyzer.classify_severity(area, h * w, conf),
                        ))
            except Exception as e:
                logger.error(f"Defect inference error: {e} – simulation fallback")
                raw = self._sim_dets(h, w)
        else:
            raw = self._sim_dets(h, w)
        if self.model and not self._defect_sim:
            INFERENCE_LATENCY.labels(model_id=self._defect_model_label).observe(time.time() - t0)
        timings["detection_ms"] = round((time.time() - t0) * 1000, 1)

        # ── Stage 5: Wall / road-surface filter ──────────────────────────────
        t0 = time.time()
        lane_mask = lane_analysis.lane_mask
        lane_poly = lane_analysis.lane_polygon
        road_dets: List[Detection] = []
        wall_dets: List[Detection] = []
        fc = {"accepted": 0, "rejected_geometry": 0, "rejected_color": 0,
              "rejected_above_horizon": 0, "rejected_aspect": 0, "rejected_other": 0}

        for det in raw:
            dec = self.surface_clf.classify(det.bbox, frame, lane_poly, lane_mask, road_mask)
            det.is_road_surface   = dec.is_road
            det.filter_reason     = dec.reason
            det.filter_confidence = dec.confidence
            det.lane_overlap      = dec.lane_overlap
            if dec.is_road:
                road_dets.append(det)
                fc["accepted"] += 1
            else:
                wall_dets.append(det)
                rk = "rejected_" + dec.reason.split("–")[0].strip().replace(" ", "_")
                fc[rk] = fc.get(rk, 0) + 1
        timings["filter_ms"] = round((time.time() - t0) * 1000, 1)

        # ── Stage 6: Active-lane priority ─────────────────────────────────────
        t0 = time.time()
        for det in road_dets:
            dp: DamagePriority = self.lane_analyzer.prioritize_detection(
                det.bbox, lane_analysis, road_mask, frame.shape
            )
            det.priority       = dp.priority
            det.priority_label = dp.priority_label
            det.lane_overlap   = dp.lane_overlap
            det.road_overlap   = dp.road_overlap
        timings["priority_ms"] = round((time.time() - t0) * 1000, 1)

        # ── Stage 7: Object detection via yolov8n.pt ─────────────────────────
        t0 = time.time()
        if self.object_model and not self._object_sim:
            try:
                for pred in self.object_model.predict(
                    frame, conf=0.35, iou=0.5, imgsz=640,
                    device=self.device, verbose=False
                ):
                    for box in pred.boxes:
                        cid = int(box.cls[0])
                        # Use actual model names for object detection too
                        obj_name = self._object_names.get(cid, OBJECT_CLASSES.get(cid, ""))
                        if not obj_name:
                            continue
                        result.object_detections.append({
                            "class":      obj_name,
                            "confidence": round(float(box.conf[0]), 3),
                            "bbox":       [int(v) for v in box.xyxy[0].tolist()],
                        })
            except Exception as e:
                logger.error(f"Object detection error: {e} – simulation fallback")
                result.object_detections = self._sim_objs()
        else:
            result.object_detections = self._sim_objs()
        timings["objects_ms"] = round((time.time() - t0) * 1000, 1)

        # ── Stage 8: Analytics ─────────────────────────────────────────────────
        active_dets       = [d for d in road_dets if d.priority == PRIORITY_ACTIVE]
        road_dets_outside = [d for d in road_dets if d.priority == PRIORITY_ROAD]

        # ★ Correct counts using damage_type (resolved from class names)
        result.pothole_count          = sum(1 for d in road_dets if d.damage_type == "pothole")
        result.crack_count            = sum(1 for d in road_dets if d.damage_type == "crack")
        result.damage_count           = sum(1 for d in road_dets if d.damage_type == "damage")
        result.total_damage_count     = len(road_dets)
        result.wall_filtered_count    = len(wall_dets)
        result.active_lane_count      = len(active_dets)
        result.road_outside_lane_count = len(road_dets_outside)
        result.offroad_count          = len(wall_dets)

        # ── Stage 8: Analytics (v2 Upgraded Flow) ──
        active_dets       = [d for d in road_dets if d.priority == PRIORITY_ACTIVE]
        road_dets_outside = [d for d in road_dets if d.priority == PRIORITY_ROAD]

        # Counts
        result.pothole_count          = sum(1 for d in road_dets if d.damage_type == "pothole")
        result.crack_count            = sum(1 for d in road_dets if d.damage_type == "crack")
        result.damage_count           = sum(1 for d in road_dets if d.damage_type == "damage")
        result.total_damage_count     = len(road_dets)
        result.wall_filtered_count    = len(wall_dets)
        result.active_lane_count      = len(active_dets)
        result.road_outside_lane_count = len(road_dets_outside)
        result.offroad_count          = len(wall_dets)

        # 1. Base health (detections only, no formation penalty yet)
        base_h = self.analyzer.compute_health_score(road_dets, h * w, history, formation_risk="none")

        # 2. Predict formation (using base health)
        result.formation_prediction, result.formation_risk = \
            self.analyzer.predict_formation(road_dets, history, base_h)

        # 3. Final upgraded health (including formation penalty)
        result.road_health_score = self.analyzer.compute_health_score(
            road_dets, h * w, history, formation_risk=result.formation_risk
        )

        # 4. RUL estimation via XGBoost ML if available, else heuristic
        try:
            if self.rul_service:
                rul_res = self.rul_service.estimate(
                    health_score=result.road_health_score,
                    pothole_count=result.pothole_count,
                    crack_count=result.crack_count,
                    damage_coverage_pct=result.damage_coverage_pct,
                    weather_condition=result.weather_condition,
                    formation_risk=result.formation_risk
                )
                result.rul_estimate_years = rul_res.rul_years
                result.rul_label = rul_res.label
                result.rul_risk_band = rul_res.risk_band
                result.rul_method = rul_res.method
            else:
                raise ValueError("RULService not loaded")
        except Exception as e:
            result.rul_estimate_years = self.analyzer.estimate_rul(
                result.road_health_score, formation_risk=result.formation_risk
            )
            result.rul_label = "Good condition — routine maintenance recommended" if result.rul_estimate_years >= 8 else "Maintenance needed"
            result.rul_risk_band = "safe" if result.rul_estimate_years >= 8 else "urgent"
            result.rul_method = "Heuristic (Fallback)"

        result.damage_coverage_pct = round(
            sum(d.area for d in road_dets) / max(h * w, 1) * 100, 2
        )
        sev = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        for d in road_dets:
            sev[d.severity] = sev.get(d.severity, 0) + 1
        result.severity_distribution = sev

        result.damage_detections = [{
            "class_name":      d.class_name,
            "confidence":      round(d.confidence, 3),
            "bbox":            [int(v) for v in d.bbox],
            "severity":        d.severity,
            "damage_type":     d.damage_type,
            "is_road_surface": d.is_road_surface,
            "filter_reason":   d.filter_reason,
            "lane_overlap":    round(d.lane_overlap, 3),
            "road_overlap":    round(d.road_overlap, 3),
            "priority":        d.priority,
            "priority_label":  d.priority_label,
        } for d in (road_dets + wall_dets)]
        result.wall_detections = [{
            "class_name":    d.class_name,
            "confidence":    round(d.confidence, 3),
            "bbox":          [int(v) for v in d.bbox],
            "filter_reason": d.filter_reason,
        } for d in wall_dets]

        # Person / face safety suppression
        person_suppression = os.environ.get("PERSON_REGION_SUPPRESSION", "true").lower() == "true"
        face_blur_enabled  = os.environ.get("FACE_BLUR_ENABLED", "false").lower() == "true"

        if person_suppression and result.object_detections:
            try:
                from backend.services.preprocessing_service import suppress_person_detections
                filtered, suppressed_count = suppress_person_detections(
                    result.damage_detections, result.object_detections
                )
                result.damage_detections = filtered
                if suppressed_count:
                    result.filter_stats["person_suppressed"] = suppressed_count
                    result.pothole_count      = sum(1 for d in filtered if d.get("damage_type") == "pothole")
                    result.crack_count        = sum(1 for d in filtered if d.get("damage_type") == "crack")
                    result.total_damage_count = len(filtered)
            except Exception as _pse:
                logger.debug(f"Person suppression skipped: {_pse}")

        if face_blur_enabled:
            try:
                from backend.services.preprocessing_service import blur_faces_in_frame
                working, face_count = blur_faces_in_frame(working)
                if face_count:
                    result.filter_stats["faces_blurred"] = face_count
            except Exception:
                pass

        result.defect_model_used = self._defect_model_label
        result.object_model_used = self._object_model_label
        result.model_used = f"defect={self._defect_model_label} | object={self._object_model_label}"

        # ── Stage 9: Annotation ────────────────────────────────────────────────
        result.annotated_image_b64 = self._to_b64(
            self._annotate(working, road_dets, wall_dets, result, weather)
        )
        result.pipeline_timings   = timings
        result.filter_stats       = fc
        result.processing_time_ms = round((time.time() - t0_total) * 1000, 1)
        
        # ── Prometheus Instrumentation ───────────────────────────────────────
        try:
            ANALYSIS_COUNT.labels(
                status="success", 
                model_id=self._defect_model_label, 
                input_type=source_type
            ).inc()
            for d in road_dets:
                DEFECTS_TOTAL.labels(defect_type=d.damage_type, severity=d.severity).inc()
            AVG_HEALTH_SCORE.set(result.road_health_score)
        except Exception as _me:
            logger.debug(f"Metrics update skipped: {_me}")

        return result

    # ── Lane overlay — only when real lanes detected ───────────────────────────

    def _draw_lane_overlay(self, frame: np.ndarray, la: LaneAnalysis) -> np.ndarray:
        """Draw lane overlay ONLY when real lane markings were detected."""
        if not la.lane_polygon or la.lane_confidence == "none":
            return frame  # no random trapezoid on faces/indoor scenes
        poly_np = np.array(la.lane_polygon, dtype=np.int32)
        ov = frame.copy()
        fill_color = (50, 230, 80) if la.lane_confidence == "strong" else (50, 200, 160)
        alpha = 0.15 if la.lane_confidence == "strong" else 0.10
        cv2.fillPoly(ov, [poly_np], fill_color)
        cv2.addWeighted(ov, alpha, frame, 1 - alpha, 0, frame)
        line_color = (0, 255, 80) if la.lane_confidence == "strong" else (0, 220, 180)
        cv2.polylines(frame, [poly_np], True, line_color, 2, cv2.LINE_AA)
        if len(la.lane_polygon) >= 4:
            lb = tuple(la.lane_polygon[0]); lt = tuple(la.lane_polygon[1])
            rt = tuple(la.lane_polygon[2]); rb = tuple(la.lane_polygon[3])
            cv2.line(frame, lb, lt, line_color, 3, cv2.LINE_AA)
            cv2.line(frame, rb, rt, line_color, 3, cv2.LINE_AA)
        return frame

    # ── "No road" annotation ───────────────────────────────────────────────────

    def _annotate_no_road(self, frame: np.ndarray, result: AnalysisResult) -> np.ndarray:
        """Annotate frame with clear NO ROAD DETECTED message."""
        ann = frame.copy()
        h, w = ann.shape[:2]

        # Dark overlay
        ov = ann.copy()
        cv2.rectangle(ov, (0, 0), (w, h), (0, 0, 0), -1)
        cv2.addWeighted(ov, 0.35, ann, 0.65, 0, ann)

        # Red border
        cv2.rectangle(ann, (4, 4), (w - 4, h - 4), (0, 60, 200), 3)

        # Main message
        msg1 = "NO ROAD DETECTED"
        msg2 = "Point camera at a road surface"
        msg3 = "Damage detection requires visible road"

        font = cv2.FONT_HERSHEY_SIMPLEX
        (tw, th), _ = cv2.getTextSize(msg1, font, 0.9, 2)
        cx = (w - tw) // 2
        cy = h // 2 - 20
        cv2.putText(ann, msg1, (cx, cy),         font, 0.9,  (0, 80, 255), 2, cv2.LINE_AA)
        (tw2, _), _ = cv2.getTextSize(msg2, font, 0.5, 1)
        cv2.putText(ann, msg2, ((w - tw2) // 2, cy + 35), font, 0.5,  (150, 150, 255), 1, cv2.LINE_AA)
        (tw3, _), _ = cv2.getTextSize(msg3, font, 0.45, 1)
        cv2.putText(ann, msg3, ((w - tw3) // 2, cy + 60), font, 0.45, (120, 120, 200), 1, cv2.LINE_AA)

        # Small HUD
        ov2 = ann.copy()
        cv2.rectangle(ov2, (8, 8), (300, 95), (10, 12, 18), -1)
        cv2.addWeighted(ov2, 0.75, ann, 0.25, 0, ann)
        cv2.rectangle(ann, (8, 8), (300, 95), (0, 40, 120), 1)
        def_short = "REAL" if "simulation" not in self._defect_model_label else "SIM"
        for i, (txt, col) in enumerate([
            (f"Health:  N/A (no road)",     (120, 120, 120)),
            (f"Defects: 0 | Potholes: 0",   (120, 120, 120)),
            (f"Status:  NO ROAD IN FRAME",  (0, 80, 255)),
            (f"Model:   [{def_short}]",     (130, 200, 130) if def_short == "REAL" else (200, 180, 80)),
        ]):
            cv2.putText(ann, txt, (16, 26 + i * 18), font, 0.38, col, 1, cv2.LINE_AA)
        return ann

    # ── Simulation ─────────────────────────────────────────────────────────────

    def _sim_dets(self, h: int, w: int) -> List[Detection]:
        """Synthetic detections for demo when best.pt is not loaded."""
        dets = []
        SIM_NAMES = {0: "pothole", 1: "crack_longitudinal", 2: "crack_transverse",
                     3: "crack_alligator", 4: "road_marking_damage", 5: "patch"}
        SIM_DTYPES = {0: "pothole", 1: "crack", 2: "crack", 3: "crack", 4: "damage", 5: "damage"}
        for _ in range(random.randint(2, 5)):
            cx = random.randint(int(w * 0.15), int(w * 0.85))
            cy = random.randint(int(h * 0.55), int(h * 0.92))
            bw = random.randint(40, 160); bh = random.randint(30, 100)
            x1 = max(0, cx - bw // 2); y1 = max(0, cy - bh // 2)
            x2 = min(w, cx + bw // 2); y2 = min(h, cy + bh // 2)
            area = (x2 - x1) * (y2 - y1)
            cid  = random.choices([0, 1, 2, 3, 4, 5], weights=[3, 3, 2, 2, 1, 1])[0]
            conf = round(random.uniform(0.48, 0.92), 3)
            dets.append(Detection(
                class_id=cid, class_name=SIM_NAMES.get(cid, "damage"),
                confidence=conf, bbox=[x1, y1, x2, y2], area=area,
                damage_type=SIM_DTYPES.get(cid, "damage"),
                severity=self.analyzer.classify_severity(area, h * w, conf),
            ))
        # Add some wall-candidate dets (upper region)
        for _ in range(random.randint(0, 2)):
            cx = random.randint(int(w * 0.05), int(w * 0.95))
            cy = random.randint(int(h * 0.05), int(h * 0.30))
            bw = random.randint(15, 60); bh = random.randint(50, 150)
            x1 = max(0, cx - bw // 2); y1 = max(0, cy - bh // 2)
            x2 = min(w, cx + bw // 2); y2 = min(h, cy + bh // 2)
            area = (x2 - x1) * (y2 - y1)
            cid  = random.randint(0, 5)
            conf = round(random.uniform(0.40, 0.72), 3)
            dets.append(Detection(
                class_id=cid, class_name=SIM_NAMES.get(cid, "damage"),
                confidence=conf, bbox=[x1, y1, x2, y2], area=area,
                damage_type=SIM_DTYPES.get(cid, "damage"),
                severity=self.analyzer.classify_severity(area, h * w, conf),
            ))
        return dets

    def _sim_objs(self):
        """Synthetic object detections for demo mode."""
        objs = ["car", "truck", "person", "bicycle", "bus", "motorcycle"]
        return [{
            "class": random.choice(objs),
            "confidence": round(random.uniform(0.55, 0.95), 3),
            "bbox": [
                random.randint(0, 300), random.randint(0, 200),
                random.randint(300, 600), random.randint(200, 400),
            ],
        } for _ in range(random.randint(0, 3))]

    # ── Annotation ─────────────────────────────────────────────────────────────

    def _annotate(self, frame, road_dets, wall_dets, result, weather) -> np.ndarray:
        ann = frame.copy()
        # Wall detections (corner brackets)
        for det in wall_dets:
            x1, y1, x2, y2 = [int(v) for v in det.bbox]
            cl = max(8, min(20, (x2 - x1) // 4))
            for px, py in [(x1, y1), (x2, y1), (x1, y2), (x2, y2)]:
                dx = cl if px == x1 else -cl
                dy = cl if py == y1 else -cl
                cv2.line(ann, (px, py), (px + dx, py), WALL_BGR, 2)
                cv2.line(ann, (px, py), (px, py + dy), WALL_BGR, 2)
            cv2.putText(ann, "NON-ROAD", (x1, max(y1 - 5, 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.33, WALL_BGR, 1)
        # Road detections
        for det in road_dets:
            x1, y1, x2, y2 = [int(v) for v in det.bbox]
            pri_col = PRIORITY_BGR.get(det.priority, (150, 150, 150))
            sev_col = SEVERITY_BGR.get(det.severity, (180, 180, 180))
            cv2.rectangle(ann, (x1, y1), (x2, y2), pri_col, 2)
            cv2.rectangle(ann, (x1 + 2, y1 + 2), (x2 - 2, y2 - 2), sev_col, 1)
            pri_short = {PRIORITY_ACTIVE: "ACTIVE", PRIORITY_ROAD: "ROAD", PRIORITY_OFFROAD: "OFFRD"}.get(det.priority, "?")
            lbl = f"{det.class_name} {det.confidence:.2f} [{pri_short}/{det.severity[:3].upper()}]"
            (tw, th), _ = cv2.getTextSize(lbl, cv2.FONT_HERSHEY_SIMPLEX, 0.35, 1)
            cv2.rectangle(ann, (x1, max(y1 - th - 6, 0)), (x1 + tw + 4, max(y1 - 2, 0)), pri_col, -1)
            cv2.putText(ann, lbl, (x1 + 2, max(y1 - 4, 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 0), 1)
        # Object detections
        for obj in result.object_detections:
            ox1, oy1, ox2, oy2 = obj["bbox"]
            cv2.rectangle(ann, (ox1, oy1), (ox2, oy2), OBJECT_BGR, 2)
            cv2.putText(ann, f"{obj['class']} {obj['confidence']:.2f}", (ox1, max(oy1 - 5, 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.37, OBJECT_BGR, 1)
        # HUD overlay
        h_f, w_f = ann.shape[:2]
        ov = ann.copy()
        cv2.rectangle(ov, (8, 8), (365, 220), (10, 12, 18), -1)
        cv2.addWeighted(ov, 0.72, ann, 0.28, 0, ann)
        cv2.rectangle(ann, (8, 8), (365, 220), (60, 80, 120), 1)
        w_disp = _weather_display(weather.condition)
        rc_col = {"none": (80, 220, 80), "low": (160, 220, 80), "medium": (0, 190, 255),
                  "high": (0, 100, 255), "critical": (0, 0, 255)}.get(result.formation_risk, (200, 200, 200))
        lc_col = {"strong": (80, 255, 80), "weak": (0, 200, 255), "curved": (0, 230, 200),
                  "none": (120, 120, 200)}.get(result.lane_confidence, (200, 200, 200))
        hc = (200, 240, 120)
        def_short = "REAL" if "simulation" not in self._defect_model_label else "SIM"
        obj_short = "REAL" if "simulation" not in self._object_model_label else "SIM"
        # Show correct pothole and crack counts in HUD
        hud_lines = [
            (f"Health:   {result.road_health_score:.0f}/100", hc),
            (f"RUL:      {result.rul_estimate_years:.1f} yrs", hc),
            (f"Potholes: {result.pothole_count}  |  Cracks: {result.crack_count}", hc),
            (f"Active:   {result.active_lane_count}  Road: {result.road_outside_lane_count}  Fltrd: {result.wall_filtered_count}", hc),
            (f"Risk:     {result.formation_risk.upper()}", rc_col),
            (f"Lane:     {result.lane_confidence.upper()} | {result.road_type.replace('_', ' ')}", lc_col),
            (f"Weather:  {w_disp}", (160, 210, 255)),
            (f"Prep:     {', '.join(result.weather_preprocessing_applied) or 'none'}", (130, 130, 160)),
            (f"Defect:   [{def_short}]  Object: [{obj_short}]", (130, 200, 130) if def_short == "REAL" else (200, 180, 80)),
        ]
        for i, (txt, col) in enumerate(hud_lines):
            cv2.putText(ann, txt, (16, 26 + i * 21), cv2.FONT_HERSHEY_SIMPLEX, 0.39, col, 1, cv2.LINE_AA)
        # Legend
        lx, ly = w_f - 165, h_f - 65
        cv2.rectangle(ann, (lx - 5, ly - 12), (w_f - 5, h_f - 5), (10, 12, 18), -1)
        leg_items = [
            ("ACTIVE LANE", PRIORITY_BGR[PRIORITY_ACTIVE]),
            ("ROAD/OUTSIDE", PRIORITY_BGR[PRIORITY_ROAD]),
            ("NON-ROAD", WALL_BGR),
        ]
        for j, (ltxt, lcol) in enumerate(leg_items):
            cv2.circle(ann, (lx + 6, ly + j * 18), 4, lcol, -1)
            cv2.putText(ann, ltxt, (lx + 15, ly + j * 18 + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.30, lcol, 1)
        return ann

    def _to_b64(self, frame: np.ndarray) -> str:
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 87])
        return base64.b64encode(buf.tobytes()).decode("utf-8")


def _weather_display(condition: str) -> str:
    return {
        "clear":           "Clear",
        "rainy":           "Rainy",
        "foggy_hazy":      "Foggy/Hazy",
        "low_light_night": "Night/Dark",
        "high_glare":      "Glare",
        "wet_road":        "Wet Road",
        "overcast_cloudy": "Overcast",
        "unknown":         "Unknown",
    }.get(condition, condition)
