"""Tests de la capa de datos (SQLite en memoria, sin red). Datos SIMULADOS."""
from __future__ import annotations

import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import inspect

from autoguard.contracts import (
    AgentVersion,
    ConfigChange,
    Dano,
    DocExtraction,
    MetaStrategy,
    Outcome,
    Patch,
    Prediction,
    QuoteOutput,
    VehicleProfile,
)
from autoguard.db import repo, session as dbs
from autoguard.db.models import ALL_TABLES, Base, VehicleRow


@pytest.fixture()
def s():
    dbs.dispose_all()
    sess = dbs.get_session("sqlite://")
    yield sess
    sess.close()
    dbs.dispose_all()


def _vehicle(i: int) -> VehicleProfile:
    return VehicleProfile(
        id=f"v{i}", marca="Nissan", modelo="Versa", anio=2015, kilometraje=90000 + i, siniestros_previos=1,
        uso="app_transporte", zona="CDMX", danos=[Dano(zona="defensa", tipo="rayon", costo_est=1500, confianza=0.9)],
    )


def _pred(i: int, vid: str = "v0", version: str = "cotizador@abc1234") -> Prediction:
    return Prediction(
        prediction_id=f"p{i}", vehicle_id=vid, agent_version=version, input_hash=f"h{i}",
        output=QuoteOutput(prima=10000 + i, intervalo=(9000 + i, 11000 + i), factores={"uso": 1.2}),
    )


def test_all_tables_created(s):
    names = set(inspect(s.get_bind()).get_table_names())
    assert set(ALL_TABLES) <= names and len(ALL_TABLES) == 8


def test_migration_sql_has_all_tables():
    sql = Path(__file__).resolve().parents[1].joinpath("db/migrations/001_init.sql").read_text()
    created = set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", sql))
    assert created == set(ALL_TABLES) == set(Base.metadata.tables)


def test_vehicle_roundtrip_and_upsert(s):
    v = _vehicle(0)
    repo.save_vehicle(s, v)
    assert repo.get_vehicle(s, "v0") == v
    repo.save_vehicle(s, v.model_copy(update={"kilometraje": 1}))
    assert repo.get_vehicle(s, "v0").kilometraje == 1
    assert len(repo.list_vehicles(s)) == 1
    assert repo.get_vehicle(s, "nope") is None


def test_documents(s):
    d = DocExtraction(documento_id="d1", tipo="factura", vin="3N1CN7AD0FL000001", anio=2015)
    repo.save_document(s, d, vehicle_id="v0", storage_url="private://bucket/d1.png")
    assert repo.list_documents(s, vehicle_id="v0") == [d]
    assert repo.list_documents(s, vehicle_id="otro") == []


def test_prediction_roundtrip(s):
    p = _pred(1)
    repo.save_prediction(s, p)
    got = repo.get_prediction(s, "p1")
    assert got.output == p.output and got.agent_version == p.agent_version
    assert [x.prediction_id for x in repo.list_predictions(s, vehicle_id="v0")] == ["p1"]


def test_bulk_10k_predictions_under_3s(s):
    preds = [_pred(i, vid=f"v{i % 50}") for i in range(10_000)]
    t0 = time.perf_counter()
    n = repo.save_predictions(s, preds)
    elapsed = time.perf_counter() - t0
    assert n == 10_000
    assert elapsed < 3.0, f"bulk insert tardó {elapsed:.2f}s"
    df = repo.predictions_df(s)
    assert len(df) == 10_000 and df["prima"].iloc[0] == 10000


def test_predictions_df_joins_vehicle_columns(s):
    repo.save_vehicle(s, _vehicle(0))
    repo.save_predictions(s, [_pred(1, "v0"), _pred(2, "sin_perfil")])
    df = repo.predictions_df(s).set_index("prediction_id")
    assert df.loc["p1", "uso"] == "app_transporte" and df.loc["p1", "danos_costo"] == 1500
    assert pd.isna(df.loc["p2", "marca"])
    for c in ("vehicle_id", "agent_version", "prima", "kilometraje", "cobertura_verificacion"):
        assert c in df.columns
    assert repo.predictions_df(s, agent_version="otra").empty


def test_outcomes_and_df(s):
    outs = [
        Outcome(outcome_id=f"o{i}", prediction_id=f"p{i}", fuente="simulador",
                valor={"vendida": i % 2 == 0, "costo_real": 9000.0 + i})
        for i in range(10)
    ]
    assert repo.save_outcomes(s, outs) == 10
    repo.save_outcome(s, Outcome(outcome_id="o_t", prediction_id="p99", fuente="taller", valor={"monto": 1}))
    df = repo.outcomes_df(s)
    assert len(df) == 11
    assert {"prediction_id", "vendida", "costo_real"} <= set(df.columns)
    assert df.set_index("outcome_id").loc["o3", "costo_real"] == 9003.0
    assert len(repo.list_outcomes(s, prediction_id="p1")) == 1


def test_outcomes_df_empty(s):
    df = repo.outcomes_df(s)
    assert df.empty and {"prediction_id", "vendida", "costo_real"} <= set(df.columns)


def test_save_errors_long_format(s):
    df = pd.DataFrame({
        "prediction_id": ["p1", "p2", "p3"],
        "loss": [100.0, 50.0, np.nan],
        "error_rel": [-0.1, 0.05, 0.2],
        "uso": ["particular"] * 3,
    })
    n = repo.save_errors(s, df, segmento={"uso": "particular"})
    assert n == 5  # 2 loss (NaN omitido) + 3 error_rel
    e = repo.errors_df(s, metrica="error_rel")
    assert list(e["valor"]) == [-0.1, 0.05, 0.2]
    assert e["segmento"].iloc[0] == {"uso": "particular"}
    assert repo.save_errors(s, df.iloc[0:0]) == 0


def test_agent_versions_and_champion(s):
    v1 = AgentVersion(id="cotizador@aaa", agent="cotizador", git_sha="aaa", estado="campeon", metrics={"loss": 1.0})
    v2 = AgentVersion(id="cotizador@bbb", agent="cotizador", parent_id=v1.id, git_sha="bbb", estado="retador")
    repo.save_agent_version(s, v1)
    repo.save_agent_version(s, v2)
    assert repo.get_champion(s).id == v1.id
    repo.set_champion(s, v2.id)
    assert repo.get_champion(s).id == v2.id
    assert repo.get_agent_version(s, v1.id).estado == "retirado"
    assert repo.get_agent_version(s, v2.id).parent_id == v1.id
    assert repo.get_agent_version(s, v1.id).metrics == {"loss": 1.0}
    with pytest.raises(KeyError):
        repo.set_champion(s, "nope")


def test_patches(s):
    p = Patch(
        patch_id="pt1", generation=2, tipo="ajuste_factor", hipotesis="app_transporte subcotiza",
        segmento={"uso": "app_transporte"},
        cambios=[ConfigChange(op="set", path="factores.uso.categorias.app_transporte", value=1.4)],
        diff="1.25 -> 1.4", metrics_before={"loss": 10.0},
    )
    repo.save_patch(s, p)
    repo.save_patch(s, p.model_copy(update={"patch_id": "pt0", "generation": 1, "veredicto": "rechazado"}))
    assert repo.get_patch(s, "pt1") == p
    assert [x.patch_id for x in repo.list_patches(s)] == ["pt0", "pt1"]
    assert [x.patch_id for x in repo.list_patches(s, veredicto="pendiente")] == ["pt1"]
    assert [x.patch_id for x in repo.list_patches(s, generation=1)] == ["pt0"]
    got = repo.set_patch_verdict(s, "pt1", "aceptado", razon="manual")
    assert got.veredicto == "aceptado" and got.razon == "manual"
    # upsert conserva el registro
    repo.save_patch(s, got.model_copy(update={"metrics_after": {"loss": 9.0}}))
    assert repo.get_patch(s, "pt1").metrics_after == {"loss": 9.0}
    assert len(repo.list_patches(s)) == 2


def test_meta_strategy(s):
    for g in range(3):
        repo.save_meta_strategy(s, MetaStrategy(
            generation=g, arms={"ajuste_factor": (1.0 + g, 1.0), "cambio_prompt": (1.0, 2.0)},
            lecciones=f"gen {g}", tasa_aceptacion=0.5, ganancia_media=0.01 * g,
        ))
    ms = repo.list_meta_strategy(s)
    assert [m.generation for m in ms] == [0, 1, 2]
    last = repo.latest_meta_strategy(s)
    assert last.arms["ajuste_factor"] == (3.0, 1.0) and last.lecciones == "gen 2"


def test_clear_all(s):
    repo.save_vehicle(s, _vehicle(0))
    repo.save_predictions(s, [_pred(1)])
    repo.save_agent_version(s, AgentVersion(id="a", agent="cotizador", git_sha="a", estado="campeon"))
    repo.save_agent_version(s, AgentVersion(id="b", agent="cotizador", parent_id="a", git_sha="b", estado="retador"))
    repo.clear_all(s)
    assert repo.list_vehicles(s) == [] and repo.predictions_df(s).empty and repo.list_agent_versions(s) == []


def test_database_url_env_and_file_sqlite(tmp_path, monkeypatch):
    dbs.dispose_all()
    url = f"sqlite:///{tmp_path}/sub/x.db"
    monkeypatch.setenv("DATABASE_URL", url)
    assert dbs.database_url() == url
    with dbs.session_scope() as sess:
        repo.save_vehicle(sess, _vehicle(7))
    with dbs.session_scope() as sess:
        assert repo.get_vehicle(sess, "v7") is not None
    assert (tmp_path / "sub" / "x.db").exists()
    dbs.dispose_all()


def test_default_url_and_postgres_normalization(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert dbs.database_url() == "sqlite:///var/autoguard.db"
    assert dbs._normalize("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert dbs._normalize("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"


def test_session_scope_rolls_back(tmp_path):
    dbs.dispose_all()
    url = f"sqlite:///{tmp_path}/r.db"
    with pytest.raises(RuntimeError):
        with dbs.session_scope(url) as sess:
            sess.add(VehicleRow(id="x", perfil_json={}))
            sess.flush()
            raise RuntimeError("boom")
    with dbs.session_scope(url) as sess:
        assert repo.get_vehicle(sess, "x") is None
    dbs.dispose_all()
