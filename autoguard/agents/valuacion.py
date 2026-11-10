"""Valuación con comparables. [T-17] Único módulo que puede usar Tavily/Firecrawl.

Orden de fuentes:
1. Caché en disco (`data/cache/comparables/<hash>.json`, o `VALUACION_CACHE_DIR`) por marca/modelo/año.
2. Red (solo si hay `TAVILY_API_KEY`): Tavily busca anuncios; Firecrawl (si hay `FIRECRAWL_API_KEY`)
   estructura cada anuncio en precio/año/km; si no, se extrae el precio del snippet con regex.
   El resultado se guarda SIEMPRE en caché (presupuesto de búsquedas limitado).
3. Mock: comparables SIMULADOS determinísticos (semilla = hash del vehículo). Se usa sin llaves o si la
   red falla. Nunca se escriben a caché.

Estimación: cada comparable se ajusta al año y km del auto (depreciación por año y por 10k km), se
descartan atípicos con MAD, se toma la mediana y se descuenta el costo de daños detectados.
Las llaves solo se leen de variables de entorno y nunca se registran.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np

from autoguard.contracts import VehicleProfile

log = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "comparables"
TAVILY_URL = "https://api.tavily.com/search"
FIRECRAWL_URL = "https://api.firecrawl.dev/v1/scrape"

AJUSTE_POR_ANIO = 0.06  # +6% por cada año más nuevo que el comparable
AJUSTE_POR_10K_KM = 0.012  # -1.2% por cada 10 000 km más que el comparable
AJUSTE_MAX = 0.40  # tope del ajuste total por comparable (±40%)
MAD_K = 3.0  # atípico si |x - mediana| > MAD_K * 1.4826 * MAD
MIN_PRECIO, MAX_PRECIO = 15_000, 5_000_000
MAX_RESULTADOS = 8

# Precio aproximado de un auto nuevo por marca (MXN, SIMULADO, solo para el mock).
PRECIO_NUEVO_MARCA = {
    "nissan": 380_000, "chevrolet": 360_000, "volkswagen": 420_000, "toyota": 480_000,
    "honda": 470_000, "mazda": 460_000, "kia": 400_000, "hyundai": 390_000, "ford": 450_000,
    "seat": 410_000, "renault": 330_000, "suzuki": 320_000, "mitsubishi": 430_000,
    "bmw": 950_000, "mercedes-benz": 1_000_000, "audi": 900_000, "jeep": 620_000,
    "dodge": 560_000, "ram": 700_000, "mg": 350_000,
}
PRECIO_NUEVO_DEFAULT = 420_000

FIRECRAWL_SCHEMA = {
    "type": "object",
    "properties": {
        "precio": {"type": "number", "description": "Precio de venta en MXN"},
        "anio": {"type": "integer"},
        "kilometraje": {"type": "integer"},
        "titulo": {"type": "string"},
    },
    "required": ["precio"],
}


# ------------------------------------------------------------------ utilidades
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.strip().lower())


def cache_key(profile: VehicleProfile) -> str:
    raw = f"{_norm(profile.marca)}|{_norm(profile.modelo)}|{int(profile.anio)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _cache_dir(cache_dir: Optional[str | Path]) -> Path:
    return Path(cache_dir or os.getenv("VALUACION_CACHE_DIR") or DEFAULT_CACHE_DIR)


def load_cache(profile: VehicleProfile, cache_dir: Optional[str | Path] = None) -> Optional[list[dict]]:
    path = _cache_dir(cache_dir) / f"{cache_key(profile)}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        comps = data.get("comparables") or []
        return comps or None
    except (OSError, ValueError):
        log.warning("caché de comparables corrupta: %s", path.name)
        return None


def save_cache(profile: VehicleProfile, comparables: list[dict], cache_dir: Optional[str | Path] = None,
               query: str = "") -> None:
    d = _cache_dir(cache_dir)
    try:
        d.mkdir(parents=True, exist_ok=True)
        payload = {
            "marca": profile.marca, "modelo": profile.modelo, "anio": profile.anio, "query": query,
            "guardado": datetime.now(timezone.utc).isoformat(), "comparables": comparables,
        }
        (d / f"{cache_key(profile)}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    except OSError as e:  # la caché nunca debe romper la valuación
        log.warning("no se pudo escribir caché de comparables: %s", type(e).__name__)


_PRECIO_RE = re.compile(r"\$\s?([0-9]{2,3}(?:[,\.][0-9]{3})+|[0-9]{5,7})")
_KM_RE = re.compile(r"([0-9]{1,3}(?:[,\.][0-9]{3})+|[0-9]{3,6})\s?(?:km|kms|kilómetros|kilometros)\b", re.I)


def _parse_int(s: str) -> int:
    return int(re.sub(r"[^0-9]", "", s))


def parse_snippet(text: str) -> dict[str, Any]:
    """Extrae precio y km de un snippet de anuncio (respaldo sin Firecrawl)."""
    out: dict[str, Any] = {}
    precios = [_parse_int(m) for m in _PRECIO_RE.findall(text or "")]
    precios = [p for p in precios if MIN_PRECIO <= p <= MAX_PRECIO]
    if precios:
        out["precio"] = float(precios[0])
    kms = [_parse_int(m) for m in _KM_RE.findall(text or "")]
    if kms:
        out["kilometraje"] = kms[0]
    return out


# ------------------------------------------------------------------ red (Tavily + Firecrawl)
def _query(profile: VehicleProfile) -> str:
    return f"{profile.marca} {profile.modelo} {profile.anio} precio venta seminuevo México"


def fetch_comparables(profile: VehicleProfile, client: Any) -> list[dict]:
    """Busca anuncios con Tavily y los estructura con Firecrawl. `client` es un httpx.Client."""
    tavily_key = os.environ["TAVILY_API_KEY"]
    fire_key = os.getenv("FIRECRAWL_API_KEY")
    r = client.post(
        TAVILY_URL,
        headers={"Authorization": f"Bearer {tavily_key}"},
        json={"query": _query(profile), "max_results": MAX_RESULTADOS, "search_depth": "basic"},
    )
    r.raise_for_status()
    comps: list[dict] = []
    for res in (r.json().get("results") or [])[:MAX_RESULTADOS]:
        url = res.get("url", "")
        item: dict[str, Any] = {}
        if fire_key and url:
            try:
                fr = client.post(
                    FIRECRAWL_URL,
                    headers={"Authorization": f"Bearer {fire_key}"},
                    json={"url": url, "formats": ["json"], "jsonOptions": {"schema": FIRECRAWL_SCHEMA}},
                )
                fr.raise_for_status()
                item = dict(((fr.json().get("data") or {}).get("json")) or {})
            except Exception as e:  # noqa: BLE001 - un anuncio fallido no invalida la búsqueda
                log.info("firecrawl falló para un anuncio: %s", type(e).__name__)
                item = {}
        via_firecrawl = bool(item.get("precio"))
        if not via_firecrawl:
            item = {**parse_snippet(res.get("content", "")), **{k: v for k, v in item.items() if v}}
        try:
            precio = float(item.get("precio") or 0)
        except (TypeError, ValueError):
            continue
        if not (MIN_PRECIO <= precio <= MAX_PRECIO):
            continue
        comps.append({
            "titulo": item.get("titulo") or res.get("title", ""),
            "url": url,
            "precio": precio,
            "anio": int(item.get("anio") or profile.anio),
            "kilometraje": int(item["kilometraje"]) if item.get("kilometraje") else None,
            "origen": "firecrawl" if via_firecrawl else "tavily_snippet",
        })
    return comps


# ------------------------------------------------------------------ mock SIMULADO
def mock_comparables(profile: VehicleProfile, n: int = MAX_RESULTADOS) -> list[dict]:
    """Comparables SIMULADOS determinísticos para el vehículo (sin red)."""
    seed = int(cache_key(profile), 16) % (2**32)
    rng = np.random.default_rng(seed)
    nuevo = PRECIO_NUEVO_MARCA.get(_norm(profile.marca), PRECIO_NUEVO_DEFAULT)
    comps = []
    for i in range(n):
        anio = int(profile.anio + rng.integers(-1, 2))
        edad = max(0, 2026 - anio)
        km = int(max(0, rng.normal(15_000 * max(edad, 0.5), 6_000)))
        valor = nuevo * max(0.12, 0.88 ** edad) * (1 - AJUSTE_POR_10K_KM * km / 10_000 * 0.5)
        precio = float(round(valor * rng.lognormal(0, 0.08), -2))
        comps.append({
            "titulo": f"SIMULADO {profile.marca} {profile.modelo} {anio}",
            "url": f"https://simulado.local/anuncio/{cache_key(profile)}-{i}",
            "precio": max(float(MIN_PRECIO), precio),
            "anio": anio,
            "kilometraje": km,
            "origen": "mock",
        })
    return comps


# ------------------------------------------------------------------ estimación
def adjust_price(comp: dict, profile: VehicleProfile) -> float:
    """Lleva el precio del comparable al año y km del auto valuado."""
    adj = AJUSTE_POR_ANIO * (profile.anio - int(comp.get("anio") or profile.anio))
    km = comp.get("kilometraje")
    if km is not None:
        adj -= AJUSTE_POR_10K_KM * (profile.kilometraje - float(km)) / 10_000
    adj = float(np.clip(adj, -AJUSTE_MAX, AJUSTE_MAX))
    return float(comp["precio"]) * (1 + adj)


def robust_estimate(precios: list[float]) -> tuple[float, float, float, np.ndarray]:
    """(mediana, lo, hi, máscara de inliers) con filtro MAD."""
    x = np.asarray(precios, dtype=float)
    med = float(np.median(x))
    mad = float(np.median(np.abs(x - med)))
    if mad > 0:
        mask = np.abs(x - med) <= MAD_K * 1.4826 * mad
    else:
        mask = np.ones(len(x), dtype=bool)
    xi = x[mask]
    med = float(np.median(xi))
    lo, hi = (float(np.percentile(xi, 25)), float(np.percentile(xi, 75))) if len(xi) > 1 else (med, med)
    return med, lo, hi, mask


def estimate(profile: VehicleProfile, comparables: list[dict], fuente: str) -> dict:
    comps = [dict(c) for c in comparables if c.get("precio")]
    if not comps:
        raise ValueError("sin comparables con precio")
    for c in comps:
        c["precio_ajustado"] = round(adjust_price(c, profile), 2)
    med, lo, hi, mask = robust_estimate([c["precio_ajustado"] for c in comps])
    for c, ok in zip(comps, mask):
        c["atipico"] = not bool(ok)
    danos = float(profile.danos_costo)
    piso = 0.05 * med  # un auto dañado conserva al menos su valor de rescate
    final = lambda v: round(max(piso, v - danos), 2)  # noqa: E731
    return {
        "precio_estimado": final(med),
        "rango": [final(lo), final(hi)],
        "comparables": comps,
        "fuente": fuente,
        "precio_mercado": round(med, 2),
        "descuento_danos": round(danos, 2),
        "n_comparables": int(mask.sum()),
        # La caché es un medio de almacenamiento, no el origen de los anuncios.
        # Una mezcla que contiene datos sintéticos también debe etiquetarse.
        "simulado": fuente == "mock" or any(
            c.get("origen") == "mock" or c.get("simulado") is True
            or "SIMULADO" in str(c.get("titulo", "")).upper()
            for c in comps
        ),
    }


# ------------------------------------------------------------------ API pública
def valuate(
    profile: VehicleProfile,
    *,
    cache_dir: Optional[str | Path] = None,
    client: Any = None,
    use_network: Optional[bool] = None,
) -> dict:
    """Devuelve {"precio_estimado", "rango": [lo, hi], "comparables": [...], "fuente": "cache|tavily|mock"}.

    `client` permite inyectar un httpx.Client (tests). `use_network=None` => usa red solo si hay
    `TAVILY_API_KEY` y `VALUACION_OFFLINE` no está activo.
    """
    cached = load_cache(profile, cache_dir)
    if cached:
        return estimate(profile, cached, "cache")

    if use_network is None:
        use_network = bool(os.getenv("TAVILY_API_KEY")) and os.getenv("VALUACION_OFFLINE", "0") != "1"
    if use_network and os.getenv("TAVILY_API_KEY"):
        own = client is None
        try:
            if own:
                import httpx

                client = httpx.Client(timeout=20.0)
            comps = fetch_comparables(profile, client)
            if comps:
                save_cache(profile, comps, cache_dir, query=_query(profile))
                return estimate(profile, comps, "tavily")
            log.info("búsqueda sin comparables válidos; se usa mock")
        except Exception as e:  # noqa: BLE001 - la valuación nunca rompe el expediente
            log.warning("valuación por red falló (%s); se usa mock", type(e).__name__)
        finally:
            if own and client is not None:
                client.close()

    return estimate(profile, mock_comparables(profile), "mock")


if __name__ == "__main__":  # pragma: no cover
    p = VehicleProfile(id="demo", marca="Nissan", modelo="Versa", anio=2019, kilometraje=80_000,
                       siniestros_previos=0)
    print(json.dumps(valuate(p), ensure_ascii=False, indent=2))
