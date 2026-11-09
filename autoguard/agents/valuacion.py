"""Valuación con comparables. [STUB — tarea T-17] Único módulo que puede usar Tavily/Firecrawl."""
from __future__ import annotations

from autoguard.contracts import VehicleProfile


def valuate(profile: VehicleProfile) -> dict:
    """Devuelve {"precio_estimado", "rango": [lo, hi], "comparables": [...], "fuente": "cache|tavily|mock"}."""
    raise NotImplementedError
