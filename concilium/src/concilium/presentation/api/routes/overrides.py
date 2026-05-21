"""Routes for skill input overrides."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from concilium.application.services.concilium_service import ConciliumService
from concilium.presentation.api.container import get_concilium_service

from ..schemas import OverrideUpsertRequest

router = APIRouter(tags=["projects - overrides"])


@router.get("/api/projects/{project_id}/overrides", summary="List saved skill overrides")
def list_overrides(
    project_id: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return service.list_overrides(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/projects/{project_id}/overrides", summary="Upsert skill input override")
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


@router.delete("/api/projects/{project_id}/overrides/{skill_id}", summary="Delete override for a skill")
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
