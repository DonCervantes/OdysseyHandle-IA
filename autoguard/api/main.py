"""API FastAPI de KAVAK AUTOGUARD AI (T-14). Datos SIMULADOS.

    uvicorn autoguard.api.main:app --reload

Auth: header `X-API-Key` == env `AUTOGUARD_API_KEY` (si la variable está vacía, la auth queda
desactivada: solo para desarrollo local). `/health` es pública. Ver `services.Settings`.
Los archivos subidos NO se almacenan (solo sus extracciones); `documents.storage_url` queda vacío.
"""
from __future__ import annotations

import json
import secrets
import time
from typing import Any, Iterator, Literal, Optional, Union

import pandas as pd
from fastapi import APIRouter, Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from autoguard.agents import cotizador
from autoguard.api.services import (
    AGENT,
    Champion,
    RsiRunner,
    Settings,
    SubprocessRsiRunner,
    Upload,
    guess_mime,
    latest_run_dir,
    procesar_expediente,
    read_jsonl,
    run_patches,
    version_id,
)
from autoguard.contracts import Outcome, Patch, Prediction, VehicleProfile
from autoguard.db import repo
from autoguard.db.models import OutcomeRow, PredictionRow
from autoguard.db.session import session_scope


# ---------------------------------------------------------------- modelos de entrada
class RsiRunParams(BaseModel):
    seed: int = 42
    batches: int = Field(default=60, ge=1, le=10_000)
    batch_size: int = Field(default=200, ge=1, le=100_000)
    k: int = Field(default=3, ge=1, le=1000)


class Decision(BaseModel):
    razon: str = ""


# ---------------------------------------------------------------- dependencias
def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _champion(request: Request) -> Champion:
    return request.app.state.champion


def get_session(request: Request) -> Iterator[Session]:
    with session_scope(request.app.state.settings.database_url) as s:
        yield s


def require_api_key(request: Request, x_api_key: Optional[str] = Header(default=None)) -> None:
    expected = request.app.state.settings.api_key
    if not expected:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="X-API-Key inválida o ausente")


def _dump(x: Any) -> Any:
    return x.model_dump(mode="json") if isinstance(x, BaseModel) else x


router = APIRouter(dependencies=[Depends(require_api_key)])


# ---------------------------------------------------------------- expedientes / vehículos / cotización
@router.post("/expedientes")
async def crear_expediente(
    request: Request,
    docs: list[UploadFile] = File(..., description="factura, tarjeta de circulación, póliza (PNG/JPG/PDF)"),
    fotos: list[UploadFile] = File(default=[]),
    tipos: list[str] = Form(default=[], description="tipo por documento (mismo orden); si falta se infiere"),
    datos: str = Form(default="{}", description="JSON: kilometraje, siniestros_previos, uso, zona, ..."),
    vehicle_id: Optional[str] = Form(default=None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        datos_d = json.loads(datos or "{}")
        if not isinstance(datos_d, dict):
            raise ValueError("datos debe ser un objeto JSON")
    except ValueError as e:
        raise HTTPException(422, f"datos inválido: {e}") from e
    # Algunos clientes mandan tipos como un solo campo "a,b,c".
    tipos_l = [t.strip() for x in tipos for t in x.split(",") if t.strip()]

    async def leer(fs: list[UploadFile]) -> list[Upload]:
        return [Upload(f.filename or "archivo", await f.read(), guess_mime(f.filename or "", f.content_type))
                for f in fs]

    docs_u, fotos_u = await leer(docs), await leer(fotos)
    if not docs_u:
        raise HTTPException(422, "se requiere al menos un documento")
    champion = _champion(request)
    cfg, sha = champion.current()
    champion.sync_db(session)
    try:
        r = procesar_expediente(docs_u, fotos_u, tipos_l, datos_d, vehicle_id, cfg, version_id(sha))
    except (ValueError, ValidationError) as e:
        raise HTTPException(422, str(e)) from e

    perfil: VehicleProfile = r["perfil"]
    pred: Prediction = r["prediccion"]
    repo.save_vehicle(session, perfil)
    for ex in r["extracciones"]:
        repo.save_document(session, ex, vehicle_id=perfil.id)
    repo.save_prediction(session, pred)
    return {
        "vehicle_id": perfil.id,
        "perfil": _dump(perfil),
        "alertas": [_dump(a) for a in perfil.alertas],
        "documentos": [_dump(e) for e in r["extracciones"]],
        "cotizacion": _dump(pred),
        "valuacion": r["valuacion"],
        "omitidos": r["omitidos"],
        "tiempo_ms": round((time.perf_counter() - t0) * 1000, 1),
        "nota": "Datos SIMULADOS",
    }


@router.get("/vehicles/{vehicle_id}")
def ver_vehiculo(vehicle_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    perfil = repo.get_vehicle(session, vehicle_id)
    if perfil is None:
        raise HTTPException(404, f"vehículo no encontrado: {vehicle_id}")
    return {
        "perfil": _dump(perfil),
        "documentos": [_dump(d) for d in repo.list_documents(session, vehicle_id=vehicle_id)],
        "predicciones": [_dump(p) for p in repo.list_predictions(session, vehicle_id=vehicle_id)],
    }


@router.post("/quote")
def cotizar(perfil: VehicleProfile, request: Request, session: Session = Depends(get_session)) -> dict[str, Any]:
    champion = _champion(request)
    cfg, sha = champion.current()
    champion.sync_db(session)
    pred = cotizador.predict(perfil, cfg, version_id(sha))
    repo.save_vehicle(session, perfil)
    repo.save_prediction(session, pred)
    return _dump(pred)


# ---------------------------------------------------------------- resultados (ingestión n8n)
@router.post("/outcomes")
def ingerir_outcomes(body: Union[list[Outcome], Outcome], session: Session = Depends(get_session)) -> dict[str, Any]:
    """Idempotente: outcomes con id ya guardado (o repetido en el lote) se cuentan como duplicados."""
    outcomes = body if isinstance(body, list) else [body]
    ids = [o.outcome_id for o in outcomes]
    existentes = set(session.scalars(select(OutcomeRow.id).where(OutcomeRow.id.in_(ids)))) if ids else set()
    nuevos: list[Outcome] = []
    vistos: set[str] = set(existentes)
    for o in outcomes:
        if o.outcome_id not in vistos:
            nuevos.append(o)
            vistos.add(o.outcome_id)
    pids = {o.prediction_id for o in nuevos}
    conocidas = set(session.scalars(select(PredictionRow.id).where(PredictionRow.id.in_(pids)))) if pids else set()
    if nuevos:
        repo.save_outcomes(session, nuevos)
    return {
        "recibidos": len(outcomes),
        "guardados": len(nuevos),
        "duplicados": len(outcomes) - len(nuevos),
        "prediccion_desconocida": sorted(pids - conocidas),
    }


# ---------------------------------------------------------------- RSI
@router.post("/rsi/run", status_code=202)
def correr_rsi(request: Request, params: Optional[RsiRunParams] = None) -> dict[str, Any]:
    runner: RsiRunner = request.app.state.rsi_runner
    try:
        return runner((params or RsiRunParams()).model_dump())
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from e


@router.get("/rsi/run/{job_id}")
def estado_rsi(job_id: str, request: Request) -> dict[str, Any]:
    status = getattr(request.app.state.rsi_runner, "status", None)
    st = status(job_id) if status else None
    if st is None:
        raise HTTPException(404, f"job no encontrado: {job_id}")
    return st


@router.get("/runs/latest")
def ultima_corrida(request: Request, incluir_curva: bool = False) -> dict[str, Any]:
    d = latest_run_dir(_settings(request).runs_dir)
    if d is None:
        raise HTTPException(404, "no hay corridas con summary.json")
    out: dict[str, Any] = {
        "run_id": d.name,
        "summary": json.loads((d / "summary.json").read_text(encoding="utf-8")),
        "archivos": sorted(p.name for p in d.iterdir() if p.is_file()),
        "n_parches": len(read_jsonl(d / "patches.jsonl")),
    }
    if incluir_curva and (d / "curve.csv").is_file():
        curve = pd.read_csv(d / "curve.csv")
        out["curva"] = json.loads(curve.to_json(orient="records"))
    return out


# ---------------------------------------------------------------- parches
def _buscar_parche(session: Session, settings: Settings, patch_id: str) -> Patch:
    p = repo.get_patch(session, patch_id)
    if p is None:  # el ciclo puede no escribir en BD: se importa desde la última corrida
        p = next((x for x in run_patches(settings.runs_dir) if x.patch_id == patch_id), None)
        if p is None:
            raise HTTPException(404, f"parche no encontrado: {patch_id}")
        repo.save_patch(session, p)
    return p


@router.get("/patches")
def listar_parches(
    request: Request,
    veredicto: Optional[str] = None,
    generation: Optional[int] = None,
    limit: Optional[int] = None,
    fuente: Literal["auto", "db", "run"] = "auto",
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """`fuente=auto`: BD si tiene parches; si no, `patches.jsonl` de la última corrida."""
    patches: list[Patch] = []
    origen = fuente
    if fuente in ("auto", "db"):
        patches = repo.list_patches(session, generation=generation, veredicto=veredicto, limit=limit)
        origen = "db"
    if fuente == "run" or (fuente == "auto" and not patches and not repo.list_patches(session, limit=1)):
        origen = "run"
        patches = run_patches(_settings(request).runs_dir)
        if generation is not None:
            patches = [p for p in patches if p.generation == generation]
        if veredicto == "pendiente":
            patches = [p for p in patches if p.veredicto is None]
        elif veredicto is not None:
            patches = [p for p in patches if p.veredicto == veredicto]
        if limit:
            patches = patches[:limit]
    return {"fuente": origen, "patches": [_dump(p) for p in patches]}


@router.post("/patches/{patch_id}/approve")
def aprobar_parche(patch_id: str, request: Request, decision: Optional[Decision] = None,
                   session: Session = Depends(get_session)) -> dict[str, Any]:
    """El actuario aprueba: el parche se aplica al campeón de producción y queda en el linaje."""
    p = _buscar_parche(session, _settings(request), patch_id)
    if p.veredicto == "invalido":
        raise HTTPException(409, "un parche inválido no se puede aprobar")
    try:
        version = _champion(request).apply(session, p)
    except ValueError as e:
        repo.set_patch_verdict(session, patch_id, "invalido", razon=f"no aplica al campeón: {e}"[:2000])
        raise HTTPException(422, f"el parche no aplica al campeón actual: {e}") from e
    razon = (decision.razon if decision and decision.razon else "aprobado por actuario (API)")
    p = repo.set_patch_verdict(session, patch_id, "aceptado", razon=razon)
    return {"patch": _dump(p), "version": _dump(version)}


@router.post("/patches/{patch_id}/reject")
def rechazar_parche(patch_id: str, request: Request, decision: Optional[Decision] = None,
                    session: Session = Depends(get_session)) -> dict[str, Any]:
    _buscar_parche(session, _settings(request), patch_id)
    razon = (decision.razon if decision and decision.razon else "rechazado por actuario (API)")
    p = repo.set_patch_verdict(session, patch_id, "rechazado", razon=razon)
    return {"patch": _dump(p)}


# ---------------------------------------------------------------- versiones
def _check_agent(agent: str) -> None:
    if agent != AGENT:
        raise HTTPException(404, f"agente sin linaje: {agent}")


@router.get("/versions/{agent}")
def versiones(agent: str, request: Request) -> dict[str, Any]:
    _check_agent(agent)
    with _champion(request).lock:
        hist = _champion(request).repo.history()
    return {"agent": agent, "versions": [_dump(v) for v in hist]}


@router.post("/versions/{agent}/revert/{sha}")
def revertir(agent: str, sha: str, request: Request, session: Session = Depends(get_session)) -> dict[str, Any]:
    _check_agent(agent)
    try:
        version = _champion(request).revert(session, sha)
    except ValueError as e:
        raise HTTPException(404, f"versión no revertible: {e}") from e
    return {"version": _dump(version)}


# ---------------------------------------------------------------- app
def create_app(settings: Optional[Settings] = None, rsi_runner: Optional[RsiRunner] = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title="KAVAK AUTOGUARD AI", version="0.1.0",
                  description="Verificación, cotización y auto-mejora recursiva. Datos SIMULADOS.")
    app.state.settings = settings
    app.state.champion = Champion(settings)
    app.state.rsi_runner = rsi_runner or SubprocessRsiRunner(settings)
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"],
        allow_credentials="*" not in settings.cors_origins,
    )

    @app.get("/health")
    def health() -> dict[str, Any]:
        from autoguard import llm

        return {"ok": True, "auth": bool(settings.api_key), "llm": "mock" if llm.is_mock() else "real"}

    app.include_router(router)
    from autoguard.api.dictamen import router as dictamen_router  # T-26
    app.include_router(dictamen_router, dependencies=[Depends(require_api_key)])
    return app


app = create_app()
