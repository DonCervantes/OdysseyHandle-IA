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

import pandas as pd

from autoguard.agents.cotizador import quote_df
from autoguard.config_schema import load_config
from autoguard.contracts import ARMS
from autoguard.evaluator.evaluator import evaluate, split_holdout
from autoguard.evaluator.objective import loss
from autoguard.rsi.analista import analyze
from autoguard.rsi.graph import build_graph
from autoguard.rsi.lineage import ConfigRepo
from autoguard.rsi.mejorador import propose
from autoguard.rsi.meta import MetaImprover
from autoguard.rsi.recolector import collect
from autoguard.sim.market import MarketSimulator


def _append(path, records):
    with path.open('a', encoding='utf-8') as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + '\n')


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
                               meta=MetaImprover(ARMS, seed), closed=[], regret=0.0, generation=0)

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
        arms = ['ajuste_factor'] * 3 if s['variant'] == 'parametros' else s['meta'].choose_arms(3)
        s['patches'] = propose(s['cfg'], s['hypotheses'], arms, s['generation'],
                               lecciones=s['meta'].lecciones)
        return s

    def evaluator(s):
        s['accepted'] = []
        for patch in s['patches']:
            verdict, challenger = evaluate(s['cfg'], patch, s['holdout'])
            if verdict.aceptado:
                s['cfg'] = challenger
                s['accepted'].append((patch, challenger))
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
                for version in s['repo'].history():
                    save_agent_version(session, version)
        _append(root / 'patches.jsonl', [dict(variant=s['variant'], **p.model_dump(mode='json'))
                                        for p in s['patches']])
        return s

    def meta(s):
        if s['variant'] == 'rsi':
            strategy = s['meta'].update(s['patches'])
            _append(root / 'meta.jsonl', [dict(variant=s['variant'], **strategy.model_dump(mode='json'))])
        return s

    graph = build_graph(dict(recolector=recollect, analista=analyst, mejorador=improve,
                            evaluador=evaluator, linaje=lineage, meta=meta))
    for batch_index in range(batches):
        batch = simulator.sample_batch(batch_size)
        for variant, s in states.items():
            prices = quote_df(batch, s['cfg'])
            outcomes = simulator.resolve(batch, prices)
            predictions = batch.assign(prima=prices, prediction_id=batch['vehicle_id'],
                                       agent_version=f"cotizador@{s['repo'].current()[1][:7]}")
            outcomes['prediction_id'] = batch['vehicle_id'].to_numpy()
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
    pd.DataFrame(curves).to_csv(root / 'curve.csv', index=False)
    for variant, s in states.items():
        _append(root / 'versions.jsonl', [dict(variant=variant, **v.model_dump(mode='json'))
                                         for v in s['repo'].history()])
    regrets = {v: s['regret'] for v, s in states.items()}
    # Convergencia observable: primera ventana de 3 lotes dentro del 5% de su media final.
    frame = pd.DataFrame(curves)
    convergence = {}
    for variant in variants:
        rows = frame[frame.variant == variant]
        final = rows.loss.tail(3).mean()
        rolling = rows.loss.rolling(3).mean()
        hits = rows.loc[(rolling - final).abs() <= final * .05, 'polizas']
        convergence[variant] = int(hits.iloc[0]) if len(hits) else None
    improvement = 1 - regrets['rsi'] / regrets['estatico']
    summary = dict(simulados=True, seed=seed, batches=batches, batch_size=batch_size, k=k,
                   regret=regrets, mejora_rsi=improvement, convergencia_polizas=convergence,
                   gate2=bool(improvement >= .4 and convergence['rsi'] is not None and
                              convergence['parametros'] is not None and
                              convergence['rsi'] < convergence['parametros']),
                   elapsed_seconds=time.perf_counter() - start,
                   database_requested=bool(os.getenv('DATABASE_URL')),
                   limitaciones=['Convergencia: ventana de 3 lotes dentro de 5% de loss final.',
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
