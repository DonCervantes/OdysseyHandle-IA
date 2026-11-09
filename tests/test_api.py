"""Tests de la API (T-14) con TestClient. Sin red: LLM en mock, BD SQLite temporal, linaje en tmp.
Datos SIMULADOS."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from autoguard.api import services
from autoguard.api.main import create_app
from autoguard.api.services import Settings, infer_tipo
from autoguard.config_schema import load_config
from autoguard.contracts import ConfigChange, Patch

REPO = Path(__file__).resolve().parents[1]
DOCS = REPO / "data" / "samples" / "docs"
KEY = "test-key-SIMULADA"
H = {"X-API-Key": KEY}


class FakeRunner:
    def __init__(self):
        self.calls = []

    def __call__(self, params):
        if self.calls:
            raise RuntimeError("ya hay una corrida RSI en curso")
        self.calls.append(params)
        return {"job_id": "job-fake", "estado": "corriendo", "params": params}

    def status(self, job_id):
        return {"job_id": job_id, "estado": "terminado"} if job_id == "job-fake" else None


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    settings = Settings(
        api_key=KEY,
        database_url=f"sqlite:///{tmp_path / 'api.db'}",
        lineage_dir=tmp_path / "lineage",
        runs_dir=tmp_path / "runs",
    )
    runner = FakeRunner()
    client = TestClient(create_app(settings, rsi_runner=runner))
    return client, settings, runner


def _files(exp: str):
    files = [("docs", (f"{exp}-{s}.png", (DOCS / f"{exp}-{s}.png").read_bytes(), "image/png"))
             for s in ("FAC", "TC", "POL")]
    return files


def _datos():
    return json.dumps({"kilometraje": 85000, "siniestros_previos": 1, "uso": "particular", "zona": "CDMX"})


def _profile(vid="veh-sim-1", **kw):
    base = {"id": vid, "marca": "Nissan", "modelo": "Versa", "anio": 2019, "kilometraje": 60000,
            "siniestros_previos": 0, "uso": "app_transporte", "zona": "CDMX"}
    return base | kw


def _write_run(runs: Path, run_id: str, patches: list[Patch]):
    d = runs / run_id
    d.mkdir(parents=True)
    (d / "summary.json").write_text(json.dumps({"regret": {"rsi": 1.0, "estatico": 2.0}}))
    (d / "curve.csv").write_text("variante,polizas,regret\nrsi,200,10.5\nestatico,200,20.0\n")
    (d / "patches.jsonl").write_text("\n".join(p.model_dump_json() for p in patches) + "\n")
    return d


def _patch(pid="p-1", **kw):
    return Patch(patch_id=pid, generation=1, tipo="ajuste_factor", hipotesis="app_transporte subcotiza",
                 cambios=[ConfigChange(op="set", path="factores.uso.categorias.app_transporte", value=1.45)],
                 diff="app_transporte: 1.25 -> 1.45", metrics_after={"loss": 900.0}, **kw)


# ---------------------------------------------------------------- auth / health / CORS
def test_health_public_and_auth_required(ctx):
    client, _, _ = ctx
    assert client.get("/health").json()["ok"] is True
    assert client.post("/quote", json=_profile()).status_code == 401
    assert client.post("/quote", json=_profile(), headers={"X-API-Key": "mala"}).status_code == 401
    assert client.post("/quote", json=_profile(), headers=H).status_code == 200


def test_auth_disabled_without_key(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    s = Settings(api_key="", database_url=f"sqlite:///{tmp_path / 'a.db'}", lineage_dir=tmp_path / "l",
                 runs_dir=tmp_path / "r")
    client = TestClient(create_app(s, rsi_runner=FakeRunner()))
    assert client.post("/quote", json=_profile()).status_code == 200
    assert client.get("/health").json()["auth"] is False


def test_cors_preflight(ctx):
    client, _, _ = ctx
    r = client.options("/quote", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
                                          "Access-Control-Request-Headers": "X-API-Key"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") in ("*", "http://localhost:5173")


# ---------------------------------------------------------------- expedientes
def test_expediente_sample_mock_fast_and_persisted(ctx):
    client, _, _ = ctx
    t0 = time.perf_counter()
    r = client.post("/expedientes", files=_files("EXP-002"), data={"datos": _datos()}, headers=H)
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200, r.text
    assert elapsed < 2.0
    body = r.json()
    codigos = {a["codigo"] for a in body["alertas"]}
    assert "VIN_NO_COINCIDE" in codigos
    perfil = body["perfil"]
    assert (perfil["marca"], perfil["modelo"], perfil["anio"]) == ("Volkswagen", "Jetta", 2017)
    assert perfil["kilometraje"] == 85000 and perfil["siniestros_previos"] == 1
    assert {d["tipo"] for d in body["documentos"]} == {"factura", "tarjeta_circulacion", "poliza_anterior"}
    cot = body["cotizacion"]
    assert cot["output"]["prima"] > 0 and cot["agent_version"].startswith("cotizador@")
    # visual/valuación: se usan si existen; si no, quedan en `omitidos` sin romper
    assert set(body["omitidos"]) <= {"visual", "valuacion"}

    v = client.get(f"/vehicles/{body['vehicle_id']}", headers=H)
    assert v.status_code == 200
    vj = v.json()
    assert vj["perfil"]["id"] == body["vehicle_id"]
    assert len(vj["documentos"]) == 3
    assert [p["prediction_id"] for p in vj["predicciones"]] == [cot["prediction_id"]]


def test_expediente_deterministic_id_and_explicit_vehicle_id(ctx):
    client, _, _ = ctx
    a = client.post("/expedientes", files=_files("EXP-001"), data={"datos": _datos()}, headers=H).json()
    b = client.post("/expedientes", files=_files("EXP-001"), data={"datos": _datos()}, headers=H).json()
    assert a["vehicle_id"] == b["vehicle_id"]
    assert a["cotizacion"]["output"] == b["cotizacion"]["output"]
    c = client.post("/expedientes", files=_files("EXP-001"), data={"datos": _datos(), "vehicle_id": "VEH-X"},
                    headers=H).json()
    assert c["vehicle_id"] == "VEH-X"


def test_expediente_with_photos_does_not_break(ctx):
    client, _, _ = ctx
    files = _files("EXP-003") + [("fotos", ("defensa_trasera_rayon.png", b"\x89PNG fake", "image/png"))]
    r = client.post("/expedientes", files=files, data={"datos": _datos()}, headers=H)
    assert r.status_code == 200, r.text
    assert "DOCUMENTO_VENCIDO" in {a["codigo"] for a in r.json()["alertas"]}


def test_expediente_bad_inputs(ctx):
    client, _, _ = ctx
    assert client.post("/expedientes", files=_files("EXP-001"), data={"datos": "{no json"},
                       headers=H).status_code == 422
    assert client.post("/expedientes", files=_files("EXP-001"), data={"tipos": ["factura"]},
                       headers=H).status_code == 422
    assert client.post("/expedientes", files=_files("EXP-001"), data={"tipos": "factura,x,otro"},
                       headers=H).status_code == 422
    assert client.post("/expedientes", files=_files("EXP-001"), data={"datos": json.dumps({"uso": "taxi"})},
                       headers=H).status_code == 422


def test_expediente_explicit_tipos_comma_separated(ctx):
    client, _, _ = ctx
    files = [("docs", ("a.png", (DOCS / "EXP-001-FAC.png").read_bytes(), "image/png")),
             ("docs", ("b.png", (DOCS / "EXP-001-TC.png").read_bytes(), "image/png"))]
    r = client.post("/expedientes", files=files, data={"tipos": "factura,tarjeta_circulacion"}, headers=H)
    assert r.status_code == 200, r.text
    assert [d["tipo"] for d in r.json()["documentos"]] == ["factura", "tarjeta_circulacion"]


def test_infer_tipo():
    assert infer_tipo("EXP-001-FAC.png") == "factura"
    assert infer_tipo("tarjeta_circulacion.jpg") == "tarjeta_circulacion"
    assert infer_tipo("EXP-9-POL.pdf") == "poliza_anterior"
    assert infer_tipo("foto.png") == "otro"


def test_optional_modules_used_when_available(ctx, monkeypatch):
    from autoguard.agents import valuacion, visual
    from autoguard.contracts import Dano

    monkeypatch.setattr(visual, "inspect", lambda imgs, hints=None: [
        Dano(zona="defensa_trasera", tipo="rayon", costo_est=1500.0, confianza=0.9)])
    monkeypatch.setattr(valuacion, "valuate", lambda p: {"precio_estimado": 200000.0, "rango": [1, 2],
                                                         "comparables": [], "fuente": "mock"})
    client, _, _ = ctx
    files = _files("EXP-001") + [("fotos", ("f.png", b"x", "image/png"))]
    body = client.post("/expedientes", files=files, data={"datos": _datos()}, headers=H).json()
    assert body["omitidos"] == {}
    assert body["perfil"]["danos"][0]["costo_est"] == 1500.0
    assert body["valuacion"]["fuente"] == "mock"


# ---------------------------------------------------------------- quote
def test_quote_matches_champion_and_persists(ctx):
    client, settings, _ = ctx
    r = client.post("/quote", json=_profile(), headers=H)
    assert r.status_code == 200
    pred = r.json()
    from autoguard.agents.cotizador import quote
    from autoguard.contracts import VehicleProfile

    expected = quote(VehicleProfile(**_profile()), load_config(settings.base_config))
    assert pred["output"]["prima"] == pytest.approx(expected.prima)
    assert client.get("/vehicles/veh-sim-1", headers=H).json()["predicciones"][0]["prediction_id"] == \
        pred["prediction_id"]
    assert client.post("/quote", json=_profile(anio="x"), headers=H).status_code == 422
    assert client.get("/vehicles/nope", headers=H).status_code == 404


# ---------------------------------------------------------------- outcomes
def test_outcomes_ingestion_idempotent(ctx):
    client, _, _ = ctx
    pid = client.post("/quote", json=_profile(), headers=H).json()["prediction_id"]
    o1 = {"outcome_id": "o-1", "prediction_id": pid, "fuente": "simulador",
          "valor": {"vendida": True, "costo_real": 12000.0}}
    o2 = {"outcome_id": "o-2", "prediction_id": "pred-desconocida", "fuente": "taller", "valor": {"costo_real": 1}}
    r = client.post("/outcomes", json=[o1, o2, o1], headers=H).json()
    assert r == {"recibidos": 3, "guardados": 2, "duplicados": 1, "prediccion_desconocida": ["pred-desconocida"]}
    r2 = client.post("/outcomes", json=o1, headers=H).json()  # objeto suelto también vale
    assert r2["guardados"] == 0 and r2["duplicados"] == 1
    assert client.post("/outcomes", json={"outcome_id": "x"}, headers=H).status_code == 422


# ---------------------------------------------------------------- RSI / runs
def test_rsi_run_uses_runner_and_conflicts(ctx):
    client, _, runner = ctx
    r = client.post("/rsi/run", json={"seed": 7, "batches": 5}, headers=H)
    assert r.status_code == 202
    assert runner.calls == [{"seed": 7, "batches": 5, "batch_size": 200, "k": 3}]
    assert client.post("/rsi/run", headers=H).status_code == 409
    assert client.get("/rsi/run/job-fake", headers=H).json()["estado"] == "terminado"
    assert client.get("/rsi/run/otro", headers=H).status_code == 404


def test_subprocess_runner_builds_cli(tmp_path, monkeypatch):
    captured = {}

    class P:
        def poll(self):
            return None

    def fake_popen(cmd, **kw):
        captured["cmd"], captured["cwd"] = cmd, kw["cwd"]
        return P()

    monkeypatch.setattr(services.subprocess, "Popen", fake_popen)
    r = services.SubprocessRsiRunner(Settings(runs_dir=tmp_path))
    out = r({"seed": 42, "batch_size": 100})
    assert captured["cmd"][1:] == ["-m", "autoguard.rsi.loop", "--seed", "42", "--batch-size", "100"]
    assert out["estado"] == "corriendo" and r.status(out["job_id"])["estado"] == "corriendo"
    with pytest.raises(RuntimeError):
        r({"seed": 1})


def test_runs_latest(ctx):
    client, settings, _ = ctx
    assert client.get("/runs/latest", headers=H).status_code == 404
    _write_run(settings.runs_dir, "run-a", [_patch()])
    body = client.get("/runs/latest?incluir_curva=true", headers=H).json()
    assert body["run_id"] == "run-a" and body["n_parches"] == 1
    assert body["summary"]["regret"]["rsi"] == 1.0
    assert body["curva"][0]["variante"] == "rsi"
    assert "summary.json" in body["archivos"]


# ---------------------------------------------------------------- parches y versiones
def test_patches_from_run_then_approve_updates_champion(ctx):
    client, settings, _ = ctx
    _write_run(settings.runs_dir, "run-a", [_patch("p-1"), _patch("p-2", veredicto="rechazado")])
    lst = client.get("/patches", headers=H).json()
    assert lst["fuente"] == "run" and [p["patch_id"] for p in lst["patches"]] == ["p-1", "p-2"]
    assert [p["patch_id"] for p in client.get("/patches?veredicto=pendiente", headers=H).json()["patches"]] == ["p-1"]

    prima0 = client.post("/quote", json=_profile(), headers=H).json()
    r = client.post("/patches/p-1/approve", json={"razon": "ok actuario"}, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["patch"]["veredicto"] == "aceptado" and r.json()["patch"]["razon"] == "ok actuario"
    prima1 = client.post("/quote", json=_profile(), headers=H).json()
    assert prima1["agent_version"] != prima0["agent_version"]
    assert prima1["output"]["factores"]["uso"] == pytest.approx(1.45)

    # ahora la BD tiene parches → fuente db
    assert client.get("/patches", headers=H).json()["fuente"] == "db"
    hist = client.get("/versions/cotizador", headers=H).json()["versions"]
    assert len(hist) == 2 and hist[0]["estado"] == "campeon"
    rej = client.post("/patches/p-2/reject", json={"razon": "no convence"}, headers=H).json()["patch"]
    assert rej["veredicto"] == "rechazado" and rej["razon"] == "no convence"
    assert client.post("/patches/nope/approve", headers=H).status_code == 404


def test_invalid_patch_is_rejected_and_marked(ctx):
    client, settings, _ = ctx
    bad = Patch(patch_id="p-bad", generation=1, tipo="ajuste_factor", hipotesis="h",
                cambios=[ConfigChange(op="set", path="factores.uso.categorias.app_transporte", value=99.0)])
    _write_run(settings.runs_dir, "run-a", [bad])
    r = client.post("/patches/p-bad/approve", headers=H)
    assert r.status_code == 422
    assert client.get("/patches?veredicto=invalido", headers=H).json()["patches"][0]["patch_id"] == "p-bad"
    assert client.post("/patches/p-bad/approve", headers=H).status_code == 409
    assert len(client.get("/versions/cotizador", headers=H).json()["versions"]) == 1


def test_revert_restores_config(ctx):
    client, settings, _ = ctx
    _write_run(settings.runs_dir, "run-a", [_patch("p-1")])
    prima0 = client.post("/quote", json=_profile(), headers=H).json()
    sha0 = client.get("/versions/cotizador", headers=H).json()["versions"][0]["git_sha"]
    client.post("/patches/p-1/approve", headers=H)
    r = client.post(f"/versions/cotizador/revert/{sha0}", headers=H)
    assert r.status_code == 200, r.text
    prima2 = client.post("/quote", json=_profile(), headers=H).json()
    assert prima2["output"]["prima"] == pytest.approx(prima0["output"]["prima"])
    hist = client.get("/versions/cotizador", headers=H).json()["versions"]
    assert len(hist) == 3  # el historial conserva todo
    assert client.post("/versions/cotizador/revert/deadbeef", headers=H).status_code == 404
    assert client.post(f"/versions/otro/revert/{sha0}", headers=H).status_code == 404
