"""Tests del sandbox (T-18). Backend subprocess forzado: no requieren Docker ni red."""
import os

import pytest

from autoguard.evaluator import sandbox
from autoguard.evaluator.sandbox import run_code

SUB = {"backend": "subprocess"}


def test_codigo_valido_devuelve_resultado():
    r = run_code("RESULT = {'suma': sum(INPUT['xs']), 'n': len(INPUT['xs'])}\nprint('hola')",
                 {"xs": [1, 2, 3]}, timeout_s=5, **SUB)
    assert r.ok and r.returncode == 0 and r.killed_reason is None
    assert r.value == {"suma": 6, "n": 3}
    assert "hola" in r.stdout
    assert r.backend == "subprocess" and r.limitaciones


def test_excede_tiempo_se_corta():
    r = run_code("import time\ntime.sleep(30)", timeout_s=0.5, **SUB)
    assert not r.ok and r.timed_out and r.killed_reason == "timeout"
    assert r.duration_s < 5


def test_bucle_cpu_se_corta():
    r = run_code("while True:\n    pass", timeout_s=1.0, **SUB)
    assert not r.ok and r.killed_reason in ("timeout", "cpu")
    assert r.duration_s < 5


def test_excede_memoria_se_corta():
    code = "import time\nx = bytearray(400 * 2**20)\nx[::4096] = b'a' * len(x[::4096])\ntime.sleep(5)\nRESULT = 1"
    r = run_code(code, timeout_s=4, mem_mb=128, **SUB)
    assert not r.ok and r.killed_reason == "memoria"
    assert r.value is None


def test_excepcion_se_reporta_sin_lanzar():
    r = run_code("raise ValueError('boom')", **SUB)
    assert not r.ok and r.returncode != 0 and r.killed_reason is None
    assert "ValueError" in r.stderr and "boom" in r.stderr


def test_red_bloqueada_a_nivel_python():
    code = ("import socket\ntry:\n    socket.socket()\n    RESULT = 'abierta'\n"
            "except PermissionError:\n    RESULT = 'bloqueada'")
    r = run_code(code, **SUB)
    assert r.ok and r.value == "bloqueada"


def test_entorno_minimo_y_directorio_temporal(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secreta")
    code = "import os\nRESULT = {'env': sorted(os.environ), 'cwd': os.getcwd(), 'home': os.environ['HOME']}"
    r = run_code(code, **SUB)
    assert r.ok
    assert "OPENAI_API_KEY" not in r.value["env"]
    assert "autoguard_sandbox_" in r.value["cwd"]
    assert os.path.realpath(r.value["home"]) == os.path.realpath(r.value["cwd"])
    assert not os.path.exists(r.value["cwd"])  # se borra al terminar


def test_salida_truncada():
    r = run_code("print('x' * 100000)", max_output=1000, **SUB)
    assert r.ok and len(r.stdout) < 1100 and "truncado" in r.stdout


def test_backend_invalido_y_docker_ausente(monkeypatch):
    with pytest.raises(ValueError):
        run_code("pass", backend="k8s")
    monkeypatch.setattr(sandbox.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError):
        run_code("pass", backend="docker")
    assert run_code("RESULT = 1").backend == "subprocess"  # auto sin docker => fallback


def test_comando_docker_sin_red_y_con_limites():
    cmd = sandbox._docker_cmd("/tmp/w", 5, 5, 256, "python:3.12-slim")
    s = " ".join(cmd)
    assert "--network none" in s and "--memory 256m" in s and "--read-only" in s
    assert "--pids-limit" in s and "/tmp/w:/work" in s
