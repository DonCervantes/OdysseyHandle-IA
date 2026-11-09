"""Modelos SQLAlchemy 2.0 de las 8 tablas del TRD.

vehicles, documents, predictions, outcomes, errors, agent_versions, patches, meta_strategy.
Los tipos JSON se mapean a JSON en SQLite y a JSONB en Postgres (ver db/migrations/001_init.sql).
Todos los datos de la demo son SIMULADOS.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from autoguard.contracts import utcnow

JSONType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class VehicleRow(Base):
    __tablename__ = "vehicles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    perfil_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DocumentRow(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    vehicle_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    tipo: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_url: Mapped[Optional[str]] = mapped_column(Text)
    extracted_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PredictionRow(Base):
    __tablename__ = "predictions"

    # Sin FK a vehicles: el simulador genera cotizaciones de autos que no se persisten como perfil.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    vehicle_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    agent: Mapped[str] = mapped_column(String(32), nullable=False, default="cotizador")
    agent_version: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    prima: Mapped[float] = mapped_column(Float, nullable=False)  # desnormalizado para consultas rápidas
    output_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OutcomeRow(Base):
    __tablename__ = "outcomes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    prediction_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    fuente: Mapped[str] = mapped_column(String(32), nullable=False)
    valor_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ErrorRow(Base):
    __tablename__ = "errors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prediction_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    metrica: Mapped[str] = mapped_column(String(32), nullable=False)
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    segmento: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentVersionRow(Base):
    __tablename__ = "agent_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    parent_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("agent_versions.id"))
    git_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    estado: Mapped[str] = mapped_column(String(16), nullable=False)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PatchRow(Base):
    __tablename__ = "patches"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    generation: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    agent: Mapped[str] = mapped_column(String(32), nullable=False, default="cotizador")
    tipo: Mapped[str] = mapped_column(String(32), nullable=False)
    nivel: Mapped[str] = mapped_column(String(16), nullable=False)
    hipotesis: Mapped[str] = mapped_column(Text, nullable=False, default="")
    segmento: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    cambios: Mapped[list[Any]] = mapped_column(JSONType, nullable=False, default=list)
    diff: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metrica_objetivo: Mapped[str] = mapped_column(String(64), nullable=False, default="loss_asimetrica")
    veredicto: Mapped[Optional[str]] = mapped_column(String(16), index=True)
    metrics_before: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    metrics_after: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    razon: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MetaStrategyRow(Base):
    __tablename__ = "meta_strategy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    estrategia_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)  # {arms, lecciones}
    tasa_aceptacion: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ganancia_media: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


Index("ix_meta_strategy_generation", MetaStrategyRow.generation)

ALL_TABLES = [
    "vehicles", "documents", "predictions", "outcomes", "errors", "agent_versions", "patches", "meta_strategy",
]
