// Resumen (portada de la app): KPIs reales de la API, actividad de agentes y accesos rápidos.
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Dot, ErrorState, Skeleton, Stat, useAsync } from "../components/ui";
import { origenParche, saludo, tonoMejora, veredictoDe, type Tono } from "../components/rsi/shared";
import { api, API_URL, ApiError } from "../lib/api";
import { fmtFecha, fmtMillones, fmtNum, fmtSignedPct, shortSha, TIPO_PARCHE_LABEL } from "../lib/format";

interface Actividad { key: string; tone: Tono; agente: string; texto: ReactNode; estado: ReactNode }

function Kpi({ loading, error, children }: { loading: boolean; error: unknown; children: ReactNode }) {
  if (loading) return <Skeleton className="h-[92px]" />;
  if (error) return <div className="card-cream flex h-[92px] items-center justify-center px-4 text-center text-[13px] text-alta">Sin datos</div>;
  return <>{children}</>;
}

const ACCESOS = [
  { to: "/app/expediente/nuevo", titulo: "Nuevo expediente", texto: "Sube factura, tarjeta y fotos: verificación, valuación y prima explicada." },
  { to: "/app/siniestro", titulo: "Dictamen de siniestro", texto: "Separa daños preexistentes de los nuevos y marca banderas." },
  { to: "/app/laboratorio", titulo: "Laboratorio RSI", texto: "Curvas de regret de las tres variantes del cotizador." },
];

export default function Resumen() {
  const health = useAsync(() => api.health(), []);
  const run = useAsync(() => api.ultimaCorrida(false), []);
  const patches = useAsync(() => api.parches(), []);
  const versions = useAsync(() => api.versiones(), []);

  const s = run.data?.summary;
  const sinCorrida = run.error instanceof ApiError && run.error.status === 404;
  const ps = patches.data?.patches ?? [];
  const runId = run.data?.run_id ?? null;
  // parches con su origen (corrida y variante, sacados del patch_id) y su orden en la respuesta
  const conOrigen = ps.map((p, i) => ({ p, i, ...origenParche(p.patch_id) }));
  const deUltima = runId ? conOrigen.filter((x) => x.runId === runId) : [];
  // KPI: solo la última corrida y solo la variante de auto-mejora (rsi)
  const kpiPs = deUltima.filter((x) => x.variante === "rsi").map((x) => x.p);
  const aceptados = kpiPs.filter((p) => p.veredicto === "aceptado").length;
  const campeona = versions.data?.versions.find((v) => v.estado === "campeon") ?? versions.data?.versions[0];
  // Actividad: preferentemente de la última corrida; primero los aceptados más recientes, luego el resto
  const recientes = (deUltima.length ? deUltima : conOrigen)
    .sort((a, b) =>
      Number(b.p.veredicto === "aceptado") - Number(a.p.veredicto === "aceptado")
      || b.p.generation - a.p.generation || a.i - b.i)
    .slice(0, 5);

  const actividad: Actividad[] = [];
  if (!health.loading) {
    actividad.push(health.error
      ? { key: "api", tone: "alta", agente: "API local", texto: `Sin conexión con la API en ${API_URL.replace(/^https?:\/\//, "")}`, estado: "Revisar" }
      : { key: "api", tone: "ok", agente: "API local", texto: `En línea · LLM ${health.data?.llm === "real" ? "real" : "simulado"}${health.data?.auth ? " · con llave" : ""}`, estado: "Ahora" });
  }
  if (campeona) {
    actividad.push({ key: "ver", tone: "ok", agente: "Cotizador", texto: <>Versión <span className="font-mono">{campeona.id}</span> en producción</>, estado: fmtFecha(campeona.created_at) });
  }
  if (s) {
    actividad.push({
      key: "run", tone: s.gate2 ? "ok" : "warn", agente: "Laboratorio RSI",
      texto: <>Corrida <span className="font-mono">{run.data?.run_id}</span>: regret {fmtSignedPct(-s.mejora_rsi)} vs reglas fijas</>,
      estado: s.gate2 ? "Gate 2 cumple" : "Gate 2 no cumple",
    });
  }
  for (const { p, variante } of recientes) {
    const v = veredictoDe(p);
    actividad.push({
      key: p.patch_id, tone: v.tone, agente: `Parche · gen. ${p.generation}${variante ? ` · ${variante === "rsi" ? "auto-mejora" : variante === "parametros" ? "parámetros" : "reglas fijas"}` : ""}`,
      texto: <>{TIPO_PARCHE_LABEL[p.tipo] ?? p.tipo}<span className="text-faint"> — </span><span className="text-muted">{p.razon || p.hipotesis}</span></>,
      estado: v.label,
    });
  }
  const cargandoActividad = health.loading || versions.loading || run.loading || patches.loading;

  return (
    <div className="space-y-8">
      <header className="space-y-4 border-b border-line pb-7">
        <span className="chip"><Dot tone={health.error ? "alta" : health.loading ? "warn" : "ok"} />{saludo()} · panel de AutoGuard AI · datos simulados</span>
        <h1 className="text-[34px] font-bold leading-[1.05] tracking-tight md:text-[48px]">
          Tu cotizador, <span className="text-gradient">aprendiendo.</span>
        </h1>
        <p className="max-w-2xl text-[16px] leading-relaxed text-muted">
          Verificación de documentos y fotos, valuación y prima explicada para autos seminuevos, con un ciclo de auto-mejora
          vigilado por un evaluador congelado. Esto es lo que pasa hoy en tu instancia local.
        </p>
        <div className="flex flex-wrap gap-2">
          <Link to="/app/expediente/nuevo" className="btn-primary">Nuevo expediente →</Link>
          <Link to="/app/laboratorio" className="btn-ghost">Ver el laboratorio</Link>
        </div>
      </header>

      <section aria-label="Indicadores" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi loading={run.loading} error={run.error}>
          {s && <Stat label="Regret RSI vs reglas fijas" value={fmtSignedPct(-s.mejora_rsi)} sub={`${fmtMillones(s.regret.rsi)} vs ${fmtMillones(s.regret.estatico)}`} tone={tonoMejora(s.mejora_rsi)} />}
        </Kpi>
        <Kpi loading={run.loading} error={run.error}>
          {s && <Stat label="Pólizas por variante" value={fmtNum(s.batches * s.batch_size)} sub={`${fmtNum(s.batches)} lotes × ${fmtNum(s.batch_size)}`} />}
        </Kpi>
        <Kpi loading={patches.loading || run.loading} error={patches.error || (run.error && !sinCorrida ? run.error : null)}>
          <Stat label="Aceptados en la última corrida (auto-mejora)" value={<>{fmtNum(aceptados)}<span className="text-[15px] text-faint"> / {fmtNum(kpiPs.length)}</span></>}
            sub={kpiPs.length ? `${Math.round((aceptados / kpiPs.length) * 100)}% pasa el evaluador` : runId ? "sin parches de esta corrida" : "sin corridas aún"} />
        </Kpi>
        <Kpi loading={versions.loading} error={versions.error}>
          <Stat label="Versión campeona" value={campeona ? shortSha(campeona.git_sha) : "—"}
            sub={versions.data ? `${fmtNum(versions.data.versions.length)} ${versions.data.versions.length === 1 ? "versión" : "versiones"} en el linaje` : undefined} />
        </Kpi>
      </section>

      {sinCorrida && (
        <div className="card-cream px-5 py-4 text-[15px] text-muted">
          Aún no hay corridas del experimento RSI. Genera la de demostración con{" "}
          <code className="font-mono text-[13px] text-ink">bash scripts/demo.sh --start</code> o lánzala desde el{" "}
          <Link to="/app/laboratorio" className="text-ink underline decoration-sand underline-offset-2">Laboratorio</Link>.
        </div>
      )}
      {!!run.error && !sinCorrida &&<ErrorState error={run.error} onRetry={run.reload} />}

      <section className="card-cream p-4 sm:p-5" aria-labelledby="h-actividad">
        <h2 id="h-actividad" className="eyebrow mb-3 text-center">Actividad de agentes</h2>
        {cargandoActividad && !actividad.length ? (
          <div className="space-y-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-7 !bg-panel" />)}</div>
        ) : !actividad.length ? (
          <p className="py-4 text-center text-[14px] text-muted">Sin actividad registrada todavía.</p>
        ) : (
          <ul className="divide-y divide-line/70">
            {actividad.map((a) => (
              <li key={a.key} className="grid grid-cols-[auto_1fr_auto] items-start gap-x-3 gap-y-0.5 py-2.5 text-[14px] sm:grid-cols-[auto_190px_1fr_auto] sm:items-center">
                <span className="pt-1.5 sm:pt-0"><Dot tone={a.tone} /></span>
                <span className="font-medium text-ink">{a.agente}</span>
                <span className="col-start-2 col-end-4 row-start-2 min-w-0 whitespace-normal break-words text-muted line-clamp-2 sm:col-start-3 sm:col-end-auto sm:row-start-1 sm:truncate sm:line-clamp-none" title={typeof a.texto === "string" ? a.texto : undefined}>{a.texto}</span>
                <span className={`col-start-3 row-start-1 whitespace-nowrap text-right text-[13px] sm:col-start-4 ${a.tone === "ok" ? "text-faint" : a.tone === "warn" ? "text-warn" : a.tone === "alta" ? "text-alta" : "text-info"}`}>{a.estado}</span>
              </li>
            ))}
          </ul>
        )}
        {!!(patches.error || versions.error) && (
          <div className="mt-3 flex justify-center">
            <button type="button" className="btn-ghost btn-sm" onClick={() => { patches.reload(); versions.reload(); health.reload(); }}>Reintentar</button>
          </div>
        )}
      </section>

      <section aria-labelledby="h-accesos" className="space-y-3">
        <h2 id="h-accesos" className="eyebrow">Accesos rápidos</h2>
        <div className="grid gap-3 md:grid-cols-3">
          {ACCESOS.map((a) => (
            <Link key={a.to} to={a.to} className="card group block p-5 transition hover:border-sand focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-taupe">
              <div className="flex items-center justify-between text-[16px] font-semibold">
                {a.titulo}<span className="text-faint transition group-hover:translate-x-0.5 group-hover:text-ink" aria-hidden="true">→</span>
              </div>
              <p className="mt-1 text-[14px] text-muted">{a.texto}</p>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
