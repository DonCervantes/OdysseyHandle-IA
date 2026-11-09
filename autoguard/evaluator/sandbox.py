"""Sandbox para ejecutar código de parches de nivel código (T-18).

Ejecuta un fragmento de Python aislado en otro proceso, con límites de tiempo, CPU y memoria, en un
directorio temporal desechable y con un entorno mínimo. Dos backends:

- ``docker`` (si el binario ``docker`` existe): ``docker run --rm --network none --memory ... --cpus 1
  --pids-limit ... --read-only`` con el directorio temporal montado en ``/work``. Aislamiento real,
  incluida la red.
- ``subprocess`` (fallback; el default en la Mac del coordinador, sin Docker): proceso hijo
  ``python -I`` en su propia sesión, ``cwd`` = directorio temporal, entorno mínimo (sin variables del
  padre, por lo que no hereda llaves de API), ``resource.setrlimit`` para CPU / tamaño de archivo /
  descriptores / core, y un vigilante que mata al grupo de procesos si excede el tiempo de pared o la
  memoria residente (RSS medida con ``ps``; necesario porque macOS rechaza RLIMIT_AS/RLIMIT_DATA).

LIMITACIONES DECLARADAS del fallback ``subprocess`` (no es una frontera de seguridad):
- **Sin aislamiento de red real.** Solo se bloquea ``socket`` a nivel Python dentro del hijo
  (best-effort: código nativo o ``ctypes`` puede saltárselo). Para aislamiento de red usar Docker.
- El sistema de archivos no está aislado: el hijo corre con el usuario del padre; solo su ``cwd`` y
  ``HOME`` apuntan al directorio temporal.
- El límite de memoria se aplica por muestreo de RSS (cada ``POLL_S``); un pico muy rápido puede
  rebasarlo brevemente antes de que el proceso sea terminado. En Linux además aplica RLIMIT_AS.

Protocolo con el código: recibe ``INPUT`` (lo que se pase en ``input_data``, serializable a JSON) como
global; si define una global ``RESULT`` serializable a JSON, se devuelve en ``SandboxResult.value``.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_TIMEOUT_S = 5.0
DEFAULT_MEM_MB = 256
DEFAULT_MAX_OUTPUT = 64_000  # bytes de stdout/stderr que se conservan
POLL_S = 0.02
DOCKER_IMAGE = "python:3.12-slim"

_CODE_FILE = "patch_code.py"
_RUNNER_FILE = "_sandbox_runner.py"
_INPUT_FILE = "input.json"
_RESULT_FILE = "result.json"

# Corre dentro del hijo: bloquea red a nivel Python (best-effort), ejecuta el código y vuelca RESULT.
_RUNNER = r'''
import json, socket, sys

def _no_net(*a, **k):
    raise PermissionError("sandbox: red deshabilitada")

class _NoSocket(socket.socket):
    def __init__(self, *a, **k):
        _no_net()

socket.socket = _NoSocket
socket.create_connection = _no_net
socket.getaddrinfo = _no_net

with open("input.json", encoding="utf-8") as f:
    INPUT = json.load(f)
with open("patch_code.py", encoding="utf-8") as f:
    src = f.read()
g = {"__name__": "__main__", "INPUT": INPUT}
exec(compile(src, "patch_code.py", "exec"), g)
if "RESULT" in g:
    with open("result.json", "w", encoding="utf-8") as f:
        json.dump(g["RESULT"], f)
'''


@dataclass
class SandboxResult:
    ok: bool  # terminó con código 0 y sin exceder límites
    returncode: int | None
    stdout: str
    stderr: str
    value: Any = None  # RESULT del código, si lo definió
    timed_out: bool = False
    killed_reason: str | None = None  # "timeout" | "memoria" | "cpu" | None
    backend: str = "subprocess"
    duration_s: float = 0.0
    limitaciones: list[str] = field(default_factory=list)


def docker_available() -> bool:
    return shutil.which("docker") is not None


def _minimal_env(workdir: str) -> dict[str, str]:
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": workdir,
        "TMPDIR": workdir,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
    }


def _set_limits(cpu_s: float, mem_mb: int) -> None:  # pragma: no cover - corre en el hijo
    import resource

    def _try(res: int, soft: int) -> None:
        try:
            _, hard = resource.getrlimit(res)
            if hard != resource.RLIM_INFINITY:
                soft = min(soft, hard)
            resource.setrlimit(res, (soft, hard if hard != resource.RLIM_INFINITY else soft))
        except (ValueError, OSError):
            pass  # macOS rechaza RLIMIT_AS/DATA: lo cubre el vigilante de RSS

    _try(resource.RLIMIT_CPU, max(1, math.ceil(cpu_s)))
    _try(resource.RLIMIT_AS, mem_mb * 2**20)
    _try(resource.RLIMIT_FSIZE, 16 * 2**20)
    _try(resource.RLIMIT_NOFILE, 64)
    _try(resource.RLIMIT_CORE, 0)


def _rss_mb(pid: int) -> float:
    """RSS total (MB) del grupo de procesos `pid` (el hijo es líder de su sesión)."""
    try:
        out = subprocess.run(["ps", "-o", "rss=", "-g", str(pid)], capture_output=True, text=True,
                             timeout=2).stdout
        vals = [int(x) for x in out.split() if x.strip().isdigit()]
        if not vals:  # algunos `ps` no aceptan -g: solo el proceso
            out = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True,
                                 timeout=2).stdout
            vals = [int(x) for x in out.split() if x.strip().isdigit()]
        return sum(vals) / 1024.0
    except Exception:
        return 0.0


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except Exception:
            pass


def _read(path: Path, limit: int) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    if len(data) > limit:
        data = data[:limit] + b"\n...[truncado]"
    return data.decode("utf-8", errors="replace")


def _docker_cmd(workdir: str, timeout_s: float, cpu_s: float, mem_mb: int, image: str) -> list[str]:
    return [
        "docker", "run", "--rm", "--network", "none",
        "--memory", f"{mem_mb}m", "--memory-swap", f"{mem_mb}m",
        "--cpus", "1", "--pids-limit", "64", "--read-only",
        "--ulimit", f"cpu={max(1, math.ceil(cpu_s))}",
        "--tmpfs", "/tmp:size=16m",
        "--security-opt", "no-new-privileges", "--cap-drop", "ALL",
        "-e", "PYTHONHASHSEED=0", "-e", "PYTHONDONTWRITEBYTECODE=1",
        "-v", f"{workdir}:/work", "-w", "/work",
        image, "python", "-I", _RUNNER_FILE,
    ]


def run_code(
    code: str,
    input_data: Any = None,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    cpu_s: float | None = None,
    mem_mb: int = DEFAULT_MEM_MB,
    backend: str = "auto",
    max_output: int = DEFAULT_MAX_OUTPUT,
    docker_image: str = DOCKER_IMAGE,
) -> SandboxResult:
    """Ejecuta `code` en el sandbox. `backend`: "auto" (Docker si existe, si no subprocess),
    "docker" o "subprocess". `cpu_s` default = `timeout_s`. Nunca lanza por fallas del código:
    todo se refleja en el `SandboxResult`."""
    if backend not in ("auto", "docker", "subprocess"):
        raise ValueError(f"backend desconocido: {backend}")
    use_docker = backend == "docker" or (backend == "auto" and docker_available())
    if backend == "docker" and not docker_available():
        raise RuntimeError("backend='docker' pedido pero docker no está instalado")
    cpu_s = timeout_s if cpu_s is None else cpu_s

    with tempfile.TemporaryDirectory(prefix="autoguard_sandbox_") as workdir:
        wd = Path(workdir)
        (wd / _CODE_FILE).write_text(code, encoding="utf-8")
        (wd / _RUNNER_FILE).write_text(_RUNNER, encoding="utf-8")
        (wd / _INPUT_FILE).write_text(json.dumps(input_data), encoding="utf-8")
        out_p, err_p = wd / "stdout.txt", wd / "stderr.txt"

        if use_docker:
            cmd = _docker_cmd(workdir, timeout_s, cpu_s, mem_mb, docker_image)
            popen_kw: dict[str, Any] = {"env": {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}}
            limitaciones: list[str] = []
            name = "docker"
        else:
            cmd = [sys.executable, "-I", _RUNNER_FILE]
            popen_kw = {
                "env": _minimal_env(workdir),
                "preexec_fn": lambda: _set_limits(cpu_s, mem_mb),
                "start_new_session": True,
            }
            limitaciones = ["sin aislamiento de red real (solo socket bloqueado a nivel Python)",
                            "filesystem no aislado (mismo usuario; cwd/HOME temporales)",
                            "memoria por muestreo de RSS"]
            name = "subprocess"

        t0 = time.monotonic()
        killed: str | None = None
        with open(out_p, "wb") as fo, open(err_p, "wb") as fe:
            proc = subprocess.Popen(cmd, cwd=workdir, stdin=subprocess.DEVNULL, stdout=fo, stderr=fe,
                                    close_fds=True, **popen_kw)
            try:
                while True:
                    try:
                        proc.wait(timeout=POLL_S)
                        break
                    except subprocess.TimeoutExpired:
                        pass
                    if time.monotonic() - t0 > timeout_s:
                        killed = "timeout"
                    elif not use_docker and _rss_mb(proc.pid) > mem_mb:
                        killed = "memoria"
                    if killed:
                        _kill_group(proc)
                        proc.wait()
                        break
            finally:
                if proc.poll() is None:
                    _kill_group(proc)
                    proc.wait()
        dur = time.monotonic() - t0
        rc = proc.returncode
        stderr = _read(err_p, max_output)
        if killed is None and rc is not None and rc < 0 and -rc == getattr(signal, "SIGXCPU", -1):
            killed = "cpu"
        if killed is None and rc not in (0, None) and "MemoryError" in stderr:
            killed = "memoria"
        if killed is None and use_docker and rc == 137:  # OOM-killer del contenedor
            killed = "memoria"
        value = None
        res_p = wd / _RESULT_FILE
        if killed is None and rc == 0 and res_p.exists():
            try:
                value = json.loads(res_p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                value = None
        return SandboxResult(
            ok=(killed is None and rc == 0),
            returncode=rc,
            stdout=_read(out_p, max_output),
            stderr=stderr,
            value=value,
            timed_out=killed == "timeout",
            killed_reason=killed,
            backend=name,
            duration_s=dur,
            limitaciones=limitaciones,
        )
