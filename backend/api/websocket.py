"""ROADAI WebSocket live streaming."""
import json, base64
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.utils.logger import get_logger
logger = get_logger(__name__)
router = APIRouter()

from backend.core.metrics      import ACTIVE_WS_CONNECTIONS

@router.websocket("/ws/stream")
async def ws_stream(ws: WebSocket):
    ACTIVE_WS_CONNECTIONS.inc()
    try:
        await ws.accept()
        engine = None
        app = ws.app
        engine = getattr(app.state, "engine", None)
        history = []
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            if msg.get("type") != "frame" or not engine:
                await ws.send_text(json.dumps({"type":"error","message":"no engine or bad msg"}))
                continue
            import cv2, numpy as np
            b64 = msg.get("frame","")
            img_bytes = base64.b64decode(b64)
            arr   = np.frombuffer(img_bytes, np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                await ws.send_text(json.dumps({"type":"error","message":"bad frame"}))
                continue
            result = engine.analyze_frame(frame, frame_id=msg.get("frame_id",0), history=history, source_type="websocket")
            d = result.__dict__.copy()
            for k in list(d.keys()):
                if isinstance(d[k], np.ndarray): d[k] = d[k].tolist()
            b64out = d.pop("annotated_image_b64","") or ""
            d["annotated_image"] = f"data:image/jpeg;base64,{b64out}" if b64out else None
            d["type"] = "result"
            history.append({"total_damage_count": d.get("total_damage_count",0)})
            if len(history)>10: history=history[-10:]
            await ws.send_text(json.dumps(d))
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try: await ws.send_text(json.dumps({"type":"error","message":str(e)}))
        except: pass
    finally:
        ACTIVE_WS_CONNECTIONS.dec()
