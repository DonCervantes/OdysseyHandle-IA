"""Techo asintótico: descenso por coordenadas ideal (sin holdout ni ε) con la estructura VERDADERA
expresada en el lenguaje de config (factores + marca + daños + 3 reglas de interacción).
Compara entrenar con TODAS las pólizas vs solo las VENDIDAS (censura), y mide el regret sobre todas.
"""
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from autoguard.sim.market import MarketSimulator
from autoguard.config_schema import load_config, CotizadorConfig
from autoguard.agents.cotizador import quote_df
from autoguard.evaluator.objective import loss
from autoguard.rsi.analista import optimal_multiplier

seed = int(sys.argv[1]) if len(sys.argv) > 1 else 42
cfg0 = load_config(Path("configs/agents/cotizador.yaml"))
sim = MarketSimulator(seed)
df = pd.concat([sim.sample_batch(200) for _ in range(60)], ignore_index=True)
p0 = quote_df(df, cfg0)
out = sim.resolve(df, p0)
c = out["costo_real"].to_numpy()
sold = out["vendida"].to_numpy()

d = cfg0.model_dump()
d["factores"]["marca"] = {"variable": "marca", "categorias": {m: 1.0 for m in df.marca.unique()}, "default": 1.0}
d["factores"]["danos_costo"] = {"variable": "danos_costo", "bins": [0, 1, 10000, 20000], "valores": [1, 1, 1, 1], "default": 1}
d["reglas"] = [
    {"id": "a", "segmento": {"antiguedad_min": 30, "siniestros_previos": 1}, "multiplicador": 1.0},
    {"id": "b", "segmento": {"uso": "app_transporte", "zona": "CDMX"}, "multiplicador": 1.0},
    {"id": "c", "segmento": {"uso": "comercial", "kilometraje_min": 200000}, "multiplicador": 1.0},
]
start = CotizadorConfig.model_validate(d)


def groups(cfg, frame):
    from autoguard import segments
    out = []
    for name, f in cfg.factores.items():
        col = (2026 - frame["anio"]) if f.variable == "antiguedad" else frame[f.variable]
        if f.categorias is not None:
            keys = col.astype(str).to_numpy()
            for k in f.categorias:
                out.append((("cat", name, k), keys == k))
        else:
            idx = np.searchsorted(np.asarray(f.bins, float), col.to_numpy(float), side="right") - 1
            for i in range(len(f.bins)):
                out.append((("bin", name, i), idx == i))
    for i, r in enumerate(cfg.reglas):
        out.append((("rule", i, None), segments.segment_mask(frame, r.segmento)))
    return out


def fit(train_mask, iters=25):
    cfg = start
    tr = df[train_mask].reset_index(drop=True)
    ct = c[train_mask]
    for _ in range(iters):
        p = quote_df(tr, cfg)
        d = cfg.model_dump()
        for (kind, a, b), m in groups(cfg, tr):
            if m.sum() < 5:
                continue
            mult = optimal_multiplier(p[m], ct[m])
            if kind == "cat":
                d["factores"][a]["categorias"][b] = float(np.clip(d["factores"][a]["categorias"][b] * mult, .2, 5))
            elif kind == "bin":
                d["factores"][a]["valores"][b] = float(np.clip(d["factores"][a]["valores"][b] * mult, .2, 5))
            else:
                d["reglas"][a]["multiplicador"] = float(np.clip(d["reglas"][a]["multiplicador"] * mult, .2, 5))
            cfg = CotizadorConfig.model_validate(d)
            p = quote_df(tr, cfg)
    return cfg


e = sim.oracle_expected_cost(df)
mo = optimal_multiplier(e, c)
static = loss(p0, c).sum()
orac = loss(e * mo, c).sum()
print(f"seed {seed}: estatico {static/1e6:.2f}M  oraculo {orac/1e6:.2f}M  (cota {1-orac/static:.1%})")
for name, mask in [("todas", np.ones(len(df), bool)), ("vendidas(estatico)", sold)]:
    cfg = fit(mask)
    l = loss(quote_df(df, cfg), c).sum()
    print(f"  ajuste con {name:20s} n={mask.sum():5d}: regret si se usara desde la póliza 1 = {l/1e6:.2f}M "
          f"(mejora {1-l/static:.1%}, exceso vs oráculo {l/orac-1:+.1%})")
    r = cfg.reglas[0].multiplicador
    print(f"     regla ant>=30&sin=1 -> {r:.3f} (real 0.65), marcas BMW {cfg.factores['marca'].categorias.get('BMW', 1):.2f}")
