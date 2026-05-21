"""Routes for global master catalog — listing catalogs, CPUs, insumos, and search."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query

from concilium.application.services.concilium_service import ConciliumService
from concilium.presentation.api.container import get_concilium_service

router = APIRouter(tags=["catalogs"])


@router.get("/api/catalogs", summary="List available master catalogs")
def list_catalogs(
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    """List catalog IDs available in config/catalogos/."""
    return {"items": service.list_catalogs()}


@router.get("/api/catalogs/{catalog_id}", summary="Get catalog metadata and summary")
def get_catalog(
    catalog_id: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    """Returns metadata and item counts for a catalog."""
    try:
        return service.get_catalog(catalog_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/catalogs/{catalog_id}/cpus", summary="List CPUs in master catalog")
def list_catalog_cpus(
    catalog_id: str,
    q: str | None = Query(None, description="Filter by código or descrição"),
    limit: int = Query(50, ge=1, le=500),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    """Returns CPUs from the master catalog, optionally filtered."""
    try:
        return service.list_catalog_cpus(catalog_id, q=q, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/catalogs/{catalog_id}/cpus/{cpu_id}", summary="Get a specific CPU from master catalog")
def get_catalog_cpu(
    catalog_id: str,
    cpu_id: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    """Returns full CPU definition from the master catalog."""
    try:
        cpu = service.get_catalog_cpu(catalog_id, cpu_id)
        if cpu is None:
            raise HTTPException(status_code=404, detail=f"CPU '{cpu_id}' não encontrada no catálogo '{catalog_id}'.")
        return cpu
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put(
    "/api/catalogs/{catalog_id}/cpus/{cpu_id}",
    summary="Create or update a CPU in the master catalog (ADR-067)",
)
def upsert_catalog_cpu(
    catalog_id: str,
    cpu_id: str,
    req: dict[str, Any] = Body(...),
    x_user: str = Header(default="anonymous", alias="X-User"),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    """Replace a CPU definition in the master catalog.

    Body: `{"cpu_data": {...}, "motivo": "reason for change"}`.
    Invalidates bundle cache and appends to `.catalog_audit.jsonl`.
    """
    cpu_data = req.get("cpu_data") or {k: v for k, v in req.items() if k != "motivo"}
    motivo = req.get("motivo", "")
    try:
        return service.upsert_catalog_cpu(catalog_id, cpu_id, cpu_data, actor=x_user, motivo=motivo)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/catalogs/{catalog_id}/insumos", summary="List insumos in master catalog")
def list_catalog_insumos(
    catalog_id: str,
    q: str | None = Query(None, description="Filter by código or descrição"),
    limit: int = Query(50, ge=1, le=500),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    """Returns insumos from the master catalog, optionally filtered."""
    try:
        return service.list_catalog_insumos(catalog_id, q=q, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/catalog/search", summary="Search CPUs across all catalogs or a specific one")
def search_catalog(
    q: str = Query(..., description="Search term (código or descrição)"),
    catalog_id: str | None = Query(None, description="Restrict to this catalog ID"),
    limit: int = Query(20, ge=1, le=100),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    """Full-text search across CPUs in the master catalog."""
    return service.search_catalog(q=q, catalog_id=catalog_id, limit=limit)
