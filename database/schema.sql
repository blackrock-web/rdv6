-- ROADAI v2 | Database Schema
-- Target: SQLite 3

-- Analysis Records
CREATE TABLE IF NOT EXISTS analyses (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    org_id TEXT,
    input_type TEXT,
    file_path TEXT,
    status TEXT DEFAULT 'pending',
    road_health_score REAL,
    rul_estimate_years REAL,
    pothole_count INTEGER DEFAULT 0,
    crack_count INTEGER DEFAULT 0,
    total_damage INTEGER DEFAULT 0,
    weather_condition TEXT,
    formation_risk TEXT,
    model_used TEXT,
    gps_lat REAL,
    gps_lng REAL,
    processing_ms REAL,
    result_json TEXT,
    annotated_path TEXT,
    created_at REAL DEFAULT (strftime('%s','now'))
);

-- Geographic Events (Detections with location)
CREATE TABLE IF NOT EXISTS geo_events (
    id TEXT PRIMARY KEY,
    analysis_id TEXT,
    latitude REAL,
    longitude REAL,
    severity TEXT,
    pothole_count INTEGER DEFAULT 0,
    crack_count INTEGER DEFAULT 0,
    road_health_score REAL,
    rul_years REAL,
    model_used TEXT,
    source_type TEXT,
    location_label TEXT,
    is_simulated INTEGER DEFAULT 0,
    segment_id TEXT,
    alert_sent INTEGER DEFAULT 0,
    created_at REAL DEFAULT (strftime('%s','now'))
);

-- Maintenance Segments
CREATE TABLE IF NOT EXISTS road_segments (
    id TEXT PRIMARY KEY,
    lat_bucket REAL,
    lon_bucket REAL,
    label TEXT,
    event_count INTEGER DEFAULT 0,
    total_potholes INTEGER DEFAULT 0,
    total_cracks INTEGER DEFAULT 0,
    avg_health REAL DEFAULT 100.0,
    worst_health REAL DEFAULT 100.0,
    worst_severity TEXT DEFAULT 'none',
    avg_rul REAL DEFAULT 10.0,
    last_observed REAL DEFAULT 0,
    maintenance_urgency TEXT DEFAULT 'none',
    trend TEXT DEFAULT 'stable'
);

-- Alerts System
CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY,
    severity TEXT,
    message TEXT,
    pothole_count INTEGER DEFAULT 0,
    crack_count INTEGER DEFAULT 0,
    road_health_score REAL,
    rul_years REAL,
    model_used TEXT,
    location_label TEXT,
    sms_status TEXT DEFAULT 'not_sent',
    sms_sid TEXT,
    sms_error TEXT,
    coordinates TEXT,
    event_type TEXT DEFAULT 'auto',
    created_at REAL DEFAULT (strftime('%s','now'))
);

-- Background Jobs
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    job_type TEXT,
    status TEXT DEFAULT 'queued',
    user_id TEXT,
    file_path TEXT,
    params TEXT,
    result TEXT,
    error TEXT,
    progress INTEGER DEFAULT 0,
    created_at REAL DEFAULT (strftime('%s','now')),
    updated_at REAL DEFAULT (strftime('%s','now')),
    completed_at REAL
);

-- Performance Indices
CREATE INDEX IF NOT EXISTS idx_geo_lat_lon ON geo_events(latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_analyses_user ON analyses(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at);
