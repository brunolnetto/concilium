"""Routes for versioned configuration entities — perfis, contextos, temas (ADR-062/065)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from concilium.application.services.concilium_service import ConciliumService
from concilium.presentation.api.container import get_concilium_service

router = APIRouter(tags=["configuration"])

# ── Perfis ────────────────────────────────────────────────────────────────────


@router.get("/api/perfis", summary="List financial profiles with version history")
def list_perfis(service: ConciliumService = Depends(get_concilium_service)) -> dict[str, Any]:
    """List all perfis (financial parameters: BDI, margin targets) — ADR-062."""
    return {"items": service.list_perfis()}


@router.get("/api/perfis/{perfil_id}/versions", summary="List versions of a profile")
def list_perfil_versions(
    perfil_id: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    return {"perfil_id": perfil_id, "versions": service.list_perfil_versions(perfil_id)}


@router.post("/api/perfis/{perfil_id}/versions", summary="Create a new profile version")
def create_perfil_version(
    perfil_id: str,
    req: dict[str, Any],
    x_user: str = Header(default="anonymous", alias="X-User"),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    """Body: `{fields: {...}, motivo: str}` (ADR-062)."""
    motivo = req.get("motivo", "")
    if not motivo:
        raise HTTPException(status_code=422, detail="Campo 'motivo' é obrigatório.")
    fields = req.get("fields") or {k: v for k, v in req.items() if k != "motivo"}
    try:
        return service.create_perfil_version(perfil_id, fields, motivo, author=x_user)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/perfis/compare", summary="Compare two profile versions")
def compare_perfil_versions(
    id: str,
    vA: str,
    vB: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    """Query params: `id`, `vA`, `vB` (ADR-062)."""
    return service.compare_perfil_versions(id, vA, vB)


# ── Contextos ─────────────────────────────────────────────────────────────────


@router.get("/api/contextos", summary="List contexts with version history")
def list_contextos(service: ConciliumService = Depends(get_concilium_service)) -> dict[str, Any]:
    """List all contextos (catalog + jurisdiction + profile bundle) — ADR-062."""
    return {"items": service.list_contextos()}


@router.get("/api/contextos/{contexto_id}/versions", summary="List versions of a context")
def list_contexto_versions(
    contexto_id: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    return {"contexto_id": contexto_id, "versions": service.list_contexto_versions(contexto_id)}


@router.post("/api/contextos/{contexto_id}/versions", summary="Create a new context version")
def create_contexto_version(
    contexto_id: str,
    req: dict[str, Any],
    x_user: str = Header(default="anonymous", alias="X-User"),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    """Body: `{fields: {...}, motivo: str}` (ADR-062)."""
    motivo = req.get("motivo", "")
    if not motivo:
        raise HTTPException(status_code=422, detail="Campo 'motivo' é obrigatório.")
    fields = req.get("fields") or {k: v for k, v in req.items() if k != "motivo"}
    try:
        return service.create_contexto_version(contexto_id, fields, motivo, author=x_user)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/contextos/compare", summary="Compare two context versions")
def compare_contexto_versions(
    id: str,
    vA: str,
    vB: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    """Query params: `id`, `vA`, `vB` (ADR-062)."""
    return service.compare_contexto_versions(id, vA, vB)


# ── Temas ─────────────────────────────────────────────────────────────────────


@router.get("/api/temas", summary="List visual themes")
def list_temas(service: ConciliumService = Depends(get_concilium_service)) -> dict[str, Any]:
    """List all TemaVisual entities (colors, fonts, branding) — ADR-065."""
    return {"items": service.list_temas()}


@router.get("/api/temas/{tema_id}/versions", summary="List versions of a theme")
def list_tema_versions(
    tema_id: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    return {"tema_id": tema_id, "versions": service.list_tema_versions(tema_id)}


@router.post("/api/temas/{tema_id}/versions", summary="Create a new theme version")
def create_tema_version(
    tema_id: str,
    req: dict[str, Any],
    x_user: str = Header(default="anonymous", alias="X-User"),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    """Body: `{fields: {...}, motivo: str}` (ADR-065)."""
    motivo = req.get("motivo", "")
    if not motivo:
        raise HTTPException(status_code=422, detail="Campo 'motivo' é obrigatório.")
    fields = req.get("fields") or {k: v for k, v in req.items() if k != "motivo"}
    try:
        return service.create_tema_version(tema_id, fields, motivo, author=x_user)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/temas/compare", summary="Compare two theme versions")
def compare_tema_versions(
    id: str,
    vA: str,
    vB: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    """Query params: `id`, `vA`, `vB` (ADR-065)."""
    return service.compare_tema_versions(id, vA, vB)


# ── Jurisdições (ADR-066) ─────────────────────────────────────────────────────


@router.get("/api/jurisdicoes", summary="List jurisdictions with overlay history")
def list_jurisdicoes(service: ConciliumService = Depends(get_concilium_service)) -> dict[str, Any]:
    """List all jurisdictions with their overlay versions (ADR-066)."""
    return {"items": service.list_jurisdicoes()}


@router.get("/api/jurisdicoes/{jurisdicao_id}/versions", summary="List versions of a jurisdiction overlay")
def list_jurisdicao_versions(
    jurisdicao_id: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    return {"jurisdicao_id": jurisdicao_id, "versions": service.list_jurisdicao_versions(jurisdicao_id)}


@router.post("/api/jurisdicoes/{jurisdicao_id}/versions", summary="Create a new jurisdiction overlay version")
def create_jurisdicao_version(
    jurisdicao_id: str,
    req: dict[str, Any],
    x_user: str = Header(default="anonymous", alias="X-User"),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    """Body: `{fields: {cpus: {}, insumos: {}}, motivo: str}` (ADR-066)."""
    motivo = req.get("motivo", "")
    if not motivo:
        raise HTTPException(status_code=422, detail="Campo 'motivo' é obrigatório.")
    fields = req.get("fields") or {k: v for k, v in req.items() if k != "motivo"}
    try:
        return service.create_jurisdicao_version(jurisdicao_id, fields, motivo, author=x_user)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/jurisdicoes/compare", summary="Compare two jurisdiction overlay versions")
def compare_jurisdicao_versions(
    id: str,
    vA: str,
    vB: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    """Query params: `id`, `vA`, `vB` (ADR-066)."""
    return service.compare_jurisdicao_versions(id, vA, vB)
