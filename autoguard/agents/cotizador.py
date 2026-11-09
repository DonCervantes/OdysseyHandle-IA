"""Cotizador base explicable. [STUB — tarea T-04]"""
from __future__ import annotations

import numpy as np
import pandas as pd

from autoguard.config_schema import CotizadorConfig
from autoguard.contracts import Prediction, QuoteOutput, VehicleProfile


def quote(profile: VehicleProfile, cfg: CotizadorConfig) -> QuoteOutput:
    """prima = base × Π factores × Π reglas que aplican; `factores` lista cada multiplicador aplicado."""
    raise NotImplementedError


def quote_df(df: pd.DataFrame, cfg: CotizadorConfig) -> np.ndarray:
    """Versión vectorizada sobre columnas VEHICLE_COLUMNS. Debe coincidir con `quote` (tolerancia 1e-6)."""
    raise NotImplementedError


def predict(profile: VehicleProfile, cfg: CotizadorConfig, agent_version: str) -> Prediction:
    """Cotiza y construye la Prediction registrable (input_hash = sha256 del perfil canónico)."""
    raise NotImplementedError
