import { useEffect, useState, useRef, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { GoogleMap, useJsApiLoader, Marker, Polyline, InfoWindow, Autocomplete } from "@react-google-maps/api";
import DashboardLayout from "@/components/roadai/DashboardLayout";
import { api, API_URL } from "@/lib/api";
import {
  MapPin, RefreshCw, AlertTriangle, CheckCircle,
  Loader2, Filter, BarChart3, Navigation, Camera, FileDown, Search, Zap, X
} from "lucide-react";
import * as XLSX from 'xlsx';
import html2canvas from "html2canvas";

const SEV_COLOR: Record<string, string> = {
  critical: "#ef4444",
  high:     "#f97316",
  medium:   "#eab308",
  low:      "#22c55e",
  none:     "#6b7280",
};

const URGENCY_BADGE: Record<string, string> = {
  critical: "bg-red-500/15 text-red-400 border-red-500/30",
  high:     "bg-orange-500/15 text-orange-400 border-orange-500/30",
  medium:   "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
  low:      "bg-green-500/15 text-green-400 border-green-500/30",
  none:     "bg-secondary text-muted-foreground border-border",
};

/* Google Maps Config */
const mapContainerStyle = {
  width: '100%',
  height: '480px'
};

const defaultCenter = {
  lat: 20.5937,
  lng: 78.9629
};

function SegmentCard({ seg }: { seg: any }) {
  return (
    <div className="road-card rounded-xl border border-border p-4 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold truncate">{seg.label}</p>
          <p className="text-[10px] font-mono text-muted-foreground">
            {seg.lat_bucket?.toFixed(5)}, {seg.lon_bucket?.toFixed(5)}
          </p>
        </div>
        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${URGENCY_BADGE[seg.maintenance_urgency] ?? URGENCY_BADGE.none}`}>
          {(seg.maintenance_urgency || "none").toUpperCase()}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2 text-center">
        {[["Avg Health", seg.avg_health?.toFixed(0), "text-foreground"],
          ["Potholes",   seg.total_potholes,           "text-red-400"],
          ["Cracks",     seg.total_cracks,              "text-yellow-400"],
        ].map(([l, v, c]) => (
          <div key={l as string} className="bg-secondary/50 rounded-lg p-2">
            <p className={`text-base font-bold ${c}`}>{v}</p>
            <p className="text-[9px] text-muted-foreground">{l}</p>
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between text-[10px] text-muted-foreground">
        <span>
          {seg.event_count} events · Trend:{" "}
          <strong className={seg.trend==="worsening"?"text-red-400":seg.trend==="improving"?"text-green-400":"text-muted-foreground"}>
            {seg.trend}
          </strong>
        </span>
        <span>RUL: {seg.avg_rul?.toFixed(1)}y</span>
      </div>
    </div>
  );
}

export default function MapPage() {
  const [searchParams] = useSearchParams();
  const [events,    setEvents]    = useState<any[]>([]);
  const [segments,  setSegments]  = useState<any[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [sevFilter, setSevFilter] = useState("all");
  const [view,      setView]      = useState<"map"|"segments">("map");
  const [sessionEvents, setSessionEvents] = useState<any[]>([]); // For breadcrumbs
  
  const [map, setMap] = useState<google.maps.Map | null>(null);
  const [userPos, setUserPos] = useState<google.maps.LatLngLiteral | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<any>(null);
  const [analyzingSat, setAnalyzingSat] = useState(false);
  const [searchBox, setSearchBox] = useState<google.maps.places.Autocomplete | null>(null);
  const [toast, setToast] = useState<{ msg: string, type: "success" | "error" | "info" } | null>(null);
  const [lastSearch, setLastSearch] = useState<google.maps.LatLngLiteral | null>(null);

  useEffect(() => {
    if (toast) {
      const t = setTimeout(() => setToast(null), 3000);
      return () => clearTimeout(t);
    }
  }, [toast]);
  
  const mapRef = useRef<HTMLDivElement>(null);

  const { isLoaded } = useJsApiLoader({
    id: 'google-map-script',
    googleMapsApiKey: (import.meta as any).env.VITE_GOOGLE_MAPS_API_KEY || "",
    libraries: ["places"]
  });

  const load = async () => {
    setLoading(true);
    try {
      const [evRes, segRes] = await Promise.all([
        api.get("/geo/events?limit=200"),
        api.get("/geo/segments?limit=50")
      ]);
      if (evRes.success !== false) setEvents(evRes.events || []);
      if (segRes.success !== false) setSegments(segRes.segments || []);
    } catch (e) {
      console.error("Failed to load map data", e);
    } finally {
      setLoading(false);
    }
  };

  const onSearchLoad = (autocomplete: google.maps.places.Autocomplete) => {
    setSearchBox(autocomplete);
  };

  const onPlaceChanged = () => {
    if (searchBox !== null) {
      const place = searchBox.getPlace();
      if (place.geometry && place.geometry.location && map) {
        map.panTo(place.geometry.location);
        map.setZoom(18);
      }
    }
  };

  const onMapLoad = useCallback((map: google.maps.Map) => {
    setMap(map);
    load();
  }, []);

  /* Auto-detect GPS on mount */
  useEffect(() => {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          const coords = { lat: pos.coords.latitude, lng: pos.coords.longitude };
          setUserPos(coords);
          if (map) map.panTo(coords);
        },
        () => console.warn("Geolocation failed or denied.")
      );
    }
  }, [map]);

  const filtered = sevFilter === "all" ? events : events.filter(e => e.severity === sevFilter);

  const breadcrumbPath = sessionEvents.map(e => ({ lat: e.latitude, lng: e.longitude }));

  const captureAndAnalyze = async () => {
    if (!map || !mapRef.current) return;
    setAnalyzingSat(true);
    try {
      // Use html2canvas for a real zero-cost capture of the map area
      const canvas = await html2canvas(mapRef.current, {
        useCORS: true,
        allowTaint: true,
        logging: false,
        ignoreElements: (el) => el.classList.contains('gm-style-cc') || el.classList.contains('gmnoprint')
      });
      
      const imageData = canvas.toDataURL("image/jpeg", 0.8);
      const center = map.getCenter();
      const zoom = map.getZoom();

      const res = await api.post("/analysis/satellite", {
        lat: center?.lat(),
        lng: center?.lng(),
        zoom: zoom,
        image: imageData
      });
      
      if (res.success !== false) {
        setEvents(prev => [res, ...prev]);
        setSessionEvents(prev => [...prev, res]);
        setSelectedEvent(res);
        setToast({ msg: "Satellite Analysis Complete!", type: "success" });
      }
    } catch (err) {
      console.error("Satellite analysis failed", err);
      setToast({ msg: "Capture failed: Map API Error", type: "error" });
    } finally {
      setAnalyzingSat(false);
    }
  };

  /* Excel Export */
  const exportToExcel = () => {
    const data = events.map(e => ({
      ID: e.id,
      Timestamp: new Date(e.timestamp * 1000).toLocaleString(),
      Latitude: e.latitude,
      Longitude: e.longitude,
      Severity: (e.severity || "none").toUpperCase(),
      Health: e.road_health_score,
      Potholes: e.pothole_count,
      Cracks: e.crack_count,
      RUL: e.rul_estimate_years,
      Location: e.location_label
    }));
    
    const ws = XLSX.utils.json_to_sheet(data);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Detection History");
    XLSX.writeFile(wb, `RoadAI_History_${Date.now()}.xlsx`);
  };

  return (
    <DashboardLayout>
      <div className="space-y-5">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
              <MapPin size={20} className="text-primary"/> Satellite GIS Dashboard
            </h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              {events.length} historical detections · {userPos ? "User Location Active" : "Detecting GPS..."}
            </p>
          </div>
          <div className="flex gap-2">
            <button onClick={exportToExcel}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-border text-sm hover:bg-secondary transition-colors text-green-400">
              <FileDown size={13}/> Export Excel
            </button>
            <button onClick={load}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-border text-sm hover:bg-secondary transition-colors">
              <RefreshCw size={13} className={loading ? "animate-spin" : ""}/> Refresh
            </button>
          </div>
        </div>

        {/* View toggle */}
        <div className="flex gap-2">
          {(["map","segments"] as const).map(v => (
            <button key={v} onClick={() => setView(v)}
              className={`px-4 py-2 rounded-lg text-sm font-medium border transition-colors ${
                view === v
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-secondary text-muted-foreground border-border hover:text-foreground"
              }`}>
              {v === "map" ? "🗺 Satellite Map" : "📊 Historical Table"}
            </button>
          ))}
        </div>

        {view === "map" && (
          <div className="space-y-4">
            {/* Severity filter pills + Capture button */}
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div className="flex items-center gap-4 flex-1">
                <div className="flex items-center gap-2">
                  <Filter size={13} className="text-muted-foreground"/>
                  {["all","critical","high","medium","low"].map(s => (
                    <button key={s} onClick={() => setSevFilter(s)}
                      className={`px-3 py-1 rounded-full text-xs font-semibold border transition-colors capitalize ${
                        sevFilter === s
                          ? "bg-primary text-primary-foreground border-primary"
                          : "border-border text-muted-foreground hover:text-foreground"
                      }`}>
                      {s === "all" ? "All" : s}
                    </button>
                  ))}
                </div>

                {/* Search Bar */}
                {isLoaded && (
                  <div className="flex-1 max-w-sm relative">
                    <Autocomplete
                      onLoad={onSearchLoad}
                      onPlaceChanged={() => {
                        if (searchBox) {
                          const place = searchBox.getPlace();
                          if (place.geometry && place.geometry.location) {
                            setLastSearch({ lat: place.geometry.location.lat(), lng: place.geometry.location.lng() });
                          }
                        }
                        onPlaceChanged();
                      }}
                    >
                      <div className="relative">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={14} />
                        <input
                          type="text"
                          placeholder="Search road or location..."
                          className="w-full pl-9 pr-4 py-2 bg-secondary/50 border border-border rounded-xl text-xs focus:bg-secondary focus:outline-none transition-all"
                        />
                        {lastSearch && (
                          <button onClick={() => { captureAndAnalyze(); setLastSearch(null); }}
                            className="absolute right-2 top-1.5 px-2 py-1 bg-primary text-primary-foreground text-[10px] font-bold rounded-lg animate-fade-in shadow-lg">
                            GO & ANALYZE
                          </button>
                        )}
                      </div>
                    </Autocomplete>
                  </div>
                )}
              </div>
              
              <button onClick={captureAndAnalyze} disabled={analyzingSat || !isLoaded}
                className="flex items-center gap-2 px-4 py-2 rounded-xl bg-purple-500/10 border border-purple-500/30 text-purple-400 font-bold text-xs hover:bg-purple-500/20 transition-all">
                {analyzingSat ? <Loader2 size={14} className="animate-spin"/> : <Camera size={14}/>}
                Analyze Satellite View
              </button>
            </div>

            {/* Map Container */}
            <div ref={mapRef} id="satellite-map-div" className="road-card rounded-xl border border-border overflow-hidden relative" style={{ height: "480px" }}>
              {!isLoaded ? (
                <div className="absolute inset-0 flex items-center justify-center bg-card">
                  <Loader2 size={24} className="animate-spin text-primary"/>
                </div>
              ) : (
                <GoogleMap
                  mapContainerStyle={mapContainerStyle}
                  center={userPos || (filtered.length > 0 ? { lat: filtered[0].latitude, lng: filtered[0].longitude } : defaultCenter)}
                  zoom={userPos ? 17 : 13}
                  onLoad={onMapLoad}
                  options={{
                    mapTypeId: 'satellite',
                    streetViewControl: false,
                    mapTypeControl: false,
                    fullscreenControl: false,
                    styles: [] // Standard bright style as requested
                  }}
                >
                  {/* Markers */}
                  {filtered.map((ev: any) => (
                    <Marker
                      key={ev.id}
                      position={{ lat: ev.latitude, lng: ev.longitude }}
                      icon={{
                        path: google.maps.SymbolPath.CIRCLE,
                        fillColor: SEV_COLOR[ev.severity] || SEV_COLOR.none,
                        fillOpacity: 0.9,
                        strokeColor: "#ffffff",
                        strokeWeight: 2,
                        scale: 7
                      }}
                      onClick={() => setSelectedEvent(ev)}
                    />
                  ))}

                  {/* Info Window */}
                  {selectedEvent && (
                    <InfoWindow
                      position={{ lat: selectedEvent.latitude, lng: selectedEvent.longitude }}
                      onCloseClick={() => setSelectedEvent(null)}
                    >
                      <div className="p-1 min-w-[160px] text-zinc-900">
                        <p className="text-[10px] font-bold uppercase" style={{ color: SEV_COLOR[selectedEvent.severity] }}>
                          {selectedEvent.severity} — {selectedEvent.source_type}
                        </p>
                        <p className="text-[11px] font-bold mt-1">Health: {selectedEvent.road_health_score?.toFixed(0)}/100</p>
                        <p className="text-[10px] text-zinc-500">RUL: {selectedEvent.rul_estimate_years?.toFixed(1)}y</p>
                        <hr className="my-1 border-zinc-200"/>
                        <p className="text-[9px] text-zinc-400 mb-2">{new Date(selectedEvent.timestamp * 1000).toLocaleString()}</p>
                        <a href={`/dashboard/${selectedEvent.id}`} className="block w-full text-center py-1 bg-purple-500 text-white rounded text-[10px] font-bold hover:bg-purple-600 transition-colors">
                          VIEW FULL REPORT
                        </a>
                      </div>
                    </InfoWindow>
                  )}

                  {/* Session Breadcrumbs Polyline */}
                  <Polyline
                    path={breadcrumbPath}
                    options={{
                      strokeColor: "#a855f7",
                      strokeOpacity: 0.8,
                      strokeWeight: 4,
                      icons: [{
                        icon: { path: google.maps.SymbolPath.FORWARD_CLOSED_ARROW },
                        offset: '100%',
                        repeat: '50px'
                      }]
                    }}
                  />
                </GoogleMap>
              )}
            </div>

            {/* Empty state */}
            {!loading && events.length === 0 && (
              <div className="flex flex-col items-center justify-center py-10 text-muted-foreground">
                <Navigation size={32} className="opacity-20 mb-2"/>
                <p className="text-sm">No GPS events found</p>
              </div>
            )}
          </div>
        )}

        {view === "segments" && (
          <div className="space-y-4">
            <div className="road-card rounded-xl border border-border p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold flex items-center gap-2">
                  <BarChart3 size={14} className="text-primary"/> Detection History & Analytics
                </h3>
                <span className="text-[10px] text-muted-foreground">{events.length} records in history</span>
              </div>
              
              {loading ? (
                <div className="flex items-center justify-center py-12"><Loader2 size={24} className="animate-spin text-primary"/></div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-border bg-secondary/30">
                        {["ID","Timestamp","Location (Lat, Lon)","Severity","Health","RUL","Reports"].map(h => (
                          <th key={h} className="text-left px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {events.map((ev) => (
                        <tr key={ev.id} className="border-b border-border last:border-0 hover:bg-secondary/20">
                          <td className="px-3 py-3 font-mono text-[10px] text-muted-foreground">#{ev.id}</td>
                          <td className="px-3 py-3">{new Date(ev.timestamp * 1000).toLocaleString()}</td>
                          <td className="px-3 py-3 font-mono text-purple-400">
                            {ev.latitude.toFixed(5)}, {ev.longitude.toFixed(5)}
                          </td>
                          <td className="px-3 py-3">
                            <span className={`text-[9px] px-2 py-0.5 rounded-full border font-bold ${URGENCY_BADGE[ev.severity] ?? URGENCY_BADGE.none}`}>
                              {(ev.severity||"none").toUpperCase()}
                            </span>
                          </td>
                          <td className="px-3 py-3 font-bold">{ev.road_health_score?.toFixed(0)}</td>
                          <td className="px-3 py-3">{ev.rul_estimate_years?.toFixed(1)}y</td>
                          <td className="px-3 py-3">
                            <div className="flex gap-2">
                              <a href={`${API_URL}/api/reports/pdf/${ev.id}`} target="_blank" className="text-primary hover:underline font-bold text-[10px]">PDF</a>
                              <a href={`${API_URL}/api/reports/json/${ev.id}`} target="_blank" className="text-muted-foreground hover:underline text-[10px]">JSON</a>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Toast Overlay */}
      {toast && (
        <div className="fixed bottom-6 right-6 z-50 animate-slide-up">
          <div className={`px-5 py-3 rounded-2xl shadow-2xl flex items-center gap-3 backdrop-blur-xl border ${
            toast.type === "success" ? "bg-green-500/10 border-green-500/30 text-green-400" :
            toast.type === "error" ? "bg-red-500/10 border-red-500/30 text-red-400" :
            "bg-primary/10 border-primary/30 text-primary"
          }`}>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
              toast.type === "success" ? "bg-green-500/20" :
              toast.type === "error" ? "bg-red-500/20" :
              "bg-primary/20"
            }`}>
              {toast.type === "success" ? <CheckCircle size={16} /> :
               toast.type === "error" ? <AlertTriangle size={16} /> :
               <Zap size={16} className="animate-pulse" />}
            </div>
            <div>
              <div className="text-[10px] uppercase font-black tracking-widest opacity-60">{toast.type}</div>
              <div className="text-xs font-bold">{toast.msg}</div>
            </div>
            <button onClick={() => setToast(null)} className="ml-2 hover:bg-white/5 p-1 rounded-lg">
              <X size={14} />
            </button>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}
