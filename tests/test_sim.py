"""Tests del simulador de mercado (T-03). Datos SIMULADOS, sin red."""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from autoguard.config_schema import CotizadorConfig, load_config
from autoguard.contracts import VEHICLE_COLUMNS
from autoguard.segments import ANIO_REFERENCIA, segment_mask
from autoguard.sim.market import ANIO_MIN, MarketSimulator

CFG_PATH = Path(__file__).resolve().parents[1] / "configs" / "agents" / "cotizador.yaml"


def _quote_base_local(df: pd.DataFrame, cfg: CotizadorConfig) -> np.ndarray:
    """Doble local del cotizador (T-04): base × Π factores (último bin ≤ x), sin reglas."""
    p = np.full(len(df), cfg.base)
    for f in cfg.factores.values():
        col = (ANIO_REFERENCIA - df["anio"]) if f.variable == "antiguedad" else df[f.variable]
        if f.categorias is not None:
            p *= col.map(f.categorias).fillna(f.default).to_numpy(dtype=float)
        else:
            idx = np.searchsorted(f.bins, col.to_numpy(dtype=float), side="right") - 1
            vals = np.asarray(f.valores)
            p *= np.where(idx < 0, f.default, vals[np.clip(idx, 0, None)])
    return p


def _quote(df: pd.DataFrame, cfg: CotizadorConfig) -> np.ndarray:
    try:
        from autoguard.agents.cotizador import quote_df

        return np.asarray(quote_df(df, cfg), dtype=float)
    except NotImplementedError:
        return _quote_base_local(df, cfg)


def test_columnas_y_rangos():
    b = MarketSimulator(1).sample_batch(2000)
    assert list(b.columns) == VEHICLE_COLUMNS
    assert len(b) == 2000 and b["vehicle_id"].is_unique
    assert b["anio"].between(ANIO_MIN, ANIO_REFERENCIA).all()
    assert (b["kilometraje"] >= 0).all() and (b["siniestros_previos"] >= 0).all()
    assert set(b["uso"]) <= {"particular", "app_transporte", "comercial"}
    assert set(b["zona"]) <= {"CDMX", "EDOMEX", "JAL", "NL", "PUE", "OTRA"}
    assert b["cobertura_verificacion"].between(0, 1).all()
    assert (b["danos_costo"] >= 0).all()
    # hay clásicos (>30 años) suficientes para la interacción oculta
    assert ((ANIO_REFERENCIA - b["anio"]) >= 30).sum() > 50


def test_km_correlacionado_con_antiguedad():
    b = MarketSimulator(2).sample_batch(5000)
    corr = np.corrcoef(ANIO_REFERENCIA - b["anio"], b["kilometraje"])[0, 1]
    assert corr > 0.5


def test_misma_semilla_misma_secuencia():
    s1, s2 = MarketSimulator(7), MarketSimulator(7)
    for _ in range(3):
        b1, b2 = s1.sample_batch(500), s2.sample_batch(500)
        pd.testing.assert_frame_equal(b1, b2)
        p = np.full(len(b1), 9000.0)
        pd.testing.assert_frame_equal(s1.resolve(b1, p), s2.resolve(b2, p))
    # lotes sucesivos son distintos y semillas distintas también
    s = MarketSimulator(7)
    a, b = s.sample_batch(100), s.sample_batch(100)
    assert not a["vehicle_id"].isin(b["vehicle_id"]).any()
    assert not MarketSimulator(8).sample_batch(100)["anio"].equals(MarketSimulator(7).sample_batch(100)["anio"])


def test_costo_real_independiente_de_primas():
    s = MarketSimulator(3)
    b = s.sample_batch(1000)
    r_bajo = s.resolve(b, np.full(len(b), 100.0))
    r_alto = s.resolve(b, np.full(len(b), 1e6))
    np.testing.assert_array_equal(r_bajo["costo_real"], r_alto["costo_real"])
    assert r_bajo["vendida"].all() and not r_alto["vendida"].any()
    assert list(r_bajo.columns) == ["vehicle_id", "vendida", "costo_real"]
    assert r_bajo["vendida"].dtype == bool


def test_costo_real_no_depende_del_orden_del_lote():
    s = MarketSimulator(4)
    b = s.sample_batch(300)
    p = np.full(len(b), 9000.0)
    r = s.resolve(b, p).set_index("vehicle_id")
    perm = b.sample(frac=1.0, random_state=0).reset_index(drop=True)
    r2 = s.resolve(perm, p).set_index("vehicle_id")
    pd.testing.assert_series_equal(r["costo_real"], r2.loc[r.index, "costo_real"])


def test_ruido_lognormal_moderado_e_insesgado():
    s = MarketSimulator(5)
    b = s.sample_batch(20000)
    esperado = s.oracle_expected_cost(b)
    r = s.resolve(b, np.zeros(len(b)))
    ratio = r["costo_real"].to_numpy() / esperado
    assert abs(ratio.mean() - 1.0) < 0.01
    sigma = np.log(ratio).std()
    assert 0.15 <= sigma <= 0.25


def test_demanda_responde_al_precio():
    s = MarketSimulator(6)
    b = s.sample_batch(5000)
    esperado = s.oracle_expected_cost(b)
    tasa = [s.resolve(b, esperado * k)["vendida"].mean() for k in (0.8, 1.0, 1.3)]
    assert tasa[0] > tasa[1] > tasa[2]
    assert 0.3 < tasa[1] < 0.9


def test_cotizador_base_tiene_sesgos_por_segmento():
    """≥3 segmentos con sesgo medio |prima/oracle - 1| > 10%: el RSI tiene qué descubrir."""
    cfg = load_config(CFG_PATH)
    s = MarketSimulator(42)
    b = s.sample_batch(20000)
    oracle = s.oracle_expected_cost(b)
    primas = _quote(b, cfg)
    assert abs((primas / oracle - 1).mean()) < 0.10  # calibrado en promedio…
    segmentos = [
        {"uso": "app_transporte"},  # factor mal calibrado
        {"uso": "app_transporte", "zona": "CDMX"},  # interacción
        {"antiguedad_min": 30, "siniestros_previos": 1},  # interacción (sobrecotiza)
        {"siniestros_previos_min": 2},  # factor mal calibrado
        {"marca": "BMW"},  # variable no usada
        {"danos_costo_min": 10000},  # variable no usada
    ]
    sesgados = []
    for seg in segmentos:
        m = segment_mask(b, seg)
        assert m.sum() >= 30, seg
        sesgo = float((primas[m] / oracle[m] - 1).mean())
        if abs(sesgo) > 0.10:
            sesgados.append((seg, sesgo))
    assert len(sesgados) >= 3, sesgados  # …pero sesgado por segmento
    # la interacción de clásicos con 1 siniestro va en dirección contraria (sobrecotiza)
    m = segment_mask(b, {"antiguedad_min": 30, "siniestros_previos": 1})
    assert (primas[m] / oracle[m] - 1).mean() > 0.10


def test_oracle_no_depende_de_columnas_extra():
    s = MarketSimulator(9)
    b = s.sample_batch(100)
    b2 = b.assign(prima=1.0, genero="x")
    np.testing.assert_array_equal(s.oracle_expected_cost(b), s.oracle_expected_cost(b2))


def test_resolve_valida_forma_de_primas():
    s = MarketSimulator(10)
    b = s.sample_batch(10)
    with pytest.raises(ValueError):
        s.resolve(b, np.ones(5))


def test_rendimiento_lote_1000():
    s = MarketSimulator(11)
    s.sample_batch(1000)  # calentamiento
    t = time.perf_counter()
    b = s.sample_batch(1000)
    s.resolve(b, s.oracle_expected_cost(b))
    assert time.perf_counter() - t < 0.05
