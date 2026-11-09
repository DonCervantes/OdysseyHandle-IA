"""Agente de inspección visual. [STUB — tarea T-12]"""
from __future__ import annotations

from autoguard.contracts import Dano


def inspect(images: list[bytes], hints: list[str] | None = None) -> list[Dano]:
    """Detecta daños visibles y estima costo de reacondicionamiento (tabla de costos determinística por
    zona×tipo; el LLM solo clasifica). Fallback mock usa `hints` (p.ej. nombres de archivo)."""
    raise NotImplementedError
