"""Simulador de mercado. [STUB — tarea T-03]"""
from __future__ import annotations

import numpy as np
import pandas as pd


class MarketSimulator:
    """Población sintética + riesgo OCULTO + demanda + siniestros, con semilla fija.

    Los factores reales del riesgo nunca se exponen fuera de este módulo (salvo `oracle_expected_cost`,
    que solo el evaluador/benchmark puede usar).
    """

    def __init__(self, seed: int = 42):
        self.seed = seed

    def sample_batch(self, n: int) -> pd.DataFrame:
        """Devuelve n autos con columnas autoguard.contracts.VEHICLE_COLUMNS. Misma semilla => misma secuencia."""
        raise NotImplementedError

    def resolve(self, batch: pd.DataFrame, primas: np.ndarray) -> pd.DataFrame:
        """Resuelve ventas y siniestros. Devuelve DataFrame alineado con columnas
        ["vehicle_id", "vendida" (bool), "costo_real" (float, MXN anual realizado)].
        `costo_real` se genera para TODOS los autos (el benchmark lo usa); el RSI solo ve los vendidos.
        Determinístico dado (seed, batch) e independiente de `primas` (salvo `vendida`)."""
        raise NotImplementedError

    def oracle_expected_cost(self, batch: pd.DataFrame) -> np.ndarray:
        """Costo esperado real (sin ruido). SOLO para benchmark/tests, nunca para agentes."""
        raise NotImplementedError
