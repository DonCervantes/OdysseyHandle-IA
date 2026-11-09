// Formulario para lanzar una corrida RSI y sondear su estado cada 3 s.
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "../../lib/api";
import type { RsiJob } from "../../lib/types";
import { Dot } from "../ui";

const JOB_KEY = "rsi:job";
const leerJob = () => { try { return sessionStorage.getItem(JOB_KEY); } catch { return null; } };
const guardarJob = (id: string | null) => {
  try { if (id) sessionStorage.setItem(JOB_KEY, id); else sessionStorage.removeItem(JOB_KEY); } catch { /* sin storage */ }
};

type Campos = { seed: string; batches: string; batch_size: string; k: string };
const DEFAULTS: Campos = { seed: "42", batches: "60", batch_size: "200", k: "3" };
const CAMPOS: { key: keyof Campos; label: string; min: number; max: number; hint: string }[] = [
  { key: "seed", label: "Semilla", min: 0, max: 2 ** 31 - 1, hint: "reproducible" },
  { key: "batches", label: "Lotes", min: 1, max: 10000, hint: "default 60" },
  { key: "batch_size", label: "Pólizas por lote", min: 1, max: 100000, hint: "default 200" },
  { key: "k", label: "Parches por generación (k)", min: 1, max: 1000, hint: "default 3" },
];

export default function RunPanel({ onDone, onToast }: { onDone: () => void; onToast: (m: string, t?: "ok" | "alta") => void }) {
  const [abierto, setAbierto] = useState(false);
  const [campos, setCampos] = useState<Campos>(DEFAULTS);
  const [job, setJob] = useState<RsiJob | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ahora, setAhora] = useState(Date.now());
  const timer = useRef<number | null>(null);

  const corriendo = job?.estado === "corriendo";

  // retoma un job lanzado antes de recargar/navegar
  useEffect(() => {
    const id = leerJob();
    if (id) api.estadoRsi(id).then(setJob, () => guardarJob(null));
  }, []);

  useEffect(() => {
    if (!job || job.estado !== "corriendo") return;
    const id = job.job_id;
    timer.current = window.setInterval(async () => {
      setAhora(Date.now());
      try {
        const st = await api.estadoRsi(id);
        setJob(st);
        if (st.estado !== "corriendo") {
          guardarJob(null);
          if (st.estado === "terminado") { onToast("Corrida terminada. Se cargó la nueva curva."); onDone(); }
          else onToast(`La corrida terminó con error (código ${String(st.returncode ?? "?")}). Revisa el log: ${String(st.log ?? "")}`, "alta");
        }
      } catch (e) {
        guardarJob(null);
        setJob(null);
        onToast(e instanceof Error ? e.message : String(e), "alta");
      }
    }, 3000);
    return () => { if (timer.current) window.clearInterval(timer.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.job_id, job?.estado]);

  const invalido = CAMPOS.find((c) => {
    const n = Number(campos[c.key]);
    return campos[c.key].trim() === "" || !Number.isInteger(n) || n < c.min || n > c.max;
  });

  async function lanzar(e: FormEvent) {
    e.preventDefault();
    if (invalido) return;
    setEnviando(true);
    setErr(null);
    try {
      const st = await api.correrRsi({
        seed: Number(campos.seed), batches: Number(campos.batches), batch_size: Number(campos.batch_size), k: Number(campos.k),
      });
      setJob(st);
      setAhora(Date.now());
      guardarJob(st.job_id);
      setAbierto(false);
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : String(e2));
    } finally {
      setEnviando(false);
    }
  }

  const inicio = typeof job?.inicio === "number" ? job.inicio * 1000 : null;
  const transcurrido = inicio ? Math.max(0, Math.round((ahora - inicio) / 1000)) : null;

  return (
    <div className="space-y-3">
      {corriendo ? (
        <div className="card-cream flex flex-wrap items-center gap-3 px-4 py-3 text-[14px]" role="status" aria-live="polite">
          <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-warn opacity-60" /><Dot tone="warn" /></span>
          <span className="font-medium">Corrida en curso</span>
          <span className="font-mono text-[12px] text-muted">{job?.job_id}</span>
          {transcurrido != null && <span className="num text-muted">{Math.floor(transcurrido / 60)}:{String(transcurrido % 60).padStart(2, "0")} min</span>}
          <span className="text-muted">Se consulta el estado cada 3 s; puedes seguir navegando.</span>
        </div>
      ) : (
        <button type="button" className="btn-primary btn-sm" onClick={() => setAbierto((v) => !v)} aria-expanded={abierto} aria-controls="rsi-form">
          {abierto ? "Cerrar" : "Correr nueva corrida"}
        </button>
      )}

      {abierto && !corriendo && (
        <form id="rsi-form" onSubmit={lanzar} className="card space-y-4 p-4 sm:p-5">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {CAMPOS.map((c) => (
              <div key={c.key}>
                <label className="label" htmlFor={`rsi-${c.key}`}>{c.label}</label>
                <input id={`rsi-${c.key}`} type="number" inputMode="numeric" min={c.min} max={c.max} className="input num"
                  value={campos[c.key]} onChange={(e) => setCampos((s) => ({ ...s, [c.key]: e.target.value }))} />
                <div className="mt-1 text-[12px] text-faint">{c.hint}</div>
              </div>
            ))}
          </div>
          <p className="text-[13px] text-warn">
            Con los valores por defecto la corrida tarda ~2 minutos (modo simulado). Al terminar se convierte en la “última corrida”.
          </p>
          {invalido && <p className="text-[13px] text-alta">Revisa “{invalido.label}”: entero entre {invalido.min} y {fmtMax(invalido.max)}.</p>}
          {err && <p className="text-[13px] text-alta" role="alert">{err}</p>}
          <div className="flex flex-wrap gap-2">
            <button type="submit" className="btn-primary btn-sm" disabled={enviando || !!invalido}>{enviando ? "Lanzando…" : "Lanzar corrida"}</button>
            <button type="button" className="btn-ghost btn-sm" onClick={() => setCampos(DEFAULTS)}>Restaurar valores</button>
          </div>
        </form>
      )}
    </div>
  );
}

const fmtMax = (n: number) => n.toLocaleString("es-MX");
