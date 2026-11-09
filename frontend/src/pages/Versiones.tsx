// Linaje del cotizador: línea de tiempo de versiones con reversión.
import { useState } from "react";
import { ConfirmDialog, EmptyState, ErrorState, PageHeader, SimBadge, Skeleton, useAsync, useToast } from "../components/ui";
import { EstadoBadge, fmtMetrica, labelMetrica } from "../components/rsi/shared";
import { api } from "../lib/api";
import { fmtFecha, shortSha } from "../lib/format";
import type { AgentVersion } from "../lib/types";

export default function Versiones() {
  const { data, error, loading, reload } = useAsync(() => api.versiones(), []);
  const [objetivo, setObjetivo] = useState<AgentVersion | null>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const versiones = data?.versions ?? [];

  async function revertir() {
    if (!objetivo) return;
    setBusy(true);
    try {
      const r = await api.revertir(objetivo.git_sha);
      toast.show(`Reversión registrada. Versión en producción: ${r.version.id}`);
      setObjetivo(null);
      reload();
    } catch (e) {
      toast.show(e instanceof Error ? e.message : String(e), "alta");
      setObjetivo(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Linaje del cotizador" title="Versiones" actions={<SimBadge />}>
        Cada parche aprobado o reversión crea una versión nueva con su commit de configuración. La primera de la lista es la
        que cotiza hoy. Revertir no borra historia: agrega una versión más al linaje.
      </PageHeader>

      {loading && !data ? (
        <div className="space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-28" />)}</div>
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : !versiones.length ? (
        <EmptyState title="Sin versiones registradas">
          El linaje se crea al iniciar la API. Levántala con <code className="font-mono text-[13px]">bash scripts/demo.sh --start</code> y recarga.
        </EmptyState>
      ) : (
        <ol className={`relative space-y-4 ${loading ? "opacity-60" : ""}`} aria-label="Versiones del cotizador, de la más reciente a la más antigua">
          <span className="absolute bottom-4 left-[11px] top-4 w-px bg-line" aria-hidden="true" />
          {versiones.map((v, i) => {
            const actual = i === 0 || v.estado === "campeon";
            const metricas = Object.entries(v.metrics ?? {});
            return (
              <li key={v.id + v.created_at} className="relative pl-9">
                <span
                  className={`absolute left-[5px] top-5 h-[13px] w-[13px] rounded-full border-2 ${actual ? "border-ok bg-ok" : "border-sand bg-paper"}`}
                  aria-hidden="true"
                />
                <div className={`p-4 sm:p-5 ${actual ? "card shadow-soft" : "card-cream"}`}>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="break-all font-mono text-[15px] font-semibold">{v.id}</span>
                        <EstadoBadge estado={v.estado} />
                        {i === 0 && v.estado !== "campeon" && <span className="chip !py-0.5 !text-[12px]">Más reciente</span>}
                      </div>
                      <dl className="flex flex-wrap gap-x-5 gap-y-1 text-[13px] text-muted">
                        <div className="flex gap-1"><dt>Commit</dt><dd className="font-mono text-ink" title={v.git_sha}>{shortSha(v.git_sha)}</dd></div>
                        <div className="flex gap-1"><dt>Padre</dt><dd className="font-mono text-ink">{v.parent_id ?? "— (versión base)"}</dd></div>
                        <div className="flex gap-1"><dt>Fecha</dt><dd className="text-ink">{fmtFecha(v.created_at)}</dd></div>
                      </dl>
                    </div>
                    {v.estado !== "campeon" && (
                      <button type="button" className="btn-ghost btn-sm" onClick={() => setObjetivo(v)} aria-label={`Revertir a la versión ${v.id}`}>Revertir a esta versión</button>
                    )}
                  </div>
                  {metricas.length > 0 ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {metricas.map(([k, val]) => (
                        <span key={k} className="chip !py-0.5 !text-[12px]">
                          {labelMetrica(k)}: <span className="num text-ink">{typeof val === "number" ? fmtMetrica(k, val) : String(val)}</span>
                        </span>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-3 text-[13px] text-faint">Sin métricas registradas para esta versión.</p>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}

      <ConfirmDialog
        open={objetivo !== null}
        title={`Revertir a ${objetivo?.id ?? ""}`}
        confirmLabel="Revertir"
        busy={busy}
        onCancel={() => setObjetivo(null)}
        onConfirm={revertir}
      >
        Las nuevas cotizaciones usarán esta configuración. La reversión queda registrada en el linaje.
      </ConfirmDialog>
      {toast.node}
    </div>
  );
}
