"""
ROADAI Preprocessing Service v3.5
===================================
Scene-condition estimator + adaptive preprocessing pipeline.

Conditions detected:
  normal_daylight | low_light | glare | rainy_wet | hazy_foggy |
  shadow_heavy | overcast

Preprocessing modes (applied in detection pipeline):
  auto | none | clahe | gamma | dehaze | low-light | denoise

All methods are honest CV operations — no AI-based dehazing.
"""
import cv2
import numpy as np
from typing import Optional, Tuple
from dataclasses import dataclass, field

from backend.utils.logger import get_logger

logger = get_logger(__name__)

# ── Scene condition detection ─────────────────────────────────

def _frame_stats(frame: np.ndarray) -> dict:
    """Compute brightness, contrast, saturation stats from a frame."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
    hsv  = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)  if len(frame.shape) == 3 else None

    mean_v   = float(np.mean(gray))
    std_v    = float(np.std(gray))
    p95      = float(np.percentile(gray, 95))
    p5       = float(np.percentile(gray, 5))
    sat_mean = float(np.mean(hsv[:, :, 1])) if hsv is not None else 0.0

    return {
        "mean_brightness": mean_v,
        "contrast_std":    std_v,
        "p95_brightness":  p95,
        "p5_brightness":   p5,
        "saturation_mean": sat_mean,
        "dark_ratio":      float(np.mean(gray < 50)),
        "bright_ratio":    float(np.mean(gray > 220)),
    }


def detect_scene_condition(frame: np.ndarray) -> Tuple[str, dict]:
    """
    Returns (condition_label, stats_dict).
    Conditions: normal_daylight | low_light | glare | rainy_wet |
                hazy_foggy | shadow_heavy | overcast
    """
    s = _frame_stats(frame)
    mb = s["mean_brightness"]
    cs = s["contrast_std"]
    p95 = s["p95_brightness"]
    p5  = s["p5_brightness"]
    sat = s["saturation_mean"]
    dr  = s["dark_ratio"]
    br  = s["bright_ratio"]

    if mb < 45 and dr > 0.35:
        condition = "low_light"
    elif br > 0.25 and p95 > 240 and cs < 45:
        condition = "glare"
    elif mb > 160 and cs < 35 and sat < 30:
        condition = "hazy_foggy"
    elif mb > 100 and cs < 40 and sat < 40 and p5 > 60:
        condition = "overcast"
    elif sat < 35 and mb > 80 and cs < 50:
        condition = "rainy_wet"
    elif dr > 0.20 and cs > 60 and mb > 60:
        condition = "shadow_heavy"
    else:
        condition = "normal_daylight"

    return condition, s


def condition_to_mode(condition: str) -> str:
    """Map detected scene condition to preprocessing mode."""
    mapping = {
        "normal_daylight": "none",
        "low_light":       "low-light",
        "glare":           "clahe",
        "rainy_wet":       "clahe",
        "hazy_foggy":      "dehaze",
        "overcast":        "clahe",
        "shadow_heavy":    "gamma",
    }
    return mapping.get(condition, "none")


# ── Preprocessing functions ────────────────────────────────────

def apply_clahe(frame: np.ndarray) -> np.ndarray:
    """CLAHE on L-channel of LAB color space."""
    lab  = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    l_eq  = clahe.apply(l)
    merged = cv2.merge([l_eq, a, b])
    return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)


def apply_gamma(frame: np.ndarray, gamma: float = 1.5) -> np.ndarray:
    """Gamma correction."""
    inv_gamma = 1.0 / gamma
    table = np.array([(i / 255.0) ** inv_gamma * 255 for i in range(256)], dtype=np.uint8)
    return cv2.LUT(frame, table)


def apply_dehaze(frame: np.ndarray) -> np.ndarray:
    """
    Dark channel prior-inspired haze reduction (simplified CV implementation).
    NOT deep-learning dehazing — clearly labeled as heuristic.
    """
    # Dark channel
    min_ch  = np.min(frame, axis=2)
    kernel  = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    dark_ch = cv2.erode(min_ch, kernel)

    # Estimate atmospheric light from top-1% brightest dark channel pixels
    num_px  = max(1, dark_ch.size // 100)
    flat_dc = dark_ch.flatten()
    indices = np.argpartition(flat_dc, -num_px)[-num_px:]
    atm     = np.max(frame.reshape(-1, 3)[np.unravel_index(indices, dark_ch.shape)[0]], axis=0)
    atm     = atm.astype(np.float32)

    # Transmission map
    norm = (frame.astype(np.float32) / (atm + 1e-6)).clip(0, 1)
    t    = 1 - 0.85 * np.min(norm, axis=2)
    t    = np.clip(t, 0.1, 1.0)

    # Recover scene radiance
    t3   = t[:, :, np.newaxis]
    atm3 = atm[np.newaxis, np.newaxis, :]
    rec  = ((frame.astype(np.float32) - atm3) / t3 + atm3).clip(0, 255).astype(np.uint8)

    # Blend 70% dehazed + 30% original to avoid over-processing
    return cv2.addWeighted(rec, 0.7, frame, 0.3, 0)


def apply_low_light(frame: np.ndarray) -> np.ndarray:
    """Retinex-inspired low-light enhancement."""
    # CLAHE first for global contrast
    enhanced = apply_clahe(frame)
    # Then gamma to lift shadows
    enhanced = apply_gamma(enhanced, gamma=1.6)
    # Mild denoising to suppress noise amplification
    enhanced = cv2.fastNlMeansDenoisingColored(enhanced, None, 6, 6, 7, 21)
    return enhanced


def apply_denoise(frame: np.ndarray) -> np.ndarray:
    return cv2.fastNlMeansDenoisingColored(frame, None, 8, 8, 7, 21)


def apply_gamma_shadow(frame: np.ndarray) -> np.ndarray:
    """Mild gamma lift for shadow-heavy scenes."""
    enhanced = apply_gamma(frame, gamma=1.3)
    return apply_clahe(enhanced)


# ── Main preprocess entry point ────────────────────────────────

@dataclass
class PreprocessResult:
    frame: np.ndarray
    condition: str
    mode_applied: str
    mode_source: str    # "auto" | "manual"
    steps: list = field(default_factory=list)
    conf_threshold_adj: float = 0.0


def preprocess_frame(
    frame: np.ndarray,
    mode: str = "auto",
) -> PreprocessResult:
    """
    Apply scene-aware preprocessing to a frame.

    mode:
      "auto"      — detect condition and pick mode automatically
      "none"      — pass through unchanged
      "clahe"     — CLAHE histogram equalization
      "gamma"     — gamma correction
      "dehaze"    — dark channel prior dehazing (heuristic)
      "low-light" — Retinex-inspired low-light enhance
      "denoise"   — NLM denoising
    """
    if frame is None or frame.size == 0:
        return PreprocessResult(frame=frame, condition="unknown", mode_applied="none", mode_source="error")

    condition  = "unknown"
    mode_source = "manual"
    effective_mode = mode

    if mode == "auto":
        condition, _ = detect_scene_condition(frame)
        effective_mode = condition_to_mode(condition)
        mode_source = "auto"
    elif mode == "none":
        return PreprocessResult(
            frame=frame, condition="unknown", mode_applied="none", mode_source="manual",
            steps=["passthrough"], conf_threshold_adj=0.0,
        )

    if effective_mode == "none":
        processed = frame
        steps = ["passthrough"]
    elif effective_mode == "clahe":
        processed = apply_clahe(frame)
        steps = ["clahe_lab"]
    elif effective_mode == "gamma":
        processed = apply_gamma_shadow(frame)
        steps = ["gamma_1.3", "clahe_lab"]
    elif effective_mode == "dehaze":
        processed = apply_dehaze(frame)
        steps = ["dark_channel_prior_dehaze (heuristic)"]
    elif effective_mode == "low-light":
        processed = apply_low_light(frame)
        steps = ["clahe_lab", "gamma_1.6", "nlm_denoise"]
    elif effective_mode == "denoise":
        processed = apply_denoise(frame)
        steps = ["nlm_denoise"]
    else:
        processed = frame
        steps = ["passthrough"]

    # Confidence threshold adjustment (lower threshold in harder conditions)
    adj = {
        "low_light":    -0.05,
        "hazy_foggy":   -0.08,
        "rainy_wet":    -0.05,
        "shadow_heavy": -0.03,
        "glare":        -0.04,
        "overcast":     -0.02,
        "normal_daylight": 0.0,
    }.get(condition, 0.0)

    return PreprocessResult(
        frame=processed,
        condition=condition,
        mode_applied=effective_mode,
        mode_source=mode_source,
        steps=steps,
        conf_threshold_adj=adj,
    )


# ── Person / face safety suppression ──────────────────────────

def suppress_person_detections(
    damage_detections: list,
    object_detections: list,
    iou_threshold: float = 0.2,
) -> Tuple[list, int]:
    """
    Remove road-damage detections that significantly overlap person bounding boxes.
    Returns (filtered_detections, suppressed_count).
    
    This is a heuristic bbox overlap check — not recognition.
    """
    person_boxes = [
        d["bbox"] for d in object_detections
        if d.get("class", "").lower() in ("person", "pedestrian")
    ]
    if not person_boxes:
        return damage_detections, 0

    filtered  = []
    suppressed = 0
    for det in damage_detections:
        bbox = det.get("bbox", [0, 0, 0, 0])
        if _overlaps_any(bbox, person_boxes, iou_threshold):
            suppressed += 1
            logger.debug(f"Suppressed damage detection overlapping person region: {bbox}")
        else:
            filtered.append(det)

    if suppressed:
        logger.info(f"Person suppression: {suppressed} road-damage detection(s) suppressed (person overlap).")
    return filtered, suppressed


def _overlaps_any(bbox: list, person_boxes: list, threshold: float) -> bool:
    for pb in person_boxes:
        if _iou(bbox, pb) >= threshold:
            return True
    return False


def _iou(a: list, b: list) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1); iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2); iy2 = min(ay2, by2)
    iw = max(0, ix2 - ix1); ih = max(0, iy2 - iy1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    a_area = max(1, (ax2 - ax1) * (ay2 - ay1))
    b_area = max(1, (bx2 - bx1) * (by2 - by1))
    return inter / (a_area + b_area - inter)


def blur_faces_in_frame(frame: np.ndarray) -> Tuple[np.ndarray, int]:
    """
    Detect and blur face-like regions using Haar cascade.
    NOT production face recognition — clearly labeled as heuristic.
    Returns (blurred_frame, face_count).
    """
    try:
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        gray   = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces  = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        result = frame.copy()
        for (x, y, w, h) in faces:
            roi = result[y:y+h, x:x+w]
            result[y:y+h, x:x+w] = cv2.GaussianBlur(roi, (51, 51), 30)
        if len(faces):
            logger.debug(f"Face blur: {len(faces)} face(s) blurred (Haar cascade heuristic)")
        return result, len(faces)
    except Exception as e:
        logger.warning(f"Face blur failed: {e}")
        return frame, 0
