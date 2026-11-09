"""Dashboard de coordinación, solo lectura."""
from datetime import datetime
from pathlib import Path
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data import aggregate, read_board

ROOT = Path(__file__).resolve().parents[2]
st.set_page_config(page_title='AUTOGUARD · Progreso', page_icon='◉', layout='wide')
st.title('AUTOGUARD · Progreso de las sesiones')
st.caption('Coordinación en vivo · Proyecto con datos SIMULADOS · Solo lectura')


@st.fragment(run_every='30s')
def board():
    if st.button('Actualizar ahora'):
        st.cache_data.clear()
    try:
        rows = read_board(ROOT)
        st.session_state['last_board'] = rows
        st.session_state['last_update'] = datetime.now().strftime('%H:%M:%S')
    except Exception as exc:
        st.warning(f'No se pudo actualizar el tablero ({type(exc).__name__}).')
        rows = st.session_state.get('last_board')
        if rows is None:
            st.info('Esperando conexión con el tablero Git.')
            return
    stats = aggregate(rows)
    st.caption(f"Última lectura correcta: {st.session_state['last_update']} · Actualización cada 30 s")
    a, b, c, d = st.columns(4)
    a.metric('Avance de agentes', f"{stats['percent']:.0f}%")
    b.metric('Terminadas', f"{stats['done']} / {stats['total']}")
    c.metric('Bloqueadas', len(stats['blocked']))
    d.metric('Pendientes humanas', len(stats['human']))
    st.progress(stats['percent'] / 100)
    left, right = st.columns([1, 2])
    with left:
        st.subheader('Tareas por estado')
        st.bar_chart(pd.DataFrame(stats['states'].items(), columns=['Estado', 'Tareas']).set_index('Estado'))
    with right:
        st.subheader('Actividad por sesión')
        st.dataframe(stats['activity'], hide_index=True, use_container_width=True)
        st.caption('Revisadas: veredicto actual done o changes_requested; no es un conteo histórico de eventos.')
    st.subheader('Tablero de tareas')
    states = st.multiselect('Filtrar por estado', sorted({r['estado'] for r in rows}))
    selected = [r for r in rows if not states or r['estado'] in states]
    columns = ['id', 'titulo', 'estado', 'dueno', 'revisor', 'asignada', 'ultimo_evento']
    st.dataframe(pd.DataFrame(selected).reindex(columns=columns), hide_index=True, use_container_width=True)
    st.subheader('Bloqueadas por dependencias')
    if stats['blocked']:
        status = {r['id']: r['estado'] for r in rows}
        st.dataframe([dict(id=r['id'], titulo=r['titulo'], pendientes=' · '.join(
            dep for dep in r['deps'].split() if status.get(dep) != 'done')) for r in stats['blocked']],
            hide_index=True, use_container_width=True)
    else:
        st.success('No hay tareas de agentes bloqueadas.')
    st.subheader('Tareas humanas pendientes')
    st.dataframe(pd.DataFrame(stats['human']).reindex(columns=['id', 'titulo', 'deps', 'deps_listas']),
                 hide_index=True, use_container_width=True)


board()
