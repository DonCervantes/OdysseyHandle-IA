// Landing de AutoGuard AI: narrativa para México. Estática (no llama a la API).
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Logo, Source } from "../components/ui";
import { DATOS_MEXICO } from "../data/mexico";
import { fmtMXN } from "../lib/format";
import ProductMockup from "../landing/ProductMockup";
import Results from "../landing/Results";

const NAV = [
  { href: "#producto", label: "Producto" },
  { href: "#como-funciona", label: "Cómo funciona" },
  { href: "#resultados", label: "Resultados" },
  { href: "#seguridad", label: "Seguridad" },
  { href: "#faq", label: "FAQ" },
];

function Section({ id, eyebrow, title, intro, children, className = "" }: {
  id: string; eyebrow: string; title: ReactNode; intro?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section id={id} className={`scroll-mt-20 py-20 sm:py-28 ${className}`} aria-labelledby={`${id}-t`}>
      <div className="wrap">
        <div className="max-w-2xl">
          <div className="eyebrow">{eyebrow}</div>
          <h2 id={`${id}-t`} className="mt-3 text-[32px] font-semibold leading-[1.08] tracking-tight sm:text-[44px]">{title}</h2>
          {intro && <p className="mt-4 text-[17px] leading-relaxed text-muted">{intro}</p>}
        </div>
        <div className="mt-12">{children}</div>
      </div>
    </section>
  );
}

function Header() {
  const [open, setOpen] = useState(false);
  return (
    <header className="sticky top-0 z-30 border-b border-transparent bg-paper/85 backdrop-blur supports-[backdrop-filter]:bg-paper/70">
      <div className="wrap flex h-16 items-center justify-between gap-4">
        <Logo />
        <nav aria-label="Secciones" className="hidden items-center gap-8 md:flex">
          {NAV.map((n) => (
            <a key={n.href} href={n.href} className="rounded text-[15px] text-muted transition hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-taupe">
              {n.label}
            </a>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          <Link to="/app" className="btn-primary btn-sm">Abrir la app</Link>
          <button
            type="button"
            className="btn-ghost btn-sm md:hidden"
            aria-expanded={open}
            aria-controls="menu-movil"
            onClick={() => setOpen((v) => !v)}
          >
            {open ? "Cerrar" : "Menú"}
          </button>
        </div>
      </div>
      {open && (
        <nav id="menu-movil" aria-label="Secciones" className="wrap border-t border-line pb-4 md:hidden">
          {NAV.map((n) => (
            <a key={n.href} href={n.href} onClick={() => setOpen(false)} className="block py-3 text-[16px] text-ink">
              {n.label}
            </a>
          ))}
        </nav>
      )}
    </header>
  );
}

function Hero() {
  return (
    <section id="producto" className="relative scroll-mt-20 overflow-hidden pb-20 pt-12 sm:pb-28 sm:pt-16">
      {/* halo cálido, sin sombras duras */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute left-1/2 top-0 -z-10 h-[620px] w-[1100px] -translate-x-1/2 rounded-full opacity-70"
        style={{ background: "radial-gradient(closest-side, rgb(var(--cream)), transparent)" }}
      />
      <div className="wrap text-center">
        <span className="chip">
          <span aria-hidden="true" className="h-1.5 w-1.5 shrink-0 rounded-full bg-sand" />
          <span>Hecho para <span className="hidden sm:inline">seminuevos en </span>México · datos simulados</span>
        </span>
        <h1 className="mx-auto mt-8 max-w-5xl text-[44px] font-bold leading-[1.02] tracking-[-0.035em] sm:text-[68px] lg:text-[88px]">
          Asegurar un seminuevo, <span className="text-gradient">sin adivinar.</span>
        </h1>
        <p className="mx-auto mt-7 max-w-2xl text-[18px] leading-relaxed text-muted sm:text-[21px]">
          Agentes de IA que revisan documentos y fotos, valúan el auto y cotizan su seguro con factores que puedes leer.
          El cotizador aprende solo, bajo un evaluador que no puede tocar.
        </p>
        <div className="mt-10 flex flex-col items-stretch justify-center gap-3 sm:flex-row sm:items-center">
          <Link to="/app/expediente/nuevo" className="btn-primary px-7 py-4 text-[17px]">Probar la app →</Link>
          <a href="#como-funciona" className="btn-ghost px-7 py-4 text-[17px]">Ver cómo funciona</a>
        </div>
      </div>
      <div className="wrap mt-16 sm:mt-20">
        <ProductMockup />
      </div>
    </section>
  );
}

function Problema() {
  return (
    <Section
      id="problema"
      eyebrow="El problema en México"
      title="Comprar un auto usado es fácil. Saber qué estás asegurando, no."
      intro="Documentos que no cuadran, daños que nadie anotó y primas calculadas con tablas de hace años. Estas son las cifras públicas con las que partimos."
      className="border-t border-line"
    >
      <div className="grid gap-x-10 sm:grid-cols-2 lg:grid-cols-3">
        {DATOS_MEXICO.map((d) => (
          <article key={d.id} className="flex flex-col border-t border-line pb-12 pt-7">
            <div className="text-[40px] font-semibold leading-none tracking-tight sm:text-[48px]">{d.valor}</div>
            <h3 className="mt-3 text-[18px] font-medium text-ink">{d.titulo}</h3>
            <p className="mt-2 flex-1 text-[15px] leading-relaxed text-muted">{d.detalle}</p>
            <div className="mt-5">
              <Source href={d.url}>Fuente: {d.fuente}{d.origen ? ` con datos de ${d.origen}` : ""} · {d.fecha}</Source>
            </div>
          </article>
        ))}
      </div>
    </Section>
  );
}

const AGENTES = [
  { n: "01", nombre: "Documental", hace: "Lee factura, tarjeta de circulación y póliza. Cruza VIN, placas, marca y año entre documentos.", ej: "VIN de factura ≠ VIN de tarjeta → alerta alta" },
  { n: "02", nombre: "Visual", hace: "Revisa las fotos, ubica daños y estima el costo de reacondicionamiento.", ej: `Espejo estrellado ${fmtMXN(900)} + rayón en puerta ${fmtMXN(1900)}` },
  { n: "03", nombre: "Valuación", hace: "Compara contra autos similares y ajusta por kilometraje y daños.", ej: `Jetta 2017 con 60,000 km declarados: ${fmtMXN(127876)} con 8 comparables` },
  { n: "04", nombre: "Cotizador", hace: "Calcula la prima con factores explicables, uno por uno.", ej: `${fmtMXN(9000)} base × zona CDMX 1.10 = ${fmtMXN(9900)}` },
];

const RSI = [
  { nombre: "Recolector", hace: "Junta lotes de pólizas y su siniestralidad simulada." },
  { nombre: "Analista", hace: "Busca segmentos donde el cotizador cobra de más o de menos." },
  { nombre: "Mejorador", hace: "Propone un parche: un factor, una variable o una regla." },
  { nombre: "Evaluador congelado", hace: "Acepta solo si mejora ≥1% en el holdout y ningún segmento empeora más de 5%.", frozen: true },
  { nombre: "Linaje", hace: "Cada versión aceptada queda en Git, con su diff y su razón." },
  { nombre: "Meta", hace: "Ajusta qué buscar en la siguiente vuelta, sin tocar el evaluador." },
];

function ComoFunciona() {
  return (
    <Section
      id="como-funciona"
      eyebrow="Cómo funciona"
      title="Cuatro agentes por expediente. Un ciclo que mejora al cotizador."
      intro="Subes documentos y fotos; en unos segundos (de 1 a 6 s en nuestras pruebas) tienes el perfil del auto, sus alertas, su valor y una prima explicada."
      className="border-t border-line"
    >
      <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {AGENTES.map((a) => (
          <li key={a.n} className="card flex flex-col p-6">
            <div className="num text-[13px] text-faint">{a.n}</div>
            <h3 className="mt-3 text-[20px] font-semibold">{a.nombre}</h3>
            <p className="mt-2 flex-1 text-[15px] leading-relaxed text-muted">{a.hace}</p>
            <div className="mt-5 rounded-lg bg-cream px-3 py-2 text-[13px] text-muted">{a.ej}</div>
          </li>
        ))}
      </ol>

      <div className="mt-20">
        <h3 className="text-[24px] font-semibold tracking-tight sm:text-[28px]">El ciclo de auto-mejora (RSI)</h3>
        <p className="mt-2 max-w-2xl text-[16px] leading-relaxed text-muted">
          Seis etapas. Cinco pueden cambiar. Una no: el evaluador que decide si un cambio entra.
        </p>
        <ol className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {RSI.map((r, i) => (
            <li
              key={r.nombre}
              className={`relative rounded-xl2 border p-5 ${r.frozen ? "border-ink bg-ink text-paper" : "border-line bg-panel"}`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className={`num text-[12px] ${r.frozen ? "text-sand" : "text-faint"}`}>{String(i + 1).padStart(2, "0")}</span>
                {r.frozen && (
                  <span className="rounded-full border border-sand/40 px-2.5 py-0.5 text-[10px] uppercase tracking-[0.06em] text-sand sm:text-[11px] sm:tracking-[0.12em]">
                    Límite que el sistema no puede tocar
                  </span>
                )}
              </div>
              <h4 className="mt-3 text-[18px] font-semibold">{r.nombre}</h4>
              <p className={`mt-1.5 text-[14px] leading-relaxed ${r.frozen ? "text-paper/75" : "text-muted"}`}>{r.hace}</p>
            </li>
          ))}
        </ol>
        <p className="mt-5 text-[14px] text-faint">
          Pérdida asimétrica: cobrar de menos cuesta 1.5×; cobrar de más, 1×. Así el sistema no “gana” bajando primas.
        </p>
      </div>
    </Section>
  );
}

const SEGURIDAD = [
  { t: "Evaluador congelado", d: "El código que juzga los parches vive fuera del alcance del RSI. Sus umbrales son fijos." },
  { t: "Lista blanca de variables", d: "Marca, modelo, antigüedad, km, siniestros, uso, zona y daños. Nunca género, edad ni datos personales." },
  { t: "Cada versión en Git", d: "Linaje completo del cotizador. Cualquier versión se revierte con un clic." },
  { t: "Trazabilidad por cotización", d: "Cada prima muestra qué factores la movieron y con qué versión del cotizador se calculó." },
  { t: "Datos simulados, sin llaves", d: "Funciona en local, en modo simulado y reproducible con semilla fija. Ninguna llave es obligatoria." },
];

function Seguridad() {
  return (
    <Section
      id="seguridad"
      eyebrow="Seguridad y equidad"
      title="Un sistema que se mejora solo necesita límites que no se muevan."
      className="border-t border-line"
    >
      <ul className="grid gap-x-10 gap-y-8 sm:grid-cols-2 lg:grid-cols-3">
        {SEGURIDAD.map((s) => (
          <li key={s.t} className="border-t border-line pt-5">
            <h3 className="text-[18px] font-semibold">{s.t}</h3>
            <p className="mt-2 text-[15px] leading-relaxed text-muted">{s.d}</p>
          </li>
        ))}
      </ul>
    </Section>
  );
}

const PERFILES = [
  { t: "Valuador", d: "Ve en un expediente qué documentos no cuadran y cuánto cuesta dejar el auto listo." },
  { t: "Cliente comprador", d: "Entiende por qué su prima es la que es, factor por factor." },
  { t: "Actuario", d: "Revisa parches, su efecto por segmento y aprueba o rechaza con razón." },
  { t: "Ajustador", d: "Recibe un dictamen preliminar del siniestro con los daños previos ya documentados." },
];

function ParaQuien() {
  return (
    <Section id="para-quien" eyebrow="Para quién" title="Una herramienta, cuatro lecturas." className="border-t border-line">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {PERFILES.map((p) => (
          <div key={p.t} className="card-cream p-6">
            <h3 className="text-[18px] font-semibold">{p.t}</h3>
            <p className="mt-2 text-[15px] leading-relaxed text-muted">{p.d}</p>
          </div>
        ))}
      </div>
    </Section>
  );
}

const FAQ: { q: string; a: ReactNode }[] = [
  { q: "¿Son datos reales?", a: "No. Autos, pólizas, siniestros y primas son simulados. Las únicas cifras reales son las públicas de México, y cada una cita su fuente." },
  { q: "¿Necesito llaves de API?", a: "No. Todo corre en modo simulado con resultados reproducibles. Si configuras una llave de LLM en tu .env local, los agentes la usan; si no, usan un modo determinístico." },
  {
    q: "¿Cómo lo corro?",
    a: (
      <>
        Desde la raíz del repo: <code className="num rounded bg-cream px-1.5 py-0.5 text-[13px]">bash scripts/demo.sh --start</code> levanta la API en :8000.
        Luego, en <code className="num rounded bg-cream px-1.5 py-0.5 text-[13px]">frontend/</code>:{" "}
        <code className="num rounded bg-cream px-1.5 py-0.5 text-[13px]">npm install && npm run dev</code> y abre localhost:5173.
      </>
    ),
  },
  { q: "¿El RSI puede hacer trampa?", a: "No puede modificar al evaluador ni sus umbrales: ese código está fuera de su alcance y se valida contra un holdout que no ve. Un parche entra solo si mejora ≥1% y ningún segmento empeora más de 5%." },
  { q: "¿Usa datos personales?", a: "No. El cotizador solo puede usar variables de una lista blanca sobre el auto y su uso. Género, edad y datos personales están fuera por diseño." },
  { q: "¿Qué falta para producción?", a: "Datos reales de siniestralidad, validación actuarial y regulatoria, integración con registros oficiales de vehículos, autenticación y monitoreo. Y cerrar la brecha entre el −26% a −29% medido y la meta del −40%." },
];

function Faq() {
  return (
    <Section id="faq" eyebrow="Preguntas frecuentes" title="Lo que nos preguntan." className="border-t border-line">
      <div className="max-w-3xl divide-y divide-line border-y border-line">
        {FAQ.map((f) => (
          <details key={f.q} className="group">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 py-5 text-[17px] font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-taupe [&::-webkit-details-marker]:hidden">
              {f.q}
              <span aria-hidden="true" className="text-[22px] font-light text-faint transition group-open:rotate-45">+</span>
            </summary>
            <div className="pb-6 pr-8 text-[15px] leading-relaxed text-muted">{f.a}</div>
          </details>
        ))}
      </div>
    </Section>
  );
}

function CtaFinal() {
  return (
    <section className="border-t border-line py-20 sm:py-28">
      <div className="wrap text-center">
        <h2 className="mx-auto max-w-3xl text-[36px] font-bold leading-[1.05] tracking-[-0.03em] sm:text-[56px]">
          Sube un expediente y <span className="text-gradient">compruébalo.</span>
        </h2>
        <p className="mx-auto mt-5 max-w-xl text-[17px] text-muted">Hay documentos y fotos de muestra en el repo. Tarda segundos.</p>
        <div className="mt-9 flex flex-col items-stretch justify-center gap-3 sm:flex-row sm:items-center">
          <Link to="/app/expediente/nuevo" className="btn-primary px-7 py-4 text-[17px]">Probar la app →</Link>
          <Link to="/app" className="btn-ghost px-7 py-4 text-[17px]">Ver el resumen</Link>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-line py-10">
      <div className="wrap flex flex-col items-start justify-between gap-4 text-[13px] text-faint sm:flex-row sm:items-center">
        <Logo />
        <p>AutoGuard AI · prototipo de hackathon · Datos simulados · las primas no son una oferta real</p>
      </div>
    </footer>
  );
}

export default function Landing() {
  return (
    <div className="min-h-screen overflow-x-clip bg-paper">
      <a href="#contenido"className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-ink focus:px-4 focus:py-2 focus:text-paper">
        Saltar al contenido
      </a>
      <Header />
      <main id="contenido" tabIndex={-1} className="focus:outline-none">
        <Hero />
        <Problema />
        <ComoFunciona />
        <Section
          id="resultados"
          eyebrow="Resultados medidos"
          title="Menos pérdida que las reglas fijas. Todavía no lo que queríamos."
          intro="Comparamos tres cotizadores sobre el mismo mercado simulado: reglas fijas, uno que solo ajusta parámetros y el ciclo de auto-mejora completo."
          className="border-t border-line"
        >
          <Results />
        </Section>
        <Seguridad />
        <ParaQuien />
        <Faq />
        <CtaFinal />
      </main>
      <Footer />
    </div>
  );
}
