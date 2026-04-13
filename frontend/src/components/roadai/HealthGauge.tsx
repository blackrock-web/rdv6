interface Props { score: number; size?: number; label?: string; }

export default function HealthGauge({ score, size=120, label }: Props) {
  const r = (size/2) - 14;
  const cx = size/2; const cy = size/2;
  const circ = 2*Math.PI*r;
  const arc = circ * 0.75;
  const filled = arc * (score/100);
  const offset = circ * 0.125;
  const color = score>=80?"#10b981":score>=60?"#f59e0b":score>=40?"#f97316":"#ef4444";
  const glow = score>=80?"rgba(16,185,129,0.6)":score>=60?"rgba(245,158,11,0.6)":score>=40?"rgba(249,115,22,0.6)":"rgba(239,68,68,0.6)";
  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative" style={{width:size,height:size}}>
        <svg width={size} height={size} style={{transform:"rotate(-225deg)"}}>
          <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(168,85,247,0.1)" strokeWidth={8}
            strokeDasharray={`${arc} ${circ-arc}`} strokeDashoffset={-offset} strokeLinecap="round" />
          <circle cx={cx} cy={cy} r={r} fill="none" stroke={color} strokeWidth={8}
            strokeDasharray={`${filled} ${circ-filled}`} strokeDashoffset={-offset} strokeLinecap="round"
            style={{ filter:`drop-shadow(0 0 6px ${glow})`, transition:"all 1s cubic-bezier(.4,0,.2,1)" }} />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <div className="text-2xl font-black" style={{color}}>{Math.round(score)}</div>
          <div className="text-[9px] text-muted-foreground tracking-wider" style={{fontFamily:"'DM Mono',monospace"}}>/ 100</div>
        </div>
      </div>
      {label && <div className="text-xs text-muted-foreground text-center">{label}</div>}
    </div>
  );
}
