import { useEffect, useState, useMemo } from "react";
import DashboardLayout from "@/components/roadai/DashboardLayout";
import { api } from "@/lib/api";
import {
  FileText, Download, RefreshCw, Loader2, BarChart3, MapPin, Clock,
  Filter, Package, Shield, AlertTriangle, Search, SortAsc, SortDesc,
  Archive,
} from "lucide-react";

function healthColor(s: number) {
  if (s >= 85) return "#10b981";
  if (s >= 70) return "#22c55e";
  if (s >= 55) return "#f59e0b";
  if (s >= 40) return "#f97316";
  return "#ef4444";
}
function healthLabel(s: number) {
  if (s >= 85) return "Excellent";
  if (s >= 70) return "Good";
  if (s >= 55) return "Moderate";
  if (s >= 40) return "Poor";
  return "Critical";
}

const SEVERITY_OPTIONS = ["all", "excellent", "good", "moderate", "poor", "critical"];

export default function Reports() {
  const [reports, setReports] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [exportingBulk, setExportingBulk] = useState(false);
  const [msg, setMsg] = useState("");
  const [severity, setSeverity] = useState("all");
  const [search, setSearch] = useState("");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const load = () => {
    setLoading(true);
    const q = severity !== "all" ? `?severity=${severity}` : "";
    Promise.all([
      api.get(`/reports/list${q}`).catch(() => null),
      api.get("/reports/summary").catch(() => null),
    ]).then(([d, s]) => {
      setReports(d?.reports || []);
      setSummary(s);
    }).finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, [severity]);

  const filtered = useMemo(() => {
    let list = [...reports];
    if (search) {
      const q = search.toLowerCase();
      list = list.filter(r =>
        (r.report_id || "").toLowerCase().includes(q) ||
        (r.location || "").toLowerCase().includes(q)
      );
    }
    return list.sort((a, b) => {
      const diff = (a.generated_at ?? 0) - (b.generated_at ?? 0);
      return sortDir === "asc" ? diff : -diff;
    });
  }, [reports, search, sortDir]);

  const download = (rid: string, fmt: "pdf" | "json") => {
    api.downloadBlob(`/reports/download/${rid}?fmt=${fmt}`)
      .then(blob => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url; a.download = `roadai_report_${rid}.${fmt}`; a.click();
      }).catch(e => setMsg(e.message));
  };

  const bulkExport = () => {
    setExportingBulk(true);
    const q = severity !== "all" ? `?severity=${severity}` : "";
    api.downloadBlob(`/reports/bulk-export${q}`)
      .then(blob => {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `roadai_reports_bulk_${Date.now()}.zip`;
        a.click();
      }).catch(e => setMsg(e.message))
      .finally(() => setExportingBulk(false));
  };

  return (
    <DashboardLayout>
      <div className="space-y-5 animate-fade-in">
        {/* Header */}
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-xl font-black gradient-text">REPORTS HUB</h1>
            <p className="text-xs text-muted-foreground mt-0.5">PDF · JSON analysis reports with filtering &amp; bulk export</p>
          </div>
          <div className="flex gap-2 flex-wrap">
            <button onClick={load} className="btn-neon px-3 py-2 rounded-xl text-xs font-bold flex items-center gap-1.5">
              <RefreshCw size={11} /> Refresh
            </button>
            <button onClick={bulkExport} disabled={exportingBulk}
              className="btn-solid px-3 py-2 rounded-xl text-xs font-bold flex items-center gap-1.5">
              {exportingBulk ? <Loader2 size={11} className="animate-spin" /> : <Archive size={11} />}
              Bulk Export ZIP
            </button>
          </div>
        </div>

        {/* Summary Cards */}
        {summary && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { icon: FileText,      label: "Total Reports",     value: summary.total,                         color: "#a855f7" },
              { icon: Shield,        label: "Avg Health",        value: summary.avg_health ? `${summary.avg_health.toFixed(0)}/100` : "—", color: summary.avg_health >= 70 ? "#10b981" : summary.avg_health >= 50 ? "#f59e0b" : "#ef4444" },
              { icon: AlertTriangle, label: "Total Potholes",    value: summary.total_potholes,                color: "#ef4444" },
              { icon: MapPin,        label: "Worst Location",    value: summary.worst_location || "N/A",       color: "#f97316" },
            ].map(({ icon: Icon, label, value, color }) => (
              <div key={label} className="road-card rounded-xl p-4 flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl flex items-center justify-center"
                  style={{ background: `${color}15`, border: `1px solid ${color}30` }}>
                  <Icon size={14} style={{ color }} />
                </div>
                <div>
                  <div className="text-[10px] text-muted-foreground uppercase tracking-widest">{label}</div>
                  <div className="text-sm font-bold truncate max-w-[120px]" style={{ color }}>{String(value)}</div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Severity distribution bar */}
        {summary?.severity_distribution && (
          <div className="road-card rounded-xl p-4">
            <div className="flex items-center gap-2 mb-3">
              <BarChart3 size={13} className="text-purple-400" />
              <h3 className="text-xs font-bold">Health Distribution</h3>
            </div>
            <div className="flex gap-1 h-3 rounded-full overflow-hidden">
              {[
                ["excellent", "#10b981"], ["good", "#22c55e"], ["moderate", "#f59e0b"],
                ["poor", "#f97316"], ["critical", "#ef4444"],
              ].map(([key, color]) => {
                const cnt = summary.severity_distribution?.[key] ?? 0;
                const pct = summary.total > 0 ? (cnt / summary.total) * 100 : 0;
                return pct > 0 ? (
                  <div key={key} style={{ width: `${pct}%`, background: color }} title={`${key}: ${cnt}`} />
                ) : null;
              })}
            </div>
            <div className="flex gap-4 mt-2 flex-wrap">
              {[
                ["Excellent", "#10b981"], ["Good", "#22c55e"], ["Moderate", "#f59e0b"],
                ["Poor", "#f97316"], ["Critical", "#ef4444"],
              ].map(([lbl, clr]) => (
                <span key={lbl} className="flex items-center gap-1 text-[10px] text-muted-foreground">
                  <span className="w-2 h-2 rounded-full" style={{ background: clr }} />{lbl}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Filters */}
        <div className="flex items-center gap-3 flex-wrap">
          <div className="relative">
            <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input type="text" placeholder="Search id or location…" value={search} onChange={e => setSearch(e.target.value)}
              className="pl-7 pr-3 py-1.5 rounded-lg bg-secondary border border-border text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-purple-500/50 w-44" />
          </div>
          <div className="flex items-center gap-1.5 flex-wrap">
            <Filter size={11} className="text-muted-foreground" />
            {SEVERITY_OPTIONS.map(s => (
              <button key={s} onClick={() => setSeverity(s)}
                className={`px-2.5 py-1 rounded-full text-[10px] font-bold transition-all capitalize ${
                  severity === s ? "bg-primary text-primary-foreground" : "bg-secondary text-muted-foreground hover:text-foreground"
                }`}>{s}</button>
            ))}
          </div>
          <button onClick={() => setSortDir(d => d === "asc" ? "desc" : "asc")}
            className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-secondary text-xs text-muted-foreground hover:text-foreground border border-border transition-all">
            {sortDir === "desc" ? <SortDesc size={11} /> : <SortAsc size={11} />}
            {sortDir === "desc" ? "Newest" : "Oldest"}
          </button>
        </div>

        {msg && (
          <div className="px-3 py-2 rounded-xl text-xs" style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", color: "#f87171" }}>
            {msg}
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-16"><Loader2 className="animate-spin text-purple-400" size={28} /></div>
        ) : filtered.length === 0 ? (
          <div className="glass rounded-xl p-12 text-center">
            <FileText size={36} className="mx-auto mb-3 text-purple-400 opacity-30" />
            <p className="text-sm font-semibold text-muted-foreground">No reports found</p>
            <p className="text-xs text-muted-foreground mt-1">Run an analysis to generate your first report</p>
          </div>
        ) : (
          <div className="grid gap-3">
            {filtered.map((r: any) => (
              <div key={r.report_id} className="glass-hover rounded-xl p-4 flex items-center gap-4 transition-all hover:scale-[1.005]">
                <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                  style={{ background: `${healthColor(r.health_score || 0)}15`, border: `1px solid ${healthColor(r.health_score || 0)}30` }}>
                  <BarChart3 size={16} style={{ color: healthColor(r.health_score || 0) }} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-bold" style={{ fontFamily: "'DM Mono',monospace" }}>
                      {r.report_id?.slice(0, 8)}...
                    </span>
                    <span className="text-xs px-2 py-0.5 rounded-full font-bold"
                      style={{ background: `${healthColor(r.health_score || 0)}15`, color: healthColor(r.health_score || 0), border: `1px solid ${healthColor(r.health_score || 0)}30` }}>
                      {healthLabel(r.health_score || 0)} · {(r.health_score || 0).toFixed(0)}/100
                    </span>
                  </div>
                  <div className="flex items-center gap-4 mt-1 text-[10px] text-muted-foreground flex-wrap">
                    <span>🕳 {r.potholes || 0} potholes</span>
                    <span>⚡ {r.cracks || 0} cracks</span>
                    {r.location && <span className="flex items-center gap-1"><MapPin size={9} />{r.location}</span>}
                    <span className="flex items-center gap-1"><Clock size={9} />{r.generated_at ? new Date(r.generated_at * 1000).toLocaleString() : "—"}</span>
                  </div>
                  {/* Health bar */}
                  <div className="mt-2 h-1 rounded-full overflow-hidden w-40" style={{ background: "rgba(255,255,255,0.06)" }}>
                    <div className="h-full rounded-full" style={{ width: `${r.health_score || 0}%`, background: healthColor(r.health_score || 0) }} />
                  </div>
                </div>
                <div className="flex gap-2 flex-shrink-0">
                  {r.has_pdf && (
                    <button onClick={() => download(r.report_id, "pdf")}
                      className="btn-solid px-3 py-1.5 rounded-lg text-[10px] font-bold flex items-center gap-1">
                      <Download size={10} /> PDF
                    </button>
                  )}
                  <button onClick={() => download(r.report_id, "json")}
                    className="btn-neon px-3 py-1.5 rounded-lg text-[10px] font-bold flex items-center gap-1">
                    <Download size={10} /> JSON
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        <p className="text-[10px] text-muted-foreground text-center pb-2">
          {filtered.length} of {reports.length} total reports shown
        </p>
      </div>
    </DashboardLayout>
  );
}
