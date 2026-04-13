import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Cpu, Activity, CheckCircle, XCircle } from "lucide-react";

export default function RuntimeDiagnosticsPanel() {
  const [status, setStatus] = useState<any>(null);
  useEffect(()=>{
    api.get("/analysis/stream/status").then(setStatus).catch(()=>{});
  },[]);
  if(!status) return null;
  const items = [
    {label:"Defect Model", value:status.defect_model, ok:!status.defect_sim},
    {label:"Object Model", value:status.object_model, ok:!status.object_sim},
    {label:"Segmentation", value:status.segmentation?.method||"N/A", ok:!!status.segmentation?.loaded},
    {label:"Depth",        value:status.depth?.method||"N/A",        ok:!!status.depth?.loaded},
    {label:"RUL Engine",   value:status.rul?.method||"heuristic",    ok:status.rul?.ml_ready},
  ];
  return (
    <div className="glass rounded-xl p-4 space-y-2">
      <div className="flex items-center gap-2 text-[10px] font-bold text-muted-foreground uppercase tracking-wider">
        <Cpu size={11} className="text-purple-400"/>Runtime Diagnostics
      </div>
      {items.map(({label,value,ok})=>(
        <div key={label} className="flex items-center gap-2 text-xs">
          {ok ? <CheckCircle size={11} className="text-green-400 flex-shrink-0"/>
               :<XCircle size={11} className="text-yellow-400 flex-shrink-0"/>}
          <span className="text-muted-foreground w-24 flex-shrink-0">{label}</span>
          <span className="text-[10px] truncate" style={{fontFamily:"'DM Mono',monospace",color:ok?"#a3e635":"#fbbf24"}}>{value}</span>
        </div>
      ))}
    </div>
  );
}
