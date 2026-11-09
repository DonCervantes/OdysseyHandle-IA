// Piezas compartidas por Nuevo expediente, Expediente y Dictamen de siniestro.
import { useEffect, useRef, useState, type ReactNode } from "react";
import type { Dano } from "../../lib/types";
import { fmtMXN, fmtPct } from "../../lib/format";

/* ---------- etiquetas ---------- */

const TIPO_DANO: Record<string, string> = {
  rayon: "Rayón",
  abolladura: "Abolladura",
  estrellado: "Estrellado",
  reparacion: "Reparación",
  reemplazo: "Reemplazo",
};
export const labelTipoDano = (t: string) => TIPO_DANO[t] || t;

const FEM = new Set(["puerta", "salpicadera", "calavera", "defensa", "cajuela"]);
/** "puerta_delantera_izq" → "Puerta delantera izquierda"; "espejo_izq" → "Espejo izquierdo". */
export function labelZona(z: string) {
  const raw = z.split("_");
  const f = FEM.has(raw[0]);
  const parts = raw.map((p) => (p === "izq" ? (f ? "izquierda" : "izquierdo") : p === "der" ? (f ? "derecha" : "derecho") : p));
  const s = parts.join(" ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export const TIPO_DOC_LABEL: Record<string, string> = {
  factura: "Factura",
  tarjeta_circulacion: "Tarjeta de circulación",
  poliza_anterior: "Póliza anterior",
  otro: "Otro",
};

/** Zonas reales de data/costos_reparacion.yaml (sin `default`). */
export const ZONAS_VEHICULO = [
  "defensa_delantera", "defensa_trasera", "cofre", "cajuela", "toldo",
  "puerta_delantera_izq", "puerta_delantera_der", "puerta_trasera_izq", "puerta_trasera_der",
  "salpicadera_izq", "salpicadera_der", "parabrisas", "faro_izq", "faro_der",
  "calavera_izq", "calavera_der", "espejo_izq", "espejo_der",
] as const;

/* ---------- contenedores ---------- */

export function Section({ title, eyebrow, aside, children, className = "", id }: {
  title: string; eyebrow?: string; aside?: ReactNode; children: ReactNode; className?: string; id?: string;
}) {
  return (
    <section className={`card p-5 md:p-6 ${className}`} aria-labelledby={id}>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          {eyebrow && <div className="eyebrow mb-1">{eyebrow}</div>}
          <h2 id={id} className="text-[19px] font-semibold tracking-tight">{title}</h2>
        </div>
        {aside && <div className="flex flex-wrap items-center gap-2">{aside}</div>}
      </div>
      {children}
    </section>
  );
}

export function Collapsible({ title, children, defaultOpen = false, count }: {
  title: string; children: ReactNode; defaultOpen?: boolean; count?: number;
}) {
  return (
    <details className="group rounded-xl border border-line bg-paper" open={defaultOpen}>
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-xl px-4 py-3 text-[15px] font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-taupe [&::-webkit-details-marker]:hidden">
        <span>{title}{count != null && <span className="ml-2 text-faint">({count})</span>}</span>
        <span aria-hidden="true" className="text-faint transition group-open:rotate-180">▾</span>
      </summary>
      <div className="border-t border-line px-4 py-3">{children}</div>
    </details>
  );
}

/** Notas de "Datos simulados" / avisos grises. */
export function Note({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "warn" | "ok" }) {
  const cls = tone === "warn" ? "border-warn/30 bg-warn/5 text-warn" : tone === "ok" ? "border-ok/30 bg-ok/5 text-ok" : "border-line bg-cream text-muted";
  return <div className={`rounded-lg border px-3.5 py-2.5 text-[14px] ${cls}`}>{children}</div>;
}

/* ---------- barras ---------- */

/** Barra de 0–1 con porcentaje. */
export function ProgressBar({ value, label }: { value: number; label: string }) {
  const v = Math.max(0, Math.min(1, value || 0));
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between text-[14px]">
        <span className="text-muted">{label}</span>
        <span className="num font-semibold">{fmtPct(v, 0)}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-cream" role="progressbar" aria-valuenow={Math.round(v * 100)} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
        <div className="h-full rounded-full bg-gradient-to-r from-taupe to-sand" style={{ width: `${v * 100}%` }} />
      </div>
    </div>
  );
}

/** Intervalo [lo, hi] con el valor puntual marcado. */
export function IntervalBar({ lo, hi, value }: { lo: number; hi: number; value: number }) {
  const span = hi - lo;
  const pos = span > 0 ? Math.max(0, Math.min(1, (value - lo) / span)) : 0.5;
  return (
    <div aria-label={`Intervalo de ${fmtMXN(lo)} a ${fmtMXN(hi)}, prima ${fmtMXN(value)}`} role="img">
      <div className="relative h-3 rounded-full bg-gradient-to-r from-sand/30 via-sand/70 to-sand/30">
        <div className="absolute top-1/2 h-6 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-ink" style={{ left: `${pos * 100}%` }} />
      </div>
      <div className="num mt-2 flex justify-between text-[13px] text-muted">
        <span>{fmtMXN(lo)}</span>
        <span>{fmtMXN(hi)}</span>
      </div>
    </div>
  );
}

/** Barra centrada en 1.00: verde a la izquierda (<1 abarata), roja a la derecha (>1 encarece). */
export function FactorBar({ m }: { m: number }) {
  const d = m - 1;
  const w = Math.min(Math.abs(d) / 0.5, 1) * 50;
  return (
    <div className="relative h-2 w-full min-w-[80px] rounded-full bg-cream" aria-hidden="true">
      <div className="absolute inset-y-[-3px] left-1/2 w-px bg-faint" />
      {d !== 0 && (
        <div
          className={`absolute inset-y-0 rounded-full ${d < 0 ? "bg-ok" : "bg-alta"}`}
          style={d < 0 ? { right: "50%", width: `${w}%` } : { left: "50%", width: `${w}%` }}
        />
      )}
    </div>
  );
}

/* ---------- daños ---------- */

export function DanosList({ danos, empty = "Sin daños detectados", emptyTone = "ok" }: { danos: Dano[]; empty?: string; emptyTone?: "ok" | "info" }) {
  if (!danos.length) return <Note tone={emptyTone}>{empty}</Note>;
  return (
    <ul className="divide-y divide-line rounded-xl border border-line">
      <li className="hidden grid-cols-[1.6fr_1fr_1fr_0.8fr] gap-3 px-4 py-2 text-[12px] uppercase tracking-wider text-faint sm:grid">
        <span>Zona</span><span>Tipo</span><span className="text-right">Costo est.</span><span className="text-right">Confianza</span>
      </li>
      {danos.map((d, i) => (
        <li key={`${d.zona}-${d.tipo}-${i}`} className="grid grid-cols-2 gap-x-3 gap-y-1 px-4 py-3 text-[15px] sm:grid-cols-[1.6fr_1fr_1fr_0.8fr] sm:items-center">
          <span className="col-span-2 font-medium sm:col-span-1">{labelZona(d.zona)}</span>
          <span className="text-muted">{labelTipoDano(d.tipo)}</span>
          <span className="num text-right">{fmtMXN(d.costo_est)}</span>
          <span className="num col-span-2 text-[13px] text-muted sm:col-span-1 sm:text-right sm:text-[15px]">
            <span className="sm:hidden">Confianza </span>{fmtPct(d.confianza, 0)}
          </span>
        </li>
      ))}
    </ul>
  );
}

/* ---------- archivos ---------- */

export interface Archivo { id: string; file: File; url?: string }
let _seq = 0;
export const nuevoId = () => `f${Date.now().toString(36)}${(_seq++).toString(36)}`;

const ext = (n: string) => n.toLowerCase().split(".").pop() || "";
export function filtrarArchivos(files: File[], exts: string[]) {
  const ok = files.filter((f) => exts.includes(ext(f.name)));
  const rechazados = files.filter((f) => !exts.includes(ext(f.name))).map((f) => f.name);
  return { ok, rechazados };
}

/** Zona de arrastrar y soltar accesible (también funciona con clic o teclado). */
export function Dropzone({ id, label, hint, accept, exts, onFiles, multiple = true }: {
  id: string; label: string; hint: ReactNode; accept: string; exts: string[];
  onFiles: (files: File[], rechazados: string[]) => void; multiple?: boolean;
}) {
  const [over, setOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const handle = (list: FileList | null) => {
    if (!list || !list.length) return;
    const { ok, rechazados } = filtrarArchivos(Array.from(list), exts);
    onFiles(ok, rechazados);
  };
  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); handle(e.dataTransfer.files); }}
      className={`relative flex flex-col items-center justify-center gap-2 rounded-xl2 border-2 border-dashed px-5 py-8 text-center transition focus-within:border-taupe focus-within:ring-2 focus-within:ring-sand/50 ${over ? "border-taupe bg-cream" : "border-line bg-paper hover:border-sand"}`}
    >
      <svg viewBox="0 0 24 24" className="h-8 w-8 text-taupe" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
        <path d="M12 16V4m0 0-4 4m4-4 4 4M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <div className="text-[15px] font-medium">
        Arrastra aquí o{" "}
        <label htmlFor={id} className="cursor-pointer text-taupe underline decoration-sand underline-offset-2 hover:text-ink">elige archivos</label>
      </div>
      <div className="text-[13px] text-muted">{hint}</div>
      <input
        ref={inputRef}
        id={id}
        type="file"
        accept={accept}
        multiple={multiple}
        aria-label={label}
        className="sr-only"
        onChange={(e) => { handle(e.target.files); if (inputRef.current) inputRef.current.value = ""; }}
      />
    </div>
  );
}

/** Miniaturas de fotos con botón quitar. Revoca las URLs al desmontar. */
export function Thumbs({ fotos, onRemove }: { fotos: Archivo[]; onRemove: (id: string) => void }) {
  if (!fotos.length) return null;
  return (
    <ul className="mt-3 grid grid-cols-3 gap-3 sm:grid-cols-4 md:grid-cols-6">
      {fotos.map((f) => (
        <li key={f.id} className="group relative overflow-hidden rounded-lg border border-line bg-cream">
          <img src={f.url} alt={`Foto ${f.file.name}`} className="aspect-square w-full object-cover" />
          <div className="truncate px-2 py-1 text-[11px] text-muted" title={f.file.name}>{f.file.name}</div>
          <button
            type="button"
            onClick={() => onRemove(f.id)}
            className="absolute right-1 top-1 rounded-md bg-ink/80 px-1.5 py-0.5 text-[12px] text-paper hover:bg-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-taupe"
            aria-label={`Quitar ${f.file.name}`}
          >
            Quitar
          </button>
        </li>
      ))}
    </ul>
  );
}

/** Mantiene una lista de fotos con URLs de vista previa y las libera al desmontar. */
export function useFotos() {
  const [fotos, setFotos] = useState<Archivo[]>([]);
  const ref = useRef(fotos);
  ref.current = fotos;
  useEffect(() => () => { ref.current.forEach((f) => f.url && URL.revokeObjectURL(f.url)); }, []);
  return {
    fotos,
    agregar: (files: File[]) => {
      const nuevas = files.map((file) => ({ id: nuevoId(), file, url: URL.createObjectURL(file) })); // fuera del updater (StrictMode lo llama 2 veces)
      setFotos((p) => [...p, ...nuevas]);
    },
    quitar: (id: string) => setFotos((p) => {
      const f = p.find((x) => x.id === id);
      if (f?.url) URL.revokeObjectURL(f.url);
      return p.filter((x) => x.id !== id);
    }),
  };
}

/** Pasos animados mientras se procesa. */
export function useSteps(active: boolean, n: number, ms = 900) {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (!active) { setI(0); return; }
    const t = setInterval(() => setI((x) => Math.min(x + 1, n - 1)), ms);
    return () => clearInterval(t);
  }, [active, n, ms]);
  return i;
}

export function Steps({ steps, current }: { steps: string[]; current: number }) {
  return (
    <ol className="space-y-2" aria-live="polite">
      {steps.map((s, i) => {
        const done = i < current;
        const now = i === current;
        return (
          <li key={s} className={`flex items-center gap-3 text-[15px] transition ${done ? "text-ok" : now ? "text-ink" : "text-faint"}`}>
            <span className={`flex h-5 w-5 items-center justify-center rounded-full border text-[11px] ${done ? "border-ok bg-ok text-white" : now ? "border-ink" : "border-line"}`} aria-hidden="true">
              {done ? "✓" : now ? <span className="h-2 w-2 animate-pulse rounded-full bg-ink" /> : ""}
            </span>
            {s}
          </li>
        );
      })}
    </ol>
  );
}

export function Spinner() {
  return <span className="h-4 w-4 animate-spin rounded-full border-2 border-paper/40 border-t-paper" aria-hidden="true" />;
}

/* ---------- expedientes guardados (sessionStorage) ---------- */

export interface ExpedienteGuardado { id: string; titulo: string }
export function listarExpedientesGuardados(): ExpedienteGuardado[] {
  const out: ExpedienteGuardado[] = [];
  try {
    for (let i = 0; i < sessionStorage.length; i++) {
      const k = sessionStorage.key(i);
      if (!k || !k.startsWith("expediente:")) continue;
      try {
        const r = JSON.parse(sessionStorage.getItem(k) || "null");
        const p = r?.perfil;
        out.push({ id: k.slice(11), titulo: p ? `${p.marca} ${p.modelo} ${p.anio}` : k.slice(11) });
      } catch { /* entrada corrupta */ }
    }
  } catch { /* sin storage */ }
  return out;
}

/** Descarga un objeto como archivo JSON. */
export function descargarJSON(data: unknown, nombre: string) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nombre;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
