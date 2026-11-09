"""Agente documental. [STUB — tarea T-05]"""
from __future__ import annotations

from autoguard.contracts import Alerta, DocExtraction, TipoDocumento, VehicleProfile


def extract(content: bytes, tipo: TipoDocumento, documento_id: str, mime: str = "application/pdf") -> DocExtraction:
    """LLM multimodal extrae VIN, placas, marca, modelo, año y vigencia (con fallback mock)."""
    raise NotImplementedError


def cross_check(extractions: list[DocExtraction]) -> list[Alerta]:
    """Reglas DETERMINÍSTICAS: VIN (normalizado, 17 chars, dígito verificador), placas, marca/modelo/año
    coinciden entre documentos; vigencias no vencidas."""
    raise NotImplementedError


def build_profile(vehicle_id: str, extractions: list[DocExtraction], extra: dict | None = None) -> VehicleProfile:
    """Consolida un VehicleProfile con alertas y cobertura_verificacion (fracción de campos verificados)."""
    raise NotImplementedError
