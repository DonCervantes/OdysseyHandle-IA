"""Tests del meta-mejorador (T-11). Sin red: LLM en modo mock."""
from __future__ import annotations

import numpy as np
import pytest

from autoguard import llm
from autoguard.contracts import ARMS, MetaStrategy, Patch
from autoguard.rsi import meta as meta_mod
from autoguard.rsi.meta import MetaImprover, patch_gain, patch_reward


@pytest.fixture(autouse=True)
def _mock_llm(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def mk_patch(i: int, gen: int, tipo: str, ganancia: float, veredicto=None) -> Patch:
    if veredicto is None:
        veredicto = "aceptado" if ganancia >= 0.01 else "rechazado"
    return Patch(
        patch_id=f"p{gen}-{i}",
        generation=gen,
        tipo=tipo,
        hipotesis=f"hipótesis {i}",
        segmento={"uso": "app_transporte"},
        cambios=[],
        veredicto=veredicto,
        metrics_before={"loss": 100.0},
        metrics_after={"loss": 100.0 * (1 - ganancia)},
        razon="" if veredicto == "aceptado" else "ganancia < delta",
    )


def run_bandit(seed: int, gens: int = 30, k: int = 3):
    probs = {"ajuste_factor": 0.2, "nueva_variable": 0.75, "cambio_regla": 0.25, "cambio_prompt": 0.02}
    env = np.random.default_rng(seed + 1000)
    m = MetaImprover(ARMS, seed=seed)
    chosen: list[str] = []
    for g in range(1, gens + 1):
        arms = m.choose_arms(k)
        chosen.extend(arms)
        patches = [
            mk_patch(i, g, a, 0.05 if env.random() < probs[a] else -0.01) for i, a in enumerate(arms)
        ]
        m.update(patches)
    return m, chosen


def test_gain_and_reward():
    p = mk_patch(0, 1, "ajuste_factor", 0.05)
    assert patch_gain(p) == pytest.approx(0.05)
    assert patch_reward(p) == 1
    assert patch_reward(mk_patch(0, 1, "ajuste_factor", 0.05, veredicto="rechazado")) == 0
    assert patch_reward(mk_patch(0, 1, "ajuste_factor", 0.05, veredicto="invalido")) == 0
    assert patch_reward(mk_patch(0, 1, "ajuste_factor", -0.02)) == 0
    p2 = Patch(patch_id="x", generation=1, tipo="cambio_regla", hipotesis="", cambios=[],
               metrics_after={"ganancia": 0.03})
    assert patch_gain(p2) == pytest.approx(0.03) and patch_reward(p2) == 1
    p3 = Patch(patch_id="y", generation=1, tipo="cambio_regla", hipotesis="", cambios=[])
    assert patch_gain(p3) == 0.0 and patch_reward(p3) == 0


def test_choose_arms_basic_and_reproducible():
    a, b = MetaImprover(ARMS, seed=7), MetaImprover(ARMS, seed=7)
    xs = a.choose_arms(50)
    assert xs == b.choose_arms(50)
    assert len(xs) == 50 and set(xs) <= set(ARMS)
    assert a.choose_arms(0) == []
    with pytest.raises(ValueError):
        MetaImprover([], seed=0)


def test_best_arm_chosen_majority_after_30_generations():
    for seed in (0, 1, 2, 42):
        m, chosen = run_bandit(seed)
        frac = chosen.count("nueva_variable") / len(chosen)
        assert frac > 0.6, (seed, frac)
        # Tras 30 generaciones el muestreo sigue prefiriéndolo claramente.
        assert m.choose_arms(200).count("nueva_variable") / 200 > 0.6
        pm = m.posterior_mean()
        assert max(pm, key=pm.get) == "nueva_variable"


def test_update_posteriors_and_strategy_fields():
    m = MetaImprover(ARMS, seed=0)
    s = m.update([
        mk_patch(0, 1, "ajuste_factor", 0.05),
        mk_patch(1, 1, "cambio_regla", -0.02),
        mk_patch(2, 1, "cambio_prompt", 0.0),
    ])
    assert isinstance(s, MetaStrategy)
    assert s.generation == 1
    assert s.arms["ajuste_factor"] == (2.0, 1.0)
    assert s.arms["cambio_regla"] == (1.0, 2.0)
    assert s.arms["cambio_prompt"] == (1.0, 2.0)
    assert s.arms["nueva_variable"] == (1.0, 1.0)
    assert s.tasa_aceptacion == pytest.approx(1 / 3)
    assert s.ganancia_media == pytest.approx(0.05 / 3)
    assert s.lecciones and "ajuste_factor" in s.lecciones
    assert m.strategy() == s
    MetaStrategy.model_validate(s.model_dump(mode="json"))


def test_empty_update_and_unknown_arm():
    m = MetaImprover(["ajuste_factor"], seed=0)
    s = m.update([])
    assert s.generation == 1 and s.tasa_aceptacion == 0.0 and s.ganancia_media == 0.0
    s = m.update([mk_patch(0, 2, "cambio_regla", 0.04)])
    assert s.arms["cambio_regla"] == (2.0, 1.0)
    assert "cambio_regla" in m.arms and "cambio_regla" in m.choose_arms(100)


def test_strategy_reverted_when_mean_gain_drops():
    m = MetaImprover(ARMS, seed=0)
    m.update([mk_patch(0, 1, "ajuste_factor", 0.05)])  # gen 1: ganancia 0.05
    l1 = m.lecciones  # estrategia nueva propuesta tras gen 1
    assert l1 and not m.last_reverted

    # gen 2 usa l1 y la ganancia sube -> se conserva y se propone l2
    m.update([mk_patch(0, 2, "ajuste_factor", 0.08)])
    assert not m.last_reverted
    l2 = m.lecciones
    assert l2 != l1

    # gen 3 usa l2 y la ganancia cae -> se revierte a l1
    s = m.update([mk_patch(0, 3, "ajuste_factor", -0.01)])
    assert m.last_reverted and m.reversions == 1
    assert s.lecciones == l1

    # gen 4: no había cambio pendiente -> no revierte aunque la ganancia sea baja; propone nueva
    m.update([mk_patch(0, 4, "ajuste_factor", -0.01)])
    assert not m.last_reverted
    assert m.lecciones != l1
    assert [h.generation for h in m.history] == [1, 2, 3, 4]


def test_no_revert_when_gain_holds():
    m = MetaImprover(ARMS, seed=0)
    for g, gain in enumerate([0.02, 0.03, 0.03, 0.05], start=1):
        m.update([mk_patch(0, g, "cambio_regla", gain)])
        assert not m.last_reverted
    assert m.reversions == 0


def test_llm_lecciones_used_and_errors_fall_back(monkeypatch):
    calls = []

    def fake(system, user, **kw):
        calls.append(user)
        return {"lecciones": "LECCIÓN LLM"}

    monkeypatch.setattr(llm, "complete_json", fake)
    m = MetaImprover(ARMS, seed=0)
    m.update([mk_patch(0, 1, "ajuste_factor", 0.05)])
    assert m.lecciones == "LECCIÓN LLM"
    assert "ajuste_factor" in calls[0]

    def boom(*a, **kw):
        raise RuntimeError("red caída")

    monkeypatch.setattr(llm, "complete_json", boom)
    m.update([mk_patch(0, 2, "ajuste_factor", 0.06)])
    assert m.lecciones and m.lecciones != "LECCIÓN LLM"
    assert len(m.lecciones) <= meta_mod.MAX_LECCIONES_CHARS


def test_reproducible_with_seed():
    m1, c1 = run_bandit(3)
    m2, c2 = run_bandit(3)
    assert c1 == c2
    assert [h.model_dump() for h in m1.history] == [h.model_dump() for h in m2.history]


def test_meta_does_not_import_evaluator():
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(meta_mod))
    mods = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    mods += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    assert not any(m and m.startswith("autoguard.evaluator") for m in mods)


def test_plan_arms_caps_control_and_returns_substitutes():
    m = MetaImprover(ARMS, seed=3)
    m.alpha["cambio_prompt"] = 50.0  # el control domina los sorteos
    for _ in range(20):
        arms, subs = m.plan_arms(3)
        assert len(arms) == 3 and arms.count("cambio_prompt") <= 1
    assert "cambio_prompt" not in subs and set(subs) == set(ARMS) - {"cambio_prompt"}
