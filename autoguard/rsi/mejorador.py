"""Mejorador: propone parches. [STUB — tarea T-08] NO puede importar autoguard.evaluator.evaluator."""
from __future__ import annotations

from autoguard.config_schema import CotizadorConfig
from autoguard.contracts import Hypothesis, MetaStrategy, Patch


def propose(
    cfg: CotizadorConfig,
    hypotheses: list[Hypothesis],
    arms: list[str],
    generation: int,
    lecciones: str = "",
    max_patches: int = 3,
) -> list[Patch]:
    """Genera hasta max_patches parches, uno por brazo en `arms` (elegidos por el meta-mejorador).
    LLM con fallback heurístico determinístico (corrige el sesgo medio del segmento)."""
    raise NotImplementedError
