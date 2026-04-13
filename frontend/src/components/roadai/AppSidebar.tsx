import { Link, useLocation } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import { useAppSettings } from "@/lib/AppSettingsContext";
import { LayoutDashboard, ScanLine, Cpu, BarChart3, FileText, Bell, Settings, LogOut, MapPin, Radio, Zap, BrainCircuit, Truck } from "lucide-react";

const ANALYST_NAV = [
  { path:"/dashboard",  icon:LayoutDashboard, label:"Dashboard",    pulse:false },
  { path:"/analyze",    icon:ScanLine,        label:"AI Analysis",  pulse:false },
  { path:"/map",        icon:MapPin,          label:"Live Map",     pulse:false },
  { path:"/models",     icon:Cpu,             label:"Models",       pulse:false },
  { path:"/benchmarks", icon:BarChart3,       label:"Benchmarks",   pulse:false },
  { path:"/reports",     icon:FileText,      label:"Reports",       pulse:false },
  { path:"/predictions", icon:BrainCircuit,  label:"Predictions",   pulse:false },
  { path:"/alerts",      icon:Bell,          label:"Alerts & SMS",  pulse:true  },
];
const USER_NAV = [
  { path:"/analyze", icon:ScanLine, label:"AI Analysis", pulse:false },
];
const ADMIN_NAV = [{ path:"/admin", icon:Settings, label:"Admin Panel" }];

const ROLE_BADGE: Record<string,string> = {
  admin:   "bg-red-500/15 text-red-400 border border-red-500/25",
  analyst: "bg-purple-500/15 text-purple-400 border border-purple-500/25",
  user:    "bg-secondary text-muted-foreground border border-border",
};

export default function AppSidebar() {
  const { user, logout, isAnalyst, isAdmin } = useAuth();
  const { settings } = useAppSettings();
  const loc = useLocation();
  const isA = (p:string) => loc.pathname === p || loc.pathname.startsWith(p+"/");
  
  let nav = isAnalyst ? [...ANALYST_NAV] : [...USER_NAV];
  
  // Filter out Live Map if disabled
  if (!settings.gps_tracking_enabled) {
    nav = nav.filter(item => item.path !== "/map");
  }

  return (
    <aside className="fixed left-0 top-0 bottom-0 w-[230px] flex flex-col z-50 overflow-y-auto bg-card border-r border-border transition-colors duration-300">

      {/* Logo */}
      <div className="px-5 py-5" style={{ borderBottom:"1px solid rgba(168,85,247,0.1)" }}>
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center relative"
            style={{ background:"linear-gradient(135deg,#6C63FF,#a855f7,#ec4899)" }}>
            <Radio size={16} className="text-white" />
            <div className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-green-400 border-2 border-background animate-glow" />
          </div>
          <div>
            <div className="text-sm font-black tracking-widest gradient-text">ROADAI</div>
            <div className="text-[9px] text-muted-foreground tracking-wider" style={{fontFamily:"'DM Mono',monospace"}}>v4.0 Intelligence</div>
          </div>
        </div>
      </div>

      {/* Status */}
      <div className="mx-3 mt-3 px-3 py-2 rounded-lg" style={{ background:"rgba(16,185,129,0.06)", border:"1px solid rgba(16,185,129,0.15)" }}>
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 rounded-full bg-green-400 animate-glow" />
          <span className="text-[9px] text-green-400 font-semibold tracking-wider" style={{fontFamily:"'DM Mono',monospace"}}>SYSTEM ONLINE</span>
        </div>
      </div>

      {/* Nav */}
      <div className="flex-1 p-3 space-y-0.5 mt-2">
        <p className="text-[9px] font-bold text-muted-foreground uppercase tracking-[0.15em] px-3 py-2">Navigation</p>
        {nav.map(({ path, icon:Icon, label, pulse }) => (
          <Link key={path} to={path}
            className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all duration-200 group ${
              isA(path) ? "nav-active font-semibold" : "text-muted-foreground hover:text-foreground hover:bg-white/5"
            }`}>
            <Icon size={15} className={isA(path) ? "text-purple-400" : "group-hover:text-purple-400 transition-colors"} />
            <span className="flex-1">{label}</span>
            {pulse && <div className="w-1.5 h-1.5 rounded-full bg-pink-400 animate-glow" />}
          </Link>
        ))}

        {isAdmin && (
          <>
            <p className="text-[9px] font-bold text-muted-foreground uppercase tracking-[0.15em] px-3 py-2 mt-4">Admin</p>
            {ADMIN_NAV.map(({ path, icon:Icon, label }) => (
              <Link key={path} to={path}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all duration-200 ${
                  isA(path) ? "bg-red-500/10 text-red-400 border-r-2 border-red-400 font-semibold" : "text-muted-foreground hover:text-red-400 hover:bg-red-500/5"
                }`}>
                <Icon size={15} />
                <span>{label}</span>
              </Link>
            ))}
          </>
        )}
      </div>

      {/* User */}
      <div className="p-3" style={{ borderTop:"1px solid rgba(168,85,247,0.1)" }}>
        <div className="px-3 py-2.5 rounded-lg glass mb-1">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold"
              style={{ background:"linear-gradient(135deg,#a855f7,#ec4899)" }}>
              {(user?.name || user?.username || "U")[0].toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-semibold truncate">{user?.name || user?.username}</div>
              <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-bold capitalize ${ROLE_BADGE[user?.role || "user"]}`}>
                {user?.role}
              </span>
            </div>
          </div>
        </div>
        <button onClick={logout}
          className="flex items-center gap-2.5 w-full px-3 py-2 rounded-lg text-xs text-red-400/70 hover:text-red-400 hover:bg-red-500/10 transition-all">
          <LogOut size={13} />
          <span>Sign Out</span>
        </button>
      </div>
    </aside>
  );
}
