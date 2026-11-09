import { Navigate, Route, Routes } from "react-router-dom";
import AppLayout from "./layouts/AppLayout";
import Landing from "./pages/Landing";
import Resumen from "./pages/Resumen";
import NuevoExpediente from "./pages/NuevoExpediente";
import Expediente from "./pages/Expediente";
import Siniestro from "./pages/Siniestro";
import Laboratorio from "./pages/Laboratorio";
import Parches from "./pages/Parches";
import Versiones from "./pages/Versiones";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/app" element={<AppLayout />}>
        <Route index element={<Resumen />} />
        <Route path="expediente/nuevo" element={<NuevoExpediente />} />
        <Route path="expediente/:vehicleId" element={<Expediente />} />
        <Route path="siniestro" element={<Siniestro />} />
        <Route path="laboratorio" element={<Laboratorio />} />
        <Route path="parches" element={<Parches />} />
        <Route path="versiones" element={<Versiones />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
