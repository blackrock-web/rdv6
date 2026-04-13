import { useEffect, useState } from "react";
import DashboardLayout from "@/components/roadai/DashboardLayout";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  Loader2, Trophy, BarChart3, Play, TrendingUp, FileText,
  CheckCircle, AlertTriangle, Cpu, Info,
} from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, LineChart, Line, ReferenceLine,
} from "recharts";

// ── Constants ────────────────────────────────────────────────────────────────

const COLORS = [
  "hsl(213,90%,68%)", "hsl(262,80%,65%)", "hsl(38,95%,55%)",
  "hsl(142,71%,45%)", "hsl(0,80%,58%)",   "hsl(186,80%,55%)",
];

const MODELS_TO_COMPARE = ["check_2", "check_2.pt", "best_pt", "best.pt", "yolov8s", "yolov8n", "faster_rcnn", "3d_lidar"];

const SCORE_DIMENSIONS = [
  { key: "weather_robustness_score", label: "Weather Robustness", color: "hsl(213,90%,68%)" },
  { key: "video_noise_score",        label: "Video + Noise",      color: "hsl(262,80%,65%)" },
  { key: "lane_robustness_score",    label: "Road Type",          color: "hsl(186,80%,55%)" },
  { key: "rul_accuracy",             label: "RUL Accuracy",       color: "hsl(38,95%,55%)" },
  { key: "health_score_accuracy",    label: "Road Health",        color: "hsl(142,71%,45%)" },
  { key: "detection_score",          label: "Pothole & Crack",    color: "hsl(0,80%,58%)" },
];

const TABS = [
  { id: "overview", label: "Score Listing", icon: <FileText size={12}/> },
  { id: "bars",     label: "Bar Charts",    icon: <BarChart3 size={12}/> },
  { id: "curve",    label: "X-Y Curves",    icon: <TrendingUp size={12}/> },
] as const;

type TabId = typeof TABS[number]["id"];

const TT_STYLE = { 
  background: "hsl(var(--card))", 
  border: "1px solid hsl(var(--border))", 
  borderRadius: 8, 
  fontSize: 11 
};

// ── Helper: shorten model name ───────────────────────────────────────────────
function shortName(name: string, id?: string): string {
  if (!name && !id) return "Unknown";
  const n = (name || id || "").toLowerCase();
  if (n.includes("check_2")) return "check_2.pt";
  if (n.includes("best") && n.includes("pt")) return "best.pt";
  if (n.includes("yolov8n") || n.includes("nano")) return "YOLOv8n";
  if (n.includes("yolov8s") || n.includes("small")) return "YOLOv8s";
  if (n.includes("faster") || n.includes("rcnn")) return "F-RCNN";
  if (n.includes("lidar")) return "3D LiDAR";
  return name || id || "Candidate";
}

// ── Components ───────────────────────────────────────────────────────────────

function ModelPodium({ model, rank }: { model: any; rank: number }) {
  const isWinner = rank === 1;
  const isCheck2 = model.model_id === "check_2" || (model.name && model.name.includes("check_2"));
  
  return (
    <div className={`road-card rounded-xl border p-4 flex flex-col items-center justify-center space-y-2 transition-all duration-500 ${
      isWinner 
        ? "border-purple-500/60 bg-gradient-to-br from-purple-500/10 to-pink-500/10 shadow-[0_0_20px_rgba(168,85,247,0.15)] scale-105 z-10" 
        : "border-border/50 bg-secondary/10"
    }`}>
      <span className={`text-2xl transition-transform ${isWinner ? "animate-bounce" : ""}`}>
        {isWinner ? "🏆" : rank === 2 ? "🥈" : "🥉"}
      </span>
      <div className="text-center">
        <p className={`font-black tracking-tight ${
          isWinner 
            ? "text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-pink-400 text-sm" 
            : "text-foreground text-xs"
        }`}>
          {model.model_name || model.name}
        </p>
        <div className="flex items-center justify-center gap-1.5 mt-1">
          <span className="text-[10px] text-muted-foreground uppercase tracking-widest font-bold">SCORE</span>
          <span className={`font-mono font-bold ${isWinner ? "text-purple-300" : "text-muted-foreground"}`}>
            {model.composite_score?.toFixed(1)}
          </span>
        </div>
      </div>
      {isWinner && (
        <div className="mt-2 text-[9px] px-2.5 py-0.5 rounded-full bg-purple-500 text-white font-black uppercase tracking-tighter shadow-lg shadow-purple-500/20">
          {isCheck2 ? "🔥 TOP PERFORMER" : "Benchmark Winner"}
        </div>
      )}
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────

export default function Benchmarks() {
  const { user } = useAuth();
  const [results, setResults] = useState<any[]>([]);
  const [running, setRunning] = useState(false);
  const [tab, setTab] = useState<TabId>("overview");

  const load = () => {
    api.get("/benchmarks/results").then((d: any) => {
      // Flatten scores into top level for easier access in graphs/tables
      const allResults = (d.results ?? []).map((r: any) => ({
        ...r,
        ...(r.benchmark_scores ?? {})
      }));

      // Show all models present in the registry
      setResults(allResults);
      setRunning(d.running ?? false);
    }).catch((err) => {
      console.error("Benchmark load failed", err);
    });
  };

  useEffect(() => { 
    load(); 
    const t = setInterval(load, 3000); 
    return () => clearInterval(t); 
  }, []);

  const runAll = async () => {
    await api.post("/benchmarks/run").catch(() => {});
    setRunning(true);
  };

  const sorted = [...results].sort((a, b) => (b.composite_score ?? 0) - (a.composite_score ?? 0));
  const winner = sorted[0];

  // Data for Bar Chart
  const barData = results.map(r => {
    const d: any = { name: shortName(r.model_name, r.id || r.model_id) };
    SCORE_DIMENSIONS.forEach(dim => {
      d[dim.label] = r[dim.key] ?? 0;
    });
    return d;
  });

  // Data for Line Chart
  const lineData = SCORE_DIMENSIONS.map(dim => {
    const d: any = { dimension: dim.label };
    results.forEach(r => {
      d[shortName(r.model_name, r.id || r.model_id)] = r[dim.key] ?? 0;
    });
    return d;
  });

  return (
    <DashboardLayout title="Performance Benchmarks" subtitle="Comparing models across standardized road condition metrics">
      <div className="space-y-6">
        
        {/* Header Actions */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-4 bg-secondary/30 p-1 rounded-lg border w-fit">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                  tab === t.id 
                    ? "bg-primary text-primary-foreground shadow-sm" 
                    : "text-muted-foreground hover:bg-secondary"
                }`}
              >
                {t.icon}
                {t.label}
              </button>
            ))}
          </div>

          <button
            onClick={runAll}
            disabled={running}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all ${
              running ? "bg-muted text-muted-foreground" : "bg-primary hover:bg-primary/90 text-primary-foreground"
            }`}
          >
            {running ? <Loader2 className="animate-spin" size={16} /> : <Play size={16} />}
            {running ? "Benchmarks Running..." : "Re-Run Benchmarks"}
          </button>
        </div>

        {/* Podium for Top 3 */}
        {tab === "overview" && sorted.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {sorted.slice(0, 3).map((m, i) => (
              <ModelPodium key={m.model_id} model={m} rank={i + 1} />
            ))}
          </div>
        )}

        {/* Dynamic Content */}
        <div className="road-card border rounded-2xl p-6 bg-card min-h-[500px]">
          
          {results.length === 0 && !running && (
            <div className="flex flex-col items-center justify-center h-[400px] text-center space-y-4">
              <Cpu size={48} className="text-muted-foreground opacity-20" />
              <div className="max-w-xs">
                <p className="text-lg font-bold">No Benchmark Data</p>
                <p className="text-sm text-muted-foreground mt-1">Run the benchmark engine to generate performance scores for available models.</p>
              </div>
              <button onClick={runAll} className="px-6 py-2 bg-primary text-primary-foreground rounded-lg font-medium">Start First Run</button>
            </div>
          )}

          {running && results.length === 0 && (
             <div className="flex flex-col items-center justify-center h-[400px] text-center space-y-4">
              <Loader2 className="animate-spin text-primary" size={48} />
              <p className="text-lg font-bold">Initializing Benchmarks</p>
              <p className="text-sm text-muted-foreground">Running inference and synthetic simulations...</p>
           </div>
          )}

          {results.length > 0 && (
            <>
              {tab === "overview" && (
                <div className="space-y-6">
                  <div className="flex items-center justify-between">
                    <h3 className="text-lg font-bold flex items-center gap-2">
                       <FileText size={18} className="text-primary"/>
                       Standardized Score Listing
                    </h3>
                  </div>
                  
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-border">
                          <th className="text-left py-3 font-semibold text-muted-foreground">Model</th>
                          {SCORE_DIMENSIONS.map(d => (
                            <th key={d.key} className="text-right py-3 font-semibold text-muted-foreground px-4">
                              {d.label}
                            </th>
                          ))}
                          <th className="text-right py-3 font-bold text-primary px-4 bg-primary/5">Composite</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/50">
                        {sorted.map(r => (
                          <tr key={r.model_id || r.id} className="group hover:bg-secondary/20 transition-colors">
                            <td className="py-2 py-3">
                              <span className="font-bold block">{shortName(r.model_name, r.id || r.model_id)}</span>
                              <span className="text-[10px] text-muted-foreground uppercase">{r.task.replace("_", " ")}</span>
                            </td>
                            {SCORE_DIMENSIONS.map(d => (
                              <td key={d.key} className="text-right py-3 px-4 font-mono">
                                <span className={Number(r[d.key]) >= 75 ? "text-road-safe font-bold" : "text-foreground"}>
                                  {r[d.key]?.toFixed(1) ?? "—"}
                                </span>
                              </td>
                            ))}
                            <td className="text-right py-3 px-4 font-mono font-bold text-primary bg-primary/5">
                              {r.composite_score?.toFixed(2)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  <div className="p-4 bg-secondary/30 rounded-xl border flex gap-4 items-start">
                    <Info size={16} className="text-primary mt-0.5" />
                    <div className="text-[11px] text-muted-foreground leading-relaxed">
                      <p className="font-semibold text-foreground mb-1">Methodology Notice:</p>
                      Scores are derived from a combination of published COCO metrics and synthetic robustness simulations. 
                      Weights: Potholes/Cracks (15%), Weather (15%), Video Noise (15%), Road Type (15%), RUL (15%), Road Health (15%), and Calibration (10%).
                      Models with <strong>best.pt</strong> are custom-trained for road defects.
                    </div>
                  </div>
                </div>
              )}

              {tab === "bars" && (
                <div className="space-y-6 h-full">
                   <h3 className="text-lg font-bold flex items-center gap-2">
                       <BarChart3 size={18} className="text-primary"/>
                       Model Comparison by Dimension
                    </h3>
                   <div className="h-[400px] w-full mt-8">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={barData} margin={{ top: 20, right: 30, left: 0, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" />
                        <XAxis dataKey="name" stroke="hsl(var(--muted-foreground))" fontSize={12} tickLine={false} axisLine={false} />
                        <YAxis hide domain={[0, 100]} />
                        <Tooltip contentStyle={TT_STYLE} cursor={{fill: 'hsl(var(--secondary)/0.5)'}} />
                        <Legend wrapperStyle={{fontSize: 10, paddingTop: 20}} />
                        {SCORE_DIMENSIONS.map((dim) => (
                          <Bar key={dim.label} dataKey={dim.label} fill={dim.color} radius={[4, 4, 0, 0]} />
                        ))}
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}

              {tab === "curve" && (
                <div className="space-y-6 h-full">
                  <h3 className="text-lg font-bold flex items-center gap-2">
                       <TrendingUp size={18} className="text-primary"/>
                       Metric Sensitivity Analysis
                  </h3>
                   <div className="h-[400px] w-full mt-8">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={lineData} margin={{ top: 20, right: 30, left: 20, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" />
                        <XAxis dataKey="dimension" stroke="hsl(var(--muted-foreground))" fontSize={11} tickLine={false} axisLine={false} />
                        <YAxis stroke="hsl(var(--muted-foreground))" fontSize={11} tickLine={false} axisLine={false} />
                        <Tooltip contentStyle={TT_STYLE} />
                        <Legend wrapperStyle={{fontSize: 10, paddingTop: 20}} />
                        <ReferenceLine y={75} stroke="hsl(var(--primary))" strokeDasharray="5 5" label={{ value: 'Target', position: 'right', fill: 'hsl(var(--primary))', fontSize: 10 }} />
                        {results.map((r, i) => (
                          <Line
                            key={r.model_id || r.id}
                            type="monotone"
                            dataKey={shortName(r.model_name, r.id || r.model_id)}
                            stroke={COLORS[i % COLORS.length]}
                            strokeWidth={(r.model_id === 'best_pt' || r.id === 'best_pt') ? 4 : 2}
                            dot={{ r: 4 }}
                            activeDot={{ r: 6 }}
                          />
                        ))}
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
