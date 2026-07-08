"""Routes for project lifecycle — CRUD, versioning, and EAP composition."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request

from concilium.application.services.concilium_service import ConciliumService
from concilium.infrastructure.auth.permission_guard import (
    PROJECT_DELETE,
    PROJECT_MANAGE_CONFIG,
    PROJECT_MANAGE_OWNERSHIP,
    permission,
    require_owner_or_admin,
    roles_from_token,
)
from concilium.infrastructure.settings import get_auth
from concilium.presentation.api.container import get_concilium_service
from concilium.presentation.api.deps import get_current_subject

from ..schemas import CreateProjectRequest, CreateProjectResponse, TransferOwnershipRequest

router = APIRouter(prefix="/api/projects", tags=["projects - core"])


def _actor_roles(request: Request) -> list[str]:
    """ADR-126 D3: extrai roles do JWT do request atual (mesma fonte de @permission)."""
    claims = getattr(request.state, "jwt_claims", {})
    return roles_from_token(claims)


def _actor_id(request: Request, x_user: str) -> str:
    """ADR-126: deriva o actor do `sub` do JWT quando disponível — nunca confia em
    `X-User` sozinho para decisões de autorização/identidade quando AUTH está
    habilitado, pois é um header controlável pelo cliente (spoofável). `X-User`
    só é usado como fallback em dev mode (AUTH_ENABLED=0), onde não há claims.
    """
    subject = get_current_subject(request)
    return subject if subject is not None else x_user


def _enforce_ownership(request: Request, project_id: str, actor: str, service: ConciliumService) -> None:
    """ADR-126 D3: 2ª camada — role já validada por @permission; aqui checa ownership.

    No-op quando AUTH_ENABLED=0 (dev/test local) — evita a chamada extra a
    `service.get_project_owner` nesse modo, mantendo compatibilidade com
    dependências fake mais antigas (pré-ADR-126) que não implementam esse método.
    """
    if not get_auth().enabled:
        return
    owner_id = service.get_project_owner(project_id)
    require_owner_or_admin(actor_id=actor, owner_id=owner_id, roles=_actor_roles(request))


# ── Project CRUD ──────────────────────────────────────────────────────────────


@router.get("", include_in_schema=False)
@router.get("/", summary="List all projects")
def list_projects(
    request: Request,
    mine: bool = False,
    x_user: str = Header(default="anonymous", alias="X-User"),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    """ADR-126 D5: `?mine=true` filtra por owner_id == actor atual (sub do JWT)."""
    if mine:
        return {"items": service.list_projects(owner_id=_actor_id(request, x_user))}
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
@permission(PROJECT_DELETE)
def delete_project(
    request: Request,
    project_id: str,
    x_user: str = Header(default="anonymous", alias="X-User"),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        actor = _actor_id(request, x_user)
        _enforce_ownership(request, project_id, actor, service)
        return service.delete_project(project_id, actor=actor)
    except PermissionError:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{project_id}/config", summary="Update mutable project metadata (nome, contexto_id)")
@permission(PROJECT_MANAGE_CONFIG)
def patch_project_config(
    request: Request,
    project_id: str,
    req: dict[str, Any],
    x_user: str = Header(default="anonymous", alias="X-User"),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        actor = _actor_id(request, x_user)
        _enforce_ownership(request, project_id, actor, service)
        return service.patch_project_config(project_id, req, actor=actor)
    except PermissionError:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── Ownership (ADR-126) ──────────────────────────────────────────────────────


@router.post(
    "/{project_id}/transfer-ownership",
    summary="Transfer project ownership (forced by admin, or pending invite by owner)",
)
@permission(PROJECT_MANAGE_OWNERSHIP)
def transfer_ownership(
    request: Request,
    project_id: str,
    req: TransferOwnershipRequest,
    x_user: str = Header(default="anonymous", alias="X-User"),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    """ADR-126 D4: handover híbrido.

    - admin: troca owner_id imediatamente (forçado, sem aceite).
    - dono atual: cria convite pendente (owner_id só muda após /accept).
    - qualquer outro actor (nem dono, nem admin): 403.
    """
    try:
        actor = _actor_id(request, x_user)
        owner_id = service.get_project_owner(project_id)
        roles = _actor_roles(request)
        if "admin" in roles:
            return service.transfer_ownership_forced(project_id, req.owner_novo, actor=actor)
        if owner_id is not None and actor == owner_id:
            return service.create_ownership_transfer_pending(project_id, req.owner_novo, actor=actor)
        raise PermissionError(
            f"Apenas o dono do projeto (owner_id={owner_id!r}) ou um admin podem iniciar a transferência de "
            f"ownership. Actor atual: {actor!r}, roles: {roles!r}."
        )
    except PermissionError:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{project_id}/transfer-ownership/{token}/accept", summary="Accept a pending ownership transfer invite")
@permission(PROJECT_MANAGE_OWNERSHIP)
def accept_ownership_transfer_route(
    request: Request,
    project_id: str,
    token: str,
    x_user: str = Header(default="anonymous", alias="X-User"),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return service.accept_ownership_transfer(project_id, token, actor=_actor_id(request, x_user))
    except PermissionError:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{project_id}/transfer-ownership/{token}/reject", summary="Reject a pending ownership transfer invite")
@permission(PROJECT_MANAGE_OWNERSHIP)
def reject_ownership_transfer_route(
    request: Request,
    project_id: str,
    token: str,
    x_user: str = Header(default="anonymous", alias="X-User"),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return service.reject_ownership_transfer(project_id, token, actor=_actor_id(request, x_user))
    except PermissionError:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Versioning ────────────────────────────────────────────────────────────────


def _build_version_tree_items(versions: list[str], version_history: dict[str, Any]) -> list[dict[str, Any]]:
    """Anexa metadados de autoria a cada versão para a resposta em árvore."""
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
    return items


def _build_version_tree_adjacency(items: list[dict[str, Any]]) -> tuple[dict[str, list[str]], list[str]]:
    """Constrói a adjacência parent→children e a lista de raízes para a árvore de versões."""
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
    return children, roots


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
        items = _build_version_tree_items(versions, version_history)
        # Build parent→children adjacency for tree structure
        children, roots = _build_version_tree_adjacency(items)
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
