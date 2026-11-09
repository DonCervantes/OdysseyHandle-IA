"""Tests SIMULADOS del dictamen preliminar (T-26 / RF-15). Sin red."""
from __future__ import annotations

from fastapi.testclient import TestClient

from autoguard.agents.dictamen import dictaminar, dictaminar_desde_hints
from autoguard.api.main import create_app
from autoguard.api.services import Settings
from autoguard.contracts import Dano, VehicleProfile


def _perfil(**kwargs) -> VehicleProfile:
    base = dict(
        id="veh-sim-dictamen",
        marca="Nissan",
        modelo="Versa",
        anio=2019,
        kilometraje=45000,
        siniestros_previos=0,
        uso="particular",
        zona="CDMX",
        danos=[],
    )
    base.update(kwargs)
    return VehicleProfile(**base)


def test_siniestro_legitimo_solo_danos_nuevos():
    """Choque nuevo en cofre; el perfil no tenía ese daño → limpio / sin bandera alta."""
    perfil = _perfil(
        danos=[Dano(zona="puerta_trasera_der", tipo="rayon", costo_est=1900, confianza=0.9)]
    )
    reclamados = [
        Dano(zona="cofre", tipo="abolladura", costo_est=3500, confianza=0.9),
        Dano(zona="faro_der", tipo="estrellado", costo_est=2500, confianza=0.85),
    ]
    r = dictaminar(perfil, danos_reclamados=reclamados, relato_zonas=["cofre", "faro_der"])
    assert r.simulados is True
    assert len(r.danos_nuevos) == 2
    assert r.danos_preexistentes == []
    assert r.costo_siniestro_est == 6000
    assert r.severidad == "limpio"
    assert not any(b.codigo == "DANO_PREEXISTENTE_RECLAMADO" for b in r.banderas)


def test_montachoques_dano_preexistente_reclamado():
    """Defensa trasera ya registrada se vuelve a reclamar → sospechoso."""
    perfil = _perfil(
        danos=[
            Dano(zona="defensa_trasera", tipo="abolladura", costo_est=2800, confianza=1.0),
        ]
    )
    r = dictaminar_desde_hints(
        perfil,
        foto_hints=["FOTO-001.png"],  # ground truth: defensa_trasera / abolladura
        relato_zonas=["defensa_trasera"],
    )
    assert r.danos_preexistentes
    assert r.danos_nuevos == []
    assert r.costo_siniestro_est == 0
    assert r.severidad == "sospechoso"
    codigos = {b.codigo for b in r.banderas}
    assert "DANO_PREEXISTENTE_RECLAMADO" in codigos
    assert "SOLO_PREEXISTENTES" in codigos


def test_zona_incompatible_y_monto_atipico():
    perfil = _perfil()
    reclamados = [Dano(zona="parabrisas", tipo="estrellado", costo_est=3200, confianza=0.9)]
    r = dictaminar(
        perfil,
        danos_reclamados=reclamados,
        relato_zonas=["toldo"],
        monto_declarado=50_000,
    )
    codigos = {b.codigo for b in r.banderas}
    assert "ZONA_INCOMPATIBLE" in codigos
    assert "MONTO_ATIPICO" in codigos
    assert r.severidad == "sospechoso"
    assert r.danos_nuevos == reclamados


def test_api_dictamen_json(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("AUTOGUARD_API_KEY", "")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/d.db")
    client = TestClient(create_app(Settings.from_env()))
    perfil = _perfil(
        danos=[Dano(zona="defensa_trasera", tipo="abolladura", costo_est=2800, confianza=1.0)]
    )
    payload = {
        "perfil": perfil.model_dump(mode="json"),
        "danos_reclamados": [
            {"zona": "defensa_trasera", "tipo": "abolladura", "costo_est": 2800, "confianza": 0.9}
        ],
        "relato_zonas": ["defensa_trasera"],
    }
    res = client.post("/dictamen", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["severidad"] == "sospechoso"
    assert body["simulados"] is True
    assert any(b["codigo"] == "DANO_PREEXISTENTE_RECLAMADO" for b in body["banderas"])
