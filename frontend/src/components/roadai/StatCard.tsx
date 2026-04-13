import { LucideIcon } from "lucide-react";
import { TrendingUp, TrendingDown } from "lucide-react";

interface Props {
  title: string; value: React.ReactNode; icon: LucideIcon;
  variant?: "safe"|"warning"|"danger"|"info"|"purple"|"magenta";
  subtitle?: string; trend?: number;
}

const VARIANTS = {
  safe:    { color:"#10b981", glow:"rgba(16,185,129,0.2)",  bg:"rgba(16,185,129,0.08)"  },
  warning: { color:"#f59e0b", glow:"rgba(245,158,11,0.2)",  bg:"rgba(245,158,11,0.08)"  },
  danger:  { color:"#ef4444", glow:"rgba(239,68,68,0.2)",   bg:"rgba(239,68,68,0.08)"   },
  info:    { color:"#06b6d4", glow:"rgba(6,182,212,0.2)",   bg:"rgba(6,182,212,0.08)"   },
  purple:  { color:"#a855f7", glow:"rgba(168,85,247,0.2)",  bg:"rgba(168,85,247,0.08)"  },
  magenta: { color:"#ec4899", glow:"rgba(236,72,153,0.2)",  bg:"rgba(236,72,153,0.08)"  },
};

export default function StatCard({ title, value, icon: Icon, variant="info", subtitle, trend }: Props) {
  const v = VARIANTS[variant];
  return (
    <div className="glass rounded-xl p-4 animate-fade-in transition-all duration-300 hover:scale-[1.02]"
      style={{ boxShadow:`0 0 20px ${v.glow}`, borderColor: `${v.color}22` }}>
      <div className="flex items-start justify-between mb-3">
        <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground font-semibold">{title}</div>
        <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background:v.bg }}>
          <Icon size={13} style={{ color:v.color }} />
        </div>
      </div>
      <div className="text-2xl font-black tracking-tight animate-count" style={{ color:v.color }}>
        {value}
      </div>
      {(subtitle || trend !== undefined) && (
        <div className="flex items-center gap-1.5 mt-1.5">
          {trend !== undefined && (
            trend > 0
              ? <TrendingUp size={10} className="text-red-400" />
              : <TrendingDown size={10} className="text-green-400" />
          )}
          {subtitle && <div className="text-[10px] text-muted-foreground">{subtitle}</div>}
        </div>
      )}
    </div>
  );
}
