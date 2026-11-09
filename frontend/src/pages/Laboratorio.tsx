// Laboratorio RSI: curvas de regret y pérdida de las 3 variantes, resumen honesto del experimento y nuevas corridas.
import { useMemo } from "react";
import { EmptyState, ErrorState, PageHeader, SimBadge, Skeleton, Stat, useAsync, useToast } from "../components/ui";
import { LossChart, RegretChart, pivotCurva } from "../components/rsi/Charts";
import RunPanel from "../components/rsi/RunPanel";
import { tonoMejora, VARIANTE_TONO } from "../components/rsi/shared";
import { api, ApiError } from "../lib/api";
import { fmtMillones, fmtNum, fmtPct, fmtSignedPct, VARIANTE_LABEL } from "../lib/format";
import type { RunSummary } from "../lib/types";

const VARS = ["estatico", "parametros", "rsi"] as const;
const DOT_CLS = { alta: "bg-alta", taupe: "bg-taupe", ok: "bg-ok" } as const;

function fmtSeg(s: number) {
  if (!Number.isFinite(s)) return "—";
  const m = Math.floor(s / 60), r = Math.round(s % 60);
  return m ? `${m} min ${r} s` : `${r} s`;
}
const fmtConv = (v: number | null | undefined) => (v == null ? "no alcanzada" : `${fmtNum(v)} pólizas`);

function ResumenCorrida({ s }: { s: RunSummary }) {
  const base = s.regret.estatico;
  const ref = s.referencia_oraculo;
  const limitaciones = Array.isArray(s.limitaciones) ? (s.limitaciones as unknown[]).map(String) : [];
  return (
    <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
      <section className="card p-5" aria-labelledby="h-regret">
        <h2 id="h-regret" className="text-[17px] font-semibold">Regret total por variante</h2>
        <p className="mt-1 text-[13px] text-muted">Pérdida acumulada frente al precio ideal. Menos es mejor.</p>
        <ul className="mt-4 space-y-3">
          {VARS.map((v) => {
            const val = s.regret[v];
            const rel = base ? (val - base) / base : null;
            return (
              <li key={v} className="space-y-1">
                <div className="flex items-center justify-between gap-3 text-[14px]">
                  <span className="flex items-center gap-2"><span className={`h-2.5 w-2.5 rounded-full ${DOT_CLS[VARIANTE_TONO[v]]}`} aria-hidden="true" />{VARIANTE_LABEL[v]}</span>
                  <span className="num">
                    {fmtMillones(val)}
                    {v !== "estatico" && rel != null && <span className={`ml-2 text-[12px] ${rel < 0 ? "text-ok" : "text-alta"}`}>{fmtSignedPct(rel)}</span>}
                  </span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-cream">
                  <div className={`h-full rounded-full ${DOT_CLS[VARIANTE_TONO[v]]}`} style={{ width: `${base ? Math.min(100, (val / base) * 100) : 0}%` }} />
                </div>
              </li>
            );
          })}
        </ul>
        {ref && (
          <div className="mt-5 border-t border-line pt-4 text-[14px]">
            <div className="eyebrow mb-1">Referencia del oráculo</div>
            <p className="text-muted">
              Un oráculo que conoce el riesgo real desde la primera póliza logra <span className="num text-ink">{fmtPct(ref.mejora_maxima_posible)}</span> de
              mejora (regret <span className="num text-ink">{fmtMillones(ref.regret)}</span>): es la cota superior.
              {ref.fraccion_capturada_rsi != null && (
                <> La auto-mejora captura <span className="num text-ink">{fmtPct(ref.fraccion_capturada_rsi)}</span> de esa mejora posible.</>
              )}
            </p>
          </div>
        )}
      </section>

      <section className="card p-5" aria-labelledby="h-gate">
        <h2 id="h-gate" className="text-[17px] font-semibold">Resultado del experimento</h2>
        <dl className="mt-3 divide-y divide-line text-[14px]">
          <div className="flex justify-between gap-3 py-2">
            <dt className="text-muted">Mejora RSI vs reglas fijas</dt>
            <dd className={`num font-semibold ${s.mejora_rsi > 0 ? "text-ok" : s.mejora_rsi < 0 ? "text-alta" : "text-ink"}`}>{fmtSignedPct(s.mejora_rsi)}</dd>
          </div>
          <div className="flex items-start justify-between gap-3 py-2">
            <dt className="text-muted">Gate 2 · convergencia a ≤10% del oráculo</dt>
            <dd>
              {s.gate2
                ? <span className="rounded-md border border-ok/30 bg-ok/10 px-2 py-0.5 text-[12px] font-semibold text-ok">Cumple</span>
                : <span className="rounded-md border border-alta/30 bg-alta/10 px-2 py-0.5 text-[12px] font-semibold text-alta">No cumple</span>}
            </dd>
          </div>
          {VARS.filter((v) => v !== "estatico").map((v) => (
            <div key={v} className="flex justify-between gap-3 py-2">
              <dt className="text-muted">Convergencia · {VARIANTE_LABEL[v]}</dt>
              <dd className={`text-right ${s.convergencia_polizas?.[v] == null ? "text-faint" : "num"}`}>
                {fmtConv(s.convergencia_polizas?.[v])}
                {s.convergencia_meseta_polizas?.[v] != null && (
                  <div className="text-[12px] text-faint">meseta: {fmtNum(s.convergencia_meseta_polizas[v])} pólizas</div>
                )}
              </dd>
            </div>
          ))}
          <div className="flex justify-between gap-3 py-2"><dt className="text-muted">Semilla</dt><dd className="num">{s.seed}</dd></div>
          <div className="flex justify-between gap-3 py-2"><dt className="text-muted">Lotes × pólizas</dt><dd className="num">{fmtNum(s.batches)} × {fmtNum(s.batch_size)} · k={s.k}</dd></div>
          <div className="flex justify-between gap-3 py-2"><dt className="text-muted">Tiempo de cómputo</dt><dd className="num">{fmtSeg(s.elapsed_seconds)}</dd></div>
        </dl>
        {!s.gate2 && (
          <p className="mt-3 text-[13px] leading-relaxed text-muted">
            Lo decimos tal cual: la auto-mejora reduce el regret, pero
            {s.convergencia_polizas?.rsi == null
              ? " no llega a mantenerse dentro del 10% de la pérdida del oráculo hasta el final de la corrida,"
              : " no alcanza el criterio de convergencia,"} así que el Gate 2 no se cumple en esta corrida.
          </p>
        )}
        {limitaciones.length > 0 && (
          <details className="mt-3 text-[13px] text-muted">
            <summary className="cursor-pointer text-ink">Notas metodológicas</summary>
            <ul className="mt-2 list-disc space-y-1 pl-5">{limitaciones.map((l) => <li key={l}>{l}</li>)}</ul>
          </details>
        )}
      </section>
    </div>
  );
}

export default function Laboratorio() {
  const { data, error, loading, reload } = useAsync(() => api.ultimaCorrida(true), []);
  const toast = useToast();
  const filas = useMemo(() => pivotCurva(data?.curva ?? []), [data]);
  const sinCorrida = error instanceof ApiError && error.status === 404;
  const s = data?.summary;
  const ahorro = s ? s.regret.estatico - s.regret.rsi : null;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Auto-mejora recursiva"
        title="Laboratorio RSI"
        actions={<SimBadge />}
      >
        Tres versiones del cotizador cotizan las mismas pólizas simuladas: con reglas fijas, ajustando solo parámetros y con
        auto-mejora completa (parámetros, variables y reglas por segmento), siempre juzgadas por un evaluador congelado.
      </PageHeader>

      <RunPanel onDone={reload} onToast={toast.show} />

      {loading && !data ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-20" />)}</div>
          <Skeleton className="h-80" />
          <Skeleton className="h-72" />
        </div>
      ) : sinCorrida ? (
        <EmptyState title="Aún no hay corridas del experimento">
          Genera la corrida de demostración con <code className="font-mono text-[13px]">bash scripts/demo.sh --start</code> o lanza una
          con el botón “Correr nueva corrida”.
        </EmptyState>
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : data && s ? (
        <div className={`space-y-6 ${loading ? "opacity-60" : ""}`}>
          <div className="flex flex-wrap items-center gap-2 text-[13px] text-muted">
            <span>Corrida</span><span className="font-mono text-ink">{data.run_id}</span>
            <span aria-hidden="true">·</span><span>{fmtNum(data.n_parches)} parches evaluados</span>
          </div>

          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Regret reglas fijas" value={fmtMillones(s.regret.estatico)} sub="línea base" />
            <Stat label="Regret auto-mejora" value={fmtMillones(s.regret.rsi)} sub={`${fmtSignedPct(-s.mejora_rsi)} vs reglas fijas`} tone={tonoMejora(s.mejora_rsi)} />
            <Stat label="Regret ahorrado" value={fmtMillones(ahorro)} sub="MXN simulados" tone={tonoMejora(ahorro)} />
            <Stat label="Gate 2" value={s.gate2 ? "Cumple" : "No cumple"} sub="convergencia ≤10% del oráculo" tone={s.gate2 ? "ok" : "alta"} />
          </div>

          {filas.length ? (
            <>
              <section className="card p-4 sm:p-5" aria-labelledby="h-curva-regret">
                <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
                  <h2 id="h-curva-regret" className="text-[17px] font-semibold">Regret acumulado</h2>
                  <span className="text-[13px] text-muted">El área verde es el regret que la auto-mejora evita frente a las reglas fijas.</span>
                </div>
                <RegretChart filas={filas} />
              </section>
              <section className="card p-4 sm:p-5" aria-labelledby="h-curva-loss">
                <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
                  <h2 id="h-curva-loss" className="text-[17px] font-semibold">Pérdida media por lote <span className="text-[13px] font-normal text-muted">(MXN por póliza)</span></h2>
                  <span className="text-[13px] text-muted">Pérdida asimétrica en MXN por póliza: cobrar de menos cuesta 1.5×, de más 1×.</span>
                </div>
                <LossChart filas={filas} />
              </section>
            </>
          ) : (
            <EmptyState title="Esta corrida no trae curva">No se encontró <code className="font-mono">curve.csv</code> en la última corrida.</EmptyState>
          )}

          <ResumenCorrida s={s} />
        </div>
      ) : null}
      {toast.node}
    </div>
  );
}
