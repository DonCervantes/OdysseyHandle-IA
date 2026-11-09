"""Lectura de corridas y actualización de resultados, sin red."""
import json

import pytest

from dashboard.data import improvement, load_run


def test_read_run_and_changed_results(tmp_path):
    (tmp_path / 'curve.csv').write_text('variant,polizas,loss,regret,generation\nestatico,200,100,20000,0\nrsi,200,50,10000,1\n')
    (tmp_path / 'summary.json').write_text(json.dumps({'gate2': True}))
    (tmp_path / 'patches.jsonl').write_text('{"patch_id":"p1"}\n{"patch_id":')
    data = load_run(tmp_path)
    assert improvement(data['curve']) == .5
    assert data['patches'] == [{'patch_id': 'p1'}]
    assert len(data['warnings']) == 1
    (tmp_path / 'curve.csv').write_text('variant,polizas,loss,regret,generation\nestatico,200,100,20000,0\nrsi,200,80,16000,1\n')
    assert improvement(load_run(tmp_path)['curve']) == pytest.approx(.2)
