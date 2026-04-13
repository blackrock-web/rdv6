"""
Lane mask, road surface classifier, and ground plane estimator.
These are heuristic/geometry-based modules (no deep learning required).
"""
import cv2
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SurfaceDecision:
    is_road: bool
    reason: str
    confidence: float
    lane_overlap: float = 0.0


class RoadSurfaceClassifier:
    """Classifies whether a bounding box is on the road surface vs wall/building."""

    def classify(self, bbox, frame, lane_polygon, lane_mask, road_mask) -> SurfaceDecision:
        x1, y1, x2, y2 = [int(v) for v in bbox]
        h, w = frame.shape[:2]

        # Above-horizon check: if box is in top 30% and thin vertically → likely wall
        box_h = y2 - y1
        box_w = x2 - x1
        center_y = (y1 + y2) / 2

        if center_y < h * 0.35 and box_h > box_w * 2:
            return SurfaceDecision(False, "above_horizon – tall narrow object", 0.85)

        # Aspect ratio check: very tall narrow boxes → likely wall crack
        aspect = box_h / max(box_w, 1)
        if aspect > 4.0 and center_y < h * 0.5:
            return SurfaceDecision(False, "geometry – extreme aspect ratio vertical", 0.80)

        # Road mask overlap
        road_overlap = 0.0
        if road_mask is not None:
            roi = road_mask[max(0,y1):min(h,y2), max(0,x1):min(w,x2)]
            if roi.size > 0:
                road_overlap = float(np.mean(roi > 0))

        # Lane overlap
        lane_overlap = 0.0
        if lane_mask is not None:
            roi = lane_mask[max(0,y1):min(h,y2), max(0,x1):min(w,x2)]
            if roi.size > 0:
                lane_overlap = float(np.mean(roi > 0))

        # Color check: road damage tends to be dark/gray
        box_region = frame[max(0,y1):min(h,y2), max(0,x1):min(w,x2)]
        if box_region.size > 0:
            hsv = cv2.cvtColor(box_region, cv2.COLOR_BGR2HSV)
            mean_sat = float(np.mean(hsv[:,:,1]))
            mean_val = float(np.mean(hsv[:,:,2]))
            # Highly saturated + bright → likely not road damage
            if mean_sat > 120 and mean_val > 180:
                return SurfaceDecision(False, "color – high saturation non-road surface", 0.72)

        # Default: if in lower road region, likely road
        if center_y > h * 0.35:
            return SurfaceDecision(True, "accepted", 0.85, lane_overlap)

        if road_overlap > 0.3 or lane_overlap > 0.2:
            return SurfaceDecision(True, "accepted", 0.80, lane_overlap)

        return SurfaceDecision(False, "rejected_other – uncertain region", 0.60, lane_overlap)


class GroundPlaneEstimator:
    """Estimates the road region mask using perspective geometry."""

    def get_road_region_mask(self, frame: np.ndarray) -> np.ndarray:
        h, w = frame.shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        # Expanded trapezoidal road region (PRD v4.1 Enhanced Horizon)
        pts = np.array([
            [int(w * 0.0), h],
            [int(w * 0.35), int(h * 0.25)],
            [int(w * 0.65), int(h * 0.25)],
            [int(w * 1.0), h],
        ], dtype=np.int32)
        cv2.fillPoly(mask, [pts], 255)
        return mask


class LaneMaskGenerator:
    """Generates a lane mask using Hough lines."""

    def generate(self, frame: np.ndarray):
        h, w = frame.shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        # Default center lane region
        pts = np.array([
            [int(w * 0.2), h],
            [int(w * 0.4), int(h * 0.55)],
            [int(w * 0.6), int(h * 0.55)],
            [int(w * 0.8), h],
        ], dtype=np.int32)
        cv2.fillPoly(mask, [pts], 255)
        return mask
