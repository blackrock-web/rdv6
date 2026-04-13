"""
Road type and active lane analyzer.
Determines which detections are in the active (ego) lane vs road vs off-road.
"""
import cv2
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

PRIORITY_ACTIVE  = "in_active_lane"
PRIORITY_ROAD    = "on_road_outside_lane"
PRIORITY_OFFROAD = "off_road_low_relevance"

ROAD_UNKNOWN = "unknown"
ROAD_HIGHWAY = "highway"
ROAD_URBAN   = "urban"
ROAD_RURAL   = "rural"


@dataclass
class LaneAnalysis:
    detected: bool = False
    lane_polygon: list = field(default_factory=list)
    lane_mask: Optional[np.ndarray] = None
    lane_confidence: str = "none"
    marking_quality: str = "unknown"
    curve_detected: bool = False
    curve_direction: str = ""
    fallback_active: bool = False
    fallback_reason: str = ""
    road_type: str = ROAD_UNKNOWN


@dataclass
class DamagePriority:
    priority: str = PRIORITY_ROAD
    priority_label: str = "Road (Outside Lane)"
    lane_overlap: float = 0.0
    road_overlap: float = 0.0


class ActiveLaneAnalyzer:
    """
    Detects the active (ego vehicle) lane using Hough line transform.
    Falls back to a geometric trapezoid if no clear lane is found.
    """

    def analyze(self, frame: np.ndarray) -> LaneAnalysis:
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 50, 150)

        # Region of interest: lower 55% of frame
        # Expanded lane ROI (PRD v4.1 Enhanced Depth)
        roi_pts = np.array([[
            (0, h),
            (int(w * 0.20), int(h * 0.30)),
            (int(w * 0.80), int(h * 0.30)),
            (w, h),
        ]], dtype=np.int32)
        roi_mask = np.zeros((h, w), dtype=np.uint8)
        cv2.fillPoly(roi_mask, roi_pts, 255)
        masked_edges = cv2.bitwise_and(edges, roi_mask)

        lines = cv2.HoughLinesP(
            masked_edges, rho=1, theta=np.pi/180,
            threshold=30, minLineLength=60, maxLineGap=80
        )

        left_lines, right_lines = [], []
        if lines is not None:
            for line in lines:
                x1, y1, x2, y2 = line[0]
                if x2 == x1:
                    continue
                slope = (y2 - y1) / (x2 - x1)
                if abs(slope) < 0.3:
                    continue
                if slope < 0 and x1 < w * 0.55:
                    left_lines.append(line[0])
                elif slope > 0 and x1 > w * 0.45:
                    right_lines.append(line[0])

        def average_line(lines_list):
            if not lines_list:
                return None
            xs, ys = [], []
            for x1, y1, x2, y2 in lines_list:
                xs.extend([x1, x2]); ys.extend([y1, y2])
            if len(xs) < 2:
                return None
            slope, intercept = np.polyfit(xs, ys, 1)
            return slope, intercept

        def line_to_coords(slope_intercept, y_start, y_end):
            if slope_intercept is None:
                return None
            slope, intercept = slope_intercept
            if abs(slope) < 1e-6:
                return None
            x1 = int((y_start - intercept) / slope)
            x2 = int((y_end - intercept) / slope)
            return x1, y_start, x2, y_end

        y_bottom = h
        y_top    = int(h * 0.35)

        left_avg  = average_line(left_lines)
        right_avg = average_line(right_lines)

        left_coords  = line_to_coords(left_avg,  y_bottom, y_top)
        right_coords = line_to_coords(right_avg, y_bottom, y_top)

        if left_coords and right_coords:
            lx1, ly1, lx2, ly2 = left_coords
            rx1, ry1, rx2, ry2 = right_coords
            polygon = [(lx1, ly1), (lx2, ly2), (rx2, ry2), (rx1, ry1)]
            confidence = "strong"
            fallback = False
            fallback_reason = ""
        elif left_coords or right_coords:
            # One lane line — use fallback for the other side
            coords = left_coords or right_coords
            cx1, cy1, cx2, cy2 = coords
            if left_coords:
                polygon = [(cx1, cy1), (cx2, cy2),
                           (int(w * 0.6), y_top), (int(w * 0.8), y_bottom)]
            else:
                polygon = [(int(w * 0.2), y_bottom), (int(w * 0.4), y_top),
                           (cx2, cy2), (cx1, cy1)]
            confidence = "weak"
            fallback = True
            fallback_reason = "single_lane_line_detected"
        else:
            # No lane markings found — return empty result, draw nothing
            return LaneAnalysis(
                detected=False,
                lane_polygon=[],
                lane_mask=np.zeros((h, w), dtype=np.uint8),
                lane_confidence="none",
                marking_quality="absent",
                curve_detected=False,
                curve_direction="",
                fallback_active=True,
                fallback_reason="no_lane_markings_detected",
                road_type=ROAD_UNKNOWN,
            )

        # Build lane mask
        lane_mask = np.zeros((h, w), dtype=np.uint8)
        poly_np = np.array(polygon, dtype=np.int32)
        cv2.fillPoly(lane_mask, [poly_np], 255)

        # Detect curve
        curve_detected = False
        curve_direction = ""
        if left_coords and right_coords:
            lx1, _, lx2, _ = left_coords
            rx1, _, rx2, _ = right_coords
            left_drift  = lx1 - lx2
            right_drift = rx1 - rx2
            avg_drift = (left_drift + right_drift) / 2
            if abs(avg_drift) > 40:
                curve_detected = True
                curve_direction = "left" if avg_drift > 0 else "right"

        # Road type heuristic
        road_type = ROAD_UNKNOWN
        if confidence == "strong":
            road_type = ROAD_URBAN if w > 1000 else ROAD_RURAL

        return LaneAnalysis(
            detected=confidence != "none",
            lane_polygon=polygon,
            lane_mask=lane_mask,
            lane_confidence=confidence,
            marking_quality="clear" if confidence == "strong" else "faded" if confidence == "weak" else "absent",
            curve_detected=curve_detected,
            curve_direction=curve_direction,
            fallback_active=fallback,
            fallback_reason=fallback_reason,
            road_type=road_type,
        )

    def prioritize_detection(self, bbox, lane_analysis: LaneAnalysis,
                             road_mask, frame_shape) -> DamagePriority:
        h, w = frame_shape[:2]
        x1, y1, x2, y2 = [int(v) for v in bbox]

        # Lane overlap
        lane_overlap = 0.0
        if lane_analysis.lane_mask is not None:
            roi = lane_analysis.lane_mask[max(0,y1):min(h,y2), max(0,x1):min(w,x2)]
            if roi.size > 0:
                lane_overlap = float(np.mean(roi > 0))

        # Road overlap
        road_overlap = 0.0
        if road_mask is not None:
            roi = road_mask[max(0,y1):min(h,y2), max(0,x1):min(w,x2)]
            if roi.size > 0:
                road_overlap = float(np.mean(roi > 0))

        if lane_overlap > 0.3:
            priority = PRIORITY_ACTIVE
            label    = "In Active Lane"
        elif road_overlap > 0.2 or (y1 + y2) / 2 > h * 0.5:
            priority = PRIORITY_ROAD
            label    = "Road (Outside Lane)"
        else:
            priority = PRIORITY_OFFROAD
            label    = "Off-Road / Non-Road"

        return DamagePriority(
            priority=priority,
            priority_label=label,
            lane_overlap=round(lane_overlap, 3),
            road_overlap=round(road_overlap, 3),
        )
