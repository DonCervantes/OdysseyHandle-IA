"""Recolector de resultados. [STUB — tarea T-06]"""
from __future__ import annotations

import pandas as pd


def collect(predictions: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    """Une predicciones (prediction_id, vehicle_id, agent_version, prima + VEHICLE_COLUMNS) con outcomes
    (prediction_id, vendida, costo_real). Devuelve SOLO casos cerrados (vendida=True) con columnas extra:
    loss (objective.loss), error_rel = (prima - costo_real) / costo_real."""
    raise NotImplementedError
