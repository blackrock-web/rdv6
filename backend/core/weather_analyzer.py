"""
Weather/scene condition analyzer using image statistics.
Heuristic-based — no external model required.
"""
import cv2
import numpy as np
from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class WeatherResult:
    condition: str = "unknown"
    confidence: float = 0.5
    condition_scores: dict = field(default_factory=dict)
    conf_threshold_adjustment: float = 0.0
    note: str = ""


class WeatherAnalyzer:
    """
    Classifies scene conditions from image statistics.
    Labels: clear | rainy | foggy_hazy | low_light_night | high_glare | wet_road | overcast_cloudy
    """

    def classify(self, frame: np.ndarray) -> WeatherResult:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        hsv  = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        mean_val  = float(np.mean(gray))
        std_val   = float(np.std(gray))
        mean_sat  = float(np.mean(hsv[:,:,1]))
        mean_hue  = float(np.mean(hsv[:,:,0]))

        scores = {}

        # Night / low light
        scores["low_light_night"] = max(0, 1.0 - mean_val / 60) if mean_val < 60 else 0.0

        # High glare
        bright_pct = float(np.mean(gray > 220))
        scores["high_glare"] = min(1.0, bright_pct * 4) if bright_pct > 0.15 else 0.0

        # Foggy / hazy: low std, mid brightness, low saturation
        if 80 < mean_val < 190 and std_val < 45 and mean_sat < 40:
            scores["foggy_hazy"] = 0.7
        else:
            scores["foggy_hazy"] = 0.0

        # Rainy: dark, low saturation, moderate std
        if mean_val < 100 and mean_sat < 50 and std_val > 25:
            scores["rainy"] = 0.6
        else:
            scores["rainy"] = 0.0

        # Wet road: bluish tones, moderate brightness
        if mean_hue > 90 and mean_val > 80:
            scores["wet_road"] = 0.5
        else:
            scores["wet_road"] = 0.0

        # Overcast: mid brightness, low saturation, medium std
        if 90 < mean_val < 160 and mean_sat < 55 and std_val < 55:
            scores["overcast_cloudy"] = 0.55
        else:
            scores["overcast_cloudy"] = 0.0

        # Clear: high brightness, decent std, decent saturation
        if mean_val > 120 and std_val > 40 and mean_sat > 40:
            scores["clear"] = 0.8
        else:
            scores["clear"] = max(0, (mean_val - 80) / 200)

        # Pick winner
        condition = max(scores, key=scores.get)
        confidence = scores[condition]

        # Confidence threshold adjustment
        adj = 0.0
        if condition in ("foggy_hazy", "rainy", "low_light_night"):
            adj = -0.10  # lower threshold — detect more in bad conditions
        elif condition == "high_glare":
            adj = 0.05

        note = ""
        if condition == "low_light_night":
            note = "Low-light conditions detected — confidence threshold reduced for better recall."
        elif condition == "high_glare":
            note = "High glare detected — some detections may be suppressed."

        return WeatherResult(
            condition=condition,
            confidence=round(confidence, 3),
            condition_scores={k: round(v, 3) for k, v in scores.items()},
            conf_threshold_adjustment=adj,
            note=note,
        )

    def preprocess(self, frame: np.ndarray, condition: str) -> Tuple[np.ndarray, List[str]]:
        """Apply condition-specific preprocessing."""
        result = frame.copy()
        steps = []

        if condition == "low_light_night":
            result = cv2.convertScaleAbs(result, alpha=1.5, beta=30)
            steps.append("brightness_boost")

        elif condition == "foggy_hazy":
            result = cv2.convertScaleAbs(result, alpha=1.3, beta=10)
            result = cv2.detailEnhance(result, sigma_s=10, sigma_r=0.15)
            steps.append("dehaze_enhance")

        elif condition == "rainy":
            kernel = np.ones((3, 3), np.float32) / 9
            result = cv2.filter2D(result, -1, kernel)
            result = cv2.convertScaleAbs(result, alpha=1.2, beta=15)
            steps.append("denoise_brighten")

        elif condition == "high_glare":
            result = cv2.convertScaleAbs(result, alpha=0.85, beta=-10)
            steps.append("glare_reduce")

        return result, steps
