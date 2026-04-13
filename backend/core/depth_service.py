"""
ROADAI Depth Service — MiDaS Depth Estimation
=============================================
Loads MiDaS_small or DPT via torch.hub.
Used to estimate pothole depth and improve RUL prediction.

HONEST STATUS:
  When PyTorch available: Real MiDaS inference.
  When not available: Heuristic depth proxy from edge analysis.
"""

import numpy as np
import cv2
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class DepthService:
    """Real MiDaS depth estimation with honest CV fallback."""

    def __init__(self):
        self.model        = None
        self.transform    = None
        self.loaded       = False
        self.use_gpu      = False
        self.method       = "not_loaded"
        self._try_load()

    def _try_load(self):
        try:
            import torch

            self.use_gpu = torch.cuda.is_available()
            device_str   = "cuda" if self.use_gpu else "cpu"
            self.device  = torch.device(device_str)

            logger.info(f"Loading MiDaS on {device_str}...")
            # Try DPT_Small first (lightweight), fallback to MiDaS_small
            try:
                self.model = torch.hub.load(
                    "intel-isl/MiDaS", "MiDaS_small",
                    trust_repo=True, force_reload=False
                )
                transforms_hub = torch.hub.load(
                    "intel-isl/MiDaS", "transforms",
                    trust_repo=True, force_reload=False
                )
                self.transform = transforms_hub.small_transform
                model_name = "MiDaS_small"
            except Exception:
                self.model = torch.hub.load(
                    "intel-isl/MiDaS", "DPT_Hybrid",
                    trust_repo=True, force_reload=False
                )
                transforms_hub = torch.hub.load(
                    "intel-isl/MiDaS", "transforms",
                    trust_repo=True, force_reload=False
                )
                self.transform = transforms_hub.dpt_transform
                model_name = "DPT_Hybrid"

            self.model = self.model.to(self.device).eval()
            self.loaded = True
            self.method = f"{model_name} ({device_str.upper()})"
            logger.info(f"✅ Depth service loaded: {self.method}")

        except ImportError:
            logger.warning("PyTorch not available — using CV heuristic depth")
            self.loaded = False
            self.method = "CV Heuristic (torch not installed)"
        except Exception as e:
            logger.warning(f"MiDaS load failed ({e}) — using CV heuristic depth")
            self.loaded = False
            self.method = f"CV Heuristic (MiDaS load error)"

    def get_depth_map(self, frame: np.ndarray) -> np.ndarray:
        """
        Returns normalized depth map (float32, 0.0-1.0) same size as frame.
        1.0 = closest/deepest; 0.0 = flat/far.
        """
        if self.loaded and self.model is not None:
            return self._midas_depth(frame)
        return self._cv_depth(frame)

    def _midas_depth(self, frame: np.ndarray) -> np.ndarray:
        """Real MiDaS depth inference."""
        try:
            import torch

            h, w = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            inp = self.transform(rgb).to(self.device)

            with torch.no_grad():
                pred = self.model(inp)
                pred = torch.nn.functional.interpolate(
                    pred.unsqueeze(1),
                    size=(h, w),
                    mode="bicubic",
                    align_corners=False,
                ).squeeze()

            depth = pred.cpu().numpy().astype(np.float32)
            # Normalize to 0-1
            dmin, dmax = depth.min(), depth.max()
            if dmax > dmin:
                depth = (depth - dmin) / (dmax - dmin)
            return depth

        except Exception as e:
            logger.warning(f"MiDaS inference error: {e}")
            return self._cv_depth(frame)

    def _cv_depth(self, frame: np.ndarray) -> np.ndarray:
        """
        CV heuristic depth proxy.
        LABELED AS HEURISTIC — not real metric depth.
        High edge density + dark regions → deeper (proxy for potholes).
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Laplacian as texture-depth proxy
        lap = cv2.Laplacian(gray.astype(np.float32), cv2.CV_32F)
        lap_abs = np.abs(lap)

        # Darkness as depth proxy (darker = potentially deeper)
        darkness = (255.0 - gray.astype(np.float32)) / 255.0

        combined = 0.6 * lap_abs / max(lap_abs.max(), 1.0) + 0.4 * darkness

        # Smooth
        depth = cv2.GaussianBlur(combined.astype(np.float32), (15, 15), 0)

        # Normalize
        dmin, dmax = depth.min(), depth.max()
        if dmax > dmin:
            depth = (depth - dmin) / (dmax - dmin)
        return depth.astype(np.float32)

    def estimate_bbox_depth(self, depth_map: np.ndarray, bbox: list) -> float:
        """
        Estimate mean depth value for a detection bounding box.
        Returns 0.0-1.0 (1.0 = deepest/closest).
        """
        if depth_map is None:
            return 0.5
        x1, y1, x2, y2 = [int(v) for v in bbox]
        h, w = depth_map.shape[:2]
        x1 = max(0, x1); y1 = max(0, y1)
        x2 = min(w, x2); y2 = min(h, y2)
        if x2 <= x1 or y2 <= y1:
            return 0.5
        region = depth_map[y1:y2, x1:x2]
        return float(np.mean(region)) if region.size > 0 else 0.5

    @property
    def status(self) -> dict:
        return {
            "loaded": self.loaded,
            "method": self.method,
            "use_gpu": self.use_gpu,
        }
