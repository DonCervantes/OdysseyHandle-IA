"""Integración SIMULADA sin llaves ni red."""
import json

import pandas as pd
import pytest

from autoguard.rsi.loop import run_experiment


def test_reproducible_artifacts_and_static_lineage(tmp_path, monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER', 'mock')
    monkeypatch.delenv('DATABASE_URL', raising=False)
    a = run_experiment(batches=6, batch_size=100, k=2, output_dir=tmp_path / 'a')
    b = run_experiment(batches=6, batch_size=100, k=2, output_dir=tmp_path / 'b')
    assert a['regret'] == b['regret']
    assert a['simulados'] and isinstance(a['gate2'], bool)
    curve = pd.read_csv(tmp_path / 'a/curve.csv')
    assert len(curve) == 18
    for variant, rows in curve.groupby('variant'):
        assert rows.polizas.tolist() == [100, 200, 300, 400, 500, 600]
        assert rows.regret.is_monotonic_increasing
        assert rows.regret.iloc[-1] == pytest.approx(a['regret'][variant])
    versions = [json.loads(line) for line in (tmp_path / 'a/versions.jsonl').read_text().splitlines()]
    assert len([v for v in versions if v['variant'] == 'estatico']) == 1
    patches = [json.loads(line) for line in (tmp_path / 'a/patches.jsonl').read_text().splitlines()]
    assert {p['variant'] for p in patches} == {'parametros', 'rsi'}
    assert all(p['tipo'] == 'ajuste_factor' for p in patches if p['variant'] == 'parametros')
    assert all(p['veredicto'] in ('aceptado', 'rechazado', 'invalido') for p in patches)


def test_database_optional(tmp_path, monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER', 'mock')
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path}/run.db')
    summary = run_experiment(batches=1, batch_size=100, k=1, output_dir=tmp_path / 'run')
    assert summary['database_requested']
    assert (tmp_path / 'run.db').exists()


def test_invalid_parameters(tmp_path):
    with pytest.raises(ValueError):
        run_experiment(k=0, output_dir=tmp_path / 'run')


def test_unique_patch_id_por_variante():
    from autoguard.rsi.loop import unique_patch_id

    assert unique_patch_id("rsi", "g1-0-ajuste_factor") == "rsi-g1-0-ajuste_factor"
    assert unique_patch_id("rsi", "rsi-g1-0-ajuste_factor") == "rsi-g1-0-ajuste_factor"
    assert unique_patch_id("parametros", "g1-0-ajuste_factor") != unique_patch_id("rsi", "g1-0-ajuste_factor")
