"""Tests del agente visual (T-12). Sin red: modo mock o LLM falso. Datos SIMULADOS."""
from __future__ import annotations

import json

import pytest

from autoguard import llm
from autoguard.agents import visual
from autoguard.contracts import Dano


@pytest.fixture(autouse=True)
def _mock_llm(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def _gt():
    return json.loads((visual.FOTOS_DIR / visual.GROUND_TRUTH).read_text(encoding="utf-8"))


def test_tabla_costos_simulada_y_determinista():
    tabla = visual._tabla()
    assert tabla["nota"] == "SIMULADO" and tabla["moneda"] == "MXN"
    assert visual.costo("defensa_trasera", "abolladura") == 2800.0
    assert visual.costo("zona_rara", "rayon") == tabla["zonas"]["default"]["rayon"]
    assert visual.costo("parabrisas", "abolladura") == tabla["zonas"]["default"]["abolladura"]
    for z in visual.zonas():
        for t in visual.tipos():
            assert visual.costo(z, t) > 0
    # el reemplazo cuesta más que el rayón en toda zona que tenga ambos
    for z, fila in tabla["zonas"].items():
        if "rayon" in fila and "reemplazo" in fila:
            assert fila["reemplazo"] > fila["rayon"], z


def test_mock_por_ground_truth():
    danos = visual.inspect([b"x"], hints=["data/samples/fotos/FOTO-003.png"])
    assert {(d.zona, d.tipo) for d in danos} == {
        ("cofre", "reparacion"), ("faro_der", "estrellado"), ("defensa_delantera", "reemplazo")}
    assert all(isinstance(d, Dano) and d.costo_est == visual.costo(d.zona, d.tipo) for d in danos)


def test_mock_por_tokens_en_nombre():
    danos = visual.inspect([], hints=["subida__Defensa_Trasera-abolladura__faro_izq-estrellado__x-y.jpg"])
    assert {(d.zona, d.tipo) for d in danos} == {("defensa_trasera", "abolladura"), ("faro_izq", "estrellado")}


def test_mock_sin_hints_o_sin_danos():
    assert visual.inspect([b"x"]) == []
    assert visual.inspect([b"x"], hints=["FOTO-006.png"]) == []


def test_consolida_por_zona_tipo_mas_costoso():
    danos = visual.inspect([], hints=["a__cofre-rayon.png", "b__cofre-reemplazo.png", "c__cofre-rayon.png"])
    assert [(d.zona, d.tipo) for d in danos] == [("cofre", "reemplazo")]


def test_llm_falso_solo_clasifica(monkeypatch):
    def falso(system, user, *, images=None, schema=None, fallback, max_tokens=2000):
        assert images == [b"img1", b"img2"]
        assert "defensa_trasera" in system
        return {"danos": [
            {"zona": "Defensa Trasera", "tipo": "abolladura", "confianza": 0.8, "costo_est": 1},  # costo ignorado
            {"zona": "rueda_de_repuesto", "tipo": "rayon", "confianza": 0.6},  # zona desconocida
            {"zona": "cofre", "tipo": "derretido", "confianza": 0.9},  # tipo inválido
            {"zona": "toldo", "tipo": "rayon", "confianza": 0.1},  # baja confianza
        ]}

    monkeypatch.setattr(llm, "is_mock", lambda: False)
    monkeypatch.setattr(llm, "complete_json", falso)
    danos = {d.zona: d for d in visual.inspect([b"img1", b"img2"])}
    assert set(danos) == {"defensa_trasera", "otra"}
    assert danos["defensa_trasera"].costo_est == 2800.0
    assert danos["defensa_trasera"].confianza == pytest.approx(0.8)
    assert danos["otra"].costo_est == visual.costo("default", "rayon")


def test_llm_falla_usa_fallback_mock(monkeypatch):
    monkeypatch.setattr(llm, "is_mock", lambda: False)
    monkeypatch.setattr(llm, "complete_json", lambda *a, fallback, **k: fallback())
    danos = visual.inspect([b"x"], hints=["FOTO-001.png"])
    assert [(d.zona, d.tipo) for d in danos] == [("defensa_trasera", "abolladura")]
    monkeypatch.setattr(llm, "complete_json", lambda *a, **k: {"danos": "basura"})
    assert [(d.zona, d.tipo) for d in visual.inspect([b"x"], hints=["FOTO-001.png"])] == [
        ("defensa_trasera", "abolladura")]


def test_muestras_y_generacion_reproducible(tmp_path):
    gt = visual.generate_samples(tmp_path)
    assert gt == _gt()
    assert "SIMULADAS" in gt["nota"]
    assert len(list(tmp_path.glob("*.png"))) == len(gt["fotos"]) >= 5
    validos_z, validos_t = set(visual.zonas()), set(visual.tipos())
    for d in gt["fotos"].values():
        assert all(x["zona"] in validos_z and x["tipo"] in validos_t for x in d["danos"])


def test_eval_recall_100_en_mock(capsys):
    r = visual.evaluate()
    assert r["modo"] == "mock" and r["recall"] == 1.0 and r["precision"] == 1.0
    assert visual.main(["--eval"]) == 0
    assert "recall" in capsys.readouterr().out
