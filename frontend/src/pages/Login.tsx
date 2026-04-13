import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import { Radio, Eye, EyeOff, Loader2, Shield } from "lucide-react";

const PARTICLES = Array.from({length:20},(_,i)=>({
  id:i, x:Math.random()*100, y:Math.random()*100,
  size:Math.random()*3+1, dur:Math.random()*8+4, delay:Math.random()*4
}));

export default function Login() {
  const [u,setU] = useState("admin");
  const [p,setP] = useState("admin123");
  const [show,setShow] = useState(false);
  const [loading,setLoading] = useState(false);
  const [error,setError] = useState("");
  const { login, user } = useAuth();
  const nav = useNavigate();
  useEffect(()=>{ if(user) nav("/dashboard"); },[user,nav]);

  const submit = async(e:React.FormEvent)=>{
    e.preventDefault(); setLoading(true); setError("");
    const ok = await login(u,p);
    if(!ok){ setError("Invalid credentials. Try admin/admin123"); setLoading(false); }
  };

  return (
    <div className="min-h-screen grid-bg flex items-center justify-center p-4 relative overflow-hidden">
      {/* Animated BG orbs */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-1/4 -left-1/4 w-[600px] h-[600px] rounded-full opacity-20 animate-spin-slow"
          style={{background:"radial-gradient(circle,rgba(108,99,255,0.4) 0%,transparent 70%)"}}/>
        <div className="absolute -bottom-1/4 -right-1/4 w-[500px] h-[500px] rounded-full opacity-15 animate-spin-slow"
          style={{background:"radial-gradient(circle,rgba(236,72,153,0.4) 0%,transparent 70%)",animationDirection:"reverse"}}/>
        {PARTICLES.map(pt=>(
          <div key={pt.id} className="absolute rounded-full animate-float"
            style={{
              left:`${pt.x}%`,top:`${pt.y}%`,
              width:`${pt.size}px`,height:`${pt.size}px`,
              background:"rgba(168,85,247,0.6)",
              animationDuration:`${pt.dur}s`,animationDelay:`${pt.delay}s`
            }}/>
        ))}
      </div>

      <div className="w-full max-w-sm relative z-10 animate-slide-up">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl mb-4 relative"
            style={{background:"linear-gradient(135deg,#6C63FF,#a855f7,#ec4899)"}}>
            <Radio size={28} className="text-white" />
            <div className="absolute -top-1 -right-1 w-3 h-3 rounded-full bg-green-400 border-2 border-background animate-glow"/>
          </div>
          <h1 className="text-3xl font-black gradient-text tracking-wide">ROADAI</h1>
          <p className="text-sm text-muted-foreground mt-1">Road Intelligence Platform v4.0</p>
        </div>

        {/* Card */}
        <div className="glass rounded-2xl p-8" style={{boxShadow:"0 0 60px rgba(168,85,247,0.15)"}}>
          <div className="flex items-center gap-2 mb-6">
            <Shield size={14} className="text-purple-400" />
            <span className="text-xs text-muted-foreground tracking-wider">SECURE ACCESS</span>
          </div>
          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-muted-foreground mb-1.5 tracking-wider">USERNAME</label>
              <input value={u} onChange={e=>setU(e.target.value)} required
                className="w-full px-4 py-3 rounded-xl text-sm outline-none transition-all"
                style={{background:"rgba(168,85,247,0.06)",border:"1px solid rgba(168,85,247,0.2)",color:"#e2d9f3",fontFamily:"'DM Mono',monospace"}}
                onFocus={e=>{e.target.style.borderColor="rgba(168,85,247,0.5)";e.target.style.boxShadow="0 0 15px rgba(168,85,247,0.15)"}}
                onBlur={e=>{e.target.style.borderColor="rgba(168,85,247,0.2)";e.target.style.boxShadow="none"}}
                placeholder="admin" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-muted-foreground mb-1.5 tracking-wider">PASSWORD</label>
              <div className="relative">
                <input type={show?"text":"password"} value={p} onChange={e=>setP(e.target.value)} required
                  className="w-full px-4 py-3 pr-10 rounded-xl text-sm outline-none transition-all"
                  style={{background:"rgba(168,85,247,0.06)",border:"1px solid rgba(168,85,247,0.2)",color:"#e2d9f3",fontFamily:"'DM Mono',monospace"}}
                  onFocus={e=>{e.target.style.borderColor="rgba(168,85,247,0.5)";e.target.style.boxShadow="0 0 15px rgba(168,85,247,0.15)"}}
                  onBlur={e=>{e.target.style.borderColor="rgba(168,85,247,0.2)";e.target.style.boxShadow="none"}}
                  placeholder="••••••••" />
                <button type="button" onClick={()=>setShow(!show)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-purple-400 transition-colors">
                  {show?<EyeOff size={14}/>:<Eye size={14}/>}
                </button>
              </div>
            </div>
            {error && (
              <div className="px-3 py-2 rounded-lg text-xs" style={{background:"rgba(239,68,68,0.1)",border:"1px solid rgba(239,68,68,0.3)",color:"#f87171"}}>
                {error}
              </div>
            )}
            <button type="submit" disabled={loading}
              className="w-full py-3 rounded-xl text-sm font-bold tracking-wider transition-all btn-solid disabled:opacity-50 mt-2">
              {loading ? <><Loader2 size={14} className="inline animate-spin mr-2"/>AUTHENTICATING...</> : "ENTER PLATFORM"}
            </button>
          </form>
          <div className="mt-5 pt-4 border-t border-border/50 space-y-1.5">
            <p className="text-[10px] text-muted-foreground text-center mb-2 tracking-wider">DEFAULT CREDENTIALS</p>
            {[["admin","admin123","Full Access"],["analyst","analyst123","Analysis"],["user","user123","View Only"]].map(([u,p,r])=>(
              <button key={u} onClick={()=>{setU(u);setP(p);}}
                className="w-full flex items-center justify-between px-3 py-1.5 rounded-lg text-[10px] transition-all hover:bg-white/5"
                style={{fontFamily:"'DM Mono',monospace",color:"rgba(168,85,247,0.7)"}}>
                <span>{u} / {p}</span><span className="text-muted-foreground">{r}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
