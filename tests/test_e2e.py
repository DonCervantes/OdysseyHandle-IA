"""Prueba de punta a punta vía API (T-25). Datos SIMULADOS.

expediente EXP-001 → perfil + cotización → outcomes simulados → corrida RSI pequeña (en proceso) →
GET /patches → aprobar parche → la cotización del mismo auto cambia y registra la nueva agent_version →
revertir a la versión original → la cotización vuelve a la original.

Sin red ni llaves: LLM en mock, BD SQLite temporal, linaje y corridas en tmp_path.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from autoguard.agents import documental, visual  # noqa: F401 — importación en frío fuera del flujo cronometrado
from autoguard.agents.cotizador import quote
from autoguard.api.main import create_app
from autoguard.api.services import Settings
from autoguard.config_schema import apply_patch, load_config
from autoguard.contracts import Patch, VehicleProfile
from autoguard.rsi.loop import run_experiment

REPO = Path(__file__).resolve().parents[1]
DOCS = REPO / "data" / "samples" / "docs"
FOTOS = REPO / "data" / "samples" / "fotos"
KEY = "e2e-key-SIMULADA"
H = {"X-API-Key": KEY}
RSI_PARAMS = {"seed": 42, "batches": 3, "batch_size": 50, "k": 3}  # una generación, corrida pequeña


class InProcessRsiRunner:
    """Sustituye al SubprocessRsiRunner: ejecuta el ciclo RSI en proceso, escribiendo en runs_dir."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.jobs: dict[str, dict] = {}

    def __call__(self, params: dict) -> dict:
        job_id = f"job-e2e-{len(self.jobs) + 1}"
        out = self.settings.runs_dir / f"sim-{params['seed']}-{job_id}"
        summary = run_experiment(output_dir=out, **params)
        self.jobs[job_id] = {"job_id": job_id, "estado": "terminado", "params": params,
                             "run_dir": str(out), "summary": summary}
        return self.jobs[job_id]

    def status(self, job_id: str):
        return self.jobs.get(job_id)


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DATABASE_URL"):
        monkeypatch.delenv(var, raising=False)
    settings = Settings(
        api_key=KEY,
        database_url=f"sqlite:///{tmp_path / 'e2e.db'}",
        lineage_dir=tmp_path / "lineage",
        runs_dir=tmp_path / "runs",
    )
    return TestClient(create_app(settings, rsi_runner=InProcessRsiRunner(settings))), settings


def _expediente_files():
    files = [("docs", (f"EXP-001-{s}.png", (DOCS / f"EXP-001-{s}.png").read_bytes(), "image/png"))
             for s in ("FAC", "TC", "POL")]
    files.append(("fotos", ("FOTO-001.png", (FOTOS / "FOTO-001.png").read_bytes(), "image/png")))
    return files


def _elegir_parche(patches: list[dict], perfil: VehicleProfile, base_cfg) -> tuple[Patch, float]:
    """Primer parche (por id: la API resuelve ids por primera aparición) no inválido que cambie la prima
    del auto de prueba; se prefieren los `aceptado` por el evaluador."""
    prima_base = quote(perfil, base_cfg).prima
    vistos: set[str] = set()
    candidatos: list[Patch] = []
    for d in patches:
        if d["patch_id"] in vistos:
            continue
        vistos.add(d["patch_id"])
        p = Patch.model_validate(d)
        if p.veredicto != "invalido":
            candidatos.append(p)
    candidatos.sort(key=lambda p: p.veredicto != "aceptado")  # estable: aceptados primero
    for p in candidatos:
        try:
            prima = quote(perfil, apply_patch(base_cfg, p)).prima
        except Exception:  # noqa: BLE001 — un parche que no aplica no sirve para la prueba
            continue
        if abs(prima - prima_base) > 1e-6:
            return p, prima
    pytest.fail(f"ningún parche de la corrida cambia la prima del auto de prueba: "
                f"{[(p.patch_id, p.veredicto, p.diff) for p in candidatos]}")


def test_end_to_end_expediente_rsi_approve_revert(ctx):
    client, settings = ctx
    t0 = time.perf_counter()
    assert client.get("/health").json()["llm"] == "mock"

    # 1) expediente EXP-001 → perfil + cotización
    datos = {"kilometraje": 60000, "siniestros_previos": 1, "uso": "particular", "zona": "CDMX"}
    r = client.post("/expedientes", files=_expediente_files(), data={"datos": json.dumps(datos)}, headers=H)
    assert r.status_code == 200, r.text
    exp = r.json()
    perfil_d = exp["perfil"]
    assert (perfil_d["marca"], perfil_d["modelo"], perfil_d["anio"]) == ("Nissan", "Versa", 2019)
    assert perfil_d["kilometraje"] == 60000 and perfil_d["siniestros_previos"] == 1
    assert perfil_d["zona"] == "CDMX" and perfil_d["uso"] == "particular"
    assert {d["tipo"] for d in exp["documentos"]} == {"factura", "tarjeta_circulacion", "poliza_anterior"}
    assert perfil_d["danos"], "la foto de muestra debería producir daños en el perfil"
    cot0 = exp["cotizacion"]
    assert cot0["output"]["prima"] > 0
    assert cot0["vehicle_id"] == exp["vehicle_id"] == perfil_d["id"]
    v0 = cot0["agent_version"]
    assert v0.startswith("cotizador@")
    perfil = VehicleProfile.model_validate(perfil_d)
    base_cfg = load_config(settings.base_config)
    assert cot0["output"]["prima"] == pytest.approx(quote(perfil, base_cfg).prima)

    versiones0 = client.get("/versions/cotizador", headers=H).json()["versions"]
    assert len(versiones0) == 1
    sha0 = versiones0[0]["git_sha"]
    assert v0 == f"cotizador@{sha0[:7]}"

    # la cotización vía /quote con el mismo perfil coincide con la del expediente
    q0 = client.post("/quote", json=perfil_d, headers=H)
    assert q0.status_code == 200, q0.text
    q0 = q0.json()
    assert q0["output"]["prima"] == pytest.approx(cot0["output"]["prima"])
    assert q0["agent_version"] == v0

    # 2) outcomes simulados (idempotentes)
    outcomes = [
        {"outcome_id": "e2e-o-1", "prediction_id": cot0["prediction_id"], "fuente": "simulador",
         "valor": {"vendida": True, "costo_real": 12500.0}},
        {"outcome_id": "e2e-o-2", "prediction_id": q0["prediction_id"], "fuente": "simulador",
         "valor": {"vendida": False, "costo_real": 9800.0}},
    ]
    r = client.post("/outcomes", json=outcomes, headers=H)
    assert r.status_code == 200, r.text
    assert r.json() == {"recibidos": 2, "guardados": 2, "duplicados": 0, "prediccion_desconocida": []}
    assert client.post("/outcomes", json=outcomes[0], headers=H).json()["duplicados"] == 1

    # 3) corrida RSI pequeña (en proceso, sobre settings.runs_dir)
    r = client.post("/rsi/run", json=RSI_PARAMS, headers=H)
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["estado"] == "terminado" and job["params"] == RSI_PARAMS
    assert client.get(f"/rsi/run/{job['job_id']}", headers=H).json()["estado"] == "terminado"
    run_dir = Path(job["run_dir"])
    assert (run_dir / "summary.json").is_file() and (run_dir / "patches.jsonl").is_file()
    latest = client.get("/runs/latest", headers=H).json()
    assert latest["run_id"] == run_dir.name
    assert latest["summary"]["simulados"] is True and latest["summary"]["seed"] == RSI_PARAMS["seed"]
    assert latest["n_parches"] > 0

    # 4) GET /patches (desde la corrida: la BD aún no tiene parches)
    lst = client.get("/patches", headers=H).json()
    assert lst["fuente"] == "run"
    assert len(lst["patches"]) == latest["n_parches"]
    patch, prima_esperada = _elegir_parche(lst["patches"], perfil, base_cfg)

    # 5) aprobar el parche → nuevo campeón en el linaje
    r = client.post(f"/patches/{patch.patch_id}/approve", json={"razon": "e2e actuario"}, headers=H)
    assert r.status_code == 200, r.text
    ap = r.json()
    assert ap["patch"]["patch_id"] == patch.patch_id
    assert ap["patch"]["veredicto"] == "aceptado" and ap["patch"]["razon"] == "e2e actuario"
    v1 = ap["version"]["id"]
    assert ap["version"]["estado"] == "campeon" and v1 != v0
    versiones1 = client.get("/versions/cotizador", headers=H).json()["versions"]
    assert len(versiones1) == 2
    assert f"cotizador@{versiones1[0]['git_sha'][:7]}" == v1

    # 6) la cotización del mismo auto cambia y registra la nueva agent_version
    q1 = client.post("/quote", json=perfil_d, headers=H)
    assert q1.status_code == 200, q1.text
    q1 = q1.json()
    assert q1["agent_version"] == v1
    assert q1["output"]["prima"] == pytest.approx(prima_esperada)
    assert q1["output"]["prima"] != pytest.approx(q0["output"]["prima"])
    preds = client.get(f"/vehicles/{exp['vehicle_id']}", headers=H).json()["predicciones"]
    por_id = {p["prediction_id"]: p["agent_version"] for p in preds}
    assert por_id[q1["prediction_id"]] == v1 and por_id[cot0["prediction_id"]] == v0

    # 7) revertir a la versión original → la cotización vuelve a la original
    r = client.post(f"/versions/cotizador/revert/{sha0}", headers=H)
    assert r.status_code == 200, r.text
    v2 = r.json()["version"]["id"]
    assert v2 != v1
    q2 = client.post("/quote", json=perfil_d, headers=H)
    assert q2.status_code == 200, q2.text
    q2 = q2.json()
    assert q2["agent_version"] == v2
    assert q2["output"]["prima"] == pytest.approx(q0["output"]["prima"])
    assert q2["output"]["factores"] == pytest.approx(q0["output"]["factores"])
    assert len(client.get("/versions/cotizador", headers=H).json()["versions"]) == 3  # linaje completo

    # Aceptación: < 60 s en modo mock. AUTOGUARD_E2E_MAX_SECONDS permite holgura en máquinas saturadas.
    limite = float(os.environ.get("AUTOGUARD_E2E_MAX_SECONDS", "60"))
    assert time.perf_counter() - t0 < limite
