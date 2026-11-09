"""Repositorio: funciones que reciben/devuelven contratos Pydantic (autoguard/contracts.py).

Todas reciben una `Session` como primer argumento. Las funciones de escritura hacen `commit` al final
(simple para la API y el loop); usa `session_scope()` si quieres agrupar varias en una transacción
(el commit interno es idempotente dentro del scope).
Escrituras individuales son upsert por id (`merge`); las masivas (`save_predictions`, `save_outcomes`,
`save_errors`) usan INSERT bulk y asumen ids nuevos.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd
from sqlalchemy import delete, insert, select, update
from sqlalchemy.orm import Session

from autoguard.contracts import (
    VEHICLE_COLUMNS,
    AgentVersion,
    DocExtraction,
    MetaStrategy,
    Outcome,
    Patch,
    Prediction,
    QuoteOutput,
    VehicleProfile,
)
from autoguard.db.models import (
    AgentVersionRow,
    DocumentRow,
    ErrorRow,
    MetaStrategyRow,
    OutcomeRow,
    PatchRow,
    PredictionRow,
    VehicleRow,
)

_BULK_CHUNK = 5000


def _bulk_insert(session: Session, model, rows: list[dict[str, Any]]) -> int:
    for i in range(0, len(rows), _BULK_CHUNK):
        session.execute(insert(model), rows[i : i + _BULK_CHUNK])
    session.commit()
    return len(rows)


# ---------------------------------------------------------------- vehicles
def save_vehicle(session: Session, perfil: VehicleProfile) -> str:
    session.merge(VehicleRow(id=perfil.id, perfil_json=perfil.model_dump(mode="json")))
    session.commit()
    return perfil.id


def save_vehicles(session: Session, perfiles: Iterable[VehicleProfile]) -> int:
    n = 0
    for p in perfiles:
        session.merge(VehicleRow(id=p.id, perfil_json=p.model_dump(mode="json")))
        n += 1
    session.commit()
    return n


def get_vehicle(session: Session, vehicle_id: str) -> Optional[VehicleProfile]:
    row = session.get(VehicleRow, vehicle_id)
    return VehicleProfile.model_validate(row.perfil_json) if row else None


def list_vehicles(session: Session, limit: Optional[int] = None) -> list[VehicleProfile]:
    stmt = select(VehicleRow).order_by(VehicleRow.created_at)
    if limit:
        stmt = stmt.limit(limit)
    return [VehicleProfile.model_validate(r.perfil_json) for r in session.scalars(stmt)]


# ---------------------------------------------------------------- documents
def save_document(
    session: Session, extraction: DocExtraction, vehicle_id: Optional[str] = None,
    storage_url: Optional[str] = None,
) -> str:
    session.merge(DocumentRow(
        id=extraction.documento_id, vehicle_id=vehicle_id, tipo=extraction.tipo, storage_url=storage_url,
        extracted_json=extraction.model_dump(mode="json"),
    ))
    session.commit()
    return extraction.documento_id


def list_documents(session: Session, vehicle_id: Optional[str] = None) -> list[DocExtraction]:
    stmt = select(DocumentRow).order_by(DocumentRow.created_at)
    if vehicle_id is not None:
        stmt = stmt.where(DocumentRow.vehicle_id == vehicle_id)
    return [DocExtraction.model_validate(r.extracted_json) for r in session.scalars(stmt)]


# ---------------------------------------------------------------- predictions
def _prediction_row(p: Prediction) -> dict[str, Any]:
    return {
        "id": p.prediction_id, "vehicle_id": p.vehicle_id, "agent": p.agent,
        "agent_version": p.agent_version, "input_hash": p.input_hash, "prima": float(p.output.prima),
        "output_json": p.output.model_dump(mode="json"), "created_at": p.created_at,
    }


def _row_to_prediction(r: PredictionRow) -> Prediction:
    return Prediction(
        prediction_id=r.id, vehicle_id=r.vehicle_id, agent=r.agent, agent_version=r.agent_version,
        input_hash=r.input_hash, output=QuoteOutput.model_validate(r.output_json), created_at=r.created_at,
    )


def save_prediction(session: Session, pred: Prediction) -> str:
    session.merge(PredictionRow(**_prediction_row(pred)))
    session.commit()
    return pred.prediction_id


def save_predictions(session: Session, preds: Iterable[Prediction]) -> int:
    """INSERT bulk (10k en < 3 s en SQLite). Los ids deben ser nuevos."""
    return _bulk_insert(session, PredictionRow, [_prediction_row(p) for p in preds])


def get_prediction(session: Session, prediction_id: str) -> Optional[Prediction]:
    row = session.get(PredictionRow, prediction_id)
    return _row_to_prediction(row) if row else None


def list_predictions(
    session: Session, vehicle_id: Optional[str] = None, agent_version: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[Prediction]:
    stmt = select(PredictionRow).order_by(PredictionRow.created_at)
    if vehicle_id is not None:
        stmt = stmt.where(PredictionRow.vehicle_id == vehicle_id)
    if agent_version is not None:
        stmt = stmt.where(PredictionRow.agent_version == agent_version)
    if limit:
        stmt = stmt.limit(limit)
    return [_row_to_prediction(r) for r in session.scalars(stmt)]


def predictions_df(session: Session, agent_version: Optional[str] = None) -> pd.DataFrame:
    """DataFrame (prediction_id, vehicle_id, agent, agent_version, input_hash, prima, created_at
    + VEHICLE_COLUMNS[1:]) con las columnas del vehículo tomadas de `vehicles` si existe el perfil
    (NaN si no). Formato de entrada de `rsi.recolector.collect`."""
    stmt = select(
        PredictionRow.id, PredictionRow.vehicle_id, PredictionRow.agent, PredictionRow.agent_version,
        PredictionRow.input_hash, PredictionRow.prima, PredictionRow.created_at,
    ).order_by(PredictionRow.created_at)
    if agent_version is not None:
        stmt = stmt.where(PredictionRow.agent_version == agent_version)
    cols = ["prediction_id", "vehicle_id", "agent", "agent_version", "input_hash", "prima", "created_at"]
    df = pd.DataFrame(session.execute(stmt).all(), columns=cols)
    vcols = [c for c in VEHICLE_COLUMNS if c != "vehicle_id"]
    if df.empty:
        for c in vcols:
            df[c] = pd.Series(dtype=object)
        return df
    ids = df["vehicle_id"].unique().tolist()
    vrows = []
    for i in range(0, len(ids), 900):  # límite de parámetros de SQLite
        for r in session.scalars(select(VehicleRow).where(VehicleRow.id.in_(ids[i : i + 900]))):
            perfil = VehicleProfile.model_validate(r.perfil_json)
            d = {c: getattr(perfil, c) for c in vcols}
            d["vehicle_id"] = r.id
            vrows.append(d)
    vdf = pd.DataFrame(vrows, columns=["vehicle_id", *vcols])
    return df.merge(vdf, on="vehicle_id", how="left")


# ---------------------------------------------------------------- outcomes
def _outcome_row(o: Outcome) -> dict[str, Any]:
    return {
        "id": o.outcome_id, "prediction_id": o.prediction_id, "fuente": o.fuente,
        "valor_json": dict(o.valor), "observed_at": o.observed_at,
    }


def _row_to_outcome(r: OutcomeRow) -> Outcome:
    return Outcome(outcome_id=r.id, prediction_id=r.prediction_id, fuente=r.fuente, valor=r.valor_json,
                   observed_at=r.observed_at)


def save_outcome(session: Session, outcome: Outcome) -> str:
    session.merge(OutcomeRow(**_outcome_row(outcome)))
    session.commit()
    return outcome.outcome_id


def save_outcomes(session: Session, outcomes: Iterable[Outcome]) -> int:
    return _bulk_insert(session, OutcomeRow, [_outcome_row(o) for o in outcomes])


def list_outcomes(session: Session, prediction_id: Optional[str] = None) -> list[Outcome]:
    stmt = select(OutcomeRow).order_by(OutcomeRow.observed_at)
    if prediction_id is not None:
        stmt = stmt.where(OutcomeRow.prediction_id == prediction_id)
    return [_row_to_outcome(r) for r in session.scalars(stmt)]


def outcomes_df(session: Session) -> pd.DataFrame:
    """DataFrame (outcome_id, prediction_id, fuente, observed_at, vendida, costo_real) con las claves
    de `valor` aplanadas como columnas. Formato de entrada de `rsi.recolector.collect`."""
    rows = session.execute(
        select(OutcomeRow.id, OutcomeRow.prediction_id, OutcomeRow.fuente, OutcomeRow.observed_at,
               OutcomeRow.valor_json).order_by(OutcomeRow.observed_at)
    ).all()
    base = pd.DataFrame(
        [(r[0], r[1], r[2], r[3]) for r in rows],
        columns=["outcome_id", "prediction_id", "fuente", "observed_at"],
    )
    valores = pd.DataFrame([r[4] or {} for r in rows])
    for c in ("vendida", "costo_real"):
        if c not in valores.columns:
            valores[c] = pd.Series([None] * len(base), dtype=object)
    return pd.concat([base, valores.reset_index(drop=True)], axis=1)


# ---------------------------------------------------------------- errors
ERROR_METRICS = ("loss", "error_rel")


def save_errors(session: Session, df: pd.DataFrame, metricas: Iterable[str] = ERROR_METRICS,
                segmento: Optional[dict[str, Any]] = None) -> int:
    """Guarda en formato largo (prediction_id, metrica, valor, segmento) cada métrica presente en `df`
    (salida de `rsi.recolector.collect`). Si `df` trae columna `segmento` (dict) se usa por fila;
    si no, el `segmento` dado (o NULL). Valores NaN se omiten."""
    if df.empty:
        return 0
    rows: list[dict[str, Any]] = []
    pids = df["prediction_id"].astype(str).tolist()
    segs = df["segmento"].tolist() if "segmento" in df.columns else [segmento] * len(df)
    for m in metricas:
        if m not in df.columns:
            continue
        vals = pd.to_numeric(df[m], errors="coerce").to_numpy(dtype=float)
        for pid, v, s in zip(pids, vals, segs):
            if np.isfinite(v):
                rows.append({"prediction_id": pid, "metrica": m, "valor": float(v),
                             "segmento": s if isinstance(s, dict) else None})
    return _bulk_insert(session, ErrorRow, rows)


def errors_df(session: Session, metrica: Optional[str] = None) -> pd.DataFrame:
    stmt = select(ErrorRow.prediction_id, ErrorRow.metrica, ErrorRow.valor, ErrorRow.segmento).order_by(ErrorRow.id)
    if metrica is not None:
        stmt = stmt.where(ErrorRow.metrica == metrica)
    return pd.DataFrame(session.execute(stmt).all(), columns=["prediction_id", "metrica", "valor", "segmento"])


# ---------------------------------------------------------------- agent_versions
def _row_to_version(r: AgentVersionRow) -> AgentVersion:
    return AgentVersion(id=r.id, agent=r.agent, parent_id=r.parent_id, git_sha=r.git_sha, estado=r.estado,
                        metrics=r.metrics_json or {}, created_at=r.created_at)


def save_agent_version(session: Session, version: AgentVersion) -> str:
    session.merge(AgentVersionRow(
        id=version.id, agent=version.agent, parent_id=version.parent_id, git_sha=version.git_sha,
        estado=version.estado, metrics_json=dict(version.metrics), created_at=version.created_at,
    ))
    session.commit()
    return version.id


def get_agent_version(session: Session, version_id: str) -> Optional[AgentVersion]:
    row = session.get(AgentVersionRow, version_id)
    return _row_to_version(row) if row else None


def list_agent_versions(session: Session, agent: Optional[str] = None,
                        estado: Optional[str] = None) -> list[AgentVersion]:
    stmt = select(AgentVersionRow).order_by(AgentVersionRow.created_at)
    if agent is not None:
        stmt = stmt.where(AgentVersionRow.agent == agent)
    if estado is not None:
        stmt = stmt.where(AgentVersionRow.estado == estado)
    return [_row_to_version(r) for r in session.scalars(stmt)]


def get_champion(session: Session, agent: str = "cotizador") -> Optional[AgentVersion]:
    vs = list_agent_versions(session, agent=agent, estado="campeon")
    return vs[-1] if vs else None


def set_champion(session: Session, version_id: str) -> AgentVersion:
    """Marca `version_id` como campeón y retira al campeón anterior del mismo agente."""
    row = session.get(AgentVersionRow, version_id)
    if row is None:
        raise KeyError(version_id)
    session.execute(
        update(AgentVersionRow)
        .where(AgentVersionRow.agent == row.agent, AgentVersionRow.estado == "campeon",
               AgentVersionRow.id != version_id)
        .values(estado="retirado")
    )
    row.estado = "campeon"
    session.commit()
    return _row_to_version(row)


# ---------------------------------------------------------------- patches
def _patch_row(p: Patch) -> PatchRow:
    return PatchRow(
        id=p.patch_id, generation=p.generation, agent=p.agent, tipo=p.tipo, nivel=p.nivel,
        hipotesis=p.hipotesis, segmento=dict(p.segmento), cambios=[c.model_dump(mode="json") for c in p.cambios],
        diff=p.diff, metrica_objetivo=p.metrica_objetivo, veredicto=p.veredicto,
        metrics_before=dict(p.metrics_before), metrics_after=dict(p.metrics_after), razon=p.razon,
    )


def _row_to_patch(r: PatchRow) -> Patch:
    return Patch(
        patch_id=r.id, generation=r.generation, agent=r.agent, tipo=r.tipo, nivel=r.nivel,
        hipotesis=r.hipotesis, segmento=r.segmento or {}, cambios=r.cambios or [], diff=r.diff,
        metrica_objetivo=r.metrica_objetivo, veredicto=r.veredicto, metrics_before=r.metrics_before or {},
        metrics_after=r.metrics_after or {}, razon=r.razon,
    )


def save_patch(session: Session, patch: Patch) -> str:
    existing = session.get(PatchRow, patch.patch_id)
    row = _patch_row(patch)
    if existing is not None:
        row.created_at = existing.created_at
    session.merge(row)
    session.commit()
    return patch.patch_id


def get_patch(session: Session, patch_id: str) -> Optional[Patch]:
    row = session.get(PatchRow, patch_id)
    return _row_to_patch(row) if row else None


def list_patches(session: Session, agent: Optional[str] = None, generation: Optional[int] = None,
                 veredicto: Optional[str] = None, limit: Optional[int] = None) -> list[Patch]:
    """Parches en orden (generation, created_at). `veredicto="pendiente"` filtra los que no tienen veredicto."""
    stmt = select(PatchRow).order_by(PatchRow.generation, PatchRow.created_at)
    if agent is not None:
        stmt = stmt.where(PatchRow.agent == agent)
    if generation is not None:
        stmt = stmt.where(PatchRow.generation == generation)
    if veredicto == "pendiente":
        stmt = stmt.where(PatchRow.veredicto.is_(None))
    elif veredicto is not None:
        stmt = stmt.where(PatchRow.veredicto == veredicto)
    if limit:
        stmt = stmt.limit(limit)
    return [_row_to_patch(r) for r in session.scalars(stmt)]


def set_patch_verdict(session: Session, patch_id: str, veredicto: str, razon: str = "") -> Patch:
    """Para aprobar/rechazar manualmente (API `/patches/{id}/approve|reject`)."""
    row = session.get(PatchRow, patch_id)
    if row is None:
        raise KeyError(patch_id)
    row.veredicto = veredicto
    if razon:
        row.razon = razon
    session.commit()
    return _row_to_patch(row)


# ---------------------------------------------------------------- meta_strategy
def save_meta_strategy(session: Session, ms: MetaStrategy) -> int:
    row = MetaStrategyRow(
        generation=ms.generation,
        estrategia_json={"arms": {k: list(v) for k, v in ms.arms.items()}, "lecciones": ms.lecciones},
        tasa_aceptacion=ms.tasa_aceptacion, ganancia_media=ms.ganancia_media,
    )
    session.add(row)
    session.commit()
    return row.id


def list_meta_strategy(session: Session) -> list[MetaStrategy]:
    rows = session.scalars(select(MetaStrategyRow).order_by(MetaStrategyRow.generation, MetaStrategyRow.id))
    return [
        MetaStrategy(
            generation=r.generation,
            arms={k: (float(v[0]), float(v[1])) for k, v in (r.estrategia_json.get("arms") or {}).items()},
            lecciones=r.estrategia_json.get("lecciones", ""),
            tasa_aceptacion=r.tasa_aceptacion, ganancia_media=r.ganancia_media,
        )
        for r in rows
    ]


def latest_meta_strategy(session: Session) -> Optional[MetaStrategy]:
    ms = list_meta_strategy(session)
    return ms[-1] if ms else None


# ---------------------------------------------------------------- utilidades
def clear_all(session: Session) -> None:
    """Borra todos los datos (útil en demos/tests). No elimina las tablas."""
    for model in (ErrorRow, OutcomeRow, PredictionRow, DocumentRow, VehicleRow, PatchRow, MetaStrategyRow):
        session.execute(delete(model))
    session.execute(update(AgentVersionRow).values(parent_id=None))
    session.execute(delete(AgentVersionRow))
    session.commit()
