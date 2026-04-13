import React, { createContext, useContext, useState } from "react";
import { api } from "@/lib/api";

interface User {
  username: string;
  role: "admin" | "analyst" | "user";
  name: string;
}

interface AuthContextType {
  user: User | null;
  login: (username: string, password: string) => Promise<{ ok: boolean; error?: string }>;
  logout: () => void;
  isAdmin: boolean;
  isAnalyst: boolean;
}

const AuthCtx = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(() => {
    try {
      const u = localStorage.getItem("roadai_user");
      return u ? JSON.parse(u) : null;
    } catch { return null; }
  });

  const login = async (username: string, password: string) => {
    try {
      const data = await api.post("/auth/login", { username, password });
      const token = data.token || data.access_token;
      if (!token) throw new Error("No token received");
      localStorage.setItem("roadai_token", token);
      const me: User = { username: data.username, role: data.role, name: data.name || data.username };
      localStorage.setItem("roadai_user", JSON.stringify(me));
      setUser(me);
      return { ok: true };
    } catch (e: any) {
      return { ok: false, error: e.message || "Login failed" };
    }
  };

  const logout = () => {
    localStorage.removeItem("roadai_token");
    localStorage.removeItem("roadai_user");
    setUser(null);
  };

  const isAdmin = user?.role === "admin";
  const isAnalyst = user?.role === "analyst" || user?.role === "admin";

  return (
    <AuthCtx.Provider value={{ user, login, logout, isAdmin, isAnalyst }}>
      {children}
    </AuthCtx.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth must be within AuthProvider");
  return ctx;
}
