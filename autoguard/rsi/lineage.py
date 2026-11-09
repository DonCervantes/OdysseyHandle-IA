"""Linaje SIMULADO en un repositorio Git propio por corrida y variante.

El mensaje de commit lo proporciona el llamador: debe incluir patch_id, tipo,
hipótesis y métricas. Puede ser JSON con ``metrics`` para exponerlas en history.
"""
from __future__ import annotations

import json
from pathlib import Path

from git import Actor, Repo

from autoguard.config_schema import CotizadorConfig, dump_config
from autoguard.contracts import AgentVersion

_CONFIG = "config.yaml"
_MARKER = ".autoguard-lineage"
_ACTOR = Actor("AUTOGUARD SIMULADO", "autoguard@example.invalid")


class ConfigRepo:
    def __init__(self, path: str | Path, agent: str = "cotizador"):
        self.path = Path(path).resolve()
        self.agent = agent

    def _repo(self) -> Repo:
        repo = Repo(self.path, search_parent_directories=False)
        if repo.bare or Path(repo.working_tree_dir).resolve() != self.path:
            raise ValueError("Se requiere un repositorio propio con working tree")
        if (self.path / _MARKER).read_text() != self.agent:
            raise ValueError("Repositorio de otro agente")
        return repo

    def _validate(self, cfg: CotizadorConfig) -> CotizadorConfig:
        cfg = CotizadorConfig.model_validate(cfg.model_dump())
        if cfg.agent != self.agent:
            raise ValueError("La configuración pertenece a otro agente")
        return cfg

    def init(self, cfg: CotizadorConfig) -> str:
        """Crea el campeón inicial; no sobrescribe un repositorio existente."""
        cfg = self._validate(cfg)
        if self.path.exists() and any(self.path.iterdir()):
            raise ValueError("El directorio de linaje debe estar vacío")
        self.path.mkdir(parents=True, exist_ok=True)
        repo = Repo.init(self.path)
        (self.path / _MARKER).write_text(self.agent)
        (self.path / _CONFIG).write_text(dump_config(cfg), encoding="utf-8")
        repo.index.add([_MARKER, _CONFIG])
        return repo.index.commit("Campeón inicial SIMULADO", author=_ACTOR, committer=_ACTOR).hexsha

    def current(self) -> tuple[CotizadorConfig, str]:
        """Lee el campeón confirmado en HEAD, independientemente del working tree."""
        import yaml

        head = self._repo().head.commit
        cfg = CotizadorConfig.model_validate(yaml.safe_load((head.tree / _CONFIG).data_stream.read()))
        return self._validate(cfg), head.hexsha

    def commit(self, cfg: CotizadorConfig, message: str) -> str:
        """Confirma un parche; message incluye identidad, hipótesis y métricas."""
        cfg = self._validate(cfg)
        if not message.strip():
            raise ValueError("El commit requiere un mensaje de trazabilidad")
        repo = self._repo()
        if repo.is_dirty(untracked_files=True):
            raise ValueError("El repositorio de linaje tiene cambios sin confirmar")
        (self.path / _CONFIG).write_text(dump_config(cfg), encoding="utf-8")
        repo.index.add([_CONFIG])
        return repo.index.commit(message, author=_ACTOR, committer=_ACTOR).hexsha

    def revert_to(self, sha: str, message: str = "") -> str:
        """Restaura bytes exactos como NUEVO commit, conservando el historial."""
        repo = self._repo()
        target = repo.commit(sha)
        if not repo.is_ancestor(target, repo.head.commit):
            raise ValueError("La versión no pertenece al historial del campeón")
        if repo.is_dirty(untracked_files=True):
            raise ValueError("El repositorio de linaje tiene cambios sin confirmar")
        data = (target.tree / _CONFIG).data_stream.read()
        (self.path / _CONFIG).write_bytes(data)
        repo.index.add([_CONFIG])
        return repo.index.commit(
            f"Reversión a {target.hexsha}\n\n{message}", author=_ACTOR, committer=_ACTOR
        ).hexsha

    def history(self) -> list[AgentVersion]:
        repo = self._repo()
        head = repo.head.commit.hexsha
        versions = []
        for c in repo.iter_commits():
            metrics = {}
            try:
                payload = json.loads(c.message)
                if isinstance(payload, dict):
                    raw = payload.get("metrics", payload.get("metrics_after", {}))
                    if isinstance(raw, dict):  # solo numéricas: AgentVersion.metrics es dict[str, float]
                        metrics = {k: float(v) for k, v in raw.items()
                                   if isinstance(v, (int, float)) and not isinstance(v, bool)}
            except (ValueError, TypeError):
                pass
            versions.append(AgentVersion(
                id=f"{self.agent}@{c.hexsha[:7]}", agent=self.agent,
                parent_id=f"{self.agent}@{c.parents[0].hexsha[:7]}" if c.parents else None,
                git_sha=c.hexsha, estado="campeon" if c.hexsha == head else "retirado",
                metrics=metrics, created_at=c.committed_datetime,
            ))
        return versions
