import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useEffect } from "react";
import { AuthProvider, useAuth } from "@/lib/auth";
import { AppSettingsProvider, useAppSettings } from "@/lib/AppSettingsContext";

// Titanium Modernized Pages
import Landing    from "@/pages/Landing";
import Login      from "@/pages/Login";
import Dashboard  from "@/pages/Dashboard";
import AnalysisWrapper from "@/pages/AnalysisWrapper";
import Models     from "@/pages/Models";
import Benchmarks from "@/pages/Benchmarks";
import Reports    from "@/pages/Reports";
import Alerts     from "@/pages/Alerts";
import Admin      from "@/pages/Admin";
import MapPage    from "@/pages/MapPage";
import Predictions from "@/pages/Predictions";


/**
 * PR - Protected Route
 * Enforces authentication and role-based access control.
 */
function PR({ children, adminOnly=false, analystUp=false, mapGuard=false }: { children:React.ReactNode; adminOnly?:boolean; analystUp?:boolean; mapGuard?:boolean }) {
  const { user } = useAuth();
  const { settings, loading } = useAppSettings();
  
  if (!user) return <Navigate to="/login" replace />;
  if (loading) return null; 
  
  if (adminOnly && user.role !== "admin") return <Navigate to="/dashboard" replace />;
  if (analystUp && user.role === "user") return <Navigate to="/analyze" replace />;
  
  if (mapGuard && !settings.gps_tracking_enabled) {
    return <Navigate to="/dashboard" replace />;
  }
  
  return <>{children}</>;
}

/**
 * DR - Default Redirect
 * Handles root-level redirection based on authentication state.
 */
function DR() {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (user.role === "user") return <Navigate to="/analyze" replace />;
  return <Navigate to="/dashboard" replace />;
}

export default function App() {
  useEffect(() => {
    // Force Titanium Dark Mode
    document.documentElement.classList.remove("light");
    localStorage.setItem("theme_mode", "dark");
  }, []);

  return (
    <AuthProvider>
      <AppSettingsProvider>
        <BrowserRouter>
          <Routes>
            {/* Entry Portals */}
            <Route path="/"           element={<Landing />} />
            <Route path="/login"      element={<Login />} />
            
            {/* Authenticated Application */}
            <Route path="/dashboard"  element={<PR analystUp><Dashboard /></PR>} />
            <Route path="/analyze/:rid?" element={<PR><AnalysisWrapper /></PR>} />
            <Route path="/map"        element={<PR analystUp mapGuard><MapPage /></PR>} />
            <Route path="/models"     element={<PR analystUp><Models /></PR>} />
            <Route path="/benchmarks" element={<PR analystUp><Benchmarks /></PR>} />
            <Route path="/reports"    element={<PR analystUp><Reports /></PR>} />
            <Route path="/alerts"      element={<PR><Alerts /></PR>} />
            <Route path="/predictions" element={<PR analystUp><Predictions /></PR>} />

            <Route path="/admin"       element={<PR adminOnly><Admin /></PR>} />
            
            {/* Fallback */}
            <Route path="*"           element={<DR />} />
          </Routes>
        </BrowserRouter>
      </AppSettingsProvider>
    </AuthProvider>
  );
}
