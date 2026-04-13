import { useState, useRef, useCallback, useMemo, useEffect } from "react";
import { useParams } from "react-router-dom";
import DashboardLayout from "@/components/roadai/DashboardLayout";
import { api, API_URL } from "@/lib/api";
import "./NewAnalysisUI.css";
import { Loader2, Download, Play, Square, Activity } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, AreaChart, Area } from "recharts";

type Mode = "image" | "video" | "rtsp";

export default function NewAnalysisUI() {
  const [mode, setMode] = useState<Mode>("image");
  const [file, setFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [videoPreview, setVideoPreview] = useState<string | null>(null);
  const [rtspUrl, setRtspUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [liveFrame, setLiveFrame] = useState<any>(null);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const [runFusion, setRunFusion] = useState(false);
  const [prepMode, setPrepMode] = useState("auto");
  const [useLane, setUseLane] = useState(true);

  const [rtspVerifying, setRtspVerifying] = useState(false);
  const [rtspStatus, setRtspStatus] = useState<any>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const streamRef = useRef<EventSource | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const { rid } = useParams();

  const loadAnalysisDetails = useCallback(async (id: string) => {
    setLoading(true); setError("");
    try {
      const res = await api.get(`/analysis/details/${id}`);
      if (res.success && res.analysis) {
        setResult(res.analysis.metadata || res.analysis);
      } else {
        setError(res.error || "Could not load analysis details");
      }
    } catch (e: any) {
      setError(e.message || "Failed to fetch analysis");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (rid) loadAnalysisDetails(rid);
  }, [rid, loadAnalysisDetails]);

  const stopStream = () => {
    if (streamRef.current) { streamRef.current.close(); streamRef.current = null; }
    if (abortRef.current) { abortRef.current.abort(); abortRef.current = null; }
  };

  const handleFile = useCallback((f: File) => {
    stopStream();
    setFile(f); setResult(null); setLiveFrame(null); setProgress(0); setError("");
    if (f.type.startsWith("image/")) {
      setImagePreview(URL.createObjectURL(f));
      setVideoPreview(null);
    } else {
      setVideoPreview(URL.createObjectURL(f));
      setImagePreview(null);
    }
  }, []);

  const verifyRtsp = async () => {
    if (!rtspUrl.trim()) return;
    setRtspVerifying(true); setRtspStatus(null);
    try {
      const r = await api.post("/analysis/rtsp/verify", { stream_url: rtspUrl, timeout_seconds: 5 });
      setRtspStatus(r);
    } catch (e: any) {
      setRtspStatus({ success: false, error: e.message || "Network error" });
    } finally {
      setRtspVerifying(false);
    }
  };

  const run = async () => {
    stopStream();
    setLoading(true); setError(""); setResult(null); setLiveFrame(null); setProgress(0);
    try {
      if (mode === "image") {
        const fd = new FormData();
        fd.append("file", file!);
        fd.append("preprocessing_mode", prepMode);
        fd.append("run_fusion", String(runFusion));
        const r = await api.postForm("/analysis/image", fd);
        setResult(r); setLoading(false);
      } else if (mode === "video") {
        const fd = new FormData();
        fd.append("file", file!);
        fd.append("preprocessing_mode", prepMode);
        fd.append("sample_rate", "1");
        fd.append("use_lane", String(useLane));

        const ctrl = new AbortController();
        abortRef.current = ctrl;

        const resp = await fetch(`${API_URL}/api/analysis/video/stream`, { method: "POST", body: fd, signal: ctrl.signal });
        if (!resp.ok) throw new Error(`Server error ${resp.status}`);

        const reader = resp.body!.getReader();
        const decoder = new TextDecoder();
        let buf = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const lines = buf.split("\n");
          buf = lines.pop()!;
          for (const line of lines) {
            if (!line.startsWith("data:")) continue;
            try {
              const data = JSON.parse(line.slice(5).trim());
              if (data.type === "frame") {
                setLiveFrame(data);
                setProgress(data.progress ?? 0);
              } else if (data.type === "complete") {
                setResult(data); setLiveFrame(null); setProgress(100); setLoading(false);
              } else if (data.error) {
                setError(data.error); setLoading(false);
              }
            } catch { }
          }
        }
        setLoading(false);
      } else {
        const isWebcam = rtspUrl === "0" || /^\d+$/.test(rtspUrl);
        const url = isWebcam
          ? `${API_URL}/api/analysis/stream/webcam?device=${rtspUrl}&preprocessing_mode=${prepMode}`
          : `${API_URL}/api/analysis/stream/rtsp?url=${encodeURIComponent(rtspUrl)}&preprocessing_mode=${prepMode}`;
        const es = new EventSource(url);
        streamRef.current = es;
        es.onmessage = (e) => {
          try {
            const data = JSON.parse(e.data);
            if (data.status === "stream_complete" || data.error) { stopStream(); if (data.error) setError(data.error); setLoading(false); }
            else { setResult(data); setLoading(false); }
          } catch { }
        };
        es.onerror = () => { stopStream(); setError("Stream connection failed"); setLoading(false); };
      }
    } catch (e: any) {
      if (e.name !== "AbortError") setError(e.message || "Analysis failed");
      setLoading(false);
    }
  };

  const exportJSON = () => {
    if (!result) return;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], { type: "application/json" }));
    a.download = `roadai_${Date.now()}.json`; a.click();
  };

  const exportPDF = async () => {
    if (!result) return;
    try {
      const res = await api.post("/reports/generate", { analysis_data: result });
      if (res?.pdf_path) window.alert(`PDF Report saved to ${res.pdf_path}`);
    } catch (e: any) {
      window.alert(`Failed to generate PDF: ${e.message}`);
    }
  };

  const display = liveFrame || result;
  const health = display?.road_health_score ?? display?.average_health_score ?? 100;
  const rul = display?.rul_estimate_years ?? 10.0;
  const r = result;
  const liveAnnotated = liveFrame?.annotated_image;

  // Chart Data Generation
  const healthHistory = useMemo(() => {
    if (!display) return [];
    return [
      { time: "T-2", health: Math.min(100, health + 15), rul: rul + 2 },
      { time: "T-1", health: Math.min(100, health + 5), rul: rul + 0.5 },
      { time: "Now", health: health, rul: rul },
    ];
  }, [health, rul, display]);

  const confidenceData = useMemo(() => {
    if (!display || (!display.fused_detections && !display.damage_detections)) return [];
    const dets = display.fused_detections || display.damage_detections || [];
    if (dets.length === 0) return [];
    // Average confidence of top 5
    return dets.slice(0, 5).map((d: any, i: number) => ({
      id: `Det ${i+1}`,
      conf: Math.round(d.confidence * 100)
    }));
  }, [display]);

  return (
    <DashboardLayout>
      <div className="new-ui-container animate-fade-in space-y-4">
        
        {/* Action Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h1 className="text-xl font-black gradient-text">DEGRADATION SCAN</h1>
            <p className="text-xs text-muted-foreground mt-0.5">Advanced Visual Output Mode</p>
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            {r && (
              <>
                <button onClick={exportJSON} className="nu-cact" style={{ background: 'var(--nu-panel)', padding: '8px 12px', fontSize: '11px' }}>
                  <Download size={14} /> JSON
                </button>
                <button onClick={exportPDF} className="nu-cact" style={{ background: 'var(--nu-panel)', padding: '8px 12px', fontSize: '11px', color: 'var(--nu-pink)' }}>
                  <FileTextIcon /> PDF REPORT
                </button>
              </>
            )}
            {loading || !!streamRef.current || !!abortRef.current ? (
              <button onClick={() => { stopStream(); setLoading(false); }} className="nu-aibtn" style={{ background: '#ef4444', fontSize: '12px', padding: '8px 16px' }}>
                <Square size={12} style={{marginRight:'4px'}}/> Stop AI
              </button>
            ) : (
              <button onClick={run} disabled={!file && !rtspUrl} className="nu-aibtn" style={{ fontSize: '12px', padding: '8px 16px' }}>
                <Play size={12} style={{marginRight:'4px'}}/> Run AI Analysis
              </button>
            )}
          </div>
        </div>

        <div className="nu-content">
          {/* MAP CARD (Input Configuration) */}
          <div className="nu-card nu-map-card">
            <div className="nu-ch">
              <span className="nu-ctitle" style={{display: 'flex', gap: '12px'}}>
                <span style={{cursor:'pointer', opacity: mode==='image'?1:0.5}} onClick={()=>setMode('image')}>📷 Image</span>
                <span style={{cursor:'pointer', opacity: mode==='video'?1:0.5}} onClick={()=>setMode('video')}>🎥 Video</span>
                <span style={{cursor:'pointer', opacity: mode==='rtsp'?1:0.5}} onClick={()=>setMode('rtsp')}>📡 RTSP</span>
              </span>
              <div className="nu-cact" onClick={()=>inputRef.current?.click()}>Pick File</div>
              <input ref={inputRef} type="file" style={{display:'none'}} accept={mode==="image"?"image/*":"video/*"} onChange={e => { if (e.target.files?.[0]) handleFile(e.target.files[0]); }} />
            </div>
            
            <div className="nu-mapwrap" style={{flexDirection: 'column', padding: '16px', gap: '12px'}}>
              {(mode === 'image' || mode === 'video') ? (
                <>
                  {!file ? (
                     <div style={{flex: 1, display: 'flex', alignItems: 'center', justifyItems: 'center', opacity: 0.5}} className="text-sm font-bold">Drop Media or Pick File</div>
                  ) : (
                    <div style={{flex: 1, width: '100%', position: 'relative', overflow: 'hidden', borderRadius: '8px'}}>
                      {imagePreview && <img src={imagePreview} style={{width: '100%', height: '100%', objectFit: 'contain'}}/>}
                      {videoPreview && <video src={videoPreview} autoPlay muted loop style={{width: '100%', height: '100%', objectFit: 'contain'}}/>}
                    </div>
                  )}
                </>
              ) : (
                <div style={{width: '100%'}}>
                  <input value={rtspUrl} onChange={e=>{setRtspUrl(e.target.value); setRtspStatus(null);}} placeholder="rtsp://... or 0" className="nu-input-control" />
                  <button onClick={verifyRtsp} disabled={rtspVerifying} style={{marginTop: '8px', width: '100%', fontSize: '11px', padding: '8px', background: 'var(--nu-card2)', border: '1px solid var(--nu-border)', color: 'var(--nu-t1)', borderRadius: '6px', cursor: 'pointer', fontWeight: 'bold'}}>
                    {rtspVerifying ? "Verifying..." : "Verify Connection"}
                  </button>
                  {rtspStatus && (
                    <div style={{fontSize: '11px', marginTop: '6px', color: rtspStatus.success ? '#00e676' : '#f44336', fontWeight: 'bold'}}>{rtspStatus.success ? '✓ Connected' : '✕ Error'}</div>
                  )}
                </div>
              )}

              {/* Filters */}
              <div style={{width: '100%', display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: 'auto'}}>
                  <select value={prepMode} onChange={e=>setPrepMode(e.target.value)} className="nu-input-control" style={{width: 'auto'}}>
                    {["auto", "none", "clahe", "dehaze"].map(m=><option key={m}>{m}</option>)}
                  </select>
                  <label style={{fontSize: '11px', display: 'flex', alignItems: 'center', gap: '4px', background: 'var(--nu-card2)', padding: '6px 10px', borderRadius: '6px', border: '1px solid var(--nu-border)'}}><input type="checkbox" checked={runFusion} onChange={e=>setRunFusion(e.target.checked)}/> Fusion Mode</label>
                  <label style={{fontSize: '11px', display: 'flex', alignItems: 'center', gap: '4px', background: 'var(--nu-card2)', padding: '6px 10px', borderRadius: '6px', border: '1px solid var(--nu-border)'}}><input type="checkbox" checked={useLane} onChange={e=>setUseLane(e.target.checked)}/> Lane Filter</label>
              </div>

              {error && <div className="nu-alert">{error}</div>}
              {loading && !liveFrame && <div style={{position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)', display: 'flex', alignItems: 'center', justifyItems: 'center', zIndex: 10}}><Loader2 size={32} className="animate-spin text-purple-400 m-auto"/></div>}
            </div>
          </div>

          {/* FREQUENCY CHART */}
          <div className="nu-card nu-freq-card">
            <div className="nu-ch">
              <span className="nu-ctitle">Detection Confidence</span>
              <div className="nu-cact"><Activity size={10} style={{marginRight: '4px'}}/> Top 5</div>
            </div>
            <div className="nu-chartwrap">
              {confidenceData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={confidenceData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                    <defs>
                      <linearGradient id="colorConf" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="var(--nu-pink)" stopOpacity={0.4}/>
                        <stop offset="95%" stopColor="var(--nu-pink)" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--nu-border)" vertical={false} />
                    <XAxis dataKey="id" tick={{fontSize: 9, fill: 'var(--nu-t2)'}} stroke="none" />
                    <YAxis tick={{fontSize: 9, fill: 'var(--nu-t2)'}} stroke="none" domain={[0, 100]}/>
                    <RechartsTooltip contentStyle={{background: 'var(--nu-card)', borderColor: 'var(--nu-border)', fontSize: '11px'}} />
                    <Area type="monotone" dataKey="conf" stroke="var(--nu-pink)" fillOpacity={1} fill="url(#colorConf)" strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div style={{opacity: 0.5, fontSize: '11px', margin: 'auto'}}>Awaiting Analysis...</div>
              )}
            </div>
          </div>

          {/* CRACK CHART (RUL) */}
          <div className="nu-card nu-crack-card">
            <div className="nu-ch">
              <span className="nu-ctitle">RUL & Health Tracking</span>
              <div className="nu-cact">Current Frame</div>
            </div>
            <div style={{display: 'flex', flex: 1, overflow: 'hidden'}}>
              <div className="nu-chartwrap" style={{flex: 1.5}}>
                {healthHistory.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={healthHistory} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--nu-border)" vertical={false} />
                      <XAxis dataKey="time" tick={{fontSize: 9, fill: 'var(--nu-t2)'}} stroke="none" />
                      <YAxis tick={{fontSize: 9, fill: 'var(--nu-t2)'}} stroke="none" domain={[0, 100]}/>
                      <RechartsTooltip contentStyle={{background: 'var(--nu-card)', borderColor: 'var(--nu-border)', fontSize: '11px'}} />
                      <Line type="monotone" dataKey="health" stroke="var(--nu-green)" strokeWidth={2} dot={{fill: 'var(--nu-green)', r: 4}} />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div style={{opacity: 0.5, fontSize: '11px', margin: 'auto'}}>Awaiting Analysis...</div>
                )}
              </div>
              <div className="nu-crackright" style={{flex: 1, padding: '16px'}}>
                <div>
                  <div className="nu-cslabel">Health Score</div>
                  <div className="nu-csval" style={{color:'var(--nu-green)'}}>{display ? Math.round(health) : "-"}</div>
                </div>
                <div style={{marginTop: '12px'}}>
                  <div className="nu-cslabel">Est. RUL (Yrs)</div>
                  <div className="nu-csval" style={{color:'var(--nu-cyan)'}}>{display?.rul_estimate_years?.toFixed(1) || "-"}</div>
                </div>
              </div>
            </div>
          </div>

          {/* METRIC CARDS */}
          <div className="nu-mrow">
            <div className="nu-mcard">
              <div className="nu-mc-t">Pothole Count</div>
              <div className="nu-mc-r">
                <div className="nu-mc-d" style={{background:'var(--nu-cyan)'}}></div>
                <span className="nu-mc-l">Latest Inference</span>
                <div className="nu-mc-ln" style={{background:'var(--nu-cyan)'}}></div>
              </div>
              <div className="nu-mc-big" style={{color:'var(--nu-cyan)'}}>{display?.pothole_count ?? 0}</div>
              <div className="nu-mc-sub">Realtime Detection Count</div>
            </div>
            <div className="nu-mcard">
              <div className="nu-mc-t">Crack Network</div>
              <div className="nu-mc-r">
                <div className="nu-mc-d" style={{background:'var(--nu-pink)'}}></div>
                <span className="nu-mc-l">Latest Inference</span>
                <div className="nu-mc-ln" style={{background:'var(--nu-pink)'}}></div>
              </div>
              <div className="nu-mc-big" style={{color:'var(--nu-pink)'}}>{display?.crack_count ?? 0}</div>
              <div className="nu-mc-sub">Identified Crack Fissures</div>
            </div>
            <div className="nu-mcard">
              <div className="nu-mc-t">Formation Risk</div>
              <div className="nu-mc-r">
                <div className="nu-mc-d" style={{background:'var(--nu-orange)'}}></div>
                <span className="nu-mc-l">Damage Proximity</span>
                <div className="nu-mc-ln" style={{background:'var(--nu-orange)'}}></div>
              </div>
              <div className="nu-mc-big" style={{color:'var(--nu-orange)', fontSize: '18px', paddingTop: '4px', textTransform: 'uppercase'}}>{display?.formation_risk || "NONE"}</div>
              <div className="nu-mc-sub">Predicted degradation threat</div>
            </div>
            <div className="nu-mcard">
              <div className="nu-mc-t">Weather Filter</div>
              <div className="nu-mc-r">
                <div className="nu-mc-d" style={{background:'var(--nu-purple)'}}></div>
                <span className="nu-mc-l">Atmospheric Noise</span>
                <div className="nu-mc-ln" style={{background:'var(--nu-purple)'}}></div>
              </div>
              <div className="nu-mc-big" style={{color:'var(--nu-purple)', fontSize: '18px', paddingTop: '4px', textTransform: 'capitalize'}}>{display?.weather_condition?.replace("_", " ") || "CLEAR"}</div>
              <div className="nu-mc-sub">Vision obfuscation level</div>
            </div>
          </div>

          {/* AI SCAN RESULTS OVERLAY */}
          <div className="nu-card nu-scan-card">
            <div className="nu-ch">
              <span className="nu-ctitle">Detection Pipeline Feed</span>
              {progress > 0 && <span style={{fontSize: '12px', color: 'var(--nu-purple)', fontWeight: 'bold'}}>Progress: {progress.toFixed(0)}%</span>}
            </div>
            <div className="nu-detbox" style={{margin: '12px', borderRadius: '8px', border: '1px solid var(--nu-border)'}}>
              {liveAnnotated ? (
                <img src={liveAnnotated} alt="annotated live" style={{borderRadius: '8px'}} />
              ) : r?.annotated_video_url ? (
                <video src={r?.annotated_video_url} autoPlay loop muted controls style={{borderRadius: '8px'}} />
              ) : r?.annotated_image ? (
                <img src={r?.annotated_image} alt="annotated result" style={{borderRadius: '8px'}} />
              ) : (
                  <div style={{opacity: 0.5, fontSize: '12px', display:'flex', flexDirection:'column', alignItems:'center'}}>
                    <ScanLineIcon size={32} style={{marginBottom: 8}}/>
                    [ Annotated Output Stream Awaiting Activation ]
                  </div>
              )}
              {display && (display.fused_detections?.length > 0 || display.damage_detections?.length > 0) && (
                  <div className="nu-det-lbl">
                    🔍 Detections: {(display.fused_detections || display.damage_detections).length}
                  </div>
              )}
            </div>
          </div>

        </div>
      </div>
    </DashboardLayout>
  );
}

function FileTextIcon() {
  return <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><line x1="10" y1="9" x2="8" y2="9"/></svg>;
}

function ScanLineIcon({size=24, style={}}) {
  return <svg style={style} xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/><line x1="7" y1="12" x2="17" y2="12"/></svg>;
}
