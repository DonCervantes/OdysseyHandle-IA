"""Experimento reproducible SIMULADO. python -m autoguard.rsi.loop --seed 42.

El benchmark usa todas las cotizaciones; los agentes solo reciben ventas de train.
DATABASE_URL habilita persistencia opcional de parches y versiones.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from autoguard.agents.cotizador import quote_df
from autoguard.config_schema import load_config
from autoguard.contracts import ARMS
from autoguard.evaluator.evaluator import evaluate, split_holdout
from autoguard.evaluator.objective import loss
from autoguard.rsi.analista import analyze, optimal_multiplier
from autoguard.rsi.graph import build_graph
from autoguard.rsi.lineage import ConfigRepo
from autoguard.rsi.mejorador import patch_target, propose
from autoguard.rsi.meta import MetaImprover
from autoguard.rsi.recolector import collect
from autoguard.sim.market import MarketSimulator


CONV_WINDOW = 3  # lotes de la media móvil
CONV_TOL = 0.10  # convergida = pérdida media móvil ≤ (1 + CONV_TOL) × la del oráculo, de ahí al final
TABU_GENS = 2  # generaciones sin re-proponer un objetivo rechazado
# Rondas por generación: si una ronda acepta parches, se propone otra sobre el campeón ya actualizado
# (mismas filas train/holdout; cada parche pasa igual por el evaluador). Aplica a parametros y rsi.
ROUNDS_MAX = 2


def _append(path, records):
    with path.open('a', encoding='utf-8') as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + '\n')


def oracle_reference(bench):
    """Oráculo calibrado: costo esperado real × el multiplicador único que minimiza la pérdida congelada
    sobre todas las pólizas (cuantil α/(α+β) del ruido, estimado de los datos: no usa constantes privadas
    del simulador). `bench` = [(costo_esperado, costo_real) por lote]."""
    expected = np.concatenate([e for e, _ in bench])
    real = np.concatenate([c for _, c in bench])
    mult = optimal_multiplier(expected, real)
    per_batch = [float(loss(e * mult, c).mean()) for e, c in bench]
    return dict(multiplicador=float(mult), regret=float(loss(expected * mult, real).sum()), loss_por_lote=per_batch)


def convergence_polizas(rows, window=CONV_WINDOW, tol=CONV_TOL):
    """Primer N (pólizas) desde el cual la media móvil de la pérdida queda ≤ (1+tol) × la del oráculo en
    TODAS las ventanas restantes; None si nunca ocurre (p.ej. una variante que no aprende)."""
    rows = rows.sort_values('batch')
    ratio = (rows['loss'].rolling(window).mean() / rows['loss_oraculo'].rolling(window).mean()).to_numpy()
    ok = np.where(np.isnan(ratio), False, ratio <= 1 + tol)
    if not ok[-1]:
        return None
    first = len(ok) - int(np.argmin(ok[::-1])) if not ok.all() else int(np.argmax(~np.isnan(ratio)))
    return int(rows['polizas'].iloc[first])


def plateau_polizas(rows, window=CONV_WINDOW, tol=CONV_TOL, min_drop=0.10):
    """Convergencia a la propia meseta: primer N desde el cual la media móvil queda ≤ (1+tol) × su nivel
    final (media de las últimas `window` ventanas) en TODAS las ventanas restantes. Solo cuenta si el error
    BAJÓ: nivel final ≤ (1 − min_drop) × la primera ventana; si no (p.ej. el estático), None."""
    rows = rows.sort_values('batch')
    roll = rows['loss'].rolling(window).mean().to_numpy()
    valid = ~np.isnan(roll)
    if valid.sum() < window:
        return None
    final = float(np.mean(roll[valid][-window:]))
    first = float(roll[valid][0])
    if not final <= (1 - min_drop) * first:
        return None
    ok = np.where(valid, roll <= (1 + tol) * final, False)
    if not ok[-1]:
        return None
    start = len(ok) - int(np.argmin(ok[::-1])) if not ok.all() else 0
    return int(rows['polizas'].iloc[start])


def unique_patch_id(variant, patch_id):
    """`<variante>-<patch_id>`; idempotente (no duplica el prefijo)."""
    prefix = f'{variant}-'
    return patch_id if not variant or patch_id.startswith(prefix) else prefix + patch_id


def acceptance_by_generation(path, variant):
    """Tasa de aceptación por generación de una variante (desde patches.jsonl): sobre todos los parches, y
    `evaluados` = solo los que llegaron al holdout con un cambio de prima posible (sin `invalido` ni el
    control `cambio_prompt`, cuya ganancia es 0 por diseño)."""
    rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    rows = [r for r in rows if r.get('variant') == variant]
    if not rows:
        return dict(primera=None, ultima=None, por_generacion={}, evaluados={})
    frame = pd.DataFrame(rows)

    def rates(f):
        rate = f.groupby('generation')['veredicto'].apply(lambda v: float((v == 'aceptado').mean()))
        return dict(primera=float(rate.iloc[0]) if len(rate) else None,
                    ultima=float(rate.iloc[-1]) if len(rate) else None,
                    por_generacion={int(g): r for g, r in rate.items()})

    out = rates(frame)
    out['evaluados'] = rates(frame[(frame['veredicto'] != 'invalido') & (frame['tipo'] != 'cambio_prompt')])
    return out


def run_experiment(seed=42, batches=60, batch_size=200, k=3, output_dir=None):
    if min(batches, batch_size, k) <= 0:
        raise ValueError('batches, batch_size y k deben ser positivos')
    start = time.perf_counter()
    root = Path(output_dir or Path('var/runs') / f'sim-{seed}-{uuid4().hex[:8]}')
    root.mkdir(parents=True, exist_ok=False)
    for filename in ('patches.jsonl', 'versions.jsonl', 'meta.jsonl'):
        (root / filename).touch()
    initial = load_config(Path(__file__).resolve().parents[2] / 'configs/agents/cotizador.yaml')
    simulator = MarketSimulator(seed)
    variants = ('estatico', 'parametros', 'rsi')
    states = {}
    curves = []
    for variant in variants:
        repo = ConfigRepo(root / 'configs' / variant)
        repo.init(initial)
        states[variant] = dict(cfg=initial.model_copy(deep=True), repo=repo,
                               meta=MetaImprover(ARMS, seed), closed=[], regret=0.0, generation=0, tabu={})

    def recollect(s):
        closed = pd.concat(s['closed'], ignore_index=True)
        # Re-cotizar con el campeón actual: no aprender errores de versiones retiradas.
        closed['prima'] = quote_df(closed, s['cfg'])
        closed['loss'] = loss(closed['prima'], closed['costo_real'])
        closed['error_rel'] = (closed['prima'] - closed['costo_real']) / closed['costo_real']
        s['train'], s['holdout'] = split_holdout(closed)
        return s

    def analyst(s):
        s['hypotheses'] = analyze(s['train'], top_k=12)
        return s

    def improve(s):
        subs = None
        if s['variant'] == 'parametros':
            arms = ['ajuste_factor'] * 3
        else:  # control limitado a 1 slot y sustitutos para slots cuyo brazo no logra proponer nada
            arms, subs = s['meta'].plan_arms(3)
        evitar = {t for t, until in s['tabu'].items() if until >= s['generation']}
        s['patches'] = propose(s['cfg'], s['hypotheses'], arms, s['generation'],
                               lecciones=s['meta'].lecciones, train=s['train'], evitar=evitar,
                               sustitutos=subs)
        s['_arms'], s['_subs'] = arms, subs
        return s

    def evaluator(s):
        s = _evaluate_round(s)
        if ROUNDS_MAX > 1:
            all_patches = list(s['patches'])
            all_accepted = list(s['accepted'])
            for r in range(2, ROUNDS_MAX + 1):
                if not s['accepted']:
                    break
                # Nueva ronda sobre el campeón ya actualizado, mismas filas train/holdout.
                s['train'] = s['train'].assign(prima=quote_df(s['train'], s['cfg']))
                s['train']['loss'] = loss(s['train']['prima'], s['train']['costo_real'])
                s['train']['error_rel'] = (s['train']['prima'] - s['train']['costo_real']) / s['train']['costo_real']
                s['hypotheses'] = analyze(s['train'], top_k=12)
                evitar = {t for t, until in s['tabu'].items() if until >= s['generation']}
                evitar |= {patch_target(p) for p in all_patches if patch_target(p)}
                # El control no cambia la prima: a lo más 1 por GENERACIÓN (no por ronda).
                controles = sum(p.tipo == 'cambio_prompt' for p in all_patches)
                arms = s['_arms'] if s['variant'] == 'parametros' else \
                    s['meta'].plan_arms(3, max_control=max(0, 1 - controles))[0]
                s['patches'] = propose(s['cfg'], s['hypotheses'], arms, s['generation'],
                                       lecciones=s['meta'].lecciones, train=s['train'], evitar=evitar,
                                       sustitutos=s['_subs'])
                for p in s['patches']:
                    p.patch_id += f'-r{r}'
                s = _evaluate_round(s)
                all_patches += s['patches']
                all_accepted += s['accepted']
            s['patches'], s['accepted'] = all_patches, all_accepted
        return s

    def _evaluate_round(s):
        # 1) Todos los parches de la generación contra el MISMO campeón: veredictos y ganancias
        #    comparables (y recompensas justas para el bandido).
        champion = s['cfg']
        results = [(patch, *evaluate(champion, patch, s['holdout'])) for patch in s['patches']]
        # 2) Composición: se parte del mejor aceptado y cada siguiente (por ganancia) se re-evalúa SOBRE la
        #    composición antes de commitear. Así dos parches que corrigen lo mismo no se suman.
        accepted = sorted((r for r in results if r[1].aceptado), key=lambda r: -r[1].ganancia)
        s['accepted'] = []
        composicion = set()
        cfg = champion
        for patch, verdict, challenger in accepted:
            if s['accepted']:
                probe = patch.model_copy(deep=True)
                probe.veredicto = None
                v2, challenger = evaluate(cfg, probe, s['holdout'])
                if not v2.aceptado:
                    patch.veredicto = 'rechazado'
                    patch.razon = (f'aceptado contra el campeón ({verdict.ganancia:+.2%}) pero no mejora sobre '
                                   f'la composición de la generación: {"; ".join(v2.razones)}')
                    composicion.add(patch.patch_id)
                    continue
                # Métricas MARGINALES (sobre la composición): las que ven la bitácora y el meta-mejorador.
                patch.metrics_before = dict(probe.metrics_before)
                patch.metrics_after = {**probe.metrics_after, 'ganancia_vs_campeon': verdict.ganancia}
                patch.razon = f'{probe.razon} (marginal sobre la composición; contra el campeón {verdict.ganancia:+.2%})'
            cfg = challenger
            s['accepted'].append((patch, cfg))
        s['cfg'] = cfg
        # 3) Tabú: lo rechazado no se re-propone durante TABU_GENS generaciones (con más datos se reintenta).
        #    Un parche que era bueno contra el campeón y solo sobró en la composición no entra al tabú.
        for patch in s['patches']:
            target = patch_target(patch)
            if not target or patch.patch_id in composicion:
                continue
            if patch.veredicto == 'rechazado':
                s['tabu'][target] = s['generation'] + TABU_GENS
            elif patch.veredicto == 'aceptado':
                s['tabu'].pop(target, None)
        return s

    def lineage(s):
        for patch, cfg in s['accepted']:
            s['repo'].commit(cfg, json.dumps(patch.model_dump(mode='json'), ensure_ascii=False))
        if os.getenv('DATABASE_URL'):
            from autoguard.db.session import session_scope
            from autoguard.db.repo import save_patch, save_agent_version
            with session_scope() as session:
                for patch in s['patches']:
                    stored = patch.model_copy(update={'patch_id': f'{root.name}-{s["variant"]}-{patch.patch_id}'})
                    save_patch(session, stored)
                for version in s['repo'].history():  # agente por variante: no tocar el campeón de producción
                    save_agent_version(session, version.model_copy(update={'agent': f"cotizador-{s['variant']}"}))
        # patch_id único por variante: el mejorador numera igual en `parametros` y `rsi` (T-32).
        _append(root / 'patches.jsonl', [{'variant': s['variant'], **p.model_dump(mode='json'),
                                          'patch_id': unique_patch_id(s['variant'], p.patch_id)}
                                         for p in s['patches']])
        return s

    def meta(s):
        if s['variant'] == 'rsi':
            strategy = s['meta'].update(s['patches'])
            _append(root / 'meta.jsonl', [dict(variant=s['variant'], **strategy.model_dump(mode='json'))])
        return s

    graph = build_graph(dict(recolector=recollect, analista=analyst, mejorador=improve,
                            evaluador=evaluator, linaje=lineage, meta=meta))
    # Benchmark: costo esperado real (oráculo) y costo realizado de TODAS las pólizas cotizadas. Solo se
    # usa para medir (regret de referencia y convergencia); ningún agente lo ve.
    bench = []
    for batch_index in range(batches):
        batch = simulator.sample_batch(batch_size)
        bench.append((simulator.oracle_expected_cost(batch), None))
        for variant, s in states.items():
            prices = quote_df(batch, s['cfg'])
            outcomes = simulator.resolve(batch, prices)
            predictions = batch.assign(prima=prices, prediction_id=batch['vehicle_id'],
                                       agent_version=f"cotizador@{s['repo'].current()[1][:7]}")
            outcomes['prediction_id'] = batch['vehicle_id'].to_numpy()
            if bench[-1][1] is None:  # costo_real no depende de las primas: igual para las 3 variantes
                bench[-1] = (bench[-1][0], outcomes['costo_real'].to_numpy(dtype=float))
            s['closed'].append(collect(predictions, outcomes))
            batch_loss = loss(prices, outcomes['costo_real'])
            s['regret'] += float(batch_loss.sum())
            curves.append(dict(variant=variant, batch=batch_index + 1,
                               polizas=(batch_index + 1) * batch_size,
                               loss=float(batch_loss.mean()), regret=s['regret'],
                               vendidas=int(outcomes['vendida'].sum()), generation=s['generation']))
            if (batch_index + 1) % k == 0 and variant != 'estatico':
                s['generation'] += 1
                s['variant'] = variant
                states[variant] = graph.invoke(s)
    for variant, s in states.items():
        _append(root / 'versions.jsonl', [dict(variant=variant, **v.model_dump(mode='json'))
                                         for v in s['repo'].history()])
    regrets = {v: s['regret'] for v, s in states.items()}
    frame = pd.DataFrame(curves)
    oracle = oracle_reference(bench)
    frame = frame.merge(pd.DataFrame(dict(batch=range(1, batches + 1), loss_oraculo=oracle['loss_por_lote'])),
                        on='batch')
    frame['ratio_oraculo'] = frame['loss'] / frame['loss_oraculo']
    frame.to_csv(root / 'curve.csv', index=False)
    convergence = {v: convergence_polizas(frame[frame.variant == v]) for v in variants}
    improvement = 1 - regrets['rsi'] / regrets['estatico']
    max_improvement = 1 - oracle['regret'] / regrets['estatico']
    conv_rsi, conv_par = convergence['rsi'], convergence['parametros']
    summary = dict(simulados=True, seed=seed, batches=batches, batch_size=batch_size, k=k,
                   regret=regrets, mejora_rsi=improvement, convergencia_polizas=convergence,
                   convergencia_meseta_polizas={v: plateau_polizas(frame[frame.variant == v]) for v in variants},
                   gate2=bool(improvement >= .4 and conv_rsi is not None and
                              (conv_par is None or conv_rsi < conv_par)),
                   referencia_oraculo=dict(
                       regret=oracle['regret'], multiplicador_cuantil=oracle['multiplicador'],
                       mejora_maxima_posible=max_improvement,
                       fraccion_capturada_rsi=improvement / max_improvement if max_improvement > 0 else None),
                   exceso_final_vs_oraculo={v: float(frame[frame.variant == v].ratio_oraculo.tail(CONV_WINDOW).mean() - 1)
                                            for v in variants},
                   tasa_aceptacion_rsi=acceptance_by_generation(root / 'patches.jsonl', 'rsi'),
                   elapsed_seconds=time.perf_counter() - start,
                   database_requested=bool(os.getenv('DATABASE_URL')),
                   limitaciones=[
                       f'Convergencia: primer N desde el cual la pérdida media móvil ({CONV_WINDOW} lotes) queda, '
                       f'para el resto de la corrida, dentro de {CONV_TOL:.0%} de la del oráculo calibrado '
                       '(costo esperado real × el multiplicador que minimiza la pérdida congelada). Una '
                       'variante que nunca llega no converge (null). `gate2` usa esta definición.',
                       f'Convergencia a la meseta (secundaria): primer N desde el cual la media móvil queda dentro de '
                       f'{CONV_TOL:.0%} de su propio nivel final, solo si el error bajó ≥10% (el estático no converge).',
                       'El oráculo es solo referencia del benchmark: conoce el riesgo oculto desde la póliza 1, '
                       'por eso su mejora sobre el estático es la cota superior alcanzable.',
                       'BD opcional guarda parches y versiones; curvas en disco.'])
    (root / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--batches', type=int, default=60)
    parser.add_argument('--batch-size', type=int, default=200)
    parser.add_argument('--k', type=int, default=3)
    parser.add_argument('--output-dir')
    args = parser.parse_args()
    print(json.dumps(run_experiment(**vars(args)), indent=2))


if __name__ == '__main__':
    main()
