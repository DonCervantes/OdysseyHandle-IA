"""Meta-mejorador: Thompson sampling por tipo de parche + lecciones. [STUB — tarea T-11]"""
from __future__ import annotations

from autoguard.contracts import MetaStrategy, Patch


class MetaImprover:
    def __init__(self, arms: list[str], seed: int = 0):
        self.arms = arms

    def choose_arms(self, k: int) -> list[str]:
        """Muestrea k brazos (con reemplazo) por Thompson sampling sobre Beta(alpha, beta)."""
        raise NotImplementedError

    def update(self, patches: list[Patch]) -> MetaStrategy:
        """Actualiza posteriors con veredictos (recompensa = ganancia>0), reescribe lecciones (LLM con
        fallback), y revierte el cambio de estrategia si la ganancia media de la generación bajó."""
        raise NotImplementedError

    def strategy(self) -> MetaStrategy:
        raise NotImplementedError
