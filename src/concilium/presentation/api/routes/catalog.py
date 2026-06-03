"""Routes for catalog management — CPU override and resolution per project."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException

from concilium.application.services.concilium_service import ConciliumService
from concilium.presentation.api.container import get_concilium_service

router = APIRouter(prefix="/api/projects", tags=["projects - catalog"])


@router.get("/{project_id}/catalog/overrides", summary="List current CPU overrides for this project")
def get_project_catalog_overrides(
    project_id: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    """Returns the cpus_overlay.json dict — keys are cpu_ids, values are override data."""
    try:
        return service.get_project_catalog_overrides(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{project_id}/catalog/cpus/{cpu_id}", summary="Extend or override a CPU definition for this project")
def extend_cpu(
    project_id: str,
    cpu_id: str,
    cpu_data: dict = Body(...),
    x_user: str = Header(default="anonymous", alias="X-User"),
    motivo: str = "",
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, str]:
    """Add or override a CPU in the project-level catalog layer (ADR-040)."""
    service.extend_cpu(project_id, cpu_id, cpu_data, actor=x_user, motivo=motivo)
    return {"status": "ok", "cpu_id": cpu_id}


@router.get(
    "/{project_id}/catalog/cpus/{cpu_id}",
    summary="Resolve a CPU definition (project override → master catalog)",
)
def resolve_cpu(
    project_id: str,
    cpu_id: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> Any:
    """Resolve CPU by priority: project override → catalog base → snapshot (ADR-040)."""
    cpu = service.resolve_cpu(project_id, cpu_id)
    if cpu is None:
        raise HTTPException(status_code=404, detail=f"CPU '{cpu_id}' não encontrada no projeto nem no catálogo base.")
    return cpu
