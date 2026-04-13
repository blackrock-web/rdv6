// API Configuration — Strictly controlled via Environment Variables for Netlify/HuggingFace split
export const API_URL = (import.meta as any).env?.VITE_API_BASE_URL 
    ? (import.meta as any).env.VITE_API_BASE_URL.replace(/\/$/, "")
    : ""; // Fallback for safety, though env is preferred

const API_BASE = `${API_URL}/api`;


function headers(json = true): HeadersInit {
  const token = localStorage.getItem("roadai_token");
  const h: Record<string, string> = {
    "ngrok-skip-browser-warning": "69420"
  };
  if (json) h["Content-Type"] = "application/json";
  if (token) h["Authorization"] = `Bearer ${token}`;
  return h;
}

async function handle(res: Response) {
  if (res.status === 401) {
    localStorage.removeItem("roadai_token");
    localStorage.removeItem("roadai_user");
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  return res.json();
}

async function handleBlob(res: Response): Promise<Blob> {
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Download failed");
  }
  return res.blob();
}

export const api = {
  get: (path: string) =>
    fetch(`${API_BASE}${path}`, { headers: headers() }).then(handle),

  post: (path: string, body?: unknown) =>
    fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: headers(),
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }).then(handle),

  del: (path: string) =>
    fetch(`${API_BASE}${path}`, { method: "DELETE", headers: headers() }).then(handle),

  postForm: (path: string, form: FormData) =>
    fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: headers(false),
      body: form,
    }).then(handle),

  downloadBlob: (path: string) =>
    fetch(`${API_BASE}${path}`, { headers: headers() }).then(handleBlob),
};

/** Public API — no auth required */
export const publicApi = {
  postForm: (path: string, form: FormData) =>
    fetch(`${API_BASE}/public${path}`, {
      method: "POST",
      body: form,
    }).then(async (res) => {
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Request failed");
      }
      return res.json();
    }),
};

export function healthColor(score: number): string {
  if (score >= 80) return "hsl(142, 71%, 45%)";
  if (score >= 60) return "hsl(38, 95%, 55%)";
  if (score >= 40) return "hsl(30, 90%, 52%)";
  return "hsl(0, 80%, 58%)";
}

export function healthLabel(score: number): string {
  if (score >= 80) return "Good";
  if (score >= 60) return "Fair";
  if (score >= 40) return "Poor";
  return "Critical";
}

export function healthClass(score: number): string {
  if (score >= 80) return "health-good";
  if (score >= 60) return "health-fair";
  if (score >= 40) return "health-poor";
  return "health-critical";
}
