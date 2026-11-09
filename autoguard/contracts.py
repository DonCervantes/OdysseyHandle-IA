"""Contratos JSON compartidos (Pydantic v2).

FUENTE DE VERDAD de las interfaces entre módulos. Cambiar un contrato rompe a otras
tareas: hazlo solo con una tarea dedicada o avisando en las notas de la tarea.
Todos los datos de la demo son SIMULADOS.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- vehículo
Uso = Literal["particular", "app_transporte", "comercial"]
Zona = Literal["CDMX", "EDOMEX", "JAL", "NL", "PUE", "OTRA"]


class Dano(BaseModel):
    zona: str  # p.ej. "defensa_trasera"
    tipo: str  # "rayon" | "abolladura" | "reparacion" | "reemplazo" | ...
    costo_est: float = Field(ge=0)
    confianza: float = Field(ge=0, le=1)


class Alerta(BaseModel):
    codigo: str  # p.ej. "VIN_NO_COINCIDE"
    severidad: Literal["info", "media", "alta"]
    detalle: str
    fuentes: list[str] = []


class VehicleProfile(BaseModel):
    id: str
    marca: str
    modelo: str
    anio: int
    kilometraje: int = Field(ge=0)
    siniestros_previos: int = Field(ge=0)
    uso: Uso = "particular"
    zona: Zona = "CDMX"
    danos: list[Dano] = []
    alertas: list[Alerta] = []
    cobertura_verificacion: float = Field(default=1.0, ge=0, le=1)
    vin: Optional[str] = None
    placas: Optional[str] = None

    @property
    def danos_costo(self) -> float:
        return float(sum(d.costo_est for d in self.danos))


# Columnas planas de un vehículo en DataFrames (simulador, recolector, evaluador).
VEHICLE_COLUMNS = [
    "vehicle_id", "marca", "modelo", "anio", "kilometraje", "siniestros_previos",
    "uso", "zona", "danos_costo", "cobertura_verificacion",
]

# Variables que el cotizador PUEDE usar (lista blanca). Atributos sensibles prohibidos.
VARIABLES_PERMITIDAS = [
    "marca", "modelo", "antiguedad", "anio", "kilometraje", "siniestros_previos",
    "uso", "zona", "danos_costo", "cobertura_verificacion",
]
VARIABLES_PROHIBIDAS = ["genero", "edad", "edad_conductor", "estado_civil", "religion", "etnia", "cp_ingreso"]


# ---------------------------------------------------------------- documentos
TipoDocumento = Literal["factura", "tarjeta_circulacion", "poliza_anterior", "otro"]


class DocExtraction(BaseModel):
    documento_id: str
    tipo: TipoDocumento
    vin: Optional[str] = None
    placas: Optional[str] = None
    marca: Optional[str] = None
    modelo: Optional[str] = None
    anio: Optional[int] = None
    vigencia: Optional[str] = None  # ISO date
    campos_extra: dict[str, Any] = {}
    confianza: float = Field(default=1.0, ge=0, le=1)


# ---------------------------------------------------------------- predicción
class QuoteOutput(BaseModel):
    prima: float = Field(ge=0)
    intervalo: tuple[float, float]
    factores: dict[str, float]  # nombre -> multiplicador aplicado (explicabilidad)
    confianza: float = Field(default=0.8, ge=0, le=1)


class Prediction(BaseModel):
    prediction_id: str
    vehicle_id: str
    agent: str = "cotizador"
    agent_version: str  # "cotizador@<git_sha[:7]>"
    input_hash: str
    output: QuoteOutput
    created_at: datetime = Field(default_factory=utcnow)


class Outcome(BaseModel):
    outcome_id: str
    prediction_id: str
    fuente: Literal["taller", "venta", "siniestro", "simulador"]
    valor: dict[str, Any]  # simulador: {"vendida": bool, "costo_real": float}
    observed_at: datetime = Field(default_factory=utcnow)


# ---------------------------------------------------------------- RSI
# Brazos del meta-mejorador = tipos de parche
TipoParche = Literal["ajuste_factor", "nueva_variable", "cambio_regla", "cambio_prompt"]
ARMS: list[str] = ["ajuste_factor", "nueva_variable", "cambio_regla", "cambio_prompt"]


class Segment(BaseModel):
    """Segmento como dict de condiciones: `<var>` igualdad, `<var>_min` >=, `<var>_max` <=.
    Ver autoguard/segments.py."""
    condiciones: dict[str, Any]


class Hypothesis(BaseModel):
    segmento: dict[str, Any]
    n: int
    sesgo_medio: float  # media de (prima - costo)/costo; >0 sobrecotiza, <0 subcotiza
    p_value: float
    impacto: float  # pérdida atribuible al segmento (mayor = más prioritario)
    texto: str  # hipótesis en lenguaje natural


class ConfigChange(BaseModel):
    """Cambio aplicable a CotizadorConfig. op:
    - "set": asigna `value` en `path` (ruta con puntos, p.ej. "factores.uso.categorias.app_transporte")
    - "add_rule": agrega `value` (dict compatible con Regla) a `reglas`
    - "remove_rule": elimina la regla con id == value
    - "add_factor": agrega `value` (dict compatible con Factor) en factores[path]
    """
    op: Literal["set", "add_rule", "remove_rule", "add_factor"]
    path: str = ""
    value: Any = None


class Patch(BaseModel):
    patch_id: str
    generation: int
    agent: str = "cotizador"
    tipo: TipoParche
    nivel: Literal["parametros", "estructura", "codigo"] = "parametros"
    hipotesis: str
    segmento: dict[str, Any] = {}
    cambios: list[ConfigChange]
    diff: str = ""  # legible para humanos, p.ej. "factores.siniestros_previos.valores[1]: 1.12 -> 1.04"
    metrica_objetivo: str = "loss_asimetrica"
    veredicto: Optional[Literal["aceptado", "rechazado", "invalido"]] = None
    metrics_before: dict[str, float] = {}
    metrics_after: dict[str, float] = {}
    razon: str = ""


class Verdict(BaseModel):
    patch_id: str
    aceptado: bool
    loss_before: float
    loss_after: float
    ganancia: float  # (loss_before - loss_after) / loss_before
    peor_segmento: Optional[dict[str, Any]] = None
    peor_delta: float = 0.0  # empeoramiento relativo máximo por segmento
    razones: list[str] = []


class AgentVersion(BaseModel):
    id: str
    agent: str
    parent_id: Optional[str] = None
    git_sha: str
    estado: Literal["campeon", "retador", "sombra", "retirado"]
    metrics: dict[str, float] = {}
    created_at: datetime = Field(default_factory=utcnow)


class MetaStrategy(BaseModel):
    generation: int
    arms: dict[str, tuple[float, float]]  # brazo -> (alpha, beta) de la Beta posterior
    lecciones: str = ""
    tasa_aceptacion: float = 0.0
    ganancia_media: float = 0.0


Variant = Literal["estatico", "parametros", "rsi"]
