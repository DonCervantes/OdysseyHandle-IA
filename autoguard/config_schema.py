"""Esquema de la configuración versionada del cotizador (YAML) y aplicación determinística de parches.

El LLM propone `ConfigChange`s; este código los aplica y valida. Un parche que no valida es "invalido"
y se descarta SIN tocar el conjunto reservado.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, model_validator

from autoguard.contracts import VARIABLES_PERMITIDAS, ConfigChange, Patch


class Factor(BaseModel):
    """Factor multiplicativo sobre una variable.
    - Numérico: `bins` (límites inferiores, ascendentes) y `valores` (misma longitud).
    - Categórico: `categorias` {valor: multiplicador}; `default` si no aparece.
    """
    variable: str
    bins: Optional[list[float]] = None
    valores: Optional[list[float]] = None
    categorias: Optional[dict[str, float]] = None
    default: float = 1.0

    @model_validator(mode="after")
    def _check(self):
        numeric = self.bins is not None or self.valores is not None
        if numeric == (self.categorias is not None):
            raise ValueError("Factor debe ser numérico (bins+valores) o categórico (categorias)")
        if numeric:
            if not self.bins or not self.valores or len(self.bins) != len(self.valores):
                raise ValueError("bins y valores deben tener la misma longitud > 0")
            if any(b2 <= b1 for b1, b2 in zip(self.bins, self.bins[1:])):
                raise ValueError("bins deben ser estrictamente ascendentes")
        mults = self.valores or list((self.categorias or {}).values())
        if any(not (0.2 <= m <= 5.0) for m in mults + [self.default]):
            raise ValueError("multiplicadores fuera de [0.2, 5.0]")
        return self


class Regla(BaseModel):
    """Multiplicador adicional para un segmento (ver autoguard/segments.py)."""
    id: str
    segmento: dict[str, Any]
    multiplicador: float = Field(ge=0.2, le=5.0)
    nota: str = ""


class CotizadorConfig(BaseModel):
    agent: str = "cotizador"
    base: float = Field(gt=0, description="Prima base anual MXN")
    factores: dict[str, Factor]
    reglas: list[Regla] = []
    intervalo_rel: float = Field(default=0.12, gt=0, lt=1)
    prompt_estrategia: str = ""  # texto que el cambio_prompt puede reescribir (explicaciones)

    @model_validator(mode="after")
    def _whitelist(self):
        for name, f in self.factores.items():
            if f.variable not in VARIABLES_PERMITIDAS:
                raise ValueError(f"variable no permitida en factor {name}: {f.variable}")
        from autoguard.segments import segment_variables

        for r in self.reglas:
            for v in segment_variables(r.segmento):
                if v not in VARIABLES_PERMITIDAS:
                    raise ValueError(f"variable no permitida en regla {r.id}: {v}")
        ids = [r.id for r in self.reglas]
        if len(ids) != len(set(ids)):
            raise ValueError("ids de reglas duplicados")
        return self


def load_config(path: str | Path) -> CotizadorConfig:
    return CotizadorConfig.model_validate(yaml.safe_load(Path(path).read_text()))


def dump_config(cfg: CotizadorConfig) -> str:
    return yaml.safe_dump(cfg.model_dump(mode="json", exclude_none=True), sort_keys=False, allow_unicode=True)


def _set_path(obj: Any, path: str, value: Any) -> None:
    parts = path.split(".")
    for p in parts[:-1]:
        obj = obj[int(p)] if isinstance(obj, list) else obj.setdefault(p, {})
    last = parts[-1]
    if isinstance(obj, list):
        obj[int(last)] = value
    else:
        obj[last] = value


def apply_changes(cfg: CotizadorConfig, cambios: list[ConfigChange]) -> CotizadorConfig:
    """Aplica cambios y re-valida. Lanza ValueError/ValidationError si el resultado es inválido."""
    data = copy.deepcopy(cfg.model_dump(mode="json"))
    for ch in cambios:
        if ch.op == "set":
            if not ch.path:
                raise ValueError("set requiere path")
            _set_path(data, ch.path, ch.value)
        elif ch.op == "add_rule":
            data.setdefault("reglas", []).append(dict(ch.value))
        elif ch.op == "remove_rule":
            data["reglas"] = [r for r in data.get("reglas", []) if r["id"] != ch.value]
        elif ch.op == "add_factor":
            if ch.path in data["factores"]:
                raise ValueError(f"factor ya existe: {ch.path}")
            data["factores"][ch.path] = dict(ch.value)
    return CotizadorConfig.model_validate(data)


def apply_patch(cfg: CotizadorConfig, patch: Patch) -> CotizadorConfig:
    return apply_changes(cfg, patch.cambios)
