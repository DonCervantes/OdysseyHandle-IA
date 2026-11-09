"""Linaje de versiones en Git. [STUB — tarea T-10]

Cada corrida usa un repo Git PROPIO (p.ej. var/runs/<run_id>/configs/<variant>), nunca el repo del proyecto.
"""
from __future__ import annotations

from pathlib import Path

from autoguard.config_schema import CotizadorConfig
from autoguard.contracts import AgentVersion


class ConfigRepo:
    def __init__(self, path: str | Path, agent: str = "cotizador"):
        self.path = Path(path)

    def init(self, cfg: CotizadorConfig) -> str:
        """Crea el repo con el campeón inicial; devuelve sha."""
        raise NotImplementedError

    def current(self) -> tuple[CotizadorConfig, str]:
        raise NotImplementedError

    def commit(self, cfg: CotizadorConfig, message: str) -> str:
        """Un parche aceptado = un commit. Devuelve sha."""
        raise NotImplementedError

    def revert_to(self, sha: str, message: str = "") -> str:
        """Restaura la config de `sha` como NUEVO commit (historial preservado). Devuelve sha nuevo."""
        raise NotImplementedError

    def history(self) -> list[AgentVersion]:
        raise NotImplementedError
