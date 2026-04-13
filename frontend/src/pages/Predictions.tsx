import { useEffect, useState } from "react";
import DashboardLayout from "@/components/roadai/DashboardLayout";
import { api } from "@/lib/api";
import {
  TrendingDown, Activity, Loader2, AlertTriangle, Clock,
  Wrench, BrainCircuit, Zap, Shield, ChevronRight,
} from "lucide-react";
import {
  AreaChart, Area, LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  Legend, ReferenceLine,
} from "recharts";

const TT = {
  contentStyle: {
    background: "rgba(8,6,18,0.95)", border: "1px solid rgba(168,85,247,0.25)",
    borderRadius: 8, fontSize: 11, color: "#e2d9f3",
  },
};

function HealthBadge({ score }: { score: number }) {
  const [label, color] =
    score >= 85 ? ["Excellent", "#10b981"] :
    score >= 70 ? ["Good",      "#22c55e"] :
    score >= 55 ? ["Moderate",  "#f59e0b"] :
    score >= 40 ? ["Poor",      "#f97316"] :
                  ["Critical",  "#ef4444"];
  return (
    <span className="text-[10px] font-bold px-2 py-0.5 rounded-full"
      style={{ background: `${color}18`, color, border: `1px solid ${color}40` }}>
      {label}
    </span>
  );
}

export default function Predictions() {
  const [days, setDays] = useState(30);
  const [forecast, setForecast] = useState<any>(null);
  const [kpi, setKpi] = useState<any>(null);
  const [trends, setTrends] = useState<any[]>([]);
  const [segments, setSegments] = useState<any[]>([]);
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.get(`/analytics/forecast?days=${days}`).catch(() => null),
      api.get(`/analytics/kpi?days=${days}`).catch(() => null),
      api.get("/analytics/trends?weeks=12").catch(() => null),
      api.get("/analytics/segments?limit=10").catch(() => null),
      api.get("/analysis/history?limit=50").catch(() => null),
    ]).then(([fc, kp, tr, sg, hi]) => {
      setForecast(fc);
      setKpi(kp);
      setTrends((tr?.data || []).filter((d: any) => d.avg_health !== null));
      setSegments(sg?.segments || []);
      setHistory(hi?.history || []);
    }).finally(() => setLoading(false));
  }, [days]);

  const currentH = forecast?.current_health ?? kpi?.avg_health_score ?? 80;
  const projectedH = forecast?.projected_health ?? currentH;
  const trendDir = forecast?.trend ?? "stable";
  const rul = kpi?.avg_rul_years ?? 10;

  // Build maintenance priority list from segments
  let urgentSegs = segments
    .filter(s => (s.avg_health ?? 100) < 70)
    .sort((a, b) => (a.avg_health ?? 100) - (b.avg_health ?? 100))
    .slice(0, 6);

  const usingFallback = urgentSegs.length === 0;
  if (usingFallback && history.length > 0) {
    urgentSegs = history
      .filter(h => (h.road_health_score ?? 100) < 70)
      .sort((a, b) => (a.road_health_score ?? 100) - (b.road_health_score ?? 100))
      .map(h => ({
        id: h.id,
        label: `${h.input_type?.toUpperCase()} Analysis (#${h.id.slice(0, 6)})`,
        avg_health: h.road_health_score,
        total_potholes: h.pothole_count,
        total_cracks: h.crack_count,
        event_count: 1,
        is_fallback: true
      }))
      .slice(0, 6);
  }

  // Build RUL bucket histogram
  const rulBuckets = [
    { label: "< 1yr",  count: 0, color: "#ef4444" },
    { label: "1-3 yr", count: 0, color: "#f97316" },
    { label: "3-5 yr", count: 0, color: "#f59e0b" },
    { label: "> 5yr",  count: 0, color: "#10b981" },
  ];
  segments.forEach(s => {
    // Backend uses avg_rul in segments table
    const r = s.avg_rul ?? s.avg_rul_years ?? 10;
    if (r < 1) rulBuckets[0].count++;
    else if (r < 3) rulBuckets[1].count++;
    else if (r < 5) rulBuckets[2].count++;
    else rulBuckets[3].count++;
  });

  return (
    <DashboardLayout>
      <div className="space-y-5 animate-fade-in">
        {/* Header with Switcher */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-black gradient-text tracking-wide">PREDICTIONS &amp; PROGNOSTICS</h1>
            <p className="text-xs text-muted-foreground mt-0.5">AI-powered road health forecasting &amp; maintenance intelligence</p>
          </div>
          <div className="flex items-center gap-1 p-1 rounded-xl bg-purple-500/5 border border-purple-500/20">
            {[7, 30, 90].map(d => (
              <button key={d} onClick={() => setDays(d)}
                className={`px-3 py-1.5 rounded-lg text-[10px] font-bold transition-all ${
                  days === d ? "bg-purple-500 text-white shadow-lg shadow-purple-500/25" : "text-muted-foreground hover:text-white hover:bg-white/5"
                }`}>
                {d}D
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-24">
            <Loader2 className="animate-spin text-purple-400" size={28} />
          </div>
        ) : (
          <>
            {/* KPI top row */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                { label: "Current Health", value: `${currentH.toFixed(0)}/100`, icon: Shield,
                  color: currentH >= 70 ? "#10b981" : currentH >= 50 ? "#f59e0b" : "#ef4444" },
                { label: `${days}-Day Forecast`, value: `${projectedH.toFixed(0)}/100`, icon: TrendingDown,
                  color: trendDir === "declining" ? "#ef4444" : trendDir === "improving" ? "#10b981" : "#a855f7" },
                { label: "Avg RUL", value: `${rul.toFixed(1)} yrs`, icon: Clock,
                  color: rul < 2 ? "#ef4444" : rul < 5 ? "#f59e0b" : "#10b981" },
                { label: "Trend", value: trendDir.charAt(0).toUpperCase() + trendDir.slice(1), icon: Activity,
                  color: trendDir === "declining" ? "#ef4444" : trendDir === "improving" ? "#10b981" : "#a855f7" },
              ].map(({ label, value, icon: Icon, color }) => (
                <div key={label} className="road-card rounded-xl p-4 flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                    style={{ background: `${color}15`, border: `1px solid ${color}30` }}>
                    <Icon size={16} style={{ color }} />
                  </div>
                  <div>
                    <div className="text-[10px] text-muted-foreground uppercase tracking-widest">{label}</div>
                    <div className="text-lg font-black" style={{ color }}>{value}</div>
                  </div>
                </div>
              ))}
            </div>

            {/* Health Forecast Chart */}
            <div className="road-card rounded-xl p-5">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-bold">{days}-Day Health Score Forecast</h3>
                  <p className="text-[10px] text-muted-foreground mt-0.5">Linear projection based on historical analysis data</p>
                </div>
                <span className={`text-xs px-2 py-1 rounded-full font-bold ${
                  trendDir === "declining" ? "text-red-400 bg-red-500/10" :
                  trendDir === "improving" ? "text-green-400 bg-green-500/10" :
                  "text-purple-400 bg-purple-500/10"
                }`}>
                  {trendDir === "declining" ? "📉 Declining" : trendDir === "improving" ? "📈 Improving" : "➡️ Stable"}
                </span>
              </div>
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={forecast?.data || []}>
                  <defs>
                    <linearGradient id="fcGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={trendDir === "declining" ? "#ef4444" : "#a855f7"} stopOpacity={0.25} />
                      <stop offset="95%" stopColor={trendDir === "declining" ? "#ef4444" : "#a855f7"} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="2 4" stroke="rgba(168,85,247,0.07)" />
                  <XAxis dataKey="day" tick={{ fill: "rgba(180,160,220,0.5)", fontSize: 9 }} stroke="none" label={{ value: "Days from now", position: "insideBottom", offset: -2, fill: "#888", fontSize: 9 }} />
                  <YAxis domain={[0, 100]} tick={{ fill: "rgba(180,160,220,0.5)", fontSize: 9 }} stroke="none" />
                  <Tooltip {...TT} />
                  <ReferenceLine y={70} stroke="#f59e0b" strokeDasharray="3 3" label={{ value: "Moderate", fill: "#f59e0b", fontSize: 9 }} />
                  <ReferenceLine y={40} stroke="#ef4444" strokeDasharray="3 3" label={{ value: "Critical", fill: "#ef4444", fontSize: 9 }} />
                  <Area type="monotone" dataKey="upper" stroke="none" fill="url(#fcGrad)" opacity={0.3} name="Confidence Band" />
                  <Area type="monotone" dataKey="forecast" stroke={trendDir === "declining" ? "#ef4444" : "#a855f7"} fill="url(#fcGrad)" strokeWidth={2} dot={false} name="Forecast" />
                  <Area type="monotone" dataKey="lower" stroke="none" fill="url(#fcGrad)" opacity={0} />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              {/* Weekly Trend */}
              <div className="road-card rounded-xl p-5">
                <h3 className="text-sm font-bold mb-4">Defect Trend (12 Weeks)</h3>
                <ResponsiveContainer width="100%" height={190}>
                  <LineChart data={trends}>
                    <CartesianGrid strokeDasharray="2 4" stroke="rgba(168,85,247,0.07)" />
                    <XAxis dataKey="week" tick={{ fill: "rgba(180,160,220,0.5)", fontSize: 9 }} stroke="none" />
                    <YAxis tick={{ fill: "rgba(180,160,220,0.5)", fontSize: 9 }} stroke="none" />
                    <Tooltip {...TT} />
                    <Legend wrapperStyle={{ fontSize: 10 }} />
                    <Line type="monotone" dataKey="potholes" stroke="#ef4444" strokeWidth={1.5} dot={false} name="Potholes" />
                    <Line type="monotone" dataKey="cracks"   stroke="#f59e0b" strokeWidth={1.5} dot={false} name="Cracks" />
                    <Line type="monotone" dataKey="avg_health" stroke="#a855f7" strokeWidth={2} dot={false} name="Avg Health" />
                  </LineChart>
                </ResponsiveContainer>
              </div>

              {/* RUL Histogram */}
              <div className="road-card rounded-xl p-5">
                <h3 className="text-sm font-bold mb-4">RUL Distribution by Segment</h3>
                <ResponsiveContainer width="100%" height={190}>
                  <BarChart data={rulBuckets}>
                    <CartesianGrid strokeDasharray="2 4" stroke="rgba(168,85,247,0.07)" vertical={false} />
                    <XAxis dataKey="label" tick={{ fill: "rgba(180,160,220,0.5)", fontSize: 10 }} stroke="none" />
                    <YAxis allowDecimals={false} tick={{ fill: "rgba(180,160,220,0.5)", fontSize: 9 }} stroke="none" />
                    <Tooltip {...TT} />
                    <Bar dataKey="count" name="Segments" radius={[4, 4, 0, 0]}>
                      {rulBuckets.map((b, i) => (
                        <rect key={i} fill={b.color} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
                <p className="text-[10px] text-muted-foreground text-center mt-2">Remaining Useful Life estimates per road segment</p>
              </div>
            </div>

            {/* Maintenance Priority Queue */}
            <div className="road-card rounded-xl p-5">
              <div className="flex items-center gap-2 mb-4">
                <Wrench size={15} className="text-orange-400" />
                <h3 className="text-sm font-bold">Maintenance Priority Queue</h3>
                {usingFallback && urgentSegs.length > 0 && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20 ml-2">
                    ANALYSIS FALLBACK
                  </span>
                )}
                <span className="text-[10px] text-muted-foreground ml-auto">Sorted by worst health first</span>
              </div>
              {urgentSegs.length === 0 ? (
                <div className="py-10 text-center">
                  <BrainCircuit size={28} className="mx-auto mb-2 text-purple-400 opacity-30" />
                  <p className="text-xs text-muted-foreground">No urgent segments detected — record geo events first.</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {urgentSegs.map((s: any, i: number) => {
                    const h = s.avg_health ?? 100;
                    const urgencyColor = h < 40 ? "#ef4444" : h < 55 ? "#f97316" : "#f59e0b";
                    return (
                      <div key={s.id || i} className="flex items-center gap-4 px-4 py-3 rounded-xl transition-all hover:bg-white/3"
                        style={{ background: `${urgencyColor}08`, border: `1px solid ${urgencyColor}25` }}>
                        <div className="text-sm font-black" style={{ color: urgencyColor, minWidth: 24 }}>
                          #{i + 1}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-xs font-semibold truncate">{s.label || `Segment ${i + 1}`}</div>
                          <div className="text-[10px] text-muted-foreground">
                            {s.total_potholes || 0} potholes · {s.total_cracks || 0} cracks · {s.event_count || 0} scans
                          </div>
                        </div>
                        <HealthBadge score={h} />
                        <div className="text-right text-xs font-mono" style={{ color: urgencyColor, minWidth: 52 }}>
                          {h.toFixed(0)}/100
                        </div>
                        <ChevronRight size={12} className="text-muted-foreground" />
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* AI Insights */}
            {kpi?.ai_insights?.length > 0 && (
              <div className="road-card rounded-xl p-5">
                <div className="flex items-center gap-2 mb-4">
                  <Zap size={14} className="text-purple-400" />
                  <h3 className="text-sm font-bold">AI Insights</h3>
                </div>
                <ul className="space-y-2">
                  {kpi.ai_insights.map((ins: string, i: number) => (
                    <li key={i} className="flex items-start gap-2.5 text-xs text-muted-foreground">
                      <span className="text-purple-400 mt-0.5 flex-shrink-0">•</span>
                      {ins}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </div>
    </DashboardLayout>
  );
}
