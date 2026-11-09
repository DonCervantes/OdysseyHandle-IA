import numpy as np
from autoguard import segments
from autoguard.config_schema import CotizadorConfig


def start_config(cfg0, frame):
    d = cfg0.model_dump()
    d["factores"]["marca"] = {"variable": "marca", "categorias": {m: 1.0 for m in sorted(frame.marca.unique())},
                              "default": 1.0}
    d["factores"]["danos_costo"] = {"variable": "danos_costo", "bins": [0, 1, 10000, 20000],
                                    "valores": [1, 1, 1, 1], "default": 1}
    d["reglas"] = [
        {"id": "a", "segmento": {"antiguedad_min": 30, "siniestros_previos": 1}, "multiplicador": 1.0},
        {"id": "b", "segmento": {"uso": "app_transporte", "zona": "CDMX"}, "multiplicador": 1.0},
        {"id": "c", "segmento": {"uso": "comercial", "kilometraje_min": 200000}, "multiplicador": 1.0},
    ]
    return CotizadorConfig.model_validate(d)


def groups(cfg, frame):
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
