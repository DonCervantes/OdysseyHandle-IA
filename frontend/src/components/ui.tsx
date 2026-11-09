// Componentes base compartidos. Úsalos en todas las páginas para mantener una sola identidad visual.
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import type { Severidad } from "../lib/types";

export function Logo({ className = "" }: { className?: string }) {
  return (
    <Link to="/" className={`inline-flex items-center gap-2 text-[17px] font-semibold tracking-tight text-ink ${className}`} aria-label="AutoGuard AI, inicio">
      <svg viewBox="0 0 32 32" className="h-6 w-6" aria-hidden="true">
        <rect width="32" height="32" rx="8" fill="rgb(var(--ink))" />
        <path d="M16 6.5 9 9.3v5.2c0 4.4 3 7.7 7 9 4-1.3 7-4.6 7-9V9.3l-7-2.8Z" fill="rgb(var(--sand))" />
        <path d="m12.6 15.6 2.4 2.4 4.4-4.8" fill="none" stroke="rgb(var(--ink))" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      autoguard
    </Link>
  );
}

export function SimBadge() {
  return <span className="chip !py-0.5 !text-[12px]"><span className="h-1.5 w-1.5 rounded-full bg-warn" />Datos simulados</span>;
}

const SEV: Record<Severidad, { cls: string; label: string }> = {
  alta: { cls: "border-alta/30 bg-alta/10 text-alta", label: "Alta" },
  media: { cls: "border-warn/30 bg-warn/10 text-warn", label: "Media" },
  info: { cls: "border-info/30 bg-info/10 text-info", label: "Info" },
};
export function SeverityBadge({ s }: { s: Severidad }) {
  const v = SEV[s] ?? SEV.info;
  return <span className={`inline-flex items-center rounded-md border px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wider ${v.cls}`}>{v.label}</span>;
}

export function Dot({ tone = "ok" }: { tone?: "ok" | "warn" | "alta" | "info" }) {
  const c = { ok: "bg-ok", warn: "bg-warn", alta: "bg-alta", info: "bg-info" }[tone];
  return <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${c}`} aria-hidden="true" />;
}

export function PageHeader({ eyebrow, title, children, actions }: { eyebrow?: string; title: string; children?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 border-b border-line pb-6">
      <div className="min-w-0 max-w-3xl space-y-2">
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1 className="text-[28px] font-semibold leading-tight tracking-tight md:text-[34px]">{title}</h1>
        {children && <div className="text-[15px] leading-relaxed text-muted">{children}</div>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Stat({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: "ok" | "alta" | "warn" }) {
  const toneCls = tone === "ok" ? "text-ok" : tone === "alta" ? "text-alta" : tone === "warn" ? "text-warn" : "text-faint";
  return (
    <div className="card-cream px-4 py-3.5 text-center">
      <div className="text-[13px] text-muted">{label}</div>
      <div className="num mt-1 text-[22px] font-semibold text-ink">{value}</div>
      {sub && <div className={`mt-0.5 text-[12px] ${toneCls}`}>{sub}</div>}
    </div>
  );
}

export function Skeleton({ className = "h-24" }: { className?: string }) {
  return <div className={`animate-pulse rounded-xl2 bg-cream ${className}`} />;
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <div className="card flex flex-wrap items-center justify-between gap-3 border-alta/30 bg-alta/5 px-5 py-4" role="alert">
      <div className="min-w-0 text-[15px] text-alta">{msg}</div>
      {onRetry && <button className="btn-ghost btn-sm" onClick={onRetry}>Reintentar</button>}
    </div>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="card-cream flex flex-col items-center gap-2 px-6 py-10 text-center">
      <div className="text-[17px] font-semibold">{title}</div>
      {children && <div className="max-w-md text-[15px] text-muted">{children}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

/** Carga asíncrona con estados loading / error / data y recarga. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const alive = useRef(true);
  const run = useCallback(() => {
    setLoading(true);
    setError(null);
    fn().then(
      (d) => { if (alive.current) { setData(d); setLoading(false); } },
      (e) => { if (alive.current) { setError(e); setLoading(false); } },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => {
    alive.current = true;
    run();
    return () => { alive.current = false; };
  }, [run]);
  return { data, error, loading, reload: run, setData };
}

/** Mensaje flotante breve (toast). */
export function useToast() {
  const [toast, setToast] = useState<{ msg: string; tone: "ok" | "alta" } | null>(null);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4200);
    return () => clearTimeout(t);
  }, [toast]);
  const node = toast ? (
    <div role="status" className={`fixed bottom-6 right-6 z-50 max-w-sm rounded-xl px-4 py-3 text-[15px] shadow-soft ${toast.tone === "ok" ? "bg-ink text-paper" : "bg-alta text-white"}`}>
      {toast.msg}
    </div>
  ) : null;
  return { show: (msg: string, tone: "ok" | "alta" = "ok") => setToast({ msg, tone }), node };
}

/** Diálogo de confirmación con razón opcional (sin window.confirm). */
export function ConfirmDialog({
  open, title, children, confirmLabel, withReason, onConfirm, onCancel, busy,
}: {
  open: boolean; title: string; children?: ReactNode; confirmLabel: string; withReason?: boolean;
  onConfirm: (razon: string) => void; onCancel: () => void; busy?: boolean;
}) {
  const [razon, setRazon] = useState("");
  useEffect(() => { if (open) setRazon(""); }, [open]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-ink/30 p-4" role="dialog" aria-modal="true" aria-label={title}>
      <div className="card w-full max-w-md space-y-4 p-6 shadow-frame">
        <h2 className="text-[19px] font-semibold">{title}</h2>
        {children && <div className="text-[15px] text-muted">{children}</div>}
        {withReason && (
          <div>
            <label className="label" htmlFor="razon">Razón (opcional)</label>
            <textarea id="razon" className="input min-h-[84px]" value={razon} onChange={(e) => setRazon(e.target.value)} />
          </div>
        )}
        <div className="flex justify-end gap-2">
          <button className="btn-ghost btn-sm" onClick={onCancel} disabled={busy}>Cancelar</button>
          <button className="btn-primary btn-sm" onClick={() => onConfirm(razon)} disabled={busy}>{busy ? "Enviando…" : confirmLabel}</button>
        </div>
      </div>
    </div>
  );
}

/** Fuente citada (para cifras públicas). */
export function Source({ href, children }: { href: string; children: ReactNode }) {
  return <a href={href} target="_blank" rel="noreferrer" className="text-[12px] text-faint underline decoration-line underline-offset-2 hover:text-muted">{children}</a>;
}
