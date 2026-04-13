import React, { createContext, useContext, useState, useEffect } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface AppSettings {
  gps_tracking_enabled: boolean;
}

interface AppSettingsContextType {
  settings: AppSettings;
  updateSettings: (newSettings: AppSettings) => Promise<void>;
  loading: boolean;
}

const AppSettingsContext = createContext<AppSettingsContextType | null>(null);

export function AppSettingsProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const [settings, setSettings] = useState<AppSettings>({ gps_tracking_enabled: false });
  const [loading, setLoading] = useState(true);

  const loadSettings = async () => {
    if (!user) return;
    try {
      const data = await api.get("/admin/settings");
      setSettings(data);
    } catch (e) {
      console.error("Failed to load app settings", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSettings();
  }, [user]);

  const updateSettings = async (newSettings: AppSettings) => {
    try {
      await api.post("/admin/settings", newSettings);
      setSettings(newSettings);
    } catch (e) {
      console.error("Failed to update settings", e);
      throw e;
    }
  };

  return (
    <AppSettingsContext.Provider value={{ settings, updateSettings, loading }}>
      {children}
    </AppSettingsContext.Provider>
  );
}

export function useAppSettings() {
  const ctx = useContext(AppSettingsContext);
  if (!ctx) throw new Error("useAppSettings must be within AppSettingsProvider");
  return ctx;
}
