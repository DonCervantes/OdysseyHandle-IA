// Formatos es-MX. Montos en MXN, porcentajes con 0–1 decimales.
const mxn = new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN", maximumFractionDigits: 0 });
const num = new Intl.NumberFormat("es-MX");

export const fmtMXN = (v: number | null | undefined) => (v == null || Number.isNaN(v) ? "—" : mxn.format(v));
export const fmtNum = (v: number | null | undefined) => (v == null || Number.isNaN(v) ? "—" : num.format(v));
export const fmtPct = (v: number | null | undefined, digits = 1) =>
  v == null || Number.isNaN(v) ? "—" : `${(v * 100).toFixed(digits).replace(/\.0$/, "")}%`;
export const fmtSignedPct = (v: number | null | undefined, digits = 1) =>
  v == null || Number.isNaN(v) ? "—" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v * 100).toFixed(digits)}%`;
/** Millones de MXN compactos: 51.31M */
export const fmtMillones = (v: number | null | undefined, digits = 2) =>
  v == null || Number.isNaN(v) ? "—" : `${(v / 1e6).toFixed(digits)}M`;
export const fmtFecha = (iso: string | null | undefined) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("es-MX", { dateStyle: "medium", timeStyle: "short" });
};
export const fmtMult = (v: number) => `×${v.toFixed(2)}`;
export const shortSha = (sha: string) => sha.slice(0, 7);

/** Nombres legibles de factores del cotizador y códigos de alerta. */
export const FACTOR_LABEL: Record<string, string> = {
  antiguedad: "Antigüedad",
  kilometraje: "Kilometraje",
  siniestros_previos: "Siniestros previos",
  uso: "Uso del vehículo",
  zona: "Zona",
  marca: "Marca",
  danos_costo: "Daños preexistentes",
  cobertura_verificacion: "Cobertura de verificación",
  modelo: "Modelo",
};
export const labelFactor = (k: string) =>
  k.startsWith("regla:") ? `Regla ${k.slice(6)}` : FACTOR_LABEL[k] || k;

export const ALERTA_LABEL: Record<string, string> = {
  VIN_FORMATO_INVALIDO: "El VIN no tiene un formato válido",
  VIN_DIGITO_VERIFICADOR: "El dígito verificador del VIN no cuadra",
  VIN_NO_COINCIDE: "El VIN no coincide entre documentos",
  PLACAS_NO_COINCIDEN: "Las placas no coinciden entre documentos",
  MARCA_NO_COINCIDE: "La marca no coincide entre documentos",
  MODELO_NO_COINCIDE: "El modelo no coincide entre documentos",
  ANIO_NO_COINCIDE: "El año no coincide entre documentos",
  VIGENCIA_ILEGIBLE: "No se pudo leer la vigencia",
  DOCUMENTO_VENCIDO: "Hay un documento vencido",
  DOCUMENTO_FALTANTE: "Falta un documento",
  BAJA_CONFIANZA: "Lectura de baja confianza",
  DATO_DECLARADO_NO_COINCIDE: "Un dato declarado no coincide con los documentos",
  DATOS_INCOMPLETOS: "Datos incompletos",
  // dictamen de siniestros
  DANO_PREEXISTENTE_RECLAMADO: "Se reclama un daño que ya estaba registrado",
  ZONA_INCOMPATIBLE: "La zona del daño no coincide con el relato",
  MONTO_ATIPICO: "El monto declarado es atípico para los daños detectados",
  SIN_DANOS_DETECTADOS: "No se detectaron daños en las fotos",
  SOLO_PREEXISTENTES: "Solo hay daños que ya estaban registrados",
};
export const labelAlerta = (codigo: string) => ALERTA_LABEL[codigo] || codigo;

export const TIPO_PARCHE_LABEL: Record<string, string> = {
  ajuste_factor: "Ajuste de factor",
  nueva_variable: "Variable nueva",
  cambio_regla: "Regla por segmento",
  cambio_prompt: "Control (explicación)",
};
export const VARIANTE_LABEL: Record<string, string> = {
  estatico: "Reglas fijas",
  parametros: "Solo parámetros",
  rsi: "Auto-mejora completa",
};
export const USO_LABEL: Record<string, string> = { particular: "Particular", app_transporte: "App de transporte", comercial: "Comercial" };
