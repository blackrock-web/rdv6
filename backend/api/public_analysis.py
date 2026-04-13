"""Public analysis API (no auth required)."""
import cv2, numpy as np
from fastapi import APIRouter, UploadFile, File, Form, Request, HTTPException
from backend.utils.logger import get_logger
logger = get_logger(__name__)
router = APIRouter()

def _rd(result):
    d = result.__dict__.copy()
    for k in list(d.keys()):
        if isinstance(d[k], np.ndarray): d[k] = d[k].tolist()
    b64 = d.pop("annotated_image_b64","") or ""
    d["annotated_image"] = f"data:image/jpeg;base64,{b64}" if b64 else None
    return d

@router.post("/image")
async def public_image(request: Request, file: UploadFile=File(...), preprocessing_mode: str=Form("auto")):
    engine = getattr(request.app.state,"engine",None)
    if not engine: raise HTTPException(503,"Engine not ready")
    frame = cv2.imdecode(np.frombuffer(await file.read(),np.uint8), cv2.IMREAD_COLOR)
    if frame is None: raise HTTPException(400,"Cannot decode image")
    return _rd(engine.analyze_frame(frame,0,preprocessing_mode=preprocessing_mode))

@router.post("/video")
async def public_video(request: Request, file: UploadFile=File(...), sample_rate: int=Form(8)):
    import time; from pathlib import Path
    engine = getattr(request.app.state,"engine",None)
    if not engine: raise HTTPException(503,"Engine not ready")
    tmp = Path("uploads")/f"pub_{int(time.time())}.mp4"
    tmp.parent.mkdir(exist_ok=True); tmp.write_bytes(await file.read())
    cap = cv2.VideoCapture(str(tmp))
    if not cap.isOpened(): tmp.unlink(missing_ok=True); raise HTTPException(400,"Cannot open video")
    results, history, fid = [], [], 0
    while True:
        ret, frame = cap.read()
        if not ret: break
        if fid % sample_rate == 0:
            rd = _rd(engine.analyze_frame(frame,fid,history))
            results.append(rd); history.append({"total_damage_count":rd.get("total_damage_count",0)})
        fid += 1
    cap.release(); tmp.unlink(missing_ok=True)
    if not results: raise HTTPException(400,"No frames")
    last = results[-1]
    avg_h = round(sum(r["road_health_score"] for r in results)/len(results),1)
    return {"type":"video","processed_frames":len(results),"average_health_score":avg_h,
            "road_health_score":avg_h,"frame_results":results[-6:],
            **{k:last.get(k) for k in ["rul_estimate_years","pothole_count","crack_count",
               "total_damage_count","damage_detections","severity_distribution","formation_risk",
               "weather_condition","model_used","annotated_image"]}}
