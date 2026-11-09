// Bitácora de parches del cotizador: filtros, detalle y aprobación/rechazo del actuario.
import { Fragment, useMemo, useState } from "react";
import { ConfirmDialog, EmptyState, ErrorState, PageHeader, SimBadge, Skeleton, useAsync, useToast } from "../components/ui";
import PatchDetail from "../components/rsi/PatchDetail";
import { VerdictBadge, cambioPerdida } from "../components/rsi/shared";
import { api, ApiError } from "../lib/api";
import { TIPO_PARCHE_LABEL } from "../lib/format";
import type { Patch } from "../lib/types";

const VEREDICTOS = [
  { v: "", label: "Todos" },
  { v: "pendiente", label: "Pendiente" },
  { v: "aceptado", label: "Aceptado" },
  { v: "rechazado", label: "Rechazado" },
  { v: "invalido", label: "Inválido" },
];
const NIVEL_LABEL: Record<string, string> = { parametros: "Parámetros", estructura: "Estructura", codigo: "Código" };
const PAGE = 30;

function DeltaPerdida({ p }: { p: Patch }) {
  const d = cambioPerdida(p);
  if (d == null) return <span className="text-faint">—</span>;
  return <span className={`num ${d < 0 ? "text-ok" : d > 0 ? "text-alta" : "text-muted"}`}>{d > 0 ? "+" : d < 0 ? "−" : ""}{Math.abs(d * 100).toFixed(1)}%</span>;
}

type Accion = { tipo: "aprobar" | "rechazar"; patch: Patch } | null;

export default function Parches() {
  const [veredicto, setVeredicto] = useState("");
  const [gen, setGen] = useState("");
  const generation = gen.trim() === "" ? undefined : Number(gen);
  const genValida = generation === undefined || (Number.isInteger(generation) && generation >= 0);
  const { data, error, loading, reload } = useAsync(
    () => api.parches({ veredicto: veredicto || undefined, generation: genValida ? generation : undefined }),
    [veredicto, genValida ? generation : "x"],
  );
  const [abiertos, setAbiertos] = useState<Set<string>>(new Set());
  const [visibles, setVisibles] = useState(PAGE);
  const [accion, setAccion] = useState<Accion>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const patches = useMemo(() => {
    const ps = [...(data?.patches ?? [])];
    // generación más reciente primero; dentro de la generación se respeta el orden de la API
    return ps.map((p, i) => ({ p, i })).sort((a, b) => b.p.generation - a.p.generation || a.i - b.i).map((x) => x.p);
  }, [data]);

  const toggle = (id: string) => setAbiertos((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  async function confirmar(razon: string) {
    if (!accion) return;
    setBusy(true);
    try {
      if (accion.tipo === "aprobar") {
        const r = await api.aprobarParche(accion.patch.patch_id, razon);
        toast.show(`Parche aprobado. Nueva versión del cotizador: ${r.version.id}`);
      } else {
        await api.rechazarParche(accion.patch.patch_id, razon);
        toast.show("Parche rechazado. Queda registrado en la bitácora.");
      }
      setAccion(null);
      reload();
    } catch (e) {
      const msg = e instanceof ApiError && (e.status === 409 || e.status === 422) ? e.message : e instanceof Error ? e.message : String(e);
      toast.show(msg, "alta");
      setAccion(null);
      if (e instanceof ApiError && e.status === 422) reload(); // la API marca el parche como inválido
    } finally {
      setBusy(false);
    }
  }

  const acciones = (p: Patch) =>
    p.veredicto == null ? (
      <div className="flex gap-2">
        <button type="button" className="btn-primary btn-sm" onClick={() => setAccion({ tipo: "aprobar", patch: p })}>Aprobar</button>
        <button type="button" className="btn-ghost btn-sm" onClick={() => setAccion({ tipo: "rechazar", patch: p })}>Rechazar</button>
      </div>
    ) : null;

  const lista = patches.slice(0, visibles);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Actuario · auto-mejora"
        title="Bitácora de parches"
        actions={<SimBadge />}
      >
        Cada parche es una propuesta del ciclo de auto-mejora: una hipótesis sobre un segmento, el cambio de configuración y
        lo que midió el evaluador congelado (acepta si mejora ≥1% en el holdout y ningún segmento empeora más de 5%).
      </PageHeader>

      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="label" htmlFor="f-veredicto">Veredicto</label>
          <select id="f-veredicto" className="input !w-auto min-w-[160px]" value={veredicto} onChange={(e) => { setVeredicto(e.target.value); setVisibles(PAGE); }}>
            {VEREDICTOS.map((o) => <option key={o.v} value={o.v}>{o.label}</option>)}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="f-gen">Generación</label>
          <input id="f-gen" type="number" min={0} inputMode="numeric" placeholder="Todas" className="input !w-28"
            value={gen} onChange={(e) => { setGen(e.target.value); setVisibles(PAGE); }} aria-invalid={!genValida} />
        </div>
        {(veredicto || gen) && (
          <button type="button" className="btn-ghost btn-sm" onClick={() => { setVeredicto(""); setGen(""); }}>Limpiar filtros</button>
        )}
        <div className="ml-auto flex items-center gap-2 text-[13px] text-muted">
          {data && (
            <>
              <span>{patches.length} parche{patches.length === 1 ? "" : "s"}</span>
              <span className="chip !py-0.5 !text-[12px]" title={data.fuente === "db" ? "Leídos de la base de datos" : "Leídos de patches.jsonl de la última corrida"}>
                fuente: <span className="font-mono">{data.fuente}</span>
              </span>
            </>
          )}
        </div>
      </div>
      {!genValida && <p className="text-[13px] text-alta">La generación debe ser un entero ≥ 0.</p>}

      {loading && !data ? (
        <div className="space-y-2">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-14" />)}</div>
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : !patches.length ? (
        veredicto === "pendiente" ? (
          <EmptyState title="No hay parches pendientes">
            Los parches de una corrida ya traen el veredicto del evaluador congelado, así que normalmente no quedan pendientes.
            Aprobar aquí aplica el parche al <strong>campeón de producción</strong> (el cotizador que usan las cotizaciones),
            que es distinto de las variantes del experimento del laboratorio.
          </EmptyState>
        ) : veredicto || gen ? (
          <EmptyState title="Sin parches con estos filtros" action={<button className="btn-ghost btn-sm" onClick={() => { setVeredicto(""); setGen(""); }}>Ver todos</button>} />
        ) : (
          <EmptyState title="Aún no hay parches">
            Ejecuta el ciclo RSI (desde el Laboratorio o con <code className="font-mono text-[13px]">bash scripts/demo.sh --start</code>) y vuelve a cargar.
          </EmptyState>
        )
      ) : (
        <>
          {/* Escritorio: tabla compacta con filas expandibles */}
          <div className={`card hidden overflow-hidden md:block ${loading ? "opacity-60" : ""}`}>
            <table className="w-full text-[14px]">
              <caption className="sr-only">Parches del cotizador</caption>
              <thead className="bg-cream text-left text-[12px] text-muted">
                <tr>
                  <th scope="col" className="px-4 py-2.5 font-medium">Parche</th>
                  <th scope="col" className="px-2 py-2.5 text-right font-medium">Gen.</th>
                  <th scope="col" className="px-2 py-2.5 font-medium">Tipo</th>
                  <th scope="col" className="px-2 py-2.5 font-medium">Nivel</th>
                  <th scope="col" className="px-2 py-2.5 font-medium">Veredicto</th>
                  <th scope="col" className="px-2 py-2.5 text-right font-medium">Δ pérdida</th>
                  <th scope="col" className="px-4 py-2.5 text-right font-medium"><span className="sr-only">Acciones</span></th>
                </tr>
              </thead>
              <tbody>
                {lista.map((p) => {
                  const open = abiertos.has(p.patch_id);
                  return (
                    <Fragment key={p.patch_id}>
                      <tr className="border-t border-line align-middle">
                        <td className="max-w-[300px] px-4 py-2.5">
                          <button type="button" onClick={() => toggle(p.patch_id)} aria-expanded={open}
                            className="flex w-full items-center gap-2 rounded text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-taupe">
                            <span className={`text-faint transition ${open ? "rotate-90" : ""}`} aria-hidden="true">›</span>
                            <span className="truncate font-mono text-[12px]" title={p.patch_id}>{p.patch_id}</span>
                          </button>
                        </td>
                        <td className="num px-2 py-2.5 text-right">{p.generation}</td>
                        <td className="px-2 py-2.5">{TIPO_PARCHE_LABEL[p.tipo] ?? p.tipo}</td>
                        <td className="px-2 py-2.5 text-muted">{NIVEL_LABEL[p.nivel] ?? p.nivel}</td>
                        <td className="px-2 py-2.5"><VerdictBadge patch={p} /></td>
                        <td className="px-2 py-2.5 text-right"><DeltaPerdida p={p} /></td>
                        <td className="px-4 py-2.5 text-right">{acciones(p)}</td>
                      </tr>
                      {open && (
                        <tr className="bg-paper">
                          <td colSpan={7} className="border-t border-line px-6 py-4"><PatchDetail patch={p} /></td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Móvil: tarjetas */}
          <ul className={`space-y-3 md:hidden ${loading ? "opacity-60" : ""}`}>
            {lista.map((p) => {
              const open = abiertos.has(p.patch_id);
              return (
                <li key={p.patch_id} className="card space-y-3 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="break-all font-mono text-[12px] text-muted">{p.patch_id}</div>
                      <div className="mt-1 text-[15px] font-medium">{TIPO_PARCHE_LABEL[p.tipo] ?? p.tipo}</div>
                      <div className="text-[13px] text-muted">Generación {p.generation} · {NIVEL_LABEL[p.nivel] ?? p.nivel}</div>
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-1">
                      <VerdictBadge patch={p} />
                      <span className="text-[12px]"><DeltaPerdida p={p} /></span>
                    </div>
                  </div>
                  {!open && <p className="line-clamp-2 text-[14px] text-muted">{p.hipotesis}</p>}
                  {open && <PatchDetail patch={p} />}
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <button type="button" className="text-[13px] text-muted underline decoration-line underline-offset-2" onClick={() => toggle(p.patch_id)} aria-expanded={open}>
                      {open ? "Ocultar detalle" : "Ver detalle"}
                    </button>
                    {acciones(p)}
                  </div>
                </li>
              );
            })}
          </ul>

          {visibles < patches.length && (
            <div className="flex justify-center">
              <button type="button" className="btn-ghost btn-sm" onClick={() => setVisibles((v) => v + PAGE)}>
                Mostrar más ({patches.length - visibles} restantes)
              </button>
            </div>
          )}
        </>
      )}

      <ConfirmDialog
        open={accion !== null}
        title={accion?.tipo === "aprobar" ? "Aprobar parche" : "Rechazar parche"}
        confirmLabel={accion?.tipo === "aprobar" ? "Aprobar y aplicar" : "Rechazar"}
        withReason
        busy={busy}
        onCancel={() => setAccion(null)}
        onConfirm={confirmar}
      >
        {accion?.tipo === "aprobar" ? (
          <>El parche <span className="font-mono text-[13px]">{accion.patch.patch_id}</span> se aplicará al cotizador de producción y se creará una nueva versión en el linaje.</>
        ) : (
          <>El parche <span className="font-mono text-[13px]">{accion?.patch.patch_id}</span> quedará marcado como rechazado.</>
        )}
      </ConfirmDialog>
      {toast.node}
    </div>
  );
}
