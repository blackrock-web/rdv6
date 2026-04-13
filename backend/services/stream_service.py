"""
ROADAI Stream Service v3.5
============================
Hardened streaming pipeline:
  - bounded frame queue
  - stale-frame dropping
  - RTSP reconnect with backoff
  - stream state tracking: connecting | live | degraded | reconnecting | failed
  - safe shutdown
"""
import cv2
import time
import threading
import queue
from typing import Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

from backend.utils.logger import get_logger

logger = get_logger(__name__)


class StreamState(str, Enum):
    IDLE        = "idle"
    CONNECTING  = "connecting"
    LIVE        = "live"
    DEGRADED    = "degraded"
    RECONNECTING= "reconnecting"
    FAILED      = "failed"
    STOPPED     = "stopped"


@dataclass
class StreamStats:
    frames_read:     int   = 0
    frames_dropped:  int   = 0
    frames_processed: int  = 0
    reconnect_count: int   = 0
    state: StreamState     = StreamState.IDLE
    fps_estimate:    float = 0.0
    last_frame_time: float = 0.0
    error:           Optional[str] = None


class HardenedStream:
    """
    Robust stream reader with bounded queue, stale-drop, and RTSP reconnect.
    
    Usage:
        stream = HardenedStream(source=0, max_queue=10, frame_skip=1, reconnect=True)
        stream.start()
        for frame in stream.read_frames():
            ...  # each item is (frame, stats)
        stream.stop()
    """

    def __init__(
        self,
        source,
        max_queue:    int  = 10,
        frame_skip:   int  = 1,
        reconnect:    bool = True,
        max_reconnects: int = 5,
        stale_timeout: float = 8.0,
    ):
        self.source        = source
        self.max_queue     = max_queue
        self.frame_skip    = max(1, frame_skip)
        self.reconnect     = reconnect
        self.max_reconnects = max_reconnects
        self.stale_timeout = stale_timeout

        self._q: queue.Queue = queue.Queue(maxsize=max_queue)
        self._stop_event     = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.stats           = StreamStats()

    def start(self):
        self._stop_event.clear()
        self.stats = StreamStats(state=StreamState.CONNECTING)
        self._thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self.stats.state = StreamState.STOPPED
        if self._thread:
            self._thread.join(timeout=4.0)

    def _open_cap(self):
        """Open the capture source, returning cap or None."""
        cap = cv2.VideoCapture(self.source)
        if not cap.isOpened():
            cap.release()
            return None
        # For RTSP: reduce internal buffer to minimize latency
        if isinstance(self.source, str) and self.source.startswith("rtsp"):
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _reader_loop(self):
        reconnect_count = 0
        backoff = 1.0

        while not self._stop_event.is_set():
            cap = self._open_cap()
            if cap is None:
                self.stats.state = StreamState.FAILED if reconnect_count >= self.max_reconnects else StreamState.RECONNECTING
                self.stats.error = f"Cannot open source: {self.source}"
                logger.warning(f"Stream cannot open {self.source} — reconnect #{reconnect_count}")
                if not self.reconnect or reconnect_count >= self.max_reconnects:
                    self.stats.state = StreamState.FAILED
                    return
                reconnect_count += 1
                self.stats.reconnect_count = reconnect_count
                time.sleep(min(backoff, 15.0))
                backoff *= 1.5
                continue

            logger.info(f"Stream opened: {self.source}")
            self.stats.state = StreamState.LIVE
            self.stats.error = None
            backoff = 1.0
            frame_idx = 0
            fps_window = []

            while not self._stop_event.is_set():
                ret, frame = cap.read()
                if not ret or frame is None:
                    logger.warning("Stream read failure")
                    break

                self.stats.frames_read += 1
                self.stats.last_frame_time = time.time()

                # FPS estimate over rolling window
                fps_window.append(time.time())
                if len(fps_window) > 30:
                    fps_window.pop(0)
                if len(fps_window) >= 2:
                    self.stats.fps_estimate = round((len(fps_window) - 1) / (fps_window[-1] - fps_window[0] + 1e-6), 1)

                # Stream quality tracking
                self.stats.state = (
                    StreamState.LIVE if self.stats.fps_estimate >= 3 or self.stats.fps_estimate == 0
                    else StreamState.DEGRADED
                )

                frame_idx += 1
                if frame_idx % self.frame_skip != 0:
                    continue

                # Bounded queue — drop oldest if full
                if self._q.full():
                    try:
                        self._q.get_nowait()
                        self.stats.frames_dropped += 1
                    except queue.Empty:
                        pass

                try:
                    self._q.put_nowait(frame.copy())
                except queue.Full:
                    self.stats.frames_dropped += 1

            cap.release()
            logger.info("Stream cap released")

            if self._stop_event.is_set():
                break

            if not self.reconnect:
                self.stats.state = StreamState.FAILED
                return

            reconnect_count += 1
            self.stats.reconnect_count = reconnect_count
            if reconnect_count >= self.max_reconnects:
                self.stats.state = StreamState.FAILED
                self.stats.error = f"Max reconnects ({self.max_reconnects}) reached"
                logger.error(self.stats.error)
                return

            self.stats.state = StreamState.RECONNECTING
            logger.info(f"Reconnecting in {backoff:.1f}s (attempt {reconnect_count}/{self.max_reconnects})")
            time.sleep(min(backoff, 15.0))
            backoff = min(backoff * 1.5, 15.0)

        self.stats.state = StreamState.STOPPED

    def read_frames(self, timeout: float = 2.0):
        """Generator — yields (frame, stats) until stopped or stale."""
        while not self._stop_event.is_set():
            try:
                frame = self._q.get(timeout=timeout)
                self.stats.frames_processed += 1
                yield frame, self.stats
            except queue.Empty:
                # Check stale stream
                if (self.stats.last_frame_time > 0 and
                        time.time() - self.stats.last_frame_time > self.stale_timeout):
                    logger.warning("Stream appears stale — no frames received")
                    self.stats.state = StreamState.DEGRADED
                if self.stats.state == StreamState.FAILED:
                    return

    def get_state(self) -> dict:
        return {
            "state":              self.stats.state.value,
            "fps":                self.stats.fps_estimate,
            "frames_read":        self.stats.frames_read,
            "frames_dropped":     self.stats.frames_dropped,
            "frames_processed":   self.stats.frames_processed,
            "reconnect_count":    self.stats.reconnect_count,
            "queue_len":          self._q.qsize(),
            "error":              self.stats.error,
        }
