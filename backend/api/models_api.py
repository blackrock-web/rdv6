"""ROADAI Models API v3.4-fix
Exposes task/runtime-role separation in all responses.
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from pathlib import Path
from dataclasses import asdict

from backend.api.auth import verify_token, require_admin
from backend.core.model_registry import ModelRegistry
from backend.core.runtime_selector import RuntimeModelSelector
from backend.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


def _get_registry(request: Request) -> ModelRegistry:
    return request.app.state.registry


def _get_selector(request: Request) -> RuntimeModelSelector:
    return request.app.state.selector


@router.get("/")
async def list_models(request: Request, token: dict = Depends(verify_token)):
    registry = _get_registry(request)
    selector = _get_selector(request)
    winner       = registry.get_benchmark_winner()
    runtime_entry = registry.get_runtime_entry()
    defect_entry  = registry.get_defect_runtime_entry()
    object_entry  = registry.get_object_runtime_entry()

    return {
        "models": registry.get_all(),
        # Backward-compat fields
        "runtime_model": runtime_entry.id if runtime_entry else None,
        "benchmark_winner": winner.id if winner else None,
        # New: explicit task-separated runtime info
        "runtime_assignment": {
            "defect_runtime": {
                "model_id": "best_pt",
                "model_name": "best.pt",
                "task": "road_defect_detection",
                "path": selector.defect_model_path,
                "ready": selector._defect_ready,
            },
            "object_runtime": {
                "model_id": "yolov8n",
                "model_name": "yolov8n.pt",
                "task": "general_object_detection",
                "path": selector.object_model_path,
                "ready": selector._object_ready,
            },
        },
        "registry_summary": registry.get_registry_summary(),
        "custom_model_present": Path("models/custom/best.pt").exists(),
    }


@router.get("/runtime")
async def runtime_info(request: Request, token: dict = Depends(verify_token)):
    selector = _get_selector(request)
    registry = _get_registry(request)
    info = selector.get_runtime_info()
    info["registry_summary"] = registry.get_registry_summary()
    return info


@router.get("/runtime-status")
async def runtime_status(request: Request, token: dict = Depends(verify_token)):
    """Detailed per-task runtime status."""
    selector = _get_selector(request)
    registry = _get_registry(request)
    return {
        **selector.get_status_summary(),
        "registry_summary": registry.get_registry_summary(),
    }


@router.post("/scan")
async def scan_models(request: Request, token: dict = Depends(require_admin)):
    registry = _get_registry(request)
    registry.scan_all_models()
    # Re-resolve paths in selector after scan
    selector = _get_selector(request)
    selector.ensure_runtime_model()
    return {
        "message": "Model scan complete",
        "count": registry.count(),
        "registry_summary": registry.get_registry_summary(),
    }


@router.post("/rescan-custom")
async def rescan_custom(request: Request, token: dict = Depends(require_admin)):
    """Re-scan for best.pt and update registry + selector."""
    registry = _get_registry(request)
    registry._scan_defect_model()
    registry._save()
    selector = _get_selector(request)
    selector._resolve_defect_model()
    selector._write_meta()
    defect_entry = registry.get_defect_runtime_entry()
    present = defect_entry is not None and defect_entry.present
    return {
        "defect_model_present": present,
        "defect_model_path": selector.defect_model_path,
        "defect_model_ready": selector._defect_ready,
        "message": (
            f"best.pt found and registered at {selector.defect_model_path}"
            if present else
            "best.pt not found – place at models/custom/best.pt and rescan"
        ),
    }


@router.post("/select-runtime")
async def select_runtime(request: Request, token: dict = Depends(require_admin)):
    """Deploy benchmark winner. Does NOT replace best.pt as defect runtime."""
    registry = _get_registry(request)
    selector = _get_selector(request)
    return selector.select_and_deploy_winner()




# ── Admin model chooser endpoints ─────────────────────────────────────────────

from pydantic import BaseModel as _BM

class SetModelRequest(_BM):
    target_path: str
    target_name: str = ""
    model_config = {"protected_namespaces": ()}

@router.post("/set-defect-model")
async def set_defect_model(
    req: SetModelRequest,
    request: Request,
    token: dict = Depends(require_admin),
):
    """Override the defect detection model path at runtime."""
    import asyncio
    from pathlib import Path as _P
    engine = getattr(request.app.state, "engine", None)
    selector = _get_selector(request)
    p = _P(req.target_path)
    if not p.exists():
        raise HTTPException(404, f"Model file not found: {req.target_path}")
    
    # Update selector path (metadata)
    selector._defect_path  = str(p)
    selector._defect_ready = True
    
    # Reload engine defect model in background thread
    if engine:
        success = await asyncio.to_thread(engine.reload_defect_model, str(p))
        if not success:
             raise HTTPException(500, f"Background model load failed for {p.name}")
             
    return {"message": f"Defect model set to {p.name}", "path": str(p), "ready": True}


@router.post("/set-object-model")
async def set_object_model(
    req: SetModelRequest,
    request: Request,
    token: dict = Depends(require_admin),
):
    """Override the object detection model path at runtime."""
    import asyncio
    from pathlib import Path as _P
    engine = getattr(request.app.state, "engine", None)
    selector = _get_selector(request)
    # Allow "yolov8n.pt" shorthand (auto-download)
    use_path = req.target_path if req.target_path.endswith(".pt") and "/" not in req.target_path else req.target_path
    p = _P(use_path)
    
    if p.exists():
        selector._object_path  = str(p)
        selector._object_ready = True
    else:
        # Assume ultralytics will auto-download
        selector._object_path  = use_path
        selector._object_ready = True
        
    if engine:
        success = await asyncio.to_thread(engine.reload_object_model, use_path)
        if not success:
            raise HTTPException(500, f"Background object model load failed for {use_path}")
            
    return {"message": f"Object model set to {use_path}", "ready": True}


@router.get("/list-available")
async def list_available_models(request: Request, token: dict = Depends(require_admin)):
    """Return all .pt files found in models/ directories."""
    import glob
    found = []
    for pattern in ["models/**/*.pt", "models/*.pt"]:
        for f in glob.glob(pattern, recursive=True):
            from pathlib import Path as _P
            p = _P(f)
            try:
                size_mb = round(p.stat().st_size / 1e6, 1)
                is_real = size_mb > 0.001
            except Exception:
                size_mb = 0; is_real = False
            found.append({"path": f, "name": p.name, "size_mb": size_mb, "is_real": is_real})
    # Add auto-download options
    found += [
        {"path": "yolov8n.pt", "name": "yolov8n.pt", "size_mb": 6.2,  "is_real": True, "auto_dl": True},
        {"path": "yolov8s.pt", "name": "yolov8s.pt", "size_mb": 22.4, "is_real": True, "auto_dl": True},
        {"path": "yolov8m.pt", "name": "yolov8m.pt", "size_mb": 52.0, "is_real": True, "auto_dl": True},
    ]
    return {"models": found}


@router.get("/{model_id}")
async def get_model(model_id: str, request: Request, token: dict = Depends(verify_token)):
    registry = _get_registry(request)
    entry = registry.get_by_id(model_id)
    if not entry:
        raise HTTPException(404, "Model not found")
    return asdict(entry)
