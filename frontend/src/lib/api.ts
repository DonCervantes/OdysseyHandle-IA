// Cliente único de la API local. Base: VITE_API_URL (por defecto http://localhost:8000).
// Header X-API-Key solo si VITE_API_KEY está definida (la API local sin AUTOGUARD_API_KEY no la pide).
import type {
  DictamenResult, ExpedienteResponse, Health, Patch, PatchesResponse, AgentVersion, RsiJob, RunLatest,
  VehicleProfile, VersionsResponse, VehicleResponse, Prediction,
} from "./types";

export const API_URL = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") || "http://localhost:8000";
const API_KEY = (import.meta.env.VITE_API_KEY as string | undefined) || "";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function detailMessage(body: unknown): string | null {
  if (!body || typeof body !== "object" || !("detail" in body)) return null;
  const d = (body as { detail: unknown }).detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => (x && typeof x === "object" && "msg" in x ? String((x as { msg: unknown }).msg) : String(x))).join("; ");
  return null;
}

async function request<T>(path: string, init: RequestInit = {}, auth = true): Promise<T> {
  const headers = new Headers(init.headers);
  if (auth && API_KEY) headers.set("X-API-Key", API_KEY);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, `No se pudo conectar con la API en ${API_URL}. ¿Está corriendo? (bash scripts/demo.sh --start)`);
  }
  const text = await res.text();
  let body: unknown = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = text; }
  if (!res.ok) {
    if (res.status === 401) throw new ApiError(401, "Llave de API inválida o ausente (VITE_API_KEY).");
    throw new ApiError(res.status, detailMessage(body) || `Error ${res.status} en ${path}`);
  }
  return body as T;
}

export const api = {
  health: () => request<Health>("/health", {}, false),

  crearExpediente: (form: FormData) => request<ExpedienteResponse>("/expedientes", { method: "POST", body: form }),
  vehiculo: (id: string) => request<VehicleResponse>(`/vehicles/${encodeURIComponent(id)}`),
  cotizar: (perfil: VehicleProfile) => request<Prediction>("/quote", { method: "POST", body: JSON.stringify(perfil) }),

  dictamenExpediente: (form: FormData) => request<DictamenResult>("/dictamen/expediente", { method: "POST", body: form }),

  ultimaCorrida: (incluirCurva = true) => request<RunLatest>(`/runs/latest?incluir_curva=${incluirCurva}`),
  correrRsi: (params: { seed?: number; batches?: number; batch_size?: number; k?: number }) =>
    request<RsiJob>("/rsi/run", { method: "POST", body: JSON.stringify(params) }),
  estadoRsi: (jobId: string) => request<RsiJob>(`/rsi/run/${encodeURIComponent(jobId)}`),

  parches: (q: { veredicto?: string; generation?: number; limit?: number } = {}) => {
    const p = new URLSearchParams();
    if (q.veredicto) p.set("veredicto", q.veredicto);
    if (q.generation != null) p.set("generation", String(q.generation));
    if (q.limit != null) p.set("limit", String(q.limit));
    const qs = p.toString();
    return request<PatchesResponse>(`/patches${qs ? `?${qs}` : ""}`);
  },
  aprobarParche: (id: string, razon: string) =>
    request<{ patch: Patch; version: AgentVersion }>(`/patches/${encodeURIComponent(id)}/approve`, { method: "POST", body: JSON.stringify({ razon }) }),
  rechazarParche: (id: string, razon: string) =>
    request<{ patch: Patch }>(`/patches/${encodeURIComponent(id)}/reject`, { method: "POST", body: JSON.stringify({ razon }) }),

  versiones: () => request<VersionsResponse>("/versions/cotizador"),
  revertir: (sha: string) => request<{ version: AgentVersion }>(`/versions/cotizador/revert/${encodeURIComponent(sha)}`, { method: "POST" }),
};

// Guarda/recupera la respuesta de un expediente para poder recargar su página.
export function guardarExpediente(r: ExpedienteResponse) {
  try { sessionStorage.setItem(`expediente:${r.vehicle_id}`, JSON.stringify(r)); } catch { /* sin storage */ }
}
export function leerExpediente(id: string): ExpedienteResponse | null {
  try {
    const s = sessionStorage.getItem(`expediente:${id}`);
    return s ? (JSON.parse(s) as ExpedienteResponse) : null;
  } catch { return null; }
}
