"""Tablero de experimentos AUTOGUARD. Datos SIMULADOS."""
import os
import sys
import time
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from data import improvement, load_run
from autoguard.rsi.lineage import ConfigRepo

st.set_page_config(page_title='AUTOGUARD · Laboratorio RSI', page_icon='◈', layout='wide')
st.title('AUTOGUARD · Laboratorio RSI')
st.caption('Datos SIMULADOS · Comparación del aprendizaje y trazabilidad de cambios')
common = ROOT / '.git'
# En worktrees, las corridas suelen vivir en el checkout principal.
if common.is_file():
    from git import Repo
    main_root = Path(Repo(ROOT).common_dir).resolve().parent
else:
    main_root = ROOT
source = st.sidebar.text_input('Directorio de corridas', os.getenv('AUTOGUARD_RUNS_DIR') or str(main_root / 'var/runs'))
runs_root = Path(source).expanduser()
runs = sorted((p for p in runs_root.glob('*') if p.is_dir() and (p / 'curve.csv').exists()),
              key=lambda p: p.stat().st_mtime, reverse=True)
if not runs:
    st.info('Todavía no hay corridas con curve.csv en este directorio.')
    st.code('LLM_PROVIDER=mock .venv/bin/python -m autoguard.rsi.loop --seed 42')
    st.stop()
run = st.sidebar.selectbox('Corrida', runs, format_func=lambda p: p.name)
if st.sidebar.button('Recargar artefactos'):
    st.rerun()
try:
    data = load_run(run)
except (OSError, ValueError) as exc:
    st.error(f'No se puede leer esta corrida: {exc}')
    st.stop()
for note in data['warnings']:
    st.warning(note)
summary = data['summary']
max_gen = max(int(data['curve'].generation.max()),
              max((p.get('generation', 0) for p in data['patches']), default=0))
st.sidebar.markdown('### Demo por generación')
demo = st.sidebar.toggle('Activar reproducción', value=False)
autoplay = st.sidebar.toggle('Avanzar automáticamente', value=False, disabled=not demo)
key = f'frame-{run.name}'
if key not in st.session_state:
    st.session_state[key] = 0
if demo and max_gen:
    control_key = f'slider-{run.name}'
    st.session_state[control_key] = st.session_state[key]
    def select_generation():
        st.session_state[key] = st.session_state[control_key]
    generation = st.sidebar.slider('Generación', 0, max_gen, key=control_key, on_change=select_generation)
else:
    generation = max_gen
st.sidebar.caption('Las métricas de la vista se calculan con los lotes visibles. Gate 2 corresponde a la corrida completa.')


@st.fragment(run_every='2s' if demo and autoplay else None)
def content():
    if demo and autoplay:
        now = time.monotonic()
        timer = f'timer-{run.name}'
        previous = st.session_state.get(timer, now)
        st.session_state.setdefault(timer, now)
        if now - previous >= 2 and st.session_state[key] < max_gen:
            st.session_state[timer] = now
            st.session_state[key] += 1
            st.rerun()
    gen = st.session_state[key] if demo else max_gen
    curve = data['curve']
    if demo:
        # La variante estática siempre tiene generación 0: recortar todas por el mismo N.
        k = int(summary.get('k', 1))
        batch_size = int(summary.get('batch_size', 1))
        cutoff = (gen + 1) * k * batch_size
        curve = curve[curve.polizas <= cutoff]
    if curve.empty:
        st.info('Sin lotes visibles en esta generación.')
        return
    a, b, c, d = st.columns(4)
    gain = improvement(curve)
    a.metric('Reducción de regret RSI', f'{gain:.1%}' if gain is not None else 'Sin datos')
    b.metric('Pólizas cotizadas / variante', f'{int(curve.polizas.max()):,}')
    c.metric('Generación visible', str(gen))
    gate = summary.get('gate2')
    d.metric('Gate 2 · corrida completa', 'Cumple' if gate is True else 'No cumple' if gate is False else 'Pendiente')
    colors = {'estatico': '#94a3b8', 'parametros': '#f59e0b', 'rsi': '#10b981'}
    labels = {'estatico': 'Estático', 'parametros': 'Parámetros', 'rsi': 'RSI'}
    left, right = st.columns(2)
    for metric, title, panel in [('loss', 'Pérdida media por lote (MXN)', left),
                                  ('regret', 'Regret acumulado (MXN)', right)]:
        fig = go.Figure()
        for variant, rows in curve.groupby('variant', sort=False):
            fig.add_trace(go.Scatter(x=rows.polizas, y=rows[metric], name=labels.get(variant, variant),
                                    mode='lines', line=dict(color=colors.get(variant)),
                                    fill='tozeroy' if metric == 'regret' else None,
                                    hovertemplate='%{x:,} pólizas<br>%{y:,.0f} MXN<extra>%{fullData.name}</extra>'))
        fig.update_layout(title=title, xaxis_title='Pólizas cotizadas', yaxis_title='MXN',
                          height=360, margin=dict(l=20, r=20, t=50, b=20))
        panel.plotly_chart(fig, use_container_width=True)
    st.caption('Pérdida asimétrica y regret medidos sobre todas las cotizaciones; aprendizaje solo con ventas de train.')
    patches = [p for p in data['patches'] if p.get('generation', 0) <= gen]
    tabs = st.tabs(['Parches', 'Linaje y reversión', 'Bandido', 'Resumen y datos'])
    with tabs[0]:
        if not patches:
            st.info('Sin parches en este corte.')
        for p in patches:
            title = f"{p.get('variant', '')} · G{p.get('generation', '?')} · {p.get('tipo', '')} · {p.get('veredicto', 'pendiente')}"
            with st.expander(title):
                st.write(p.get('hipotesis', ''))
                before, after = st.columns(2)
                before.json(p.get('metrics_before', {}))
                after.json(p.get('metrics_after', {}))
                st.code(p.get('diff') or '(sin diff)', language=None)
                st.write(p.get('razon', ''))
                st.json(p.get('cambios', []))
    with tabs[1]:
        versions = data['versions']
        if demo:
            st.caption('Historial completo de la corrida; la reversión está deshabilitada durante la demo.')
        st.dataframe(pd.DataFrame(versions), hide_index=True, use_container_width=True)
        variant = st.selectbox('Repositorio de la variante', ['rsi', 'parametros', 'estatico'])
        repo_path = run / 'configs' / variant
        if (repo_path / '.git').exists():
            repo = ConfigRepo(repo_path)
            try:
                history = repo.history()
                st.caption(f'Campeón actual del repositorio: {history[0].git_sha[:10]}')
                sha = st.selectbox('Restaurar versión', [v.git_sha for v in history], format_func=lambda s: s[:10])
                if st.button('Revertir configuración de esta variante', disabled=demo, type='primary'):
                    new_sha = repo.revert_to(sha, 'Reversión manual desde tablero SIMULADO')
                    st.success(f'Nueva versión: {new_sha[:10]}. El historial Git se conserva.')
                st.caption('La reversión crea un commit en esta corrida. Las curvas registradas conservan el resultado del experimento original.')
            except Exception as exc:
                st.error(f'No se pudo leer o revertir el linaje: {exc}')
        else:
            st.info('Esta copia de artefactos no incluye repositorios de configuración.')
    with tabs[2]:
        records = []
        for m in data['meta']:
            if m.get('generation', 0) <= gen:
                for arm, values in m.get('arms', {}).items():
                    alpha, beta = values
                    records.append(dict(generacion=m['generation'], brazo=arm, media=alpha / (alpha + beta)))
        if records:
            frame = pd.DataFrame(records)
            st.line_chart(frame.pivot_table(index='generacion', columns='brazo', values='media'))
            st.caption('Media posterior α/(α+β) por brazo; no representa frecuencia de selección.')
            visible_meta = [m for m in data['meta'] if m.get('generation', 0) <= gen]
            st.write(visible_meta[-1].get('lecciones', ''))
        else:
            st.info('Sin observaciones del bandido en este corte.')
    with tabs[3]:
        st.json(summary)
        st.dataframe(curve, hide_index=True, use_container_width=True)
        st.download_button('Descargar curvas visibles', curve.to_csv(index=False), 'curve.csv', 'text/csv')
        if os.getenv('DATABASE_URL'):
            if st.button('Consultar parches de BD'):
                try:
                    from autoguard.db.session import session_scope
                    from autoguard.db.repo import list_patches
                    with session_scope() as session:
                        st.dataframe([p.model_dump(mode='json') for p in list_patches(session)], hide_index=True)
                    st.caption('BD compartida: puede incluir otras corridas y parches de producción.')
                except Exception as exc:
                    st.warning(f'BD no disponible ({type(exc).__name__}).')


content()
