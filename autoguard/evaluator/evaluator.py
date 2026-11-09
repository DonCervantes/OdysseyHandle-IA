"""Evaluador CONGELADO (T-09). Fuera del alcance de escritura del grafo RSI.

- `split_holdout`: partición determinística por sha256(vehicle_id) → el mismo vehículo cae siempre del
  mismo lado, sin depender de semillas ni del orden de las filas.
- `evaluate`: valida el parche (apply_patch + lista blanca). Un parche inválido se rechaza SIN leer el
  holdout. Si es válido, re-cotiza el holdout con campeón y retador (`cotizador.quote_df`) y acepta si
  la ganancia relativa en `objective.loss` es ≥ DELTA y ningún segmento con n ≥ MIN_SEGMENT_N empeora
  más de EPSILON.

Segmentos revisados para regresión (determinísticos):
- un segmento por bin de cada factor numérico del campeón y del retador (sobre variables enteras de
  vehículo: antiguedad, kilometraje, siniestros_previos, anio),
- un segmento por categoría observada en el holdout de uso, zona, marca,
- el segmento del parche y el de cada regla del campeón y del retador.
"""
from __future__ import annotations

import hashlib
from typing import Any

import numpy as np
import pandas as pd

from autoguard import segments
from autoguard.agents.cotizador import quote_df
from autoguard.config_schema import CotizadorConfig, apply_patch
from autoguard.contracts import VARIABLES_PERMITIDAS, VARIABLES_PROHIBIDAS, Patch, Verdict
from autoguard.evaluator import objective

_CATEGORICAS = ("uso", "zona", "marca")
_NUMERICAS_ENTERAS = ("antiguedad", "anio", "kilometraje", "siniestros_previos")


# ---------------------------------------------------------------- holdout
def _hash_unit(vehicle_id: Any) -> float:
    h = hashlib.sha256(str(vehicle_id).encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big") / 2.0**64


def split_holdout(closed: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(train, holdout) determinístico por hash de vehicle_id (HOLDOUT_FRACTION). El mejorador solo ve train."""
    if len(closed) == 0:
        return closed.copy(), closed.copy()
    u = closed["vehicle_id"].map(_hash_unit).to_numpy(dtype=float)
    is_hold = u < objective.HOLDOUT_FRACTION
    return closed.loc[~is_hold].copy(), closed.loc[is_hold].copy()


# ---------------------------------------------------------------- validación
def _patch_variables(patch: Patch) -> set[str]:
    """Variables que el parche menciona explícitamente (segmento, reglas y factores que agrega/modifica)."""
    vars_: set[str] = set(segments.segment_variables(patch.segmento))
    for ch in patch.cambios:
        v = ch.value
        if ch.op == "add_rule" and isinstance(v, dict):
            vars_.update(segments.segment_variables(v.get("segmento") or {}))
        elif ch.op == "add_factor" and isinstance(v, dict) and "variable" in v:
            vars_.add(str(v["variable"]))
        elif ch.op == "set" and ch.path.endswith(".variable"):
            vars_.add(str(v))
        elif ch.op == "set" and ch.path.endswith(".segmento") and isinstance(v, dict):
            vars_.update(segments.segment_variables(v))
    return vars_


def _validate(champion: CotizadorConfig, patch: Patch) -> tuple[CotizadorConfig | None, str]:
    vars_ = _patch_variables(patch)
    prohibidas = sorted(v for v in vars_ if v in VARIABLES_PROHIBIDAS)
    if prohibidas:
        return None, f"variable prohibida: {', '.join(prohibidas)}"
    fuera = sorted(v for v in vars_ if v not in VARIABLES_PERMITIDAS)
    if fuera:
        return None, f"variable fuera de lista blanca: {', '.join(fuera)}"
    try:
        challenger = apply_patch(champion, patch)  # re-valida lista blanca y rangos
    except Exception as e:  # ValueError / ValidationError / KeyError / IndexError / TypeError
        return None, f"parche no aplica: {type(e).__name__}: {str(e).splitlines()[0][:200]}"
    return challenger, ""


# ---------------------------------------------------------------- segmentos
def _numeric_segments(var: str, bins: list[float]) -> list[dict[str, Any]]:
    out = []
    for i, lo in enumerate(bins):
        seg: dict[str, Any] = {f"{var}_min": lo}
        if i + 1 < len(bins):
            seg[f"{var}_max"] = bins[i + 1] - 1  # variables enteras: [lo, next-1]
        out.append(seg)
    return out


def _regression_segments(holdout: pd.DataFrame, cfgs: list[CotizadorConfig], patch: Patch) -> list[dict[str, Any]]:
    segs: list[dict[str, Any]] = []
    for cfg in cfgs:
        for f in cfg.factores.values():
            if f.bins is not None and f.variable in _NUMERICAS_ENTERAS:
                segs.extend(_numeric_segments(f.variable, list(f.bins)))
    for var in _CATEGORICAS:
        if var in holdout.columns:
            for val in sorted(holdout[var].dropna().astype(str).unique()):
                segs.append({var: val})
    if patch.segmento:
        segs.append(dict(patch.segmento))
    for cfg in cfgs:
        segs.extend(dict(r.segmento) for r in cfg.reglas)
    # dedupe preservando orden; descarta segmentos sobre columnas ausentes
    seen: set[str] = set()
    uniq = []
    for s in segs:
        key = repr(sorted(s.items()))
        has_cols = all(v in holdout.columns or (v == "antiguedad" and "anio" in holdout.columns)
                       for v in segments.segment_variables(s))
        if key not in seen and has_cols and s:
            seen.add(key)
            uniq.append(s)
    return uniq


# ---------------------------------------------------------------- evaluación
def _reject(patch: Patch, razon: str, lb: float = 0.0, la: float = 0.0, g: float = 0.0) -> Verdict:
    return Verdict(patch_id=patch.patch_id, aceptado=False, loss_before=lb, loss_after=la, ganancia=g,
                   razones=[razon])


def evaluate(champion: CotizadorConfig, patch: Patch, holdout: pd.DataFrame) -> tuple[Verdict, CotizadorConfig | None]:
    """Valida el parche (apply_patch + lista blanca; inválido => rechazado sin evaluar), re-cotiza el
    holdout con campeón y retador, acepta si ganancia >= DELTA y ningún segmento (n>=MIN_SEGMENT_N)
    empeora más de EPSILON. Devuelve (veredicto, config_retador o None)."""
    challenger, err = _validate(champion, patch)
    if challenger is None:
        # inválido: NO se toca el holdout
        return _reject(patch, f"invalido: {err}"), None

    if len(holdout) == 0:
        return _reject(patch, "holdout vacío: no se puede evaluar"), None

    costo = holdout["costo_real"].to_numpy(dtype=float)
    l_before = objective.loss(quote_df(holdout, champion), costo)
    l_after = objective.loss(quote_df(holdout, challenger), costo)
    lb, la = float(l_before.mean()), float(l_after.mean())
    ganancia = (lb - la) / lb if lb > 0 else 0.0

    razones: list[str] = []
    peor_seg: dict[str, Any] | None = None
    peor_delta = 0.0
    for seg in _regression_segments(holdout, [champion, challenger], patch):
        mask = segments.segment_mask(holdout, seg)
        n = int(mask.sum())
        if n < objective.MIN_SEGMENT_N:
            continue
        sb, sa = float(l_before[mask].mean()), float(l_after[mask].mean())
        delta = (sa - sb) / sb if sb > 0 else (np.inf if sa > 0 else 0.0)
        if peor_seg is None or delta > peor_delta:
            peor_seg, peor_delta = seg, float(delta)
        if delta > objective.EPSILON:
            razones.append(f"segmento [{segments.describe(seg)}] (n={n}) empeora {delta:+.1%} > ε={objective.EPSILON:.0%}")

    if ganancia < objective.DELTA:
        razones.insert(0, f"ganancia {ganancia:+.2%} < δ={objective.DELTA:.0%}")

    aceptado = not razones
    if aceptado:
        razones.append(f"ganancia {ganancia:+.2%} ≥ δ y ningún segmento empeora > ε")
    verdict = Verdict(
        patch_id=patch.patch_id,
        aceptado=aceptado,
        loss_before=lb,
        loss_after=la,
        ganancia=float(ganancia),
        peor_segmento=peor_seg,
        peor_delta=float(peor_delta) if np.isfinite(peor_delta) else 1e9,
        razones=razones,
    )
    return verdict, (challenger if aceptado else None)
