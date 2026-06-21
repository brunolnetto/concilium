"""Routes for campaign exploration — ADR-070 parametric sweep over project GO space."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from concilium.application.services.concilium_service import ConciliumService
from concilium.domain.constants import META_MARGEM_PADRAO, TOLERANCIA_MARGEM_PADRAO
from concilium.presentation.api.container import get_concilium_service

router = APIRouter(prefix="/api/projects", tags=["projects - campaign"])


# ── Request models ────────────────────────────────────────────────────────────


class CampaignRunRequest(BaseModel):
    campaign_file: str | None = None  # absolute path; None = project default
    procurement_intent: str = "rfp"
    workers: int = 4
    reset: bool = True


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_store(service: ConciliumService, project_id: str):
    """Return a CampaignRunStore for the project, raising 404 if project unknown."""
    from pathlib import Path

    from concilium.infrastructure.settings import get_storage
    from concilium.infrastructure.storage.campaign_store import CampaignRunStore

    storage = get_storage()
    projects_root = storage.projects_root
    if projects_root is None:
        from concilium.presentation.cli.shared import _tools_root

        projects_root = _tools_root() / "projetos"
    projects_root = Path(projects_root)

    # Validate that the project exists via the service layer
    try:
        service.get_project(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    slug = project_id.upper()
    project_dir = projects_root / slug
    return CampaignRunStore(project_dir)


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get(
    "/{project_id}/campaign/runs",
    summary="List all campaign runs (ADR-070)",
)
def list_campaign_runs(
    project_id: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> list[dict[str, Any]]:
    """List all campaign runs for a project, most-recent first."""
    store = _get_store(service, project_id)

    items = []
    for run_id in reversed(store.list_runs()):
        meta = store.load_meta(run_id) or {}
        items.append(
            {
                "run_id": run_id,
                "campaign_version": meta.get("campaign_version"),
                "status": meta.get("status"),
                "n_avaliados": meta.get("n_avaliados"),
                "n_viaveis": meta.get("n_viaveis"),
                "gerado_em": meta.get("gerado_em"),
            }
        )
    return items


@router.post(
    "/{project_id}/campaign/run",
    summary="Execute a campaign sweep (ADR-070)",
    status_code=202,
)
def run_campaign(
    project_id: str,
    req: CampaignRunRequest,
    background_tasks: BackgroundTasks,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    """Kick off a campaign run asynchronously.

    Returns immediately with ``{run_id, status: "RUNNING"}`` while the sweep
    executes in the background.  Poll
    ``GET /api/projects/{project_id}/campaign/runs/{run_id}`` for completion.
    """
    import json
    from pathlib import Path

    from concilium.application.services.campaign.campaign_report import (
        render_campaign_report_md,
        render_campaign_report_pdf,
        serialize_campaign_report,
    )
    from concilium.application.services.campaign.campaign_service import construir_cubo, executar_campanha
    from concilium.application.skills.phase_classifier import is_campaign_allowed_for_intent, normalize_procurement_intent
    from concilium.domain.models.campaign.campaign import GoResearchCampaignBundle, ParametroSweep, PerfilExpectativas
    from concilium.infrastructure.settings import get_storage
    from concilium.infrastructure.storage.campaign_store import CampaignRunStore
    from concilium.presentation.cli.commands_campaign import _load_project_base_spec

    storage = get_storage()
    projects_root = storage.projects_root
    if projects_root is None:
        from concilium.presentation.cli.shared import _tools_root

        projects_root = _tools_root() / "projetos"
    projects_root = Path(projects_root)

    config_root = Path(storage.config_root)

    # Validate project
    try:
        service.get_project(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    slug = project_id.upper()
    intent = normalize_procurement_intent(req.procurement_intent)
    if not is_campaign_allowed_for_intent(intent):
        raise HTTPException(
            status_code=422,
            detail=(
                "Campanha GO é permitida apenas para RFP. "
                "RFI é fase exploratória de catálogo (PU x Q)."
            ),
        )

    # Resolve campaign file
    if req.campaign_file:
        campaign_file = Path(req.campaign_file)
    else:
        _candidates = [
            projects_root / slug / "campaigns" / "campaign_v1.json",
            projects_root.parent / "data" / slug / "campaigns" / "campaign_v1.json",
        ]
        campaign_file = next((p for p in _candidates if p.exists()), _candidates[0])

    if not campaign_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Campaign file not found: {campaign_file}",
        )

    cfg = json.loads(campaign_file.read_text(encoding="utf-8"))

    base_spec = _load_project_base_spec(projects_root, slug)
    if base_spec is None:
        raise HTTPException(
            status_code=422,
            detail=f"Project '{slug}' has no canonical spec for campaign.",
        )

    # Build bundle
    perf_raw = cfg.get("perfil_expectativas") or {}
    perfil = PerfilExpectativas(
        meta_margem_pct=perf_raw.get("meta_margem_pct", META_MARGEM_PADRAO),
        tolerancia_margem=perf_raw.get("tolerancia_margem", TOLERANCIA_MARGEM_PADRAO),
        prazo_contratual_semanas=perf_raw.get("prazo_contratual_semanas"),
    )
    sweep = [ParametroSweep(campo=s["campo"], valores=s["valores"]) for s in (cfg.get("sweep") or [])]
    bundle = GoResearchCampaignBundle(
        base_spec=base_spec,
        sweep=sweep,
        perfil_expectativas=perfil,
        top_k=cfg.get("top_k", 5),
        campaign_version=cfg.get("campaign_version", "v1"),
    )

    # Create run slot immediately so we can return the run_id
    store = CampaignRunStore(projects_root / slug)
    run_id = store.new_run()
    store.save_config(run_id, cfg)
    store.save_meta(
        run_id,
        {
            "campaign_version": bundle.campaign_version,
            "status": "RUNNING",
            "n_avaliados": 0,
            "n_viaveis": 0,
            "n_falhas": 0,
        },
    )

    workers = req.workers
    reset = req.reset

    def _run_in_background() -> None:
        try:
            result = executar_campanha(
                bundle,
                config_root=config_root,
                projects_root=projects_root,
                procurement_intent=intent.value,
                num_workers=workers,
                reset=reset,
            )
            cube = construir_cubo(bundle, result)
            report = serialize_campaign_report(result, cube)
            md = render_campaign_report_md(report)
            pdf = render_campaign_report_pdf(report, md)

            store.save_bundle(run_id, report)
            store.save_cube(run_id, report.get("cubo") or {})
            store.save_report(run_id, report, md, pdf)
            store.save_meta(
                run_id,
                {
                    "campaign_version": result.campaign_version,
                    "status": result.status,
                    "n_avaliados": result.n_cenarios_avaliados,
                    "n_viaveis": result.n_cenarios_viaveis,
                    "n_falhas": result.n_falhas,
                },
            )
        except Exception as exc:  # noqa: BLE001
            store.save_meta(
                run_id,
                {
                    "campaign_version": bundle.campaign_version,
                    "status": "ABORTADO",
                    "n_avaliados": 0,
                    "n_viaveis": 0,
                    "n_falhas": 0,
                    "erro": str(exc),
                },
            )

    background_tasks.add_task(_run_in_background)

    return {"run_id": run_id, "status": "RUNNING"}


@router.get(
    "/{project_id}/campaign/runs/{run_id}",
    summary="Get full bundle for a specific campaign run (ADR-070)",
)
def get_campaign_run(
    project_id: str,
    run_id: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    """Return the full CampaignOutputBundle JSON for a specific run."""
    store = _get_store(service, project_id)

    if run_id not in store.list_runs():
        raise HTTPException(status_code=404, detail=f"Campaign run '{run_id}' not found.")

    bundle = store.load_bundle(run_id)
    meta = store.load_meta(run_id) or {}
    if bundle is None:
        # Run exists (meta written) but bundle not yet produced (still RUNNING)
        return {"run_id": run_id, "meta": meta, "bundle": None}

    return {"run_id": run_id, "meta": meta, "bundle": bundle}


@router.get(
    "/{project_id}/campaign/runs/{run_id}/report",
    summary="Get campaign report in a specific format (ADR-070)",
)
def get_campaign_run_report(
    project_id: str,
    run_id: str,
    format: str = Query("json", pattern="^(json|md|pdf)$"),
    service: ConciliumService = Depends(get_concilium_service),
) -> Response:
    """Download the campaign report.

    ``format`` can be ``json`` (default), ``md`` (Markdown), or ``pdf``.
    """
    store = _get_store(service, project_id)

    if run_id not in store.list_runs():
        raise HTTPException(status_code=404, detail=f"Campaign run '{run_id}' not found.")

    run_path = store.run_path(run_id)

    if format == "json":
        report = store.load_report_json(run_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Report JSON not yet available.")
        import json

        return Response(
            content=json.dumps(report, indent=2, ensure_ascii=False, default=str),
            media_type="application/json",
        )

    if format == "md":
        md_path = run_path / store.REPORT_MD
        if not md_path.exists():
            raise HTTPException(status_code=404, detail="Report Markdown not yet available.")
        return Response(content=md_path.read_text(encoding="utf-8"), media_type="text/markdown")

    # pdf
    pdf_path = run_path / store.REPORT_PDF
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Report PDF not yet available.")
    return Response(
        content=pdf_path.read_bytes(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="campaign_report_{run_id}.pdf"'},
    )
