"""Routes for pipeline run management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from concilium.application.services.concilium_service import ConciliumService
from concilium.infrastructure.auth.permission_guard import permission
from concilium.presentation.api.container import get_concilium_service
from concilium.presentation.api.rate_limit import limiter

from ..schemas import (
    ForkVersionRequest,
    RerunProjectRequest,
    RunProjectRequest,
    RunProjectResponse,
    RunStartResponse,
)

router = APIRouter(prefix="/api/projects", tags=["projects - runs"])

_PIPELINE_LIMIT = "10/minute"


@router.post("/{project_id}/runs", response_model=RunProjectResponse, summary="Run pipeline (synchronous)")
@limiter.limit(_PIPELINE_LIMIT)
@permission("project:run")
def run_project(
    request: Request,
    response: Response,
    project_id: str,
    req: RunProjectRequest,
    x_user: str = Header(default="anonymous", alias="X-User"),
    service: ConciliumService = Depends(get_concilium_service),
) -> RunProjectResponse:
    try:
        payload = service.run_project(
            project_id,
            base_version=req.base_version,
            fork_version=req.fork_version,
            procurement_intent=req.procurement_intent,
            skill_inputs_override=req.skill_inputs_override,
            use_saved_overrides=req.use_saved_overrides,
            use_mobilizacao_policy=req.use_mobilizacao_policy,
            use_strict_catalog_baseline=req.use_strict_catalog_baseline,
            actor=x_user,
        )
        return RunProjectResponse(**payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/{project_id}/runs/start",
    response_model=RunStartResponse,
    summary="Start pipeline run (asynchronous)",
)
@limiter.limit(_PIPELINE_LIMIT)
@permission("project:run")
def start_run_project(
    request: Request,
    response: Response,
    project_id: str,
    req: RunProjectRequest,
    x_user: str = Header(default="anonymous", alias="X-User"),
    service: ConciliumService = Depends(get_concilium_service),
) -> RunStartResponse:
    try:
        payload = service.start_run_project(
            project_id,
            base_version=req.base_version,
            fork_version=req.fork_version,
            procurement_intent=req.procurement_intent,
            skill_inputs_override=req.skill_inputs_override,
            use_saved_overrides=req.use_saved_overrides,
            use_mobilizacao_policy=req.use_mobilizacao_policy,
            use_strict_catalog_baseline=req.use_strict_catalog_baseline,
            actor=x_user,
        )
        return RunStartResponse(**payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/{project_id}/rerun",
    response_model=RunProjectResponse,
    summary="Re-run from a previous run or version",
)
@limiter.limit(_PIPELINE_LIMIT)
@permission("project:run")
def rerun_project(
    request: Request,
    response: Response,
    project_id: str,
    req: RerunProjectRequest,
    x_user: str = Header(default="anonymous", alias="X-User"),
    service: ConciliumService = Depends(get_concilium_service),
) -> RunProjectResponse:
    try:
        base_version = req.base_version
        if not base_version and req.base_run_id:
            base_version = service.resolve_run_base_version(project_id, req.base_run_id)
        payload = service.run_project(
            project_id,
            base_version=base_version,
            fork_version=req.fork_version,
            procurement_intent=req.procurement_intent,
            skill_inputs_override=req.skill_inputs_override,
            use_saved_overrides=req.use_saved_overrides,
            use_mobilizacao_policy=req.use_mobilizacao_policy,
            use_strict_catalog_baseline=req.use_strict_catalog_baseline,
            actor=x_user,
        )
        return RunProjectResponse(**payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{project_id}/runs", summary="List all runs for a project")
def list_runs(
    project_id: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return {"items": service.list_runs(project_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{project_id}/runs/{run_id}", summary="Get a specific run")
def get_run(
    project_id: str,
    run_id: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return service.get_run(project_id, run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{project_id}/versions/{version}/fork", summary="Fork a version (copy-on-write)")
def fork_version(
    project_id: str,
    version: str,
    req: ForkVersionRequest | None = None,
    x_user: str = Header(default="anonymous", alias="X-User"),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        actor = req.actor if req and req.actor else x_user
        return service.fork_version(project_id, version, actor=actor)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
