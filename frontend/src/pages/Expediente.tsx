// Expediente: alertas, prima explicada, daños, valuación, perfil y documentos de un vehículo.
import { Link, useLocation, useParams } from "react-router-dom";
import { EmptyState, ErrorState, PageHeader, SeverityBadge, SimBadge, Skeleton, Stat, useAsync } from "../components/ui";
import { ApiError, api, leerExpediente } from "../lib/api";
import type {
  Alerta, DocExtraction, ExpedienteResponse, Prediction, Severidad, Valuacion, VehicleProfile,
} from "../lib/types";
import { USO_LABEL, fmtFecha, fmtMXN, fmtMult, fmtNum, fmtPct, labelAlerta, labelFactor } from "../lib/format";
import {
  Collapsible, DanosList, FactorBar, IntervalBar, Note, ProgressBar, Section, TIPO_DOC_LABEL, descargarJSON,
} from "../components/expediente/bits";

/** Vista unificada: la respuesta de POST /expedientes o lo disponible en GET /vehicles/{id}. */
interface Vista {
  vehicle_id: string;
  perfil: VehicleProfile;
  alertas: Alerta[];
  documentos: DocExtraction[];
  cotizacion: Prediction | null;
  /** undefined = no disponible en esta vista (GET /vehicles no trae valuación). */
  valuacion: Valuacion | null | undefined;
  omitidos: Record<string, string>;
  tiempo_ms: number | null;
  crudo: unknown;
}

function desdeExpediente(r: ExpedienteResponse): Vista {
  return {
    vehicle_id: r.vehicle_id, perfil: r.perfil, alertas: r.alertas, documentos: r.documentos,
    cotizacion: r.cotizacion, valuacion: r.valuacion, omitidos: r.omitidos || {}, tiempo_ms: r.tiempo_ms, crudo: r,
  };
}

const ORDEN: Record<Severidad, number> = { alta: 0, media: 1, info: 2 };

export default function Expediente() {
  const { vehicleId = "" } = useParams();
  const location = useLocation();
  const st = location.state as ExpedienteResponse | null;
  const cand = st && st.vehicle_id === vehicleId ? st : leerExpediente(vehicleId);
  // Solo se usa si tiene la forma completa de POST /expedientes (evita romper con entradas viejas o corruptas).
  const local = cand && Array.isArray(cand.perfil?.danos) && Array.isArray(cand.alertas) && Array.isArray(cand.documentos) ? cand : null;

  const { data, error, loading, reload } = useAsync<Vista>(async () => {
    if (local) return desdeExpediente(local);
    const v = await api.vehiculo(vehicleId);
    const preds = [...(v.predicciones || [])].sort((a, b) => b.created_at.localeCompare(a.created_at));
    return {
      vehicle_id: vehicleId, perfil: v.perfil, alertas: v.perfil.alertas || [], documentos: v.documentos || [],
      cotizacion: preds[0] ?? null, valuacion: undefined, omitidos: {}, tiempo_ms: null, crudo: v,
    };
  }, [vehicleId]);

  if (loading) {
    return (
      <div className="space-y-6" aria-busy="true" aria-label="Cargando expediente">
        <Skeleton className="h-28" />
        <Skeleton className="h-32" />
        <Skeleton className="h-72" />
        <div className="grid gap-6 md:grid-cols-2"><Skeleton className="h-48" /><Skeleton className="h-48" /></div>
      </div>
    );
  }
  if (error) {
    if (error instanceof ApiError && error.status === 404) {
      return (
        <EmptyState title="No encontramos este expediente" action={<Link to="/app/expediente/nuevo" className="btn-primary btn-sm">Nuevo expediente</Link>}>
          El vehículo <span className="num">{vehicleId}</span> no existe en la base local. Crea un expediente nuevo.
        </EmptyState>
      );
    }
    return <ErrorState error={error} onRetry={reload} />;
  }
  if (!data) return <EmptyState title="Sin datos" />;

  const { perfil } = data;
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={`Expediente · ${data.vehicle_id}`}
        title={`${perfil.marca} ${perfil.modelo} ${perfil.anio}`}
        actions={
          <>
            <Link to="/app/expediente/nuevo" className="btn-ghost btn-sm">Nuevo expediente</Link>
            <Link to={`/app/siniestro?vehicle_id=${encodeURIComponent(data.vehicle_id)}`} className="btn-ghost btn-sm">Dictaminar siniestro</Link>
            <button className="btn-primary btn-sm" onClick={() => descargarJSON(data.crudo, `expediente-${data.vehicle_id}.json`)}>Descargar JSON</button>
          </>
        }
      >
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <span className="chip"><span className="text-faint">VIN</span><span className="num text-ink">{perfil.vin || "—"}</span></span>
          <span className="chip"><span className="text-faint">Placas</span><span className="num text-ink">{perfil.placas || "—"}</span></span>
          {data.tiempo_ms != null && (
            <span className="chip"><span className="text-faint">Análisis</span><span className="num text-ink">{(data.tiempo_ms / 1000).toFixed(1)} s</span></span>
          )}
          <SimBadge />
        </div>
      </PageHeader>

      <Alertas alertas={data.alertas} />
      <Prima pred={data.cotizacion} />

      <div className="grid gap-6 md:grid-cols-2">
        <Danos perfil={perfil} omitidos={data.omitidos} />
        <Perfil perfil={perfil} />
      </div>

      <ValuacionCard valuacion={data.valuacion} omitidos={data.omitidos} />

      <Collapsible title="Documentos procesados" count={data.documentos.length}>
        <Documentos docs={data.documentos} />
      </Collapsible>
    </div>
  );
}

/* ---------------- Alertas ---------------- */

function Alertas({ alertas }: { alertas: Alerta[] }) {
  const ord = [...alertas].sort((a, b) => (ORDEN[a.severidad] ?? 3) - (ORDEN[b.severidad] ?? 3));
  const n = (s: Severidad) => alertas.filter((a) => a.severidad === s).length;
  const altas = n("alta");
  return (
    <Section
      title="Alertas"
      eyebrow="Cruce de documentos"
      id="sec-alertas"
      className={altas ? "border-alta/30" : ""}
      aside={
        <span className="num text-[14px] text-muted">
          <span className={altas ? "font-semibold text-alta" : ""}>{altas} {altas === 1 ? "alta" : "altas"}</span> · {n("media")} {n("media") === 1 ? "media" : "medias"} · {n("info")} info
        </span>
      }
    >
      {ord.length === 0 ? (
        <Note tone="ok">Sin discrepancias detectadas entre documentos.</Note>
      ) : (
        <ul className="space-y-3">
          {ord.map((a, i) => (
            <li key={`${a.codigo}-${i}`} className={`rounded-xl border px-4 py-3 ${a.severidad === "alta" ? "border-alta/30 bg-alta/5" : a.severidad === "media" ? "border-warn/30 bg-warn/5" : "border-line bg-paper"}`}>
              <div className="flex flex-wrap items-center gap-2">
                <SeverityBadge s={a.severidad} />
                <span className="text-[15px] font-semibold">{labelAlerta(a.codigo)}</span>
                <span className="font-mono text-[12px] text-faint">{a.codigo}</span>
              </div>
              <p className="mt-1.5 break-words text-[14px] text-muted">{a.detalle}</p>
              {a.fuentes.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {a.fuentes.map((f) => <span key={f} className="rounded-md border border-line bg-panel px-1.5 py-0.5 font-mono text-[11px] text-muted">{f}</span>)}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

/* ---------------- Prima ---------------- */

function Prima({ pred }: { pred: Prediction | null }) {
  if (!pred) {
    return (
      <Section title="Prima del seguro" id="sec-prima">
        <EmptyState title="Sin cotización registrada">Este vehículo todavía no tiene una predicción del cotizador.</EmptyState>
      </Section>
    );
  }
  const o = pred.output;
  const factores = Object.entries(o.factores || {}).sort((a, b) => Math.abs(b[1] - 1) - Math.abs(a[1] - 1));
  return (
    <section className="card overflow-hidden border-sand shadow-soft" aria-labelledby="sec-prima">
      <div className="grid gap-6 bg-cream/60 p-5 md:grid-cols-[1fr_1.1fr] md:p-7">
        <div className="space-y-1">
          <div className="eyebrow">Prima del seguro · simulada</div>
          <h2 id="sec-prima" className="sr-only">Prima del seguro</h2>
          <div className="num text-[44px] font-semibold leading-none tracking-tight md:text-[56px]">{fmtMXN(o.prima)}</div>
          <div className="text-[15px] text-muted">MXN por año · confianza <span className="num font-semibold text-ink">{fmtPct(o.confianza, 0)}</span></div>
        </div>
        <div className="self-center">
          <div className="mb-2 text-[13px] text-muted">Intervalo estimado</div>
          <IntervalBar lo={o.intervalo[0]} hi={o.intervalo[1]} value={o.prima} />
        </div>
      </div>
      <div className="p-5 md:p-7">
        <h3 className="mb-3 text-[16px] font-semibold">Factores que explican la prima</h3>
        {factores.length === 0 ? (
          <Note>Sin ajustes: se aplicó la prima base del cotizador.</Note>
        ) : (
          <ul className="divide-y divide-line rounded-xl border border-line">
            {factores.map(([k, m]) => (
              <li key={k} className="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-2 px-4 py-3 sm:grid-cols-[1.2fr_70px_1fr_110px]">
                <span className="text-[15px] font-medium">{labelFactor(k)}</span>
                <span className={`num text-right text-[15px] font-semibold ${m < 1 ? "text-ok" : m > 1 ? "text-alta" : "text-muted"}`}>{fmtMult(m)}</span>
                <span className="col-span-2 sm:col-span-1"><FactorBar m={m} /></span>
                <span className="hidden text-right text-[13px] text-muted sm:block">{m < 1 ? "abarata" : m > 1 ? "encarece" : "neutral"}</span>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-4 text-[14px] text-muted">Solo se usan variables del vehículo; nunca género, edad ni datos personales.</p>
        <p className="mt-2 break-all font-mono text-[12px] text-faint">
          {pred.agent_version} · {pred.prediction_id} · {fmtFecha(pred.created_at)}
        </p>
      </div>
    </section>
  );
}

/* ---------------- Daños ---------------- */

function Danos({ perfil, omitidos }: { perfil: VehicleProfile; omitidos: Record<string, string> }) {
  const total = perfil.danos.reduce((s, d) => s + d.costo_est, 0);
  return (
    <Section
      title="Daños detectados en fotos"
      id="sec-danos"
      aside={perfil.danos.length > 0 ? <span className="text-[14px] text-muted">Reacondicionamiento <span className="num font-semibold text-ink">{fmtMXN(total)}</span></span> : undefined}
    >
      <div className="space-y-3">
        {omitidos.visual && <Note>Revisión visual omitida: {omitidos.visual}</Note>}
        <DanosList danos={perfil.danos} />
      </div>
    </Section>
  );
}

/* ---------------- Perfil ---------------- */

function Perfil({ perfil }: { perfil: VehicleProfile }) {
  return (
    <Section title="Perfil" id="sec-perfil">
      <div className="grid grid-cols-2 gap-3">
        <Stat label="Kilometraje" value={fmtNum(perfil.kilometraje)} sub="km" />
        <Stat label="Siniestros previos" value={fmtNum(perfil.siniestros_previos)} />
        <Stat label="Uso" value={<span className="font-sans text-[18px]">{USO_LABEL[perfil.uso] || perfil.uso}</span>} />
        <Stat label="Zona" value={perfil.zona} />
      </div>
      <div className="mt-5">
        <ProgressBar value={perfil.cobertura_verificacion} label="Cobertura de verificación" />
        <p className="mt-1.5 text-[13px] text-faint">Fracción de campos confirmados por al menos 2 documentos.</p>
      </div>
    </Section>
  );
}

/* ---------------- Valuación ---------------- */

function ValuacionCard({ valuacion, omitidos }: { valuacion: Valuacion | null | undefined; omitidos: Record<string, string> }) {
  if (valuacion === undefined) {
    return (
      <Section title="Valuación" id="sec-val">
        <Note>Valuación no disponible en esta vista. Solo se calcula al crear el expediente.</Note>
      </Section>
    );
  }
  if (valuacion === null) {
    return (
      <Section title="Valuación" id="sec-val">
        <Note>Valuación omitida{omitidos.valuacion ? `: ${omitidos.valuacion}` : "."}</Note>
      </Section>
    );
  }
  const v = valuacion;
  return (
    <Section
      title="Valuación"
      eyebrow="Precio de compra estimado"
      id="sec-val"
      aside={<span className="chip !py-0.5 !text-[12px]">Fuente: {v.fuente}</span>}
    >
      <div className="grid gap-5 md:grid-cols-[1fr_1.4fr]">
        <div>
          <div className="num text-[34px] font-semibold leading-none tracking-tight">{fmtMXN(v.precio_estimado)}</div>
          <div className="num mt-2 text-[14px] text-muted">Rango {fmtMXN(v.rango[0])} – {fmtMXN(v.rango[1])}</div>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Stat label="Mercado" value={<span className="text-[17px]">{fmtMXN(v.precio_mercado)}</span>} />
          <Stat label="Desc. por daños" value={<span className="whitespace-nowrap text-[17px]">{v.descuento_danos ? `−${fmtMXN(v.descuento_danos)}` : fmtMXN(0)}</span>} sub={v.descuento_danos ? "por daños detectados" : undefined} tone={v.descuento_danos ? "alta" : undefined} />
          <Stat label="Comparables" value={<span className="text-[17px]">{fmtNum(v.n_comparables)}</span>} />
        </div>
      </div>
      <div className="mt-5">
        <Collapsible title="Comparables" count={v.comparables.length}>
          {v.comparables.length === 0 ? (
            <p className="text-[14px] text-muted">Sin comparables.</p>
          ) : (
            <div className="-mx-4 overflow-x-auto px-4">
              <table className="w-full min-w-[560px] text-left text-[14px]">
                <thead className="text-[12px] uppercase tracking-wider text-faint">
                  <tr>
                    <th className="py-2 pr-3 font-normal">Anuncio</th>
                    <th className="py-2 pr-3 text-right font-normal">Año</th>
                    <th className="py-2 pr-3 text-right font-normal">Km</th>
                    <th className="py-2 pr-3 text-right font-normal">Precio</th>
                    <th className="py-2 text-right font-normal">Ajustado</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {v.comparables.map((c, i) => (
                    <tr key={i} className={c.atipico ? "text-faint" : ""}>
                      <td className="py-2 pr-3">
                        <span className="mr-2">{c.titulo || "—"}</span>
                        {c.atipico && <span className="rounded-md border border-warn/30 bg-warn/10 px-1.5 py-0.5 text-[11px] font-semibold text-warn">Atípico</span>}
                      </td>
                      <td className="num py-2 pr-3 text-right">{c.anio ?? "—"}</td>
                      <td className="num py-2 pr-3 text-right">{fmtNum(c.kilometraje)}</td>
                      <td className="num py-2 pr-3 text-right">{fmtMXN(c.precio)}</td>
                      <td className="num py-2 text-right">{fmtMXN(c.precio_ajustado)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="mt-2 text-[12px] text-faint">Anuncios simulados; los enlaces no apuntan a sitios reales.</p>
        </Collapsible>
      </div>
    </Section>
  );
}

/* ---------------- Documentos ---------------- */

function Documentos({ docs }: { docs: DocExtraction[] }) {
  if (!docs.length) return <p className="text-[14px] text-muted">Sin documentos procesados.</p>;
  return (
    <ul className="grid gap-3 md:grid-cols-2">
      {docs.map((d) => (
        <li key={d.documento_id} className="rounded-xl border border-line bg-panel p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-mono text-[13px] font-semibold">{d.documento_id}</span>
            <span className="chip !py-0.5 !text-[12px]">{TIPO_DOC_LABEL[d.tipo] || d.tipo}</span>
          </div>
          <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[14px]">
            {([
              ["VIN", d.vin], ["Placas", d.placas], ["Marca", d.marca], ["Modelo", d.modelo],
              ["Año", d.anio], ["Vigencia", d.vigencia], ["Confianza", fmtPct(d.confianza, 0)],
            ] as [string, string | number | null][]).map(([k, val]) => (
              <div key={k} className="contents">
                <dt className="text-faint">{k}</dt>
                <dd className="num min-w-0 break-all text-ink">{val ?? "—"}</dd>
              </div>
            ))}
          </dl>
        </li>
      ))}
    </ul>
  );
}
