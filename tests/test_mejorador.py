"""Tests del mejorador (fallback heurístico, sin red). Datos SIMULADOS.

El cotizador real (T-04) y el analista (T-07) pueden ser stubs aún: usamos un `quote_df` local que sigue la
semántica de config_schema (factor = valor del último bin con límite ≤ x; categorías con default; reglas por
segment_mask) y hipótesis construidas como lo haría el analista (sesgo medio de error_rel por segmento).
"""
from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from autoguard import llm
from autoguard.config_schema import CotizadorConfig, apply_patch, load_config
from autoguard.contracts import ARMS, Hypothesis
from autoguard.rsi import mejorador
from autoguard.rsi.mejorador import correction, propose
from autoguard.segments import ANIO_REFERENCIA, segment_mask

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _mock_llm(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture()
def cfg() -> CotizadorConfig:
    return load_config(ROOT / "configs/agents/cotizador.yaml")


# ---------------------------------------------------------------- dobles locales
def local_quote_df(df: pd.DataFrame, cfg: CotizadorConfig) -> np.ndarray:
    prima = np.full(len(df), cfg.base, dtype=float)
    for f in cfg.factores.values():
        if f.variable == "antiguedad" and "antiguedad" not in df:
            col = ANIO_REFERENCIA - df["anio"]
        elif f.variable in df:
            col = df[f.variable]
        else:
            prima *= f.default
            continue
        if f.categorias is not None:
            prima *= col.map(lambda v: f.categorias.get(v, f.default)).to_numpy(dtype=float)
        else:
            x = col.to_numpy(dtype=float)
            idx = np.searchsorted(np.asarray(f.bins), x, side="right") - 1
            vals = np.asarray(f.valores)
            prima *= np.where(idx >= 0, vals[np.clip(idx, 0, None)], f.default)
    for r in cfg.reglas:
        prima *= np.where(segment_mask(df, r.segmento), r.multiplicador, 1.0)
    return prima


def synthetic_data(cfg: CotizadorConfig, n: int = 6000, seed: int = 7) -> pd.DataFrame:
    """Riesgo oculto con sesgos plantados respecto a la config base."""
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "vehicle_id": [f"v{i}" for i in range(n)],
        "marca": rng.choice(["Nissan", "VW", "Chevrolet", "Seat", "BMW"], n),
        "modelo": "X",
        "anio": rng.integers(1988, 2026, n),
        "kilometraje": rng.integers(0, 300_000, n),
        "siniestros_previos": rng.choice([0, 1, 2], n, p=[0.6, 0.3, 0.1]),
        "uso": rng.choice(["particular", "app_transporte", "comercial"], n, p=[0.6, 0.25, 0.15]),
        "zona": rng.choice(["CDMX", "EDOMEX", "JAL", "NL", "PUE", "OTRA"], n),
        "danos_costo": rng.choice([0.0, 30_000.0], n, p=[0.8, 0.2]),
        "cobertura_verificacion": 1.0,
    })
    prima = local_quote_df(df, cfg)
    real = np.ones(n)
    real *= np.where(df["uso"] == "app_transporte", 1.45 / 1.15, 1.0)  # factor mal calibrado
    real *= np.where((ANIO_REFERENCIA - df["anio"] >= 30) & (df["siniestros_previos"] == 1), 0.7, 1.0)  # interacción
    real *= np.where(df["marca"] == "BMW", 1.5, 1.0)  # variable no usada
    real *= np.where(df["danos_costo"] >= 20_000, 1.3, 1.0)
    df["prima"] = prima
    df["costo_real"] = prima * real * rng.lognormal(0, 0.05, n)
    return df


def segment_bias(df: pd.DataFrame, prima: np.ndarray, segmento: dict) -> float:
    m = segment_mask(df, segmento)
    return float(np.mean((prima[m] - df["costo_real"].to_numpy()[m]) / df["costo_real"].to_numpy()[m]))


def hypothesis_for(df: pd.DataFrame, segmento: dict, impacto: float = 1.0) -> Hypothesis:
    m = segment_mask(df, segmento)
    return Hypothesis(segmento=segmento, n=int(m.sum()), sesgo_medio=segment_bias(df, df["prima"].to_numpy(), segmento),
                      p_value=0.001, impacto=impacto, texto=f"sesgo en {segmento}")


PLANTED = [
    {"uso": "app_transporte"},
    {"antiguedad_min": 30, "siniestros_previos": 1},
    {"marca": "BMW"},
    {"danos_costo_min": 20_000},
]


# ---------------------------------------------------------------- aceptación
@pytest.mark.parametrize("arm", ["ajuste_factor", "cambio_regla", "nueva_variable"])
@pytest.mark.parametrize("segmento", PLANTED)
def test_fallback_patches_valid_and_reduce_segment_bias(cfg, arm, segmento):
    df = synthetic_data(cfg)
    h = hypothesis_for(df, segmento)
    assert abs(h.sesgo_medio) > 0.1
    patches = propose(cfg, [h], [arm], generation=1)
    assert len(patches) == 1
    p = patches[0]
    applicable = not (
        (arm == "ajuste_factor" and segmento in ({"marca": "BMW"}, {"danos_costo_min": 20_000}))
        or (arm == "nueva_variable" and segmento in ({"uso": "app_transporte"},
                                                     {"antiguedad_min": 30, "siniestros_previos": 1}))
    )
    if not applicable:
        # sin cambio posible para ese brazo/hipótesis: se marca inválido, no se inventa
        assert p.veredicto == "invalido" and p.cambios == []
        return
    assert p.veredicto is None, p.razon
    assert p.tipo == arm and p.cambios and p.diff
    new_cfg = apply_patch(cfg, p)
    after = segment_bias(df, local_quote_df(df, new_cfg), segmento)
    assert abs(after) < abs(h.sesgo_medio) * 0.7, (arm, segmento, h.sesgo_medio, after)


def test_cambio_regla_is_restricted_to_segment(cfg):
    df = synthetic_data(cfg)
    seg = {"antiguedad_min": 30, "siniestros_previos": 1}
    p = propose(cfg, [hypothesis_for(df, seg)], ["cambio_regla"], generation=3)[0]
    new_cfg = apply_patch(cfg, p)
    m = segment_mask(df, seg)
    before, after = local_quote_df(df, cfg), local_quote_df(df, new_cfg)
    np.testing.assert_allclose(before[~m], after[~m])
    assert new_cfg.reglas[-1].segmento == seg
    assert new_cfg.reglas[-1].multiplicador == pytest.approx(correction(hypothesis_for(df, seg).sesgo_medio), abs=1e-3)


def test_cambio_prompt_does_not_change_prices_and_uses_lecciones(cfg):
    df = synthetic_data(cfg, n=500)
    p = propose(cfg, [hypothesis_for(df, {"uso": "app_transporte"})], ["cambio_prompt"], 1,
                lecciones="las reglas por segmento funcionan")[0]
    new_cfg = apply_patch(cfg, p)
    assert "las reglas por segmento funcionan" in new_cfg.prompt_estrategia
    np.testing.assert_allclose(local_quote_df(df, cfg), local_quote_df(df, new_cfg))
    # sin hipótesis también produce un control válido
    p2 = propose(cfg, [], ["cambio_prompt"], 1)[0]
    assert p2.veredicto is None and p2.cambios


def test_one_patch_per_arm_repeated_arms_use_distinct_hypotheses(cfg):
    df = synthetic_data(cfg)
    hyps = [hypothesis_for(df, s, impacto=10 - i) for i, s in enumerate(PLANTED)]
    patches = propose(cfg, hyps, ["cambio_regla", "cambio_regla", "cambio_regla", "ajuste_factor"], 2,
                      max_patches=3)
    assert len(patches) == 3
    assert [p.segmento for p in patches] == PLANTED[:3]  # en orden de impacto, sin repetir
    assert len({p.patch_id for p in patches}) == 3
    ids = [c.value["id"] for p in patches for c in p.cambios]
    assert len(set(ids)) == 3
    for p in patches:
        apply_patch(cfg, p)


def test_nueva_variable_skips_to_hypothesis_with_unused_variable(cfg):
    df = synthetic_data(cfg)
    hyps = [hypothesis_for(df, {"uso": "app_transporte"}, 5), hypothesis_for(df, {"marca": "BMW"}, 1)]
    p = propose(cfg, hyps, ["nueva_variable"], 1)[0]
    assert p.veredicto is None and p.segmento == {"marca": "BMW"}
    assert p.cambios[0].op == "add_factor" and p.cambios[0].path == "marca"


def test_deterministic(cfg):
    df = synthetic_data(cfg)
    hyps = [hypothesis_for(df, s, impacto=i) for i, s in enumerate(PLANTED)]
    a = propose(cfg, hyps, ARMS, 4, max_patches=4)
    b = propose(cfg, hyps, ARMS, 4, max_patches=4)
    assert [p.model_dump(exclude={"razon"}) for p in a] == [p.model_dump(exclude={"razon"}) for p in b]
    assert [p.tipo for p in a] == ARMS


def test_existing_rule_same_segment_is_adjusted_not_duplicated(cfg):
    df = synthetic_data(cfg)
    seg = {"uso": "app_transporte"}
    p1 = propose(cfg, [hypothesis_for(df, seg)], ["cambio_regla"], 1)[0]
    cfg2 = apply_patch(cfg, p1)
    df["prima"] = local_quote_df(df, cfg2)
    df["costo_real"] = df["costo_real"] * 1.1  # el segmento sigue subcotizado
    p2 = propose(cfg2, [hypothesis_for(df, seg)], ["cambio_regla"], 2)[0]
    assert p2.cambios[0].op == "set" and p2.cambios[0].path == "reglas.0.multiplicador"
    assert len(apply_patch(cfg2, p2).reglas) == 1


def test_llm_invalid_patch_is_marked_invalido(cfg, monkeypatch):
    """Con LLM 'real' (cliente falso) que propone algo fuera del esquema -> invalido; nunca hay red."""
    monkeypatch.setattr(llm, "is_mock", lambda: False)
    monkeypatch.setattr(llm, "complete_json", lambda *a, **k: {
        "cambios": [{"op": "set", "path": "factores.uso.categorias.app_transporte", "value": 9.0}],
        "diff": "x", "razon": "llm"})
    df = synthetic_data(cfg, n=500)
    p = propose(cfg, [hypothesis_for(df, {"uso": "app_transporte"})], ["ajuste_factor"], 1)[0]
    assert p.veredicto == "invalido" and "esquema" in p.razon


def test_llm_valid_patch_used_and_wrong_ops_fall_back(cfg, monkeypatch):
    calls = []

    def fake(system, user, **k):
        calls.append((system, user))
        if '"brazo": "ajuste_factor"' in user:
            return {"cambios": [{"op": "set", "path": "factores.uso.categorias.app_transporte", "value": 1.4}],
                    "diff": "1.15 -> 1.4", "razon": "llm"}
        return {"cambios": [{"op": "add_factor", "path": "genero", "value": {}}]}  # op no permitida p/ regla

    monkeypatch.setattr(llm, "is_mock", lambda: False)
    monkeypatch.setattr(llm, "complete_json", fake)
    df = synthetic_data(cfg, n=500)
    h = hypothesis_for(df, {"uso": "app_transporte"})
    a, b = propose(cfg, [h], ["ajuste_factor", "cambio_regla"], 1, lecciones="LECCION-X")
    assert a.veredicto is None and a.cambios[0].value == 1.4 and a.razon == "llm"
    assert b.veredicto is None and b.cambios[0].op == "add_rule"  # fallback heurístico
    assert all("LECCION-X" in s for s, _ in calls)


def test_correction_bounds():
    assert correction(0.0) == 1.0
    assert correction(-0.2) == pytest.approx(1.25)
    assert correction(10.0) == 0.5 and correction(-0.99) == 2.0 and correction(float("nan")) == 2.0


def test_mejorador_does_not_import_evaluator():
    tree = ast.parse(Path(mejorador.__file__).read_text(encoding="utf-8"))
    mods = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)] + \
           [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    assert not any(m and m.startswith("autoguard.evaluator") for m in mods)


def test_sustitutos_fill_slots_of_exhausted_arm(cfg):
    df = synthetic_data(cfg, n=3000)
    hyps = [hypothesis_for(df, {"uso": "app_transporte"})]
    evitar = {f"nueva:{v}" for v in mejorador.VARIABLES_PERMITIDAS}
    sin = propose(cfg, hyps, ["nueva_variable"] * 3, 1, train=df, evitar=evitar)
    assert all(p.veredicto == "invalido" for p in sin)
    con = propose(cfg, hyps, ["nueva_variable"] * 3, 1, train=df, evitar=set(evitar),
                  sustitutos=["ajuste_factor", "cambio_regla"])
    invalid = [p for p in con if p.veredicto == "invalido"]
    valid = [p for p in con if p.veredicto != "invalido"]
    assert [p.tipo for p in invalid] == ["nueva_variable"]  # el brazo agotado se registra una sola vez
    assert len(valid) == 3 and len({p.patch_id for p in con}) == len(con)
