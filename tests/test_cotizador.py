"""Tests del cotizador base (T-04). Datos SIMULADOS."""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from autoguard.agents import cotizador as cz
from autoguard.config_schema import apply_changes, load_config
from autoguard.contracts import ConfigChange, Dano, VehicleProfile

CFG_PATH = Path(__file__).resolve().parents[1] / "configs" / "agents" / "cotizador.yaml"
MARCAS = ["Nissan", "Volkswagen", "Chevrolet", "Toyota", "Honda", "Kia", "Mazda", "Ford"]
USOS = ["particular", "app_transporte", "comercial"]
ZONAS = ["CDMX", "EDOMEX", "JAL", "NL", "PUE", "OTRA"]


@pytest.fixture(scope="module")
def cfg():
    return load_config(CFG_PATH)


@pytest.fixture(scope="module")
def cfg_rich(cfg):
    """Config con reglas, factor categórico sobre marca y numérico sobre danos_costo."""
    return apply_changes(cfg, [
        ConfigChange(op="add_rule", value={"id": "viejo_1sin", "segmento": {"antiguedad_min": 30,
                     "siniestros_previos": 1}, "multiplicador": 0.8}),
        ConfigChange(op="add_rule", value={"id": "app_cdmx", "segmento": {"uso": "app_transporte",
                     "zona": "CDMX"}, "multiplicador": 1.25}),
        ConfigChange(op="add_factor", path="marca", value={"variable": "marca",
                     "categorias": {"Nissan": 1.05, "Toyota": 0.9}}),
        ConfigChange(op="add_factor", path="danos", value={"variable": "danos_costo",
                     "bins": [1000, 20000], "valores": [1.05, 1.2]}),
    ])


def _profiles(n: int, seed: int = 7) -> list[VehicleProfile]:
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        anio = int(rng.integers(1985, 2027))
        danos = [Dano(zona="defensa", tipo="rayon", costo_est=float(rng.choice([0, 500, 5000, 30000])),
                      confianza=0.9)] if rng.random() < 0.5 else []
        out.append(VehicleProfile(
            id=f"v{i}", marca=str(rng.choice(MARCAS)), modelo="X", anio=anio,
            kilometraje=int(rng.integers(0, 350000)), siniestros_previos=int(rng.integers(0, 4)),
            uso=str(rng.choice(USOS)), zona=str(rng.choice(ZONAS)), danos=danos,
            cobertura_verificacion=float(rng.random()),
        ))
    return out


def _p(**kw) -> VehicleProfile:
    base = dict(id="v", marca="Nissan", modelo="Versa", anio=2020, kilometraje=60000,
                siniestros_previos=0, uso="particular", zona="JAL")
    base.update(kw)
    return VehicleProfile(**base)


def test_quote_hand_computed(cfg):
    # antiguedad 6 -> 1.0; km 60000 -> 1.0; sin 0 -> 1.0; particular 1.0; JAL 1.0
    q = cz.quote(_p(), cfg)
    assert q.prima == pytest.approx(9000.0)
    assert q.factores == {}
    # antiguedad 31 -> 1.2; km 250k -> 1.15; sin 2 -> 1.3; app 1.15; CDMX 1.1
    q = cz.quote(_p(anio=1995, kilometraje=250000, siniestros_previos=2, uso="app_transporte",
                    zona="CDMX"), cfg)
    assert q.prima == pytest.approx(9000 * 1.2 * 1.15 * 1.3 * 1.15 * 1.1)
    assert q.factores == pytest.approx({"antiguedad": 1.2, "kilometraje": 1.15, "siniestros_previos": 1.3,
                                        "uso": 1.15, "zona": 1.1})


def test_bin_boundaries(cfg):
    f = cfg.factores["kilometraje"]
    assert cz._factor_value(f, 49999) == 0.95
    assert cz._factor_value(f, 50000) == 1.0
    assert cz._factor_value(f, 10**7) == 1.15
    assert cz._factor_value(f, -1) == f.default  # por debajo del primer bin
    assert cz._factor_value(f, None) == f.default


def test_rules_and_explicability(cfg_rich):
    q = cz.quote(_p(anio=1990, siniestros_previos=1, uso="app_transporte", zona="CDMX", marca="Toyota"),
                 cfg_rich)
    assert q.factores["regla:viejo_1sin"] == 0.8
    assert q.factores["regla:app_cdmx"] == 1.25
    assert q.factores["marca"] == 0.9
    assert "danos" not in q.factores  # danos_costo 0 < 1000 -> default 1.0
    expected = 9000 * np.prod(list(q.factores.values()))
    assert q.prima == pytest.approx(expected)


def test_interval_and_confidence(cfg):
    full = cz.quote(_p(cobertura_verificacion=1.0), cfg)
    assert full.intervalo == pytest.approx((9000 * 0.88, 9000 * 1.12))
    low = cz.quote(_p(cobertura_verificacion=0.0), cfg)
    assert low.intervalo == pytest.approx((9000 * 0.76, 9000 * 1.24))
    assert full.confianza > low.confianza


def test_missing_column_uses_default(cfg_rich):
    df = cz.profiles_df(_profiles(50)).drop(columns=["marca", "zona"])
    p = cz.quote_df(df, cfg_rich)
    full = cz.profiles_df(_profiles(50)).assign(marca="__otra__", zona="__otra__")
    # zona ausente -> default 1.0 ; marca ausente -> default 1.0 ; la regla app_cdmx (zona) no aplica
    assert np.allclose(p, cz.quote_df(full, cfg_rich))


def test_quote_and_quote_df_match_1000(cfg_rich):
    profiles = _profiles(1000)
    vec = cz.quote_df(cz.profiles_df(profiles), cfg_rich)
    one = np.array([cz.quote(p, cfg_rich).prima for p in profiles])
    assert np.allclose(vec, one, rtol=0, atol=1e-6)


def test_quote_df_without_antiguedad_column(cfg_rich):
    df = cz.profiles_df(_profiles(200))
    assert np.allclose(cz.quote_df(df, cfg_rich), cz.quote_df(df.drop(columns=["antiguedad"]), cfg_rich))


def test_quote_df_100k_under_1s(cfg_rich):
    df = cz.profiles_df(_profiles(1000))
    big = pd.concat([df] * 100, ignore_index=True)
    cz.quote_df(big.head(10), cfg_rich)  # calentamiento
    t0 = time.perf_counter()
    out = cz.quote_df(big, cfg_rich)
    assert time.perf_counter() - t0 < 1.0
    assert out.shape == (100_000,) and np.all(out > 0)


def test_predict_deterministic(cfg):
    p = _p(danos=[Dano(zona="cofre", tipo="abolladura", costo_est=3000, confianza=0.8)])
    a = cz.predict(p, cfg, "cotizador@abc1234")
    b = cz.predict(p, cfg, "cotizador@abc1234")
    assert a.input_hash == b.input_hash and len(a.input_hash) == 64
    assert a.prediction_id == b.prediction_id
    assert a.vehicle_id == "v" and a.agent_version == "cotizador@abc1234"
    assert a.output == cz.quote(p, cfg)
    assert cz.predict(_p(kilometraje=1), cfg, "cotizador@abc1234").input_hash != a.input_hash
    assert cz.predict(p, cfg, "cotizador@def5678").prediction_id != a.prediction_id
