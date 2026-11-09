"""Tests del agente documental (T-05). Sin red: LLM en modo mock o cliente falso. Datos SIMULADOS."""
from __future__ import annotations

import json
from datetime import date

import pytest

from autoguard import llm
from autoguard.agents import documental as doc
from autoguard.contracts import DocExtraction

HOY = date(2026, 11, 9)


@pytest.fixture(autouse=True)
def _mock_llm(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def _gt():
    return json.loads((doc.SAMPLES_DIR / doc.GROUND_TRUTH).read_text(encoding="utf-8"))


def _ex(doc_id, tipo="factura", **kw):
    base = dict(vin="1HGCM82633A004352", placas="ABC-123-D", marca="Honda", modelo="Accord", anio=2003)
    base.update(kw)
    return DocExtraction(documento_id=doc_id, tipo=tipo, **base)


# ---------------------------------------------------------------- VIN
def test_vin_digito_verificador():
    assert doc.vin_valido("1HGCM82633A004352")  # VIN de referencia NHTSA
    assert doc.vin_valido("1m8gdm9axkp042788")  # minúsculas, X como dígito
    assert not doc.vin_valido("1HGCM82643A004352")  # dígito alterado
    assert not doc.vin_valido("1HGCM8263")  # corto
    assert not doc.vin_valido("1HGCM82633A00435O")  # contiene O
    assert doc.normalize_vin(" 1hgcm-8263 3a004352 ") == "1HGCM82633A004352"


def test_cross_check_vin_invalido_y_formato():
    codigos = [a.codigo for a in doc.cross_check(
        [_ex("A", vin="1HGCM82643A004352"), _ex("B", tipo="tarjeta_circulacion", vin="XYZ")], hoy=HOY)]
    assert "VIN_DIGITO_VERIFICADOR" in codigos
    assert "VIN_FORMATO_INVALIDO" in codigos


def test_cross_check_expediente_limpio_sin_alertas():
    exs = [_ex("A"), _ex("B", tipo="tarjeta_circulacion", placas="abc 123 d", marca="HONDA", vigencia="2030-01-01")]
    assert doc.cross_check(exs, hoy=HOY) == []


def test_cross_check_discrepancias():
    exs = [
        _ex("A"),
        _ex("B", tipo="tarjeta_circulacion", vin="3N1CN7AD3KL812345", placas="ZZZ-999-Z", anio=2004,
            modelo="Civic", vigencia="2030-01-01"),
    ]
    alertas = {a.codigo: a for a in doc.cross_check(exs, hoy=HOY)}
    assert {"VIN_NO_COINCIDE", "PLACAS_NO_COINCIDEN", "ANIO_NO_COINCIDE", "MODELO_NO_COINCIDE"} <= set(alertas)
    assert alertas["VIN_NO_COINCIDE"].severidad == "alta"
    assert set(alertas["VIN_NO_COINCIDE"].fuentes) == {"A", "B"}


def test_cross_check_vigencias():
    exs = [
        _ex("A"),
        _ex("B", tipo="tarjeta_circulacion", vigencia="2023-06-30"),
        _ex("C", tipo="poliza_anterior", vigencia="2026-01-01"),
        _ex("D", tipo="otro", vigencia="no-es-fecha"),
    ]
    alertas = doc.cross_check(exs, hoy=HOY)
    venc = {a.fuentes[0]: a.severidad for a in alertas if a.codigo == "DOCUMENTO_VENCIDO"}
    assert venc == {"B": "alta", "C": "info"}
    assert any(a.codigo == "VIGENCIA_ILEGIBLE" for a in alertas)


def test_cross_check_documento_faltante_y_baja_confianza():
    alertas = doc.cross_check([_ex("A", confianza=0.3)], hoy=HOY)
    codigos = [a.codigo for a in alertas]
    assert "DOCUMENTO_FALTANTE" in codigos and "BAJA_CONFIANZA" in codigos


def test_cross_check_determinista():
    exs = [_ex("A"), _ex("B", tipo="tarjeta_circulacion", vin="3N1CN7AD3KL812345", vigencia="2020-01-01")]
    assert doc.cross_check(exs, hoy=HOY) == doc.cross_check(exs, hoy=HOY)


# ---------------------------------------------------------------- extracción
def test_extract_mock_lee_ground_truth():
    gt = _gt()
    for doc_id, d in gt["documentos"].items():
        ex = doc.extract((doc.SAMPLES_DIR / d["archivo"]).read_bytes(), d["tipo"], doc_id, mime="image/png")
        for c in doc.CAMPOS:
            assert getattr(ex, c) == d[c], (doc_id, c)


def test_extract_mock_documento_desconocido():
    ex = doc.extract(b"", "factura", "NO-EXISTE")
    assert ex.documento_id == "NO-EXISTE" and ex.confianza == 0.0 and ex.vin is None


def test_extract_con_llm_falso(monkeypatch):
    llamadas = {}

    def falso(system, user, *, images=None, schema=None, fallback, max_tokens=2000):
        llamadas["images"] = images
        return {"vin": "1hgcm82633a004352", "placas": "ABC-123-D", "marca": "Honda", "modelo": "Accord",
                "anio": "2003", "vigencia": None, "campos_extra": {}, "confianza": 0.93}

    monkeypatch.setattr(llm, "is_mock", lambda: False)
    monkeypatch.setattr(llm, "complete_json", falso)
    ex = doc.extract(b"\x89PNG...", "factura", "X1", mime="image/png")
    assert llamadas["images"] == [b"\x89PNG..."]
    assert ex.vin == "1HGCM82633A004352" and ex.anio == 2003 and ex.confianza == pytest.approx(0.93)


def test_extract_llm_basura_usa_fallback(monkeypatch):
    monkeypatch.setattr(llm, "is_mock", lambda: False)
    monkeypatch.setattr(llm, "complete_json", lambda *a, **k: {"anio": "abc", "confianza": "x"})
    ex = doc.extract(b"", "factura", "EXP-001-FAC", mime="image/png")
    assert ex.vin is None and ex.confianza == 0.0  # con LLM real nunca se filtra el ground truth


# ---------------------------------------------------------------- perfil
def test_build_profile_consolida_y_cobertura():
    exs = [_ex("A", placas=None), _ex("B", tipo="tarjeta_circulacion", vigencia="2030-01-01"),
           _ex("C", tipo="poliza_anterior", vigencia="2027-01-01")]
    p = doc.build_profile("veh-1", exs, {"kilometraje": 80000, "uso": "app_transporte", "zona": "JAL",
                                         "siniestros_previos": 1, "hoy": HOY,
                                         "danos": [{"zona": "defensa", "tipo": "rayon", "costo_est": 1500,
                                                    "confianza": 0.9}]})
    assert (p.marca, p.modelo, p.anio, p.vin, p.placas) == ("Honda", "Accord", 2003, "1HGCM82633A004352", "ABC-123-D")
    assert p.cobertura_verificacion == 1.0
    assert p.alertas == []
    assert (p.kilometraje, p.uso, p.zona, p.siniestros_previos) == (80000, "app_transporte", "JAL", 1)
    assert p.danos_costo == 1500


def test_build_profile_discrepancia_baja_cobertura():
    exs = [_ex("A"), _ex("B", tipo="tarjeta_circulacion", vin="3N1CN7AD3KL812345", vigencia="2030-01-01")]
    p = doc.build_profile("veh-2", exs, {"hoy": HOY})
    assert p.vin == "1HGCM82633A004352"  # empate → factura (más confiable)
    assert p.cobertura_verificacion == pytest.approx(0.8)
    assert any(a.codigo == "VIN_NO_COINCIDE" for a in p.alertas)


def test_build_profile_sin_datos():
    p = doc.build_profile("veh-3", [DocExtraction(documento_id="A", tipo="otro")], {"hoy": HOY})
    assert p.cobertura_verificacion == 0.0
    assert any(a.codigo == "DATOS_INCOMPLETOS" for a in p.alertas)


def test_build_profile_dato_declarado_no_coincide():
    p = doc.build_profile("veh-4", [_ex("A")], {"anio": 2010, "hoy": HOY})
    assert p.anio == 2003
    assert any(a.codigo == "DATO_DECLARADO_NO_COINCIDE" for a in p.alertas)


# ---------------------------------------------------------------- muestras y --eval
def test_muestras_expedientes_y_alertas_esperadas():
    gt = _gt()
    assert len(gt["expedientes"]) == 3 and "SIMULADO" in gt["nota"]
    for exp_id, e in gt["expedientes"].items():
        exs = [doc.extract(b"", gt["documentos"][i]["tipo"], i) for i in e["documentos"]]
        codigos = {a.codigo for a in doc.cross_check(exs, hoy=HOY)}
        for esperado in e["alertas_esperadas"]:
            assert esperado.split(":")[0] in codigos, (exp_id, esperado)
    exs2 = [doc.extract(b"", gt["documentos"][i]["tipo"], i) for i in gt["expedientes"]["EXP-002"]["documentos"]]
    assert all(doc.vin_valido(e.vin) for e in exs2)  # el VIN distinto es válido: solo la coincidencia lo delata
    exs1 = [doc.extract(b"", gt["documentos"][i]["tipo"], i) for i in gt["expedientes"]["EXP-001"]["documentos"]]
    assert not [a for a in doc.cross_check(exs1, hoy=HOY) if a.severidad != "info"]


def test_generate_samples_reproducible(tmp_path):
    gt = doc.generate_samples(tmp_path)
    assert gt == _gt()
    assert len(list(tmp_path.glob("*.png"))) == 9


def test_eval_mock_100(capsys):
    r = doc.evaluate()
    assert r["modo"] == "mock"
    assert all(p == 1.0 for p in r["precision_por_campo"].values())
    assert all(r["alertas_esperadas_detectadas"].values())
    assert doc.main(["--eval"]) == 0
    assert "GLOBAL" in capsys.readouterr().out
