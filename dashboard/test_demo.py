"""Reproducción de artefactos SIMULADOS sin red ni ejecución del RSI."""
import json
from pathlib import Path
import time

import pandas as pd
from streamlit.testing.v1 import AppTest

from dashboard.demo import accepted_at, seconds_per_generation, select_runs, visible_curve


def make_run(path):
    path.mkdir(parents=True)
    rows = []
    for gen in range(3):
        for variant, multiplier in [('estatico', 1), ('parametros', .8), ('rsi', .6)]:
            rows.append(dict(variant=variant, polizas=(gen + 1) * 200, loss=100 * multiplier,
                             regret=(gen + 1) * 20000 * multiplier, generation=gen if variant != 'estatico' else 0))
    pd.DataFrame(rows).to_csv(path / 'curve.csv', index=False)
    (path / 'summary.json').write_text(json.dumps({'k': 1, 'batch_size': 200, 'gate2': False}))
    (path / 'patches.jsonl').write_text(json.dumps(dict(patch_id='p1', variant='rsi', generation=1,
                                                       tipo='cambio_regla', veredicto='aceptado', diff='SIMULADO ×1.1')) + '\n')
    return path


def test_fallback_and_same_policy_cut(tmp_path):
    fallback = make_run(tmp_path / 'demo')
    runs, used_fallback = select_runs(tmp_path / 'missing', fallback)
    assert runs == [fallback] and used_fallback
    primary = make_run(tmp_path / 'runs' / 'new')
    runs, used_fallback = select_runs(primary.parent, fallback)
    assert runs == [primary] and not used_fallback
    curve = pd.read_csv(primary / 'curve.csv')
    for summary in ({'k': 1, 'batch_size': 200}, {}):
        visible = visible_curve(curve, 1, summary)
        assert visible.groupby('variant').polizas.max().to_dict() == {
            'estatico': 400, 'parametros': 400, 'rsi': 400}
    patches = [dict(generation=1, veredicto='aceptado'), dict(generation=1, veredicto='rechazado'),
               dict(generation=2, veredicto='aceptado')]
    assert accepted_at(patches, 1) == [patches[0]]
    assert seconds_per_generation(20, 1) * 20 == 40
    assert seconds_per_generation(20, 2) == seconds_per_generation(20, 1) / 2


def test_play_pause_speed_and_patch_reveal(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    fallback = make_run(tmp_path / 'backup')
    monkeypatch.setenv('AUTOGUARD_RUNS_DIR', str(tmp_path / 'missing'))
    monkeypatch.setenv('AUTOGUARD_NO_DOTENV', '1')
    monkeypatch.delenv('DATABASE_URL', raising=False)
    app = AppTest.from_file(str(root / 'dashboard/app.py')).run(timeout=15)
    assert not app.exception
    # Plan B is selected directly; no code execution or backend is involved.
    app.sidebar.text_input[1].set_value(str(fallback)).run()
    app.sidebar.toggle[0].set_value(True).run()
    assert not app.exception
    frame_key = f'frame-{fallback.resolve()}'
    playing_key = f'playing-{fallback.resolve()}'
    timer_key = f'timer-{fallback.resolve()}'
    next(button for button in app.button if button.label == '▶ Play').click().run()
    assert app.session_state[playing_key]
    # Simulate a timer tick, avoiding waits and nondeterministic wall-clock tests.
    app.session_state[timer_key] = time.monotonic() - 100
    app.run()
    assert not app.exception
    assert app.session_state[frame_key] == 1
    assert any('p1' in notice.value for notice in app.success)
    next(button for button in app.button if button.label == 'Ⅱ Pausa').click().run()
    assert not app.session_state[playing_key]
    app.session_state[timer_key] = time.monotonic() - 100
    app.run()
    assert app.session_state[frame_key] == 1
    next(control for control in app.select_slider if control.label == 'Velocidad').set_value(4.0).run()
    assert not app.exception
    next(button for button in app.button if button.label == '↺ Inicio').click().run()
    assert app.session_state[frame_key] == 0
    assert not app.session_state[playing_key]
