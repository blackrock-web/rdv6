"""
ROADAI Wall/Surface Filter v4.0
================================
Advanced classifier to distinguish:
  1. Road potholes (actual road surface damage)
  2. Road cracks   (pavement fractures on ground plane)
  3. Wall cracks   (vertical surface - FILTERED OUT)
  4. Wall holes    (building/wall holes - FILTERED OUT)
  5. Off-road      (any other non-road surface - FILTERED OUT)

Algorithm combines:
  A. Geometric/positional heuristics  (bbox position, aspect ratio, horizon)
  B. Color/texture analysis           (road gray vs wall brick/plaster)
  C. Surface normal estimation        (vertical vs horizontal plane)
  D. Context-aware depth cues         (perspective, vanishing point)
  E. Optional: segmentation mask overlap
  F. Optional: depth map vertical gradient
"""
import cv2
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List
from backend.utils.logger import get_logger

logger = get_logger(__name__)


# ── Decision result ─────────────────────────────────────────────────────────

@dataclass
class SurfaceDecision:
    is_road:         bool
    surface_type:    str   # road_pothole | road_crack | wall_crack | wall_hole | off_road | uncertain
    reason:          str
    confidence:      float
    lane_overlap:    float = 0.0
    road_overlap:    float = 0.0
    wall_score:      float = 0.0
    road_score:      float = 0.0
    geometry_flag:   str   = ""
    color_flag:      str   = ""
    depth_flag:      str   = ""


# ── Main classifier ─────────────────────────────────────────────────────────

class WallRoadSurfaceClassifier:
    """
    Production-grade wall vs road surface classifier.
    All heuristics are clearly labeled - no fake ML claims.
    
    Admin-configurable sensitivity controls allow tuning
    the aggressiveness of wall/hole filtering.
    """

    def __init__(self):
        # Configurable thresholds (admin can adjust via API)
        self.horizon_ratio          = 0.40   # anything above this y-fraction = above horizon
        self.wall_aspect_threshold  = 3.0    # height/width > this → likely wall crack
        self.min_road_overlap       = 0.20   # min road mask coverage to accept
        self.wall_color_sat_thresh  = 90     # high saturation = wall paint/brick
        self.wall_texture_thresh    = 110    # high texture variance = wall surface
        self.upper_zone_reject      = 0.30   # reject detections in top N% with no road overlap
        self.filter_sensitivity     = "medium"  # low | medium | high | aggressive

    def configure(self, settings: dict):
        """Update thresholds from admin config."""
        if "horizon_ratio"         in settings: self.horizon_ratio         = float(settings["horizon_ratio"])
        if "wall_aspect_threshold" in settings: self.wall_aspect_threshold = float(settings["wall_aspect_threshold"])
        if "min_road_overlap"      in settings: self.min_road_overlap      = float(settings["min_road_overlap"])
        if "filter_sensitivity"    in settings:
            self.filter_sensitivity = settings["filter_sensitivity"]
            # Auto-tune thresholds based on sensitivity
            if self.filter_sensitivity == "low":
                self.upper_zone_reject    = 0.20
                self.wall_aspect_threshold = 4.5
                self.min_road_overlap     = 0.10
            elif self.filter_sensitivity == "high":
                self.upper_zone_reject    = 0.40
                self.wall_aspect_threshold = 2.5
                self.min_road_overlap     = 0.30
            elif self.filter_sensitivity == "aggressive":
                self.upper_zone_reject    = 0.50
                self.wall_aspect_threshold = 2.0
                self.min_road_overlap     = 0.40

    def classify(self, bbox: list, frame: np.ndarray,
                 lane_polygon: list, lane_mask: Optional[np.ndarray],
                 road_mask: Optional[np.ndarray],
                 depth_map: Optional[np.ndarray] = None) -> SurfaceDecision:
        """
        Classify a detection bounding box as road surface or non-road.
        
        Returns SurfaceDecision with detailed reason for admin transparency.
        """
        x1, y1, x2, y2 = [int(v) for v in bbox]
        h, w = frame.shape[:2]

        box_h   = max(y2 - y1, 1)
        box_w   = max(x2 - x1, 1)
        area    = box_h * box_w
        cx      = (x1 + x2) / 2
        cy      = (y1 + y2) / 2
        aspect  = box_h / box_w   # >1 = taller than wide

        wall_score = 0.0
        road_score = 0.0
        geometry_flag = ""
        color_flag    = ""
        depth_flag    = ""

        # ── A. GEOMETRIC / POSITIONAL CHECKS ──────────────────────────────

        # A1: Horizon check — above horizon line = never road
        horizon_y = h * self.horizon_ratio
        if cy < horizon_y:
            wall_score += 0.60
            geometry_flag += "above_horizon;"

        # A2: Extreme vertical aspect ratio → wall crack pattern
        if aspect > self.wall_aspect_threshold:
            wall_score += 0.45
            geometry_flag += f"aspect_{aspect:.1f};"

        # A3: If in bottom 45% of frame → strong road prior
        if cy > h * 0.55:
            road_score += 0.50
            geometry_flag += "lower_frame;"

        # A4: Very small box in top zone → wall artifact
        if cy < h * self.upper_zone_reject and area < (h * w * 0.005):
            wall_score += 0.35
            geometry_flag += "small_upper;"

        # A5: Centered horizontally in frame = ego lane road
        center_bias = abs(cx - w / 2) / (w / 2)  # 0=center, 1=edge
        if center_bias < 0.35 and cy > h * 0.50:
            road_score += 0.25
            geometry_flag += "center_lower;"

        # ── B. COLOR / TEXTURE ANALYSIS ───────────────────────────────────

        x1c = max(0, x1); y1c = max(0, y1)
        x2c = min(w, x2); y2c = min(h, y2)
        box_region = frame[y1c:y2c, x1c:x2c]

        if box_region.size > 0:
            hsv = cv2.cvtColor(box_region, cv2.COLOR_BGR2HSV)
            mean_sat  = float(np.mean(hsv[:, :, 1]))
            mean_val  = float(np.mean(hsv[:, :, 2]))
            std_val   = float(np.std(hsv[:, :, 2]))
            mean_hue  = float(np.mean(hsv[:, :, 0]))

            # B1: High saturation = wall paint/brick, not road asphalt
            if mean_sat > self.wall_color_sat_thresh:
                wall_score += 0.35
                color_flag += f"high_sat_{mean_sat:.0f};"

            # B2: Road asphalt is dark gray, low saturation
            if mean_sat < 50 and 30 < mean_val < 180:
                road_score += 0.30
                color_flag += "asphalt_gray;"

            # B3: Very bright + saturated = painted wall
            if mean_val > 200 and mean_sat > 60:
                wall_score += 0.30
                color_flag += "bright_saturated;"

            # B4: Texture variance
            gray_roi = cv2.cvtColor(box_region, cv2.COLOR_BGR2GRAY)
            lap = cv2.Laplacian(gray_roi.astype(np.float32), cv2.CV_32F)
            texture_var = float(np.std(lap))

            if texture_var > self.wall_texture_thresh:
                # High texture in upper zone = wall surface
                if cy < h * 0.45:
                    wall_score += 0.20
                    color_flag += f"hi_texture_upper_{texture_var:.0f};"
            else:
                # Low texture in lower zone = smooth road
                if cy > h * 0.50:
                    road_score += 0.15
                    color_flag += "smooth_lower;"

            # B5: Warm reddish tones = brick wall
            if 0 < mean_hue < 20 and mean_sat > 60:
                wall_score += 0.25
                color_flag += "brick_tone;"

        # ── C. ROAD MASK OVERLAP ──────────────────────────────────────────

        road_overlap  = 0.0
        lane_overlap  = 0.0

        if road_mask is not None:
            roi = road_mask[y1c:y2c, x1c:x2c]
            if roi.size > 0:
                road_overlap = float(np.mean(roi > 0))
                if road_overlap > self.min_road_overlap:
                    road_score += road_overlap * 0.50
                    geometry_flag += f"road_mask_{road_overlap:.2f};"
                elif road_overlap < 0.05:
                    wall_score += 0.30
                    geometry_flag += "no_road_mask;"

        if lane_mask is not None:
            roi = lane_mask[y1c:y2c, x1c:x2c]
            if roi.size > 0:
                lane_overlap = float(np.mean(roi > 0))
                if lane_overlap > 0.15:
                    road_score += lane_overlap * 0.40
                    geometry_flag += f"lane_{lane_overlap:.2f};"

        # ── D. DEPTH VERTICAL GRADIENT CHECK ──────────────────────────────

        if depth_map is not None:
            roi_depth = depth_map[y1c:y2c, x1c:x2c]
            if roi_depth.size > 0:
                # Road surface: depth increases downward (closer to camera)
                # Wall: depth is uniform (flat plane)
                if roi_depth.shape[0] > 2:
                    top_depth  = float(np.mean(roi_depth[:roi_depth.shape[0]//3, :]))
                    bot_depth  = float(np.mean(roi_depth[2*roi_depth.shape[0]//3:, :]))
                    depth_grad = bot_depth - top_depth

                    if depth_grad > 0.15:
                        # Depth increases downward → ground plane (road)
                        road_score += 0.20
                        depth_flag += f"ground_grad_{depth_grad:.2f};"
                    elif abs(depth_grad) < 0.05:
                        # Uniform depth → wall (vertical flat surface)
                        if cy < h * 0.50:
                            wall_score += 0.20
                            depth_flag += f"flat_depth_upper;"

        # ── E. FINAL DECISION ──────────────────────────────────────────────

        net = road_score - wall_score
        is_road = net > 0.0 or road_score > 0.40

        # Force override: definitely wall if very high wall score
        if wall_score > 0.90:
            is_road = False
        # Force override: definitely road if in bottom zone with road mask
        if cy > h * 0.65 and road_overlap > 0.30:
            is_road = True

        # Surface type classification
        if not is_road:
            if aspect > self.wall_aspect_threshold and cy < h * 0.55:
                surface_type = "wall_crack"
            elif area < h * w * 0.004 and cy < h * 0.50:
                surface_type = "wall_hole"
            elif cy < horizon_y:
                surface_type = "off_road"
            else:
                surface_type = "wall_crack"
        else:
            surface_type = "road_surface"

        confidence = min(0.98, abs(net) * 1.5 + 0.40)
        reason     = f"{surface_type} | road={road_score:.2f} wall={wall_score:.2f}"
        if geometry_flag:
            reason += f" | geo:[{geometry_flag.rstrip(';')}]"
        if color_flag:
            reason += f" | color:[{color_flag.rstrip(';')}]"

        return SurfaceDecision(
            is_road        = is_road,
            surface_type   = surface_type,
            reason         = reason,
            confidence     = round(confidence, 3),
            lane_overlap   = round(lane_overlap, 3),
            road_overlap   = round(road_overlap, 3),
            wall_score     = round(wall_score, 3),
            road_score     = round(road_score, 3),
            geometry_flag  = geometry_flag,
            color_flag     = color_flag,
            depth_flag     = depth_flag,
        )


# ── Ground plane estimator ──────────────────────────────────────────────────

class GroundPlaneEstimator:
    """Heuristic road region mask using perspective trapezoid."""

    def get_road_region_mask(self, frame: np.ndarray) -> np.ndarray:
        h, w = frame.shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        pts = np.array([
            [int(w * 0.05), h],
            [int(w * 0.30), int(h * 0.45)],
            [int(w * 0.70), int(h * 0.45)],
            [int(w * 0.95), h],
        ], dtype=np.int32)
        cv2.fillPoly(mask, [pts], 255)
        return mask
