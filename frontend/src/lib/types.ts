// Tipos del contrato de la API FastAPI (autoguard/api/main.py, autoguard/api/dictamen.py,
// autoguard/contracts.py). No inventar campos: si la API cambia, actualizar aquí.

export type Severidad = "info" | "media" | "alta";
export type Uso = "particular" | "app_transporte" | "comercial";
export type Zona = "CDMX" | "EDOMEX" | "JAL" | "NL" | "PUE" | "OTRA";
export type TipoDocumento = "factura" | "tarjeta_circulacion" | "poliza_anterior" | "otro";

export interface Alerta { codigo: string; severidad: Severidad; detalle: string; fuentes: string[] }
export interface Dano { zona: string; tipo: string; costo_est: number; confianza: number }

export interface VehicleProfile {
  id: string; marca: string; modelo: string; anio: number; kilometraje: number; siniestros_previos: number;
  uso: Uso; zona: Zona; danos: Dano[]; alertas: Alerta[]; cobertura_verificacion: number;
  vin: string | null; placas: string | null;
}

export interface DocExtraction {
  documento_id: string; tipo: TipoDocumento; vin: string | null; placas: string | null; marca: string | null;
  modelo: string | null; anio: number | null; vigencia: string | null; campos_extra: Record<string, unknown>;
  confianza: number;
}

export interface QuoteOutput { prima: number; intervalo: [number, number]; factores: Record<string, number>; confianza: number }
export interface Prediction {
  prediction_id: string; vehicle_id: string; agent: string; agent_version: string; input_hash: string;
  output: QuoteOutput; created_at: string;
}

export interface Comparable {
  titulo?: string; precio: number; precio_ajustado: number; atipico: boolean; anio?: number; kilometraje?: number;
  url?: string; [k: string]: unknown;
}
export interface Valuacion {
  precio_estimado: number; rango: [number, number]; comparables: Comparable[]; fuente: string;
  precio_mercado: number; descuento_danos: number; n_comparables: number; simulado: boolean;
}

export interface ExpedienteResponse {
  vehicle_id: string; perfil: VehicleProfile; alertas: Alerta[]; documentos: DocExtraction[];
  cotizacion: Prediction; valuacion: Valuacion | null; omitidos: Record<string, string>; tiempo_ms: number; nota: string;
}
export interface VehicleResponse { perfil: VehicleProfile; documentos: DocExtraction[]; predicciones: Prediction[] }

export interface ConfigChange { op: "set" | "add_rule" | "remove_rule" | "add_factor"; path: string; value: unknown }
export type TipoParche = "ajuste_factor" | "nueva_variable" | "cambio_regla" | "cambio_prompt";
export interface Patch {
  patch_id: string; generation: number; agent: string; tipo: TipoParche; nivel: "parametros" | "estructura" | "codigo";
  hipotesis: string; segmento: Record<string, unknown>; cambios: ConfigChange[]; diff: string; metrica_objetivo: string;
  veredicto: "aceptado" | "rechazado" | "invalido" | null; metrics_before: Record<string, number>;
  metrics_after: Record<string, number>; razon: string;
}
export interface PatchesResponse { fuente: "db" | "run"; patches: Patch[] }

export interface AgentVersion {
  id: string; agent: string; parent_id: string | null; git_sha: string;
  estado: "campeon" | "retador" | "sombra" | "retirado"; metrics: Record<string, number>; created_at: string;
}
export interface VersionsResponse { agent: string; versions: AgentVersion[] }

export interface CurvePoint {
  variant: "estatico" | "parametros" | "rsi"; batch: number; polizas: number; loss: number; regret: number;
  vendidas: number; generation: number; loss_oraculo?: number; ratio_oraculo?: number;
}
export interface RunSummary {
  simulados: boolean; seed: number; batches: number; batch_size: number; k: number;
  regret: Record<"estatico" | "parametros" | "rsi", number>; mejora_rsi: number;
  convergencia_polizas: Record<string, number | null>; convergencia_meseta_polizas?: Record<string, number | null>;
  gate2: boolean; elapsed_seconds: number;
  referencia_oraculo?: { regret: number; multiplicador_cuantil: number; mejora_maxima_posible: number; fraccion_capturada_rsi: number | null };
  exceso_final_vs_oraculo?: Record<string, number>;
  [k: string]: unknown;
}
export interface RunLatest { run_id: string; summary: RunSummary; archivos: string[]; n_parches: number; curva?: CurvePoint[] }

export interface RsiJob { job_id: string; estado: string; params?: Record<string, number>; [k: string]: unknown }

export interface Health { ok: boolean; auth: boolean; llm: "mock" | "real" }

export type SeveridadDictamen = "limpio" | "revision" | "sospechoso";
export interface DictamenResult {
  vehicle_id: string; danos_reclamados: Dano[]; danos_preexistentes: Dano[]; danos_nuevos: Dano[];
  costo_siniestro_est: number; costo_preexistente_coincidente: number; banderas: Alerta[];
  severidad: SeveridadDictamen; explicacion: string[]; simulados: boolean;
}
