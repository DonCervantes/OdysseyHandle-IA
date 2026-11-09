"""Lectura y agregados del tablero compartido; ningún comando de escritura."""
import csv
import io
import subprocess
from collections import Counter
from pathlib import Path

SESSIONS = ('claude-dylan', 'claude-elias', 'gpt-dylan', 'cursor-elias')
ACTIVE = {'claimed', 'review', 'reviewing', 'changes_requested'}
COLUMNS = {'id', 'tipo', 'estado', 'dueno', 'revisor', 'deps_listas', 'deps', 'ultimo_evento', 'titulo'}


def parse_tsv(text):
    reader = csv.DictReader(io.StringIO(text), delimiter='\t')
    if not COLUMNS.issubset(reader.fieldnames or []):
        raise ValueError('El tablero TSV no contiene las columnas esperadas')
    return [{k: (v or '') for k, v in row.items()} for row in reader if row.get('id')]


def read_board(root: Path):
    result = subprocess.run(['bash', str(root / 'scripts/tasks.sh'), 'tsv'], cwd=root,
                            capture_output=True, text=True, timeout=25, check=True)
    return parse_tsv(result.stdout)


def aggregate(rows):
    agents = [r for r in rows if r['tipo'] == 'claude']
    done = sum(r['estado'] == 'done' for r in agents)
    activity = []
    for session in SESSIONS:
        owned = [r for r in agents if r['dueno'].split(':')[0] == session]
        activity.append(dict(sesion=session, hechas=sum(r['estado'] == 'done' for r in owned),
                             en_curso=sum(r['estado'] in ACTIVE for r in owned),
                             revisadas=sum(r['revisor'].split(':')[0] == session and
                                           r['estado'] in {'done', 'changes_requested'} for r in agents)))
    return dict(total=len(agents), done=done, percent=100 * done / len(agents) if agents else 0,
                states=dict(Counter(r['estado'] for r in agents)), activity=activity,
                blocked=[r for r in agents if r['deps_listas'] != 'si' and r['estado'] != 'done'],
                human=[r for r in rows if r['tipo'] == 'humano' and r['estado'] != 'done'])
