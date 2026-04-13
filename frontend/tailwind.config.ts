import type { Config } from "tailwindcss";
const config: Config = {
  darkMode: ["class"],
  content: ["./index.html","./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))", input: "hsl(var(--input))", ring: "hsl(var(--ring))",
        background: "hsl(var(--background))", foreground: "hsl(var(--foreground))",
        primary: { DEFAULT: "hsl(var(--primary))", foreground: "hsl(var(--primary-foreground))" },
        secondary: { DEFAULT: "hsl(var(--secondary))", foreground: "hsl(var(--secondary-foreground))" },
        destructive: { DEFAULT: "hsl(var(--destructive))", foreground: "hsl(var(--destructive-foreground))" },
        muted: { DEFAULT: "hsl(var(--muted))", foreground: "hsl(var(--muted-foreground))" },
        accent: { DEFAULT: "hsl(var(--accent))", foreground: "hsl(var(--accent-foreground))" },
        card: { DEFAULT: "hsl(var(--card))", foreground: "hsl(var(--card-foreground))" },
        neon: { purple: "#a855f7", magenta: "#ec4899", cyan: "#06b6d4", green: "#10b981" },
        "road-danger": "hsl(var(--road-danger))",
        "road-warning": "hsl(var(--road-warning))",
        "road-safe": "hsl(var(--road-safe))",
      },
      borderRadius: { lg: "var(--radius)", md: "calc(var(--radius) - 2px)", sm: "calc(var(--radius) - 4px)" },
      backgroundImage: {
        "neon-gradient": "linear-gradient(135deg, #6C63FF 0%, #a855f7 40%, #ec4899 100%)",
        "dark-mesh": "radial-gradient(ellipse at 20% 50%, rgba(108,99,255,0.15) 0%, transparent 60%), radial-gradient(ellipse at 80% 20%, rgba(236,72,153,0.12) 0%, transparent 50%)",
      },
      animation: {
        "pulse-glow": "pulse-glow 2s ease-in-out infinite",
        "fade-in": "fade-in 0.4s ease-out",
        "slide-up": "slide-up 0.5s ease-out",
        "float": "float 6s ease-in-out infinite",
        "scan-line": "scan-line 2s linear infinite",
        "glow-pulse": "glow-pulse 3s ease-in-out infinite",
      },
      keyframes: {
        "pulse-glow": { "0%,100%": { opacity:"1" }, "50%": { opacity:"0.4" } },
        "fade-in": { from: { opacity:"0", transform:"translateY(8px)" }, to: { opacity:"1", transform:"translateY(0)" } },
        "slide-up": { from: { opacity:"0", transform:"translateY(20px)" }, to: { opacity:"1", transform:"translateY(0)" } },
        "float": { "0%,100%": { transform:"translateY(0px)" }, "50%": { transform:"translateY(-8px)" } },
        "scan-line": { "0%": { transform:"translateY(-100%)" }, "100%": { transform:"translateY(100vh)" } },
        "glow-pulse": { "0%,100%": { boxShadow:"0 0 20px rgba(168,85,247,0.3)" }, "50%": { boxShadow:"0 0 40px rgba(236,72,153,0.5)" } },
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
export default config;
