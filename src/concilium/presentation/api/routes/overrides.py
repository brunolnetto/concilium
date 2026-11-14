"""Routes for skill input overrides."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from concilium.application.scheduling.project_bdi_exact_store import ProjectBdiExactError
from concilium.application.services.concilium_service import ConciliumService
from concilium.presentation.api.container import get_concilium_service

from ..schemas import OverrideUpsertRequest, ProjectBdiExatoSaveRequest

router = APIRouter(prefix="/api/projects", tags=["projects - overrides"])


@router.get("/{project_id}/overrides", summary="List saved skill overrides")
def list_overrides(
    project_id: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return service.list_overrides(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{project_id}/overrides", summary="Upsert skill input override")
def upsert_override(
    project_id: str,
    req: OverrideUpsertRequest,
    x_user: str = Header(default="anonymous", alias="X-User"),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return service.upsert_override(project_id, req.skill_id, req.inputs, actor=x_user)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{project_id}/overrides/{skill_id}", summary="Delete override for a skill")
def delete_override(
    project_id: str,
    skill_id: str,
    x_user: str = Header(default="anonymous", alias="X-User"),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return service.delete_override(project_id, skill_id, actor=x_user)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# N9.1 (#206): exact BDI declaration of the project — what the exact price reads.
# The legacy float profile (bdi/perfil_bdi.json) is never returned as, nor converted into, this form.


@router.get("/{project_id}/bdi-exato", summary="Exact BDI declaration status and effective markup layers")
def get_project_bdi_exato(
    project_id: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return service.get_project_bdi_exato(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{project_id}/bdi-exato", summary="Save a new version of the exact BDI declaration")
def save_project_bdi_exato(
    project_id: str,
    req: ProjectBdiExatoSaveRequest,
    x_user: str = Header(default="anonymous", alias="X-User"),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return service.save_project_bdi_exato(
            project_id,
            req.declaracao,
            confirmado_por=req.confirmado_por,
            motivo_revisao=req.motivo_revisao,
            actor=x_user,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProjectBdiExactError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
