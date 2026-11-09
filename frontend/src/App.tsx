import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import AppLayout from "./layouts/AppLayout";
import Landing from "./pages/Landing";
import { Skeleton } from "./components/ui";

// Pantallas de la app con carga diferida: las gráficas (recharts) no se descargan en la landing.
const Resumen = lazy(() => import("./pages/Resumen"));
const NuevoExpediente = lazy(() => import("./pages/NuevoExpediente"));
const Expediente = lazy(() => import("./pages/Expediente"));
const Siniestro = lazy(() => import("./pages/Siniestro"));
const Laboratorio = lazy(() => import("./pages/Laboratorio"));
const Parches = lazy(() => import("./pages/Parches"));
const Versiones = lazy(() => import("./pages/Versiones"));

function Cargando() {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Cargando">
      <Skeleton className="h-10 w-1/2" />
      <Skeleton className="h-40" />
    </div>
  );
}

const page = (el: JSX.Element) => <Suspense fallback={<Cargando />}>{el}</Suspense>;

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/app" element={<AppLayout />}>
        <Route index element={page(<Resumen />)} />
        <Route path="expediente/nuevo" element={page(<NuevoExpediente />)} />
        <Route path="expediente/:vehicleId" element={page(<Expediente />)} />
        <Route path="siniestro" element={page(<Siniestro />)} />
        <Route path="laboratorio" element={page(<Laboratorio />)} />
        <Route path="parches" element={page(<Parches />)} />
        <Route path="versiones" element={page(<Versiones />)} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
