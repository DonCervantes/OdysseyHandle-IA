"""Recolector de resultados: une predicciones con outcomes y calcula el error por póliza cerrada.

Robusto ante datos sucios:
- outcomes duplicados por `prediction_id`: gana el más reciente (`observed_at` si existe; si no, el último
  en orden de llegada);
- predicciones sin outcome, con `vendida` faltante/False, o con `costo_real` faltante/no positivo: se
  descartan (no son casos cerrados evaluables);
- predicciones duplicadas por `prediction_id`: se conserva la última;
- outcomes con `valor` como dict (formato `contracts.Outcome`) se aplanan a `vendida`/`costo_real`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from autoguard.evaluator.objective import loss

OUTCOME_COLUMNS = ["vendida", "costo_real"]


def _to_bool(s: pd.Series) -> pd.Series:
    def conv(v) -> bool:
        if isinstance(v, str):
            return v.strip().lower() in ("true", "1", "si", "sí", "yes", "t")
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return False
        try:
            if pd.isna(v):
                return False
        except (TypeError, ValueError):
            pass
        return bool(v)

    return s.map(conv).astype(bool)


def _normalize_outcomes(outcomes: pd.DataFrame) -> pd.DataFrame:
    out = outcomes.copy()
    if "valor" in out.columns:
        valores = pd.DataFrame(
            [v if isinstance(v, dict) else {} for v in out["valor"]], index=out.index
        )
        for c in OUTCOME_COLUMNS:
            if c in valores.columns:
                out[c] = valores[c].where(valores[c].notna(), out[c]) if c in out.columns else valores[c]
    for c in OUTCOME_COLUMNS:
        if c not in out.columns:
            out[c] = np.nan
    out["_orden"] = np.arange(len(out))
    sort_cols = ["_orden"]
    if "observed_at" in out.columns:
        out["_ts"] = pd.to_datetime(out["observed_at"], errors="coerce", utc=True)
        sort_cols = ["_ts", "_orden"]
    out = out.sort_values(sort_cols, na_position="first", kind="stable")
    out = out.drop_duplicates("prediction_id", keep="last")
    return out[["prediction_id", *OUTCOME_COLUMNS]]


def collect(predictions: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    """Une predicciones (prediction_id, vehicle_id, agent_version, prima + VEHICLE_COLUMNS) con outcomes
    (prediction_id, vendida, costo_real). Devuelve SOLO casos cerrados (vendida=True) con columnas extra:
    loss (objective.loss), error_rel = (prima - costo_real) / costo_real."""
    preds = predictions.drop(columns=[c for c in OUTCOME_COLUMNS if c in predictions.columns])
    preds = preds.drop_duplicates("prediction_id", keep="last")
    if outcomes is None or len(outcomes) == 0 or len(preds) == 0:
        empty = preds.iloc[0:0].copy()
        for c in (*OUTCOME_COLUMNS, "loss", "error_rel"):
            empty[c] = pd.Series(dtype=float)
        return empty.reset_index(drop=True)

    outs = _normalize_outcomes(outcomes)
    df = preds.merge(outs, on="prediction_id", how="inner", validate="one_to_one")
    df["vendida"] = _to_bool(df["vendida"])
    df["costo_real"] = pd.to_numeric(df["costo_real"], errors="coerce")
    df["prima"] = pd.to_numeric(df["prima"], errors="coerce")
    closed = df["vendida"] & (df["costo_real"] > 0) & df["prima"].notna()
    df = df.loc[closed].reset_index(drop=True)

    prima = df["prima"].to_numpy(dtype=float)
    costo = df["costo_real"].to_numpy(dtype=float)
    df["loss"] = loss(prima, costo)
    df["error_rel"] = (prima - costo) / costo
    return df
