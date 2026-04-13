"""
ROADAI Runtime Model Selector v3.4-fix
========================================
Manages runtime model assignments:
  • Defect detection runtime  → best.pt  (NEVER replaced by a benchmark candidate)
  • Object detection runtime  → yolov8n.pt

Key fixes:
  • No longer copies models into models/runtime/mymodel.pt stub
  • Uses direct paths from registry / env vars
  • Does not create placeholder files when real models exist
  • Reports honest status when models are missing
  • detect_model_path / object_model_path properties for DetectionEngine
"""
import os
import json
from pathlib import Path
from typing import Optional

from backend.core.model_registry import ModelRegistry, ModelEntry
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Legacy paths kept for backward compat with health endpoint
RUNTIME_META_PATH = Path("models/runtime/runtime_info.json")

# Env-configurable model paths (set by setup.sh / start.sh)
_DEFECT_MODEL_PATH = os.environ.get("DEFECT_MODEL_PATH", "models/custom/best.pt")
_OBJECT_MODEL_PATH = os.environ.get("OBJECT_MODEL_PATH", "models/candidates/yolov8n.pt")


def _is_real_model(path: Path) -> bool:
    try:
        if not path.exists():
            return False
        content = path.read_bytes()
        return not (content.startswith(b"ROADAI") or len(content) < 1024)
    except Exception:
        return False


class RuntimeModelSelector:
    def __init__(self, registry: ModelRegistry):
        self.registry = registry
        self._defect_path:  Optional[str] = None
        self._object_path:  Optional[str] = None
        self._defect_ready: bool = False
        self._object_ready: bool = False

    # ── Path resolution ───────────────────────────────────────────────────────

    @property
    def defect_model_path(self) -> Optional[str]:
        """Path to best.pt (pothole/crack detector). None if not available."""
        return self._defect_path if self._defect_ready else None

    @property
    def object_model_path(self) -> Optional[str]:
        """Path to yolov8n.pt (general object detector). None if not available."""
        return self._object_path if self._object_ready else None

    # ── Initialisation ────────────────────────────────────────────────────────

    def ensure_runtime_model(self):
        """
        Resolve and validate runtime model paths.
        Writes runtime_info.json for health endpoint backward compat.
        Does NOT create stub .pt files.
        """
        RUNTIME_META_PATH.parent.mkdir(parents=True, exist_ok=True)

        # ── Defect model (best.pt) ───────────────────────────────────────────
        self._resolve_defect_model()

        # ── Object detection model (yolov8n.pt) ─────────────────────────────
        self._resolve_object_model()

        # ── Write runtime_info.json (metadata only, no stub .pt) ────────────
        self._write_meta()

        # Log summary
        if self._defect_ready:
            logger.info(f"✅ Defect runtime  : best.pt   → {self._defect_path}")
        else:
            logger.warning("⚠️  Defect runtime  : best.pt MISSING – simulation mode for road defects")

        if self._object_ready:
            logger.info(f"✅ Object runtime  : yolov8n  → {self._object_path}")
        else:
            logger.warning("⚠️  Object runtime  : yolov8n.pt not found – will auto-download on demand")

    def _resolve_defect_model(self):
        """Locate best.pt from env var, registry, or known locations."""
        candidates = [
            Path(_DEFECT_MODEL_PATH),
            Path("models/custom/best.pt"),
            Path("models/best.pt"),
        ]
        # Also check registry
        reg_entry = self.registry.get_defect_runtime_entry()
        if reg_entry and reg_entry.path:
            candidates.insert(0, Path(reg_entry.path))

        for p in candidates:
            if _is_real_model(p):
                self._defect_path  = str(p)
                self._defect_ready = True
                return

        self._defect_path  = str(Path(_DEFECT_MODEL_PATH))  # store path even if missing
        self._defect_ready = False

    def _resolve_object_model(self):
        """Locate yolov8n.pt from env var, registry, or known locations."""
        candidates = [
            Path(_OBJECT_MODEL_PATH),
            Path("models/candidates/yolov8n.pt"),
        ]
        reg_entry = self.registry.get_object_runtime_entry()
        if reg_entry and reg_entry.path:
            candidates.insert(0, Path(reg_entry.path))

        for p in candidates:
            if _is_real_model(p):
                self._object_path  = str(p)
                self._object_ready = True
                return

        # yolov8n.pt can be auto-downloaded by ultralytics on first inference
        # so we allow this to be "not ready" without being a fatal error
        self._object_path  = str(Path(_OBJECT_MODEL_PATH))
        self._object_ready = False

    # ── Benchmark deployment ──────────────────────────────────────────────────

    def select_and_deploy_winner(self) -> dict:
        """
        Select the benchmark winner and mark it as the benchmark runtime in the registry.
        This does NOT change the defect model (best.pt stays as defect runtime).
        The winner is used only for benchmark comparison tracking.
        """
        winner = self.registry.get_benchmark_winner()
        if not winner:
            available = self.registry.get_available()
            if available:
                winner = available[0]
            else:
                return {"status": "no_models", "message": "No benchmarked models available"}

        # Allow virtual/reference models to be tracked as winners even if no physical file exists
        is_ref = getattr(winner, "source", "") == "reference" or winner.path == "reference_baseline"
        
        if not is_ref:
            if not winner.path or not Path(winner.path).exists():
                return {"status": "error", "message": f"Winner model path invalid: {winner.path}"}

        self.registry.set_runtime(winner.id)
        self._write_meta()

        result = {
            "status": "success",
            "benchmark_winner": winner.name,
            "winner_model_id": winner.id,
            "winner_path": winner.path,
            "composite_score": winner.composite_score,
            "note": "Benchmark winner tracked. Defect runtime (best.pt) and object runtime (yolov8n.pt) unchanged.",
        }
        logger.info(f"✅ Benchmark winner set: {winner.name} (score={winner.composite_score})")
        return result

    # ── Metadata / status ─────────────────────────────────────────────────────

    def _write_meta(self):
        winner = self.registry.get_benchmark_winner()
        meta = {
            "defect_runtime": {
                "model": "best.pt",
                "task": "road_defect_detection",
                "path": self._defect_path,
                "ready": self._defect_ready,
            },
            "object_runtime": {
                "model": "yolov8n.pt",
                "task": "general_object_detection",
                "path": self._object_path,
                "ready": self._object_ready,
            },
            "benchmark_winner": winner.name if winner else "none",
            "benchmark_winner_id": winner.id if winner else "none",
            "benchmark_winner_score": winner.composite_score if winner else 0.0,
            "note": (
                "best.pt is ALWAYS the pothole/crack detection runtime. "
                "yolov8n.pt is ALWAYS the object detection runtime. "
                "Benchmark winner is tracked separately."
            ),
        }
        try:
            RUNTIME_META_PATH.write_text(json.dumps(meta, indent=2))
        except Exception as e:
            logger.warning(f"Could not write runtime_info.json: {e}")

    def get_runtime_info(self) -> dict:
        if RUNTIME_META_PATH.exists():
            try:
                return json.loads(RUNTIME_META_PATH.read_text())
            except Exception:
                pass
        return {
            "defect_runtime": {
                "model": "best.pt",
                "task": "road_defect_detection",
                "path": self._defect_path,
                "ready": self._defect_ready,
            },
            "object_runtime": {
                "model": "yolov8n.pt",
                "task": "general_object_detection",
                "path": self._object_path,
                "ready": self._object_ready,
            },
            "benchmark_winner": "none",
        }

    def get_status_summary(self) -> dict:
        return {
            "defect_model_ready": self._defect_ready,
            "defect_model_path": self._defect_path,
            "object_model_ready": self._object_ready,
            "object_model_path": self._object_path,
            "simulation_mode": not (self._defect_ready or self._object_ready),
        }
