"""Routes for analysis — version comparison, artifacts, audit, diagnostics."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from concilium.application.services.concilium_service import ConciliumService
from concilium.presentation.api.container import get_concilium_service

from ..schemas import CompareRequest

router = APIRouter(tags=["projects - analysis"])


# ── Version comparison ────────────────────────────────────────────────────────


@router.post("/api/projects/{project_id}/compare", summary="Compare two canonical versions (POST body)")
def compare(
    project_id: str,
    req: CompareRequest,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return service.compare_versions(project_id, req.left_version, req.right_version)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/projects/{project_id}/compare", summary="Compare two canonical versions (query params)")
def compare_query(
    project_id: str,
    left: str,
    right: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return service.compare_versions(project_id, left, right)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── Artifacts ─────────────────────────────────────────────────────────────────


@router.get("/api/projects/{project_id}/artifacts", summary="List output artifacts")
def list_artifacts(
    project_id: str,
    version: str | None = None,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return service.list_artifacts(project_id, version)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/projects/{project_id}/artefacts", summary="List output artifacts (alias)", include_in_schema=False)
def list_artefacts_alias(
    project_id: str,
    version: str | None = None,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return service.list_artifacts(project_id, version)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/api/projects/{project_id}/artefacts/{version}",
    summary="List artifacts by version (alias)",
    include_in_schema=False,
)
def list_artefacts_by_version_alias(
    project_id: str,
    version: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return service.list_artifacts(project_id, version)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/projects/{project_id}/artifacts/download", summary="Download an artifact file")
def download_artifact(
    project_id: str,
    kind: str,
    filename: str,
    version: str | None = None,
    service: ConciliumService = Depends(get_concilium_service),
) -> Response:
    try:
        data, media_type = service.get_artifact_bytes(project_id, version, kind, filename)
        return Response(
            content=data,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/api/projects/{project_id}/benchmark-reference", summary="Get the benchmark reference snapshot for this project"
)
def get_benchmark_reference(
    project_id: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return service.get_benchmark_reference(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── Audit ─────────────────────────────────────────────────────────────────────


@router.get("/api/projects/{project_id}/audit", summary="List audit log entries")
def list_audit(
    project_id: str,
    limit: int = 200,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return {"items": service.list_audit(project_id, limit=limit)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Diagnóstico PE (ADR-060/061) ──────────────────────────────────────────────


@router.get(
    "/api/projects/{project_id}/diagnostico-pe",
    summary="Get breakeven diagnosis and backtracking from last successful run",
)
def get_diagnostico_pe(
    project_id: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    """Returns DiagnosticoPE and BacktrackingPE for the active version (ADR-060/061)."""
    try:
        return service.get_diagnostico_pe(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        return {"diagnostico_pe": None, "backtracking_pe": None, "aviso": str(exc)}
