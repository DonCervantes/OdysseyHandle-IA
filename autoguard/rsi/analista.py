"""Analista de errores por segmento (T-07).

Entrada: DataFrame del recolector (VEHICLE_COLUMNS + prima, costo_real, loss, error_rel).
Segmentos candidatos: bins de antigüedad, kilometraje y siniestros; categorías de uso, zona y marca;
y todos los pares de condiciones de variables distintas. Por segmento (n ≥ min_n):

- sesgo_medio = media de error_rel (>0 sobrecotiza, <0 subcotiza)
- p_value     = t-test de una muestra vs 0 (scipy)
- impacto     = suma de loss del segmento × |sesgo_medio|

Se devuelven las top_k hipótesis significativas (p < 0.05) por impacto, evitando redundancia: se
descarta un segmento contenido en (o que contiene a) otro ya elegido con el mismo signo de sesgo.
El texto es determinístico (sin LLM).
"""
from __future__ import annotations

from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from autoguard import segments
from autoguard.contracts import Hypothesis
from autoguard.evaluator.objective import loss as objective_loss

P_MAX = 0.05
MAX_CATEGORIAS = 15  # por variable categórica (las más frecuentes), acota el número de pares

# Bordes inferiores de los bins numéricos (enteros). El último bin queda abierto (solo `_min`).
BINS: dict[str, list[int]] = {
    "antiguedad": [0, 5, 10, 20, 30],
    "kilometraje": [0, 50_000, 100_000, 150_000, 200_000],
    "siniestros_previos": [0, 1, 2, 3],
}
CATEGORICAS = ["uso", "zona", "marca"]
ORDEN = ["antiguedad", "kilometraje", "siniestros_previos", "uso", "zona", "marca"]


def _py(v: Any) -> Any:
    return v.item() if isinstance(v, np.generic) else v


def _single_segments(df: pd.DataFrame) -> list[tuple[str, dict[str, Any]]]:
    """(variable, segmento) para cada condición de una variable."""
    out: list[tuple[str, dict[str, Any]]] = []
    for var in ORDEN:
        if var in BINS:
            if var not in df.columns and not (var == "antiguedad" and "anio" in df.columns):
                continue
            edges = BINS[var]
            for i, lo in enumerate(edges):
                hi = edges[i + 1] - 1 if i + 1 < len(edges) else None
                seg: dict[str, Any] = {}
                if hi is not None and hi == lo:
                    seg[var] = lo
                else:
                    if i > 0:
                        seg[f"{var}_min"] = lo
                    if hi is not None:
                        seg[f"{var}_max"] = hi
                out.append((var, seg))
        elif var in df.columns:
            vals = df[var].dropna().value_counts().head(MAX_CATEGORIAS).index
            for v in sorted(vals, key=str):
                out.append((var, {var: _py(v)}))
    return out


def _texto(seg: dict[str, Any], n: int, sesgo: float, p: float) -> str:
    accion = "sobrecotiza" if sesgo > 0 else "subcotiza"
    mult = 1.0 / (1.0 + sesgo) if sesgo > -1 else float("inf")
    return (
        f"En el segmento [{segments.describe(seg)}] el cotizador {accion} en promedio "
        f"{abs(sesgo) * 100:.1f}% (n={n}, p={p:.2g}). Un multiplicador ≈ {mult:.3f} para este "
        f"segmento corregiría el sesgo."
    )


def analyze(errors: pd.DataFrame, top_k: int = 3, min_n: int = 30) -> list[Hypothesis]:
    """Agrupa errores por segmentos candidatos (1 y 2 variables), calcula sesgo medio de error_rel,
    significancia (t-test vs 0) e impacto; devuelve las top_k hipótesis significativas (p<0.05)."""
    if errors is None or len(errors) == 0 or top_k <= 0:
        return []
    df = errors.reset_index(drop=True)
    if "error_rel" not in df.columns:
        df = df.assign(error_rel=(df["prima"] - df["costo_real"]) / df["costo_real"])
    if "loss" not in df.columns:
        df = df.assign(loss=objective_loss(df["prima"], df["costo_real"]))
    err = df["error_rel"].to_numpy(dtype=float)
    ok = np.isfinite(err)
    if not ok.all():
        df, err = df[ok].reset_index(drop=True), err[ok]
    if len(df) < min_n:
        return []
    lss = df["loss"].to_numpy(dtype=float)

    singles = [(var, seg, segments.segment_mask(df, seg)) for var, seg in _single_segments(df)]
    singles = [s for s in singles if s[2].sum() >= min_n]
    candidates: list[tuple[dict[str, Any], np.ndarray]] = [(seg, m) for _, seg, m in singles]
    for (v1, s1, m1), (v2, s2, m2) in combinations(singles, 2):
        if v1 == v2:
            continue
        m = m1 & m2
        if m.sum() >= min_n:
            candidates.append(({**s1, **s2}, m))

    scored = []
    for seg, m in candidates:
        e = err[m]
        n = int(m.sum())
        sesgo = float(e.mean())
        if e.std(ddof=1) == 0:
            p = 0.0 if sesgo != 0 else 1.0
        else:
            p = float(stats.ttest_1samp(e, 0.0).pvalue)
        if not (p < P_MAX) or sesgo == 0:
            continue
        impacto = float(lss[m].sum() * abs(sesgo))
        scored.append((impacto, -len(seg), seg, m, n, sesgo, p))
    # orden determinístico: impacto desc, luego segmentos más simples, luego por descripción
    scored.sort(key=lambda t: (-t[0], -t[1], segments.describe(t[2])))

    chosen: list[tuple[np.ndarray, float]] = []
    out: list[Hypothesis] = []
    for impacto, _, seg, m, n, sesgo, p in scored:
        redundante = any(
            np.sign(sesgo) == np.sign(s2) and (not (m & ~m2).any() or not (m2 & ~m).any())
            for m2, s2 in chosen
        )
        if redundante:
            continue
        chosen.append((m, sesgo))
        out.append(Hypothesis(segmento=seg, n=n, sesgo_medio=sesgo, p_value=p, impacto=impacto,
                              texto=_texto(seg, n, sesgo, p)))
        if len(out) >= top_k:
            break
    return out
