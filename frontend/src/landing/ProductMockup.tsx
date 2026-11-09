// Maqueta estática del producto dentro de un marco de navegador (no llama a la API).
import { Dot } from "../components/ui";
import { fmtMXN } from "../lib/format";

const NAV = ["Resumen", "Expedientes", "Siniestros", "Laboratorio RSI", "Parches", "Versiones"];

const KPIS = [
  { label: "Expedientes hoy", value: "24", sub: "~1.6 s cada uno" },
  { label: "Alertas altas", value: "3", sub: "VIN no coincide", tone: "text-alta" },
  { label: "Prima media", value: fmtMXN(9900), sub: "zona CDMX ×1.10" },
  { label: "Regret vs reglas fijas", value: "−28.4%", sub: "semilla 42", tone: "text-ok" },
];

type Tone = "ok" | "warn" | "alta";
const ACTIVIDAD: { tone: Tone; agente: string; accion: string; hora: string }[] = [
  { tone: "alta", agente: "Documental", accion: "Detectó un VIN que no coincide entre factura y tarjeta en EXP-002", hora: "09:42" },
  { tone: "ok", agente: "Visual", accion: `Estimó ${fmtMXN(2800)} de reacondicionamiento (espejo y rayón en puerta)`, hora: "09:42" },
  { tone: "ok", agente: "Valuación", accion: `Valuó el Jetta 2017 en ${fmtMXN(126722)} con 8 comparables`, hora: "09:43" },
  { tone: "ok", agente: "Cotizador", accion: `Prima de ${fmtMXN(9900)}: base ${fmtMXN(9000)} × factor zona CDMX 1.10`, hora: "09:43" },
  { tone: "ok", agente: "RSI", accion: "El evaluador congelado aceptó un parche que bajó la pérdida en el holdout", hora: "08:15" },
  { tone: "warn", agente: "RSI", accion: "Evaluando un nuevo parche por segmento — esperando veredicto", hora: "En proceso" },
];

export default function ProductMockup() {
  return (
    <figure className="relative mx-auto w-full max-w-[1000px]" aria-label="Maqueta de la app de AutoGuard AI con datos simulados">
      <div className="overflow-hidden rounded-[18px] border border-line bg-panel shadow-frame">
        {/* barra del navegador */}
        <div className="flex items-center gap-3 border-b border-line bg-cream px-3 py-2.5 sm:px-4">
          <div className="flex gap-1.5" aria-hidden="true">
            <span className="h-2.5 w-2.5 rounded-full bg-line" />
            <span className="h-2.5 w-2.5 rounded-full bg-line" />
            <span className="h-2.5 w-2.5 rounded-full bg-line" />
          </div>
          <div className="min-w-0 flex-1 truncate rounded-md border border-line bg-panel px-3 py-1 text-center text-[12px] text-muted">
            localhost:5173/app
          </div>
        </div>

        <div className="flex gap-4 p-3 sm:p-5">
          {/* barra lateral */}
          <nav className="hidden w-40 shrink-0 flex-col gap-1 md:flex" aria-hidden="true">
            {NAV.map((n, i) => (
              <span
                key={n}
                className={`rounded-lg px-3 py-2 text-center text-[13px] ${i === 0 ? "bg-cream font-medium text-ink" : "text-muted"}`}
              >
                {n}
              </span>
            ))}
          </nav>

          <div className="min-w-0 flex-1 space-y-3">
            <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-4 sm:gap-3">
              {KPIS.map((k) => (
                <div key={k.label} className="card-cream px-3 py-3 text-center">
                  <div className="truncate text-[12px] text-muted">{k.label}</div>
                  <div className={`num mt-1 text-[17px] font-semibold sm:text-[19px] ${k.tone ?? "text-ink"}`}>{k.value}</div>
                  <div className="mt-0.5 truncate text-[11px] text-faint">{k.sub}</div>
                </div>
              ))}
            </div>

            <div className="card-cream px-3 py-3 sm:px-4">
              <div className="mb-2 text-center text-[11px] uppercase tracking-[0.12em] text-faint">
                Actividad de agentes — hoy
              </div>
              <ul className="divide-y divide-line/70">
                {ACTIVIDAD.map((a, i) => (
                  <li
                    key={i}
                    className={`${i >= 3 && i < ACTIVIDAD.length - 1 ? "hidden sm:grid" : "grid"} grid-cols-[auto_1fr_auto] items-start gap-x-3 py-2 text-[13px] sm:grid-cols-[auto_7.5rem_1fr_auto] sm:items-center`}
                  >
                    <span className="pt-1.5 sm:pt-0"><Dot tone={a.tone} /></span>
                    <span className="font-medium text-ink">{a.agente}</span>
                    <span className="col-start-2 row-start-2 text-muted sm:col-start-auto sm:row-start-auto">{a.accion}</span>
                    <span className={`col-start-3 row-start-1 whitespace-nowrap text-right text-[12px] sm:col-start-auto sm:row-start-auto ${a.hora === "En proceso" ? "text-warn" : "num text-faint"}`}>
                      {a.hora}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </div>
      <figcaption className="mt-3 flex justify-center">
        <span className="chip !py-0.5 !text-[12px]"><span className="h-1.5 w-1.5 rounded-full bg-warn" />Datos simulados · maqueta</span>
      </figcaption>
    </figure>
  );
}
