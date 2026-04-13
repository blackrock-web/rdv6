"""ROADAI Analysis API v4 — image/video/webcam/RTSP with fusion"""
import asyncio, json, time, uuid, base64, os
from pathlib import Path
from typing import Optional, AsyncGenerator
from fastapi import APIRouter, UploadFile, File, Form, Request, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from backend.utils.logger import get_logger
from backend.services.geo_service import get_analysis_stats
from backend.db.database import get_db, doc_to_dict, docs_to_list
logger = get_logger(__name__)
router = APIRouter()

def _get_engine(req):
    e = getattr(req.app.state,"engine",None)
    if not e: raise HTTPException(503,"Detection engine not initialized")
    return e

def _result_to_dict(result):
    import numpy as np
    d = result.__dict__.copy()
    for k in list(d.keys()):
        if isinstance(d[k], np.ndarray): d[k] = d[k].tolist()
    b64 = d.pop("annotated_image_b64","") or ""
    d["annotated_image"] = f"data:image/jpeg;base64,{b64}" if b64 else None
    return d

def _enrich_with_fusion(frame, rd, req):
    import numpy as np
    fusion = getattr(req.app.state,"fusion",None)
    rul_svc = getattr(req.app.state,"rul_service",None)
    if not fusion: return rd
    try:
        fused = fusion.fuse(frame, rd.get("damage_detections",[]), run_seg=True, run_depth=True)
        rd.update({"fused_detections":fused["fused_detections"],"road_coverage_pct":fused["road_coverage_pct"],
                   "seg_method":fused["seg_method"],"depth_method":fused["depth_method"],
                   "fusion_applied":True,"removed_by_seg":fused["removed_by_seg"]})
        depths = [d.get("depth_value",0.5) for d in fused["fused_detections"]]
        avg_depth = float(np.mean(depths)) if depths else 0.5
        if rul_svc:
            r = rul_svc.estimate(
                health_score=rd.get("road_health_score", 100.0),
                pothole_count=rd.get("pothole_count", 0),
                crack_count=rd.get("crack_count", 0),
                damage_coverage_pct=rd.get("damage_coverage_pct", 0.0),
                avg_depth=avg_depth,
                severity_dist=rd.get("severity_distribution", {}),
                weather_condition=rd.get("weather_condition", "clear")
            )
            rd.update({"rul_estimate_years":r.rul_years,"rul_risk_band":r.risk_band,
                       "rul_label":r.label,"rul_method":r.method,"avg_depth":round(avg_depth,3)})
    except Exception as e:
        logger.warning(f"Fusion failed: {e}")
    return rd

async def _save_analysis(rd, itype):
    try:
        rid = rd.get("report_id") or str(uuid.uuid4())
        res_to_save = rd.copy()
        res_to_save["id"] = rid
        res_to_save["input_type"] = itype
        res_to_save["status"] = "done"
        res_to_save["created_at"] = time.time()
        
        db = await get_db()
        await db.analyses.insert_one(res_to_save)
        
        # GPS/Geo Event recording
        glat = rd.get("gps_lat")
        glng = rd.get("gps_lng")
        if glat is not None and glng is not None:
            try:
                from backend.services.geo_service import record_event
                await record_event(rd, latitude=glat, longitude=glng, source_type=itype)
            except Exception as ge: logger.warning(f"Geo record failed: {ge}")
            
        # Report generation
        try:
            from backend.services.report_service import generate_report
            generate_report(rd, report_id=rid, gps_lat=glat, gps_lon=glng)
        except Exception as re: logger.warning(f"Auto-report failed: {re}")
                
    except Exception as e:
        logger.warning(f"Save failed: {e}")

@router.post("/image")
async def analyze_image(request: Request, file: UploadFile=File(...),
                        preprocessing_mode: str=Form("auto"), run_fusion: bool=Form(False),
                        latitude: Optional[float]=Form(None), longitude: Optional[float]=Form(None)):
    import cv2, numpy as np, asyncio
    engine = _get_engine(request)
    # Read file content safely
    content = await file.read()
    frame  = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
    if frame is None: raise HTTPException(400,"Could not decode image")
    
    # Offload heavy AI inference to a background thread to avoid blocking the event loop
    # This prevents the server from hanging and causing 502/CORS errors during processing.
    rd_raw = await asyncio.to_thread(
        engine.analyze_frame, 
        frame, 
        frame_id=0, 
        preprocessing_mode=preprocessing_mode, 
        source_type="image"
    )
    rd = _result_to_dict(rd_raw)
    
    rd["gps_lat"] = latitude
    rd["gps_lng"] = longitude
    if run_fusion: rd = _enrich_with_fusion(frame, rd, request)
    await _save_analysis(rd, "image")
    return rd

@router.post("/satellite")
async def analyze_satellite(request: Request, body: dict):
    """
    Analyzes a base64 satellite screenshot from the frontend.
    body: { "image": "data:image/...", "lat": 12.3, "lng": 77.4, "zoom": 18 }
    """
    import cv2, numpy as np, base64
    engine = _get_engine(request)
    
    img_data = body.get("image")
    if not img_data or "," not in img_data:
        raise HTTPException(400, "Invalid image data")
    
    header, encoded = img_data.split(",", 1)
    # Fix potential incorrect padding errors by adding extra '='
    encoded += "=" * (-len(encoded) % 4)
    nparr = np.frombuffer(base64.b64decode(encoded, validate=False), np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if frame is None:
        raise HTTPException(400, "Could not decode satellite image")
        
    # Analyze frame (Perspective is top-down here, but models usually generalize)
    rd = _result_to_dict(engine.analyze_frame(frame, frame_id=0, preprocessing_mode="none", source_type="satellite"))
    
    # Inject GPS coordinates from the center of the map capture
    rd["gps_lat"] = body.get("lat")
    rd["gps_lng"] = body.get("lng")
    rd["satellite_zoom"] = body.get("zoom")
    
    # Run fusion/RUL if available
    rd = _enrich_with_fusion(frame, rd, request)
    
    await _save_analysis(rd, "satellite")
    return rd

@router.post("/video")
async def analyze_video(request: Request, file: UploadFile=File(...),
                        sample_rate: int=Form(2),   # ★ Every 2nd frame (was 5)
                        preprocessing_mode: str=Form("auto"),
                        run_fusion: bool=Form(False),
                        latitude: Optional[float]=Form(None),
                        longitude: Optional[float]=Form(None)):
    import cv2, numpy as np
    engine = _get_engine(request)
    tmp    = Path("uploads") / f"tmp_{int(time.time())}.mp4"
    tmp.parent.mkdir(exist_ok=True)
    tmp.write_bytes(await file.read())
    cap    = cv2.VideoCapture(str(tmp))
    if not cap.isOpened():
        tmp.unlink(missing_ok=True); raise HTTPException(400,"Cannot open video")
    fps    = cap.get(cv2.CAP_PROP_FPS) or 25
    w      = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h      = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    out_filename = f"annotated_vid_{int(time.time())}.mp4"
    out_path = Path("outputs") / out_filename
    out_path.parent.mkdir(exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(str(out_path), fourcc, fps, (w, h))

    total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    results, history, fid = [], [], 0
    last_bgr = None

    while True:
        ret, frame = cap.read()
        if not ret: break
        if fid % sample_rate == 0:
            rd = _result_to_dict(engine.analyze_frame(frame, frame_id=fid, history=history, preprocessing_mode=preprocessing_mode, source_type="video"))
            if run_fusion: rd = _enrich_with_fusion(frame,rd,request)
            
            b64_str = rd.get("annotated_image", "")
            if b64_str and b64_str.startswith("data:"):
                import numpy as np
                import cv2
                img_data = base64.b64decode(b64_str.split(",", 1)[1])
                last_bgr = cv2.imdecode(np.frombuffer(img_data, np.uint8), cv2.IMREAD_COLOR)
            else:
                last_bgr = frame
                
            # clear huge b64 string from history to save RAM
            rd["annotated_image"] = None 
            results.append(rd); history.append({"total_damage_count":rd.get("total_damage_count",0)})
        
        if last_bgr is not None:
            writer.write(last_bgr)
        else:
            writer.write(frame)
        fid += 1
        
    cap.release(); writer.release()
    tmp.unlink(missing_ok=True)
    
    if os.name == 'posix' and os.system('command -v ffmpeg >/dev/null 2>&1') == 0:
        # Re-encode to ensure browser compatibility
        final_path = str(out_path).replace(".mp4", "_web.mp4")
        os.system(f"ffmpeg -y -i {out_path} -vcodec libx264 -f mp4 {final_path} -hide_banner -loglevel error")
        if Path(final_path).exists():
            out_path.unlink()
            out_filename = Path(final_path).name

    if not results: raise HTTPException(400,"No frames processed")
    last = results[-1]
    avg_h = round(sum(r["road_health_score"] for r in results)/len(results),1)
    
    out = {"type":"video","processed_frames":len(results),"total_frames":total,
           "average_health_score":avg_h,"road_health_score":avg_h,
           "pothole_count":max(r["pothole_count"] for r in results),
           "crack_count":max(r["crack_count"] for r in results),
           "frame_results":results[-10:],
           "annotated_video_url": f"/outputs/{out_filename}",
           "gps_lat": latitude, "gps_lng": longitude,
           **{k:last.get(k) for k in ["rul_estimate_years","rul_label","rul_risk_band","rul_method","damage_detections","object_detections",
              "severity_distribution","formation_risk","formation_prediction","lane_detected",
              "weather_condition","model_used","active_lane_count",
              "road_outside_lane_count","wall_filtered_count","damage_coverage_pct",
              "pipeline_timings","filter_stats","wall_detections"]}}
    await _save_analysis(out,"video"); return out

@router.post("/video/stream")
async def analyze_video_stream(
    request: Request,
    file: UploadFile = File(...),
    sample_rate: int = Form(1),
    preprocessing_mode: str = Form("auto"),
    use_lane: bool = Form(True),    # ★ Lane toggle: False = skip lane detection/priority
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
):
    """Stream annotated frames as SSE during video processing."""
    import cv2, numpy as np

    engine = _get_engine(request)
    tmp = Path("uploads") / f"stream_{int(time.time())}.mp4"
    tmp.parent.mkdir(exist_ok=True)
    tmp.write_bytes(await file.read())

    async def _generate():
        import cv2, numpy as np
        cap = cv2.VideoCapture(str(tmp))
        if not cap.isOpened():
            yield f"data: {json.dumps({'error': 'Cannot open video'})}\n\n"
            return

        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        fps   = cap.get(cv2.CAP_PROP_FPS) or 25
        fid, history, results = 0, [], []

        # ★ Cumulative unique detection tracking (deduplicated by rounded bbox position)
        seen_potholes: set = set()
        seen_cracks:   set = set()

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if fid % sample_rate == 0:
                    rd = _result_to_dict(
                        engine.analyze_frame(
                            frame, frame_id=fid, history=history,
                            preprocessing_mode=preprocessing_mode, source_type="video",
                            use_lane=use_lane,
                        )
                    )
                    rd["gps_lat"] = latitude
                    rd["gps_lng"] = longitude
                    history.append({"total_damage_count": rd.get("total_damage_count", 0)})
                    if len(history) > 10:
                        history = history[-10:]

                    # ★ Accumulate unique detections across frames
                    # Key = rounded center of bbox to dedupe same defect across frames
                    for det in rd.get("damage_detections", []):
                        bbox = det.get("bbox", [0,0,0,0])
                        cx = round((bbox[0] + bbox[2]) / 2 / 40)  # ~40px grid for dedup
                        cy = round((bbox[1] + bbox[3]) / 2 / 40)
                        key = (fid // max(fps, 1), cx, cy)  # also segment by ~1s window
                        dtype = det.get("damage_type", "")
                        if dtype == "pothole":
                            seen_potholes.add(key)
                        elif dtype == "crack":
                            seen_cracks.add(key)

                    results.append(rd)
                    progress = round(fid / total * 100, 1)
                    cumulative_p = len(seen_potholes)
                    cumulative_c = len(seen_cracks)

                    payload = {
                        "type": "frame",
                        "frame_id": fid,
                        "progress": progress,
                        "total_frames": total,
                        "fps": fps,
                        "annotated_image": rd.get("annotated_image"),
                        "pothole_count":  cumulative_p,   # ★ Cumulative, not per-frame
                        "crack_count":    cumulative_c,   # ★ Cumulative, not per-frame
                        "road_health_score": rd.get("road_health_score", 100),
                        "severity_distribution": rd.get("severity_distribution", {}),
                        "formation_risk": rd.get("formation_risk", "low"),
                        "weather_condition": rd.get("weather_condition", "clear"),
                        "damage_detections": rd.get("damage_detections", []),
                    }
                    yield f"data: {json.dumps(payload)}\n\n"
                    await asyncio.sleep(0)

                fid += 1
        finally:
            cap.release()
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass

        # Final summary calculated via cumulative damage
        if results:
            total_potholes = len(seen_potholes)
            total_cracks   = len(seen_cracks)
            total_damage   = total_potholes + total_cracks
            
            # Compute cumulative health score using the DamageAnalyzer
            avg_h = engine.analyzer.compute_cumulative_health(total_potholes, total_cracks)
            
            # Recalculate RUL based on the cumulative health
            traffic_factor = 1.5 # placeholder or from history
            final_rul = engine.analyzer.estimate_rul(avg_h, traffic_factor=traffic_factor)
            
            last = results[-1]
            last["rul_estimate_years"] = final_rul
            last["road_health_score"] = avg_h

            # ★ Auto-trigger SMS alert if road is significantly damaged
            sms_status = {"sent": False, "reason": "not_triggered", "error": None}
            if avg_h < 60 or total_damage >= 5:
                try:
                    from backend.core.twilio_sms_service import send_sms
                    rul   = last.get("rul_estimate_years", "N/A")
                    risk  = last.get("formation_risk", "unknown")
                    msg = (
                        f"🚨 ROADAI ALERT — Road Damage Detected!\n"
                        f"Health Score : {avg_h}/100\n"
                        f"Potholes     : {total_potholes}\n"
                        f"Cracks       : {total_cracks}\n"
                        f"Formation Risk: {risk.upper()}\n"
                        f"Remaining Life: {rul} years\n"
                        f"Immediate inspection recommended."
                    )
                    result_sms = await asyncio.to_thread(send_sms, msg)
                    sms_status = {
                        "sent": result_sms.get("success", False),
                        "reason": "health_critical" if avg_h < 60 else "high_damage_count",
                        "error": result_sms.get("error"),
                        "sid":   result_sms.get("sid"),
                    }
                except Exception as sms_e:
                    sms_status = {"sent": False, "reason": "exception", "error": str(sms_e)}

            summary = {
                "type": "complete",
                "processed_frames": len(results),
                "total_frames":     total,
                "average_health_score": avg_h,
                "road_health_score":    avg_h,
                "pothole_count":  total_potholes,
                "crack_count":    total_cracks,
                "total_damage":   total_damage,
                "sms_alert":      sms_status,
                **{k: last.get(k) for k in [
                    "rul_estimate_years", "rul_label", "rul_risk_band", "rul_method", "damage_detections", "object_detections",
                    "severity_distribution", "formation_risk", "lane_detected",
                    "weather_condition", "model_used", "pipeline_timings",
                    "annotated_image",
                ]},
                "annotated_video_url": None,
            }
            yield f"data: {json.dumps(summary)}\n\n"
        else:
            yield f"data: {json.dumps({'type': 'complete', 'error': 'No frames processed'})}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

async def _sse_frames(engine, cap, max_frames=1800, prep="auto"):
    fid, history, t0 = 0, [], time.time()
    try:
        while fid < max_frames:
            ret, frame = cap.read()
            if not ret:
                yield f"data: {json.dumps({'error':'Stream ended'})}\n\n"; break
            try:
                rd = _result_to_dict(engine.analyze_frame(frame, frame_id=fid, history=history, preprocessing_mode=prep, source_type="stream"))
                history.append({"total_damage_count":rd.get("total_damage_count",0)})
                if len(history)>10: history=history[-10:]
                rd["stream_fps"]   = round(fid/max(time.time()-t0,0.1),1)
                rd["stream_frame"] = fid
                yield f"data: {json.dumps(rd)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error':str(e),'frame_id':fid})}\n\n"
            fid += 1
            await asyncio.sleep(0.001)
    finally:
        cap.release()
        yield f"data: {json.dumps({'status':'stream_complete','total_frames':fid})}\n\n"

@router.get("/stream/webcam")
async def stream_webcam(request: Request, device: int=Query(0), preprocessing_mode: str=Query("auto")):
    import cv2
    cap = cv2.VideoCapture(device)
    if not cap.isOpened(): raise HTTPException(400,f"Cannot open webcam {device}")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,640); cap.set(cv2.CAP_PROP_FRAME_HEIGHT,480); cap.set(cv2.CAP_PROP_FPS,15)
    return StreamingResponse(_sse_frames(_get_engine(request),cap,1800,preprocessing_mode),
        media_type="text/event-stream",
        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

@router.get("/stream/rtsp")
async def stream_rtsp(request: Request, url: str=Query(...), duration: int=Query(60),
                      preprocessing_mode: str=Query("auto")):
    import cv2
    source = int(url) if url.isdigit() else url
    cap    = cv2.VideoCapture(source)
    if not cap.isOpened(): raise HTTPException(400,f"Cannot open stream: {url}")
    max_f  = int(duration*(cap.get(cv2.CAP_PROP_FPS) or 25))
    return StreamingResponse(_sse_frames(_get_engine(request),cap,max_f,preprocessing_mode),
        media_type="text/event-stream",
        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

class RtspBody(BaseModel):
    stream_url: str; duration_seconds: int=8; sample_rate: int=5

class RtspVerifyBody(BaseModel):
    stream_url: str; timeout_seconds: int=5

@router.post("/rtsp/verify")
async def verify_rtsp(body: RtspVerifyBody):
    """Test if an RTSP/webcam URL is reachable. Returns fps/resolution or error."""
    import cv2, threading, time
    result = {"success": False, "fps": None, "width": None, "height": None, "error": None}

    def _try_open():
        try:
            source = int(body.stream_url) if body.stream_url.isdigit() else body.stream_url
            cap = cv2.VideoCapture(source)
            if not cap.isOpened():
                result["error"] = f"Cannot open stream: {body.stream_url}"
                return
            ret, _ = cap.read()
            if not ret:
                result["error"] = "Stream opened but no frames received"
                cap.release(); return
            result["success"] = True
            result["fps"]    = round(cap.get(cv2.CAP_PROP_FPS) or 0, 1)
            result["width"]  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            result["height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()
        except Exception as e:
            result["error"] = str(e)

    t = threading.Thread(target=_try_open, daemon=True)
    t.start()
    t.join(timeout=body.timeout_seconds)
    if t.is_alive():
        result["error"] = f"Timeout after {body.timeout_seconds}s — check URL/network"
    return result

@router.post("/rtsp")
async def analyze_rtsp(request: Request, body: RtspBody):
    import cv2
    engine = _get_engine(request)
    source = int(body.stream_url) if body.stream_url.isdigit() else body.stream_url
    cap    = cv2.VideoCapture(source)
    if not cap.isOpened(): raise HTTPException(400,f"Cannot open: {body.stream_url}")
    results, history = [], []
    for i in range(int(body.duration_seconds*(cap.get(cv2.CAP_PROP_FPS) or 25))):
        ret, frame = cap.read()
        if not ret: break
        if i % body.sample_rate == 0:
            rd = _result_to_dict(engine.analyze_frame(frame, frame_id=i, history=history, source_type="webcam"))
            results.append(rd); history.append({"total_damage_count":rd.get("total_damage_count",0)})
    cap.release()
    if not results: raise HTTPException(400,"No frames captured")
    last = results[-1]
    return {"type":"rtsp","processed_frames":len(results),
            "average_health_score":round(sum(r["road_health_score"] for r in results)/len(results),1),
            **{k:last.get(k) for k in ["road_health_score","rul_estimate_years","rul_label","rul_risk_band","rul_method","pothole_count",
               "crack_count","total_damage_count","damage_detections","object_detections",
               "severity_distribution","formation_risk","lane_detected","weather_condition",
               "model_used","annotated_image","active_lane_count","damage_coverage_pct","pipeline_timings"]}}

@router.get("/stream/status")
async def stream_status(request: Request):
    engine = _get_engine(request)
    seg   = getattr(request.app.state,"seg_service",None)
    depth = getattr(request.app.state,"depth_service",None)
    rul   = getattr(request.app.state,"rul_service",None)
    fusion= getattr(request.app.state,"fusion",None)
    return {"defect_model":engine._defect_model_label,"object_model":engine._object_model_label,
            "defect_sim":engine._defect_sim,"object_sim":engine._object_sim,
            "segmentation":seg.status if seg else {},"depth":depth.status if depth else {},
            "rul":rul.status if rul else {},"fusion":"active" if fusion else "not_loaded"}

@router.get("/stats")
async def analysis_stats():
    return await get_analysis_stats()

@router.get("/history")
async def get_analysis_history(limit: int = 50):
    try:
        db = await get_db()
        cursor = db.analyses.find().sort("created_at", -1).limit(limit)
        history = docs_to_list(await cursor.to_list(length=limit))
        return {"success": True, "history": history}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.get("/details/{analysis_id}")
async def get_analysis_details(analysis_id: str):
    try:
        db = await get_db()
        doc = await db.analyses.find_one({"id": analysis_id})
        if not doc: raise HTTPException(404, "Analysis not found")
        return {"success": True, "analysis": doc_to_dict(doc)}
    except Exception as e:
        return {"success": False, "error": str(e)}
