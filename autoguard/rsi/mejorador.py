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
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Optional

from autoguard import llm
from autoguard.config_schema import CotizadorConfig, apply_patch, dump_config
from autoguard.contracts import VARIABLES_PERMITIDAS, ConfigChange, Hypothesis, Patch
from autoguard.segments import ANIO_REFERENCIA, _split, describe

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
) -> list[Patch]:
    """Genera hasta max_patches parches, uno por brazo en `arms` (elegidos por el meta-mejorador).
    LLM con fallback heurístico determinístico (corrige el sesgo medio del segmento)."""
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
            rule_id = f"g{generation}_{j}_{_slug(h.segmento) if h else 'ctl'}"
            n = 1
            while rule_id in existing_ids:
                n += 1
                rule_id = f"g{generation}_{j}_{n}_{_slug(h.segmento) if h else 'ctl'}"
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
        patch = Patch(
            patch_id=patch_id, generation=generation, tipo=arm, nivel=NIVEL[arm],
            hipotesis=_texto_hipotesis(h), segmento=dict(h.segmento) if h else {},
            cambios=prop["cambios"], diff=prop.get("diff", ""),
            razon=prop.get("razon", "") or ("propuesto por LLM" if prop.get("llm") else "heurística determinística"),
        )
        try:
            apply_patch(cfg, patch)
        except Exception as e:  # noqa: BLE001 — cualquier error de validación => inválido
            patch.veredicto = "invalido"
            patch.razon = f"no valida contra el esquema: {str(e).splitlines()[0][:200]}"
        patches.append(patch)
    return patches
