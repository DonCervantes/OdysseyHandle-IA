"""Dictamen preliminar de siniestros (RF-15). Datos SIMULADOS.

Compara daños detectados en fotos del siniestro (`visual.inspect`) contra el perfil
registrado (daños preexistentes) y genera banderas antifraude determinísticas.
"""
from __future__ import annotations

from typing import Any, Iterable, Literal, Optional

from pydantic import BaseModel, Field

from autoguard.agents import visual
from autoguard.contracts import Alerta, Dano, VehicleProfile

SeveridadDictamen = Literal["limpio", "revision", "sospechoso"]

# Umbral: si el costo reclamado supera N× la suma tipica de los tipos detectados → atípico.
_MONTO_ATIPICO_FACTOR = 2.5
# Tolerancia de tipo: mismo zona con tipo más leve registrado cuenta como preexistente.
_TIPO_SEVERIDAD = {
    "rayon": 1,
    "abolladura": 2,
    "estrellado": 3,
    "reparacion": 3,
    "reemplazo": 4,
}


class DictamenResult(BaseModel):
    """Salida explicable del dictamen preliminar. SIMULADO."""

    vehicle_id: str
    danos_reclamados: list[Dano]
    danos_preexistentes: list[Dano]
    danos_nuevos: list[Dano]
    costo_siniestro_est: float = Field(ge=0)
    costo_preexistente_coincidente: float = Field(ge=0)
    banderas: list[Alerta] = []
    severidad: SeveridadDictamen = "limpio"
    explicacion: list[str] = []
    simulados: bool = True


def _norm(s: str) -> str:
    return str(s or "").strip().lower().replace(" ", "_").replace("-", "_")


def _key(d: Dano) -> tuple[str, str]:
    return _norm(d.zona), _norm(d.tipo)


def _sev(tipo: str) -> int:
    return _TIPO_SEVERIDAD.get(_norm(tipo), 2)


def _preexistente_cubre(registrado: Dano, reclamado: Dano) -> bool:
    """True si el daño del perfil ya cubre (misma zona, severidad ≥) el reclamado."""
    if _norm(registrado.zona) != _norm(reclamado.zona):
        return False
    return _sev(registrado.tipo) >= _sev(reclamado.tipo)


def _clasificar(
    registrados: list[Dano], reclamados: list[Dano]
) -> tuple[list[Dano], list[Dano]]:
    pre, nuevos = [], []
    for rec in reclamados:
        if any(_preexistente_cubre(reg, rec) for reg in registrados):
            pre.append(rec)
        else:
            nuevos.append(rec)
    return pre, nuevos


def _zonas_relato(relato_zonas: Optional[Iterable[str]]) -> set[str]:
    return {_norm(z) for z in (relato_zonas or []) if str(z).strip()}


def _banderas(
    pre: list[Dano],
    nuevos: list[Dano],
    reclamados: list[Dano],
    relato_zonas: set[str],
    monto_declarado: Optional[float],
) -> list[Alerta]:
    out: list[Alerta] = []
    for d in pre:
        out.append(
            Alerta(
                codigo="DANO_PREEXISTENTE_RECLAMADO",
                severidad="alta",
                detalle=(
                    f"La zona '{d.zona}' ({d.tipo}) ya figuraba en el expediente registrado; "
                    "posible montachoques / daño preexistente reclamado."
                ),
                fuentes=["perfil.danos", "visual.inspect"],
            )
        )

    detectadas = {_norm(d.zona) for d in reclamados}
    if relato_zonas and detectadas and relato_zonas.isdisjoint(detectadas):
        out.append(
            Alerta(
                codigo="ZONA_INCOMPATIBLE",
                severidad="alta",
                detalle=(
                    f"El relato indica zonas {sorted(relato_zonas)} pero las fotos muestran "
                    f"{sorted(detectadas)}."
                ),
                fuentes=["relato", "visual.inspect"],
            )
        )

    costo_tabla = float(sum(d.costo_est for d in reclamados))
    if monto_declarado is not None and costo_tabla > 0 and monto_declarado > _MONTO_ATIPICO_FACTOR * costo_tabla:
        out.append(
            Alerta(
                codigo="MONTO_ATIPICO",
                severidad="media",
                detalle=(
                    f"Monto declarado {monto_declarado:.0f} MXN supera "
                    f"{_MONTO_ATIPICO_FACTOR}× el costo tipico de tabla ({costo_tabla:.0f} MXN)."
                ),
                fuentes=["relato.monto", "data/costos_reparacion.yaml"],
            )
        )

    if not reclamados:
        out.append(
            Alerta(
                codigo="SIN_DANOS_DETECTADOS",
                severidad="media",
                detalle="No se detectaron daños en las fotos del siniestro.",
                fuentes=["visual.inspect"],
            )
        )
    elif not nuevos and pre:
        out.append(
            Alerta(
                codigo="SOLO_PREEXISTENTES",
                severidad="alta",
                detalle="Todo el daño reclamado ya estaba registrado en el perfil.",
                fuentes=["perfil.danos", "visual.inspect"],
            )
        )
    return out


def _severidad(banderas: list[Alerta]) -> SeveridadDictamen:
    if any(b.severidad == "alta" for b in banderas):
        return "sospechoso"
    if banderas:
        return "revision"
    return "limpio"


def dictaminar(
    perfil: VehicleProfile,
    *,
    fotos: Optional[list[bytes]] = None,
    hints: Optional[list[str]] = None,
    danos_reclamados: Optional[list[Dano]] = None,
    relato_zonas: Optional[list[str]] = None,
    monto_declarado: Optional[float] = None,
) -> DictamenResult:
    """Emite dictamen preliminar. Prefiere `danos_reclamados` si se pasan; si no, inspecciona fotos."""
    if danos_reclamados is None:
        if not fotos:
            raise ValueError("se requieren fotos del siniestro o danos_reclamados")
        danos_reclamados = visual.inspect(fotos, hints=hints)

    registrados = list(perfil.danos or [])
    pre, nuevos = _clasificar(registrados, danos_reclamados)
    banderas = _banderas(pre, nuevos, danos_reclamados, _zonas_relato(relato_zonas), monto_declarado)
    costo_nuevos = float(sum(d.costo_est for d in nuevos))
    costo_pre = float(sum(d.costo_est for d in pre))
    explicacion = [
        f"Perfil {perfil.id}: {len(registrados)} daño(s) preexistente(s) registrados.",
        f"Reclamados detectados: {len(danos_reclamados)}; nuevos={len(nuevos)}; preexistentes={len(pre)}.",
        f"Costo estimado del siniestro (solo nuevos): {costo_nuevos:.0f} MXN SIMULADOS.",
    ]
    for b in banderas:
        explicacion.append(f"[{b.codigo}] {b.detalle}")

    return DictamenResult(
        vehicle_id=perfil.id,
        danos_reclamados=danos_reclamados,
        danos_preexistentes=pre,
        danos_nuevos=nuevos,
        costo_siniestro_est=costo_nuevos,
        costo_preexistente_coincidente=costo_pre,
        banderas=banderas,
        severidad=_severidad(banderas),
        explicacion=explicacion,
        simulados=True,
    )


def dictaminar_desde_hints(
    perfil: VehicleProfile,
    foto_hints: list[str],
    **kwargs: Any,
) -> DictamenResult:
    """Atajo para tests/demo: inspecciona con hints mock sin bytes reales."""
    fotos = [b"SIMULADO"] * len(foto_hints)
    return dictaminar(perfil, fotos=fotos, hints=foto_hints, **kwargs)
