// Gráficas del laboratorio RSI (recharts): regret acumulado y pérdida media por lote.
import { useMemo } from "react";
import {
  Area, CartesianGrid, ComposedChart, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import type { CurvePoint } from "../../lib/types";
import { fmtMillones, fmtNum, VARIANTE_LABEL } from "../../lib/format";
import { useChartColors, VARIANTE_TONO } from "./shared";

const VARIANTES = ["estatico", "parametros", "rsi"] as const;
type V = (typeof VARIANTES)[number];

export interface FilaCurva {
  batch: number; polizas: number;
  estatico?: number; parametros?: number; rsi?: number;
  ahorro?: [number, number];
  loss_estatico?: number; loss_parametros?: number; loss_rsi?: number; loss_oraculo?: number;
}

/** Pivota la curva larga (una fila por variante y lote) a una fila por lote. */
export function pivotCurva(curva: CurvePoint[]): FilaCurva[] {
  const m = new Map<number, FilaCurva>();
  for (const c of curva) {
    const f = m.get(c.batch) ?? { batch: c.batch, polizas: c.polizas };
    if ((VARIANTES as readonly string[]).includes(c.variant)) {
      f[c.variant as V] = c.regret;
      f[`loss_${c.variant}` as `loss_${V}`] = c.loss;
    }
    if (c.loss_oraculo != null && f.loss_oraculo == null) f.loss_oraculo = c.loss_oraculo;
    f.polizas = Math.max(f.polizas, c.polizas);
    m.set(c.batch, f);
  }
  const filas = [...m.values()].sort((a, b) => a.batch - b.batch);
  for (const f of filas) if (f.estatico != null && f.rsi != null) f.ahorro = [f.rsi, f.estatico];
  return filas;
}

const axisTick = { fontSize: 12 };
/** Marcas del eje X cada 3,000 pólizas, desde 0 hasta el máximo de la curva. */
const PASO_X = 3000;
function ticksX(filas: FilaCurva[]): number[] {
  const max = filas.reduce((m, f) => Math.max(m, f.polizas), 0);
  const out: number[] = [];
  for (let t = 0; t <= max; t += PASO_X) out.push(t);
  return out;
}
const fmtK = (v: number) => (Math.abs(v) >= 1000 ? `${(v / 1000).toLocaleString("es-MX", { maximumFractionDigits: 1 })}k` : String(v));

function TooltipBox({ active, payload, label, kind }: {
  active?: boolean; label?: number; kind: "regret" | "loss";
  payload?: { dataKey?: unknown; name?: string; value?: unknown; color?: string; payload?: FilaCurva }[];
}) {
  if (!active || !payload?.length) return null;
  const fila = payload[0]?.payload;
  const items = payload.filter((p) => typeof p.value === "number");
  return (
    <div className="rounded-lg border border-line bg-panel px-3 py-2 text-[12px] shadow-soft">
      <div className="mb-1 font-medium text-ink">Lote {fila?.batch} · {fmtNum(label)} pólizas</div>
      {kind === "loss" && <div className="mb-1 text-faint">Pérdida media · MXN por póliza</div>}
      {items.map((p) => (
        <div key={String(p.dataKey)} className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-1.5 text-muted"><span className="h-2 w-2 rounded-full" style={{ background: p.color }} />{p.name}</span>
          <span className="num text-ink">{kind === "regret" ? fmtMillones(p.value as number) : `${fmtNum(Math.round(p.value as number))} MXN`}</span>
        </div>
      ))}
      {kind === "regret" && fila?.ahorro && (
        <div className="mt-1 flex justify-between gap-4 border-t border-line pt-1 text-ok">
          <span>Regret ahorrado</span><span className="num">{fmtMillones(fila.ahorro[1] - fila.ahorro[0])}</span>
        </div>
      )}
    </div>
  );
}

function ChartLegend({ items }: { items: { label: string; color: string; kind: "line" | "dash" | "area" }[] }) {
  return (
    <ul className="mt-2 flex flex-wrap justify-center gap-x-4 gap-y-1 text-[13px] text-muted">
      {items.map((i) => (
        <li key={i.label} className="flex items-center gap-1.5">
          {i.kind === "area"
            ? <span className="h-3 w-3 rounded-sm" style={{ background: i.color }} aria-hidden="true" />
            : <span className="w-4 border-t-2" style={{ borderColor: i.color, borderTopStyle: i.kind === "dash" ? "dashed" : "solid" }} aria-hidden="true" />}
          {i.label}
        </li>
      ))}
    </ul>
  );
}

export function RegretChart({ filas }: { filas: FilaCurva[] }) {
  const c = useChartColors();
  return (
    <>
    <ResponsiveContainer width="100%" height={320}>
      <ComposedChart data={filas} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
        <CartesianGrid stroke={c.line} strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="polizas" type="number" domain={[0, "dataMax"]} ticks={ticksX(filas)} tickFormatter={fmtK} tick={{ ...axisTick, fill: c.muted }} stroke={c.line}
          label={{ value: "Pólizas cotizadas", position: "insideBottom", offset: -2, fill: c.faint, fontSize: 12 }} height={38} />
        <YAxis tickFormatter={(v: number) => fmtMillones(v, 0)} tick={{ ...axisTick, fill: c.muted }} stroke={c.line} width={44} />
        <Tooltip content={<TooltipBox kind="regret" />} />
        <Area dataKey="ahorro" name="Regret ahorrado" stroke="none" fill={c.alpha("ok", 0.14)} isAnimationActive={false} legendType="square" />
        {VARIANTES.map((v) => (
          <Line key={v} dataKey={v} name={VARIANTE_LABEL[v]} type="monotone" dot={false} isAnimationActive={false}
            stroke={c[VARIANTE_TONO[v]]} strokeWidth={v === "rsi" ? 2.5 : 1.8} />
        ))}
      </ComposedChart>
    </ResponsiveContainer>
    <ChartLegend items={[
      ...VARIANTES.map((v) => ({ label: VARIANTE_LABEL[v], color: c[VARIANTE_TONO[v]], kind: "line" as const })),
      { label: "Regret ahorrado (RSI vs reglas fijas)", color: c.alpha("ok", 0.25), kind: "area" as const },
    ]} />
    </>
  );
}

export function LossChart({ filas }: { filas: FilaCurva[] }) {
  const c = useChartColors();
  const hayOraculo = useMemo(() => filas.some((f) => f.loss_oraculo != null), [filas]);
  return (
    <>
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={filas} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
        <CartesianGrid stroke={c.line} strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="polizas" type="number" domain={[0, "dataMax"]} ticks={ticksX(filas)} tickFormatter={fmtK} tick={{ ...axisTick, fill: c.muted }} stroke={c.line}
          label={{ value: "Pólizas cotizadas", position: "insideBottom", offset: -2, fill: c.faint, fontSize: 12 }} height={38} />
        <YAxis tickFormatter={fmtK} tick={{ ...axisTick, fill: c.muted }} stroke={c.line} width={44} domain={["auto", "auto"]} />
        <Tooltip content={<TooltipBox kind="loss" />} />
        {VARIANTES.map((v) => (
          <Line key={v} dataKey={`loss_${v}`} name={VARIANTE_LABEL[v]} type="monotone" dot={false} isAnimationActive={false}
            stroke={c[VARIANTE_TONO[v]]} strokeWidth={v === "rsi" ? 2.2 : 1.5} strokeOpacity={0.9} />
        ))}
        {hayOraculo && (
          <Line dataKey="loss_oraculo" name="Oráculo (referencia)" type="monotone" dot={false} isAnimationActive={false}
            stroke={c.info} strokeWidth={1.5} strokeDasharray="5 4" />
        )}
      </LineChart>
    </ResponsiveContainer>
    <ChartLegend items={[
      ...VARIANTES.map((v) => ({ label: VARIANTE_LABEL[v], color: c[VARIANTE_TONO[v]], kind: "line" as const })),
      ...(hayOraculo ? [{ label: "Oráculo (referencia)", color: c.info, kind: "dash" as const }] : []),
    ]} />
    </>
  );
}
