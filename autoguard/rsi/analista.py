"""Analista de errores por segmento (T-07, reorientado a la pérdida asimétrica en T-23).

Entrada: DataFrame del recolector (VEHICLE_COLUMNS + prima, costo_real, loss, error_rel).
Segmentos candidatos: bins de antigüedad, kilometraje, siniestros y daños preexistentes; categorías de
uso, zona y marca; y todos los pares de condiciones de variables distintas. Por segmento (n ≥ min_n):

- sesgo_medio = media de error_rel (>0 sobrecotiza, <0 subcotiza). Solo descriptivo.
- multiplicador óptimo m* = argmin_m Σ L(m·prima, costo) con la pérdida CONGELADA L. Con L lineal por
  tramos (α por cobrar de menos, β por cobrar de más) el argmin exacto es el cuantil de nivel α/(α+β) de
  costo/prima ponderado por prima (`best_multiplier`), no el que anula el sesgo medio. Se encoge hacia 1
  en escala log por n/(n+SHRINK_N0) para no sobre-reaccionar a segmentos chicos.
- impacto     = pérdida reducible = Σ L(prima, costo) − Σ L(m*·prima, costo) en el segmento.
- p_value     = prueba de signo: en el óptimo, P(costo > prima) = β/(α+β); se contrasta la fracción
  observada de pólizas subcotizadas contra ese valor (aproximación normal a la binomial).

Se devuelven las top_k hipótesis significativas (p < 0.05) por impacto, evitando redundancia: se
descarta un segmento contenido en (o que contiene a) otro ya elegido con el mismo signo de sesgo.
El texto es determinístico (sin LLM).

α y β NO se importan: se leen evaluando la pérdida congelada (`loss(0, 1) = α`, `loss(1, 0) = β`), de modo
que el RSI solo hace lectura de `loss`.
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

# Pesos de la pérdida congelada, leídos (no importados) de la función objetivo.
ALPHA_L = float(objective_loss(0.0, 1.0))  # cobrar 0 a un costo 1 => α
BETA_L = float(objective_loss(1.0, 0.0))  # cobrar 1 a un costo 0 => β
NIVEL_CUANTIL = ALPHA_L / (ALPHA_L + BETA_L)  # 0.6 con α=1.5, β=1.0
P_SUBCOTIZA_OPTIMO = 1.0 - NIVEL_CUANTIL  # fracción de pólizas con costo > prima en el óptimo
SHRINK_N0 = 30  # encogimiento: m = exp(log(m*) · n / (n + SHRINK_N0))
MULT_MIN, MULT_MAX = 0.5, 2.0  # corrección máxima por parche (estabilidad ante ruido)

# Bordes inferiores de los bins numéricos (enteros). El último bin queda abierto (solo `_min`).
BINS: dict[str, list[int]] = {
    "antiguedad": [0, 5, 10, 20, 30],
    "kilometraje": [0, 50_000, 100_000, 150_000, 200_000],
    "siniestros_previos": [0, 1, 2, 3],
    # daños preexistentes en MXN (enteros): sin daño / leve / medio / fuerte
    "danos_costo": [0, 1, 10_000, 20_000],
}
CATEGORICAS = ["uso", "zona", "marca"]
ORDEN = ["antiguedad", "kilometraje", "siniestros_previos", "uso", "zona", "marca", "danos_costo"]


# ---------------------------------------------------------------- multiplicador óptimo
def row_loss(prima, costo) -> np.ndarray:
    """Pérdida congelada por póliza (lectura de `objective.loss`)."""
    return np.asarray(objective_loss(prima, costo), dtype=float)


def total_loss(prima, costo) -> float:
    """Σ de la pérdida congelada (lectura de `objective.loss`)."""
    return float(np.sum(objective_loss(prima, costo)))


def optimal_multiplier(prima, costo) -> float:
    """argmin_m Σ L(m·prima, costo), exacto (sin encogimiento ni cotas).

    Σ_i p_i·[α(r_i − m)⁺ + β(m − r_i)⁺] con r_i = c_i/p_i es convexa en m; su subgradiente se anula
    cuando la fracción del peso Σp de las pólizas con r_i < m alcanza α/(α+β): cuantil ponderado.
    """
    p = np.asarray(prima, dtype=float)
    c = np.asarray(costo, dtype=float)
    ok = np.isfinite(p) & np.isfinite(c) & (p > 0)
    p, c = p[ok], c[ok]
    if len(p) == 0:
        return 1.0
    r = c / p
    order = np.argsort(r, kind="stable")
    r, w = r[order], p[order]
    cw = np.cumsum(w)
    k = int(np.searchsorted(cw, NIVEL_CUANTIL * cw[-1], side="left"))
    return float(r[min(k, len(r) - 1)])


def best_multiplier(prima, costo, n0: float = SHRINK_N0) -> float:
    """Multiplicador corrector para un grupo de pólizas: `optimal_multiplier` encogido hacia 1 en escala
    log por n/(n+n0) y acotado a [MULT_MIN, MULT_MAX]."""
    n = int(np.isfinite(np.asarray(costo, dtype=float)).sum())
    if n == 0:
        return 1.0
    m = optimal_multiplier(prima, costo)
    if not np.isfinite(m) or m <= 0:
        return MULT_MAX if not np.isfinite(m) else MULT_MIN
    shrunk = float(np.exp(np.log(m) * n / (n + n0)))
    return float(min(MULT_MAX, max(MULT_MIN, shrunk)))


def _sign_test_p(costo: np.ndarray, prima: np.ndarray) -> float:
    """p-value bilateral de H0: P(costo > prima) = P_SUBCOTIZA_OPTIMO (la prima ya es óptima)."""
    n = len(costo)
    if n == 0:
        return 1.0
    k = float(np.sum(costo > prima))
    q = P_SUBCOTIZA_OPTIMO
    sd = np.sqrt(n * q * (1 - q))
    z = (k - n * q) / sd
    return float(2 * stats.norm.sf(abs(z)))


def _sign_test_p_many(masks: np.ndarray, under: np.ndarray) -> list[float]:
    """`_sign_test_p` para cada fila de `masks` (bool, segmentos × pólizas); `under` = costo > prima."""
    n = masks.sum(axis=1).astype(float)
    k = (masks & under).sum(axis=1).astype(float)
    q = P_SUBCOTIZA_OPTIMO
    with np.errstate(divide="ignore", invalid="ignore"):
        z = (k - n * q) / np.sqrt(n * q * (1 - q))
    p = 2 * stats.norm.sf(np.abs(z))
    return [1.0 if ni == 0 else float(pi) for ni, pi in zip(n, p)]


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


def _texto(seg: dict[str, Any], n: int, sesgo: float, p: float, mult: float, reducible: float) -> str:
    accion = "sobrecotiza" if sesgo > 0 else "subcotiza"
    return (
        f"En el segmento [{segments.describe(seg)}] el cotizador {accion} en promedio "
        f"{abs(sesgo) * 100:.1f}% (n={n}, p={p:.2g}). Con la pérdida asimétrica, un multiplicador "
        f"≈ {mult:.3f} para este segmento reduciría la pérdida en train en {reducible:,.0f}."
    )


def analyze(errors: pd.DataFrame, top_k: int = 3, min_n: int = 30) -> list[Hypothesis]:
    """Agrupa errores por segmentos candidatos (1 y 2 variables), calcula el multiplicador que minimiza la
    pérdida congelada, la pérdida reducible (impacto) y la significancia (prueba de signo contra el
    óptimo); devuelve las top_k hipótesis significativas (p<0.05) por pérdida reducible."""
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
    prima = df["prima"].to_numpy(dtype=float)
    costo = df["costo_real"].to_numpy(dtype=float)

    singles = [(var, seg, segments.segment_mask(df, seg)) for var, seg in _single_segments(df)]
    singles = [s for s in singles if s[2].sum() >= min_n]
    candidates: list[tuple[dict[str, Any], np.ndarray]] = [(seg, m) for _, seg, m in singles]
    for (v1, s1, m1), (v2, s2, m2) in combinations(singles, 2):
        if v1 == v2:
            continue
        m = m1 & m2
        if m.sum() >= min_n:
            candidates.append(({**s1, **s2}, m))

    # Prueba de signo vectorizada sobre todos los candidatos a la vez (misma aritmética que
    # `_sign_test_p`, elemento a elemento: resultado idéntico, sin una llamada a scipy por segmento).
    pvals = _sign_test_p_many(np.array([m for _, m in candidates]), costo > prima) if candidates else []
    scored = []
    for (seg, m), p in zip(candidates, pvals):
        if not (p < P_MAX):
            continue
        n = int(m.sum())
        sesgo = float(err[m].mean())
        if sesgo == 0:
            continue
        mult = best_multiplier(prima[m], costo[m])
        reducible = float(lss[m].sum() - total_loss(mult * prima[m], costo[m]))
        if not reducible > 0:
            continue
        scored.append((reducible, -len(seg), seg, m, n, sesgo, p, mult))
    # orden determinístico: impacto desc, luego segmentos más simples, luego por descripción
    scored.sort(key=lambda t: (-t[0], -t[1], segments.describe(t[2])))

    chosen: list[tuple[np.ndarray, float]] = []
    out: list[Hypothesis] = []
    for impacto, _, seg, m, n, sesgo, p, mult in scored:
        redundante = any(
            np.sign(sesgo) == np.sign(s2) and (not (m & ~m2).any() or not (m2 & ~m).any())
            for m2, s2 in chosen
        )
        if redundante:
            continue
        chosen.append((m, sesgo))
        out.append(Hypothesis(segmento=seg, n=n, sesgo_medio=sesgo, p_value=p, impacto=impacto,
                              texto=_texto(seg, n, sesgo, p, mult, impacto)))
        if len(out) >= top_k:
            break
    return out
