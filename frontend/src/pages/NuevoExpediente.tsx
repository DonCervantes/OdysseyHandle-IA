// Nuevo expediente: documentos + fotos + datos declarados → POST /expedientes.
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ErrorState, PageHeader, SimBadge } from "../components/ui";
import { api, guardarExpediente } from "../lib/api";
import type { TipoDocumento } from "../lib/types";
import {
  Dropzone, Note, Section, Spinner, Steps, Thumbs, TIPO_DOC_LABEL, nuevoId, useFotos, useSteps,
} from "../components/expediente/bits";
import { formExpediente, type DatosDeclarados, type TipoElegido } from "../components/expediente/formdata";

const PASOS = ["Leyendo documentos…", "Verificando datos…", "Revisando fotos…", "Valuando y cotizando…"];
const TIPOS: TipoDocumento[] = ["factura", "tarjeta_circulacion", "poliza_anterior", "otro"];
const DOC_EXTS = ["png", "jpg", "jpeg", "pdf"];
const FOTO_EXTS = ["png", "jpg", "jpeg"];

interface Doc { id: string; file: File; tipo: TipoElegido }

function entero(v: string) {
  return v.trim() === "" || (/^\d+$/.test(v.trim()) && Number(v) >= 0);
}

export default function NuevoExpediente() {
  const navigate = useNavigate();
  const [docs, setDocs] = useState<Doc[]>([]);
  const { fotos, agregar, quitar } = useFotos();
  const [datos, setDatos] = useState<DatosDeclarados>({ kilometraje: "", siniestros_previos: "", uso: "", zona: "" });
  const [vehicleId, setVehicleId] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [intentado, setIntentado] = useState(false);
  const paso = useSteps(enviando, PASOS.length);

  const kmOk = entero(datos.kilometraje);
  const sinOk = entero(datos.siniestros_previos);
  const valido = docs.length > 0 && kmOk && sinOk;

  const rechazo = (r: string[], tipos: string) => {
    if (r.length) setAviso(`Se ignoraron ${r.length} archivo(s) que no son ${tipos}: ${r.join(", ")}`);
  };

  function enviar(e: FormEvent) {
    e.preventDefault();
    void analizar();
  }

  async function analizar() {
    setIntentado(true);
    if (!valido || enviando) return;
    setEnviando(true);
    setError(null);
    try {
      const fd = formExpediente(docs, fotos.map((f) => f.file), datos, vehicleId);
      const r = await api.crearExpediente(fd);
      guardarExpediente(r);
      navigate(`/app/expediente/${encodeURIComponent(r.vehicle_id)}`, { state: r });
    } catch (err) {
      setError(err);
      setEnviando(false);
    }
  }

  const set = (k: keyof DatosDeclarados) => (e: { target: { value: string } }) => setDatos((d) => ({ ...d, [k]: e.target.value }));

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Valuador · expediente" title="Nuevo expediente" actions={<SimBadge />}>
        Sube los documentos del auto y, si los tienes, fotos y datos declarados. AutoGuard cruza los documentos,
        detecta daños, valúa el auto y explica su prima en segundos.
      </PageHeader>

      <form onSubmit={enviar} className="grid gap-6 lg:grid-cols-[1fr_320px]" noValidate>
        <div className="min-w-0 space-y-6">
          <Section title="Documentos" eyebrow="Obligatorio · al menos 1" id="sec-docs">
            <Dropzone
              id="docs"
              label="Documentos del vehículo"
              accept=".png,.jpg,.jpeg,.pdf,image/png,image/jpeg,application/pdf"
              exts={DOC_EXTS}
              hint="PNG, JPG o PDF: factura, tarjeta de circulación, póliza anterior."
              onFiles={(ok, r) => { setDocs((p) => [...p, ...ok.map((file) => ({ id: nuevoId(), file, tipo: "" as TipoElegido }))]); rechazo(r, "PNG, JPG o PDF"); }}
            />
            <p className="mt-2 text-[13px] text-muted">
              El nombre del archivo ayuda a inferir el tipo: <span className="num">FAC</span> = factura,{" "}
              <span className="num">TC</span> = tarjeta de circulación, <span className="num">POL</span> = póliza.
            </p>
            {docs.length > 0 && (
              <ul className="mt-4 divide-y divide-line rounded-xl border border-line">
                {docs.map((d, i) => (
                  <li key={d.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                    <span className="num w-6 shrink-0 text-[13px] text-faint">{i + 1}</span>
                    <span className="min-w-0 flex-[1_1_70%] truncate text-[15px] sm:flex-1" title={d.file.name}>{d.file.name}</span>
                    <div className="ml-9 flex flex-1 gap-2 sm:ml-0 sm:flex-none">
                    <label className="sr-only" htmlFor={`tipo-${d.id}`}>Tipo de {d.file.name}</label>
                    <select
                      id={`tipo-${d.id}`}
                      className="input min-w-0 flex-1 !py-1.5 text-[14px] sm:!w-auto sm:flex-none"
                      value={d.tipo}
                      onChange={(e) => setDocs((p) => p.map((x) => (x.id === d.id ? { ...x, tipo: e.target.value as TipoElegido } : x)))}
                    >
                      <option value="">Inferir del nombre</option>
                      {TIPOS.map((t) => <option key={t} value={t}>{TIPO_DOC_LABEL[t]}</option>)}
                    </select>
                    <button type="button" className="btn-ghost btn-sm" onClick={() => setDocs((p) => p.filter((x) => x.id !== d.id))} aria-label={`Quitar ${d.file.name}`}>
                      Quitar
                    </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {docs.length > 1 && docs.some((d) => d.tipo) && docs.some((d) => !d.tipo) && (
              <p className="mt-2 text-[13px] text-warn">Hay documentos con tipo elegido y otros en “Inferir”: se inferirán todos del nombre.</p>
            )}
            {intentado && docs.length === 0 && <p className="mt-2 text-[14px] text-alta" role="alert">Agrega al menos un documento.</p>}
          </Section>

          <Section title="Fotos del vehículo" eyebrow="Opcional" id="sec-fotos">
            <Dropzone
              id="fotos"
              label="Fotos del vehículo"
              accept=".png,.jpg,.jpeg,image/png,image/jpeg"
              exts={FOTO_EXTS}
              hint="PNG o JPG. Se usan para detectar daños y estimar el reacondicionamiento."
              onFiles={(ok, r) => { agregar(ok); rechazo(r, "PNG o JPG"); }}
            />
            <Thumbs fotos={fotos} onRemove={quitar} />
          </Section>

          {aviso && <Note tone="warn">{aviso}</Note>}

          <Section title="Datos declarados" eyebrow="Opcional" id="sec-datos">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="label" htmlFor="km">Kilometraje</label>
                <input id="km" className="input num" inputMode="numeric" placeholder="p. ej. 85000" value={datos.kilometraje} onChange={set("kilometraje")} aria-invalid={!kmOk} />
                {!kmOk && <p className="mt-1 text-[13px] text-alta">Escribe un entero mayor o igual a 0.</p>}
              </div>
              <div>
                <label className="label" htmlFor="sin">Siniestros previos</label>
                <input id="sin" className="input num" inputMode="numeric" placeholder="p. ej. 0" value={datos.siniestros_previos} onChange={set("siniestros_previos")} aria-invalid={!sinOk} />
                {!sinOk && <p className="mt-1 text-[13px] text-alta">Escribe un entero mayor o igual a 0.</p>}
              </div>
              <div>
                <label className="label" htmlFor="uso">Uso</label>
                <select id="uso" className="input" value={datos.uso} onChange={set("uso")}>
                  <option value="">Sin declarar</option>
                  <option value="particular">Particular</option>
                  <option value="app_transporte">App de transporte</option>
                  <option value="comercial">Comercial</option>
                </select>
              </div>
              <div>
                <label className="label" htmlFor="zona">Zona</label>
                <select id="zona" className="input" value={datos.zona} onChange={set("zona")}>
                  <option value="">Sin declarar</option>
                  {["CDMX", "EDOMEX", "JAL", "NL", "PUE", "OTRA"].map((z) => <option key={z} value={z}>{z}</option>)}
                </select>
              </div>
              <div className="sm:col-span-2">
                <label className="label" htmlFor="vid">ID de vehículo (opcional)</label>
                <input id="vid" className="input num" placeholder="Se genera solo si lo dejas vacío" value={vehicleId} onChange={(e) => setVehicleId(e.target.value)} />
              </div>
            </div>
          </Section>
        </div>

        <aside className="space-y-4 lg:sticky lg:top-24 lg:self-start">
          <div className="card space-y-4 p-5">
            <div className="text-[14px] text-muted">
              <span className="num font-semibold text-ink">{docs.length}</span> documento(s) ·{" "}
              <span className="num font-semibold text-ink">{fotos.length}</span> foto(s)
            </div>
            <button type="submit" className="btn-primary w-full" disabled={enviando || (intentado && !valido)}>
              {enviando && <Spinner />}
              {enviando ? "Analizando…" : "Analizar expediente"}
            </button>
            {enviando && <Steps steps={PASOS} current={paso} />}
            {error != null && !enviando && <ErrorState error={error} onRetry={() => void analizar()} />}
          </div>

          <div className="card-cream space-y-2 p-5 text-[14px] leading-relaxed text-muted">
            <div className="font-semibold text-ink">Probar con una muestra</div>
            <p>Los archivos de prueba (todos SIMULADOS) están en la carpeta del repo <span className="num text-[12px]">data/samples/</span>. Arrástralos desde tu explorador:</p>
            <ul className="list-disc space-y-1 pl-5">
              <li><span className="num text-[12px] text-ink">docs/EXP-002-FAC.png</span>, <span className="num text-[12px] text-ink">EXP-002-TC.png</span> y <span className="num text-[12px] text-ink">EXP-002-POL.png</span> como documentos.</li>
              <li><span className="num text-[12px] text-ink">fotos/FOTO-002.png</span> como foto.</li>
            </ul>
            <p>Resultado esperado: un Volkswagen Jetta 2017 con una <strong className="text-alta">alerta alta</strong> (el VIN de la tarjeta no coincide con factura y póliza), dos daños y su prima explicada.</p>
            <p>EXP-001 (+ FOTO-001, Nissan Versa 2019) es un caso limpio para comparar. Después, prueba el <Link to="/app/siniestro" className="text-taupe underline underline-offset-2">dictamen de siniestro</Link> con FOTO-002.</p>
          </div>
        </aside>
      </form>
    </div>
  );
}
