"""
ROADAI Enterprise Metrics — Prometheus Instrumentation
======================================================
Provides custom gauges and counters for operational observability.
"""
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response

# ── Metrics Definitions ───────────────────────────────────────────────────────

# Total analyses processed by the engine
ANALYSIS_COUNT = Counter(
    "roadai_analysis_total",
    "Total number of road analyses processed",
    ["status", "model_id", "input_type"]
)

# Latency tracking for inference batches
INFERENCE_LATENCY = Histogram(
    "roadai_inference_duration_seconds",
    "Time spent in AI inference pipeline (seconds)",
    ["model_id"],
    buckets=(0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, float("inf"))
)

# Global health score averages
AVG_HEALTH_SCORE = Gauge(
    "roadai_avg_health",
    "Global average road health score (0–100)"
)

# Total defect counts by type and severity
DEFECTS_TOTAL = Counter(
    "roadai_defects_total",
    "Total volume of detected road defects",
    ["defect_type", "severity"]
)

# Active WebSocket connections
ACTIVE_WS_CONNECTIONS = Gauge(
    "roadai_active_ws_connections",
    "Number of active real-time dashboard subscribers"
)

# ── Endpoint Handler ──────────────────────────────────────────────────────────

def metrics_endpoint():
    """Returns Prometheus formatted metrics."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
