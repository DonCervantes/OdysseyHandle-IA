"""Lógica de la API sin FastAPI (testeable por separado): ajustes, campeón versionado, expedientes,
corridas RSI. Todos los datos de la demo son SIMULADOS.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from autoguard.config_schema import CotizadorConfig, apply_patch, load_config
from autoguard.contracts import AgentVersion, DocExtraction, Patch, TipoDocumento
from autoguard.db import repo
from autoguard.rsi.lineage import ConfigRepo

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------- ajustes
@dataclass
class Settings:
    """Se leen del entorno (`.env`); ninguna llave se escribe en código ni en logs.

    - AUTOGUARD_API_KEY: si está vacía, la autenticación queda DESACTIVADA (solo desarrollo local).
    - DATABASE_URL: ver autoguard/db/session.py.
    - AUTOGUARD_LINEAGE_DIR: repo Git del campeón de producción (default var/lineage/cotizador).
    - AUTOGUARD_RUNS_DIR: salidas del ciclo RSI (default var/runs).
    - AUTOGUARD_CORS_ORIGINS: orígenes separados por coma (default "*").
    """
    api_key: str = ""
    database_url: Optional[str] = None
    lineage_dir: Path = REPO_ROOT / "var" / "lineage" / "cotizador"
    runs_dir: Path = REPO_ROOT / "var" / "runs"
    base_config: Path = REPO_ROOT / "configs" / "agents" / "cotizador.yaml"
    cors_origins: list[str] = field(default_factory=lambda: ["*"])

    @classmethod
    def from_env(cls) -> "Settings":
        def p(name: str, default: Path) -> Path:
            v = os.environ.get(name)
            return Path(v) if v else default

        d = cls()
        origins = os.environ.get("AUTOGUARD_CORS_ORIGINS", "*")
        return cls(
            api_key=os.environ.get("AUTOGUARD_API_KEY", ""),
            database_url=os.environ.get("DATABASE_URL") or None,
            lineage_dir=p("AUTOGUARD_LINEAGE_DIR", d.lineage_dir),
            runs_dir=p("AUTOGUARD_RUNS_DIR", d.runs_dir),
            base_config=p("AUTOGUARD_BASE_CONFIG", d.base_config),
            cors_origins=[o.strip() for o in origins.split(",") if o.strip()] or ["*"],
        )


# ---------------------------------------------------------------- campeón (linaje Git + BD)
AGENT = "cotizador"


def version_id(sha: str, agent: str = AGENT) -> str:
    return f"{agent}@{sha[:7]}"


class Champion:
    """Campeón de PRODUCCIÓN del cotizador: HEAD del repo de linaje. Se inicializa desde
    `configs/agents/cotizador.yaml` la primera vez. Las operaciones se serializan con un lock."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.lock = threading.RLock()
        self._repo: Optional[ConfigRepo] = None

    @property
    def repo(self) -> ConfigRepo:
        with self.lock:
            if self._repo is None:
                r = ConfigRepo(self.settings.lineage_dir, agent=AGENT)
                if not (self.settings.lineage_dir / ".git").exists():
                    r.init(load_config(self.settings.base_config))
                self._repo = r
            return self._repo

    def current(self) -> tuple[CotizadorConfig, str]:
        with self.lock:
            return self.repo.current()

    def sync_db(self, session: Session, metrics: Optional[dict[str, float]] = None) -> AgentVersion:
        """Registra el HEAD actual como campeón en `agent_versions` (idempotente)."""
        with self.lock:
            _, sha = self.repo.current()
            vid = version_id(sha)
            existing = repo.get_agent_version(session, vid)
            if existing is None:
                prev = repo.get_champion(session, AGENT)
                repo.save_agent_version(session, AgentVersion(
                    id=vid, agent=AGENT, parent_id=prev.id if prev else None, git_sha=sha,
                    estado="campeon", metrics=metrics or {},
                ))
            if existing is None or existing.estado != "campeon":
                return repo.set_champion(session, vid)
            return existing

    def apply(self, session: Session, patch: Patch) -> AgentVersion:
        """Aplica un parche aprobado al campeón y lo confirma en el linaje. ValueError si es inválido."""
        with self.lock:
            self.sync_db(session)
            cfg, _ = self.repo.current()
            try:
                nuevo = apply_patch(cfg, patch)
            except Exception as e:  # ValidationError, KeyError/IndexError de rutas inexistentes, ...
                raise ValueError(f"{type(e).__name__}: {e}") from e
            msg = json.dumps({
                "patch_id": patch.patch_id, "tipo": patch.tipo, "hipotesis": patch.hipotesis,
                "diff": patch.diff, "metrics": patch.metrics_after, "aprobado_por": "actuario (API)",
            }, ensure_ascii=False, sort_keys=True)
            self.repo.commit(nuevo, msg)
            return self.sync_db(session, metrics=_numeric(patch.metrics_after))

    def revert(self, session: Session, sha: str) -> AgentVersion:
        with self.lock:
            self.sync_db(session)
            try:
                self.repo.revert_to(sha, message="Reversión solicitada vía API")
            except ValueError:
                raise
            except Exception as e:  # BadName/BadObject de GitPython: sha inexistente
                raise ValueError(f"sha desconocido: {sha}") from e
            return self.sync_db(session)


def _numeric(d: dict[str, Any]) -> dict[str, float]:
    return {k: float(v) for k, v in d.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}


# ---------------------------------------------------------------- expedientes
_TIPOS_TOKENS: dict[str, TipoDocumento] = {
    "FAC": "factura", "FACTURA": "factura", "CFDI": "factura",
    "TC": "tarjeta_circulacion", "TARJETA": "tarjeta_circulacion", "CIRCULACION": "tarjeta_circulacion",
    "POL": "poliza_anterior", "POLIZA": "poliza_anterior", "SEGURO": "poliza_anterior",
}
TIPOS_VALIDOS = ("factura", "tarjeta_circulacion", "poliza_anterior", "otro")


def documento_id(filename: str) -> str:
    """Id del documento = nombre de archivo sin extensión (el mock del documental lo usa como llave)."""
    stem = Path(filename or "documento").stem
    return re.sub(r"[^A-Za-z0-9_\-]", "_", stem)[:64] or "documento"


def infer_tipo(filename: str) -> TipoDocumento:
    tokens = re.split(r"[^A-Za-z0-9]+", Path(filename or "").stem.upper())
    for t in reversed(tokens):
        if t in _TIPOS_TOKENS:
            return _TIPOS_TOKENS[t]
    return "otro"


def guess_mime(filename: str, declared: Optional[str]) -> str:
    if declared and declared != "application/octet-stream":
        return declared
    ext = Path(filename or "").suffix.lower()
    return {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
            ".gif": "image/gif", ".pdf": "application/pdf"}.get(ext, "application/octet-stream")


def vehicle_id_for(contents: list[bytes], datos: dict[str, Any]) -> str:
    """Id determinístico a partir del contenido de los archivos y los datos declarados."""
    h = hashlib.sha256()
    for c in contents:
        h.update(hashlib.sha256(c).digest())
    h.update(json.dumps(datos, sort_keys=True, ensure_ascii=False, default=str).encode())
    return "veh-" + h.hexdigest()[:16]


@dataclass
class Upload:
    filename: str
    content: bytes
    mime: str


def procesar_expediente(
    docs: list[Upload], fotos: list[Upload], tipos: list[str], datos: dict[str, Any],
    vehicle_id: Optional[str], cfg: CotizadorConfig, agent_version: str,
) -> dict[str, Any]:
    """docs → extracción + verificación cruzada → (visual) → perfil → (valuación) → cotización.
    Los módulos opcionales (visual T-12, valuación T-17) se omiten si no existen o fallan."""
    from autoguard.agents import cotizador, documental

    if tipos and len(tipos) != len(docs):
        raise ValueError(f"'tipos' tiene {len(tipos)} elementos y hay {len(docs)} documentos")
    for t in tipos:
        if t not in TIPOS_VALIDOS:
            raise ValueError(f"tipo de documento inválido: {t!r} (válidos: {', '.join(TIPOS_VALIDOS)})")

    omitidos: dict[str, str] = {}
    extractions: list[DocExtraction] = []
    usados: set[str] = set()
    for i, d in enumerate(docs):
        did = documento_id(d.filename)
        base, k = did, 2
        while did in usados:
            did, k = f"{base}-{k}", k + 1
        usados.add(did)
        tipo = tipos[i] if tipos else infer_tipo(d.filename)
        extractions.append(documental.extract(d.content, tipo, did, mime=d.mime))

    extra = dict(datos)
    if fotos:
        try:
            from autoguard.agents import visual

            danos = visual.inspect([f.content for f in fotos], hints=[f.filename for f in fotos])
            extra["danos"] = list(extra.get("danos", [])) + [x.model_dump() for x in danos]
        except NotImplementedError:
            omitidos["visual"] = "no implementado (T-12)"
        except Exception as e:  # noqa: BLE001 — un módulo opcional no tumba el expediente
            omitidos["visual"] = f"error: {type(e).__name__}"

    vid = vehicle_id or vehicle_id_for([d.content for d in docs + fotos], datos)
    profile = documental.build_profile(vid, extractions, extra=extra)

    valuacion = None
    try:
        from autoguard.agents import valuacion as val_mod

        valuacion = val_mod.valuate(profile)
    except NotImplementedError:
        omitidos["valuacion"] = "no implementado (T-17)"
    except Exception as e:  # noqa: BLE001
        omitidos["valuacion"] = f"error: {type(e).__name__}"

    pred = cotizador.predict(profile, cfg, agent_version)
    return {"perfil": profile, "extracciones": extractions, "prediccion": pred, "valuacion": valuacion,
            "omitidos": omitidos}


# ---------------------------------------------------------------- corridas RSI
def latest_run_dir(runs_dir: Path) -> Optional[Path]:
    if not runs_dir.is_dir():
        return None
    runs = [d for d in runs_dir.iterdir() if d.is_dir() and (d / "summary.json").is_file()]
    if not runs:
        return None
    return max(runs, key=lambda d: ((d / "summary.json").stat().st_mtime, d.name))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def run_patches(runs_dir: Path) -> list[Patch]:
    """Parches de la corrida más reciente (`patches.jsonl`); ignora líneas que no son un Patch."""
    d = latest_run_dir(runs_dir)
    if d is None:
        return []
    out = []
    for rec in read_jsonl(d / "patches.jsonl"):
        try:
            out.append(Patch.model_validate(rec.get("patch", rec)))
        except Exception:  # noqa: BLE001
            continue
    return out


RsiRunner = Callable[[dict[str, Any]], dict[str, Any]]


class SubprocessRsiRunner:
    """Lanza `python -m autoguard.rsi.loop` (CLI de T-13) en segundo plano; un job a la vez."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.jobs: dict[str, dict[str, Any]] = {}
        self.lock = threading.Lock()

    def _estado(self, job: dict[str, Any]) -> dict[str, Any]:
        rc = job["proc"].poll()
        estado = "corriendo" if rc is None else ("terminado" if rc == 0 else "fallido")
        return {k: v for k, v in job.items() if k != "proc"} | {"estado": estado, "returncode": rc}

    def __call__(self, params: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            for job in self.jobs.values():
                if job["proc"].poll() is None:
                    raise RuntimeError(f"ya hay una corrida RSI en curso: {job['job_id']}")
            job_id = "job-" + uuid.uuid4().hex[:12]
            cmd = [sys.executable, "-m", "autoguard.rsi.loop"]
            for k, v in params.items():
                cmd += [f"--{k.replace('_', '-')}", str(v)]
            log_dir = self.settings.runs_dir / "_api_jobs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log = open(log_dir / f"{job_id}.log", "wb")  # noqa: SIM115 — vive lo que el proceso
            env = dict(os.environ)
            env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
            proc = subprocess.Popen(cmd, cwd=REPO_ROOT, stdout=log, stderr=subprocess.STDOUT, env=env)
            job = {"job_id": job_id, "params": params, "inicio": time.time(), "proc": proc,
                   "log": str(log_dir / f"{job_id}.log")}
            self.jobs[job_id] = job
            return self._estado(job)

    def status(self, job_id: str) -> Optional[dict[str, Any]]:
        job = self.jobs.get(job_id)
        return self._estado(job) if job else None
