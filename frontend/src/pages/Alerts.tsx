import { useEffect, useState } from "react";
import DashboardLayout from "@/components/roadai/DashboardLayout";
import { api } from "@/lib/api";
import { Bell, CheckCircle, XCircle, AlertTriangle, Send, Loader2, RefreshCw, MessageSquare } from "lucide-react";

const SEV_COLORS: Record<string,string> = {
  critical: "border-red-500/30 bg-red-500/8",
  high: "border-orange-500/30 bg-orange-500/8",
  medium: "border-yellow-500/30 bg-yellow-500/8",
  low: "border-green-500/30 bg-green-500/8",
};

export default function Alerts() {
  const [alerts, setAlerts] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [testMsg, setTestMsg] = useState("");
  const [smsConfig, setSmsConfig] = useState<any>(null);
  const [form, setForm] = useState({ severity:"high", health:45, potholes:3, cracks:5, rul:2.5, location:"", message:"" });

  const load = () => {
    setLoading(true);
    Promise.all([
      api.get("/alerts/history?limit=30").then(d => setAlerts(d.alerts||[])),
      api.get("/alerts/stats").then(setStats),
      api.get("/alerts/sms/config").then(setSmsConfig),
    ]).catch(()=>{}).finally(()=>setLoading(false));
  };
  useEffect(()=>{ load(); },[]);

  const trigger = async () => {
    setSending(true); setTestMsg("");
    try {
      const r = await api.post("/alerts/sms/trigger", {
        severity: form.severity, health_score: form.health, pothole_count: form.potholes,
        crack_count: form.cracks, rul_estimate_years: form.rul, location_label: form.location,
        custom_message: form.message||undefined, auto_send: true,
      });
      setTestMsg(`Alert ${r.alert_id?.slice(0,8)} — SMS: ${r.sms_status}${r.error?" ("+r.error+")":""}`);
      load();
    } catch(e:any){ setTestMsg("Error: "+e.message); }
    finally{ setSending(false); }
  };

  const formatTime = (ts: number) => ts ? new Date(ts*1000).toLocaleString() : "—";

  return (
    <DashboardLayout>
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5 animate-fade-in">
        <div className="xl:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-black gradient-text">ALERTS & SMS</h1>
              <p className="text-xs text-muted-foreground mt-0.5">Twilio SMS alerts · Alert history</p>
            </div>
            <button onClick={load} className="btn-neon px-3 py-2 rounded-xl text-xs font-bold flex items-center gap-1.5">
              <RefreshCw size={11}/> Refresh
            </button>
          </div>

          {/* Stats */}
          {stats && (
            <div className="grid grid-cols-3 gap-3">
              {[["Total", stats.total||0, "#a855f7"],["Sent", stats.sent||0, "#10b981"],["Failed", stats.failed||0, "#ef4444"]].map(([l,v,c])=>(
                <div key={l as string} className="glass rounded-xl p-3 text-center">
                  <div className="text-xl font-black" style={{color:c as string}}>{v}</div>
                  <div className="text-[10px] text-muted-foreground mt-0.5">{l} Alerts</div>
                </div>
              ))}
            </div>
          )}

          {/* SMS Config status */}
          <div className="glass rounded-xl p-3 flex items-center gap-3">
            <MessageSquare size={14} className="text-purple-400 flex-shrink-0"/>
            <div className="flex-1">
              <div className="text-xs font-bold">Twilio SMS {smsConfig?.configured ? "Configured" : "Not Configured"}</div>
              <div className="text-[10px] text-muted-foreground mt-0.5">
                {smsConfig?.configured ? `From: ${smsConfig.from_number||"—"}  To: ${smsConfig.to_number||"—"}` : "Set TWILIO_* env vars to enable SMS"}
              </div>
            </div>
            {smsConfig?.configured
              ? <CheckCircle size={14} className="text-green-400"/>
              : <XCircle size={14} className="text-yellow-400"/>}
          </div>

          {/* Alert list */}
          {loading ? <div className="flex justify-center py-10"><Loader2 className="animate-spin text-purple-400" size={24}/></div>
          : alerts.length === 0 ? (
            <div className="glass rounded-xl p-10 text-center">
              <Bell size={32} className="mx-auto mb-2 text-purple-400 opacity-25"/>
              <p className="text-sm font-semibold text-muted-foreground">No alerts yet</p>
              <p className="text-xs text-muted-foreground mt-1">Use the trigger panel to test SMS alerts</p>
            </div>
          ) : (
            <div className="space-y-2">
              {alerts.map((a:any, i:number) => (
                <div key={i} className={`rounded-xl p-3.5 border ${SEV_COLORS[a.severity]||SEV_COLORS.medium}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <AlertTriangle size={12} style={{color:a.severity==="critical"?"#ef4444":a.severity==="high"?"#f97316":"#f59e0b"}}/>
                        <span className="text-xs font-bold uppercase">{a.severity}</span>
                        {a.location_label && <span className="text-[10px] text-muted-foreground">{a.location_label}</span>}
                      </div>
                      <p className="text-[11px] text-muted-foreground mt-1 leading-relaxed">{a.message?.slice(0,120)||"Road condition alert"}</p>
                      <div className="flex gap-3 mt-1.5 text-[10px] text-muted-foreground" style={{fontFamily:"'DM Mono',monospace"}}>
                        <span>H:{a.road_health_score?.toFixed(0)||"—"}</span>
                        <span>🕳{a.pothole_count||0}</span>
                        <span>⚡{a.crack_count||0}</span>
                        <span>RUL:{a.rul_estimate_years?.toFixed(1)||"—"}y</span>
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
                      <span className={`text-[9px] px-1.5 py-0.5 rounded font-bold ${a.sms_status==="sent"?"badge-low":"badge-none"}`}>
                        {a.sms_status==="sent"?"✓ SENT":"○ "+a.sms_status}
                      </span>
                      <span className="text-[9px] text-muted-foreground">{formatTime(a.created_at)}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Trigger panel */}
        <div className="space-y-4">
          <div className="glass rounded-xl p-5 space-y-4">
            <h3 className="text-sm font-black gradient-text">TRIGGER ALERT</h3>
            {[
              {label:"Severity", key:"severity", type:"select", opts:["low","medium","high","critical"]},
              {label:"Health Score", key:"health", type:"number", min:0, max:100},
              {label:"Potholes", key:"potholes", type:"number", min:0, max:50},
              {label:"Cracks", key:"cracks", type:"number", min:0, max:50},
              {label:"RUL (years)", key:"rul", type:"number", min:0, max:20, step:0.1},
              {label:"Location", key:"location", type:"text"},
              {label:"Custom Message", key:"message", type:"text"},
            ].map(({label,key,type,opts,min,max,step}:any) => (
              <div key={key}>
                <label className="block text-[10px] font-bold text-muted-foreground uppercase tracking-wider mb-1">{label}</label>
                {type==="select" ? (
                  <select value={(form as any)[key]} onChange={e=>setForm({...form,[key]:e.target.value})}
                    className="w-full px-3 py-2 rounded-lg text-xs outline-none"
                    style={{background:"rgba(168,85,247,0.06)",border:"1px solid rgba(168,85,247,0.2)",color:"#e2d9f3"}}>
                    {opts.map((o:string)=><option key={o} value={o}>{o}</option>)}
                  </select>
                ) : (
                  <input type={type} value={(form as any)[key]} step={step}
                    onChange={e=>setForm({...form,[key]:type==="number"?parseFloat(e.target.value)||0:e.target.value})}
                    className="w-full px-3 py-2 rounded-lg text-xs outline-none"
                    style={{background:"rgba(168,85,247,0.06)",border:"1px solid rgba(168,85,247,0.2)",color:"#e2d9f3",fontFamily:type==="text"?"inherit":"'DM Mono',monospace"}}
                    onFocus={e=>{e.target.style.borderColor="rgba(168,85,247,0.5)"}}
                    onBlur={e=>{e.target.style.borderColor="rgba(168,85,247,0.2)"}}/>
                )}
              </div>
            ))}
            {testMsg && (
              <div className="px-3 py-2 rounded-lg text-[10px]"
                style={{background:testMsg.includes("Error")?"rgba(239,68,68,0.1)":"rgba(16,185,129,0.1)",
                        border:`1px solid ${testMsg.includes("Error")?"rgba(239,68,68,0.3)":"rgba(16,185,129,0.3)"}`,
                        color:testMsg.includes("Error")?"#f87171":"#34d399"}}>
                {testMsg}
              </div>
            )}
            <button onClick={trigger} disabled={sending}
              className="w-full py-3 rounded-xl btn-solid text-xs font-black tracking-wider flex items-center justify-center gap-2 disabled:opacity-50">
              {sending?<><Loader2 size={13} className="animate-spin"/>SENDING...</>:<><Send size={13}/>TRIGGER SMS ALERT</>}
            </button>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
