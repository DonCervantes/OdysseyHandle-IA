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
from demo import accepted_at, seconds_per_generation, select_runs, visible_curve
from autoguard.rsi.lineage import ConfigRepo

st.set_page_config(page_title='AUTOGUARD · Laboratorio RSI', layout='wide', initial_sidebar_state='collapsed')
st.markdown('<style>.block-container{padding-top:2rem;padding-bottom:2rem} h1{font-size:2.25rem!important} h2{font-size:1.5rem!important}</style>', unsafe_allow_html=True)
st.caption('AUTOGUARD / EXPERIMENTO DE APRENDIZAJE')
st.caption('Datos simulados · Cada cambio deja evidencia y puede revertirse.')
common = ROOT / '.git'
# En worktrees, las corridas suelen vivir en el checkout principal.
if common.is_file():
    from git import Repo
    main_root = Path(Repo(ROOT).common_dir).resolve().parent
else:
    main_root = ROOT
source = st.sidebar.text_input('Directorio de corridas', os.getenv('AUTOGUARD_RUNS_DIR') or str(main_root / 'var/runs'))
runs_root = Path(source).expanduser()
fallback = st.sidebar.text_input('Corrida de respaldo (plan B)', str(main_root / 'data/demo_run'))
runs, using_fallback = select_runs(runs_root, Path(fallback).expanduser())
if not runs:
    st.info('Sin corridas nuevas ni de respaldo. Selecciona una carpeta con curve.csv o genera una corrida mock.')
    st.code('LLM_PROVIDER=mock .venv/bin/python -m autoguard.rsi.loop --seed 42')
    st.stop()
if using_fallback:
    st.sidebar.info('Plan B: mostrando una corrida pregrabada de respaldo.')
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
key = f'frame-{run.resolve()}'
playing_key = f'playing-{run.resolve()}'
timer_key = f'timer-{run.resolve()}'
st.session_state.setdefault(key, 0)
st.session_state.setdefault(playing_key, False)
if not demo:
    st.session_state[playing_key] = False
speed = st.sidebar.select_slider('Velocidad', options=[0.5, 1.0, 2.0, 4.0], value=1.0,
                                 format_func=lambda value: f'{value:g}×', disabled=not demo)
interval = seconds_per_generation(max_gen, speed)


def play():
    if st.session_state[key] >= max_gen:
        st.session_state[key] = 0
    st.session_state[playing_key] = True
    st.session_state[timer_key] = time.monotonic()


def pause():
    st.session_state[playing_key] = False


def restart():
    pause()
    st.session_state[key] = 0


play_col, pause_col, restart_col = st.sidebar.columns(3)
play_col.button('▶ Play', on_click=play, disabled=not demo or max_gen == 0)
pause_col.button('Ⅱ Pausa', on_click=pause, disabled=not demo)
restart_col.button('↺ Inicio', on_click=restart, disabled=not demo)
if demo and max_gen:
    control_key = f'slider-{run.resolve()}'
    st.session_state[control_key] = st.session_state[key]
    def select_generation():
        pause()
        st.session_state[key] = st.session_state[control_key]
    st.sidebar.slider('Generación', 0, max_gen, key=control_key, on_change=select_generation)
    st.sidebar.progress(st.session_state[key] / max_gen)
    st.sidebar.caption(f"{'Reproduciendo' if st.session_state[playing_key] else 'En pausa'} · "
                       f'{interval:.1f} s por generación · 1× ≈ 40 s por corrida')
st.sidebar.caption('Las métricas de la vista se calculan con los lotes visibles. Gate 2 corresponde a la corrida completa.')


@st.fragment(run_every=interval if demo and st.session_state[playing_key] else None)
def content():
    if demo and st.session_state[playing_key]:
        now = time.monotonic()
        if now - st.session_state.get(timer_key, now) >= interval:
            st.session_state[timer_key] = now
            st.session_state[key] = min(max_gen, st.session_state[key] + 1)
            if st.session_state[key] >= max_gen:
                pause()
            st.rerun()
    gen = st.session_state[key] if demo else max_gen
    curve = data['curve']
    if demo:
        curve = visible_curve(curve, gen, summary)
    if curve.empty:
        st.info('Sin lotes visibles en esta generación.')
        return
    gain = improvement(curve) if demo else summary.get('mejora_rsi', improvement(curve))
    st.title(f'El RSI reduce el regret {gain:.1%}' if gain is not None and gain >= 0 else
             f'El regret del RSI aumenta {abs(gain):.1%}' if gain is not None else 'El aprendizaje espera su primera corrida')
    st.caption('Resultado del corte visible' if demo else 'Resultado completo de la corrida seleccionada')
    a, b, c, d = st.columns(4)
    a.metric('Reducción de regret RSI', f'{gain:.1%}' if gain is not None else 'Sin datos')
    b.metric('Pólizas cotizadas / variante', f'{int(curve.polizas.max()):,}')
    c.metric('Generación visible', str(gen))
    convergence = summary.get('convergencia_polizas', {}).get('rsi')
    st.caption(f'Convergencia RSI según esta corrida: {int(convergence):,} pólizas' if convergence is not None else
               'Convergencia RSI según esta corrida: no alcanzada en esta corrida.')
    totals = summary.get('regret', {})
    if totals:
        st.caption('Regret total · ' + ' · '.join(f'{name}: {totals[v]:,.0f} MXN' for v, name in
                   [('estatico', 'Reglas fijas'), ('parametros', 'Solo parámetros'), ('rsi', 'RSI completo')] if v in totals))
    gate = summary.get('gate2')
    d.metric('Gate 2 · corrida completa', 'Cumple' if gate is True else 'No cumple' if gate is False else 'Pendiente')
    colors = {'estatico': '#64748b', 'parametros': '#b7791f', 'rsi': '#007f73'}
    labels = {'estatico': 'Reglas fijas', 'parametros': 'Solo parámetros', 'rsi': 'RSI completo'}
    left, right = st.columns(2)
    for metric, title, panel in [('loss', 'Pérdida media por lote (MXN)', left),
                                  ('regret', 'Regret acumulado (MXN)', right)]:
        fig = go.Figure()
        for variant, rows in curve.groupby('variant', sort=False):
            fig.add_trace(go.Scatter(x=rows.polizas, y=rows[metric], name=labels.get(variant, variant),
                                    mode='lines', line=dict(color=colors.get(variant)),
                                    fill='tozeroy' if metric == 'regret' else None,
                                    hovertemplate='%{x:,} pólizas<br>%{y:,.0f} MXN<extra>%{fullData.name}</extra>'))
        for patch in data['patches']:
            if patch.get('veredicto') != 'aceptado' or patch.get('generation', 0) > gen:
                continue
            variant = patch.get('variant', 'rsi')
            x = patch.get('generation', 0) * int(summary.get('k', 1)) * int(summary.get('batch_size', 1))
            rows = curve[(curve.variant == variant) & (curve.polizas <= x)]
            if rows.empty or x > curve.polizas.max():
                continue
            fig.add_trace(go.Scatter(x=[rows.polizas.iloc[-1]], y=[rows[metric].iloc[-1]], mode='markers',
                marker=dict(symbol='diamond', size=9, color=colors.get(variant)), showlegend=False,
                text=[f"Parche aceptado · G{patch.get('generation')} · {patch.get('tipo')}"],
                hovertemplate='%{text}<extra></extra>'))
        fig.update_layout(title=title, xaxis_title='Pólizas cotizadas', yaxis_title='MXN',
                          height=360, margin=dict(l=20, r=20, t=50, b=20))
        panel.plotly_chart(fig, use_container_width=True)
    st.caption('Pérdida asimétrica y regret medidos sobre todas las cotizaciones; aprendizaje solo con ventas de train.')
    st.subheader('Cada generación propone, comprueba y aprende')
    st.caption(f'Generación {gen} · Reconstrucción de una corrida registrada; no representa ejecución en tiempo real.')
    st.markdown('**Recolector → Analista → Mejorador → Evaluador congelado → Linaje → Meta-mejorador**')
    st.caption('Ventas observadas → hipótesis en train → cambios candidatos → veredicto en holdout → versión Git → lecciones y posteriors')
    patches = [p for p in data['patches'] if p.get('generation', 0) <= gen]
    newly_accepted = accepted_at(patches, gen) if demo else []
    for patch in newly_accepted:
        st.success(f"✓ Parche aceptado · {patch.get('variant', '')} · G{gen} · "
                   f"{patch.get('patch_id', '')} · {patch.get('tipo', '')}")
        st.caption(patch.get('diff') or patch.get('hipotesis', ''))
    tabs = st.tabs(['La historia de los cambios', 'Versiones y garantías', 'Aprende a mejorar', 'Evidencia de la corrida'])
    with tabs[0]:
        st.subheader('Una hipótesis solo avanza con evidencia')
        f1, f2 = st.columns(2)
        verdicts = f1.multiselect('Veredicto', sorted({p.get('veredicto', 'pendiente') for p in patches}))
        types = f2.multiselect('Tipo de cambio', sorted({p.get('tipo', '') for p in patches}))
        filtered = [p for p in patches if (not verdicts or p.get('veredicto') in verdicts) and (not types or p.get('tipo') in types)]
        if not filtered:
            st.info('Sin parches en este corte.')
        for p in filtered:
            title = f"{p.get('variant', '')} · G{p.get('generation', '?')} · {p.get('tipo', '')} · {p.get('veredicto', 'pendiente')}"
            with st.expander(title, expanded=p in newly_accepted):
                st.write(p.get('hipotesis', ''))
                before, after = st.columns(2)
                old = p.get('metrics_before', {}).get('loss')
                new = p.get('metrics_after', {}).get('loss')
                before.metric('Pérdida en holdout antes · MXN', f'{old:,.0f}' if old is not None else 'Sin evaluación')
                after.metric('Pérdida en holdout después · MXN', f'{new:,.0f}' if new is not None else 'Sin evaluación')
                st.code(p.get('diff') or '(sin diff)', language=None)
                st.write(p.get('razon', ''))
                st.json(p.get('cambios', []))
    with tabs[1]:
        st.subheader('El evaluador conserva las reglas; cada versión conserva su historia')
        st.write('Evaluador inmutable · Holdout reservado al evaluador · Variables permitidas por lista blanca · Reversión mediante un nuevo commit')
        versions = data['versions']
        if 'revert_notice' in st.session_state:
            st.success(st.session_state.pop('revert_notice'))
        if demo:
            st.caption('Historial completo de la corrida; la reversión está deshabilitada durante la demo.')
        st.caption('Historial registrado al cerrar la corrida (artefacto original).')
        st.dataframe(pd.DataFrame(versions), hide_index=True, use_container_width=True)
        variant = st.selectbox('Repositorio de la variante', ['rsi', 'parametros', 'estatico'])
        repo_path = run / 'configs' / variant
        if (repo_path / '.git').exists():
            repo = ConfigRepo(repo_path)
            try:
                history = repo.history()
                st.caption(f'Campeón actual del repositorio: {history[0].git_sha[:10]}')
                st.dataframe([version.model_dump(mode='json') for version in history],
                             hide_index=True, use_container_width=True)
                sha = st.selectbox('Restaurar versión', [v.git_sha for v in history], format_func=lambda s: s[:10])
                confirmed = st.checkbox(f'Confirmo restaurar {sha[:10]} en {variant}', key=f'confirm-{run}-{variant}-{sha}', disabled=demo)
                if st.button('Revertir configuración de esta variante', disabled=demo or not confirmed, type='primary'):
                    new_sha = repo.revert_to(sha, 'Reversión manual desde tablero SIMULADO')
                    st.session_state['revert_notice'] = f'Nueva versión: {new_sha[:10]}. El historial Git se conserva.'
                    st.rerun()
                st.caption('La reversión crea un commit en esta corrida. Las curvas registradas conservan el resultado del experimento original.')
            except Exception as exc:
                st.error(f'No se pudo leer o revertir el linaje: {exc}')
        else:
            st.info('Esta copia de artefactos no incluye repositorios de configuración.')
    with tabs[2]:
        st.subheader('La experiencia cambia qué tipo de mejora se intenta')
        acceptance = []
        for generation in sorted({p.get('generation', 0) for p in patches}):
            evaluated = [p for p in patches if p.get('generation') == generation and p.get('variant') == 'rsi' and p.get('veredicto') in ('aceptado', 'rechazado')]
            if evaluated:
                acceptance.append({'Generación': generation, 'Aceptados / evaluados (%)': 100 * sum(p['veredicto'] == 'aceptado' for p in evaluated) / len(evaluated)})
        if acceptance:
            st.line_chart(pd.DataFrame(acceptance).set_index('Generación'))
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
