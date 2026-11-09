"""Mejorador: propone parches sobre la config del cotizador. NO puede importar autoguard.evaluator.evaluator.

Un parche por brazo de `arms` (elegidos por el meta-mejorador; puede haber repetidos). Cada brazo toma la
primera hipótesis (en orden de impacto) que aún no usó y para la que sabe construir un cambio:

- ajuste_factor : `set` de un multiplicador existente del factor de la variable del segmento,
                  multiplicado por 1/(1+sesgo) (corrige el sesgo medio).
- cambio_regla  : `add_rule` con multiplicador = 1/(1+sesgo) acotado, restringido al segmento (o ajusta la
                  regla existente con el mismo segmento).
- nueva_variable: `add_factor` sobre una variable permitida que el cotizador aún no usa (p.ej. marca,
                  danos_costo), con el multiplicador corrector en la parte del rango que define el segmento.
- cambio_prompt : reescribe `prompt_estrategia` (no cambia la prima; sirve de control para el bandido).

Si hay llave de LLM (`llm.is_mock()` es False) se pide la propuesta al LLM con el prompt de
`prompts/mejorador.md` (incluye las `lecciones` del meta-mejorador); el fallback es la heurística
determinística. Todo parche se valida con `apply_patch` antes de devolverse; si no valida (o no hay
hipótesis aplicable) se devuelve con veredicto "invalido" para que el evaluador no gaste el holdout.

Modo con datos (T-23, `propose(..., train=df)`): las heurísticas de arriba corrigen el sesgo MEDIO, pero
con pérdida asimétrica el multiplicador óptimo es otro. Si se pasan las filas de train (VEHICLE_COLUMNS +
costo_real), cada multiplicador se calcula con `analista.best_multiplier` (argmin exacto de la pérdida
congelada sobre las filas train del grupo, con encogimiento por n):

- ajuste_factor : reajusta TODOS los bins/categorías del factor de la variable (cada uno con su propia
                  búsqueda 1-D sobre sus filas; paso de descenso por coordenadas). Prefiere hipótesis de
                  una variable.
- cambio_regla  : regla sobre el segmento con su multiplicador óptimo. Prefiere segmentos de 2 variables
                  (interacciones que un factor no puede expresar).
- nueva_variable: factor COMPLETO sobre una variable permitida no usada (todas las marcas; bins de daños).
- cambio_prompt : igual que antes (control).

Además, en modo con datos: cada hipótesis se usa a lo más una vez por generación (dos brazos sobre el mismo
segmento causaban doble corrección) y solo se propone un parche si baja la pérdida en train.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from autoguard import llm
from autoguard.agents.cotizador import quote_df
from autoguard.config_schema import CotizadorConfig, apply_patch, dump_config
from autoguard.contracts import VARIABLES_PERMITIDAS, ConfigChange, Hypothesis, Patch
from autoguard.rsi.analista import BINS as ANALISTA_BINS
from autoguard.rsi.analista import best_multiplier, row_loss, total_loss
from autoguard.segments import ANIO_REFERENCIA, _split, describe, segment_mask

PROMPTS_DIR = Path(__file__).parent / "prompts"

# Rango de corrección por parche: evita saltos bruscos con sesgos ruidosos.
MULT_MIN, MULT_MAX = 0.5, 2.0
# Límites duros del esquema (config_schema.Factor / Regla).
SCHEMA_MIN, SCHEMA_MAX = 0.2, 5.0

NIVEL = {
    "ajuste_factor": "parametros",
    "cambio_prompt": "parametros",
    "cambio_regla": "estructura",
    "nueva_variable": "estructura",
}

# Candidatas para nueva_variable cuando el segmento no trae ninguna variable libre.
NUEVAS_PREFERIDAS = ["marca", "danos_costo", "cobertura_verificacion", "modelo"]
# Bins para un factor numérico NUEVO (modo con datos). Los del analista + cobertura.
NUEVOS_BINS: dict[str, list[float]] = {
    **{k: [float(x) for x in v] for k, v in ANALISTA_BINS.items()},
    "cobertura_verificacion": [0.0, 0.6, 0.8, 0.9],
}
MIN_N_GRUPO = 15  # filas train mínimas para reajustar un bin/categoría (si no, se deja como está)
MIN_CAMBIO = 0.01  # no se emiten cambios de multiplicador menores a 1% (diff legible)
# Variables equivalentes (no tiene sentido agregar `anio` si ya hay factor de `antiguedad`).
_GRUPOS = {"anio": "antiguedad", "antiguedad": "antiguedad"}


# ---------------------------------------------------------------- utilidades
def correction(sesgo: float) -> float:
    """Multiplicador que lleva el sesgo medio relativo a 0: 1/(1+sesgo), acotado."""
    if not math.isfinite(sesgo) or sesgo <= -0.95:
        return MULT_MAX
    return float(min(MULT_MAX, max(MULT_MIN, 1.0 / (1.0 + sesgo))))


def _clamp(m: float) -> float:
    return round(float(min(SCHEMA_MAX, max(SCHEMA_MIN, m))), 4)


def _slug(segmento: dict[str, Any]) -> str:
    s = "_".join(f"{k}{v}" for k, v in segmento.items())
    return re.sub(r"[^A-Za-z0-9_]+", "", s)[:40] or "todos"


def _fmt(x: float) -> str:
    return f"{x:.4g}"


def _numeric_range(segmento: dict[str, Any], var: str) -> Optional[tuple[float, float]]:
    """Rango [lo, hi] que el segmento impone sobre `var` (convierte anio <-> antiguedad)."""
    lo, hi = -math.inf, math.inf
    found = False
    for key, val in segmento.items():
        v, op = _split(key)
        if isinstance(val, str) or isinstance(val, bool):
            continue
        val = float(val)
        if v == var:
            found = True
            if op == ">=":
                lo = max(lo, val)
            elif op == "<=":
                hi = min(hi, val)
            else:
                lo, hi = max(lo, val), min(hi, val)
        elif {v, var} == {"anio", "antiguedad"}:
            found = True
            conv = ANIO_REFERENCIA - val
            if op == ">=":  # anio >= x  <=>  antiguedad <= ref - x (y viceversa)
                hi = min(hi, conv)
            elif op == "<=":
                lo = max(lo, conv)
            else:
                lo, hi = max(lo, conv), min(hi, conv)
    return (lo, hi) if found else None


def _bins_in_range(bins: list[float], lo: float, hi: float) -> list[int]:
    """Índices de bins cuyo intervalo [b_i, b_{i+1}) cae dentro de [lo, hi]; si ninguno cae completo,
    el bin que contiene `lo` (o el primero si lo = -inf)."""
    idx = []
    for i, b in enumerate(bins):
        nxt = bins[i + 1] if i + 1 < len(bins) else math.inf
        if b >= lo and (nxt <= hi + 1 or (math.isinf(hi) and math.isinf(nxt))):
            idx.append(i)
    if idx:
        return idx
    start = lo if math.isfinite(lo) else bins[0]
    cont = [i for i, b in enumerate(bins) if b <= start]
    return [cont[-1] if cont else 0]


def _used_groups(cfg: CotizadorConfig) -> set[str]:
    return {_GRUPOS.get(f.variable, f.variable) for f in cfg.factores.values()}


# ---------------------------------------------------------------- heurísticas por brazo
def _heur_ajuste_factor(cfg: CotizadorConfig, h: Hypothesis) -> Optional[dict[str, Any]]:
    m = correction(h.sesgo_medio)
    for key, val in h.segmento.items():
        var, op = _split(key)
        for name, f in cfg.factores.items():
            if f.categorias is not None and f.variable == var and op == "==" and isinstance(val, str):
                old = f.categorias.get(val, f.default)
                new = _clamp(old * m)
                path = f"factores.{name}.categorias.{val}"
                return {"cambios": [ConfigChange(op="set", path=path, value=new)],
                        "diff": f"{path}: {_fmt(old)} -> {_fmt(new)}"}
            if f.bins is not None and _GRUPOS.get(f.variable, f.variable) == _GRUPOS.get(var, var):
                rng = _numeric_range(h.segmento, f.variable)
                if rng is None:
                    continue
                cambios, diffs = [], []
                for i in _bins_in_range(f.bins, *rng):
                    old = f.valores[i]
                    new = _clamp(old * m)
                    path = f"factores.{name}.valores.{i}"
                    cambios.append(ConfigChange(op="set", path=path, value=new))
                    diffs.append(f"{path}: {_fmt(old)} -> {_fmt(new)}")
                return {"cambios": cambios, "diff": "; ".join(diffs)}
    return None


def _heur_cambio_regla(cfg: CotizadorConfig, h: Hypothesis, rule_id: str) -> Optional[dict[str, Any]]:
    if not h.segmento:
        return None
    m = correction(h.sesgo_medio)
    for i, r in enumerate(cfg.reglas):
        if r.segmento == h.segmento:
            new = _clamp(r.multiplicador * m)
            path = f"reglas.{i}.multiplicador"
            return {"cambios": [ConfigChange(op="set", path=path, value=new)],
                    "diff": f"{path} ({r.id}): {_fmt(r.multiplicador)} -> {_fmt(new)}"}
    regla = {"id": rule_id, "segmento": dict(h.segmento), "multiplicador": _clamp(m),
             "nota": f"corrige sesgo {h.sesgo_medio:+.1%} en {describe(h.segmento)}"}
    return {"cambios": [ConfigChange(op="add_rule", value=regla)],
            "diff": f"+ regla {rule_id}: [{describe(h.segmento)}] × {_fmt(regla['multiplicador'])}"}


def _heur_nueva_variable(cfg: CotizadorConfig, h: Hypothesis) -> Optional[dict[str, Any]]:
    used = _used_groups(cfg)
    m = _clamp(correction(h.sesgo_medio))
    for key, val in h.segmento.items():
        var, op = _split(key)
        if var not in VARIABLES_PERMITIDAS or _GRUPOS.get(var, var) in used or var in cfg.factores:
            continue
        if op == "==" and isinstance(val, str):
            factor = {"variable": var, "categorias": {str(val): m}, "default": 1.0}
            desc = f"{var}={val} × {_fmt(m)}"
        else:
            rng = _numeric_range(h.segmento, var)
            if rng is None:
                continue
            lo, hi = rng
            bins: list[float] = []
            valores: list[float] = []
            if math.isfinite(lo) and lo > 0:
                bins += [0.0, float(lo)]
                valores += [1.0, m]
            else:
                bins += [0.0]
                valores += [m]
            if math.isfinite(hi):
                nxt = float(math.floor(hi) + 1) if float(hi).is_integer() else math.nextafter(hi, math.inf)
                if nxt <= bins[-1]:
                    continue
                bins.append(nxt)
                valores.append(1.0)
            if all(v == 1.0 for v in valores):
                continue
            factor = {"variable": var, "bins": bins, "valores": valores, "default": 1.0}
            desc = f"{var} en [{_fmt(lo)}, {_fmt(hi)}] × {_fmt(m)}"
        return {"cambios": [ConfigChange(op="add_factor", path=var, value=factor)],
                "diff": f"+ factor {var}: {desc}"}
    return None


def _heur_cambio_prompt(cfg: CotizadorConfig, h: Optional[Hypothesis], lecciones: str) -> dict[str, Any]:
    foco = f"Prioriza explicar el ajuste en {describe(h.segmento)} ({h.texto})." if h else ""
    texto = " ".join(x for x in [
        "Explica la prima listando los factores con mayor efecto primero.", foco,
        f"Lecciones: {lecciones.strip()}" if lecciones.strip() else "",
    ] if x)
    return {"cambios": [ConfigChange(op="set", path="prompt_estrategia", value=texto)],
            "diff": f"prompt_estrategia: {len(cfg.prompt_estrategia)} -> {len(texto)} caracteres"}


def _heuristic(arm: str, cfg: CotizadorConfig, h: Optional[Hypothesis], lecciones: str,
               rule_id: str) -> Optional[dict[str, Any]]:
    if arm == "cambio_prompt":
        return _heur_cambio_prompt(cfg, h, lecciones)
    if h is None:
        return None
    if arm == "ajuste_factor":
        return _heur_ajuste_factor(cfg, h)
    if arm == "cambio_regla":
        return _heur_cambio_regla(cfg, h, rule_id)
    if arm == "nueva_variable":
        return _heur_nueva_variable(cfg, h)
    return None


# ---------------------------------------------------------------- modo con datos (T-23)
def _col(df: pd.DataFrame, var: str) -> Optional[pd.Series]:
    if var == "antiguedad" and "antiguedad" not in df.columns and "anio" in df.columns:
        return ANIO_REFERENCIA - df["anio"]
    return df[var] if var in df.columns else None


def _bin_index(col: pd.Series, bins: list[float]) -> np.ndarray:
    x = pd.to_numeric(col, errors="coerce").to_numpy(dtype=float)
    idx = np.searchsorted(np.asarray(bins, dtype=float), x, side="right") - 1
    return np.where(np.isnan(x), -1, idx)


def _vars_of(h: Hypothesis) -> list[str]:
    return list(dict.fromkeys(_split(k)[0] for k in h.segmento))


def _factor_for(cfg: CotizadorConfig, var: str):
    g = _GRUPOS.get(var, var)
    for name, f in cfg.factores.items():
        if _GRUPOS.get(f.variable, f.variable) == g:
            return name, f
    return None


def _refit_factor(name: str, f, train: pd.DataFrame, prima: np.ndarray, costo: np.ndarray):
    """Cambios `set` que reajustan cada bin/categoría del factor con su multiplicador óptimo."""
    col = _col(train, f.variable)
    if col is None:
        return [], []
    cambios, diffs = [], []
    if f.categorias is not None:
        keys = col.astype(str).to_numpy()
        cats = list(f.categorias) + sorted(set(keys) - set(f.categorias))
        groups = [(cat, keys == cat, f.categorias.get(cat, f.default), f"factores.{name}.categorias.{cat}")
                  for cat in cats]
    else:
        idx = _bin_index(col, f.bins)
        groups = [(i, idx == i, f.valores[i], f"factores.{name}.valores.{i}") for i in range(len(f.bins))]
    for _, m, old, path in groups:
        if m.sum() < MIN_N_GRUPO:
            continue
        new = _clamp(old * best_multiplier(prima[m], costo[m]))
        if abs(new / old - 1) < MIN_CAMBIO:
            continue
        cambios.append(ConfigChange(op="set", path=path, value=new))
        diffs.append(f"{path}: {_fmt(old)} -> {_fmt(new)}")
    return cambios, diffs


def _train_loss(cfg: CotizadorConfig, cambios: list[ConfigChange], train: pd.DataFrame,
                costo: np.ndarray) -> Optional[float]:
    try:
        new_cfg = apply_patch(cfg, Patch(patch_id="probe", generation=0, tipo="ajuste_factor",
                                         hipotesis="", cambios=cambios))
    except Exception:  # noqa: BLE001 — no aplica => no es candidato
        return None
    return total_loss(quote_df(train, new_cfg), costo)


def _data_cambio_regla(cfg, h, train, prima, costo, rule_id: str) -> Optional[dict[str, Any]]:
    if not h.segmento:
        return None
    m = segment_mask(train, h.segmento)
    if m.sum() < MIN_N_GRUPO:
        return None
    mult = best_multiplier(prima[m], costo[m])
    if abs(mult - 1) < MIN_CAMBIO:
        return None
    for i, r in enumerate(cfg.reglas):
        if r.segmento == h.segmento:
            new = _clamp(r.multiplicador * mult)
            path = f"reglas.{i}.multiplicador"
            return {"cambios": [ConfigChange(op="set", path=path, value=new)],
                    "diff": f"{path} ({r.id}): {_fmt(r.multiplicador)} -> {_fmt(new)}"}
    regla = {"id": rule_id, "segmento": dict(h.segmento), "multiplicador": _clamp(mult),
             "nota": f"minimiza la pérdida asimétrica en {describe(h.segmento)} (n={int(m.sum())})"}
    return {"cambios": [ConfigChange(op="add_rule", value=regla)],
            "diff": f"+ regla {rule_id}: [{describe(h.segmento)}] × {_fmt(regla['multiplicador'])}"}


def _new_factor(var: str, train: pd.DataFrame, prima: np.ndarray, costo: np.ndarray) -> Optional[dict[str, Any]]:
    """Factor completo sobre `var`: una categoría por valor observado (p.ej. todas las marcas) o los bins de
    NUEVOS_BINS (p.ej. daños), cada uno con su multiplicador óptimo encogido."""
    col = _col(train, var)
    if col is None:
        return None
    if var in NUEVOS_BINS:
        bins = NUEVOS_BINS[var]
        idx = _bin_index(col, bins)
        valores = [_clamp(best_multiplier(prima[idx == i], costo[idx == i]))
                   if (idx == i).sum() >= MIN_N_GRUPO else 1.0 for i in range(len(bins))]
        if all(abs(v - 1) < MIN_CAMBIO for v in valores):
            return None
        return {"variable": var, "bins": bins, "valores": valores, "default": 1.0}
    if pd.api.types.is_numeric_dtype(col):
        return None  # numérica sin bins definidos: no se inventan cortes
    keys = col.astype(str).to_numpy()
    cats = {}
    for cat in sorted(set(keys)):
        m = keys == cat
        if m.sum() >= MIN_N_GRUPO:
            mult = _clamp(best_multiplier(prima[m], costo[m]))
            if abs(mult - 1) >= MIN_CAMBIO:
                cats[cat] = mult
    return {"variable": var, "categorias": cats, "default": 1.0} if cats else None


def _describe_factor(factor: dict[str, Any]) -> str:
    if "categorias" in factor:
        return ", ".join(f"{k}: ×{_fmt(v)}" for k, v in factor["categorias"].items())
    return ", ".join(f"≥{_fmt(b)}: ×{_fmt(v)}" for b, v in zip(factor["bins"], factor["valores"]))


def patch_target(patch: Patch) -> str:
    """Objetivo de un parche (para no re-proponer lo recién rechazado): el factor reajustado, la variable
    nueva o el segmento de la regla. Vacío para el control y parches sin cambios."""
    if not patch.cambios:
        return ""
    ch = patch.cambios[0]
    if patch.tipo == "ajuste_factor" and ch.path.startswith("factores."):
        return "factor:" + ch.path.split(".")[1]
    if patch.tipo == "nueva_variable" and ch.op == "add_factor":
        return "nueva:" + ch.path
    if patch.tipo == "cambio_regla":
        return "regla:" + describe(patch.segmento)
    return ""


# ---- robustez en train: ningún segmento debe empeorar (imita el criterio público de aceptación)
ROBUST_EPS = 0.025  # peor empeoramiento relativo tolerado en un segmento de train (la mitad de ε)
ROBUST_MIN_N = 30
MAX_AMORTIGUAR = 2  # cada amortiguamiento toma la raíz cuadrada del multiplicador del cambio
_NUMERICAS = ("antiguedad", "anio", "kilometraje", "siniestros_previos")


def _check_segments(cfgs: list[CotizadorConfig], train: pd.DataFrame, segmento: dict[str, Any]) -> list[dict]:
    segs: list[dict[str, Any]] = []
    for c in cfgs:
        for f in c.factores.values():
            if f.bins is not None and f.variable in _NUMERICAS:
                for i, lo in enumerate(f.bins):
                    seg: dict[str, Any] = {f"{f.variable}_min": lo}
                    if i + 1 < len(f.bins):
                        seg[f"{f.variable}_max"] = f.bins[i + 1] - 1
                    segs.append(seg)
    for var in ("uso", "zona", "marca"):
        if var in train.columns:
            segs.extend({var: v} for v in sorted(train[var].dropna().astype(str).unique()))
    if segmento:
        segs.append(dict(segmento))
    for c in cfgs:
        segs.extend(dict(r.segmento) for r in c.reglas)
    seen, out = set(), []
    for s in segs:
        k = repr(sorted(s.items()))
        if s and k not in seen:
            seen.add(k)
            out.append(s)
    return out


def _worst_segment(cfg, new_cfg, train, l_before: np.ndarray, l_after: np.ndarray, segmento) -> float:
    worst = 0.0
    for seg in _check_segments([cfg, new_cfg], train, segmento):
        m = segment_mask(train, seg)
        if m.sum() < ROBUST_MIN_N:
            continue
        sb = float(l_before[m].sum())
        if sb > 0:
            worst = max(worst, (float(l_after[m].sum()) - sb) / sb)
    return worst


def _get_path(data: Any, path: str) -> Any:
    for part in path.split("."):
        if isinstance(data, list):
            data = data[int(part)]
        elif isinstance(data, dict):
            data = data.get(part)
        else:
            return None
        if data is None:
            return None
    return data


def _sqrt_step(new: float, old: float) -> float:
    return _clamp(old * math.sqrt(new / old)) if old else new


def _damp(cfg: CotizadorConfig, cambios: list[ConfigChange]) -> list[ConfigChange]:
    """Mitad del paso en escala log: cada multiplicador nuevo m pasa a old·(m/old)^0.5."""
    data = cfg.model_dump(mode="json")
    out = []
    for ch in cambios:
        v = ch.value
        if ch.op == "set" and isinstance(v, (int, float)) and ch.path != "prompt_estrategia":
            old = _get_path(data, ch.path)
            if old is None:  # categoría nueva: parte del default del factor
                old = _get_path(data, ".".join(ch.path.split(".")[:2] + ["default"])) or 1.0
            out.append(ch.model_copy(update={"value": _sqrt_step(float(v), float(old))}))
        elif ch.op == "add_rule" and isinstance(v, dict):
            out.append(ch.model_copy(update={"value": {**v, "multiplicador": _sqrt_step(v["multiplicador"], 1.0)}}))
        elif ch.op == "add_factor" and isinstance(v, dict):
            f = dict(v)
            if "valores" in f:
                f["valores"] = [_sqrt_step(x, 1.0) for x in f["valores"]]
            if "categorias" in f:
                f["categorias"] = {k: _sqrt_step(x, 1.0) for k, x in f["categorias"].items()}
            out.append(ch.model_copy(update={"value": f}))
        else:
            out.append(ch)
    return out


def _diff_from(cfg: CotizadorConfig, cambios: list[ConfigChange]) -> str:
    data = cfg.model_dump(mode="json")
    parts = []
    for ch in cambios:
        if ch.op == "set":
            parts.append(f"{ch.path}: {_get_path(data, ch.path)} -> {ch.value}")
        elif ch.op == "add_rule":
            parts.append(f"+ regla {ch.value['id']}: [{describe(ch.value['segmento'])}] × {_fmt(ch.value['multiplicador'])}")
        elif ch.op == "add_factor":
            parts.append(f"+ factor {ch.path}: {_describe_factor(ch.value)}")
    return "; ".join(parts)


def _robustify(cfg, prop, train, costo, l_before: np.ndarray, segmento) -> Optional[dict[str, Any]]:
    """Exige que el parche baje la pérdida en train y que ningún segmento de train empeore > ROBUST_EPS;
    si algún segmento empeora, amortigua el paso hasta MAX_AMORTIGUAR veces. None si no lo logra."""
    base = float(l_before.sum())
    cambios = list(prop["cambios"])
    for k in range(MAX_AMORTIGUAR + 1):
        try:
            new_cfg = apply_patch(cfg, Patch(patch_id="probe", generation=0, tipo="ajuste_factor",
                                             hipotesis="", cambios=cambios))
        except Exception:  # noqa: BLE001
            return None
        l_after = row_loss(quote_df(train, new_cfg), costo)
        after = float(l_after.sum())
        if not after < base:
            return None
        worst = _worst_segment(cfg, new_cfg, train, l_before, l_after, segmento)
        if worst <= ROBUST_EPS:
            nota = f"train: pérdida {after / base - 1:+.2%}, peor segmento {worst:+.1%}"
            if k:
                nota += f", paso amortiguado {k}x"
            diff = prop.get("diff", "") if k == 0 else _diff_from(cfg, cambios)
            return {**prop, "cambios": cambios, "diff": diff, "razon": prop.get("razon") or nota}
        cambios = _damp(cfg, cambios)
    return None


def _hyp_for_var(hyps: list[Hypothesis], var: str) -> Optional[tuple[int, Hypothesis]]:
    """Primera hipótesis (por impacto) que involucra a `var`, prefiriendo las de una sola variable."""
    g = _GRUPOS.get(var, var)
    match = [(i, h) for i, h in enumerate(hyps) if any(_GRUPOS.get(v, v) == g for v in _vars_of(h))]
    match.sort(key=lambda t: len(_vars_of(t[1])) > 1)
    return match[0] if match else None


def _candidates(arm, cfg, hyps, used_hyps, used_targets, train, prima, costo, base, generation, j, existing_ids):
    """Candidatos de un brazo como (target, índice_hipótesis, hipótesis, propuesta, texto, segmento),
    los que más bajan la pérdida en train primero."""
    out = []
    if arm == "ajuste_factor":  # Gauss-Southwell: el factor cuyo reajuste completo más baja la pérdida
        for name, f in cfg.factores.items():
            target = f"factor:{name}"
            if target in used_targets:
                continue
            cambios, diffs = _refit_factor(name, f, train, prima, costo)
            after = _train_loss(cfg, cambios, train, costo) if cambios else None
            if after is None or not after < base:
                continue
            hit = _hyp_for_var(hyps, f.variable)
            i, h = hit if hit else (-1, None)
            text = h.texto if h else f"Reajuste del factor {name} (pérdida train {after / base - 1:+.2%})."
            out.append((after, target, i, h, {"cambios": cambios, "diff": "; ".join(diffs)}, text,
                        dict(h.segmento) if h else {}))
    elif arm == "nueva_variable":  # la variable permitida no usada que más baja la pérdida
        used = _used_groups(cfg)
        for var in VARIABLES_PERMITIDAS:
            target = f"nueva:{var}"
            if target in used_targets or _GRUPOS.get(var, var) in used or var in cfg.factores:
                continue
            factor = _new_factor(var, train, prima, costo)
            if factor is None:
                continue
            cambios = [ConfigChange(op="add_factor", path=var, value=factor)]
            after = _train_loss(cfg, cambios, train, costo)
            if after is None or not after < base:
                continue
            hit = _hyp_for_var(hyps, var)
            i, h = hit if hit else (-1, None)
            text = h.texto if h else f"La variable {var} explica parte del error (pérdida train {after / base - 1:+.2%})."
            out.append((after, target, i, h, {"cambios": cambios, "diff": f"+ factor {var}: {_describe_factor(factor)}"},
                        text, dict(h.segmento) if h else {}))
    elif arm == "cambio_regla":  # hipótesis del analista; interacciones (2 variables) primero
        for i, h in enumerate(hyps):
            target = "regla:" + describe(h.segmento)
            if i in used_hyps or target in used_targets:
                continue
            prop = _data_cambio_regla(cfg, h, train, prima, costo, _rule_id(generation, j, h, existing_ids))
            if prop is None:
                continue
            after = _train_loss(cfg, prop["cambios"], train, costo)
            if after is None or not after < base:
                continue
            pref = 0 if len(_vars_of(h)) >= 2 else 1
            out.append(((pref, i), target, i, h, prop, h.texto, dict(h.segmento)))
    out.sort(key=lambda t: t[0])
    return [t[1:] for t in out]


def _propose_data(cfg, hypotheses, arms, generation, lecciones, max_patches, train, evitar,
                  sustitutos=None) -> list[Patch]:
    train = train.reset_index(drop=True)
    costo = train["costo_real"].to_numpy(dtype=float)
    prima = quote_df(train, cfg)  # prima del campeón vigente (no la histórica)
    l_before = row_loss(prima, costo)
    base = float(l_before.sum())
    hyps = sorted(hypotheses, key=lambda h: -h.impacto)
    existing_ids = {r.id for r in cfg.reglas}
    use_llm = not llm.is_mock()
    used_hyps: set[int] = set()
    used_targets: set[str] = set(evitar)
    patches: list[Patch] = []

    agotados: set[str] = set()  # brazos que ya no encontraron cambio válido en esta generación

    def _slot_arms(arm):
        # El brazo elegido primero; si se agota, los sustitutos (sin repetir agotados).
        yield arm
        for s in sustitutos or []:
            if s != arm and s in NIVEL and s != "cambio_prompt":
                yield s

    for j, arm in enumerate(arms[:max_patches]):
        patch_id = f"g{generation}-{j}-{arm}"
        if arm not in NIVEL:
            patches.append(Patch(patch_id=patch_id, generation=generation, tipo="cambio_prompt",
                                 hipotesis="", cambios=[], veredicto="invalido",
                                 razon=f"brazo desconocido: {arm}"))
            continue
        if sustitutos is not None and arm != "cambio_prompt":
            for k_try, cand_arm in enumerate(_slot_arms(arm)):
                if cand_arm in agotados:
                    continue
                pid = patch_id if k_try == 0 else f"g{generation}-{j}s{k_try}-{cand_arm}"
                patch = _data_slot(cand_arm, pid, cfg, hyps, used_hyps, used_targets, train, prima, costo,
                                   base, generation, j, existing_ids, l_before, lecciones, use_llm)
                patches.append(patch)
                if patch.veredicto == "invalido":
                    agotados.add(cand_arm)
                    continue
                break
            continue
        if arm == "cambio_prompt":
            h = hyps[0] if hyps else None
            heur = _heur_cambio_prompt(cfg, h, lecciones)
            prop = _llm_proposal(arm, cfg, h, lecciones, "ctl", heur) if use_llm else heur
            patches.append(_make_patch(cfg, patch_id, generation, arm, h, prop or heur))
            continue
        patches.append(_data_slot(arm, patch_id, cfg, hyps, used_hyps, used_targets, train, prima, costo,
                                  base, generation, j, existing_ids, l_before, lecciones, use_llm))
    return patches


def _data_slot(arm, patch_id, cfg, hyps, used_hyps, used_targets, train, prima, costo, base, generation, j,
               existing_ids, l_before, lecciones, use_llm) -> Patch:
    """Un slot del modo con datos: el mejor candidato robusto del brazo, o un parche inválido."""
    chosen = None
    for target, i, h, prop, text, seg in _candidates(arm, cfg, hyps, used_hyps, used_targets, train,
                                                     prima, costo, base, generation, j, existing_ids):
        if use_llm:
            rid = _rule_id(generation, j, h, existing_ids)
            prop = _llm_proposal(arm, cfg, h, lecciones, rid, prop) or prop
        robust = _robustify(cfg, prop, train, costo, l_before, seg)
        if robust is not None:
            chosen = (target, i, h, robust, text, seg)
            break
    if chosen is None:
        return Patch(patch_id=patch_id, generation=generation, tipo=arm, nivel=NIVEL[arm],
                     hipotesis=_texto_hipotesis(hyps[0] if hyps else None), cambios=[],
                     veredicto="invalido",
                     razon=f"sin cambio para {arm} que mejore train sin empeorar segmentos")
    target, i, h, prop, text, seg = chosen
    used_targets.add(target)
    if i >= 0:
        used_hyps.add(i)
    return _make_patch(cfg, patch_id, generation, arm, h, prop, hipotesis=text, segmento=seg)


# ---------------------------------------------------------------- LLM
_OPS_POR_BRAZO = {
    "ajuste_factor": {"set"},
    "cambio_regla": {"add_rule", "remove_rule", "set"},
    "nueva_variable": {"add_factor"},
    "cambio_prompt": {"set"},
}

LLM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["cambios"],
    "properties": {
        "cambios": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["op"],
                "properties": {"op": {"type": "string"}, "path": {"type": "string"}, "value": {}},
            },
        },
        "diff": {"type": "string"},
        "razon": {"type": "string"},
    },
}


def _load_prompt(name: str) -> str:
    try:
        return (PROMPTS_DIR / name).read_text(encoding="utf-8")
    except OSError:
        return ""


def _llm_proposal(arm: str, cfg: CotizadorConfig, h: Optional[Hypothesis], lecciones: str,
                  rule_id: str, heur: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Pide el parche al LLM; en modo mock o ante error devuelve la heurística (vía fallback)."""
    def fallback() -> dict[str, Any]:
        if heur is None:
            return {"cambios": [], "diff": "", "_heuristica": True}
        return {"cambios": [c.model_dump(mode="json") for c in heur["cambios"]], "diff": heur["diff"],
                "_heuristica": True}

    system = _load_prompt("mejorador.md").replace("{lecciones}", lecciones.strip() or "(sin lecciones aún)")
    user = json.dumps({
        "brazo": arm,
        "operaciones_permitidas": sorted(_OPS_POR_BRAZO[arm]),
        "id_regla_sugerido": rule_id,
        "variables_permitidas": VARIABLES_PERMITIDAS,
        "hipotesis": h.model_dump(mode="json") if h else None,
        "multiplicador_corrector_sugerido": correction(h.sesgo_medio) if h else 1.0,
        "config_actual_yaml": dump_config(cfg),
    }, ensure_ascii=False, indent=1)
    out = llm.complete_json(system, user, schema=LLM_SCHEMA, fallback=fallback, max_tokens=1500)
    if not isinstance(out, dict) or not out.get("cambios"):
        return heur
    try:
        cambios = [ConfigChange.model_validate(c) for c in out["cambios"]]
    except Exception:  # noqa: BLE001 — respuesta malformada del LLM
        return heur
    if any(c.op not in _OPS_POR_BRAZO[arm] for c in cambios):
        return heur
    if arm == "cambio_prompt" and any(c.path != "prompt_estrategia" for c in cambios):
        return heur
    return {"cambios": cambios, "diff": str(out.get("diff", "")), "razon": str(out.get("razon", "")),
            "llm": not out.get("_heuristica", False)}


# ---------------------------------------------------------------- API
def _texto_hipotesis(h: Optional[Hypothesis]) -> str:
    if h is None:
        return "sin hipótesis: control"
    return h.texto or f"sesgo {h.sesgo_medio:+.1%} en {describe(h.segmento)} (n={h.n})"


def propose(
    cfg: CotizadorConfig,
    hypotheses: list[Hypothesis],
    arms: list[str],
    generation: int,
    lecciones: str = "",
    max_patches: int = 3,
    train: Optional[pd.DataFrame] = None,
    evitar: Optional[set[str]] = None,
    sustitutos: Optional[list[str]] = None,
) -> list[Patch]:
    """Genera hasta max_patches parches, uno por brazo en `arms` (elegidos por el meta-mejorador).
    LLM con fallback heurístico determinístico.

    Sin `train`: la heurística corrige el sesgo medio del segmento (comportamiento original de T-08).
    Con `train` (filas train con VEHICLE_COLUMNS + costo_real): modo con datos (ver docstring del módulo);
    `evitar` = objetivos (`patch_target`) rechazados hace poco, que no se re-proponen.
    `sustitutos` (solo modo con datos) = brazos, en orden de preferencia, que ocupan el slot de un brazo
    que no encuentra cambio válido (el intento fallido queda como parche inválido para el bandido)."""
    if train is not None and len(train) > 0 and "costo_real" in train.columns:
        return _propose_data(cfg, hypotheses, arms, generation, lecciones, max_patches, train, evitar or set(),
                             sustitutos)
    hyps = sorted(hypotheses, key=lambda h: -h.impacto)
    existing_ids = {r.id for r in cfg.reglas}
    used: dict[str, set[int]] = {}
    patches: list[Patch] = []
    use_llm = not llm.is_mock()

    for j, arm in enumerate(arms[:max_patches]):
        patch_id = f"g{generation}-{j}-{arm}"
        if arm not in NIVEL:
            patches.append(Patch(patch_id=patch_id, generation=generation, tipo="cambio_prompt",
                                 hipotesis="", cambios=[], veredicto="invalido",
                                 razon=f"brazo desconocido: {arm}"))
            continue
        tried = used.setdefault(arm, set())
        chosen: Optional[tuple[int, Optional[Hypothesis], dict[str, Any]]] = None
        candidates: list[tuple[int, Optional[Hypothesis]]] = [(i, h) for i, h in enumerate(hyps) if i not in tried]
        if arm == "cambio_prompt" or not candidates:
            candidates = candidates or [(-1, None)]
        for i, h in candidates:
            rule_id = _rule_id(generation, j, h, existing_ids)
            heur = _heuristic(arm, cfg, h, lecciones, rule_id)
            prop = _llm_proposal(arm, cfg, h, lecciones, rule_id, heur) if use_llm else heur
            if prop is not None and prop.get("cambios"):
                chosen = (i, h, prop)
                break
        if chosen is None:
            patches.append(Patch(patch_id=patch_id, generation=generation, tipo=arm, nivel=NIVEL[arm],
                                 hipotesis=_texto_hipotesis(hyps[0] if hyps else None), cambios=[],
                                 veredicto="invalido", razon=f"sin hipótesis aplicable para {arm}"))
            continue
        i, h, prop = chosen
        if i >= 0:
            tried.add(i)
        patches.append(_make_patch(cfg, patch_id, generation, arm, h, prop))
    return patches


def _rule_id(generation: int, j: int, h: Optional[Hypothesis], existing_ids: set[str]) -> str:
    slug = _slug(h.segmento) if h else "ctl"
    rule_id = f"g{generation}_{j}_{slug}"
    n = 1
    while rule_id in existing_ids:
        n += 1
        rule_id = f"g{generation}_{j}_{n}_{slug}"
    return rule_id


def _make_patch(cfg: CotizadorConfig, patch_id: str, generation: int, arm: str, h: Optional[Hypothesis],
                prop: dict[str, Any], hipotesis: Optional[str] = None,
                segmento: Optional[dict[str, Any]] = None) -> Patch:
    patch = Patch(
        patch_id=patch_id, generation=generation, tipo=arm, nivel=NIVEL[arm],
        hipotesis=hipotesis or _texto_hipotesis(h),
        segmento=dict(segmento if segmento is not None else (h.segmento if h else {})),
        cambios=prop["cambios"], diff=prop.get("diff", ""),
        razon=prop.get("razon", "") or ("propuesto por LLM" if prop.get("llm") else "heurística determinística"),
    )
    try:
        apply_patch(cfg, patch)
    except Exception as e:  # noqa: BLE001 — cualquier error de validación => inválido
        patch.veredicto = "invalido"
        patch.razon = f"no valida contra el esquema: {str(e).splitlines()[0][:200]}"
    return patch
