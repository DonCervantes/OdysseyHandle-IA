"""Router FastAPI del dictamen preliminar de siniestros (T-26 / RF-15).

Se monta desde `autoguard.api.main.create_app` con auth (`X-API-Key`).
"""
from __future__ import annotations

import json
from typing import Iterator, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from autoguard.agents.dictamen import DictamenResult, dictaminar
from autoguard.api.services import Upload, guess_mime
from autoguard.contracts import Dano, VehicleProfile
from autoguard.db import repo
from autoguard.db.session import session_scope

router = APIRouter(prefix="/dictamen", tags=["dictamen"])


class DictamenJSON(BaseModel):
    perfil: VehicleProfile
    danos_reclamados: list[Dano]
    relato_zonas: list[str] = Field(default_factory=list)
    monto_declarado: Optional[float] = None


def get_session(request: Request) -> Iterator[Session]:
    with session_scope(request.app.state.settings.database_url) as s:
        yield s


@router.post("", response_model=DictamenResult)
@router.post("/", response_model=DictamenResult, include_in_schema=False)
def dictamen_json(body: DictamenJSON) -> DictamenResult:
    try:
        return dictaminar(
            body.perfil,
            danos_reclamados=body.danos_reclamados,
            relato_zonas=body.relato_zonas or None,
            monto_declarado=body.monto_declarado,
        )
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/expediente", response_model=DictamenResult)
async def dictamen_expediente(
    request: Request,
    fotos: list[UploadFile] = File(..., description="fotos del siniestro"),
    vehicle_id: Optional[str] = Form(default=None),
    perfil_json: Optional[str] = Form(default=None, description="VehicleProfile JSON si no hay vehicle_id"),
    relato_zonas: str = Form(default="[]", description="JSON lista de zonas del relato"),
    monto_declarado: Optional[float] = Form(default=None),
    session: Session = Depends(get_session),
) -> DictamenResult:
    try:
        zonas = json.loads(relato_zonas or "[]")
        if not isinstance(zonas, list):
            raise ValueError("relato_zonas debe ser una lista JSON")
    except (json.JSONDecodeError, ValueError) as e:
        raise HTTPException(422, f"relato_zonas inválido: {e}") from e

    perfil: Optional[VehicleProfile] = None
    if vehicle_id:
        perfil = repo.get_vehicle(session, vehicle_id)
        if perfil is None:
            raise HTTPException(404, f"vehículo no encontrado: {vehicle_id}")
    elif perfil_json:
        try:
            perfil = VehicleProfile.model_validate(json.loads(perfil_json))
        except (json.JSONDecodeError, ValidationError) as e:
            raise HTTPException(422, f"perfil_json inválido: {e}") from e
    else:
        raise HTTPException(422, "se requiere vehicle_id o perfil_json")

    uploads = [
        Upload(f.filename or f"foto-{i}.png", await f.read(), guess_mime(f.filename or "", f.content_type))
        for i, f in enumerate(fotos)
    ]
    if not uploads:
        raise HTTPException(422, "se requiere al menos una foto")

    try:
        return dictaminar(
            perfil,
            fotos=[u.content for u in uploads],
            hints=[u.filename for u in uploads],
            relato_zonas=[str(z) for z in zonas],
            monto_declarado=monto_declarado,
        )
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
