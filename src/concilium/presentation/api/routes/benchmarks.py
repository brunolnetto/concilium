"""Routes for benchmark operations — listing, packing, and downloading.

Global listing route remains for template discovery.
Artifact routes (download/pack) are scoped to projects (ADR-066 §D4).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from concilium.application.services.concilium_service import ConciliumService
from concilium.presentation.api.container import get_concilium_service

router = APIRouter(tags=["benchmarks"])


@router.get("/api/benchmarks", summary="List available benchmark template slugs")
def list_benchmarks(service: ConciliumService = Depends(get_concilium_service)) -> dict[str, Any]:
    """Global benchmark templates — not scoped to any project."""
    return {"items": service.list_benchmarks()}


# ── Project-scoped benchmark routes (ADR-066) ─────────────────────────────────


@router.get(
    "/api/projects/{project_id}/benchmarks",
    summary="List benchmarks referenced by this project",
)
def list_project_benchmarks(
    project_id: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    """Returns the benchmark slug(s) linked to this project via benchmark_slug in meta."""
    try:
        project = service.get_project(project_id)
        slug = project.get("benchmark_slug")
        return {"items": [slug] if slug else []}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/api/projects/{project_id}/benchmarks/{slug}/download",
    summary="Download benchmark artifacts in project context",
    response_class=FileResponse,
)
def download_project_benchmark_zip(
    project_id: str,
    slug: str,
    charts: bool = Query(True),
    cenarios: bool = Query(False),
    service: ConciliumService = Depends(get_concilium_service),
) -> FileResponse:
    """Download ZIP of benchmark artifacts scoped to this project (ADR-066)."""
    from pathlib import Path

    from concilium.application.benchmarks.charts.output_packager import empacotar_outputs

    config_root: Path = service.config_root  # type: ignore[attr-defined]
    try:
        zip_path = empacotar_outputs(
            slug=slug,
            config_root=config_root,
            gerar_graficos=charts,
            incluir_cenarios=cenarios,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao empacotar: {e}") from e

    filename = f"benchmark_{slug.upper()}_{zip_path.stem.split('_')[-1]}.zip"
    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/api/projects/{project_id}/benchmarks/{slug}/pack",
    summary="Trigger asynchronous benchmark packaging in project context",
)
def trigger_project_pack_benchmark(
    project_id: str,
    slug: str,
    background_tasks: BackgroundTasks,
    charts: bool = Query(True),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, str]:
    """Queue benchmark packaging in background (ADR-066)."""
    from pathlib import Path

    from concilium.application.benchmarks.charts.output_packager import empacotar_outputs

    config_root: Path = service.config_root  # type: ignore[attr-defined]

    def _pack() -> None:
        try:
            empacotar_outputs(slug=slug, config_root=config_root, gerar_graficos=charts)
        except Exception:
            pass

    background_tasks.add_task(_pack)
    return {
        "status": "queued",
        "slug": slug.upper(),
        "download": f"/api/projects/{project_id}/benchmarks/{slug}/download",
    }
