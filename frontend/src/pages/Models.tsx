import { useEffect, useState } from "react";
import DashboardLayout from "@/components/roadai/DashboardLayout";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Cpu, RefreshCw, Trophy, CheckCircle, XCircle, Loader2, Info } from "lucide-react";

const STATUS_STYLES: Record<string, string> = {
  runtime:    "text-primary",
  benchmarked:"text-road-safe",
  available:  "text-road-warning",
  not_loaded: "text-muted-foreground",
};

const CATEGORY_STYLES: Record<string, string> = {
  candidate: "bg-primary/10 text-primary border-primary/20",
  custom:    "bg-purple-500/10 text-purple-400 border-purple-500/20",
  runtime:   "bg-road-safe/10 text-road-safe border-road-safe/20",
};

export default function Models() {
  const { user } = useAuth();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const load = () => {
    setLoading(true);
    api.get("/models/").then(setData).catch(() => {}).finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const rescan = async () => {
    setBusy(true); setMsg("");
    const r = await api.post("/models/rescan-custom").catch(() => ({ message: "Error" }));
    setMsg(r.message);
    load();
    setBusy(false);
  };

  const selectRuntime = async () => {
    setBusy(true); setMsg("");
    const r = await api.post("/models/select-runtime").catch(() => ({ message: "Error" }));
    setMsg(r.benchmark_winner ? `Runtime set → ${r.benchmark_winner}` : r.message || "Done");
    load();
    setBusy(false);
  };

  const scan = async () => {
    setBusy(true); setMsg("");
    const r = await api.post("/models/scan").catch(() => ({ message: "Error" }));
    setMsg(r.message || "Done");
    load();
    setBusy(false);
  };

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <Loader2 className="animate-spin text-primary" size={32} />
        </div>
      </DashboardLayout>
    );
  }

  const models: any[] = data?.models ?? [];

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Model Registry</h1>
            <p className="text-sm text-muted-foreground mt-1">
              All registered models, benchmark scores, and runtime selection
            </p>
          </div>
          {user?.role === "admin" && (
            <div className="flex gap-2 flex-wrap">
              <button onClick={scan} disabled={busy}
                className="flex items-center gap-2 px-3 py-2 rounded-lg bg-secondary border border-border text-sm hover:bg-accent transition-colors disabled:opacity-50">
                <RefreshCw size={13} /> Scan All
              </button>
              <button onClick={rescan} disabled={busy}
                className="flex items-center gap-2 px-3 py-2 rounded-lg bg-secondary border border-border text-sm hover:bg-accent transition-colors disabled:opacity-50">
                <Cpu size={13} /> Rescan best.pt
              </button>
              <button onClick={selectRuntime} disabled={busy}
                className="flex items-center gap-2 px-3 py-2 rounded-lg bg-primary text-primary-foreground text-sm hover:opacity-90 transition-opacity disabled:opacity-50">
                <Trophy size={13} /> Select Runtime
              </button>
            </div>
          )}
        </div>

        {msg && (
          <div className="p-3 rounded-lg bg-primary/10 border border-primary/20 text-sm text-primary">
            {msg}
          </div>
        )}

        {/* Runtime status row */}
        <div className="road-card rounded-xl border border-border p-5">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              {
                label: "Defect Runtime (best.pt)",
                value: data?.runtime_assignment?.defect_runtime?.ready
                  ? <span className="flex items-center gap-1.5 text-road-safe text-sm"><CheckCircle size={13}/> Ready</span>
                  : <span className="flex items-center gap-1.5 text-road-warning text-sm"><XCircle size={13}/> Missing</span>,
              },
              {
                label: "Object Runtime (yolov8n)",
                value: data?.runtime_assignment?.object_runtime?.ready
                  ? <span className="flex items-center gap-1.5 text-road-safe text-sm"><CheckCircle size={13}/> Ready</span>
                  : <span className="flex items-center gap-1.5 text-road-warning text-sm"><XCircle size={13}/> Missing</span>,
              },
              {
                label: "Custom best.pt",
                value: data?.custom_model_present
                  ? <span className="flex items-center gap-1.5 text-road-safe text-sm"><CheckCircle size={13}/> Loaded</span>
                  : <span className="text-muted-foreground text-sm">Not added yet</span>,
              },
              {
                label: "Benchmark Winner",
                value: <span className="flex items-center gap-1.5 text-purple-400 text-sm">
                  {data?.benchmark_winner ? <><Trophy size={13}/> {data.benchmark_winner}</> : "Not yet run"}
                </span>,
              },
            ].map(({ label, value }) => (
              <div key={label}>
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold mb-1.5">{label}</p>
                {value}
              </div>
            ))}
          </div>
        </div>

        {/* best.pt instructions */}
        {!data?.custom_model_present && (
          <div className="flex gap-3 p-4 rounded-xl border border-road-warning/30 bg-road-warning/5">
            <Info size={16} className="text-road-warning flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-semibold text-road-warning mb-1">Custom model (best.pt) not added yet</p>
              <p className="text-xs text-muted-foreground leading-relaxed">
                1. Copy your YOLO model to <code className="font-mono bg-secondary px-1.5 py-0.5 rounded text-foreground">models/custom/best.pt</code><br />
                2. Click <strong>Rescan best.pt</strong> above<br />
                3. Run benchmarks → Select runtime
              </p>
            </div>
          </div>
        )}

        {/* Models table */}
        <div className="road-card rounded-xl border border-border overflow-hidden">
          <div className="px-5 py-4 border-b border-border flex items-center justify-between">
            <h3 className="text-sm font-semibold">All Models ({models.length})</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-secondary/50">
                  {["Model", "Category", "Status", "mAP50", "F1", "FPS", "Size", "Composite", "Runtime"].map((h) => (
                    <th key={h} className="text-left px-4 py-2.5 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold border-b border-border">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {models.map((m: any) => (
                  <tr key={m.id} className="border-b border-border last:border-0 hover:bg-secondary/30 transition-colors">
                    <td className="px-4 py-3">
                      <p className="font-medium text-sm text-foreground">{m.name}</p>
                      <p className="text-[10px] text-muted-foreground truncate max-w-[180px]">{m.description}</p>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded-full border text-[10px] font-medium ${CATEGORY_STYLES[m.category] ?? "bg-secondary border-border text-muted-foreground"}`}>
                        {m.category}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`flex items-center gap-1 text-[11px] font-medium ${STATUS_STYLES[m.status] ?? "text-muted-foreground"}`}>
                        ● {m.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono">
                      {m.benchmark_scores?.mAP50 ? `${(m.benchmark_scores.mAP50 * 100).toFixed(1)}%` : "—"}
                    </td>
                    <td className="px-4 py-3 font-mono">
                      {m.benchmark_scores?.f1_score ? `${(m.benchmark_scores.f1_score * 100).toFixed(1)}%` : "—"}
                    </td>
                    <td className="px-4 py-3 font-mono">
                      {m.benchmark_scores?.fps ? m.benchmark_scores.fps.toFixed(0) : "—"}
                    </td>
                    <td className="px-4 py-3 font-mono">
                      {m.benchmark_scores?.model_size_mb ? `${m.benchmark_scores.model_size_mb.toFixed(0)} MB` : "—"}
                    </td>
                    <td className="px-4 py-3">
                      {m.composite_score > 0 ? (
                        <div className="flex items-center gap-2">
                          <div className="w-14 h-1.5 bg-muted rounded-full overflow-hidden">
                            <div className="h-full rounded-full"
                              style={{ width: `${m.composite_score}%`, background: m.is_runtime ? "hsl(213,90%,68%)" : "hsl(142,71%,45%)" }} />
                          </div>
                          <span className="font-mono font-bold text-[11px]">{m.composite_score.toFixed(1)}</span>
                        </div>
                      ) : "—"}
                    </td>
                    <td className="px-4 py-3">
                      {m.is_runtime && (
                        <span className="px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20 text-[10px] font-semibold">
                          ⬢ Runtime
                        </span>
                      )}
                      {!m.is_runtime && data?.benchmark_winner === m.id && (
                        <span className="px-2 py-0.5 rounded-full bg-purple-500/10 text-purple-400 border border-purple-500/20 text-[10px] font-semibold">
                          🏆 Winner
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
