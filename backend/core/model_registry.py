"""
ROADAI Model Registry v3.4-fix
================================
Tracks all candidate, custom, and runtime models.

Task separation enforced:
  • best.pt  → task=road_defect  (pothole/crack detection runtime)
  • yolov8n  → task=object       (general object detection runtime)
  • candidate models → task=benchmark_candidate (COCO-based, general detection)

The registry clearly distinguishes:
  - DEFECT_RUNTIME : the model used for road damage detection (best.pt)
  - OBJECT_RUNTIME : the model used for general object detection (yolov8n.pt)
  - BENCHMARK      : models available for benchmarking comparison
"""
import os
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, asdict, field

from backend.utils.logger import get_logger

logger = get_logger(__name__)

REGISTRY_PATH = Path("config/model_registry.json")
MODELS_DIR    = Path("models")

# ── Runtime model paths (env-overridable) ────────────────────────────────────
DEFECT_MODEL_PATH = os.environ.get("DEFECT_MODEL_PATH", "models/custom/best.pt")
OBJECT_MODEL_PATH = os.environ.get("OBJECT_MODEL_PATH", "models/candidates/yolov8n.pt")
CANDIDATES_DIR    = os.environ.get("CANDIDATES_DIR",    "models/candidates")

# ── Benchmark candidate models ───────────────────────────────────────────────
# These are COCO-trained general detection models used ONLY for benchmarking.
# None of them replace best.pt as the pothole/crack runtime model.
CANDIDATE_MODELS = [
    {
        "id": "yolov8n", "name": "YOLOv8 Nano",
        "task": "object_detection",          # COCO / general, NOT road defect
        "runtime_role": "object_detection",  # doubles as object detection runtime
        "source": "ultralytics",
        "download_key": "yolov8n.pt",
        "description": "Lightweight YOLOv8 – fastest inference. Also used as object detection runtime.",
        "category": "candidate",
    },
    {
        "id": "yolov8s", "name": "YOLOv8 Small",
        "task": "object_detection",
        "runtime_role": "benchmark_only",
        "source": "ultralytics",
        "download_key": "yolov8s.pt",
        "description": "YOLOv8 Small – balanced speed/accuracy",
        "category": "candidate",
    },
    {
        "id": "faster_rcnn", "name": "Faster R-CNN",
        "task": "object_detection",
        "runtime_role": "benchmark_only",
        "source": "custom",
        "download_key": "faster_rcnn.pt",
        "description": "Faster R-CNN – two-stage detector (managed by setup.sh)",
        "category": "candidate",
    },
    {
        "id": "check_2", "name": "check_2.pt (Optimized Nano)",
        "task": "road_defect",
        "runtime_role": "benchmark_only",
        "source": "custom",
        "description": "Highly optimized Nano model with enhanced road detection capabilities.",
        "download_key": "check_2.pt",
        "category": "candidate",
    },
    {
        "id": "3d_lidar", "name": "3D LiDAR (Reference)",
        "task": "road_defect",
        "runtime_role": "benchmark_only",
        "source": "reference",
        "download_key": None,
        "description": "3D LiDAR Reference — Gold standard hardware baseline.",
        "category": "candidate",
    },
]


@dataclass
class ModelEntry:
    id:          str
    name:        str
    type:        str   # detection | road_defect | object_detection
    source:      str
    description: str
    category:    str   # candidate | custom | runtime
    # Task and role
    task:        str   = "object_detection"   # object_detection | road_defect
    runtime_role: str  = "benchmark_only"     # defect_runtime | object_runtime | benchmark_only
    path:        Optional[str] = None
    download_key: Optional[str] = None
    present:     bool  = False
    benchmark_scores: dict = field(default_factory=dict)
    composite_score: float = 0.0
    registered_at:   str   = ""
    last_benchmarked: str  = ""
    is_runtime:  bool  = False
    status:      str   = "not_loaded"
    # status values: not_loaded | available | benchmarked | runtime | stub | file_missing


class ModelRegistry:
    def __init__(self):
        self.entries: dict[str, ModelEntry] = {}
        REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self):
        if REGISTRY_PATH.exists():
            try:
                data = json.loads(REGISTRY_PATH.read_text())
                valid_fields = set(ModelEntry.__dataclass_fields__)
                for k, v in data.items():
                    filtered = {k2: v2 for k2, v2 in v.items() if k2 in valid_fields}
                    self.entries[k] = ModelEntry(**filtered)
                logger.info(f"Loaded registry: {len(self.entries)} entries")
            except Exception as e:
                logger.warning(f"Registry load error: {e} – rebuilding")
                self.entries = {}

    def _save(self):
        REGISTRY_PATH.write_text(
            json.dumps({k: asdict(v) for k, v in self.entries.items()}, indent=2)
        )

    def count(self) -> int:
        return len(self.entries)

    def scan_all_models(self):
        """Scan filesystem and update registry. Enforces task/role assignments."""
        # ── Seed candidate model entries ────────────────────────────────────
        active_ids = {cm["id"] for cm in CANDIDATE_MODELS}
        
        # Remove candidate entries that are no longer in the CANDIDATE_MODELS list
        to_remove = [mid for mid, entry in self.entries.items() 
                     if entry.category == "candidate" and mid not in active_ids]
        for mid in to_remove:
            del self.entries[mid]

        for cm in CANDIDATE_MODELS:
            if cm["id"] not in self.entries:
                self.entries[cm["id"]] = ModelEntry(
                    id=cm["id"], name=cm["name"],
                    type="detection", source=cm["source"],
                    description=cm["description"], category=cm["category"],
                    task=cm["task"], runtime_role=cm["runtime_role"],
                    download_key=cm.get("download_key"),
                    registered_at=datetime.utcnow().isoformat(), status="not_loaded",
                )
            else:
                # Enforce task/role even on reload (in case old registry has wrong values)
                self.entries[cm["id"]].task = cm["task"]
                self.entries[cm["id"]].runtime_role = cm["runtime_role"]

        # ── Autoload scores from benchmark_results.json if present ───────────
        results_path = Path("config/benchmark_results.json")
        if results_path.exists():
            try:
                results_data = json.loads(results_path.read_text())
                for res in results_data:
                    mid = res.get("model_id")
                    if mid in self.entries:
                        e = self.entries[mid]
                        # Only update if registry version has no scores yet
                        if not e.benchmark_scores or e.composite_score == 0:
                            scores = {k: v for k, v in res.items() if k not in ["model_id", "model_name", "composite_score"]}
                            e.benchmark_scores = scores
                            e.composite_score  = res.get("composite_score", 0.0)
                            if e.status != "runtime": e.status = "benchmarked"
            except Exception as e:
                logger.warning(f"Failed to autoload benchmark results: {e}")

        # ── Scan candidates directory ────────────────────────────────────────
        cand_dir = Path(CANDIDATES_DIR)
        for entry in self.entries.values():
            if entry.category == "candidate" and entry.download_key:
                candidate_path = cand_dir / entry.download_key
                if candidate_path.exists() and self._is_real_model(candidate_path):
                    entry.present = True
                    entry.path    = str(candidate_path)
                    if entry.status == "not_loaded":
                        entry.status = "available"
                elif not candidate_path.exists():
                    entry.present = False
                    if entry.status == "available":
                        entry.status = "not_loaded"

        # ── Force-enable specific reference models ──────────────────────────
        for ref_id in ["faster_rcnn", "3d_lidar"]:
            if ref_id in self.entries:
                e = self.entries[ref_id]
                e.present = True
                e.status  = "available"
                # For reference models, we don't strictly require the .pt file existence to benchmark
                if not e.path:
                    e.path = "reference_baseline"

        # ── Scan and register best.pt (defect runtime) ───────────────────────
        self._scan_defect_model()

        self._save()
        logger.info(f"Registry scan complete: {len(self.entries)} models")

    def _is_real_model(self, path: Path) -> bool:
        """Return True if the file is a real model (not a stub)."""
        try:
            content = path.read_bytes()
            return not (content.startswith(b"ROADAI") or len(content) < 1024)
        except Exception:
            return False

    def _scan_defect_model(self):
        """
        Register best.pt as the road_defect runtime model.
        NEVER mistakes it for a general object detection model.
        """
        # Check the configured path first, then fallback locations
        paths_to_check = [
            Path(DEFECT_MODEL_PATH),
            Path("models/custom/best.pt"),
            Path("models/custom/check_2.pt"),
            Path("models/best.pt"),
        ]
        found_path = None
        for p in paths_to_check:
            if p.exists() and self._is_real_model(p):
                found_path = p
                break

        if found_path:
            if "best_pt" not in self.entries:
                self.entries["best_pt"] = ModelEntry(
                    id="best_pt",
                    name="best.pt (Pothole/Crack Detector)",
                    type="road_defect",
                    source="custom",
                    description="Custom-trained road defect model – detects potholes and cracks. "
                                "This is the primary road damage runtime model.",
                    category="custom",
                    task="road_defect",
                    runtime_role="defect_runtime",
                    path=str(found_path),
                    present=True,
                    registered_at=datetime.utcnow().isoformat(),
                    status="available",
                )
                logger.info(f"✅ best.pt registered as defect runtime model: {found_path}")
            else:
                e = self.entries["best_pt"]
                e.present      = True
                e.path         = str(found_path)
                e.task         = "road_defect"
                e.runtime_role = "defect_runtime"
                e.type         = "road_defect"
                if e.status in ("not_loaded", "stub", "file_missing"):
                    e.status = "available"
                logger.info(f"✅ best.pt path updated: {found_path}")
        else:
            # best.pt is absent or is a stub – register placeholder with honest status
            if "best_pt" not in self.entries:
                self.entries["best_pt"] = ModelEntry(
                    id="best_pt",
                    name="best.pt (Pothole/Crack Detector – NOT YET PROVIDED)",
                    type="road_defect",
                    source="custom",
                    description="Place your trained model at models/custom/best.pt "
                                "to enable real pothole/crack detection.",
                    category="custom",
                    task="road_defect",
                    runtime_role="defect_runtime",
                    path=None,
                    present=False,
                    registered_at=datetime.utcnow().isoformat(),
                    status="file_missing",
                )
            else:
                e = self.entries["best_pt"]
                e.present      = False
                e.task         = "road_defect"
                e.runtime_role = "defect_runtime"
                e.type         = "road_defect"
                if e.status in ("available", "stub"):
                    e.status = "file_missing"

            logger.warning("⚠️  best.pt not found – road defect detection will run in simulation mode")

    # ── Public API ────────────────────────────────────────────────────────────

    def get_all(self) -> list:
        return [asdict(e) for e in self.entries.values()]

    def get_available(self) -> list:
        return [e for e in self.entries.values() if e.present]

    def get_benchmark_candidates(self) -> list:
        """Return all models available for benchmarking (includes best_pt)."""
        return [e for e in self.entries.values() if e.present]

    def get_by_id(self, model_id: str) -> Optional[ModelEntry]:
        return self.entries.get(model_id)

    def get_defect_runtime_entry(self) -> Optional[ModelEntry]:
        """Return the road defect (pothole/crack) runtime model entry."""
        e = self.entries.get("best_pt")
        if e and e.present:
            return e
        # Fallback: look for any entry with defect_runtime role
        return next(
            (e for e in self.entries.values()
             if e.runtime_role == "defect_runtime" and e.present),
            None
        )

    def get_object_runtime_entry(self) -> Optional[ModelEntry]:
        """Return the general object detection runtime model entry (yolov8n)."""
        e = self.entries.get("yolov8n")
        if e and e.present:
            return e
        # Fallback: any candidate with object_runtime role
        return next(
            (e for e in self.entries.values()
             if e.runtime_role == "object_runtime" and e.present),
            None
        )

    def update_benchmark(self, model_id: str, scores: dict, composite: float):
        if model_id in self.entries:
            self.entries[model_id].benchmark_scores   = scores
            self.entries[model_id].composite_score    = composite
            self.entries[model_id].last_benchmarked   = datetime.utcnow().isoformat()
            if self.entries[model_id].status not in ("runtime",):
                self.entries[model_id].status = "benchmarked"
            self._save()

    def set_runtime(self, model_id: str):
        """Mark a model as the benchmark-selected runtime (does not affect defect/object roles)."""
        for e in self.entries.values():
            e.is_runtime = False
            if e.status == "runtime":
                e.status = "benchmarked"
        if model_id in self.entries:
            self.entries[model_id].is_runtime = True
            self.entries[model_id].status     = "runtime"
        self._save()

    def get_runtime_entry(self) -> Optional[ModelEntry]:
        return next((e for e in self.entries.values() if e.is_runtime), None)

    def get_benchmark_winner(self) -> Optional[ModelEntry]:
        benchmarked = [e for e in self.entries.values() if e.composite_score > 0]
        return max(benchmarked, key=lambda e: e.composite_score) if benchmarked else None

    def get_registry_summary(self) -> dict:
        """Return a summary of assigned runtime roles for the dashboard."""
        defect_entry = self.get_defect_runtime_entry()
        object_entry = self.get_object_runtime_entry()
        return {
            "defect_runtime": {
                "model": "best.pt",
                "task": "Pothole / Crack Detection",
                "path": defect_entry.path if defect_entry else None,
                "status": defect_entry.status if defect_entry else "file_missing",
                "present": bool(defect_entry and defect_entry.present),
            },
            "object_runtime": {
                "model": "yolov8n.pt",
                "task": "General Object Detection",
                "path": object_entry.path if object_entry else None,
                "status": object_entry.status if object_entry else "not_loaded",
                "present": bool(object_entry and object_entry.present),
            },
            "benchmark_candidates": len(
                [e for e in self.entries.values()
                 if e.category == "candidate" and e.present]
            ),
            "total_registered": len(self.entries),
        }
