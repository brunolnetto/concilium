"""Routes for project lifecycle — CRUD, versioning, and EAP composition."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException

from concilium.application.services.concilium_service import ConciliumService
from concilium.presentation.api.container import get_concilium_service

from ..schemas import CreateProjectRequest, CreateProjectResponse

router = APIRouter(prefix="/api/projects", tags=["projects - core"])


# ── Project CRUD ──────────────────────────────────────────────────────────────


@router.get("", include_in_schema=False)
@router.get("/", summary="List all projects")
def list_projects(service: ConciliumService = Depends(get_concilium_service)) -> dict[str, Any]:
    return {"items": service.list_projects()}


@router.post("", include_in_schema=False)
@router.post("/", response_model=CreateProjectResponse, summary="Create a new project")
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


@router.get("/{project_id}", summary="Get project metadata")
def get_project(
    project_id: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return service.get_project(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{project_id}", summary="Delete project and all version folders")
def delete_project(
    project_id: str,
    x_user: str = Header(default="anonymous", alias="X-User"),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return service.delete_project(project_id, actor=x_user)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{project_id}/config", summary="Update mutable project metadata (nome, contexto_id)")
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


@router.get("/{project_id}/versions", summary="List all versions")
def list_versions(
    project_id: str,
    tree: bool = False,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    """Lista versões do projeto.

    ADR-119 D3: `?tree=true` retorna árvore hierárquica com metadados de autoria por versão.
    """
    try:
        versions = service.list_versions(project_id)
        if not tree:
            return {"items": versions}
        # Build tree with authorship metadata
        version_history = service.get_version_history(project_id)
        items = []
        for v in versions:
            meta = version_history.get(v) or {}
            items.append(
                {
                    "version": v,
                    "criado_em": meta.get("criado_em"),
                    "criado_por": meta.get("criado_por"),
                    "role_criador": meta.get("role_criador"),
                    "procurement_intent": meta.get("procurement_intent"),
                    "forked_from": meta.get("forked_from"),
                    "motivo": meta.get("motivo"),
                }
            )
        # Build parent→children adjacency for tree structure
        children: dict[str, list[str]] = {}
        roots: list[str] = []
        for item in items:
            item_version = item["version"]
            assert isinstance(item_version, str)
            parent = item.get("forked_from")
            if parent and parent in [i["version"] for i in items]:
                assert isinstance(parent, str)
                children.setdefault(parent, []).append(item_version)
            else:
                roots.append(item_version)
        return {"items": items, "roots": roots, "children": children}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{project_id}/versions/{version}", summary="Delete a version")
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


@router.get("/{project_id}/eap", summary="Get EAP items and status_eap for a 'project' type project")
def get_eap(
    project_id: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    """Returns items, count and status_eap (RASCUNHO / RASCUNHO_PRONTO / ATIVO) — ADR-063."""
    try:
        return service.get_eap(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{project_id}/eap", summary="Replace EAP items — validates DAG and updates status_eap")
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
