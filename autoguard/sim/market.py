"""Simulador de mercado con riesgo OCULTO. Todos los datos son SIMULADOS.

Diseño:
- `sample_batch` genera una población sintética de autos del mercado mexicano (marca/modelo realistas,
  año 1985–2026, km correlacionado con la antigüedad, siniestros previos, uso, zona, daños).
- El costo esperado real = BASE × Π factores reales × interacciones. Los factores reales difieren a
  propósito de `configs/agents/cotizador.yaml` para que el RSI tenga algo que descubrir:
    (a) factores mal calibrados (p.ej. app_transporte real 1.45 vs 1.15; siniestros 1.30/1.65),
    (b) interacciones (autos con ≥30 años y exactamente 1 siniestro cuestan MENOS: ×0.65;
        app_transporte en CDMX cuesta más: ×1.30; comercial con ≥200k km: ×1.15),
    (c) variables que el cotizador base no usa (`marca` y `danos_costo`).
- `resolve` añade ruido lognormal (σ=0.20, media 1) por vehículo. El ruido se deriva de un hash
  estable de (seed, vehicle_id): es determinístico y NO depende de las primas ni del orden del lote.
- Demanda: disposición a pagar = costo esperado × WTP_MARKUP × lognormal(σ=0.25); compra si prima < dap.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.special import ndtri

from autoguard.contracts import VEHICLE_COLUMNS
from autoguard.segments import ANIO_REFERENCIA

ANIO_MIN = 1985

# ---------------------------------------------------------------- población (SIMULADA)
# (marca, modelo, peso relativo)
_CATALOGO: list[tuple[str, str, float]] = [
    ("Nissan", "Versa", 8), ("Nissan", "Sentra", 6), ("Nissan", "March", 5), ("Nissan", "Tsuru", 4),
    ("Nissan", "NP300", 3),
    ("Volkswagen", "Jetta", 6), ("Volkswagen", "Vento", 4), ("Volkswagen", "Sedan", 2),
    ("Volkswagen", "Tiguan", 2),
    ("Chevrolet", "Aveo", 7), ("Chevrolet", "Spark", 3), ("Chevrolet", "Chevy", 3), ("Chevrolet", "Tornado", 2),
    ("Toyota", "Corolla", 4), ("Toyota", "Yaris", 3), ("Toyota", "Hilux", 2), ("Toyota", "RAV4", 2),
    ("Honda", "Civic", 3), ("Honda", "CR-V", 3), ("Honda", "City", 2),
    ("Mazda", "Mazda 3", 3), ("Mazda", "CX-5", 2),
    ("Kia", "Rio", 3), ("Kia", "Seltos", 2), ("Kia", "Forte", 2),
    ("Ford", "Lobo", 2), ("Ford", "Ranger", 2), ("Ford", "Figo", 2), ("Ford", "Focus", 1),
    ("Hyundai", "Grand i10", 2), ("Hyundai", "Accent", 2),
    ("BMW", "Serie 3", 1), ("Audi", "A3", 1), ("Mercedes-Benz", "Clase C", 1),
]
_MARCAS = np.array([m for m, _, _ in _CATALOGO])
_MODELOS = np.array([mo for _, mo, _ in _CATALOGO])
_P_CATALOGO = np.array([w for _, _, w in _CATALOGO], dtype=float)
_P_CATALOGO /= _P_CATALOGO.sum()

_USOS = np.array(["particular", "app_transporte", "comercial"])
_P_USOS = np.array([0.74, 0.16, 0.10])
_ZONAS = np.array(["CDMX", "EDOMEX", "JAL", "NL", "PUE", "OTRA"])
_P_ZONAS = np.array([0.28, 0.20, 0.15, 0.15, 0.08, 0.14])

# ---------------------------------------------------------------- riesgo OCULTO (no exportar)
_BASE_REAL = 7600.0
_ANT_BINS = np.array([0, 5, 10, 20, 30])
_ANT_VALS = np.array([0.92, 1.00, 1.12, 1.30, 1.15])
_KM_BINS = np.array([0, 50_000, 100_000, 200_000])
_KM_VALS = np.array([0.93, 1.00, 1.10, 1.28])
_SIN_BINS = np.array([0, 1, 2])
_SIN_VALS = np.array([1.00, 1.30, 1.65])
_USO_REAL = {"particular": 1.00, "app_transporte": 1.45, "comercial": 1.25}
_ZONA_REAL = {"CDMX": 1.15, "EDOMEX": 1.25, "JAL": 1.00, "NL": 0.95, "PUE": 0.90, "OTRA": 0.85}
_MARCA_REAL = {
    "BMW": 1.40, "Audi": 1.40, "Mercedes-Benz": 1.40,
    "Toyota": 0.90, "Honda": 0.92, "Mazda": 0.92,
}  # resto 1.0
_DANOS_ESCALA = 40_000.0  # +1 por cada 40k MXN de daño preexistente…
_DANOS_TOPE = 1.5  # …hasta ×1.5

_SIGMA_COSTO = 0.20
_SIGMA_DAP = 0.25
WTP_MARKUP = 1.10

_MASK64 = np.uint64(0xFFFFFFFFFFFFFFFF)


def _splitmix64(x: np.ndarray) -> np.ndarray:
    """Hash entero vectorizado (aritmética uint64 con overflow modular)."""
    with np.errstate(over="ignore"):
        z = (x + np.uint64(0x9E3779B97F4A7C15)) & _MASK64
        z = ((z ^ (z >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)) & _MASK64
        z = ((z ^ (z >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)) & _MASK64
        return z ^ (z >> np.uint64(31))


def _bin_lookup(x: np.ndarray, bins: np.ndarray, vals: np.ndarray) -> np.ndarray:
    idx = np.searchsorted(bins, x, side="right") - 1
    return vals[np.clip(idx, 0, len(vals) - 1)]


class MarketSimulator:
    """Población sintética + riesgo OCULTO + demanda + siniestros, con semilla fija. Datos SIMULADOS.

    Los factores reales del riesgo nunca se exponen fuera de este módulo (salvo `oracle_expected_cost`,
    que solo el evaluador/benchmark puede usar).
    """

    def __init__(self, seed: int = 42):
        self.seed = seed
        self._rng = np.random.default_rng(seed)
        self._counter = 0

    # ------------------------------------------------------------ población
    def sample_batch(self, n: int) -> pd.DataFrame:
        """Devuelve n autos con columnas autoguard.contracts.VEHICLE_COLUMNS. Misma semilla => misma secuencia."""
        rng = self._rng
        n = int(n)

        cat = rng.choice(len(_CATALOGO), size=n, p=_P_CATALOGO)
        # antigüedad: mayoría de autos recientes + cola de clásicos (25–41 años)
        clasico = rng.random(n) < 0.12
        ant = np.where(
            clasico,
            rng.integers(25, ANIO_REFERENCIA - ANIO_MIN + 1, size=n),
            np.minimum(np.floor(rng.exponential(8.0, size=n)), 24),
        ).astype(int)
        anio = ANIO_REFERENCIA - ant

        uso = rng.choice(len(_USOS), size=n, p=_P_USOS)
        zona = rng.choice(len(_ZONAS), size=n, p=_P_ZONAS)

        # km correlacionado con antigüedad; uso intensivo recorre más
        km_anual = 12_000 * rng.lognormal(0.0, 0.35, size=n) * np.array([1.0, 2.2, 1.7])[uso]
        km = np.maximum(ant, 0.3) * km_anual
        km = np.minimum(km, 600_000).astype(int)

        siniestros = np.minimum(rng.poisson(0.18 + 0.015 * ant + 0.15 * (uso > 0)), 5).astype(int)

        con_dano = rng.random(n) < 0.35
        danos = np.where(con_dano, rng.lognormal(np.log(7_000), 0.8, size=n), 0.0).round(0)

        cobertura = rng.beta(8, 2, size=n).round(3)

        ids = [f"SIM-{self.seed}-{i:07d}" for i in range(self._counter, self._counter + n)]
        self._counter += n

        df = pd.DataFrame({
            "vehicle_id": ids,
            "marca": _MARCAS[cat],
            "modelo": _MODELOS[cat],
            "anio": anio,
            "kilometraje": km,
            "siniestros_previos": siniestros,
            "uso": _USOS[uso],
            "zona": _ZONAS[zona],
            "danos_costo": danos,
            "cobertura_verificacion": cobertura,
        })
        return df[VEHICLE_COLUMNS]

    # ------------------------------------------------------------ riesgo oculto
    def oracle_expected_cost(self, batch: pd.DataFrame) -> np.ndarray:
        """Costo esperado real (sin ruido). SOLO para benchmark/tests, nunca para agentes."""
        ant = (ANIO_REFERENCIA - batch["anio"].to_numpy()).astype(float)
        km = batch["kilometraje"].to_numpy().astype(float)
        sin = batch["siniestros_previos"].to_numpy().astype(float)
        uso = batch["uso"].to_numpy()
        zona = batch["zona"].to_numpy()
        marca = batch["marca"].to_numpy()
        danos = batch["danos_costo"].to_numpy().astype(float) if "danos_costo" in batch else np.zeros(len(batch))

        f = np.full(len(batch), _BASE_REAL)
        f *= _bin_lookup(ant, _ANT_BINS, _ANT_VALS)
        f *= _bin_lookup(km, _KM_BINS, _KM_VALS)
        f *= _bin_lookup(sin, _SIN_BINS, _SIN_VALS)
        f *= pd.Series(uso).map(_USO_REAL).fillna(1.0).to_numpy()
        f *= pd.Series(zona).map(_ZONA_REAL).fillna(1.0).to_numpy()
        f *= pd.Series(marca).map(_MARCA_REAL).fillna(1.0).to_numpy()
        f *= np.minimum(1.0 + danos / _DANOS_ESCALA, _DANOS_TOPE)
        # interacciones
        f *= np.where((ant >= 30) & (sin == 1), 0.65, 1.0)
        f *= np.where((uso == "app_transporte") & (zona == "CDMX"), 1.30, 1.0)
        f *= np.where((uso == "comercial") & (km >= 200_000), 1.15, 1.0)
        return f

    def _uniforms(self, batch: pd.DataFrame, stream: int) -> np.ndarray:
        """Uniformes (0,1) determinísticas por (seed, vehicle_id, stream)."""
        h = pd.util.hash_pandas_object(batch["vehicle_id"].astype(str), index=False).to_numpy().astype(np.uint64)
        key = _splitmix64(np.array([self.seed & 0xFFFFFFFFFFFFFFFF], dtype=np.uint64))[0]
        with np.errstate(over="ignore"):
            x = _splitmix64(h ^ key ^ _splitmix64(np.array([stream], dtype=np.uint64))[0])
        return ((x >> np.uint64(11)).astype(np.float64) + 0.5) / float(1 << 53)

    def resolve(self, batch: pd.DataFrame, primas: np.ndarray) -> pd.DataFrame:
        """Resuelve ventas y siniestros. Devuelve DataFrame alineado con columnas
        ["vehicle_id", "vendida" (bool), "costo_real" (float, MXN anual realizado)].
        `costo_real` se genera para TODOS los autos (el benchmark lo usa); el RSI solo ve los vendidos.
        Determinístico dado (seed, batch) e independiente de `primas` (salvo `vendida`)."""
        primas = np.asarray(primas, dtype=float)
        if primas.shape != (len(batch),):
            raise ValueError(f"primas debe tener forma ({len(batch)},), recibido {primas.shape}")
        esperado = self.oracle_expected_cost(batch)

        z_costo = ndtri(self._uniforms(batch, 1))
        costo_real = esperado * np.exp(_SIGMA_COSTO * z_costo - 0.5 * _SIGMA_COSTO**2)

        z_dap = ndtri(self._uniforms(batch, 2))
        dap = esperado * WTP_MARKUP * np.exp(_SIGMA_DAP * z_dap - 0.5 * _SIGMA_DAP**2)
        vendida = primas < dap

        return pd.DataFrame({
            "vehicle_id": batch["vehicle_id"].to_numpy(),
            "vendida": vendida.astype(bool),
            "costo_real": costo_real.round(2),
        })
