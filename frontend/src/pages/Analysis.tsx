import { useState, useRef, useCallback, useEffect } from "react";
import DashboardLayout from "@/components/roadai/DashboardLayout";
import HealthGauge from "@/components/roadai/HealthGauge";
import { api, API_URL } from "@/lib/api";
import { useAppSettings } from "@/lib/AppSettingsContext";
import {
  Upload, Video, Wifi, Play, Loader2, AlertTriangle, CheckCircle, Activity,
  Clock, Route, ShieldX, Car, Eye, Filter, Layers, FileDown, Zap, Info,
  ChevronDown, ChevronUp, X, Cpu, Crosshair, MessageSquare, Signal, MapPin, RefreshCw,
  History as HistoryIcon
} from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

type Mode = "image" | "video" | "rtsp";

const SEV_COLOR: Record<string, string> = {
  critical: "#ef4444", high: "#f97316", medium: "#f59e0b", low: "#10b981",
};
const RISK_BADGE: Record<string, string> = {
  critical: "bg-red-500/15 text-red-400 border-red-500/30",
  high: "bg-orange-500/15 text-orange-400 border-orange-500/30",
  medium: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
  low: "bg-green-500/15 text-green-400 border-green-500/30",
  none: "badge-none",
};
const TT = {
  contentStyle: {
    background: "rgba(8,6,18,0.95)", border: "1px solid rgba(168,85,247,0.25)",
    borderRadius: 8, fontSize: 11, color: "#e2d9f3",
  }
};

const PIPELINE_STAGES = [
  { key: "weather_ms", label: "Weather" }, { key: "lane_ms", label: "Lane" },
  { key: "road_mask_ms", label: "Road Mask" }, { key: "detection_ms", label: "Detection" },
  { key: "filter_ms", label: "Wall Filter" }, { key: "priority_ms", label: "Priority" },
  { key: "objects_ms", label: "Objects" },
];
const STAGE_COLORS = ["#6C63FF", "#10b981", "#f59e0b", "#a855f7", "#ec4899", "#06b6d4", "#ef4444"];

function PipelineBar({ timings }: { timings: Record<string, number> }) {
  const total = Object.values(timings).reduce((a, b) => a + b, 0) || 1;
  return (
    <div className="space-y-1.5">
      {PIPELINE_STAGES.map(({ key, label }, i) => {
        const ms = timings[key] ?? 0;
        return (
          <div key={key} className="flex items-center gap-2 text-[10px]">
            <span className="w-16 text-muted-foreground shrink-0">{label}</span>
            <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: "rgba(168,85,247,0.08)" }}>
              <div className="h-full rounded-full transition-all duration-700"
                style={{ width: `${(ms / total) * 100}%`, background: STAGE_COLORS[i] }} />
            </div>
            <span className="w-12 text-right text-muted-foreground" style={{ fontFamily: "'DM Mono',monospace" }}>{ms}ms</span>
          </div>
        );
      })}
    </div>
  );
}

function DetectionList({ detections }: { detections: any[] }) {
  const [exp, setExp] = useState(false);
  const shown = exp ? detections : detections.slice(0, 5);
  return (
    <div className="space-y-1.5">
      {shown.map((d: any, i: number) => (
        <div key={i} className="flex items-center gap-3 px-3 py-2 rounded-lg transition-all hover:bg-white/3"
          style={{ background: "rgba(168,85,247,0.04)", border: `1px solid ${SEV_COLOR[d.fused_severity || d.severity] || SEV_COLOR.medium}22` }}>
          <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: SEV_COLOR[d.fused_severity || d.severity] || SEV_COLOR.medium }} />
          <div className="flex-1 min-w-0">
            <span className="text-xs font-bold capitalize">{d.class_name || d.damage_type || "damage"}</span>
            {d.priority_label && <span className="text-[9px] text-muted-foreground ml-2">{d.priority_label}</span>}
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            {d.depth_value !== undefined && (
              <span className="text-[9px] text-cyan-400" style={{ fontFamily: "'DM Mono',monospace" }}>d:{d.depth_value?.toFixed(2)}</span>
            )}
            <span className="text-[10px] text-muted-foreground" style={{ fontFamily: "'DM Mono',monospace" }}>{(d.confidence * 100).toFixed(0)}%</span>
            <span className={`text-[9px] px-1.5 py-0.5 rounded badge-${d.fused_severity || d.severity}`}>{d.fused_severity || d.severity}</span>
          </div>
        </div>
      ))}
      {detections.length > 5 && (
        <button onClick={() => setExp(!exp)} className="w-full text-[10px] text-purple-400 hover:text-purple-300 py-1 flex items-center justify-center gap-1">
          {exp ? <><ChevronUp size={10} />Show Less</> : <><ChevronDown size={10} />+{detections.length - 5} more</>}
        </button>
      )}
    </div>
  );
}

// ─── SMS Alert Badge ─────────────────────────────────────────────────────────
function SmsAlertBadge({ sms }: { sms: any }) {
  if (!sms) return null;
  if (sms.sent) return (
    <div className="flex items-center gap-2 px-4 py-3 rounded-xl text-sm font-semibold animate-fade-in"
      style={{ background: "linear-gradient(135deg,rgba(16,185,129,0.15),rgba(168,85,247,0.1))", border: "1px solid rgba(16,185,129,0.4)" }}>
      <MessageSquare size={16} className="text-green-400 flex-shrink-0" />
      <div>
        <div className="text-green-300 font-bold">📲 SMS Alert Sent!</div>
        <div className="text-[11px] text-green-400/70 mt-0.5">Road damage reported to maintenance team via Twilio{sms.sid ? ` · SID: ${sms.sid.slice(-8)}` : ""}</div>
      </div>
    </div>
  );
  if (sms.reason === "not_triggered") return (
    <div className="flex items-center gap-2 px-4 py-3 rounded-xl text-sm"
      style={{ background: "rgba(99,102,241,0.08)", border: "1px solid rgba(99,102,241,0.25)" }}>
      <CheckCircle size={14} className="text-indigo-400 flex-shrink-0" />
      <span className="text-indigo-300 text-xs">Road condition acceptable — no SMS needed (health ≥ 60 &amp; damage &lt; 5)</span>
    </div>
  );
  return (
    <div className="flex items-center gap-2 px-4 py-3 rounded-xl text-sm"
      style={{ background: "rgba(234,179,8,0.08)", border: "1px solid rgba(234,179,8,0.25)" }}>
      <AlertTriangle size={14} className="text-yellow-400 flex-shrink-0" />
      <span className="text-yellow-300 text-xs">SMS not sent: {sms.error || "Twilio not configured"} — <span className="font-bold">Configure in Admin → Twilio</span></span>
    </div>
  );
}

export default function Analysis() {
  const { settings } = useAppSettings();
  const [mode, setMode] = useState<Mode>("image");
  const [file, setFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);   // for images
  const [videoPreview, setVideoPreview] = useState<string | null>(null);   // for videos (objectURL)
  const [rtspUrl, setRtspUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [liveFrame, setLiveFrame] = useState<any>(null);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const [showPipeline, setShowPipeline] = useState(false);
  const [runFusion, setRunFusion] = useState(false);
  const [prepMode, setPrepMode] = useState("auto");
  const [useLane, setUseLane] = useState(true);
  const [dragging, setDragging] = useState(false);

  // GPS state
  const [lat, setLat] = useState<string>("");
  const [lng, setLng] = useState<string>("");
  const [detectingGps, setDetectingGps] = useState(false);
  const [history, setHistory] = useState<any[]>([]);

  const loadLocalHistory = async () => {
    try {
      const res = await api.get("/analysis/history?limit=5");
      if (res.success) setHistory(res.history || []);
    } catch (e) { console.error("Failed to load local history", e); }
  };

  useEffect(() => {
    loadLocalHistory();
  }, []);

  // RTSP verify state
  const [rtspVerifying, setRtspVerifying] = useState(false);
  const [rtspStatus, setRtspStatus] = useState<any>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const streamRef = useRef<EventSource | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const stopStream = () => {
    if (streamRef.current) { streamRef.current.close(); streamRef.current = null; }
    if (abortRef.current) { abortRef.current.abort(); abortRef.current = null; }
  };

  const [toast, setToast] = useState<{ msg: string, type: "success" | "error" | "info" } | null>(null);

  useEffect(() => {
    if (toast) {
      const t = setTimeout(() => setToast(null), 3000);
      return () => clearTimeout(t);
    }
  }, [toast]);

  const detectGps = () => {
    if (!navigator.geolocation) return;
    setDetectingGps(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLat(pos.coords.latitude.toFixed(6));
        setLng(pos.coords.longitude.toFixed(6));
        setDetectingGps(false);
        setToast({ msg: "Location detected successfully!", type: "success" });
      },
      () => {
        setError("GPS detection failed. Please enter manually.");
        setDetectingGps(false);
        setToast({ msg: "GPS Failure: Accuracy unavailable", type: "error" });
      }
    );
  };

  const handleFile = useCallback((f: File) => {
    stopStream();
    setFile(f); setResult(null); setLiveFrame(null); setProgress(0); setError("");
    // Always create objectURL for video so the original panel plays
    if (f.type.startsWith("image/")) {
      setImagePreview(URL.createObjectURL(f));
      setVideoPreview(null);
    } else {
      setVideoPreview(URL.createObjectURL(f));
      setImagePreview(null);
    }
  }, []);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setDragging(false);
    if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
  }, [handleFile]);

  // ── RTSP Verify ──
  const verifyRtsp = async () => {
    if (!rtspUrl.trim()) return;
    setRtspVerifying(true); setRtspStatus(null);
    try {
      const r = await api.post("/analysis/rtsp/verify", { stream_url: rtspUrl, timeout_seconds: 5 });
      setRtspStatus(r);
    } catch (e: any) {
      setRtspStatus({ success: false, error: e.message || "Network error" });
    } finally {
      setRtspVerifying(false);
    }
  };

  const run = async () => {
    stopStream();
    setLoading(true); setError(""); setResult(null); setLiveFrame(null); setProgress(0);
    try {
      if (mode === "image") {
        const fd = new FormData();
        fd.append("file", file!);
        fd.append("preprocessing_mode", prepMode);
        fd.append("run_fusion", String(runFusion));
        if (lat) fd.append("latitude", lat);
        if (lng) fd.append("longitude", lng);
        const r = await api.postForm("/analysis/image", fd);
        setResult(r); setLoading(false);
      } else if (mode === "video") {
        const fd = new FormData();
        fd.append("file", file!);
        fd.append("preprocessing_mode", prepMode);
        fd.append("sample_rate", "1");
        fd.append("use_lane", String(useLane));
        if (lat) fd.append("latitude", lat);
        if (lng) fd.append("longitude", lng);

        const ctrl = new AbortController();
        abortRef.current = ctrl;

        const resp = await fetch(`${API_URL}/api/analysis/video/stream`, { method: "POST", body: fd, signal: ctrl.signal });
        if (!resp.ok) throw new Error(`Server error ${resp.status}`);

        const reader = resp.body!.getReader();
        const decoder = new TextDecoder();
        let buf = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const lines = buf.split("\n");
          buf = lines.pop()!;
          for (const line of lines) {
            if (!line.startsWith("data:")) continue;
            try {
              const data = JSON.parse(line.slice(5).trim());
              if (data.type === "frame") {
                setLiveFrame(data);
                setProgress(data.progress ?? 0);
              } else if (data.type === "complete") {
                setResult(data); setLiveFrame(null); setProgress(100); setLoading(false);
                setToast({ msg: "Analysis Complete!", type: "success" });
                loadLocalHistory();
              } else if (data.error) {
                setError(data.error); setLoading(false);
                setToast({ msg: data.error, type: "error" });
              }
            } catch { }
          }
        }
        setLoading(false);
      } else {
        // RTSP / Webcam SSE
        const isWebcam = rtspUrl === "0" || /^\d+$/.test(rtspUrl);
        let url = isWebcam
          ? `${API_URL}/api/analysis/stream/webcam?device=${rtspUrl}&preprocessing_mode=${prepMode}`
          : `${API_URL}/api/analysis/stream/rtsp?url=${encodeURIComponent(rtspUrl)}&preprocessing_mode=${prepMode}`;

        if (lat) url += `&latitude=${lat}`;
        if (lng) url += `&longitude=${lng}`;

        const es = new EventSource(url);
        streamRef.current = es;
        es.onmessage = (e) => {
          try {
            const data = JSON.parse(e.data);
            if (data.status === "stream_complete" || data.error) { stopStream(); if (data.error) setError(data.error); setLoading(false); }
            else { setResult(data); setLoading(false); }
          } catch { }
        };
        es.onerror = () => {
          stopStream();
          setError("Stream connection failed");
          setLoading(false);
          setToast({ msg: "RTSP Connection Failed", type: "error" });
        };
      }
    } catch (e: any) {
      if (e.name !== "AbortError") {
        setError(e.message || "Analysis failed");
        setToast({ msg: e.message || "Analysis failed", type: "error" });
      }
      setLoading(false);
    }
  };

  const exportJSON = () => {
    if (!result) return;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], { type: "application/json" }));
    a.download = `roadai_${Date.now()}.json`; a.click();
  };

  const display = liveFrame || result;
  const r = result;
  const health = display?.road_health_score ?? display?.average_health_score ?? 100;
  const sevDist = display?.severity_distribution || { low: 0, medium: 0, high: 0, critical: 0 };
  const sevData = Object.entries(sevDist).map(([k, v]) => ({ name: k.toUpperCase(), count: v as number, fill: SEV_COLOR[k] }));
  const allDets = display?.fused_detections || display?.damage_detections || [];
  const liveAnnotated = liveFrame?.annotated_image;

  return (
    <DashboardLayout>
      <div className="grid grid-cols-1 xl:grid-cols-5 gap-5 animate-fade-in">
        {/* ── LEFT — Input ── */}
        <div className="xl:col-span-2 space-y-4">
          <div>
            <h1 className="text-xl font-black gradient-text">AI ANALYSIS</h1>
            <p className="text-xs text-muted-foreground mt-0.5">Image · Video · RTSP Stream · Auto SMS Alert</p>
          </div>

          {/* Mode selector */}
          <div className="glass rounded-xl p-1 flex gap-1">
            {([["image", "Image", Upload], ["video", "Video", Video], ["rtsp", "RTSP", Wifi]] as const).map(([m, l, Icon]) => (
              <button key={m} onClick={() => setMode(m)}
                className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-lg text-xs font-bold tracking-wider transition-all ${mode === m ? "btn-solid" : "text-muted-foreground hover:text-foreground"}`}>
                <Icon size={12} />{l}
              </button>
            ))}
          </div>

          {/* Upload zone */}
          {(mode === "image" || mode === "video") && (
            <div
              onDrop={onDrop} onDragOver={e => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)}
              onClick={() => inputRef.current?.click()}
              className="rounded-xl p-6 text-center cursor-pointer transition-all border-2 border-dashed"
              style={{ borderColor: dragging ? "rgba(168,85,247,0.6)" : file ? "rgba(168,85,247,0.35)" : "rgba(168,85,247,0.15)", background: dragging ? "rgba(168,85,247,0.06)" : file ? "rgba(168,85,247,0.03)" : "rgba(0,0,0,0.2)" }}>
              <input ref={inputRef} type="file" className="hidden"
                accept={mode === "image" ? "image/*" : "video/*"}
                onChange={e => { if (e.target.files?.[0]) handleFile(e.target.files[0]); }} />
              {file ? (
                <div>
                  {imagePreview && <img src={imagePreview} alt="preview" className="mx-auto mb-2 rounded-lg max-h-32 object-contain" />}
                  {videoPreview && (
                    <video src={videoPreview} muted playsInline className="mx-auto mb-2 rounded-lg max-h-32 object-contain" />
                  )}
                  <div className="text-xs font-semibold text-purple-300">{file.name}</div>
                  <div className="text-[10px] text-muted-foreground mt-0.5">{(file.size / 1024 / 1024).toFixed(2)} MB · {mode}</div>
                  <button onClick={e => { e.stopPropagation(); setFile(null); setImagePreview(null); setVideoPreview(null); }}
                    className="mt-2 text-[10px] text-red-400 hover:text-red-300 flex items-center gap-1 mx-auto">
                    <X size={10} />Remove
                  </button>
                </div>
              ) : (
                <div>
                  <Upload size={24} className="mx-auto mb-2 text-purple-400 opacity-50" />
                  <div className="text-sm font-semibold text-muted-foreground">Drop {mode} here</div>
                  <div className="text-[10px] text-muted-foreground mt-1">{mode === "image" ? "JPG, PNG, BMP" : "MP4, AVI, MOV"} · Max 500MB</div>
                </div>
              )}
            </div>
          )}

          {/* RTSP URL + Verify */}
          {mode === "rtsp" && (
            <div className="space-y-2">
              <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">RTSP URL or Webcam Index</label>
              <input value={rtspUrl} onChange={e => { setRtspUrl(e.target.value); setRtspStatus(null); }}
                placeholder="rtsp://... or 0 (webcam)"
                className="w-full px-4 py-3 rounded-xl text-sm outline-none transition-all"
                style={{ background: "rgba(168,85,247,0.06)", border: "1px solid rgba(168,85,247,0.2)", color: "#e2d9f3", fontFamily: "'DM Mono',monospace" }}
                onFocus={e => { e.target.style.borderColor = "rgba(168,85,247,0.5)"; }}
                onBlur={e => { e.target.style.borderColor = "rgba(168,85,247,0.2)"; }} />
              <button onClick={verifyRtsp} disabled={!rtspUrl.trim() || rtspVerifying}
                className="w-full py-2 rounded-xl text-xs font-bold flex items-center justify-center gap-2 transition-all disabled:opacity-40"
                style={{ background: "rgba(6,182,212,0.1)", border: "1px solid rgba(6,182,212,0.3)", color: "#67e8f9" }}>
                {rtspVerifying ? <><Loader2 size={12} className="animate-spin" />Testing Connection…</> : <><Signal size={12} />Test Connection</>}
              </button>
              {rtspStatus && (
                <div className={`px-3 py-2 rounded-xl text-xs flex items-center gap-2 animate-fade-in ${rtspStatus.success
                  ? "bg-green-500/10 border border-green-500/30 text-green-300"
                  : "bg-red-500/10 border border-red-500/30 text-red-300"}`}>
                  {rtspStatus.success
                    ? <><CheckCircle size={12} />Connected — {rtspStatus.width}×{rtspStatus.height} @ {rtspStatus.fps}fps</>
                    : <><AlertTriangle size={12} />{rtspStatus.error}</>}
                </div>
              )}
            </div>
          )}

          {/* Location / GPS */}
          {settings.gps_tracking_enabled && (
            <div className="glass rounded-xl p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Location (Optional)</div>
                <button onClick={detectGps} disabled={detectingGps}
                  className="text-[10px] text-purple-400 hover:text-purple-300 flex items-center gap-1">
                  {detectingGps ? <Loader2 size={10} className="animate-spin" /> : <MapPin size={10} />}
                  {detectingGps ? "Detecting..." : "Auto-detect GPS"}
                </button>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[10px] text-muted-foreground mb-1 block">Latitude</label>
                  <input value={lat} onChange={e => setLat(e.target.value)} placeholder="0.000000"
                    className="w-full px-3 py-2 rounded-lg text-xs outline-none bg-secondary/50 border border-border" />
                </div>
                <div>
                  <label className="text-[10px] text-muted-foreground mb-1 block">Longitude</label>
                  <input value={lng} onChange={e => setLng(e.target.value)} placeholder="0.000000"
                    className="w-full px-3 py-2 rounded-lg text-xs outline-none bg-secondary/50 border border-border" />
                </div>
              </div>
            </div>
          )}

          {/* Options */}
          <div className="glass rounded-xl p-4 space-y-3">
            <div className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Analysis Options</div>
            <div>
              <label className="text-[10px] text-muted-foreground mb-1 block">Preprocessing Mode</label>
              <select value={prepMode} onChange={e => setPrepMode(e.target.value)}
                className="w-full px-3 py-2 rounded-lg text-xs outline-none"
                style={{ background: "rgba(168,85,247,0.06)", border: "1px solid rgba(168,85,247,0.15)", color: "#e2d9f3" }}>
                {["auto", "none", "clahe", "gamma", "dehaze", "low-light", "denoise"].map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
            <label className="flex items-center gap-2 cursor-pointer">
              <div onClick={() => setRunFusion(!runFusion)}
                className={`w-9 h-5 rounded-full transition-all relative ${runFusion ? "bg-purple-500" : "bg-secondary"}`}>
                <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all`} style={{ left: runFusion ? "18px" : "2px" }} />
              </div>
              <span className="text-xs text-muted-foreground">Enable Fusion (Seg+Depth+RUL)</span>
              <span className="text-[9px] text-cyan-400 ml-auto">+DeepLab+MiDaS</span>
            </label>
            {/* Lane toggle */}
            <label className="flex items-center gap-2 cursor-pointer">
              <div onClick={() => setUseLane(!useLane)}
                className={`w-9 h-5 rounded-full transition-all relative ${useLane ? "bg-green-500" : "bg-secondary"}`}>
                <div className="absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all" style={{ left: useLane ? "18px" : "2px" }} />
              </div>
              <span className="text-xs text-muted-foreground">Lane Detection</span>
              <span className={`text-[9px] ml-auto font-bold ${useLane ? "text-green-400" : "text-muted-foreground"}`}>
                {useLane ? "ON — priority filter active" : "OFF — raw detection"}
              </span>
            </label>
            {/* Auto-SMS notice */}
            <div className="flex items-start gap-2 px-3 py-2 rounded-lg" style={{ background: "rgba(236,72,153,0.06)", border: "1px solid rgba(236,72,153,0.2)" }}>
              <MessageSquare size={11} className="text-pink-400 flex-shrink-0 mt-0.5" />
              <span className="text-[10px] text-pink-300/80">Auto SMS alert will be sent via Twilio if health &lt; 60 or damage ≥ 5</span>
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="px-3 py-2 rounded-xl text-xs flex items-center gap-2"
              style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", color: "#f87171" }}>
              <AlertTriangle size={12} />{error}
            </div>
          )}

          {/* Run button */}
          <div className="flex gap-2">
            <button onClick={run} disabled={loading || !!streamRef.current || !!abortRef.current || (mode !== "rtsp" && !file) || (mode === "rtsp" && !rtspUrl)}
              className="flex-1 py-3.5 rounded-xl btn-solid text-sm font-black tracking-widest disabled:opacity-40 flex items-center justify-center gap-2">
              {(loading || !!streamRef.current || !!abortRef.current) && !streamRef.current && !abortRef.current ? <><Loader2 size={15} className="animate-spin" />PROCESSING…</> : <><Zap size={15} />RUN AI ANALYSIS</>}
            </button>
            {(loading || !!streamRef.current || !!abortRef.current) && (
              <button onClick={() => { stopStream(); setLoading(false); }} className="px-6 py-3.5 rounded-xl bg-red-500/20 text-red-500 text-sm font-black border border-red-500/50 hover:bg-red-500/30 transition-colors">
                STOP
              </button>
            )}
          </div>

          <div className="flex gap-2">
            <a href={`${API_URL}/api/analysis/stream/webcam?device=0`} target="_blank"
              className="flex-1 py-2 rounded-lg btn-neon text-[10px] font-bold text-center tracking-wider">📷 WEBCAM SSE</a>
            <a href={`${API_URL}/docs`} target="_blank"
              className="flex-1 py-2 rounded-lg btn-neon text-[10px] font-bold text-center tracking-wider">📖 API DOCS</a>
          </div>

          {/* Recent History Sidebar Card */}
          <div className="glass rounded-xl p-4 space-y-3">
            <div className="flex items-center justify-between border-b border-border/50 pb-2">
              <div className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest flex items-center gap-1.5">
                <HistoryIcon size={12} className="text-purple-400" /> RECENT SCANS
              </div>
              <button onClick={loadLocalHistory} className="p-1 hover:bg-white/5 rounded text-muted-foreground">
                <RefreshCw size={10} className={loading ? "animate-spin" : ""} />
              </button>
            </div>
            <div className="space-y-2">
              {history.length === 0 ? (
                <p className="text-[10px] text-muted-foreground py-2 text-center italic">No recent scans found</p>
              ) : (
                history.map((h, i) => (
                  <button key={h.id}
                    onClick={() => {
                      setResult(h.metadata || h);
                      setImagePreview(h.annotated_path?.includes(".jpg") ? h.annotated_path : null);
                      setVideoPreview(h.annotated_path?.includes(".mp4") ? h.annotated_path : null);
                    }}
                    className="w-full text-left p-2 rounded-lg bg-secondary/20 border border-border/30 hover:bg-secondary/40 transition-all group">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[10px] font-bold text-purple-200 uppercase truncate">
                        {h.input_type} · {h.id.slice(0, 8)}
                      </span>
                      <span className="text-[9px] font-mono text-muted-foreground">
                        {new Date(h.created_at * 1000).toLocaleDateString()}
                      </span>
                    </div>
                    <div className="flex items-center justify-between mt-1">
                      <div className="flex gap-2">
                        <span className="text-[9px] text-red-400">P:{h.pothole_count}</span>
                        <span className="text-[9px] text-pink-400">C:{h.crack_count}</span>
                      </div>
                      <span className="text-[10px] font-black text-purple-400 group-hover:text-purple-300">
                        {Math.round(h.road_health_score)}%
                      </span>
                    </div>
                  </button>
                ))
              )}
            </div>
          </div>
        </div>

        {/* ── RIGHT — Results ── */}
        <div className="xl:col-span-3 space-y-4">
          {!display && !loading && (
            <div className="glass rounded-xl p-12 flex flex-col items-center justify-center text-center h-full min-h-[400px]"
              style={{ border: "2px dashed rgba(168,85,247,0.15)" }}>
              <Crosshair size={40} className="text-purple-400 opacity-30 mb-4 animate-pulse" />
              <p className="text-sm font-semibold text-muted-foreground">Ready for Analysis</p>
              <p className="text-xs text-muted-foreground mt-1 max-w-xs">Upload an image or video, or connect an RTSP stream to run the AI pipeline</p>
              <div className="mt-6 grid grid-cols-3 gap-3 text-[10px] text-muted-foreground">
                {[["YOLO Detection", "best.pt model"], ["DeepLab Seg", "Road mask"], ["MiDaS Depth", "Severity est."], ["Lane Filter", "Active lane"], ["Wall Filter", "Non-road drop"], ["XGBoost RUL", "Life estimate"]].map(([t, s]) => (
                  <div key={t} className="px-2 py-2 rounded-lg text-center" style={{ background: "rgba(168,85,247,0.04)", border: "1px solid rgba(168,85,247,0.08)" }}>
                    <div className="font-bold text-purple-400/70">{t}</div>
                    <div className="mt-0.5">{s}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── LIVE STREAMING PANEL ── */}
          {liveFrame && (
            <div className="space-y-3 animate-fade-in">
              {/* Progress */}
              <div className="glass rounded-xl p-3">
                <div className="flex items-center justify-between text-[10px] mb-2">
                  <span className="font-bold gradient-text flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-purple-400 animate-pulse block" />
                    LIVE AI PROCESSING
                  </span>
                  <span className="text-muted-foreground" style={{ fontFamily: "'DM Mono',monospace" }}>
                    Frame {liveFrame.frame_id} / {liveFrame.total_frames} · {progress.toFixed(1)}%
                  </span>
                </div>
                <div className="h-2 rounded-full overflow-hidden" style={{ background: "rgba(168,85,247,0.1)" }}>
                  <div className="h-full rounded-full transition-all duration-300"
                    style={{ width: `${progress}%`, background: "linear-gradient(90deg,#6C63FF,#a855f7,#ec4899)" }} />
                </div>
              </div>

              {/* Live KPIs */}
              <div className="grid grid-cols-4 gap-2">
                {[
                  { label: "Health", value: `${Math.round(liveFrame.road_health_score ?? 100)}/100`, color: liveFrame.road_health_score >= 70 ? "#10b981" : liveFrame.road_health_score >= 50 ? "#f59e0b" : "#ef4444" },
                  { label: "Potholes", value: liveFrame.pothole_count ?? 0, color: "#ef4444" },
                  { label: "Cracks", value: liveFrame.crack_count ?? 0, color: "#ec4899" },
                  { label: "Risk", value: (liveFrame.formation_risk ?? "-").toUpperCase(), color: "#a855f7" },
                ].map(({ label, value, color }) => (
                  <div key={label} className="glass rounded-xl p-2 text-center">
                    <div className="text-lg font-black animate-number" style={{ color }}>{value}</div>
                    <div className="text-[9px] text-muted-foreground">{label}</div>
                  </div>
                ))}
              </div>

              {/* ★ Dual video panel during streaming */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="glass-panel rounded-xl overflow-hidden relative flex items-center justify-center bg-black/40 min-h-[260px]">
                  {videoPreview
                    ? <video src={videoPreview} muted loop autoPlay className="w-full h-[260px] object-contain" />
                    : <div className="text-muted-foreground text-xs">Original</div>}
                  <div className="absolute top-2 left-2 px-2 py-1 rounded text-[10px] font-bold tracking-widest bg-black/70 border border-white/10 text-white">ORIGINAL</div>
                </div>
                <div className="glass-panel rounded-xl overflow-hidden relative flex items-center justify-center bg-black/40 min-h-[260px]"
                  style={{ boxShadow: "0 0 30px rgba(168,85,247,0.2)" }}>
                  {liveAnnotated
                    ? <img src={liveAnnotated} alt="live annotated" className="w-full h-[260px] object-contain" />
                    : <div className="text-muted-foreground text-xs animate-pulse">Processing frame…</div>}
                  <div className="absolute top-2 right-2 px-2 py-1 rounded text-[10px] font-bold bg-purple-900/60 border border-purple-500/50 text-purple-200 flex gap-1.5 items-center">
                    <span className="animate-glow w-1.5 h-1.5 rounded-full bg-purple-400 block" />LIVE AI
                  </div>
                </div>
              </div>

              {allDets.length > 0 && (
                <div className="glass rounded-xl p-3">
                  <div className="text-[10px] font-bold text-muted-foreground uppercase mb-2 flex items-center gap-2">
                    <Crosshair size={11} className="text-purple-400" /> {allDets.length} DETECTIONS (LIVE)
                  </div>
                  <DetectionList detections={allDets.slice(0, 5)} />
                </div>
              )}
            </div>
          )}

          {/* Image processing loader */}
          {loading && !liveFrame && (
            <div className="glass rounded-xl p-12 flex flex-col items-center justify-center min-h-[400px]">
              <div className="relative mb-6">
                <div className="w-16 h-16 rounded-full border-2 border-purple-400/20 flex items-center justify-center">
                  <Loader2 size={28} className="animate-spin text-purple-400" />
                </div>
                <div className="absolute inset-0 rounded-full border border-purple-400/30 animate-ping" />
              </div>
              <p className="text-sm font-bold gradient-text">AI Pipeline Running</p>
              <p className="text-xs text-muted-foreground mt-2">YOLO → Wall Filter → Lane Priority → XGBoost RUL</p>
              <div className="mt-6 flex gap-1">
                {["Weather", "Lane", "Mask", "Detection", "Filter", "Priority", "Objects"].map((s, i) => (
                  <div key={s} className="w-1.5 h-6 rounded-full animate-glow"
                    style={{ background: `rgba(168,85,247,${0.3 + i * 0.1})`, animationDelay: `${i * 0.15}s` }} />
                ))}
              </div>
            </div>
          )}

          {/* ── FINAL RESULT PANEL ── */}
          {r && !liveFrame && (
            <div className="space-y-4 animate-slide-up">
              {/* ★ Dual video panel — original + annotated */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="glass-panel rounded-xl overflow-hidden relative flex items-center justify-center bg-black/40 min-h-[300px]">
                  {videoPreview ? (
                    <video src={videoPreview} controls autoPlay muted loop className="w-full h-[400px] object-contain" />
                  ) : imagePreview ? (
                    <img src={imagePreview} className="w-full h-[400px] object-contain" alt="original" />
                  ) : (
                    <div className="text-muted-foreground text-xs flex flex-col items-center">
                      <Wifi size={24} className="mb-2 opacity-50" /><span>Original Stream</span>
                    </div>
                  )}
                  <div className="absolute top-2 left-2 px-2 py-1 rounded text-[10px] font-bold tracking-widest bg-black/70 border border-white/10 text-white backdrop-blur">ORIGINAL INPUT</div>
                </div>

                <div className="glass-panel rounded-xl overflow-hidden relative flex items-center justify-center bg-black/40 min-h-[300px]"
                  style={{ boxShadow: "0 0 30px rgba(168,85,247,0.15)" }}>
                  {r.annotated_video_url ? (
                    <video src={r.annotated_video_url} controls autoPlay muted loop className="w-full h-[400px] object-contain" />
                  ) : r.annotated_image ? (
                    <img src={r.annotated_image} className="w-full h-[400px] object-contain" alt="annotated" />
                  ) : (
                    <div className="text-muted-foreground text-xs animate-pulse">Awaiting Pipeline…</div>
                  )}
                  <div className="absolute top-2 right-2 px-2 py-1 rounded text-[10px] font-bold tracking-widest bg-purple-900/60 border border-purple-500/50 text-purple-200 backdrop-blur z-10 flex gap-2 items-center">
                    {progress === 100 && <CheckCircle size={10} className="text-green-400" />}
                    <span className="animate-glow w-1.5 h-1.5 rounded-full bg-purple-400 block" />AI OUTPUT
                  </div>
                </div>
              </div>

              {/* ★ Analysis Complete Card */}
              {r.type === "complete" && (
                <div className="rounded-xl p-5 border animate-slide-up space-y-4"
                  style={{
                    background: r.road_health_score < 60
                      ? "linear-gradient(135deg,rgba(239,68,68,0.12),rgba(236,72,153,0.08))"
                      : "linear-gradient(135deg,rgba(16,185,129,0.08),rgba(168,85,247,0.06))",
                    borderColor: r.road_health_score < 60 ? "rgba(239,68,68,0.35)" : "rgba(16,185,129,0.3)"
                  }}>
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-black gradient-text flex items-center gap-2">
                      <CheckCircle size={14} className="text-green-400" />
                      ANALYSIS COMPLETE
                    </h3>
                    <span className="text-[10px] text-muted-foreground" style={{ fontFamily: "'DM Mono',monospace" }}>
                      {r.processed_frames} frames / {r.total_frames} total
                    </span>
                  </div>

                  {/* Big KPIs */}
                  <div className="grid grid-cols-4 gap-2">
                    {[
                      { label: "Potholes", value: r.pothole_count ?? 0, color: "#ef4444", icon: "🕳️" },
                      { label: "Cracks", value: r.crack_count ?? 0, color: "#ec4899", icon: "⚡" },
                      { label: "Health", value: `${Math.round(r.road_health_score ?? 100)}/100`, color: r.road_health_score >= 70 ? "#10b981" : r.road_health_score >= 50 ? "#f59e0b" : "#ef4444", icon: "❤️" },
                      { label: "RUL", value: `${r.rul_estimate_years?.toFixed(1) ?? 10}y`, color: "#a855f7", icon: "⏳" },
                    ].map(({ label, value, color, icon }) => (
                      <div key={label} className="glass rounded-xl p-2.5 text-center">
                        <div className="text-lg mb-0.5">{icon}</div>
                        <div className="text-xl font-black animate-number" style={{ color }}>{value}</div>
                        <div className="text-[9px] text-muted-foreground mt-0.5">{label}</div>
                      </div>
                    ))}
                  </div>

                  {/* Risk row */}
                  <div className="flex items-center gap-3 flex-wrap">
                    <span className={`text-[10px] px-2 py-1 rounded-full border font-bold ${RISK_BADGE[r.formation_risk] || RISK_BADGE.none}`}>
                      Formation Risk: {(r.formation_risk || "none").toUpperCase()}
                    </span>
                    <span className="text-[10px] text-muted-foreground">Total defects: <span className="font-bold text-white">{(r.pothole_count ?? 0) + (r.crack_count ?? 0)}</span></span>
                    {r.weather_condition && <span className="text-[10px] text-muted-foreground">Weather: <span className="text-white">{r.weather_condition.replace("_", " ")}</span></span>}
                    {/* Lane status badge */}
                    <span className={`text-[10px] px-2 py-1 rounded-full border font-bold ${useLane ? "bg-green-500/15 text-green-400 border-green-500/30" : "badge-none"}`}>
                      Lane: {useLane ? "ON ✓" : "OFF"}
                    </span>
                  </div>

                  {/* ★ SMS Alert Status */}
                  <SmsAlertBadge sms={r.sms_alert} />
                </div>
              )}

              {/* Top metrics */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                  { label: "Health Score", value: `${Math.round(health)}/100`, color: health >= 70 ? "#10b981" : health >= 50 ? "#f59e0b" : "#ef4444" },
                  { label: "Potholes", value: r.pothole_count ?? 0, color: "#ef4444" },
                  { label: "Cracks", value: r.crack_count ?? 0, color: "#ec4899" },
                  { label: "RUL Estimate", value: `${r.rul_estimate_years?.toFixed(1) ?? 10}y`, color: "#a855f7" },
                ].map(({ label, value, color }) => (
                  <div key={label} className="glass rounded-xl p-3 text-center">
                    <div className="text-xl font-black animate-number" style={{ color }}>{value}</div>
                    <div className="text-[10px] text-muted-foreground mt-0.5">{label}</div>
                  </div>
                ))}
              </div>

              {/* Health + summary */}
              <div className="grid grid-cols-3 gap-4">
                <div className="glass rounded-xl p-4 flex items-center justify-center">
                  <HealthGauge score={health} size={100} />
                </div>
                <div className="glass rounded-xl p-4 col-span-2 space-y-2.5">
                  <div className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Analysis Summary</div>
                  {[
                    ["Formation Risk", r.formation_risk, RISK_BADGE[r.formation_risk] || RISK_BADGE.none],
                    ["Weather", r.weather_condition?.replace("_", " ") || "unknown", "badge-none"],
                    ["Lane Detected", r.lane_detected ? "Yes" : "No", r.lane_detected ? "badge-low" : "badge-none"],
                    ["Wall Filtered", `${r.wall_filtered_count ?? 0} removed`, "badge-none"],
                    ["Active Lane Hits", `${r.active_lane_count ?? 0}`, "badge-medium"],
                  ].map(([k, v, cls]) => (
                    <div key={k as string} className="flex items-center justify-between text-xs">
                      <span className="text-muted-foreground">{k}</span>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${cls}`}>{v}</span>
                    </div>
                  ))}
                  {r.rul_label && (
                    <div className="text-[10px] mt-1 px-2 py-1.5 rounded-lg" style={{ background: "rgba(168,85,247,0.06)", border: "1px solid rgba(168,85,247,0.12)", color: "#c084fc" }}>
                      💡 {r.rul_label}
                    </div>
                  )}
                </div>
              </div>

              {/* Severity chart */}
              {Object.values(sevDist).some((v: any) => v > 0) && (
                <div className="glass rounded-xl p-4">
                  <div className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider mb-3">Severity Distribution</div>
                  <ResponsiveContainer width="100%" height={80}>
                    <BarChart data={sevData} barSize={32}>
                      <CartesianGrid strokeDasharray="2 4" stroke="rgba(168,85,247,0.07)" />
                      <XAxis dataKey="name" tick={{ fill: "rgba(180,160,220,0.5)", fontSize: 9 }} stroke="none" />
                      <YAxis tick={{ fill: "rgba(180,160,220,0.5)", fontSize: 9 }} stroke="none" />
                      <Tooltip {...TT} />
                      <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                        {sevData.map((d, i) => <rect key={i} fill={d.fill} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Detections */}
              {allDets.length > 0 && (
                <div className="glass rounded-xl p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                      <Crosshair size={11} className="text-purple-400" />
                      {allDets.length} DETECTIONS {r.fusion_applied ? "(FUSED)" : ""}
                    </div>
                    {r.removed_by_seg > 0 && (
                      <span className="text-[9px] text-cyan-400" style={{ fontFamily: "'DM Mono',monospace" }}>-{r.removed_by_seg} removed by seg</span>
                    )}
                  </div>
                  <DetectionList detections={allDets} />
                </div>
              )}

              {/* Objects */}
              {r.object_detections?.length > 0 && (
                <div className="glass rounded-xl p-4">
                  <div className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider mb-2 flex items-center gap-2">
                    <Car size={11} className="text-cyan-400" />SCENE OBJECTS ({r.object_detections.length})
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {r.object_detections.map((o: any, i: number) => (
                      <span key={i} className="px-2 py-1 rounded-lg text-[10px] font-semibold"
                        style={{ background: "rgba(6,182,212,0.08)", border: "1px solid rgba(6,182,212,0.2)", color: "#67e8f9" }}>
                        {o.class} {(o.confidence * 100).toFixed(0)}%
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Pipeline timing */}
              {r.pipeline_timings && Object.keys(r.pipeline_timings).length > 0 && (
                <div className="glass rounded-xl p-4">
                  <button onClick={() => setShowPipeline(!showPipeline)}
                    className="flex items-center gap-2 w-full text-[10px] font-bold text-muted-foreground uppercase tracking-wider">
                    <Activity size={11} className="text-purple-400" />
                    Pipeline Timings ({r.processing_time_ms?.toFixed(0) || 0}ms total)
                    {showPipeline ? <ChevronUp size={10} className="ml-auto" /> : <ChevronDown size={10} className="ml-auto" />}
                  </button>
                  {showPipeline && <div className="mt-3"><PipelineBar timings={r.pipeline_timings} /></div>}
                </div>
              )}

              {/* Footer */}
              <div className="glass rounded-xl p-3 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Cpu size={12} className="text-purple-400" />
                  <span className="text-[10px] text-muted-foreground">Model:</span>
                  <span className="text-[10px] font-bold text-purple-300" style={{ fontFamily: "'DM Mono',monospace" }}>{r.model_used || "unknown"}</span>
                </div>
                <div className="flex gap-2">
                  <button onClick={exportJSON} className="flex items-center gap-1 px-3 py-1.5 rounded-lg btn-neon text-[10px] font-bold">
                    <FileDown size={10} />JSON
                  </button>
                  <button onClick={async () => {
                    const res = await api.post("/reports/generate", { analysis_data: r }).catch(() => null);
                    if (res?.pdf_path || res?.json_path) alert(`Report saved: ${res.pdf_path || res.json_path}`);
                  }} className="flex items-center gap-1 px-3 py-1.5 rounded-lg btn-solid text-[10px] font-bold">
                    <FileDown size={10} />PDF
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── TOAST OVERLAY ── */}
      {toast && (
        <div className="fixed bottom-6 right-6 z-50 animate-slide-up">
          <div className={`px-5 py-3 rounded-2xl shadow-2xl flex items-center gap-3 backdrop-blur-xl border ${toast.type === "success" ? "bg-green-500/10 border-green-500/30 text-green-400" :
              toast.type === "error" ? "bg-red-500/10 border-red-500/30 text-red-400" :
                "bg-purple-500/10 border-purple-500/30 text-purple-300"
            }`}>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center ${toast.type === "success" ? "bg-green-500/20" :
                toast.type === "error" ? "bg-red-500/20" :
                  "bg-purple-500/20"
              }`}>
              {toast.type === "success" ? <CheckCircle size={16} /> :
                toast.type === "error" ? <AlertTriangle size={16} /> :
                  <Zap size={16} className="animate-pulse" />}
            </div>
            <div>
              <div className="text-[10px] uppercase font-black tracking-widest opacity-60">{toast.type}</div>
              <div className="text-xs font-bold">{toast.msg}</div>
            </div>
            <button onClick={() => setToast(null)} className="ml-2 hover:bg-white/5 p-1 rounded-lg">
              <X size={14} />
            </button>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}
