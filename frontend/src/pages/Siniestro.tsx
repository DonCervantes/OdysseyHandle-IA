// Dictamen preliminar de siniestro: fotos del siniestro vs daños registrados → POST /dictamen/expediente.
import { useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { EmptyState, ErrorState, PageHeader, SeverityBadge, SimBadge, Skeleton, Stat } from "../components/ui";
import { api } from "../lib/api";
import type { Alerta, DictamenResult } from "../lib/types";
import { fmtMXN, fmtNum, labelAlerta } from "../lib/format";
import {
  DanosList, Dropzone, Note, Section, Spinner, Thumbs, ZONAS_VEHICULO, labelZona, listarExpedientesGuardados, useFotos,
} from "../components/expediente/bits";
import { formDictamen } from "../components/expediente/formdata";

/** Valores reales de autoguard/agents/dictamen.py (`SeveridadDictamen`). */
type Sev = "limpio" | "revision" | "sospechoso";

const SEV_UI: Record<Sev, { titulo: string; texto: string; cls: string; dot: string }> = {
  limpio: { titulo: "Limpio", texto: "Sin señales de fraude: el daño reclamado es nuevo y coherente con el relato.", cls: "border-ok/30 bg-ok/5 text-ok", dot: "bg-ok" },
  revision: { titulo: "Requiere revisión", texto: "Hay señales que un ajustador debe revisar antes de pagar.", cls: "border-warn/30 bg-warn/5 text-warn", dot: "bg-warn" },
  sospechoso: { titulo: "Sospechoso", texto: "Señales fuertes de daño preexistente o reclamo inflado.", cls: "border-alta/30 bg-alta/5 text-alta", dot: "bg-alta" },
};
const normSev = (s: string): Sev => (s === "limpio" || s === "sospechoso" ? s : "revision");

const BANDERA_LABEL: Record<string, string> = {
  DANO_PREEXISTENTE_RECLAMADO: "Daño preexistente reclamado",
  ZONA_INCOMPATIBLE: "Las zonas del relato no coinciden con las fotos",
  MONTO_ATIPICO: "Monto declarado atípico",
  SIN_DANOS_DETECTADOS: "No se detectaron daños en las fotos",
  SOLO_PREEXISTENTES: "Todo el daño ya estaba registrado",
};
const labelBandera = (c: string) => BANDERA_LABEL[c] || labelAlerta(c);
const ORDEN = { alta: 0, media: 1, info: 2 } as const;

export default function Siniestro() {
  const [params] = useSearchParams();
  const guardados = useMemo(() => listarExpedientesGuardados(), []);
  const [vehicleId, setVehicleId] = useState(params.get("vehicle_id") || guardados[0]?.id || "");
  const { fotos, agregar, quitar } = useFotos();
  const [zonas, setZonas] = useState<string[]>([]);
  const [monto, setMonto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [res, setRes] = useState<DictamenResult | null>(null);
  const [intentado, setIntentado] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const resRef = useRef<HTMLDivElement>(null);

  const montoNum = Number(monto.replace(/,/g, "").trim());
  const montoOk = monto.trim() === "" || (Number.isFinite(montoNum) && montoNum >= 0);
  const valido = fotos.length > 0 && vehicleId.trim() !== "" && montoOk;

  async function dictaminar() {
    setIntentado(true);
    if (!valido || enviando) return;
    setEnviando(true);
    setError(null);
    setRes(null);
    try {
      const r = await api.dictamenExpediente(formDictamen(fotos.map((f) => f.file), vehicleId, zonas, monto));
      setRes(r);
      setTimeout(() => resRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    } catch (e) {
      setError(e);
    } finally {
      setEnviando(false);
    }
  }
  const enviar = (e: FormEvent) => { e.preventDefault(); void dictaminar(); };
  const toggle = (z: string) => setZonas((p) => (p.includes(z) ? p.filter((x) => x !== z) : [...p, z]));

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Ajustador · siniestros" title="Dictamen de siniestro" actions={<SimBadge />}>
        Compara las fotos de un siniestro con los daños ya registrados del auto para detectar daños preexistentes o
        reclamos inflados (p. ej. “montachoques”).
      </PageHeader>

      <form onSubmit={enviar} className="grid gap-6 lg:grid-cols-[1fr_320px]" noValidate>
        <div className="min-w-0 space-y-6">
          <Section title="Vehículo" eyebrow="Expediente ya creado" id="sec-veh">
            {guardados.length > 0 && (
              <div className="mb-3">
                <label className="label" htmlFor="guardado">Elegir de esta sesión</label>
                <select id="guardado" className="input" value={guardados.some((g) => g.id === vehicleId) ? vehicleId : ""} onChange={(e) => e.target.value && setVehicleId(e.target.value)}>
                  <option value="">— Otro (escríbelo abajo) —</option>
                  {guardados.map((g) => <option key={g.id} value={g.id}>{g.titulo} · {g.id}</option>)}
                </select>
              </div>
            )}
            <label className="label" htmlFor="vid">ID del vehículo</label>
            <input id="vid" className="input num" placeholder="veh-…" value={vehicleId} onChange={(e) => setVehicleId(e.target.value)} aria-invalid={intentado && !vehicleId.trim()} />
            {intentado && !vehicleId.trim() && <p className="mt-1 text-[14px] text-alta" role="alert">Escribe el ID de un vehículo con expediente.</p>}
            {guardados.length === 0 && (
              <p className="mt-2 text-[13px] text-muted">
                No hay expedientes en esta sesión. <Link to="/app/expediente/nuevo" className="text-taupe underline underline-offset-2">Crea uno</Link> o pega su ID.
              </p>
            )}
          </Section>

          <Section title="Fotos del siniestro" eyebrow="Obligatorio · al menos 1" id="sec-fotos">
            <Dropzone
              id="fotos-siniestro"
              label="Fotos del siniestro"
              accept=".png,.jpg,.jpeg,image/png,image/jpeg"
              exts={["png", "jpg", "jpeg"]}
              hint="PNG o JPG del daño reclamado."
              onFiles={(ok, r) => { agregar(ok); setAviso(r.length ? `Se ignoraron ${r.length} archivo(s) que no son PNG o JPG: ${r.join(", ")}` : null); }}
            />
            <Thumbs fotos={fotos} onRemove={quitar} />
            {aviso && <div className="mt-3"><Note tone="warn">{aviso}</Note></div>}
            {intentado && fotos.length === 0 && <p className="mt-2 text-[14px] text-alta" role="alert">Agrega al menos una foto.</p>}
          </Section>

          <Section title="Relato del asegurado" eyebrow="Opcional" id="sec-relato">
            <fieldset>
              <legend className="label">Zonas que el asegurado dice que se dañaron</legend>
              <div className="flex flex-wrap gap-2">
                {ZONAS_VEHICULO.map((z) => {
                  const on = zonas.includes(z);
                  return (
                    <button
                      key={z}
                      type="button"
                      aria-pressed={on}
                      onClick={() => toggle(z)}
                      className={`rounded-full border px-3 py-1.5 text-[13px] transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-taupe ${on ? "border-ink bg-ink text-paper" : "border-line bg-panel text-muted hover:border-sand"}`}
                    >
                      {labelZona(z)}
                    </button>
                  );
                })}
              </div>
            </fieldset>
            <div className="mt-4 max-w-xs">
              <label className="label" htmlFor="monto">Monto declarado (MXN, opcional)</label>
              <input id="monto" className="input num" inputMode="decimal" placeholder="p. ej. 20000" value={monto} onChange={(e) => setMonto(e.target.value)} aria-invalid={!montoOk} />
              {!montoOk && <p className="mt-1 text-[13px] text-alta">Escribe un monto mayor o igual a 0.</p>}
            </div>
          </Section>
        </div>

        <aside className="space-y-4 lg:sticky lg:top-24 lg:self-start">
          <div className="card space-y-3 p-5">
            <button type="submit" className="btn-primary w-full" disabled={enviando}>
              {enviando && <Spinner />}
              {enviando ? "Dictaminando…" : "Emitir dictamen"}
            </button>
            <p className="text-[13px] text-muted">Dictamen preliminar y determinístico. No sustituye la revisión de un ajustador.</p>
          </div>
          <div className="card-cream space-y-2 p-5 text-[14px] leading-relaxed text-muted">
            <div className="font-semibold text-ink">Probar con una muestra</div>
            <p>1. Crea el expediente de <span className="num text-[12px] text-ink">EXP-002</span> con la foto <span className="num text-[12px] text-ink">FOTO-002.png</span>.</p>
            <p>2. Aquí, sube otra vez <span className="num text-[12px] text-ink">data/samples/fotos/FOTO-002.png</span>: el daño ya estaba registrado → <strong className="text-alta">sospechoso</strong>.</p>
            <p>Con <span className="num text-[12px] text-ink">FOTO-001.png</span> (defensa trasera, daño nuevo) el dictamen sale <strong className="text-ok">limpio</strong>.</p>
          </div>
        </aside>
      </form>

      <div ref={resRef} className="scroll-mt-24">
        {enviando ? (
          <div className="space-y-4" aria-busy="true" aria-label="Emitiendo dictamen"><Skeleton className="h-32" /><Skeleton className="h-48" /></div>
        ) : error != null ? (
          <ErrorState error={error} onRetry={() => void dictaminar()} />
        ) : res ? (
          <Resultado r={res} />
        ) : (
          <EmptyState title="Aún no hay dictamen">Elige el vehículo, sube las fotos del siniestro y presiona “Emitir dictamen”.</EmptyState>
        )}
      </div>
    </div>
  );
}

function Resultado({ r }: { r: DictamenResult }) {
  const sev = normSev(r.severidad);
  const ui = SEV_UI[sev];
  const banderas = [...r.banderas].sort((a, b) => (ORDEN[a.severidad] ?? 3) - (ORDEN[b.severidad] ?? 3));
  return (
    <div className="space-y-6">
      <section className={`rounded-xl2 border p-6 md:p-8 ${ui.cls}`} aria-live="polite" aria-labelledby="dict-sev">
        <div className="eyebrow !text-current opacity-70">Dictamen preliminar · {r.vehicle_id}</div>
        <div className="mt-2 flex items-center gap-3">
          <span className={`h-4 w-4 shrink-0 rounded-full ${ui.dot}`} aria-hidden="true" />
          <h2 id="dict-sev" className="text-[34px] font-semibold leading-none tracking-tight md:text-[44px]">{ui.titulo}</h2>
        </div>
        <p className="mt-3 max-w-2xl text-[15px] text-ink/80">{ui.texto}</p>
      </section>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Costo del siniestro" value={fmtMXN(r.costo_siniestro_est)} sub="solo daños nuevos" />
        <Stat label="Preexistente coincidente" value={fmtMXN(r.costo_preexistente_coincidente)} sub={r.costo_preexistente_coincidente > 0 ? "no debería pagarse" : "sin coincidencias"} tone={r.costo_preexistente_coincidente > 0 ? "alta" : "ok"} />
        <Stat label="Daños nuevos" value={fmtNum(r.danos_nuevos.length)} />
        <Stat label="Daños preexistentes" value={fmtNum(r.danos_preexistentes.length)} tone={r.danos_preexistentes.length ? "alta" : undefined} sub={r.danos_preexistentes.length ? "ya registrados" : undefined} />
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Section title="Daños nuevos" eyebrow="Cubribles" id="dict-nuevos">
          <DanosList danos={r.danos_nuevos} empty="Ningún daño nuevo." emptyTone="info" />
        </Section>
        <Section title="Daños preexistentes" eyebrow="Ya estaban en el expediente" id="dict-pre">
          {r.danos_preexistentes.length ? <DanosList danos={r.danos_preexistentes} /> : <Note tone="ok">Ningún daño reclamado estaba registrado antes.</Note>}
        </Section>
      </div>

      <Section title="Banderas" id="dict-banderas" aside={<span className="num text-[14px] text-muted">{banderas.length}</span>}>
        {banderas.length === 0 ? <Note tone="ok">Sin banderas.</Note> : <Banderas banderas={banderas} />}
      </Section>

      <Section title="Explicación" id="dict-exp">
        <ol className="list-decimal space-y-1.5 pl-5 text-[14px] text-muted">
          {r.explicacion.map((e, i) => <li key={i} className="break-words">{e}</li>)}
        </ol>
        {r.simulados && <p className="mt-3 text-[12px] text-faint">Costos de tabla SIMULADOS (data/costos_reparacion.yaml).</p>}
      </Section>
    </div>
  );
}

function Banderas({ banderas }: { banderas: Alerta[] }) {
  return (
    <ul className="space-y-3">
      {banderas.map((a, i) => (
        <li key={`${a.codigo}-${i}`} className={`rounded-xl border px-4 py-3 ${a.severidad === "alta" ? "border-alta/30 bg-alta/5" : a.severidad === "media" ? "border-warn/30 bg-warn/5" : "border-line bg-paper"}`}>
          <div className="flex flex-wrap items-center gap-2">
            <SeverityBadge s={a.severidad} />
            <span className="text-[15px] font-semibold">{labelBandera(a.codigo)}</span>
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
  );
}
