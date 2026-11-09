"""Tests del analista de errores (T-07). Datos sintéticos SIMULADOS, sin dependencias de otras tareas."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from autoguard import segments
from autoguard.evaluator.objective import loss
from autoguard.rsi.analista import analyze

MARCAS = ["Nissan", "Volkswagen", "Chevrolet", "Toyota", "Honda", "Kia"]


def synthetic_errors(n: int = 6000, seed: int = 0, plant: dict | None = None, bias: float = 0.0,
                     noise: float = 0.10) -> pd.DataFrame:
    """Errores del recolector con sesgo `bias` plantado en el segmento `plant` (resto ~0)."""
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "vehicle_id": [f"v{i}" for i in range(n)],
        "marca": rng.choice(MARCAS, n),
        "modelo": "X",
        "anio": rng.integers(1985, 2027, n),
        "kilometraje": rng.integers(0, 300_000, n),
        "siniestros_previos": rng.choice([0, 1, 2, 3], n, p=[0.6, 0.25, 0.1, 0.05]),
        "uso": rng.choice(["particular", "app_transporte", "comercial"], n, p=[0.6, 0.25, 0.15]),
        "zona": rng.choice(["CDMX", "EDOMEX", "JAL", "NL", "PUE", "OTRA"], n),
        "danos_costo": 0.0,
        "cobertura_verificacion": 1.0,
    })
    costo = rng.lognormal(np.log(10_000), 0.3, n)
    err = rng.normal(0.0, noise, n)
    if plant:
        err = err + np.where(segments.segment_mask(df, plant), bias, 0.0)
    prima = costo * (1 + err)
    return df.assign(prima=prima, costo_real=costo, loss=loss(prima, costo), error_rel=(prima - costo) / costo)


@pytest.mark.parametrize("plant,bias", [
    ({"uso": "app_transporte", "zona": "CDMX"}, -0.30),
    ({"antiguedad_min": 30, "siniestros_previos": 1}, 0.35),
    ({"marca": "Kia"}, -0.20),
    ({"kilometraje_min": 200_000}, -0.15),
])
def test_recovers_planted_segment_top1(plant, bias):
    hyps = analyze(synthetic_errors(plant=plant, bias=bias), top_k=3)
    assert hyps, "debe encontrar al menos una hipótesis"
    top = hyps[0]
    assert top.segmento == plant
    assert np.sign(top.sesgo_medio) == np.sign(bias)
    assert top.sesgo_medio == pytest.approx(bias, abs=0.05)
    assert top.p_value < 0.05 and top.n >= 30
    assert ("subcotiza" if bias < 0 else "sobrecotiza") in top.texto


def test_no_bias_no_hypotheses_or_few():
    hyps = analyze(synthetic_errors(seed=3, noise=0.05), top_k=3)
    # sin sesgo plantado: lo que pase el umbral por azar tiene sesgo pequeño
    assert all(abs(h.sesgo_medio) < 0.03 for h in hyps)


def test_redundancy_children_and_parents_skipped():
    plant = {"uso": "app_transporte", "zona": "CDMX"}
    df = synthetic_errors(plant=plant, bias=-0.30)
    hyps = analyze(df, top_k=5)
    masks = [segments.segment_mask(df, h.segmento) for h in hyps]
    for i in range(len(hyps)):
        for j in range(i):
            if np.sign(hyps[i].sesgo_medio) != np.sign(hyps[j].sesgo_medio):
                continue
            mi, mj = masks[i], masks[j]
            assert (mi & ~mj).any() and (mj & ~mi).any(), (hyps[i].segmento, hyps[j].segmento)


def test_min_n_and_top_k_and_sorted():
    df = synthetic_errors(plant={"marca": "Kia"}, bias=-0.2)
    hyps = analyze(df, top_k=2, min_n=200)
    assert len(hyps) <= 2
    assert all(h.n >= 200 for h in hyps)
    assert [h.impacto for h in hyps] == sorted([h.impacto for h in hyps], reverse=True)


def test_deterministic_and_json_safe():
    df = synthetic_errors(plant={"zona": "PUE"}, bias=0.25)
    a, b = analyze(df), analyze(df)
    assert [h.model_dump() for h in a] == [h.model_dump() for h in b]
    import json

    json.dumps([h.model_dump() for h in a])  # segmentos con tipos nativos


def test_robust_inputs():
    assert analyze(pd.DataFrame()) == []
    df = synthetic_errors(n=500, plant={"zona": "PUE"}, bias=0.3)
    # sin loss/error_rel: se derivan de prima y costo_real
    hyps = analyze(df.drop(columns=["loss", "error_rel"]))
    assert hyps and hyps[0].segmento == {"zona": "PUE"}
    # costo 0 (error_rel inf) no rompe
    df2 = df.copy()
    df2.loc[0, "costo_real"] = 0.0
    df2.loc[0, "error_rel"] = np.inf
    assert analyze(df2)[0].segmento == {"zona": "PUE"}
