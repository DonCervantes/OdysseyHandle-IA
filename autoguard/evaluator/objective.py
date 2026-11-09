"""Función objetivo CONGELADA. El grafo RSI (mejorador, meta-mejorador, analista) NO puede modificar
este módulo ni sus constantes. Cambiarlas requiere una tarea humana explícita.

L(p, c) = ALPHA * max(0, c - p) + BETA * max(0, p - c),  ALPHA > BETA
R(N)    = sum_{i<=N} L(p_i, c_i)
"""
from __future__ import annotations

import numpy as np

ALPHA = 1.5  # costo de cobrar de menos
BETA = 1.0   # costo de cobrar de más
DELTA = 0.01  # mejora mínima relativa en el conjunto reservado para aceptar un parche (1%)
EPSILON = 0.05  # empeoramiento relativo máximo permitido en cualquier segmento (5%)
MIN_SEGMENT_N = 30  # segmentos con menos casos no se usan para el chequeo de regresión
HOLDOUT_FRACTION = 0.20


def loss(prima, costo) -> np.ndarray:
    p = np.asarray(prima, dtype=float)
    c = np.asarray(costo, dtype=float)
    return ALPHA * np.maximum(0.0, c - p) + BETA * np.maximum(0.0, p - c)


def regret(prima, costo) -> np.ndarray:
    """Regret acumulado R(N) para N = 1..len."""
    return np.cumsum(loss(prima, costo))
