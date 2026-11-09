"""Lectura de artefactos RSI; acepta JSONL incompleto durante una escritura."""
import json
from pathlib import Path

import pandas as pd


def read_jsonl(path):
    records, warnings = [], []
    if not path.exists():
        return records, warnings
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError('Se esperaba un objeto')
            records.append(value)
        except ValueError:
            warnings.append(f'{path.name}: línea {number} incompleta o inválida')
    return records, warnings


def load_run(path):
    path = Path(path)
    warnings = []
    summary = {}
    try:
        summary = json.loads((path / 'summary.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        warnings.append('Resumen pendiente o no disponible.')
    curve = pd.read_csv(path / 'curve.csv')
    required = {'variant', 'polizas', 'loss', 'regret', 'generation'}
    if not required.issubset(curve.columns):
        raise ValueError(f'Faltan columnas de curvas: {required - set(curve.columns)}')
    result = dict(curve=curve.sort_values('polizas'), summary=summary, warnings=warnings)
    for name in ('patches', 'versions', 'meta'):
        result[name], notes = read_jsonl(path / f'{name}.jsonl')
        warnings.extend(notes)
    return result


def improvement(curve):
    latest = curve.sort_values('polizas').groupby('variant').tail(1).set_index('variant')
    if not {'estatico', 'rsi'}.issubset(latest.index) or latest.loc['estatico', 'regret'] == 0:
        return None
    return 1 - latest.loc['rsi', 'regret'] / latest.loc['estatico', 'regret']
