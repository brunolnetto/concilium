"""Routes for project lifecycle — CRUD, versioning, and EAP composition."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException

from concilium.application.services.concilium_service import ConciliumService
from concilium.presentation.api.container import get_concilium_service

from ..schemas import CreateProjectRequest, CreateProjectResponse

router = APIRouter(tags=["projects - core"])


# ── Project CRUD ──────────────────────────────────────────────────────────────


@router.get("/api/projects", summary="List all projects")
def list_projects(service: ConciliumService = Depends(get_concilium_service)) -> dict[str, Any]:
    return {"items": service.list_projects()}


@router.post("/api/projects", response_model=CreateProjectResponse, summary="Create a new project")
def create_project(
    req: CreateProjectRequest,
    x_user: str = Header(default="anonymous", alias="X-User"),
    service: ConciliumService = Depends(get_concilium_service),
) -> CreateProjectResponse:
    try:
        payload = service.create_project(req, actor=x_user)
        return CreateProjectResponse(**payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/projects/{project_id}", summary="Get project metadata")
def get_project(
    project_id: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return service.get_project(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/api/projects/{project_id}/config", summary="Update mutable project metadata (nome, contexto_id)")
def patch_project_config(
    project_id: str,
    req: dict[str, Any],
    x_user: str = Header(default="anonymous", alias="X-User"),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return service.patch_project_config(project_id, req, actor=x_user)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Versioning ────────────────────────────────────────────────────────────────


@router.get("/api/projects/{project_id}/versions", summary="List all versions")
def list_versions(
    project_id: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return {"items": service.list_versions(project_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/api/projects/{project_id}/versions/{version}", summary="Delete a version")
def delete_version(
    project_id: str,
    version: str,
    x_user: str = Header(default="anonymous", alias="X-User"),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return service.delete_version(project_id, version, actor=x_user)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── EAP (ADR-063) ────────────────────────────────────────────────────────────


@router.get("/api/projects/{project_id}/eap", summary="Get EAP items and status_eap for a 'project' type project")
def get_eap(
    project_id: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    """Returns items, count and status_eap (RASCUNHO / RASCUNHO_PRONTO / ATIVO) — ADR-063."""
    try:
        return service.get_eap(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/api/projects/{project_id}/eap", summary="Replace EAP items — validates DAG and updates status_eap")
def upsert_eap(
    project_id: str,
    eap_items: list[dict[str, Any]] = Body(...),
    x_user: str = Header(default="anonymous", alias="X-User"),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    """Replaces EAP, validates predecessores DAG, sets status_eap accordingly — ADR-063."""
    try:
        return service.upsert_eap(project_id, eap_items, actor=x_user)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
