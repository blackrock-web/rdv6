"""
ROADAI v4.0 — Industry-Grade FastAPI Backend
============================================
Upgrades from v3.6:
  • FastAPI (async, high-performance) replacing Flask
  • Real DeepLabV3 road segmentation (torchvision)
  • MiDaS depth estimation (torch.hub)
  • Fusion engine: YOLO + Segmentation + Depth
  • XGBoost RUL ML pipeline
  • Job queue with async video processing
  • Full GPS/geo tracking with SQLite
  • PDF report generation
  • JWT auth with organizations
  • WebSocket live streaming
  • TensorRT/ONNX export support
  • SaaS-ready with API keys & usage tracking
"""
import os, sys, time
from pathlib import Path
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")       # use GPU if present
os.environ.setdefault("OMP_NUM_THREADS", "4")

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.utils.logger import get_logger
from backend.db.database                import init_db

logger = get_logger(__name__)


def _ensure_dirs():
    for d in ["uploads","outputs","outputs/reports","config",
              "models/custom","models/runtime","models/candidates",
              "data/jobs"]:
        Path(d).mkdir(parents=True, exist_ok=True)


def _ensure_users():
    import json
    f = Path("config/users.json")
    if not f.exists():
        f.write_text(json.dumps({
            "admin":   {"password":"admin123",   "role":"admin",   "name":"System Admin",   "email":"admin@roadai.local"},
            "analyst": {"password":"analyst123", "role":"analyst", "name":"Road Analyst",    "email":"analyst@roadai.local"},
            "user":    {"password":"user123",    "role":"user",    "name":"Field Viewer",   "email":"user@roadai.local"},
        }, indent=2))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting ROADAI v2.0...")
    _ensure_dirs()
    # Initialise DB and detect mode early (in background task to avoid blocking boot)
    from backend.db.database import get_db

    # Model registry + runtime selector
    from backend.core.model_registry   import ModelRegistry
    from backend.core.runtime_selector import RuntimeModelSelector
    
    app.state.registry = ModelRegistry()
    app.state.registry.scan_all_models()
    app.state.selector = RuntimeModelSelector(app.state.registry)
    
    # Pre-initialize state with None
    app.state.engine = None
    app.state.seg_service = None
    app.state.depth_service = None
    app.state.fusion = None
    app.state.rul_service = None

    async def _async_init():
        import asyncio
        try:
            logger.info("⚙️  Deep-Loading AI Components (Background)...")
            
            # Initialize DB connection in background
            from backend.db.database import get_db
            await get_db()
            
            # These imports are fast (just Python module loading)
            from backend.core.detection_engine     import DetectionEngine
            from backend.core.segmentation_service import SegmentationService
            from backend.core.depth_service        import DepthService
            from backend.core.fusion_service       import FusionEngine
            from backend.core.rul_service          import RULService

            # 1. Runtime selector (may load model paths — sync)
            await asyncio.to_thread(app.state.selector.ensure_runtime_model)

            # 2. Detection Engine — CUDA/ONNX loading (sync, blocking)
            app.state.engine = await asyncio.to_thread(
                lambda: DetectionEngine(selector=app.state.selector)
            )

            # 3. Segmentation — torchvision DeepLabV3 loading (sync, blocking)
            app.state.seg_service = await asyncio.to_thread(SegmentationService)

            # 4. Depth estimation — torch.hub MiDaS (sync, blocking, slowest)
            app.state.depth_service = await asyncio.to_thread(DepthService)

            # 5. Fusion engine (wraps seg + depth, fast)
            app.state.fusion = FusionEngine(
                seg_service=app.state.seg_service,
                depth_service=app.state.depth_service
            )

            # 6. RUL / XGBoost (sync, blocking)
            app.state.rul_service = await asyncio.to_thread(RULService)

            logger.info("✅ ROADAI v4.0 Deep-Load Complete!")
        except Exception as e:
            logger.error(f"❌ Critical Background Init Failed: {e}", exc_info=True)

    import asyncio
    init_task = asyncio.create_task(_async_init())
    
    # Optional: ensure task doesn't block server closure
    app.state.init_task = init_task
    
    logger.info("🌐 API Engine Online — accepting requests immediately ✅")
    yield
    logger.info("🛑 Shutting down ROADAI v4.0...")


app = FastAPI(
    title="ROADAI v4.0",
    description="Industry-Grade Road Degradation Detection Platform",
    version="4.0.0",
    lifespan=lifespan,
)

# CORS Configuration
raw_origins = os.environ.get("CORS_ORIGINS", "")
origins = []

if raw_origins:
    if raw_origins.startswith("["):
        import json
        try:
            origins = json.loads(raw_origins)
        except:
             origins = [o.strip().strip('"').strip("'") for o in raw_origins.strip("[]").split(",") if o.strip()]
    else:
        origins = [o.strip() for o in raw_origins.split(",") if o.strip()]

# Always allow these critical production and dev origins
essential_origins = [
    "https://roadaiv4.netlify.app",
    "https://roadai-v4.netlify.app",
    "http://localhost:5173",
    "http://127.0.0.1:5173"
]
for eo in essential_origins:
    if eo not in origins:
        origins.append(eo)
    # Also add versions with/without trailing slashes for safety
    if eo.endswith("/"):
        alt = eo[:-1]
    else:
        alt = eo + "/"
    if alt not in origins:
        origins.append(alt)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if "*" not in origins else ["*"],
    allow_credentials=True if "*" not in origins else False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# ── Mount routers ──────────────────────────────────────────────────────────────
from backend.api.auth          import router as auth_router
from backend.api.analysis      import router as analysis_router
from backend.api.public_analysis import router as public_router
from backend.api.models_api    import router as models_router
from backend.api.benchmarks    import router as benchmarks_router
from backend.api.reports       import router as reports_router
from backend.api.alerts        import router as alerts_router
from backend.api.geo           import router as geo_router
from backend.api.jobs          import router as jobs_router
from backend.api.websocket     import router as ws_router
from backend.api.admin         import router as admin_router
from backend.api.analytics     import router as analytics_router
from backend.core.metrics      import metrics_endpoint

app.include_router(auth_router,       prefix="/api/auth",       tags=["Auth"])
app.include_router(public_router,     prefix="/api/public",     tags=["Public"])
app.include_router(analysis_router,   prefix="/api/analysis",   tags=["Analysis"])
app.include_router(models_router,     prefix="/api/models",     tags=["Models"])
app.include_router(benchmarks_router, prefix="/api/benchmarks", tags=["Benchmarks"])
app.include_router(reports_router,    prefix="/api/reports",    tags=["Reports"])
app.include_router(alerts_router,     prefix="/api/alerts",     tags=["Alerts"])
app.include_router(geo_router,        prefix="/api/geo",        tags=["Geo"])
app.include_router(jobs_router,       prefix="/api/jobs",       tags=["Jobs"])
app.include_router(ws_router,                                    tags=["WebSocket"])
app.include_router(admin_router,      prefix="/api/admin",      tags=["Admin"])
app.include_router(analytics_router,  prefix="/api/analytics",  tags=["Analytics"])

# Prometheus Metrics Endpoint
app.get("/metrics", tags=["System"])(metrics_endpoint)

for folder in ["uploads", "outputs"]:
    Path(folder).mkdir(exist_ok=True)
    app.mount(f"/{folder}", StaticFiles(directory=folder), name=folder)

app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/", tags=["System"])
@app.head("/", tags=["System"])
async def root():
    """Root endpoint to satisfy Render's default health check and HEAD requests."""
    return {"status": "online", "message": "ROADAI v4.0 API Service", "timestamp": time.time()}


@app.get("/ping", tags=["System"])
async def ping():
    return {"status": "pong", "timestamp": time.time()}


@app.get("/api/health")
async def health():
    engine      = getattr(app.state, "engine", None)
    seg_service = getattr(app.state, "seg_service", None)
    depth_service = getattr(app.state, "depth_service", None)
    rul_service = getattr(app.state, "rul_service", None)
    return {
        "status": "healthy",
        "version": "4.0.0",
        "defect_inference": "real" if engine and not engine._defect_sim else "cv_simulation",
        "object_inference": "real" if engine and not engine._object_sim else "cv_simulation",
        "segmentation":     "deeplab_loaded" if seg_service and seg_service.loaded else "not_loaded",
        "depth_estimation": "midas_loaded"   if depth_service and depth_service.loaded else "not_loaded",
        "rul_model":        "xgboost_ml"     if rul_service and rul_service.ml_ready else "heuristic",
        "services": {
            "geo": "active", "alerts": "active", "reports": "active",
            "streaming": "websocket", "jobs": "active", "fusion": "active",
        },
    }


@app.get("/api/runtime-status")
async def runtime_status():
    selector = getattr(app.state, "selector", None)
    registry = getattr(app.state, "registry", None)
    if not selector:
        raise HTTPException(503, "Selector not initialised")
    return {
        **selector.get_runtime_info(),
        "registry_summary": registry.get_registry_summary() if registry else {},
    }


from fastapi.responses import FileResponse

@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    # Ignore core backend routes
    if full_path.startswith("api/") or full_path.startswith("docs") or full_path.startswith("openapi.json") or full_path.startswith("metrics"):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Not found")
        
    frontend_dir = Path("frontend")
    
    # Try to return the exact requested file (e.g. assets/main.js, favicon.ico)
    if full_path:
        file_path = frontend_dir / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
    
    # Fallback to index.html for React Router
    index_path = frontend_dir / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
        
    return {"status": "Frontend not found. Please ensure index.html exists in frontend/."}


# (Routes moved above)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False, workers=1)
