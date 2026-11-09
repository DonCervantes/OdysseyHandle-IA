"""Evaluador CONGELADO. [STUB — tarea T-09]"""
from __future__ import annotations

import pandas as pd

from autoguard.config_schema import CotizadorConfig
from autoguard.contracts import Patch, Verdict


def split_holdout(closed: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(train, holdout) determinístico por hash de vehicle_id (HOLDOUT_FRACTION). El mejorador solo ve train."""
    raise NotImplementedError


def evaluate(champion: CotizadorConfig, patch: Patch, holdout: pd.DataFrame) -> tuple[Verdict, CotizadorConfig | None]:
    """Valida el parche (apply_patch + lista blanca; inválido => rechazado sin evaluar), re-cotiza el
    holdout con campeón y retador, acepta si ganancia >= DELTA y ningún segmento (n>=MIN_SEGMENT_N)
    empeora más de EPSILON. Devuelve (veredicto, config_retador o None)."""
    raise NotImplementedError
