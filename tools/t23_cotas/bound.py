"""Cota: pérdida por póliza del estático vs oráculo (cuantil 0.6) en la secuencia de seed dada."""
import sys
import numpy as np
from pathlib import Path
from scipy.special import ndtri
from autoguard.sim.market import MarketSimulator, _SIGMA_COSTO
from autoguard.config_schema import load_config
from autoguard.agents.cotizador import quote_df
from autoguard.evaluator.objective import loss

seed = int(sys.argv[1]) if len(sys.argv) > 1 else 42
cfg = load_config(Path("configs/agents/cotizador.yaml"))
sim = MarketSimulator(seed)
import pandas as pd
batch = pd.concat([sim.sample_batch(200) for _ in range(60)], ignore_index=True)
p0 = quote_df(batch, cfg)
out = sim.resolve(batch, p0)
c = out["costo_real"].to_numpy()
e = sim.oracle_expected_cost(batch)
q = np.exp(_SIGMA_COSTO * ndtri(0.6) - 0.5 * _SIGMA_COSTO**2)
for name, p in [("estatico", p0), ("oraculo_media", e), ("oraculo_q0.6", e * q)]:
    l = loss(p, c)
    print(f"{name:15s} total={l.sum()/1e6:7.2f}M  media={l.mean():8.1f}")
# escala global óptima sobre estático
best = min((loss(p0 * s, c).sum(), s) for s in np.linspace(0.6, 1.6, 101))
print(f"estatico*escala_opt s={best[1]:.2f} total={best[0]/1e6:.2f}M")
print("vendidas estatico:", out["vendida"].mean())
