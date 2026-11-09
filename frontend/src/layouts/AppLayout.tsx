// Layout de la app: barra lateral (como la maqueta de la referencia) + barra superior con estado de la API.
import { NavLink, Outlet } from "react-router-dom";
import { Dot, Logo, SimBadge, useAsync } from "../components/ui";
import { api, API_URL } from "../lib/api";

const NAV = [
  { to: "/app", label: "Resumen", end: true },
  { to: "/app/expediente/nuevo", label: "Nuevo expediente" },
  { to: "/app/siniestro", label: "Dictamen de siniestro" },
  { to: "/app/laboratorio", label: "Laboratorio RSI" },
  { to: "/app/parches", label: "Bitácora de parches" },
  { to: "/app/versiones", label: "Versiones" },
];

function ApiStatus() {
  const { data, error, loading } = useAsync(() => api.health(), []);
  const tone = loading ? "warn" : error ? "alta" : "ok";
  const text = loading ? "Conectando…" : error ? "API sin conexión" : `API local · LLM ${data?.llm === "real" ? "real" : "simulado"}`;
  return (
    <span className="inline-flex items-center gap-2 text-[13px] text-muted" title={API_URL}>
      <Dot tone={tone} />
      {text}
    </span>
  );
}

export default function AppLayout() {
  return (
    <div className="min-h-screen bg-paper">
      <header className="sticky top-0 z-30 border-b border-line bg-paper/90 backdrop-blur">
        <div className="flex items-center gap-4 px-5 py-3">
          <Logo />
          <span className="hidden text-faint sm:inline">/</span>
          <span className="hidden text-[14px] text-muted sm:inline">app</span>
          <div className="ml-auto flex items-center gap-4">
            <ApiStatus />
            <SimBadge />
          </div>
        </div>
      </header>
      <div className="flex">
        <aside className="sticky top-[53px] hidden h-[calc(100vh-53px)] w-60 shrink-0 border-r border-line px-3 py-5 md:block">
          <nav className="flex flex-col gap-1" aria-label="Secciones de la app">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.end}
                className={({ isActive }) =>
                  `rounded-lg px-3 py-2 text-[15px] transition ${isActive ? "bg-cream font-medium text-ink" : "text-muted hover:bg-cream/60 hover:text-ink"}`
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
          <p className="mt-8 px-3 text-[12px] leading-relaxed text-faint">
            Prototipo local. Las primas no son una oferta real.
          </p>
        </aside>
        <div className="min-w-0 flex-1">
          <nav className="flex gap-1 overflow-x-auto border-b border-line px-3 py-2 md:hidden" aria-label="Secciones">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end}
                className={({ isActive }) => `shrink-0 rounded-lg px-3 py-1.5 text-[14px] ${isActive ? "bg-cream font-medium" : "text-muted"}`}>
                {n.label}
              </NavLink>
            ))}
          </nav>
          <main className="mx-auto w-full max-w-[1100px] px-5 py-8 md:px-8">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
