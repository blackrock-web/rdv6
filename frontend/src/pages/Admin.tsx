import { useEffect, useState } from "react";
import DashboardLayout from "@/components/roadai/DashboardLayout";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Settings, Users, Cpu, BarChart3, Trash2, Plus, Loader2, CheckCircle, Shield, Activity, Radio, Phone, Save, Database, Bell } from "lucide-react";

export default function Admin() {
  const { user } = useAuth();
  const [sysInfo, setSysInfo] = useState<any>(null);
  const [usage, setUsage] = useState<any>(null);
  const [users, setUsers] = useState<any[]>([]);
  const [health, setHealth] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState("");
  const [newUser, setNewUser] = useState({username:"",password:"",name:"",email:"",role:"analyst"});
  const [adding, setAdding] = useState(false);
  
  const [twilio, setTwilio] = useState({account_sid:"", auth_token:"", phone_number:"", target_phone:""});
  const [twilioMsg, setTwilioMsg] = useState("");
  const [modelsList, setModelsList] = useState<any[]>([]);
  const [modelMsg, setModelMsg] = useState("");
  const [uiVersion, setUiVersion] = useState(localStorage.getItem("analysis_ui") || "old");
  const [themeMode, setThemeMode] = useState(localStorage.getItem("theme_mode") || "dark");
  const [gpsEnabled, setGpsEnabled] = useState(false);
  const [purging, setPurging] = useState(false);

  const load = () => {
    setLoading(true);
    setMsg("");
    Promise.all([
      api.get("/admin/system-info").then(setSysInfo).catch(e => console.error("SysInfo failed", e)),
      api.get("/admin/usage-stats").then(setUsage).catch(e => console.error("Usage failed", e)),
      api.get("/auth/users").then(setUsers).catch(e => console.error("Users failed", e)),
      api.get("/health").then(setHealth).catch(e => console.error("Health failed", e)),
      api.get("/admin/twilio-config").then(setTwilio).catch(e => console.error("Twilio failed", e)),
      api.get("/models/list-available").then(r => setModelsList(r?.models || [])).catch(e => console.error("Models failed", e)),
      api.get("/admin/settings").then(s => setGpsEnabled(s?.gps_tracking_enabled ?? false)).catch(e => console.error("Settings failed", e)),
    ]).finally(() => setLoading(false));
  };
  useEffect(()=>{ load(); },[]);

  const addUser = async() => {
    if(!newUser.username||!newUser.password) return;
    setAdding(true); setMsg("");
    try {
      await api.post("/auth/register", newUser);
      setMsg(`✅ User '${newUser.username}' created`);
      setNewUser({username:"",password:"",name:"",email:"",role:"analyst"});
      load();
    } catch(e:any){ setMsg("❌ "+e.message); }
    finally{ setAdding(false); }
  };

  const deleteUser = async(uname:string) => {
    if(!confirm(`Delete user '${uname}'?`)) return;
    try {
      await api.del(`/auth/users/${uname}`);
      setMsg(`✅ User '${uname}' deleted`);
      load();
    } catch(e:any){ setMsg("❌ "+e.message); }
  };

  const clearUploads = async() => {
    const r = await api.del("/admin/clear-uploads").catch(e=>({deleted:0,error:e.message}));
    setMsg(`✅ Deleted ${(r as any).deleted} temp files`);
  };

  const saveTwilio = async () => {
    setTwilioMsg("");
    try {
      await api.post("/admin/twilio-config", twilio);
      setTwilioMsg("✅ Twilio config saved");
    } catch(e:any) { setTwilioMsg("❌ " + e.message); }
  };

  const setDefectModel = async (path:string) => {
    if(!path) return;
    setModelMsg("Applying...");
    try {
      await api.post("/models/set-defect-model", { target_path: path });
      setModelMsg("✅ Defect model active");
      load();
    } catch (e: any) {
      const detail = e.response?.data?.detail || e.message || "Unknown Error";
      setModelMsg("❌ " + (typeof detail === "object" ? JSON.stringify(detail) : detail));
    }
  };

  const setObjectModel = async (path: string) => {
    if (!path) return;
    setModelMsg("Applying...");
    try {
      await api.post("/models/set-object-model", { target_path: path });
      setModelMsg("✅ Object model active");
      load();
    } catch (e: any) {
      const detail = e.response?.data?.detail || e.message || "Unknown Error";
      setModelMsg("❌ " + (typeof detail === "object" ? JSON.stringify(detail) : detail));
    }
  };

  const saveUiPrefs = (type: "ui" | "theme", val: string) => {
    if (type === "ui") {
      setUiVersion(val);
      localStorage.setItem("analysis_ui", val);
    } else {
      setThemeMode(val);
      localStorage.setItem("theme_mode", val);
    }
    window.dispatchEvent(new Event("ui-prefs-changed"));
  };
  
  const toggleGps = async (val: boolean) => {
    try {
      await api.post("/admin/settings", { gps_tracking_enabled: val });
      setGpsEnabled(val);
      setMsg(`✅ GPS Tracking ${val ? "Enabled" : "Disabled"}`);
    } catch (e: any) { setMsg("❌ Failed to update GPS setting"); }
  };

  const purgeHistory = async () => {
    if (!confirm("⚠️ PERMANENT DELETE: Are you sure you want to delete ALL analysis history? This cannot be undone.")) return;
    setPurging(true);
    try {
      const r = await api.del("/admin/clear-history");
      setMsg(`✅ History Purged: Deleted ${(r as any).deleted} records`);
      load();
    } catch (e: any) { setMsg("❌ Purge failed: " + e.message); }
    finally { setPurging(false); }
  };

  const purgeAlerts = async () => {
    if (!confirm("⚠️ PERMANENT DELETE: Delete ALL alert logs?")) return;
    setPurging(true);
    try {
      const r = await api.del("/admin/clear-alerts");
      setMsg(`✅ Alerts Purged: Deleted ${(r as any).deleted} logs`);
      load();
    } catch (e: any) { setMsg("❌ Purge failed: " + e.message); }
    finally { setPurging(false); }
  };

  if(loading) return <DashboardLayout><div className="flex justify-center py-20"><Loader2 className="animate-spin text-purple-400" size={28}/></div></DashboardLayout>;

  return (
    <DashboardLayout>
      <div className="space-y-5 animate-fade-in">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{background:"linear-gradient(135deg,#ef4444,#dc2626)"}}>
            <Shield size={14} className="text-white"/>
          </div>
          <div>
            <h1 className="text-xl font-black text-red-400">ADMIN PANEL</h1>
            <p className="text-xs text-muted-foreground mt-0.5">System info · Users · Usage · Maintenance</p>
          </div>
        </div>

        {msg && <div className="px-3 py-2 rounded-xl text-xs" style={{background:msg.startsWith("✅")?"rgba(16,185,129,0.1)":"rgba(239,68,68,0.1)",border:`1px solid ${msg.startsWith("✅")?"rgba(16,185,129,0.3)":"rgba(239,68,68,0.3)"}`,color:msg.startsWith("✅")?"#34d399":"#f87171"}}>{msg}</div>}

        {/* System health */}
        {health && (
          <div className="glass rounded-xl p-4 space-y-2">
            <div className="flex items-center gap-2 text-xs font-bold text-muted-foreground uppercase tracking-wider mb-3">
              <Radio size={11} className="text-green-400"/> System Status
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
              {[
                ["API","healthy","safe"],
                ["Defect Model",health.defect_inference,health.defect_inference==="real"?"safe":"warning"],
                ["Object Model",health.object_inference,health.object_inference==="real"?"safe":"warning"],
                ["Segmentation",health.segmentation||"—",health.segmentation?.includes("loaded")?"safe":"warning"],
                ["RUL Engine",health.rul_model||"—",health.rul_model==="xgboost_ml"?"safe":"warning"],
              ].map(([k,v,t])=>(
                <div key={k as string} className="glass rounded-xl p-3 text-center">
                  <CheckCircle size={14} className={`mx-auto mb-1 ${t==="safe"?"text-green-400":"text-yellow-400"}`}/>
                  <div className="text-[10px] text-muted-foreground">{k}</div>
                  <div className={`text-[10px] font-bold mt-0.5 ${t==="safe"?"text-green-400":"text-yellow-400"}`} style={{fontFamily:"'DM Mono',monospace"}}>{v}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* UI Preferences */}
          <div className="glass rounded-xl p-4 space-y-4">
            <div className="text-xs font-bold text-muted-foreground uppercase tracking-wider flex items-center justify-between">
              <span className="flex items-center gap-2"><Settings size={11} className="text-pink-400"/> UI & Preferences</span>
            </div>
            <div className="space-y-4">
              <div>
                <label className="text-[10px] text-muted-foreground uppercase tracking-wider block mb-1">Analysis Page UI</label>
                <div className="flex gap-2">
                  <button onClick={() => saveUiPrefs("ui", "old")} className={`flex-1 py-2 rounded-lg text-xs font-bold border transition-colors ${uiVersion === "old" ? "bg-purple-500/20 border-purple-500/50 text-purple-300" : "bg-transparent border-border/50 text-muted-foreground"}`}>
                    Current UI
                  </button>
                  <button onClick={() => saveUiPrefs("ui", "new")} className={`flex-1 py-2 rounded-lg text-xs font-bold border transition-colors ${uiVersion === "new" ? "bg-pink-500/20 border-pink-500/50 text-pink-300" : "bg-transparent border-border/50 text-muted-foreground"}`}>
                    Updated UI
                  </button>
                </div>
              </div>
              <div>
                <label className="text-[10px] text-muted-foreground uppercase tracking-wider block mb-1">Theme</label>
                <div className="flex gap-2">
                  <button onClick={() => saveUiPrefs("theme", "dark")} className={`flex-1 py-2 rounded-lg text-xs font-bold border transition-colors ${themeMode === "dark" ? "bg-purple-500/20 border-purple-500/50 text-purple-300" : "bg-transparent border-border/50 text-muted-foreground"}`}>
                    Dark Mode
                  </button>
                  <button onClick={() => saveUiPrefs("theme", "light")} className={`flex-1 py-2 rounded-lg text-xs font-bold border transition-colors ${themeMode === "light" ? "bg-pink-500/20 border-pink-500/50 text-pink-300" : "bg-transparent border-border/50 text-muted-foreground"}`}>
                    Light Mode
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Maintenance & Feature Flags */}
          <div className="glass rounded-xl p-4 space-y-4">
            <div className="text-xs font-bold text-muted-foreground uppercase tracking-wider flex items-center justify-between">
              <span className="flex items-center gap-2"><Settings size={11} className="text-orange-400"/> Operations & Feature Gating</span>
            </div>
            
            <div className="space-y-4">
              <div className="flex items-center justify-between p-3 rounded-xl bg-purple-500/5 border border-purple-500/10">
                <div>
                  <div className="text-[11px] font-bold text-foreground">GPS Tracking & Live Map</div>
                  <div className="text-[9px] text-muted-foreground">Toggle visibility of map and geo-tagging features</div>
                </div>
                <button 
                  onClick={() => toggleGps(!gpsEnabled)}
                  className={`w-12 h-6 rounded-full transition-all relative ${gpsEnabled ? "bg-green-500" : "bg-muted"}`}
                >
                  <div className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-all ${gpsEnabled ? "left-7" : "left-1"}`} />
                </button>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <button onClick={purgeHistory} disabled={purging}
                  className="py-2.5 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-[10px] font-bold flex items-center justify-center gap-2 hover:bg-red-500/20 transition-all">
                  <Database size={11} /> Purge History
                </button>
                <button onClick={purgeAlerts} disabled={purging}
                  className="py-2.5 rounded-xl bg-orange-500/10 border border-orange-500/20 text-orange-400 text-[10px] font-bold flex items-center justify-center gap-2 hover:bg-orange-500/20 transition-all">
                  <Bell size={11} /> Purge Alerts
                </button>
              </div>
            </div>
          </div>

          {/* Usage stats */}
          {usage && (
            <div className="glass rounded-xl p-4 space-y-3">
              <div className="text-xs font-bold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                <Activity size={11} className="text-purple-400"/> Usage Statistics
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="glass rounded-xl p-3 text-center">
                  <div className="text-2xl font-black text-purple-400">{usage.total_analyses||0}</div>
                  <div className="text-[10px] text-muted-foreground">Total Analyses</div>
                </div>
                <div className="glass rounded-xl p-3 text-center">
                  <div className="text-2xl font-black text-pink-400">{usage.total_alerts||0}</div>
                  <div className="text-[10px] text-muted-foreground">Total Alerts</div>
                </div>
              </div>
              {usage.by_type && (
                <div className="space-y-1.5">
                  {Object.entries(usage.by_type).map(([t,c]:any)=>(
                    <div key={t} className="flex items-center justify-between text-xs">
                      <span className="text-muted-foreground capitalize">{t}</span>
                      <span className="font-bold text-purple-300" style={{fontFamily:"'DM Mono',monospace"}}>{c}</span>
                    </div>
                  ))}
                </div>
              )}
              <button onClick={clearUploads} className="w-full py-2 rounded-lg btn-neon text-[10px] font-bold flex items-center justify-center gap-1.5">
                <Trash2 size={10}/> Clear Temp Uploads
              </button>
            </div>
          )}

          {/* System info */}
          {sysInfo && (
            <div className="glass rounded-xl p-4 space-y-3">
              <div className="text-xs font-bold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                <Cpu size={11} className="text-cyan-400"/> System Info
              </div>
              {[
                ["Platform", sysInfo.platform?.split(" ")[0]||"—"],
                ["Python", sysInfo.python||"—"],
                ["CPU Cores", sysInfo.cpu_count||"—"],
                ["GPU", sysInfo.gpu?.device_name||sysInfo.gpu?.available?"GPU Available":"CPU Only"],
              ].map(([k,v])=>(
                <div key={k as string} className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">{k}</span>
                  <span className="font-bold text-cyan-300 text-right" style={{fontFamily:"'DM Mono',monospace",maxWidth:"60%",overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{v}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Twilio and Models */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* Twilio Settings */}
          <div className="glass rounded-xl p-4 space-y-4">
            <div className="text-xs font-bold text-muted-foreground uppercase tracking-wider flex items-center justify-between">
              <span className="flex items-center gap-2"><Phone size={11} className="text-green-400"/> Twilio Alerts Config</span>
              {twilioMsg && <span className={twilioMsg.startsWith("✅")?"text-green-400":"text-red-400"}>{twilioMsg}</span>}
            </div>
            <div className="space-y-2">
              {[
                ["Account SID", "account_sid", "text"],
                ["Auth Token", "auth_token", "password"],
                ["From Number", "phone_number", "text"],
                ["To Number", "target_phone", "text"]
              ].map(([l,k,t])=>(
                <div key={k}>
                  <label className="text-[9px] text-muted-foreground uppercase tracking-wider block mb-0.5">{l}</label>
                  <input type={t} value={(twilio as any)[k]} onChange={e=>setTwilio({...twilio,[k]:e.target.value})}
                    className="w-full px-3 py-2 rounded-lg text-xs outline-none"
                    style={{background:"rgba(168,85,247,0.06)",border:"1px solid rgba(168,85,247,0.15)",color:"#e2d9f3"}}
                    onFocus={e=>{e.target.style.borderColor="rgba(168,85,247,0.45)"}}
                    onBlur={e=>{e.target.style.borderColor="rgba(168,85,247,0.15)"}}/>
                </div>
              ))}
              <button onClick={saveTwilio} className="w-full mt-2 py-2 rounded-lg btn-solid text-xs font-bold flex items-center justify-center gap-1.5">
                <Save size={12}/> Save Configuration
              </button>
            </div>
          </div>

          {/* Manual Model Selection */}
          <div className="glass rounded-xl p-4 space-y-4">
            <div className="text-xs font-bold text-muted-foreground uppercase tracking-wider flex items-center justify-between">
              <span className="flex items-center gap-2"><Database size={11} className="text-pink-400"/> Manual Runtime Selection</span>
              {modelMsg && <span className={modelMsg.startsWith("✅")?"text-green-400":modelMsg.startsWith("❌")?"text-red-400":"text-yellow-400"}>{modelMsg}</span>}
            </div>
            <div className="space-y-3">
              <div>
                <label className="text-[10px] text-muted-foreground uppercase tracking-wider block mb-1">Defect Model (Road Damages)</label>
                <select onChange={e=>setDefectModel(e.target.value)} defaultValue=""
                  className="w-full px-3 py-2 rounded-lg text-xs outline-none"
                  style={{background:"rgba(168,85,247,0.06)",border:"1px solid rgba(168,85,247,0.15)",color:"#e2d9f3"}}>
                  <option value="" disabled>Select model...</option>
                  {modelsList.map((m:any)=>(
                    <option key={`def-${m.path}`} value={m.path}>{m.name} ({m.size_mb} MB)</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-[10px] text-muted-foreground uppercase tracking-wider block mb-1">Object Model (Traffic/Context)</label>
                <select onChange={e=>setObjectModel(e.target.value)} defaultValue=""
                  className="w-full px-3 py-2 rounded-lg text-xs outline-none"
                  style={{background:"rgba(168,85,247,0.06)",border:"1px solid rgba(168,85,247,0.15)",color:"#e2d9f3"}}>
                  <option value="" disabled>Select model...</option>
                  {modelsList.map((m:any)=>(
                    <option key={`obj-${m.path}`} value={m.path}>{m.name} {m.auto_dl?"(Auto DL)":""}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>
        </div>

        {/* User management */}
        <div className="glass rounded-xl p-4 space-y-4">
          <div className="text-xs font-bold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
            <Users size={11} className="text-purple-400"/> User Management
          </div>
          <div className="space-y-2">
            {users.map((u:any)=>(
              <div key={u.username} className="flex items-center gap-3 px-3 py-2.5 rounded-xl"
                style={{background:"rgba(168,85,247,0.04)",border:"1px solid rgba(168,85,247,0.1)"}}>
                <div className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0"
                  style={{background:"linear-gradient(135deg,#a855f7,#ec4899)"}}>
                  {(u.name||u.username||"?")[0].toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-bold">{u.name||u.username}</div>
                  <div className="text-[10px] text-muted-foreground">{u.email||u.username} · {u.role}</div>
                </div>
                <span className={`text-[9px] px-2 py-0.5 rounded-full font-bold capitalize ${u.role==="admin"?"badge-critical":u.role==="analyst"?"badge-medium":"badge-none"}`}>{u.role}</span>
                {u.username !== user?.username && (
                  <button onClick={()=>deleteUser(u.username)} className="text-red-400/50 hover:text-red-400 transition-colors">
                    <Trash2 size={12}/>
                  </button>
                )}
              </div>
            ))}
          </div>

          {/* Add user */}
          <div className="pt-3 border-t border-border/50">
            <div className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider mb-3">ADD USER</div>
            <div className="grid grid-cols-2 gap-2 mb-2">
              {[["Username","username","text"],["Password","password","password"],["Full Name","name","text"],["Email","email","email"]].map(([l,k,t])=>(
                <div key={k}>
                  <label className="text-[9px] text-muted-foreground uppercase tracking-wider block mb-0.5">{l}</label>
                  <input type={t} value={(newUser as any)[k]} onChange={e=>setNewUser({...newUser,[k]:e.target.value})}
                    className="w-full px-3 py-1.5 rounded-lg text-xs outline-none"
                    style={{background:"rgba(168,85,247,0.06)",border:"1px solid rgba(168,85,247,0.15)",color:"#e2d9f3"}}
                    onFocus={e=>{e.target.style.borderColor="rgba(168,85,247,0.45)"}}
                    onBlur={e=>{e.target.style.borderColor="rgba(168,85,247,0.15)"}}/>
                </div>
              ))}
            </div>
            <div className="flex gap-2">
              <select value={newUser.role} onChange={e=>setNewUser({...newUser,role:e.target.value})}
                className="flex-1 px-3 py-1.5 rounded-lg text-xs outline-none"
                style={{background:"rgba(168,85,247,0.06)",border:"1px solid rgba(168,85,247,0.15)",color:"#e2d9f3"}}>
                {["admin","analyst","user"].map(r=><option key={r} value={r}>{r}</option>)}
              </select>
              <button onClick={addUser} disabled={adding||!newUser.username||!newUser.password}
                className="btn-solid px-4 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 disabled:opacity-50">
                {adding?<Loader2 size={11} className="animate-spin"/>:<Plus size={11}/>} Add
              </button>
            </div>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
