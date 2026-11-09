"""Tests del evaluador congelado (T-09). Datos SIMULADOS, sin red, semilla fija."""
from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from autoguard.agents.cotizador import quote_df
from autoguard.config_schema import load_config
from autoguard.contracts import ConfigChange, Patch
from autoguard.evaluator import objective
from autoguard.evaluator.evaluator import evaluate, split_holdout

ROOT = Path(__file__).resolve().parents[1]
CFG_PATH = ROOT / "configs" / "agents" / "cotizador.yaml"
MARCAS = ["Nissan", "Volkswagen", "Chevrolet", "Toyota", "Honda", "Kia"]
USOS = ["particular", "app_transporte", "comercial"]
ZONAS = ["CDMX", "EDOMEX", "JAL", "NL", "PUE", "OTRA"]


@pytest.fixture(scope="module")
def cfg():
    return load_config(CFG_PATH)


def _vehicles(n: int, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    anio = rng.integers(1990, 2027, n)
    return pd.DataFrame({
        "vehicle_id": [f"veh-{i:06d}" for i in range(n)],
        "marca": rng.choice(MARCAS, n),
        "modelo": "SIMULADO",
        "anio": anio,
        "kilometraje": rng.integers(0, 300_000, n),
        "siniestros_previos": rng.integers(0, 4, n),
        "uso": rng.choice(USOS, n),
        "zona": rng.choice(ZONAS, n),
        "danos_costo": 0.0,
        "cobertura_verificacion": 1.0,
    })


@pytest.fixture(scope="module")
def holdout(cfg):
    """Costo real = prima del campeón × ruido, salvo app_transporte que cuesta 40% más (sesgo plantado)."""
    df = _vehicles(3000)
    rng = np.random.default_rng(11)
    base = quote_df(df, cfg)
    sesgo = np.where(df["uso"] == "app_transporte", 1.4, 1.0)
    df["prima"] = base
    df["costo_real"] = base * sesgo * rng.lognormal(0.0, 0.1, len(df))
    return df


def _patch(cambios, pid="p-1", tipo="ajuste_factor", segmento=None) -> Patch:
    return Patch(patch_id=pid, generation=1, tipo=tipo, hipotesis="SIMULADO", segmento=segmento or {},
                 cambios=[ConfigChange(**c) for c in cambios])


FIX_APP = {"op": "set", "path": "factores.uso.categorias.app_transporte", "value": 1.15 * 1.4}


# ---------------------------------------------------------------- split_holdout
def test_split_holdout_deterministico_y_disjunto(holdout):
    train, hold = split_holdout(holdout)
    assert len(train) + len(hold) == len(holdout)
    assert set(train["vehicle_id"]).isdisjoint(hold["vehicle_id"])
    assert abs(len(hold) / len(holdout) - objective.HOLDOUT_FRACTION) < 0.03
    # independiente del orden de las filas y de llamadas repetidas
    _, hold2 = split_holdout(holdout.sample(frac=1.0, random_state=3))
    assert set(hold2["vehicle_id"]) == set(hold["vehicle_id"])


def test_split_holdout_estable_por_vehiculo(holdout):
    _, hold_full = split_holdout(holdout)
    _, hold_sub = split_holdout(holdout.iloc[:500])
    assert set(hold_sub["vehicle_id"]) == set(hold_full["vehicle_id"]) & set(holdout.iloc[:500]["vehicle_id"])


def test_split_holdout_vacio():
    empty = pd.DataFrame(columns=["vehicle_id"])
    tr, ho = split_holdout(empty)
    assert len(tr) == 0 and len(ho) == 0


# ---------------------------------------------------------------- evaluate
def test_acepta_parche_que_corrige_sesgo(cfg, holdout):
    verdict, retador = evaluate(cfg, _patch([FIX_APP]), holdout)
    assert verdict.aceptado, verdict.razones
    assert verdict.ganancia >= objective.DELTA
    assert verdict.loss_after < verdict.loss_before
    assert verdict.peor_delta <= objective.EPSILON
    assert retador is not None
    assert retador.factores["uso"].categorias["app_transporte"] == pytest.approx(1.15 * 1.4)
    # el campeón no se muta
    assert cfg.factores["uso"].categorias["app_transporte"] == pytest.approx(1.15)


def test_rechaza_regresion_por_segmento_aunque_mejore_total(cfg, holdout):
    patch = _patch([FIX_APP, {"op": "set", "path": "factores.zona.categorias.PUE", "value": 1.3}])
    verdict, retador = evaluate(cfg, patch, holdout)
    assert verdict.ganancia >= objective.DELTA  # mejora el total...
    assert not verdict.aceptado  # ...pero empeora PUE
    assert retador is None
    assert verdict.peor_delta > objective.EPSILON
    assert verdict.peor_segmento is not None
    assert any("zona = PUE" in r for r in verdict.razones)


def test_rechaza_ganancia_menor_a_delta(cfg, holdout):
    patch = _patch([{"op": "set", "path": "prompt_estrategia", "value": "explica mejor"}], tipo="cambio_prompt")
    verdict, retador = evaluate(cfg, patch, holdout)
    assert not verdict.aceptado and retador is None
    assert verdict.ganancia == pytest.approx(0.0)
    assert any("δ" in r for r in verdict.razones)


def test_segmentos_pequenos_no_bloquean(cfg, holdout):
    # regla que empeora mucho un segmento minúsculo (n < MIN_SEGMENT_N) + corrección grande
    seg = {"kilometraje_max": 1000}
    n_seg = int((holdout["kilometraje"] <= 1000).sum())
    assert 0 < n_seg < objective.MIN_SEGMENT_N
    patch = _patch([FIX_APP, {"op": "add_rule", "value": {"id": "tiny", "segmento": seg, "multiplicador": 1.25}}],
                   tipo="cambio_regla", segmento=seg)
    verdict, retador = evaluate(cfg, patch, holdout)
    assert verdict.aceptado, verdict.razones
    # el segmento minúsculo sí empeoró > ε, pero no cuenta por n < MIN_SEGMENT_N
    m = (holdout["kilometraje"] <= 1000).to_numpy()
    c = holdout["costo_real"].to_numpy()
    lb = objective.loss(quote_df(holdout, cfg), c)[m].mean()
    la = objective.loss(quote_df(holdout, retador), c)[m].mean()
    assert (la - lb) / lb > objective.EPSILON


@pytest.mark.parametrize("cambio", [
    {"op": "add_factor", "path": "genero", "value": {"variable": "genero", "categorias": {"F": 0.9}}},
    {"op": "add_rule", "value": {"id": "r1", "segmento": {"edad_min": 60}, "multiplicador": 1.2}},
    {"op": "set", "path": "factores.zona.variable", "value": "cp_ingreso"},
])
def test_rechaza_variable_prohibida(cfg, holdout, cambio):
    verdict, retador = evaluate(cfg, _patch([cambio]), holdout)
    assert not verdict.aceptado and retador is None
    assert verdict.razones[0].startswith("invalido")
    assert "prohibida" in verdict.razones[0]


def test_rechaza_variable_fuera_de_lista_blanca(cfg, holdout):
    cambio = {"op": "add_factor", "path": "color", "value": {"variable": "color", "categorias": {"rojo": 1.1}}}
    verdict, retador = evaluate(cfg, _patch([cambio]), holdout)
    assert not verdict.aceptado and retador is None
    assert "lista blanca" in verdict.razones[0]


class _HoldoutTrampa:
    """Cualquier acceso al holdout falla: prueba que un parche inválido no lo consume."""
    accesos = 0

    def __getattr__(self, name):
        type(self).accesos += 1
        raise AssertionError(f"holdout consumido: .{name}")

    def __getitem__(self, key):
        type(self).accesos += 1
        raise AssertionError("holdout consumido: []")

    def __len__(self):
        type(self).accesos += 1
        raise AssertionError("holdout consumido: len()")


@pytest.mark.parametrize("cambios", [
    [{"op": "set", "path": "factores.uso.categorias.app_transporte", "value": 99.0}],  # fuera de rango
    [{"op": "set", "path": "factores.antiguedad.valores.9", "value": 1.0}],  # índice inválido
    [{"op": "add_factor", "path": "uso", "value": {"variable": "uso", "categorias": {"x": 1.0}}}],  # duplicado
    [{"op": "add_rule", "value": {"id": "r", "segmento": {"genero": "F"}, "multiplicador": 1.0}}],
])
def test_parche_invalido_no_consume_holdout(cfg, cambios):
    _HoldoutTrampa.accesos = 0
    verdict, retador = evaluate(cfg, _patch(cambios), _HoldoutTrampa())
    assert not verdict.aceptado and retador is None
    assert verdict.razones[0].startswith("invalido")
    assert _HoldoutTrampa.accesos == 0


def test_holdout_vacio_rechaza(cfg, holdout):
    verdict, retador = evaluate(cfg, _patch([FIX_APP]), holdout.iloc[:0])
    assert not verdict.aceptado and retador is None


def test_reproducible(cfg, holdout):
    v1, _ = evaluate(cfg, _patch([FIX_APP]), holdout)
    v2, _ = evaluate(cfg, _patch([FIX_APP]), holdout.copy())
    assert v1.model_dump() == v2.model_dump()


def test_regresion_en_segmento_del_parche(cfg, holdout):
    """Una regla que sobrecotiza su propio segmento se rechaza (empeora ese segmento)."""
    seg = {"siniestros_previos_min": 2, "uso": "particular"}
    patch = _patch([FIX_APP, {"op": "add_rule", "value": {"id": "malo", "segmento": seg, "multiplicador": 1.5}}],
                   tipo="cambio_regla", segmento=seg)
    verdict, retador = evaluate(cfg, patch, holdout)
    assert not verdict.aceptado and retador is None
    assert verdict.peor_delta > objective.EPSILON


# ---------------------------------------------------------------- aislamiento del RSI (AST)
ALLOWED_IMPORTS = {
    ("autoguard.evaluator.objective", "loss"),
    ("autoguard.evaluator.evaluator", "split_holdout"),
    ("autoguard.evaluator.evaluator", "evaluate"),
}


def _rsi_files() -> list[Path]:
    files = sorted((ROOT / "autoguard" / "rsi").rglob("*.py"))
    assert files, "no se encontraron módulos en autoguard/rsi"
    return files


def _violations(source: str, fname: str = "<mod>") -> list[str]:
    tree = ast.parse(source)
    errs: list[str] = []
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("autoguard.evaluator"):
                    errs.append(f"{fname}:{node.lineno} import {a.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level:
                errs.append(f"{fname}:{node.lineno} import relativo prohibido en rsi")
                continue
            if mod == "autoguard" and any(a.name == "evaluator" for a in node.names):
                errs.append(f"{fname}:{node.lineno} from autoguard import evaluator")
            if mod.startswith("autoguard.evaluator"):
                for a in node.names:
                    if (mod, a.name) not in ALLOWED_IMPORTS:
                        errs.append(f"{fname}:{node.lineno} from {mod} import {a.name}")
                    else:
                        imported.add(a.asname or a.name)
        elif isinstance(node, ast.Call):
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else ""
            if name in {"__import__", "import_module"}:
                errs.append(f"{fname}:{node.lineno} import dinámico")
            if name == "setattr" and node.args and isinstance(node.args[0], ast.Name) and node.args[0].id in imported:
                errs.append(f"{fname}:{node.lineno} setattr sobre {node.args[0].id}")
        elif isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id in imported:
                    errs.append(f"{fname}:{node.lineno} escribe atributo de {t.value.id}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            v = node.value.replace("\\", "/")
            if "evaluator/" in v or "objective.py" in v or "evaluator.py" in v:
                errs.append(f"{fname}:{node.lineno} ruta hacia autoguard/evaluator en literal")
    return errs


def test_rsi_no_importa_ni_escribe_evaluador():
    errs = []
    for f in _rsi_files():
        errs += _violations(f.read_text(encoding="utf-8"), str(f.relative_to(ROOT)))
    assert not errs, "\n".join(errs)


@pytest.mark.parametrize("src", [
    "import autoguard.evaluator.objective",
    "from autoguard.evaluator import objective",
    "from autoguard import evaluator",
    "from autoguard.evaluator.objective import ALPHA",
    "from autoguard.evaluator.evaluator import _validate",
    "from ..evaluator import objective",
    "import importlib\nimportlib.import_module('autoguard.evaluator.objective')",
    "from autoguard.evaluator.objective import loss\nloss.x = 1",
    "from autoguard.evaluator.objective import loss\nsetattr(loss, 'x', 1)",
    "open('autoguard/evaluator/objective.py', 'w').write('ALPHA = 0')",
])
def test_detector_ast_atrapa_violaciones(src):
    assert _violations(src)


def test_detector_ast_permite_lectura_autorizada():
    src = ("from autoguard.evaluator.objective import loss\n"
           "from autoguard.evaluator.evaluator import split_holdout, evaluate\n"
           "x = loss([1], [2])\n")
    assert _violations(src) == []
