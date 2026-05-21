"""Routes for workforce mobilization policies and deliverables config (ADR-054)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from concilium.application.services.concilium_service import ConciliumService
from concilium.presentation.api.container import get_concilium_service

from ..schemas import DeliverablesConfigRequest, MobilizacaoPolicyUpsertRequest, SimulateRequest

router = APIRouter(tags=["projects - mobilization"])


# ── Mobilization policies (ADR-054) ───────────────────────────────────────────


@router.get("/api/projects/{project_id}/mobilizacao-policies", summary="Get saved mobilization policies")
def get_mobilizacao_policies(
    project_id: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return {"items": service.get_mobilizacao_policies(project_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/api/projects/{project_id}/mobilizacao-policies", summary="Create or update a mobilization policy for an activity"
)
def upsert_mobilizacao_policy(
    project_id: str,
    req: MobilizacaoPolicyUpsertRequest,
    x_user: str = Header(default="anonymous", alias="X-User"),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        service.upsert_mobilizacao_policy(project_id, req.item_id, req.policy.model_dump(), actor=x_user)
        return {"status": "ok", "item_id": req.item_id}
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/projects/{project_id}/mobilizacao-policies/{item_id}", summary="Delete a mobilization policy")
def delete_mobilizacao_policy(
    project_id: str,
    item_id: str,
    x_user: str = Header(default="anonymous", alias="X-User"),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        service.delete_mobilizacao_policy(project_id, item_id, actor=x_user)
        return {"status": "ok", "item_id": item_id}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/api/projects/{project_id}/mobilizacao-policies/validate",
    summary="Validate all saved WMP policies without running the pipeline",
)
def validate_mobilizacao_policies(
    project_id: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    """ADR-054 Phase 3: structural validation only — does not execute skills."""
    try:
        items = service.validate_mobilizacao_policies(project_id)
        has_errors = any(i.get("status") == "ERRO" for i in items)
        has_warnings = any(i.get("status") == "AVISO" for i in items)
        return {
            "status": "ERRO" if has_errors else "AVISO" if has_warnings else "OK",
            "items": items,
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/api/projects/{project_id}/mobilizacao-policies/simulate", summary="Simulate mobilization curve (stateless)"
)
def simulate_mobilizacao_policy(
    project_id: str,
    req: SimulateRequest,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    """Derives execution curve from a policy without persisting any state."""
    try:
        return service.simulate_mobilizacao_policy(project_id, req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Deliverables config ───────────────────────────────────────────────────────


@router.get("/api/projects/{project_id}/deliverables-config", summary="Get deliverable generation flags")
def get_deliverables_config(
    project_id: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return service.get_deliverables_config(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/api/projects/{project_id}/deliverables-config", summary="Update which deliverables are generated on run")
def put_deliverables_config(
    project_id: str,
    req: DeliverablesConfigRequest,
    x_user: str = Header(default="anonymous", alias="X-User"),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return service.put_deliverables_config(project_id, req.model_dump(), actor=x_user)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
