"""Analista de errores. [STUB — tarea T-07]"""
from __future__ import annotations

import pandas as pd

from autoguard.contracts import Hypothesis


def analyze(errors: pd.DataFrame, top_k: int = 3, min_n: int = 30) -> list[Hypothesis]:
    """Agrupa errores por segmentos candidatos (1 y 2 variables), calcula sesgo medio de error_rel,
    significancia (t-test vs 0) e impacto; devuelve las top_k hipótesis significativas (p<0.05)."""
    raise NotImplementedError
