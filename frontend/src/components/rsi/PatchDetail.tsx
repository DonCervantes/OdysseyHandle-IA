// Detalle de un parche: hipótesis, segmento, diff colapsable, métricas antes/después y razón.
import { useState } from "react";
import type { Patch } from "../../lib/types";
import { esProporcion, fmtMetrica, fmtSegmento, labelMetrica } from "./shared";

export function SegmentChips({ segmento }: { segmento: Record<string, unknown> }) {
  const chips = fmtSegmento(segmento);
  if (!chips.length) return <span className="text-[13px] text-faint">Sin segmento (toda la cartera)</span>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {chips.map((c) => <span key={c} className="chip !px-2 !py-0.5 font-mono !text-[12px]">{c}</span>)}
    </div>
  );
}

export function MetricsTable({ patch }: { patch: Patch }) {
  const before = patch.metrics_before ?? {};
  const after = patch.metrics_after ?? {};
  const keys = Array.from(new Set([...Object.keys(before), ...Object.keys(after)]));
  if (!keys.length) return <p className="text-[13px] text-faint">Sin métricas registradas.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[320px] text-[13px]">
        <caption className="sr-only">Métricas antes y después del parche {patch.patch_id}</caption>
        <thead>
          <tr className="text-left text-faint">
            <th scope="col" className="py-1 pr-3 font-medium">Métrica</th>
            <th scope="col" className="py-1 pr-3 text-right font-medium">Antes</th>
            <th scope="col" className="py-1 pr-3 text-right font-medium">Después</th>
            <th scope="col" className="py-1 text-right font-medium">Diferencia</th>
          </tr>
        </thead>
        <tbody className="num">
          {keys.map((k) => {
            const a = before[k], b = after[k];
            const both = a != null && b != null;
            const d = both ? b - a : null;
            const isLoss = /loss|perdida|regret/.test(k);
            const tone = d == null || d === 0 || !isLoss ? "text-muted" : d < 0 ? "text-ok" : "text-alta";
            const rel = both && a ? d! / a : null;
            return (
              <tr key={k} className="border-t border-line">
                <th scope="row" className="py-1.5 pr-3 text-left font-sans font-normal text-muted">{labelMetrica(k)}</th>
                <td className="py-1.5 pr-3 text-right">{fmtMetrica(k, a)}</td>
                <td className="py-1.5 pr-3 text-right">{fmtMetrica(k, b)}</td>
                <td className={`py-1.5 text-right ${tone}`}>
                  {d == null ? "—" : esProporcion(k) ? fmtMetrica(k, d) : (
                    <>
                      {d > 0 ? "+" : d < 0 ? "−" : ""}{Math.abs(d).toLocaleString("es-MX", { maximumFractionDigits: 0 })}
                      {rel != null && <span className="ml-1 text-[11px]">({rel > 0 ? "+" : "−"}{Math.abs(rel * 100).toFixed(1)}%)</span>}
                    </>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function DiffBlock({ diff }: { diff: string }) {
  const [open, setOpen] = useState(false);
  if (!diff) return <p className="text-[13px] text-faint">Sin diff.</p>;
  const lines = diff.split(/;\s*|\n/).filter(Boolean);
  const long = lines.length > 3;
  const shown = open || !long ? lines : lines.slice(0, 3);
  return (
    <div>
      <pre className="whitespace-pre-wrap break-words rounded-lg border border-line bg-cream px-3 py-2 font-mono text-[12px] leading-relaxed text-ink">
        {shown.join("\n")}
        {!open && long && "\n…"}
      </pre>
      {long && (
        <button type="button" className="mt-1 text-[12px] text-muted underline decoration-line underline-offset-2 hover:text-ink" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
          {open ? "Ver menos" : `Ver diff completo (${lines.length} cambios)`}
        </button>
      )}
    </div>
  );
}

export default function PatchDetail({ patch }: { patch: Patch }) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div className="space-y-3">
        <div>
          <div className="eyebrow mb-1">Hipótesis</div>
          <p className="text-[14px] leading-relaxed text-ink">{patch.hipotesis || "—"}</p>
        </div>
        <div>
          <div className="eyebrow mb-1">Segmento</div>
          <SegmentChips segmento={patch.segmento} />
        </div>
        <div>
          <div className="eyebrow mb-1">Diff de configuración</div>
          <DiffBlock diff={patch.diff} />
        </div>
      </div>
      <div className="space-y-3">
        <div>
          <div className="eyebrow mb-1">Métricas antes / después · {patch.metrica_objetivo ? labelMetrica(patch.metrica_objetivo) : "objetivo"}</div>
          <MetricsTable patch={patch} />
        </div>
        {patch.razon && (
          <div>
            <div className="eyebrow mb-1">Razón del veredicto</div>
            <p className="text-[14px] text-muted">{patch.razon}</p>
          </div>
        )}
      </div>
    </div>
  );
}
