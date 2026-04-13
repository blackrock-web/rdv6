import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import DashboardLayout from "@/components/roadai/DashboardLayout";
import StatCard from "@/components/roadai/StatCard";
import HealthGauge from "@/components/roadai/HealthGauge";
import { api, healthColor, API_URL } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  CircleDot, AlertTriangle, Activity, Zap, Shield, Trophy, Route, Cpu,
  BarChart3, TrendingDown, MapPin, MessageSquare, Filter, Layers, TrendingUp, RefreshCw,
} from "lucide-react";
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line, RadarChart, Radar,
  PolarGrid, PolarAngleAxis, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, ReferenceLine,
} from "recharts";
import { Link } from "react-router-dom";
import { Loader2, Play, Image as ImageIcon, FileText as FileTextIcon, History, FileDown } from "lucide-react";
import * as XLSX from 'xlsx';

const TT = {
  contentStyle: {
    background: "rgba(8,6,18,0.97)",
    border: "1px solid rgba(168,85,247,0.3)",
    borderRadius: 10, fontSize: 11, color: "#e2d9f3",
    boxShadow: "0 8px 32px rgba(0,0,0,0.6)",
  },
  cursor: { stroke: "rgba(168,85,247,0.2)" },
};

const MODEL_RADAR = [
  { metric: "mAP50",     v8m: 74, v11m: 75, frcnn: 78 },
  { metric: "FPS",       v8m: 53, v11m: 62, frcnn: 15 },
  { metric: "F1",        v8m: 74, v11m: 77, frcnn: 79 },
  { metric: "Recall",    v8m: 71, v11m: 73, frcnn: 76 },
  { metric: "Precision", v8m: 79, v11m: 81, frcnn: 83 },
];

function buildRulProjection(startHealth: number) {
  const points = [];
  for (let yr = 0; yr <= 12; yr++) {
    const degradation = yr * 6.5;
    const h = Math.max(0, startHealth - degradation);
    const rulRoadai = Math.max(0, 12 - yr);
    const rulYolo8m = Math.max(0, 11 - yr * 1.1);
    const rulFrcnn  = Math.max(0, 10 - yr * 1.2);
    points.push({ year: `Y${yr}`, health: Math.round(h), roadai: +rulRoadai.toFixed(1), yolov8m: +rulYolo8m.toFixed(1), frcnn: +rulFrcnn.toFixed(1) });
  }
  return points;
}

function buildTimeline(trend: { index: number; score: number }[]) {
  if (trend.length >= 5) return trend.slice(-14).map((t) => ({
    day: `#${t.index + 1}`,
    potholes: Math.round((100 - t.score) / 14),
    cracks: Math.round((100 - t.score) / 9),
    score: t.score,
  }));
  return Array.from({ length: 7 }, (_, i) => ({ day: `D${i + 1}`, potholes: 0, cracks: 0, score: 100 }));
}

const FORMATION_STATS = [
  { label: "Wall Cracks",  count: 0, color: "#ec4899", icon: "🧱" },
  { label: "Potholes",     count: 0, color: "#ef4444", icon: "🕳️" },
  { label: "Surface Holes",count: 0, color: "#f97316", icon: "⚫" },
  { label: "Wall Filtered",count: 0, color: "#a855f7", icon: "🔍" },
];

export default function Dashboard() {
  const { user } = useAuth();
  const [stats, setStats]     = useState<any>(null);
  const [runtime, setRuntime] = useState<any>(null);
  const [alerts, setAlerts]   = useState<any[]>([]);
  const [benchData, setBenchData] = useState<any[]>([]);
  const [winner, setWinner]   = useState<string | null>(null);
  const [geoStats, setGeoStats] = useState<any>(null);
  const [topSegs, setTopSegs] = useState<any[]>([]);
  const [alertStats, setAlertStats] = useState<any>(null);
  const [formStats, setFormStats]   = useState(FORMATION_STATS);

  const navigate = useNavigate();
  const { rid } = useParams();
  const [history, setHistory] = useState<any[]>([]);
  const selectedId = rid || "global";
  const [selectedData, setSelectedData] = useState<any>(null);
  const [loadingHistory, setLoadingHistory] = useState(false);

  const loadHistory = async () => {
    setLoadingHistory(true);
    try {
      const res = await api.get("/analysis/history?limit=50");
      if (res.success) setHistory(res.history || []);
    } catch (e) { console.error("Failed to load history", e); }
    finally { setLoadingHistory(false); }
  };

  const exportToExcel = () => {
    const data = history.map(h => ({
      ID: h.id,
      Type: h.input_type,
      Timestamp: new Date(h.created_at * 1000).toLocaleString(),
      Health: h.road_health_score,
      Potholes: h.pothole_count,
      Cracks: h.crack_count,
      RUL: h.rul_estimate_years,
      Lat: h.gps_lat,
      Lng: h.gps_lng
    }));
    const ws = XLSX.utils.json_to_sheet(data);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "RoadAI History");
    XLSX.writeFile(wb, `RoadAI_Full_History_${Date.now()}.xlsx`);
  };

  useEffect(() => {
    loadHistory();
    if (rid && history.length > 0) {
       const found = history.find(h => h.id === rid);
       if (found) setSelectedData(found);
    }
  }, [rid, history.length]);

  useEffect(() => {
    const wsUrl = API_URL.replace("http", "ws") + "/api/analytics/ws";
    const ws = new WebSocket(wsUrl);
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "kpi_update" && msg.data) {
          setStats(msg.data);
          setGeoStats((prev: any) => ({ ...prev, total: msg.data.geo_events }));
          if (msg.data.wall_filtered_count != null) {
            setFormStats([
              { label: "Wall Cracks",   count: msg.data.wall_crack_count   ?? 0, color: "#ec4899", icon: "🧱" },
              { label: "Potholes",      count: msg.data.total_potholes     ?? 0, color: "#ef4444", icon: "🕳️" },
              { label: "Surface Holes", count: msg.data.surface_hole_count ?? 0, color: "#f97316", icon: "⚫" },
              { label: "Wall Filtered", count: msg.data.wall_filtered_count?? 0, color: "#a855f7", icon: "🔍" },
            ]);
          }
        }
      } catch { }
    };
    api.get("/runtime-status").then(setRuntime).catch(() => {});
    api.get("/alerts/history?limit=5").then(d => setAlerts((d.alerts || []).reverse())).catch(() => {});
    api.get("/alerts/stats").then(setAlertStats).catch(() => {});
    api.get("/benchmarks/results").then(d => { setBenchData(d.results || []); setWinner(d.winner_name || null); }).catch(() => {});
    api.get("/geo/events?limit=50").then(d => {
      const evs = d.events || [];
      setGeoStats((prev: any) => ({
        ...prev,
        critical: evs.filter((e: any) => e.severity === "critical").length,
        avgHealth: evs.length ? Math.round(evs.reduce((a: number, e: any) => a + (e.road_health_score || 0), 0) / evs.length) : null,
      }));
    }).catch(() => {});
    api.get("/geo/segments/critical?n=3").then(d => setTopSegs(d.segments || [])).catch(() => {});
    return () => { ws.close(); };
  }, []);

  const isGlobal = selectedId === "global";
  const displayStats = isGlobal ? stats : (selectedData?.metadata || selectedData);
  const avgH = isGlobal ? (stats?.avg_health_score ?? 100) : (displayStats?.road_health_score ?? displayStats?.average_health_score ?? 100);
  const trend = isGlobal ? (stats?.health_trend ?? []) : [];
  const timeline = buildTimeline(trend);
  const rulData  = buildRulProjection(avgH);

  const handleSelect = (id: string) => {
    if (id === "global") {
      navigate("/dashboard");
      setSelectedData(null);
    } else {
      navigate(`/dashboard/${id}`);
      const found = history.find(h => h.id === id);
      setSelectedData(found);
    }
  };

  const modelChart = benchData.length > 0
    ? benchData.sort((a, b) => (b.composite_score ?? 0) - (a.composite_score ?? 0)).slice(0, 6).map(m => ({
        name: (m.model_name || m.model_id || "").replace("YOLOv", "v").split(" ")[0],
        mAP50: Math.round((m.mAP50 ?? 0) * 100),
        fps: Math.round(m.fps ?? 0),
        rul: Math.round(m.rul_accuracy ?? 70),
      }))
    : [
        { name: "v8n",   mAP50: 61,  fps: 123, rul: 62 },
        { name: "v8s",   mAP50: 69,  fps: 88,  rul: 68 },
        { name: "v8m",   mAP50: 74,  fps: 53,  rul: 72 },
        { name: "v11m",  mAP50: 75,  fps: 62,  rul: 74 },
        { name: "FRCNN", mAP50: 78,  fps: 15,  rul: 70 },
        { name: "ROADAI",mAP50: 80,  fps: 55,  rul: 85 },
      ];

  const smsSent   = alertStats?.sent ?? 0;

  return (
    <DashboardLayout>
      <div className="space-y-5 animate-fade-in">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400">
               <Activity size={20} />
            </div>
            <div>
              <h1 className="text-2xl font-black gradient-text tracking-wide uppercase">
                {isGlobal ? "Dashboard" : "Analysis Report"}
              </h1>
              <p className="text-[10px] text-muted-foreground mt-0.5 font-mono">
                {isGlobal 
                  ? `Welcome, ${user?.name} · ROADAI v4.0 · GPU Pipeline Active` 
                  : `Viewing RID: ${selectedId} · ${new Date(selectedData?.created_at * 1000).toLocaleString()}`}
              </p>
            </div>
          </div>
          
          <div className="flex items-center gap-3">
            <button onClick={exportToExcel}
              className="px-4 py-2 rounded-xl bg-green-500/10 border border-green-500/30 text-green-400 font-bold text-xs hover:bg-green-500/20 transition-all flex items-center gap-2">
              <FileDown size={14}/> EXCEL
            </button>
            <div className="flex items-center gap-2 bg-secondary/40 border border-border/60 p-1.5 rounded-xl backdrop-blur-sm shadow-inner">
              <div className="flex items-center gap-2 px-3 border-r border-border/40 py-1">
                <History size={12} className="text-muted-foreground" />
                <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">Select Report</span>
              </div>
              <select 
                value={selectedId} 
                onChange={(e) => handleSelect(e.target.value)}
                className="bg-transparent text-xs font-black px-3 py-1 outline-none cursor-pointer min-w-[240px] text-purple-100"
              >
                <option value="global" className="bg-zinc-900">🌐 Fleet Global Aggregation</option>
                <optgroup label="Detailed Recent Scans" className="bg-zinc-900 border-t border-border">
                  {history.map(h => (
                    <option key={h.id} value={h.id} className="bg-zinc-900 font-mono">
                      {h.input_type === "satellite" ? "🛰" : h.input_type === "image" ? "🖼" : "🎥"} {h.id.slice(0,8).toUpperCase()} · {Math.round(h.road_health_score)}% Health · {new Date(h.created_at * 1000).toLocaleDateString()}
                    </option>
                  ))}
                </optgroup>
              </select>
              <button 
                onClick={loadHistory} 
                className="p-1.5 hover:bg-white/10 rounded-lg text-muted-foreground transition-all active:scale-95"
                title="Refresh Analytics"
              >
                {loadingHistory ? <Loader2 size={12} className="animate-spin text-purple-400" /> : <RefreshCw size={12} />}
              </button>
            </div>
            <Link to="/analyze" className="btn-solid px-5 py-2 rounded-xl text-xs font-bold tracking-wider flex items-center gap-2">
              <Zap size={13} />NEW SCAN
            </Link>
          </div>
        </div>

        <div className="glass rounded-xl p-4 flex flex-wrap items-center gap-4"
          style={{ borderColor: "rgba(168,85,247,0.25)" }}>
          <Zap size={16} className="text-pink-400 flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-[9px] text-muted-foreground uppercase tracking-widest font-bold mb-1">ACTIVE RUNTIME MODELS</p>
            <div className="flex flex-wrap gap-4 text-xs" style={{ fontFamily: "'DM Mono',monospace" }}>
              <span><span className="text-muted-foreground">Defect: </span>
                <span className={runtime?.defect_model?.ready ? "text-green-400" : "text-yellow-400"}>
                  {runtime?.defect_model?.path?.split("/").pop() ?? "best.pt"} {runtime?.defect_model?.ready ? "●" : "○"}
                </span>
              </span>
              <span><span className="text-muted-foreground">Object: </span>
                <span className={runtime?.object_model?.ready ? "text-green-400" : "text-yellow-400"}>
                  {runtime?.object_model?.path?.split("/").pop() ?? "yolov8n.pt"} {runtime?.object_model?.ready ? "●" : "○"}
                </span>
              </span>
              <span><span className="text-muted-foreground">Seg: </span><span className="text-cyan-400">DeepLabV3</span></span>
              <span><span className="text-muted-foreground">Depth: </span><span className="text-cyan-400">MiDaS</span></span>
              <span><span className="text-muted-foreground">RUL: </span><span className="text-purple-400">XGBoost</span></span>
              <span><span className="text-muted-foreground">SMS: </span>
                <span className={smsSent > 0 ? "text-green-400" : "text-muted-foreground"}>
                  {smsSent > 0 ? `${smsSent} sent ✓` : "Twilio ready"}
                </span>
              </span>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
          <StatCard title="Health Score"  value={<span className="animate-number">{`${avgH.toFixed(0)}/100`}</span>} icon={Shield}      variant={avgH >= 70 ? "safe" : avgH >= 50 ? "warning" : "danger"} />
          <StatCard title={isGlobal ? "Total Analyses" : "Input Mode"}   value={isGlobal ? (stats?.total_analyses ?? 0) : (displayStats?.type || displayStats?.input_type || "N/A")}  icon={Activity}    variant="purple" />
          <StatCard title="Potholes"   value={<span className="animate-number">{displayStats?.pothole_count ?? displayStats?.total_potholes ?? 0}</span>}  icon={CircleDot}   variant="danger" />
          <StatCard title="Cracks"     value={<span className="animate-number">{displayStats?.crack_count ?? displayStats?.total_cracks ?? 0}</span>}    icon={AlertTriangle} variant="warning" />
          <StatCard title="RUL (Years)"   value={<span className="animate-number">{displayStats?.rul_estimate_years?.toFixed(1) ?? "—"}</span>} icon={TrendingDown} variant={displayStats?.rul_estimate_years < 3 ? "danger" : "safe"} />
          <StatCard title="Geo Events" value={<span className="animate-number">{isGlobal ? (geoStats?.total ?? "—") : "1"}</span>}      icon={MapPin}      variant="purple" subtitle={isGlobal && geoStats?.critical ? `${geoStats.critical} critical` : "Local"} />
          <StatCard title="SMS Status"   value={isGlobal ? smsSent : (displayStats?.sms_alert?.sent ? "Sent" : "None")} icon={MessageSquare} variant={isGlobal ? (smsSent > 0 ? "safe" : "info") : (displayStats?.sms_alert?.sent ? "safe" : "info")} />
          <StatCard title="Weather"     value={displayStats?.weather_condition?.replace("_"," ") || "Clear"} icon={Cpu} variant="info" />
        </div>

        {!isGlobal && (selectedData?.annotated_path || displayStats?.annotated_video_url || displayStats?.annotated_image) && (
          <div className="road-card rounded-xl p-5 animate-slide-up">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-bold gradient-text flex items-center gap-2">
                {displayStats?.annotated_video_url ? <Play size={14}/> : <ImageIcon size={14}/>}
                INFERENCE FEED OUTPUT
              </h3>
              <div className="flex gap-2">
                 {displayStats?.id && displayStats.id !== "global" && (
                   <div className="flex gap-2">
                      <a href={`${API_URL}/api/reports/pdf/${displayStats.id}`} target="_blank" rel="noreferrer"
                        className="text-[10px] font-bold text-pink-400 border border-pink-400/30 px-3 py-1 rounded-lg hover:bg-pink-400/10">
                       VIEW PDF REPORT
                     </a>
                     <a href={`${API_URL}/api/reports/json/${displayStats.id}`} target="_blank" rel="noreferrer"
                        className="text-[10px] font-bold text-muted-foreground border border-border px-3 py-1 rounded-lg hover:bg-secondary">
                       JSON
                     </a>
                   </div>
                 )}
              </div>
            </div>
            <div className="w-full bg-black rounded-xl overflow-hidden border border-border flex items-center justify-center min-h-[300px] lg:min-h-[500px]">
              {displayStats?.annotated_video_url || (selectedData?.annotated_path?.includes(".mp4")) ? (
                <video src={displayStats?.annotated_video_url || selectedData?.annotated_path} controls className="w-full h-full object-contain" />
              ) : (
                <img src={displayStats?.annotated_image || selectedData?.annotated_path} alt="Analysis Output" className="w-full h-full object-contain" />
              )}
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          <div className="lg:col-span-2 road-card rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-bold gradient-text">Road Health Trend</h3>
              <span className="text-[10px] text-pink-400 font-bold">LIVE ●</span>
            </div>
            <ResponsiveContainer width="100%" height={180}>
              <AreaChart data={timeline}>
                <defs>
                  <linearGradient id="healthGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#a855f7" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="#ec4899" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="2 4" stroke="rgba(168,85,247,0.07)" />
                <XAxis dataKey="day" tick={{ fill: "rgba(180,160,220,0.5)", fontSize: 9 }} stroke="rgba(168,85,247,0.1)" />
                <YAxis domain={[0, 100]} tick={{ fill: "rgba(180,160,220,0.5)", fontSize: 9 }} stroke="rgba(168,85,247,0.1)" />
                <Tooltip {...TT} />
                <Area type="monotone" dataKey="score" stroke="#a855f7" fill="url(#healthGrad)" strokeWidth={2.5} dot={false} name="Health Score" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <div className="road-card rounded-xl p-5 flex flex-col items-center justify-center gap-4">
            <HealthGauge score={avgH} size={130} label="Average Road Health" />
            <div className="text-center">
              <div className="text-xs font-bold" style={{ color: avgH >= 70 ? "#10b981" : avgH >= 50 ? "#f59e0b" : "#ef4444" }}>
                {avgH >= 70 ? "GOOD CONDITION" : avgH >= 50 ? "MODERATE" : "POOR CONDITION"}
              </div>
            </div>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
