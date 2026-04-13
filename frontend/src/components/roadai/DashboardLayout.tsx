import { ReactNode } from "react";
import AppSidebar from "./AppSidebar";

interface DashboardLayoutProps {
  children: ReactNode;
  title?: string;
  subtitle?: string;
}

export default function DashboardLayout({ children, title, subtitle }: DashboardLayoutProps) {
  return (
    <div className="flex min-h-screen bg-background">
      <AppSidebar />
      <main className="flex-1 ml-[230px] min-h-screen overflow-y-auto">
        <div className="p-6 max-w-[1600px] mx-auto space-y-6">
          {(title || subtitle) && (
            <div className="mb-8">
              {title && <h1 className="text-2xl font-black tracking-tight text-foreground">{title}</h1>}
              {subtitle && <p className="text-sm text-muted-foreground mt-1">{subtitle}</p>}
            </div>
          )}
          {children}
        </div>
      </main>
    </div>
  );
}
