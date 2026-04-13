import { useNavigate } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import { useEffect, useState, useRef } from "react";
import { publicApi, healthColor } from "@/lib/api";
import HealthGauge from "@/components/roadai/HealthGauge";
import { Route, Shield, Activity, BarChart3, Zap, Eye, ArrowRight, Upload, Loader2, AlertTriangle, Filter, Radio } from "lucide-react";

const FEATURES = [
  { icon:Eye,      title:"Real-Time AI Detection",   desc:"Detect potholes, cracks & road damage from images, video, webcam or RTSP streams with YOLO best.pt." },
  { icon:Activity, title:"Health Score + RUL",        desc:"0–100 road health score with Remaining Useful Life via XGBoost ML + AASHTO deterioration model." },
  { icon:Zap,      title:"DeepLab Segmentation",      desc:"DeepLabV3 road segmentation removes wall/building false positives from detections." },
  { icon:BarChart3,title:"Multi-Model Benchmarks",    desc:"Compare YOLOv8/v11, EfficientDet, Faster R-CNN. Honest published metrics clearly labeled." },
  { icon:Shield,   title:"MiDaS Depth Estimation",    desc:"Real MiDaS depth maps estimate pothole severity and improve RUL prediction accuracy." },
  { icon:Filter,   title:"Wall vs Road Filter",       desc:"9-stage pipeline filters non-road surfaces. Active lane prioritisation for dashcam use." },
];

const SEV_COLOR: Record<string,string> = { critical:"#ef4444", high:"#f97316", medium:"#f59e0b", low:"#10b981" };

export default function Landing() {
  const { user } = useAuth();
  const nav = useNavigate();
  useEffect(()=>{ if(user) nav("/dashboard"); },[user,nav]);
  const [file,setFile] = useState<File|null>(null);
  const [loading,setLoading] = useState(false);
  const [result,setResult] = useState<any>(null);
  const [error,setError] = useState("");
  const [demoMode,setDemoMode] = useState<"image"|"video">("image");
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile=(f:File)=>{ setFile(f); setResult(null); setError(""); };
  const runDemo=async()=>{
    if(!file) return; setLoading(true); setError(""); setResult(null);
    try {
      const fd=new FormData(); fd.append("file",file);
      const r = await publicApi.postForm(demoMode==="image"?"/image":"/video",fd);
      setResult(r);
    } catch(e:any){ setError(e.message||"Analysis failed"); } finally { setLoading(false); }
  };
  const health=result?.road_health_score??result?.average_health_score??100;

  return (
    <div className="min-h-screen grid-bg text-foreground overflow-x-hidden">
      {/* Nav */}
      <nav className="fixed top-0 left-0 right-0 z-50 px-6 py-4 flex items-center justify-between"
        style={{background:"rgba(8,6,18,0.9)",backdropFilter:"blur(20px)",borderBottom:"1px solid rgba(168,85,247,0.1)"}}>
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{background:"linear-gradient(135deg,#6C63FF,#a855f7,#ec4899)"}}>
            <Radio size={14} className="text-white"/>
          </div>
          <span className="font-black gradient-text tracking-widest text-sm">ROADAI</span>
          <span className="text-[9px] px-2 py-0.5 rounded-full text-purple-400" style={{background:"rgba(168,85,247,0.1)",border:"1px solid rgba(168,85,247,0.2)",fontFamily:"'DM Mono',monospace"}}>v4.0</span>
        </div>
        <button onClick={()=>nav("/login")} className="btn-solid px-5 py-2 rounded-xl text-xs font-bold tracking-wider">
          LAUNCH PLATFORM →
        </button>
      </nav>

      {/* Hero */}
      <section className="pt-28 pb-16 px-6 text-center relative overflow-hidden">
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-1/4 left-1/4 w-[500px] h-[500px] rounded-full opacity-10 animate-spin-slow"
            style={{background:"radial-gradient(circle,rgba(108,99,255,0.6) 0%,transparent 70%)"}}/>
          <div className="absolute bottom-1/4 right-1/4 w-[400px] h-[400px] rounded-full opacity-8 animate-spin-slow"
            style={{background:"radial-gradient(circle,rgba(236,72,153,0.5) 0%,transparent 70%)",animationDirection:"reverse"}}/>
        </div>
        <div className="relative max-w-4xl mx-auto">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full mb-6 text-xs font-semibold"
            style={{background:"rgba(168,85,247,0.1)",border:"1px solid rgba(168,85,247,0.25)",color:"#c084fc"}}>
            <div className="w-1.5 h-1.5 rounded-full bg-green-400 animate-glow"/>
            PRODUCTION-GRADE ROAD AI — GPU ACCELERATED
          </div>
          <h1 className="text-5xl md:text-7xl font-black mb-6 leading-none">
            <span className="gradient-text">ROAD</span>
            <span className="text-foreground">AI</span>
          </h1>
          <p className="text-xl text-muted-foreground max-w-2xl mx-auto mb-8 leading-relaxed">
            Industry-grade road degradation intelligence. Real YOLO detection + DeepLabV3 segmentation + MiDaS depth + XGBoost RUL. No simulation. No fakes.
          </p>
          <div className="flex items-center justify-center gap-4 flex-wrap">
            <button onClick={()=>nav("/login")} className="btn-solid px-8 py-3.5 rounded-xl font-bold tracking-wider text-sm flex items-center gap-2">
              ENTER PLATFORM <ArrowRight size={16}/>
            </button>
            <button onClick={()=>document.getElementById("demo")?.scrollIntoView({behavior:"smooth"})}
              className="btn-neon px-8 py-3.5 rounded-xl font-bold tracking-wider text-sm">
              TRY FREE DEMO
            </button>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="py-16 px-6 max-w-6xl mx-auto">
        <h2 className="text-2xl font-black text-center mb-3 gradient-text">REAL AI MODULES</h2>
        <p className="text-center text-muted-foreground text-sm mb-10">Every module uses real ML/CV — no simulations</p>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {FEATURES.map((f,i)=>(
            <div key={i} className="glass-hover rounded-xl p-5" style={{animationDelay:`${i*0.1}s`}}>
              <div className="w-10 h-10 rounded-xl flex items-center justify-center mb-4"
                style={{background:"rgba(168,85,247,0.12)",border:"1px solid rgba(168,85,247,0.2)"}}>
                <f.icon size={18} className="text-purple-400"/>
              </div>
              <h3 className="font-bold mb-2 text-sm">{f.title}</h3>
              <p className="text-xs text-muted-foreground leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Live Demo */}
      <section id="demo" className="py-16 px-6 max-w-5xl mx-auto">
        <h2 className="text-2xl font-black text-center mb-3 gradient-text">FREE LIVE DEMO</h2>
        <p className="text-center text-muted-foreground text-sm mb-10">No login required — upload a road image or video</p>
        <div className="glass rounded-2xl p-6" style={{boxShadow:"0 0 60px rgba(168,85,247,0.1)"}}>
          <div className="flex gap-2 mb-5">
            {(["image","video"] as const).map(m=>(
              <button key={m} onClick={()=>setDemoMode(m)}
                className={`px-4 py-2 rounded-lg text-xs font-bold tracking-wider transition-all ${demoMode===m?"btn-solid":"btn-neon"}`}>
                {m.toUpperCase()}
              </button>
            ))}
          </div>
          <div onClick={()=>inputRef.current?.click()}
            className="border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all mb-4"
            style={{borderColor:file?"rgba(168,85,247,0.5)":"rgba(168,85,247,0.2)",background:file?"rgba(168,85,247,0.05)":"transparent"}}>
            <input ref={inputRef} type="file" accept={demoMode==="image"?"image/*":"video/*"} className="hidden"
              onChange={e=>{ if(e.target.files?.[0]) handleFile(e.target.files[0]); }} />
            {file ? (
              <div>
                <div className="text-sm font-semibold text-purple-300">{file.name}</div>
                <div className="text-xs text-muted-foreground mt-1">{(file.size/1024/1024).toFixed(2)} MB</div>
                <button onClick={e=>{e.stopPropagation();setFile(null);}} className="text-xs text-red-400 mt-2 hover:text-red-300">Remove</button>
              </div>
            ) : (
              <div>
                <Upload size={28} className="mx-auto mb-2 text-purple-400 opacity-60"/>
                <div className="text-sm font-semibold text-muted-foreground">Drop road {demoMode} here</div>
                <div className="text-xs text-muted-foreground mt-1">Click to browse</div>
              </div>
            )}
          </div>
          {error && <div className="mb-4 px-3 py-2 rounded-lg text-xs" style={{background:"rgba(239,68,68,0.1)",border:"1px solid rgba(239,68,68,0.3)",color:"#f87171"}}>{error}</div>}
          <button onClick={runDemo} disabled={!file||loading}
            className="w-full py-3 rounded-xl btn-solid text-sm font-bold tracking-wider disabled:opacity-50">
            {loading ? <><Loader2 size={14} className="inline animate-spin mr-2"/>ANALYZING...</> : "RUN AI ANALYSIS"}
          </button>

          {result && (
            <div className="mt-6 space-y-4 animate-slide-up">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[[`${Math.round(health)}/100`,"Road Health",healthColor(health)],
                  [result.pothole_count??0,"Potholes","#ef4444"],
                  [result.crack_count??0,"Cracks","#f59e0b"],
                  [`${result.rul_estimate_years?.toFixed(1)??10}y`,"RUL Est.","#a855f7"]].map(([v,l,c])=>(
                  <div key={l} className="glass rounded-xl p-3 text-center">
                    <div className="text-xl font-black" style={{color:c as string}}>{v}</div>
                    <div className="text-[10px] text-muted-foreground mt-0.5">{l}</div>
                  </div>
                ))}
              </div>
              {result.annotated_image && (
                <div className="relative rounded-xl overflow-hidden" style={{border:"1px solid rgba(168,85,247,0.2)"}}>
                  <img src={result.annotated_image} alt="annotated" className="w-full object-contain" style={{maxHeight:400}}/>
                  <div className="absolute top-2 right-2 px-2 py-1 rounded text-[10px] font-bold"
                    style={{background:"rgba(8,6,18,0.85)",border:"1px solid rgba(168,85,247,0.3)",fontFamily:"'DM Mono',monospace",color:"#c084fc"}}>
                    AI ANNOTATED
                  </div>
                </div>
              )}
              {result.damage_detections?.length>0 && (
                <div className="space-y-1.5">
                  <div className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2">Detected Defects</div>
                  {result.damage_detections.slice(0,4).map((d:any,i:number)=>(
                    <div key={i} className="flex items-center gap-3 px-3 py-2 rounded-lg"
                      style={{background:"rgba(168,85,247,0.05)",border:"1px solid rgba(168,85,247,0.1)"}}>
                      <div className="w-2 h-2 rounded-full" style={{background:SEV_COLOR[d.severity]??SEV_COLOR.medium}}/>
                      <span className="text-xs font-semibold capitalize">{d.class_name||d.damage_type}</span>
                      <span className="text-xs text-muted-foreground ml-auto" style={{fontFamily:"'DM Mono',monospace"}}>{(d.confidence*100).toFixed(0)}%</span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded badge-${d.severity}`}>{d.severity}</span>
                    </div>
                  ))}
                </div>
              )}
              <div className="text-center pt-2">
                <button onClick={()=>nav("/login")} className="btn-neon px-6 py-2.5 rounded-xl text-xs font-bold tracking-wider">
                  FULL PLATFORM ACCESS →
                </button>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* Footer */}
      <footer className="py-8 px-6 text-center" style={{borderTop:"1px solid rgba(168,85,247,0.1)"}}>
        <div className="gradient-text font-black text-lg mb-1">ROADAI v4.0</div>
        <p className="text-xs text-muted-foreground">GPU-Accelerated Road Intelligence • FastAPI • YOLO • DeepLabV3 • MiDaS • XGBoost</p>
      </footer>
    </div>
  );
}
