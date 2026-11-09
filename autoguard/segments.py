"""Segmentos: dict de condiciones sobre columnas de un vehículo.

    {"anio_max": 1996, "siniestros_previos": 1, "uso": "app_transporte", "kilometraje_min": 150000}

- `<var>`      -> igualdad
- `<var>_min`  -> >=
- `<var>_max`  -> <=
`antiguedad` se deriva como ANIO_REFERENCIA - anio.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

ANIO_REFERENCIA = 2026


def _split(key: str) -> tuple[str, str]:
    for suf, op in (("_min", ">="), ("_max", "<=")):
        if key.endswith(suf):
            return key[: -len(suf)], op
    return key, "=="


def segment_variables(segmento: dict[str, Any]) -> list[str]:
    return [_split(k)[0] for k in segmento]


def _column(df: pd.DataFrame, var: str) -> pd.Series:
    if var == "antiguedad" and "antiguedad" not in df.columns:
        return ANIO_REFERENCIA - df["anio"]
    return df[var]


def segment_mask(df: pd.DataFrame, segmento: dict[str, Any]) -> np.ndarray:
    mask = np.ones(len(df), dtype=bool)
    for key, val in segmento.items():
        var, op = _split(key)
        col = _column(df, var)
        if op == ">=":
            mask &= (col >= val).to_numpy()
        elif op == "<=":
            mask &= (col <= val).to_numpy()
        else:
            mask &= (col == val).to_numpy()
    return mask


def matches(row: dict[str, Any], segmento: dict[str, Any]) -> bool:
    return bool(segment_mask(pd.DataFrame([row]), segmento)[0])


def describe(segmento: dict[str, Any]) -> str:
    sym = {">=": "≥", "<=": "≤", "==": "="}
    return ", ".join(f"{_split(k)[0]} {sym[_split(k)[1]]} {v}" for k, v in segmento.items()) or "todos"
