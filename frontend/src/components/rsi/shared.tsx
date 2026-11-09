// Piezas compartidas de las pantallas RSI (Resumen, Laboratorio, Parches, Versiones).
import { useMemo } from "react";
import type { AgentVersion, Patch } from "../../lib/types";

/* ------------------------------------------------------------------ colores para recharts
   recharts necesita strings de color; se leen los tripletes RGB de los tokens de index.css en tiempo de
   ejecución (con los mismos valores como respaldo si no hay DOM). */
const TOKENS = ["paper", "cream", "panel", "line", "ink", "muted", "faint", "taupe", "sand", "ok", "warn", "alta", "info"] as const;
type Token = (typeof TOKENS)[number];
const FALLBACK: Record<Token, string> = {
  paper: "252 251 248", cream: "246 242 234", panel: "255 255 255", line: "233 227 215", ink: "28 26 23",
  muted: "111 103 89", faint: "165 155 138", taupe: "140 122 95", sand: "203 185 156", ok: "47 125 82",
  warn: "181 134 44", alta: "179 65 47", info: "108 127 138",
};

export type Palette = Record<Token, string> & { alpha: (t: Token, a: number) => string };

export function useChartColors(): Palette {
  return useMemo(() => {
    const css = typeof window !== "undefined" ? getComputedStyle(document.documentElement) : null;
    const raw = {} as Record<Token, string>;
    for (const t of TOKENS) raw[t] = (css?.getPropertyValue(`--${t}`).trim() || FALLBACK[t]).replace(/\s+/g, " ");
    const out = {} as Record<Token, string>;
    for (const t of TOKENS) out[t] = `rgb(${raw[t]})`;
    return { ...out, alpha: (t: Token, a: number) => `rgb(${raw[t]} / ${a})` };
  }, []);
}

/** Color por variante del experimento: reglas fijas (rojo), solo parámetros (taupe), auto-mejora (verde). */
export const VARIANTE_TONO = { estatico: "alta", parametros: "taupe", rsi: "ok" } as const;

/* ------------------------------------------------------------------ veredictos */
export type Tono = "ok" | "warn" | "alta" | "info";
export const VEREDICTO: Record<string, { label: string; tone: Tono; cls: string }> = {
  aceptado: { label: "Aceptado", tone: "ok", cls: "border-ok/30 bg-ok/10 text-ok" },
  rechazado: { label: "Rechazado", tone: "warn", cls: "border-warn/30 bg-warn/10 text-warn" },
  invalido: { label: "Inválido", tone: "alta", cls: "border-alta/30 bg-alta/10 text-alta" },
  pendiente: { label: "Pendiente", tone: "info", cls: "border-info/30 bg-info/10 text-info" },
};
export const veredictoDe = (p: Pick<Patch, "veredicto">) => VEREDICTO[p.veredicto ?? "pendiente"] ?? VEREDICTO.pendiente;

export function VerdictBadge({ patch }: { patch: Pick<Patch, "veredicto"> }) {
  const v = veredictoDe(patch);
  return <span className={`inline-flex items-center whitespace-nowrap rounded-md border px-2 py-0.5 text-[12px] font-semibold ${v.cls}`}>{v.label}</span>;
}

/* ------------------------------------------------------------------ versiones */
export const ESTADO_VERSION: Record<AgentVersion["estado"], { label: string; cls: string }> = {
  campeon: { label: "En producción", cls: "border-ok/30 bg-ok/10 text-ok" },
  retador: { label: "Retadora", cls: "border-warn/30 bg-warn/10 text-warn" },
  sombra: { label: "En sombra", cls: "border-info/30 bg-info/10 text-info" },
  retirado: { label: "Retirada", cls: "border-line bg-cream text-muted" },
};
export function EstadoBadge({ estado }: { estado: AgentVersion["estado"] }) {
  const v = ESTADO_VERSION[estado] ?? { label: estado, cls: "border-line bg-cream text-muted" };
  return <span className={`inline-flex items-center whitespace-nowrap rounded-md border px-2 py-0.5 text-[12px] font-semibold ${v.cls}`}>{v.label}</span>;
}

/* ------------------------------------------------------------------ métricas */
export const METRICA_LABEL: Record<string, string> = {
  loss: "Pérdida media",
  loss_asimetrica: "Pérdida asimétrica",
  ganancia: "Ganancia",
  peor_delta: "Peor segmento (Δ)",
  loss_holdout: "Pérdida holdout",
  regret: "Regret",
};
export const labelMetrica = (k: string) => METRICA_LABEL[k] || k.replace(/_/g, " ");
/** Las métricas que son proporciones (ganancia, deltas) se muestran como %; el resto como número. */
export const esProporcion = (k: string) => /ganancia|delta|ratio|mejora|fraccion|tasa/.test(k);
export const fmtMetrica = (k: string, v: number | undefined | null) => {
  if (v == null || Number.isNaN(v)) return "—";
  if (esProporcion(k)) return `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v * 100).toFixed(1)}%`;
  return v.toLocaleString("es-MX", { maximumFractionDigits: Math.abs(v) >= 100 ? 0 : 3 });
};

/** Cambio relativo de la pérdida de un parche (negativo = baja la pérdida = mejora). */
export function cambioPerdida(p: Patch): number | null {
  const a = p.metrics_before?.loss, b = p.metrics_after?.loss;
  if (a == null || b == null || !a) return null;
  return (b - a) / a;
}

export const fmtSegmento = (seg: Record<string, unknown>) =>
  Object.entries(seg ?? {}).map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : String(v)}`);

/* ------------------------------------------------------------------ origen del parche
   Los parches de una corrida se guardan como `<run_id>-<variante>-g<gen>-…` (autoguard/rsi/loop.py), p.ej.
   `demo-seed42-rsi-g1-1-ajuste_factor` o `sim-42-02652207-parametros-g3-0-…`. Los aprobados a mano o de otras
   fuentes pueden no traer prefijo: entonces runId/variante quedan en null. */
export const VARIANTES = ["estatico", "parametros", "rsi"] as const;
export type Variante = (typeof VARIANTES)[number];
const ORIGEN_RE = /^(?:(.+?)-)?(estatico|parametros|rsi)-(g\d.*)$/;
export function origenParche(patchId: string): { runId: string | null; variante: Variante | null } {
  const m = ORIGEN_RE.exec(patchId ?? "");
  if (!m) return { runId: null, variante: null };
  return { runId: m[1] || null, variante: m[2] as Variante };
}

/** Tono según el signo de una mejora (positiva = bien). */
export const tonoMejora = (v: number | null | undefined): "ok" | "alta" | undefined =>
  v == null || Number.isNaN(v) || v === 0 ? undefined : v > 0 ? "ok" : "alta";

/** Saludo según la hora local. */
export function saludo(d = new Date()) {
  const h = d.getHours();
  return h < 12 ? "Buenos días" : h < 19 ? "Buenas tardes" : "Buenas noches";
}
