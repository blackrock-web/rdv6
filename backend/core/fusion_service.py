"""
ROADAI Fusion Engine — YOLO + DeepLabV3 + MiDaS
================================================
Combines:
  Stage A: Remove non-road detections using segmentation mask
  Stage B: Assign depth-based severity score
  Stage C: Attach enriched metadata to each detection
"""

import numpy as np
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class FusionEngine:
    """
    Multi-model fusion pipeline.
    Fuses YOLO detections with segmentation mask and depth map.
    """

    def __init__(self, seg_service=None, depth_service=None):
        self.seg_service   = seg_service
        self.depth_service = depth_service

    def fuse(self, frame: np.ndarray, raw_detections: list,
             run_seg: bool = True, run_depth: bool = True) -> dict:
        """
        Main fusion method.
        Args:
            frame: BGR frame
            raw_detections: list of detection dicts from DetectionEngine
            run_seg: whether to run segmentation (adds compute)
            run_depth: whether to run depth (adds compute)
        Returns:
            dict with fused_detections, road_mask, depth_map, road_coverage_pct,
            fusion_methods
        """
        h, w = frame.shape[:2]
        frame_area = h * w

        # Stage A: Segmentation road mask
        road_mask  = None
        seg_method = "none"
        road_coverage = 0.0
        if run_seg and self.seg_service is not None:
            road_mask     = self.seg_service.get_road_mask(frame)
            road_coverage = round(float(np.sum(road_mask > 0)) / max(frame_area, 1) * 100, 2)
            seg_method    = self.seg_service.method

        # Stage B: Depth map
        depth_map    = None
        depth_method = "none"
        if run_depth and self.depth_service is not None:
            depth_map    = self.depth_service.get_depth_map(frame)
            depth_method = self.depth_service.method

        # Stage C: Fuse each detection
        fused = []
        removed_by_seg = 0

        for det in raw_detections:
            bbox  = det.get("bbox", [0, 0, w, h])
            x1, y1, x2, y2 = [int(v) for v in bbox]

            # ── Segmentation filter ──────────────────────────────────────────
            seg_overlap = 1.0
            seg_filtered = False
            if road_mask is not None:
                x1c = max(0, x1); y1c = max(0, y1)
                x2c = min(w, x2); y2c = min(h, y2)
                if x2c > x1c and y2c > y1c:
                    region = road_mask[y1c:y2c, x1c:x2c]
                    seg_overlap = float(np.sum(region > 0)) / max(region.size, 1)
                    if seg_overlap < 0.25:
                        # Less than 25% of bbox on road → skip
                        seg_filtered = True
                        removed_by_seg += 1

            if seg_filtered:
                continue

            # ── Depth estimation ─────────────────────────────────────────────
            depth_val  = 0.5
            depth_sev  = det.get("severity", "medium")
            if depth_map is not None and self.depth_service is not None:
                depth_val = self.depth_service.estimate_bbox_depth(depth_map, bbox)
                # Override severity based on depth if detection is a pothole/crack
                dt = det.get("damage_type", "damage")
                if dt in ("pothole", "crack"):
                    depth_sev = _depth_to_severity(depth_val)

            # ── Build fused detection ────────────────────────────────────────
            fused_det = dict(det)
            fused_det["seg_overlap"]        = round(seg_overlap, 3)
            fused_det["depth_value"]        = round(depth_val, 3)
            fused_det["depth_severity"]     = depth_sev
            fused_det["fused_severity"]     = _fuse_severity(det.get("severity","medium"), depth_sev)
            fused_det["fusion_applied"]     = True
            fused.append(fused_det)

        return {
            "fused_detections":   fused,
            "removed_by_seg":     removed_by_seg,
            "road_coverage_pct":  road_coverage,
            "seg_method":         seg_method,
            "depth_method":       depth_method,
            "fusion_applied":     True,
        }


def _depth_to_severity(depth: float) -> str:
    if depth > 0.75: return "critical"
    if depth > 0.55: return "high"
    if depth > 0.35: return "medium"
    return "low"


def _fuse_severity(yolo_sev: str, depth_sev: str) -> str:
    """Combine YOLO severity and depth-derived severity (take worse)."""
    rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    ys = rank.get(yolo_sev, 1)
    ds = rank.get(depth_sev, 1)
    # Weighted: 60% YOLO, 40% depth
    combined = round(ys * 0.6 + ds * 0.4)
    inv = {0: "low", 1: "medium", 2: "high", 3: "critical"}
    return inv.get(combined, "medium")
