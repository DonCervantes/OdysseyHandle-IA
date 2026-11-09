"""Aprendiz online IDEAL: conoce la estructura verdadera (factores + marca + daños + 3 reglas). Cada K lotes
reajusta (descenso por coordenadas, encogimiento opcional) con TODAS las ventas train acumuladas y cotiza
los siguientes K lotes. Sin holdout ni ε. Cota superior de lo que un RSI puede lograr con este flujo de datos.
"""
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from autoguard.sim.market import MarketSimulator
from autoguard.config_schema import load_config, CotizadorConfig
from autoguard.agents.cotizador import quote_df
from autoguard.evaluator.objective import loss
from autoguard.evaluator.evaluator import split_holdout
from autoguard.rsi.analista import optimal_multiplier, best_multiplier

sys.path.insert(0, str(Path(__file__).parent))
from ceiling_lib import start_config, groups  # noqa: E402

seed = int(sys.argv[1]) if len(sys.argv) > 1 else 42
shrink = len(sys.argv) > 2 and sys.argv[2] == "shrink"
cfg0 = load_config(Path("configs/agents/cotizador.yaml"))
sim = MarketSimulator(seed)
K, B, N = 3, 60, 200
cfg = None
closed = []
regret = 0.0
static_regret = 0.0
for b in range(B):
    batch = sim.sample_batch(N)
    use = cfg if cfg is not None else cfg0
    p = quote_df(batch, use)
    out = sim.resolve(batch, p)
    c = out["costo_real"].to_numpy()
    regret += loss(p, c).sum()
    static_regret += loss(quote_df(batch, cfg0), c).sum()
    sold = batch[out["vendida"].to_numpy()].assign(costo_real=c[out["vendida"].to_numpy()])
    closed.append(sold)
    if (b + 1) % K == 0:
        allc = pd.concat(closed, ignore_index=True)
        train, _ = split_holdout(allc)
        train = train.reset_index(drop=True)
        ct = train["costo_real"].to_numpy()
        cur = start_config(cfg0, allc) if cfg is None else cfg
        for _ in range(8):
            for key, m in groups(cur, train):
                if m.sum() < 5:
                    continue
                pp = quote_df(train, cur)
                mult = best_multiplier(pp[m], ct[m]) if shrink else optimal_multiplier(pp[m], ct[m])
                d = cur.model_dump()
                kind, a, bb = key
                if kind == "cat":
                    d["factores"][a]["categorias"][bb] = float(np.clip(d["factores"][a]["categorias"][bb] * mult, .2, 5))
                elif kind == "bin":
                    d["factores"][a]["valores"][bb] = float(np.clip(d["factores"][a]["valores"][bb] * mult, .2, 5))
                else:
                    d["reglas"][a]["multiplicador"] = float(np.clip(d["reglas"][a]["multiplicador"] * mult, .2, 5))
                cur = CotizadorConfig.model_validate(d)
        cfg = cur
print(f"seed {seed} shrink={shrink}: estatico {static_regret/1e6:.2f}M  ideal-online {regret/1e6:.2f}M  "
      f"mejora {1-regret/static_regret:.1%}")
