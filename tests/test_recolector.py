"""Tests del recolector (datos SIMULADOS, sin red)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from autoguard.contracts import VEHICLE_COLUMNS
from autoguard.evaluator.objective import loss
from autoguard.rsi.recolector import collect


def _preds(n: int = 6) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    return pd.DataFrame({
        "prediction_id": [f"p{i}" for i in range(n)],
        "vehicle_id": [f"v{i}" for i in range(n)],
        "agent_version": "cotizador@abc1234",
        "prima": 10_000.0 + 1000 * np.arange(n),
        "marca": "Nissan", "modelo": "Versa",
        "anio": rng.integers(1990, 2026, n), "kilometraje": rng.integers(0, 300_000, n),
        "siniestros_previos": 0, "uso": "particular", "zona": "CDMX",
        "danos_costo": 0.0, "cobertura_verificacion": 1.0,
    })


def test_basic_join_and_metrics():
    preds = _preds(4)
    outs = pd.DataFrame({
        "prediction_id": ["p0", "p1", "p2", "p3"],
        "vendida": [True, False, True, True],
        "costo_real": [12_000.0, 5_000.0, 10_000.0, 13_000.0],
    })
    df = collect(preds, outs)
    assert list(df["prediction_id"]) == ["p0", "p2", "p3"]
    assert set(VEHICLE_COLUMNS) <= set(df.columns)
    assert {"prima", "agent_version", "costo_real", "loss", "error_rel"} <= set(df.columns)
    np.testing.assert_allclose(df["loss"], loss(df["prima"], df["costo_real"]))
    row = df.set_index("prediction_id").loc["p0"]
    assert row["loss"] == pytest.approx(1.5 * 2000)  # subcotiza: ALPHA
    assert row["error_rel"] == pytest.approx((10_000 - 12_000) / 12_000)
    row = df.set_index("prediction_id").loc["p2"]
    assert row["loss"] == pytest.approx(2000) and row["error_rel"] == pytest.approx(0.2)


def test_missing_outcomes_are_dropped():
    df = collect(_preds(5), pd.DataFrame({"prediction_id": ["p1"], "vendida": [True], "costo_real": [9000.0]}))
    assert list(df["prediction_id"]) == ["p1"]


def test_duplicate_outcomes_keep_latest_by_observed_at():
    outs = pd.DataFrame({
        "prediction_id": ["p0", "p0", "p0"],
        "vendida": [True, True, True],
        "costo_real": [1.0, 3.0, 2.0],
        "observed_at": pd.to_datetime(["2026-01-01", "2026-03-01", "2026-02-01"], utc=True),
    })
    df = collect(_preds(2), outs)
    assert len(df) == 1 and df["costo_real"].iloc[0] == 3.0


def test_duplicate_outcomes_without_timestamp_keep_last():
    outs = pd.DataFrame({"prediction_id": ["p0", "p0"], "vendida": [False, True], "costo_real": [np.nan, 7000.0]})
    df = collect(_preds(2), outs)
    assert len(df) == 1 and df["costo_real"].iloc[0] == 7000.0


def test_duplicate_predictions_do_not_duplicate_rows():
    preds = pd.concat([_preds(2), _preds(2).iloc[[0]]], ignore_index=True)
    df = collect(preds, pd.DataFrame({"prediction_id": ["p0"], "vendida": [True], "costo_real": [9000.0]}))
    assert len(df) == 1


def test_dirty_values():
    outs = pd.DataFrame({
        "prediction_id": ["p0", "p1", "p2", "p3", "p4"],
        "vendida": ["true", None, 1, True, "False"],
        "costo_real": [9000.0, 9000.0, None, 0.0, 9000.0],
    })
    df = collect(_preds(5), outs)
    # p1 vendida None, p2 costo faltante, p3 costo 0, p4 "False"
    assert list(df["prediction_id"]) == ["p0"]
    assert np.isfinite(df["error_rel"]).all()


def test_valor_dict_format():
    outs = pd.DataFrame({
        "prediction_id": ["p0", "p1"],
        "fuente": "simulador",
        "valor": [{"vendida": True, "costo_real": 11_000.0}, {"vendida": False}],
    })
    df = collect(_preds(2), outs)
    assert list(df["prediction_id"]) == ["p0"] and df["costo_real"].iloc[0] == 11_000.0


def test_missing_outcome_columns_and_empty_inputs():
    df = collect(_preds(3), pd.DataFrame({"prediction_id": ["p0"]}))
    assert df.empty
    df = collect(_preds(3), pd.DataFrame(columns=["prediction_id", "vendida", "costo_real"]))
    assert df.empty and {"loss", "error_rel", "prima"} <= set(df.columns)


def test_does_not_mutate_inputs_and_ignores_stale_columns_in_predictions():
    preds = _preds(2)
    preds["costo_real"] = -1.0  # columna rancia en predicciones no debe ganar
    outs = pd.DataFrame({"prediction_id": ["p0", "p1"], "vendida": [True, True], "costo_real": [8000.0, 9000.0]})
    before_p, before_o = preds.copy(), outs.copy()
    df = collect(preds, outs)
    assert list(df["costo_real"]) == [8000.0, 9000.0]
    pd.testing.assert_frame_equal(preds, before_p)
    pd.testing.assert_frame_equal(outs, before_o)
