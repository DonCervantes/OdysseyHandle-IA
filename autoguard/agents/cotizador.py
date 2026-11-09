"""Cotizador base explicable (T-04).

prima = base × Π factores × Π reglas que aplican.

- Factor numérico: multiplicador del último bin con límite ≤ x; si x < bins[0] o falta → `default`.
- Factor categórico: `categorias[str(x)]`, si no aparece → `default`.
- Factor sobre una columna ausente (o nula) → `default`.
- `antiguedad` = segments.ANIO_REFERENCIA - anio (si no viene como columna).
- Regla: multiplica si `segments.matches`; una regla sobre una columna ausente no aplica.
- Intervalo = prima × (1 ± intervalo_rel × (2 - cobertura_verificacion)), cota inferior ≥ 0.
- `factores` en la salida = cada multiplicador ≠ 1 aplicado, por nombre de factor y `regla:<id>`.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import numpy as np
import pandas as pd

from autoguard import segments
from autoguard.config_schema import CotizadorConfig, Factor
from autoguard.contracts import Prediction, QuoteOutput, VehicleProfile


# ---------------------------------------------------------------- utilidades
def profile_row(profile: VehicleProfile) -> dict[str, Any]:
    """Fila plana (VEHICLE_COLUMNS + antiguedad) de un perfil."""
    return {
        "vehicle_id": profile.id,
        "marca": profile.marca,
        "modelo": profile.modelo,
        "anio": profile.anio,
        "antiguedad": segments.ANIO_REFERENCIA - profile.anio,
        "kilometraje": profile.kilometraje,
        "siniestros_previos": profile.siniestros_previos,
        "uso": profile.uso,
        "zona": profile.zona,
        "danos_costo": profile.danos_costo,
        "cobertura_verificacion": profile.cobertura_verificacion,
    }


def profiles_df(profiles: list[VehicleProfile]) -> pd.DataFrame:
    return pd.DataFrame([profile_row(p) for p in profiles])


def _is_null(x: Any) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def _cat_key(x: Any) -> str:
    if isinstance(x, (float, np.floating)) and float(x).is_integer():
        return str(int(x))
    if isinstance(x, (np.integer,)):
        return str(int(x))
    return str(x)


def _factor_value(f: Factor, x: Any) -> float:
    if _is_null(x):
        return f.default
    if f.categorias is not None:
        return float(f.categorias.get(_cat_key(x), f.default))
    try:
        xv = float(x)
    except (TypeError, ValueError):
        return f.default
    idx = int(np.searchsorted(np.asarray(f.bins, dtype=float), xv, side="right")) - 1
    return float(f.valores[idx]) if idx >= 0 else f.default


def _confianza(cobertura: float) -> float:
    return float(min(1.0, max(0.0, 0.5 + 0.4 * cobertura)))


def _intervalo(prima: float, cfg: CotizadorConfig, cobertura: float) -> tuple[float, float]:
    rel = cfg.intervalo_rel * (2.0 - cobertura)
    return (max(0.0, prima * (1.0 - rel)), prima * (1.0 + rel))


# ---------------------------------------------------------------- API
def quote(profile: VehicleProfile, cfg: CotizadorConfig) -> QuoteOutput:
    """prima = base × Π factores × Π reglas que aplican; `factores` lista cada multiplicador aplicado."""
    row = profile_row(profile)
    prima = float(cfg.base)
    aplicados: dict[str, float] = {}
    for name, f in cfg.factores.items():
        m = _factor_value(f, row.get(f.variable))
        prima *= m
        if m != 1.0:
            aplicados[name] = m
    for r in cfg.reglas:
        if all(v in row for v in segments.segment_variables(r.segmento)) and segments.matches(row, r.segmento):
            prima *= r.multiplicador
            if r.multiplicador != 1.0:
                aplicados[f"regla:{r.id}"] = float(r.multiplicador)
    cob = float(profile.cobertura_verificacion)
    return QuoteOutput(
        prima=prima,
        intervalo=_intervalo(prima, cfg, cob),
        factores=aplicados,
        confianza=_confianza(cob),
    )


def _column(df: pd.DataFrame, var: str) -> pd.Series | None:
    if var in df.columns:
        return df[var]
    if var == "antiguedad" and "anio" in df.columns:
        return segments.ANIO_REFERENCIA - df["anio"]
    return None


def _has_var(df: pd.DataFrame, var: str) -> bool:
    return var in df.columns or (var == "antiguedad" and "anio" in df.columns)


def _factor_vector(f: Factor, col: pd.Series | None, n: int) -> np.ndarray:
    if col is None:
        return np.full(n, f.default, dtype=float)
    if f.categorias is not None:
        if pd.api.types.is_float_dtype(col):
            keys = col.map(lambda x: None if _is_null(x) else _cat_key(x))
        else:
            keys = col.astype(object).where(col.notna(), None).map(lambda x: None if x is None else str(x))
        return keys.map(f.categorias).astype(float).fillna(f.default).to_numpy()
    x = pd.to_numeric(col, errors="coerce").to_numpy(dtype=float)
    bins = np.asarray(f.bins, dtype=float)
    vals = np.asarray(f.valores, dtype=float)
    idx = np.searchsorted(bins, x, side="right") - 1
    out = np.where(idx >= 0, vals[np.clip(idx, 0, len(vals) - 1)], f.default)
    return np.where(np.isnan(x), f.default, out)


def quote_df(df: pd.DataFrame, cfg: CotizadorConfig) -> np.ndarray:
    """Versión vectorizada sobre columnas VEHICLE_COLUMNS. Debe coincidir con `quote` (tolerancia 1e-6)."""
    n = len(df)
    prima = np.full(n, float(cfg.base), dtype=float)
    for f in cfg.factores.values():
        prima *= _factor_vector(f, _column(df, f.variable), n)
    for r in cfg.reglas:
        if all(_has_var(df, v) for v in segments.segment_variables(r.segmento)):
            prima *= np.where(segments.segment_mask(df, r.segmento), r.multiplicador, 1.0)
    return prima


def input_hash(profile: VehicleProfile) -> str:
    canon = json.dumps(profile.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def predict(profile: VehicleProfile, cfg: CotizadorConfig, agent_version: str) -> Prediction:
    """Cotiza y construye la Prediction registrable (input_hash = sha256 del perfil canónico).
    `prediction_id` es determinístico: sha256(agent_version|input_hash)[:24] (reproducible con semilla)."""
    h = input_hash(profile)
    pid = "pred-" + hashlib.sha256(f"{agent_version}|{h}".encode()).hexdigest()[:24]
    return Prediction(
        prediction_id=pid,
        vehicle_id=profile.id,
        agent=cfg.agent,
        agent_version=agent_version,
        input_hash=h,
        output=quote(profile, cfg),
    )
