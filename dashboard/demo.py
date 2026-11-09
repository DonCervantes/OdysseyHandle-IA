"""Selección de corridas y cortes de reproducción; sin datos ni resultados inventados."""
from pathlib import Path


def discover_runs(directory):
    """Acepta un contenedor de corridas o una corrida directa (plan B)."""
    directory = Path(directory)
    if (directory / 'curve.csv').is_file():
        return [directory]
    return sorted((p for p in directory.glob('*') if p.is_dir() and (p / 'curve.csv').is_file()),
                  key=lambda p: p.stat().st_mtime, reverse=True)


def select_runs(primary, fallback):
    runs = discover_runs(primary)
    if runs:
        return runs, False
    return discover_runs(fallback), True


def seconds_per_generation(max_generation, speed=1.0):
    """A 1× recorre las generaciones en unos 40 s; siempre permite pausar."""
    return max(0.2, 40.0 / max(1, max_generation) / speed)


def visible_curve(curve, generation, summary):
    # El estático siempre registra generation=0: cortar variantes por el mismo N.
    if summary.get('k') and summary.get('batch_size'):
        cutoff = (generation + 1) * int(summary['k']) * int(summary['batch_size'])
    else:
        learning = curve[curve['variant'] != 'estatico']
        if learning.empty:
            learning = curve
        eligible = learning[learning['generation'] <= generation]
        cutoff = eligible['polizas'].max() if not eligible.empty else 0
    return curve[curve['polizas'] <= cutoff]


def accepted_at(patches, generation):
    return [p for p in patches if p.get('generation') == generation and p.get('veredicto') == 'aceptado']
