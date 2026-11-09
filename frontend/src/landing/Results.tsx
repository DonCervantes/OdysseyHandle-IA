// Resultados medidos: regret de las 3 variantes por semilla (números reales, datos simulados).
import { fmtMillones, fmtSignedPct, VARIANTE_LABEL } from "../lib/format";
import { CORRIDAS, delta, RANGO_PARAM, RANGO_RSI } from "./data";

const VARIANTES = [
  { key: "estatico", bar: "bg-line" },
  { key: "parametros", bar: "bg-sand" },
  { key: "rsi", bar: "bg-taupe" },
] as const;

const MAX = Math.max(...CORRIDAS.map((c) => c.estatico));
const prom = (k: "estatico" | "parametros" | "rsi") => CORRIDAS.reduce((s, c) => s + c[k], 0) / CORRIDAS.length;
// Cuántas veces la mejora promedio del RSI supera la de ajustar solo parámetros (≈1.75 con las 4 semillas).
const VECES = (delta(prom("rsi"), prom("estatico")) / delta(prom("parametros"), prom("estatico"))).toFixed(1);

export default function Results() {
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.25fr_1fr]">
      {/* barras promedio */}
      <div className="card min-w-0 p-5 sm:p-7">
        <div className="eyebrow">Pérdida acumulada promedio · 4 semillas</div>
        <p className="mt-1 text-[14px] text-muted">60 lotes × 200 pólizas simuladas. Menos es mejor.</p>
        <div className="mt-6 space-y-5">
          {VARIANTES.map((v) => {
            const p = prom(v.key);
            const d = delta(p, prom("estatico"));
            return (
              <div key={v.key}>
                <div className="mb-1.5 flex items-baseline justify-between gap-3 text-[14px]">
                  <span className="font-medium">{VARIANTE_LABEL[v.key]}</span>
                  <span className="num text-muted">
                    {fmtMillones(p)} {v.key !== "estatico" && <span className={v.key === "rsi" ? "text-ok" : ""}>({fmtSignedPct(d)})</span>}
                  </span>
                </div>
                <div className="h-3 overflow-hidden rounded-full bg-cream" aria-hidden="true">
                  <div className={`h-full rounded-full ${v.bar}`} style={{ width: `${(p / MAX) * 100}%` }} />
                </div>
              </div>
            );
          })}
        </div>

        <div className="mt-7 overflow-x-auto">
          <table className="w-full min-w-[280px] text-[13px]">
            <caption className="sr-only">Regret por semilla y variante, en millones de pesos simulados</caption>
            <thead>
              <tr className="border-b border-line text-left text-faint">
                <th scope="col" className="py-2 font-normal">Semilla</th>
                <th scope="col" className="py-2 text-right font-normal">Reglas fijas</th>
                <th scope="col" className="py-2 text-right font-normal">Solo parámetros</th>
                <th scope="col" className="py-2 text-right font-normal">Auto-mejora</th>
              </tr>
            </thead>
            <tbody className="num">
              {CORRIDAS.map((c) => (
                <tr key={c.seed} className="border-b border-line/60 last:border-0">
                  <td className="py-2">{c.seed}</td>
                  <td className="py-2 text-right">{fmtMillones(c.estatico)}</td>
                  <td className="py-2 text-right">
                    {fmtMillones(c.parametros)} <span className="hidden text-faint sm:inline">{fmtSignedPct(delta(c.parametros, c.estatico))}</span>
                  </td>
                  <td className="py-2 text-right">
                    {fmtMillones(c.rsi)} <span className="hidden text-ok sm:inline">{fmtSignedPct(delta(c.rsi, c.estatico))}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* bloque honesto */}
      <div className="flex min-w-0 flex-col gap-4">
        <div className="card-cream p-5 sm:p-7">
          <div className="eyebrow">Lo que logramos</div>
          <div className="num mt-3 text-[34px] font-semibold leading-none tracking-tight sm:text-[48px]">
            {fmtSignedPct(RANGO_RSI.peor)} <span className="text-faint">a</span> {fmtSignedPct(RANGO_RSI.mejor)}
          </div>
          <p className="mt-3 text-[15px] leading-relaxed text-muted">
            de pérdida frente a reglas fijas con el ciclo de auto-mejora completo. Ajustar solo parámetros se queda en{" "}
            {fmtSignedPct(RANGO_PARAM.peor)} a {fmtSignedPct(RANGO_PARAM.mejor)}: en promedio, el ciclo completo logra ~{VECES}× la mejora de ajustar solo parámetros.
          </p>
        </div>
        <div className="card p-5 sm:p-7">
          <div className="eyebrow">Lo que no logramos</div>
          <p className="mt-3 text-[15px] leading-relaxed text-muted">
            Nuestra meta interna era <strong className="font-semibold text-ink">−40%</strong> y no la alcanzamos. Para ponerlo en contexto: un
            oráculo con conocimiento perfecto llega a ~44% y un aprendiz ideal que ya conoce la estructura, a 39–41%. El margen que falta es real
            y lo decimos tal cual.
          </p>
        </div>
      </div>
    </div>
  );
}
