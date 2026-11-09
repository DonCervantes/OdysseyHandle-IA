"""Tests unitarios de la lógica de T-23 orientada a la pérdida asimétrica (analista, mejorador en modo con
datos, robustez y utilidades del loop). Datos SIMULADOS construidos en el test; sin red, LLM en modo mock.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from autoguard import segments
from autoguard.agents.cotizador import quote_df
from autoguard.config_schema import CotizadorConfig, apply_patch, load_config
from autoguard.contracts import ConfigChange, Hypothesis, Patch, Verdict
from autoguard.evaluator.objective import loss
from autoguard.rsi import analista, loop, mejorador
from autoguard.rsi.analista import (
    ALPHA_L, BETA_L, MULT_MAX, MULT_MIN, NIVEL_CUANTIL, analyze, best_multiplier, optimal_multiplier,
)
from autoguard.rsi.mejorador import patch_target, propose
from autoguard.segments import ANIO_REFERENCIA

ROOT = Path(__file__).resolve().parents[1]
# Con ruido lognormal(0, σ) la prima "justa" (=costo esperado sin ruido) queda por debajo del cuantil 0.6;
# este factor calibra el nivel global para que el único sesgo sea el plantado.
SIGMA = 0.15
Z06 = 0.2533471031357997  # Φ^-1(0.6)


@pytest.fixture(autouse=True)
def _mock_llm(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)


@pytest.fixture(scope="module")
def cfg() -> CotizadorConfig:
    return load_config(ROOT / "configs/agents/cotizador.yaml")


def _vehicles(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "vehicle_id": [f"v{seed}_{i}" for i in range(n)],
        "marca": rng.choice(["Nissan", "VW", "Chevrolet", "Seat", "BMW"], n),
        "modelo": rng.choice(["A", "B"], n),
        "anio": rng.integers(1988, 2026, n),
        "kilometraje": rng.integers(0, 300_000, n),
        "siniestros_previos": rng.choice([0, 1, 2], n, p=[0.6, 0.3, 0.1]),
        "uso": rng.choice(["particular", "app_transporte", "comercial"], n, p=[0.6, 0.25, 0.15]),
        "zona": rng.choice(["CDMX", "EDOMEX", "JAL", "NL", "PUE", "OTRA"], n),
        "danos_costo": rng.choice([0.0, 5_000.0, 30_000.0], n, p=[0.6, 0.2, 0.2]),
        "cobertura_verificacion": 1.0,
    })


def make_train(cfg, n=2500, seed=11, factor=True, marca=True, danos=True, interaccion=True) -> pd.DataFrame:
    """Train SIMULADO: costo = prima_campeón × riesgo plantado × ruido, calibrado al cuantil 0.6."""
    df = _vehicles(n, seed)
    rng = np.random.default_rng(seed + 1)
    real = np.ones(n)
    if factor:
        real *= np.where(df["uso"] == "app_transporte", 1.45 / 1.15, 1.0)
    if interaccion:
        real *= np.where((ANIO_REFERENCIA - df["anio"] >= 30) & (df["siniestros_previos"] == 1), 0.6, 1.0)
    if marca:
        real *= np.where(df["marca"] == "BMW", 1.6, 1.0)
    if danos:
        real *= np.where(df["danos_costo"] >= 20_000, 1.3, 1.0)
    noise = rng.lognormal(0.0, SIGMA, n) / np.exp(SIGMA * Z06)
    return df.assign(costo_real=quote_df(df, cfg) * real * noise)


def train_loss(cfg, df) -> float:
    return float(loss(quote_df(df, cfg), df["costo_real"]).sum())


@pytest.fixture(scope="module")
def train_full(cfg):
    return make_train(cfg)


@pytest.fixture(scope="module")
def hyps_full(cfg, train_full):
    return analyze(train_full.assign(prima=quote_df(train_full, cfg)), top_k=12)


# ================================================================ 1. optimal_multiplier
def test_constantes_derivadas_de_loss():
    assert ALPHA_L == 1.5 and BETA_L == 1.0
    assert NIVEL_CUANTIL == pytest.approx(0.6)


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_optimal_multiplier_es_argmin_en_malla(seed):
    rng = np.random.default_rng(seed)
    n = int(rng.integers(20, 300))
    prima = rng.lognormal(np.log(9000), 0.4, n)
    costo = prima * rng.lognormal(rng.normal(0, 0.3), rng.uniform(0.1, 0.6), n)
    m_star = optimal_multiplier(prima, costo)
    grid = np.linspace(0.2, 5.0, 20001)
    losses = np.array([loss(m * prima, costo).sum() for m in grid])
    m_grid = grid[int(np.argmin(losses))]
    assert loss(m_star * prima, costo).sum() <= losses.min() + 1e-6 * losses.min()
    assert m_star == pytest.approx(m_grid, abs=5e-3 * max(1.0, m_grid))


def test_optimal_multiplier_no_es_el_que_anula_el_sesgo_medio():
    rng = np.random.default_rng(42)
    prima = np.full(5000, 10_000.0)
    costo = prima * rng.lognormal(0.0, 0.4, 5000)
    m_star = optimal_multiplier(prima, costo)
    m_sesgo = 1.0 / np.mean(prima / costo)  # anula mean((m·p − c)/c)
    assert np.mean((m_sesgo * prima - costo) / costo) == pytest.approx(0.0, abs=1e-9)
    assert abs(m_star - m_sesgo) > 0.05
    l_star = loss(m_star * prima, costo).sum()
    l_sesgo = loss(m_sesgo * prima, costo).sum()
    assert l_star < 0.99 * l_sesgo
    # con prima constante, m* es el cuantil 0.6 de costo/prima
    assert m_star == pytest.approx(np.quantile(costo / prima, 0.6), rel=2e-3)


def test_optimal_multiplier_entradas_degeneradas():
    assert optimal_multiplier([], []) == 1.0
    assert optimal_multiplier([0.0, -1.0, np.nan], [1.0, 2.0, 3.0]) == 1.0
    # ignora filas no finitas
    assert optimal_multiplier([1.0, 1.0, np.inf, 1.0], [2.0, 2.0, 99.0, np.nan]) == 2.0


# ================================================================ 2. best_multiplier
def test_best_multiplier_encoge_hacia_uno():
    rng = np.random.default_rng(0)
    prima = np.full(20_000, 100.0)
    costo = prima * 1.3 * rng.lognormal(0, 0.05, 20_000)
    opt = optimal_multiplier(prima, costo)
    pocas = best_multiplier(prima[:5], costo[:5])
    muchas = best_multiplier(prima, costo)
    assert 1.0 < pocas < 1.1  # 5/(5+30) del log
    assert pocas == pytest.approx(np.exp(np.log(optimal_multiplier(prima[:5], costo[:5])) * 5 / 35))
    assert muchas == pytest.approx(opt, rel=5e-3)
    # monótono en n
    ms = [best_multiplier(prima[:n], costo[:n]) for n in (5, 30, 300, 3000)]
    assert ms == sorted(ms)


def test_best_multiplier_cotas_y_entradas_invalidas():
    p = np.full(10_000, 100.0)
    assert best_multiplier(p, p * 10) == MULT_MAX
    assert best_multiplier(p, p * 0.05) == MULT_MIN
    assert best_multiplier(p, np.zeros_like(p)) == MULT_MIN  # m* = 0
    assert best_multiplier([], []) == 1.0
    assert best_multiplier([1.0, 2.0], [np.nan, np.inf]) == 1.0
    assert np.isfinite(best_multiplier([1.0, np.nan, 2.0], [1.5, 3.0, np.nan]))


# ================================================================ 3. analyze
def _errores(n=4000, seed=5, plant=None, bias=0.0):
    df = _vehicles(n, seed)
    rng = np.random.default_rng(seed)
    costo = rng.lognormal(np.log(10_000), 0.3, n)
    ratio = rng.lognormal(0.0, 0.10, n) * np.exp(0.10 * Z06)  # prima ya en el cuantil óptimo
    if plant:
        ratio = ratio * np.where(segments.segment_mask(df, plant), 1 + bias, 1.0)
    prima = costo * ratio
    return df.assign(prima=prima, costo_real=costo)


@pytest.mark.parametrize("plant", [{"danos_costo_min": 1, "danos_costo_max": 9_999},
                                   {"danos_costo_min": 20_000}])
def test_analyze_recupera_sesgo_en_bins_de_danos(plant):
    df = _errores(plant=plant, bias=-0.25)
    hyps = analyze(df, top_k=5)
    assert hyps and hyps[0].segmento == plant
    top = hyps[0]
    m = segments.segment_mask(df, plant)
    l0 = loss(df["prima"][m], df["costo_real"][m]).sum()
    mult = best_multiplier(df["prima"][m], df["costo_real"][m])
    reducible = l0 - loss(mult * df["prima"][m], df["costo_real"][m]).sum()
    assert top.impacto > 0 and top.impacto == pytest.approx(reducible, rel=1e-9)
    assert [h.impacto for h in hyps] == sorted((h.impacto for h in hyps), reverse=True)
    assert all(h.impacto > 0 and h.p_value < 0.05 for h in hyps)


# ================================================================ 4. mejorador con datos
def _check(cfg, df, patch, arm):
    assert patch.tipo == arm and patch.veredicto is None, patch.razon
    new = apply_patch(cfg, patch)  # no falla
    assert train_loss(new, df) < train_loss(cfg, df)
    return new


@pytest.fixture(scope="module")
def factor_patches(cfg, train_full, hyps_full):
    return propose(cfg, hyps_full, ["ajuste_factor"] * 3, 1, train=train_full)


def test_ajuste_factor_baja_perdida_y_objetivos_unicos(cfg, train_full, factor_patches):
    targets = [patch_target(p) for p in factor_patches if p.veredicto != "invalido"]
    assert targets and len(targets) == len(set(targets))
    assert all(t.startswith("factor:") for t in targets)
    assert targets[0] == "factor:uso"  # el factor mal calibrado es el de mayor ganancia
    for p in factor_patches:
        if p.veredicto != "invalido":
            _check(cfg, train_full, p, "ajuste_factor")
    p0 = factor_patches[0]
    assert all(ch.op == "set" and ch.path.startswith("factores.uso.") for ch in p0.cambios)
    new = apply_patch(cfg, p0)
    assert new.factores["uso"].categorias["app_transporte"] > cfg.factores["uso"].categorias["app_transporte"] * 1.1


def test_nueva_variable_descubre_factor_completo(cfg, train_full, hyps_full):
    ps = propose(cfg, hyps_full, ["nueva_variable"] * 2, 1, train=train_full)
    targets = [patch_target(p) for p in ps]
    assert targets[0] in ("nueva:marca", "nueva:danos_costo")
    assert set(targets) == {"nueva:marca", "nueva:danos_costo"}
    for p in ps:
        _check(cfg, train_full, p, "nueva_variable")
        ch = p.cambios[0]
        assert ch.op == "add_factor"
        if ch.path == "marca":  # factor COMPLETO: varias marcas, BMW la más cara
            cats = ch.value["categorias"]
            assert len(cats) >= 2 and max(cats, key=cats.get) == "BMW"
        else:
            assert ch.value["bins"] == [0.0, 1.0, 10_000.0, 20_000.0]
            assert ch.value["valores"][3] == max(ch.value["valores"])


def test_cambio_regla_prefiere_interaccion_plantada(cfg):
    df = make_train(cfg, n=3000, seed=21, factor=False, marca=False, danos=False, interaccion=True)
    hyps = analyze(df.assign(prima=quote_df(df, cfg)), top_k=6)
    plant = {"antiguedad_min": 30, "siniestros_previos": 1}
    assert plant in [h.segmento for h in hyps]
    ps = propose(cfg, hyps, ["cambio_regla"] * 2, 1, train=df)
    p0 = ps[0]
    new = _check(cfg, df, p0, "cambio_regla")
    assert p0.segmento == plant
    assert p0.cambios[0].op == "add_rule" and new.reglas[-1].multiplicador < 1.0
    segs = [describe for describe in (patch_target(p) for p in ps if p.veredicto != "invalido")]
    assert len(segs) == len(set(segs))


def test_evitar_excluye_objetivo_y_determinismo(cfg, train_full, hyps_full, factor_patches):
    first = patch_target(factor_patches[0])
    ps = propose(cfg, hyps_full, ["ajuste_factor"], 1, train=train_full, evitar={first})
    assert patch_target(ps[0]) not in ("", first)
    again = propose(cfg, hyps_full, ["ajuste_factor"] * 3, 1, train=train_full)
    assert [p.model_dump() for p in again] == [p.model_dump() for p in factor_patches]


def test_hipotesis_no_se_repite_entre_brazos(cfg, train_full, hyps_full):
    ps = propose(cfg, hyps_full, ["cambio_regla", "cambio_regla", "nueva_variable"], 2, train=train_full)
    valid = [p for p in ps if p.veredicto != "invalido"]
    targets = [patch_target(p) for p in valid]
    assert len(targets) == len(set(targets))
    reglas = [json.dumps(p.segmento, sort_keys=True) for p in valid if p.tipo == "cambio_regla"]
    assert len(reglas) == len(set(reglas))


def test_patch_target():
    mk = lambda tipo, cambios, seg=None: Patch(patch_id="x", generation=0, tipo=tipo, hipotesis="",  # noqa: E731
                                               segmento=seg or {}, cambios=cambios)
    assert patch_target(mk("ajuste_factor", [ConfigChange(op="set", path="factores.zona.categorias.CDMX",
                                                          value=1.2)])) == "factor:zona"
    assert patch_target(mk("nueva_variable", [ConfigChange(op="add_factor", path="marca",
                                                           value={"variable": "marca"})])) == "nueva:marca"
    seg = {"uso": "app_transporte", "zona": "CDMX"}
    assert patch_target(mk("cambio_regla", [ConfigChange(op="add_rule", value={})], seg)) == \
        "regla:" + segments.describe(seg)
    assert patch_target(mk("cambio_prompt", [ConfigChange(op="set", path="prompt_estrategia", value="x")])) == ""
    assert patch_target(mk("ajuste_factor", [])) == ""


# ================================================================ 5. robustez
def test_damp_toma_la_raiz_en_escala_log(cfg):
    cambios = [
        ConfigChange(op="set", path="factores.uso.categorias.app_transporte", value=1.15 * 1.44),
        ConfigChange(op="set", path="factores.marca.categorias.BMW", value=1.69),  # sin factor: parte de 1
        ConfigChange(op="add_rule", value={"id": "r", "segmento": {"uso": "comercial"}, "multiplicador": 0.64}),
        ConfigChange(op="add_factor", path="danos_costo",
                     value={"variable": "danos_costo", "bins": [0.0, 20_000.0], "valores": [1.0, 1.21]}),
        ConfigChange(op="set", path="prompt_estrategia", value="sin cambio"),
    ]
    d = mejorador._damp(cfg, cambios)
    assert d[0].value == pytest.approx(1.15 * 1.2, abs=1e-4)
    assert d[1].value == pytest.approx(1.3, abs=1e-4)
    assert d[2].value["multiplicador"] == pytest.approx(0.8, abs=1e-4)
    assert d[3].value["valores"] == pytest.approx([1.0, 1.1], abs=1e-4)
    assert d[4].value == "sin cambio"


def _robust_case(cfg):
    """Regla sobre uso=app_transporte ×1.6 cuando app está subcotizado (×1.6) en todas las zonas MENOS PUE:
    baja la pérdida total pero sobrecotiza app en PUE (empeora el segmento zona=PUE)."""
    df = make_train(cfg, n=3000, seed=31, factor=False, marca=False, danos=False, interaccion=False)
    m = ((df["uso"] == "app_transporte") & (df["zona"] != "PUE")).to_numpy()
    df = df.assign(costo_real=df["costo_real"] * np.where(m, 1.6, 1.0))
    costo = df["costo_real"].to_numpy(dtype=float)
    l_before = analista.row_loss(quote_df(df, cfg), costo)
    seg = {"uso": "app_transporte"}
    prop = {"cambios": [ConfigChange(op="add_rule", value={"id": "r1", "segmento": seg, "multiplicador": 1.6})],
            "diff": "+ regla r1"}
    return df, costo, l_before, seg, prop


def test_robustify_amortigua_o_descarta_segmento_que_empeora(cfg):
    df, costo, l_before, seg, prop = _robust_case(cfg)
    full = apply_patch(cfg, Patch(patch_id="p", generation=0, tipo="cambio_regla", hipotesis="",
                                  cambios=prop["cambios"]))
    l_full = analista.row_loss(quote_df(df, full), costo)
    assert l_full.sum() < l_before.sum()
    worst_full = mejorador._worst_segment(cfg, full, df, l_before, l_full, seg)
    assert worst_full > mejorador.ROBUST_EPS  # el cambio completo empeora algún segmento de train
    out = mejorador._robustify(cfg, prop, df, costo, l_before, seg)
    if out is None:
        return  # descartado: válido
    mult = out["cambios"][0].value["multiplicador"]
    assert mult < 1.6 and mult in (pytest.approx(1.6 ** 0.5, abs=1e-4), pytest.approx(1.6 ** 0.25, abs=1e-4))
    assert "amortiguado" in out["razon"]
    new = apply_patch(cfg, Patch(patch_id="p", generation=0, tipo="cambio_regla", hipotesis="",
                                 cambios=out["cambios"]))
    l_new = analista.row_loss(quote_df(df, new), costo)
    assert l_new.sum() < l_before.sum()
    assert mejorador._worst_segment(cfg, new, df, l_before, l_new, seg) <= mejorador.ROBUST_EPS


def test_robustify_descarta_si_no_baja_train_y_respeta_lo_robusto(cfg):
    df, costo, l_before, seg, _ = _robust_case(cfg)
    malo = {"cambios": [ConfigChange(op="add_rule", value={"id": "r2", "segmento": {"uso": "particular"},
                                                          "multiplicador": 0.5})], "diff": ""}
    assert mejorador._robustify(cfg, malo, df, costo, l_before, {"uso": "particular"}) is None
    seg_ok = {"uso": "app_transporte", "zona": "CDMX"}
    bueno = {"cambios": [ConfigChange(op="add_rule", value={"id": "r3", "segmento": seg_ok,
                                                           "multiplicador": 2.0})], "diff": "+ r3"}
    out = mejorador._robustify(cfg, bueno, df, costo, l_before, seg_ok)
    assert out is not None and out["cambios"] == bueno["cambios"] and out["diff"] == "+ r3"
    assert "amortiguado" not in out["razon"]


# ================================================================ 6. loop
def _rows(ratios, oracle=100.0, batch_size=10):
    n = len(ratios)
    return pd.DataFrame(dict(batch=range(1, n + 1), polizas=[(i + 1) * batch_size for i in range(n)],
                             loss=[oracle * r for r in ratios], loss_oraculo=[oracle] * n))


def test_convergence_polizas():
    assert loop.convergence_polizas(_rows([3.0] * 10)) is None  # nunca baja
    # entra en el lote 5 y se queda: la primera ventana [3,4,5] aún es mala; [4,5,6]... depende de la media
    ratios = [2.0] * 4 + [1.0] * 6
    rows = _rows(ratios)
    got = loop.convergence_polizas(rows)
    roll = pd.Series(ratios).rolling(3).mean()
    first_ok = int(np.argmax(roll.to_numpy() <= 1.1))
    assert got == (first_ok + 1) * 10 == 70
    # entra y sale: converge después de su última salida
    ratios = [1.0] * 4 + [2.0] + [1.0] * 5
    assert loop.convergence_polizas(_rows(ratios)) == 80  # ventanas que tocan el lote 5 => lotes 5..7 malos
    # termina mal => None aunque haya estado bien antes
    assert loop.convergence_polizas(_rows([1.0] * 8 + [2.0, 2.0])) is None
    # siempre bien => primer lote con ventana completa
    assert loop.convergence_polizas(_rows([1.0] * 6)) == 30
    # el orden de entrada no importa (ordena por lote)
    assert loop.convergence_polizas(_rows(ratios).sample(frac=1, random_state=0)) == 80
    # window=1 y todo bien => el primer lote
    assert loop.convergence_polizas(_rows([1.0] * 4), window=1) == 10


def test_oracle_reference():
    rng = np.random.default_rng(3)
    bench = []
    for _ in range(4):
        e = rng.lognormal(np.log(9000), 0.3, 50)
        bench.append((e, e * rng.lognormal(0, 0.2, 50)))
    ref = loop.oracle_reference(bench)
    e = np.concatenate([b[0] for b in bench])
    c = np.concatenate([b[1] for b in bench])
    # cuantil ponderado (por costo esperado) nivel 0.6 de c/e
    r = c / e
    order = np.argsort(r)
    cw = np.cumsum(e[order])
    q = r[order][np.searchsorted(cw, 0.6 * cw[-1])]
    assert ref["multiplicador"] == pytest.approx(q)
    assert ref["regret"] == pytest.approx(loss(e * q, c).sum())
    assert len(ref["loss_por_lote"]) == 4
    assert sum(lpb * 50 for lpb in ref["loss_por_lote"]) == pytest.approx(ref["regret"])
    # ninguna otra constante global lo mejora
    for m in (q * 0.97, q * 1.03, 1.0):
        assert loss(e * m, c).sum() >= ref["regret"]


def test_loop_compone_parches_y_rechaza_el_redundante(tmp_path, monkeypatch):
    """Dos parches aceptados contra el mismo campeón que corrigen lo mismo: el segundo se re-evalúa sobre la
    composición y queda rechazado. Evaluador doble: acepta si el parche cambia la config (ganancia por id)."""
    ganancia = {"dup_a": 0.05, "dup_b": 0.04, "otro": 0.03}
    calls = []

    def fake_evaluate(champion, patch, holdout):
        challenger = apply_patch(champion, patch)
        base = patch.patch_id.split("@")[0]
        cambia = challenger.model_dump() != champion.model_dump()
        calls.append((base, cambia))
        g = ganancia[base] if cambia else 0.0
        ok = g >= 0.01
        razon = f"ganancia {g:+.2%} ≥ δ" if ok else f"ganancia {g:+.2%} < δ=1%"
        patch.veredicto = "aceptado" if ok else "rechazado"
        patch.razon = razon
        return Verdict(patch_id=patch.patch_id, aceptado=ok, loss_before=1.0, loss_after=1 - g,
                       ganancia=g, razones=[razon]), (challenger if ok else None)

    def fake_propose(cfg, hyps, arms, generation, **kw):
        same = [ConfigChange(op="set", path="factores.uso.categorias.app_transporte", value=1.4)]
        mk = lambda pid, cambios: Patch(patch_id=f"{pid}@g{generation}", generation=generation,  # noqa: E731
                                        tipo="ajuste_factor", hipotesis="h", cambios=cambios)
        return [mk("dup_b", same), mk("dup_a", list(same)),
                mk("otro", [ConfigChange(op="set", path="factores.zona.categorias.PUE", value=1.1)])]

    monkeypatch.setattr(loop, "evaluate", fake_evaluate)
    monkeypatch.setattr(loop, "propose", fake_propose)
    monkeypatch.setattr(loop, "analyze", lambda train, top_k=12: [])
    monkeypatch.setattr(loop, "ROUNDS_MAX", 1)  # una sola ronda: aísla la lógica de composición
    loop.run_experiment(seed=1, batches=1, batch_size=60, k=1, output_dir=tmp_path / "run")
    patches = [json.loads(line) for line in (tmp_path / "run/patches.jsonl").read_text(encoding="utf-8").splitlines()]
    for variant in ("parametros", "rsi"):
        got = {p["patch_id"].split("@")[0]: p for p in patches if p["variant"] == variant}
        assert got["dup_a"]["veredicto"] == "aceptado"  # mayor ganancia: se compone primero
        assert got["otro"]["veredicto"] == "aceptado"
        assert got["dup_b"]["veredicto"] == "rechazado"
        assert "no mejora sobre la composición" in got["dup_b"]["razon"]
        assert "+4.00%" in got["dup_b"]["razon"]
    versions = [json.loads(line) for line in (tmp_path / "run/versions.jsonl").read_text(encoding="utf-8").splitlines()]
    # v0 + dup_a + otro por variante que aprende
    assert sum(v["variant"] == "rsi" for v in versions) == 3
    # cada variante: 3 contra el campeón + re-evaluación de los 2 siguientes sobre la composición
    assert len(calls) == 2 * 5
