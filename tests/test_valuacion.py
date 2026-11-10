"""Tests de valuación (T-17). Nunca llaman a la red: httpx.MockTransport y sockets bloqueados."""
from __future__ import annotations

import json
import socket

import httpx
import pytest

from autoguard.agents import valuacion as V
from autoguard.contracts import Dano, VehicleProfile


@pytest.fixture(autouse=True)
def _no_network(monkeypatch, tmp_path):
    def guard(*a, **kw):
        raise AssertionError("los tests no deben abrir sockets")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.delenv("VALUACION_OFFLINE", raising=False)
    monkeypatch.setenv("VALUACION_CACHE_DIR", str(tmp_path / "cache"))


def prof(**kw) -> VehicleProfile:
    base = dict(id="v1", marca="Nissan", modelo="Versa", anio=2019, kilometraje=80_000, siniestros_previos=0)
    base.update(kw)
    return VehicleProfile(**base)


def test_mock_without_keys_is_deterministic_and_labeled(tmp_path):
    r1, r2 = V.valuate(prof()), V.valuate(prof())
    assert r1 == r2
    assert r1["fuente"] == "mock" and r1["simulado"] is True
    lo, hi = r1["rango"]
    assert 0 < lo <= r1["precio_estimado"] <= hi
    assert all("SIMULADO" in c["titulo"] for c in r1["comparables"])
    assert not list((tmp_path / "cache").glob("*.json"))  # el mock no se cachea
    # vehículos distintos -> comparables distintos
    assert V.valuate(prof(modelo="Sentra"))["comparables"] != r1["comparables"]


def test_robust_median_ignores_outliers():
    med, lo, hi, mask = V.robust_estimate([200_000, 205_000, 198_000, 210_000, 202_000, 2_000_000, 1_000])
    assert 198_000 <= med <= 210_000
    assert mask.tolist() == [True] * 5 + [False, False]
    assert 198_000 <= lo <= med <= hi <= 210_000


def test_km_year_and_damage_adjustments():
    comps = [{"precio": 200_000.0, "anio": 2019, "kilometraje": 80_000} for _ in range(5)]
    base = V.estimate(prof(), comps, "cache")
    assert base["precio_estimado"] == pytest.approx(200_000)
    mas_km = V.estimate(prof(kilometraje=130_000), comps, "cache")
    assert mas_km["precio_estimado"] == pytest.approx(200_000 * (1 - 5 * V.AJUSTE_POR_10K_KM))
    mas_nuevo = V.estimate(prof(anio=2020), comps, "cache")
    assert mas_nuevo["precio_estimado"] == pytest.approx(200_000 * (1 + V.AJUSTE_POR_ANIO))
    danado = V.estimate(prof(danos=[Dano(zona="defensa", tipo="reemplazo", costo_est=15_000, confianza=0.9)]),
                        comps, "cache")
    assert danado["precio_estimado"] == pytest.approx(185_000)
    assert danado["descuento_danos"] == 15_000
    # ajuste acotado
    extremo = V.estimate(prof(anio=2026), comps, "cache")
    assert extremo["precio_estimado"] == pytest.approx(200_000 * (1 + V.AJUSTE_MAX))
    # nunca negativo
    total = V.estimate(prof(danos=[Dano(zona="x", tipo="reemplazo", costo_est=900_000, confianza=1)]),
                       comps, "cache")
    assert total["precio_estimado"] > 0


def _transport(calls, *, firecrawl_ok=True):
    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        if req.url.host == "api.tavily.com":
            results = [
                {"title": f"Versa 2019 #{i}", "url": f"https://anuncios.example/{i}",
                 "content": f"Nissan Versa 2019 en venta $2{i}0,000 con {70 + i},000 km"}
                for i in range(4)
            ] + [{"title": "sin precio", "url": "https://anuncios.example/x", "content": "llama ya"}]
            return httpx.Response(200, json={"results": results})
        if req.url.host == "api.firecrawl.dev":
            if not firecrawl_ok:
                return httpx.Response(500, json={"success": False})
            url = json.loads(req.content)["url"]
            if url.endswith("/x"):
                return httpx.Response(200, json={"success": True, "data": {"json": {}}})
            i = int(url.rsplit("/", 1)[1])
            return httpx.Response(200, json={"success": True, "data": {"json": {
                "precio": 210_000 + 1_000 * i, "anio": 2019, "kilometraje": 80_000, "titulo": f"Anuncio {i}"}}})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_network_path_with_injected_client_writes_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-secreta")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-secreta")
    calls: list[httpx.Request] = []
    client = httpx.Client(transport=_transport(calls))
    r = V.valuate(prof(), client=client)
    assert r["fuente"] == "tavily" and r["simulado"] is False
    assert len(r["comparables"]) == 4  # el anuncio sin precio se descarta
    assert all(c["origen"] == "firecrawl" for c in r["comparables"])
    assert r["precio_estimado"] == pytest.approx(211_500)
    assert calls[0].headers["authorization"] == "Bearer tvly-secreta"
    files = list((tmp_path / "cache").glob("*.json"))
    assert len(files) == 1
    assert "secreta" not in files[0].read_text()  # nunca se guarda la llave

    # segunda llamada: sale de caché, sin tocar la red
    n = len(calls)
    r2 = V.valuate(prof(kilometraje=80_000), client=client)
    assert r2["fuente"] == "cache" and len(calls) == n
    assert r2["precio_estimado"] == r["precio_estimado"]
    assert r2["simulado"] is False


def test_firecrawl_failure_falls_back_to_snippet(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "k2")
    r = V.valuate(prof(), client=httpx.Client(transport=_transport([], firecrawl_ok=False)))
    assert r["fuente"] == "tavily"
    assert {c["origen"] for c in r["comparables"]} == {"tavily_snippet"}
    assert sorted(c["precio"] for c in r["comparables"]) == [200_000, 210_000, 220_000, 230_000]


def test_tavily_only_without_firecrawl_key(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    calls: list[httpx.Request] = []
    r = V.valuate(prof(), client=httpx.Client(transport=_transport(calls)))
    assert r["fuente"] == "tavily"
    assert all(req.url.host == "api.tavily.com" for req in calls)


def test_network_error_falls_back_to_mock(monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-secreta")
    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(503)))
    with caplog.at_level("DEBUG"):
        r = V.valuate(prof(), client=client)
    assert r["fuente"] == "mock"
    assert "tvly-secreta" not in caplog.text
    assert not list((tmp_path / "cache").glob("*.json"))


def test_offline_flag_and_use_network_false(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    boom = httpx.Client(transport=httpx.MockTransport(lambda req: (_ for _ in ()).throw(AssertionError)))
    monkeypatch.setenv("VALUACION_OFFLINE", "1")
    assert V.valuate(prof(), client=boom)["fuente"] == "mock"
    monkeypatch.delenv("VALUACION_OFFLINE")
    assert V.valuate(prof(), client=boom, use_network=False)["fuente"] == "mock"


def test_cache_key_normalizes_and_corrupt_cache_ignored(tmp_path):
    assert V.cache_key(prof(marca=" NISSAN ", modelo="versa")) == V.cache_key(prof())
    d = tmp_path / "cache"
    d.mkdir()
    (d / f"{V.cache_key(prof())}.json").write_text("{no json")
    assert V.valuate(prof())["fuente"] == "mock"


def test_parse_snippet():
    assert V.parse_snippet("Precio $185,500 MXN, 92,000 km") == {"precio": 185_500.0, "kilometraje": 92_000}
    assert V.parse_snippet("Precio $1,000") == {}
    assert V.parse_snippet("") == {}


def test_shipped_cache_samples_are_simulated_and_valid():
    files = list(V.DEFAULT_CACHE_DIR.glob("*.json"))
    assert files, "debe existir al menos un ejemplo SIMULADO en data/cache/comparables"
    for f in files:
        data = json.loads(f.read_text())
        assert "SIMULADO" in data.get("nota", "")
        p = prof(marca=data["marca"], modelo=data["modelo"], anio=data["anio"])
        assert f.stem == V.cache_key(p)
        r = V.valuate(p, cache_dir=V.DEFAULT_CACHE_DIR)
        assert r["fuente"] == "cache" and r["precio_estimado"] > 0
        assert r["simulado"] is True


def test_mixed_cached_comparables_keep_simulated_label(tmp_path):
    comps = [{"precio": 200_000, "origen": "tavily_snippet"},
             {"precio": 210_000, "origen": "mock"}]
    V.save_cache(prof(), comps, tmp_path)
    assert V.valuate(prof(), cache_dir=tmp_path)["simulado"] is True
