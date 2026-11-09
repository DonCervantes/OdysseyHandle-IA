// Construcción EXACTA de los multipart de POST /expedientes y POST /dictamen/expediente.
// Nunca se fija Content-Type: el navegador agrega el boundary.
import type { TipoDocumento } from "../../lib/types";

export type TipoElegido = TipoDocumento | "";

export interface DatosDeclarados {
  kilometraje: string;
  siniestros_previos: string;
  uso: string;
  zona: string;
}

/** Objeto `datos` sin llaves vacías (los enteros como número). */
export function datosLimpios(d: DatosDeclarados): Record<string, string | number> {
  const out: Record<string, string | number> = {};
  if (d.kilometraje.trim() !== "") out.kilometraje = Number(d.kilometraje);
  if (d.siniestros_previos.trim() !== "") out.siniestros_previos = Number(d.siniestros_previos);
  if (d.uso) out.uso = d.uso;
  if (d.zona) out.zona = d.zona;
  return out;
}

export function formExpediente(
  docs: { file: File; tipo: TipoElegido }[],
  fotos: File[],
  datos: DatosDeclarados,
  vehicleId: string,
): FormData {
  const fd = new FormData();
  docs.forEach((d) => fd.append("docs", d.file));
  fotos.forEach((f) => fd.append("fotos", f));
  // "tipos" solo si TODOS los documentos tienen tipo elegido (la API exige el mismo largo que docs).
  if (docs.length > 0 && docs.every((d) => d.tipo !== "")) docs.forEach((d) => fd.append("tipos", d.tipo));
  fd.append("datos", JSON.stringify(datosLimpios(datos)));
  if (vehicleId.trim()) fd.append("vehicle_id", vehicleId.trim());
  return fd;
}

export function formDictamen(fotos: File[], vehicleId: string, zonas: string[], monto: string): FormData {
  const fd = new FormData();
  fotos.forEach((f) => fd.append("fotos", f));
  fd.append("vehicle_id", vehicleId.trim());
  fd.append("relato_zonas", JSON.stringify(zonas)); // la API espera una lista JSON en un solo campo
  const m = Number(monto.replace(/,/g, "").trim());
  if (monto.trim() !== "" && Number.isFinite(m)) fd.append("monto_declarado", String(m));
  return fd;
}
