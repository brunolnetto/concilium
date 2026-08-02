"""Routes for analysis — version comparison, artifacts, audit, diagnostics."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from concilium.application.services.concilium_service import ConciliumService
from concilium.presentation.api.container import get_concilium_service

from ..schemas import CompareRequest, SimulateCalendarioOperacionalRequest

router = APIRouter(prefix="/api/projects", tags=["projects - analysis"])


# ── Version comparison ────────────────────────────────────────────────────────


@router.post("/{project_id}/compare", summary="Compare two canonical versions (POST body)")
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


@router.get("/{project_id}/compare", summary="Compare two canonical versions (query params)")
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


@router.get("/{project_id}/artifacts", summary="List output artifacts")
def list_artifacts(
    project_id: str,
    version: str | None = None,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return service.list_artifacts(project_id, version)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{project_id}/artifacts/download", summary="Download an artifact file")
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


@router.get("/{project_id}/benchmark-reference", summary="Get the benchmark reference snapshot for this project")
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


@router.get("/{project_id}/audit", summary="List audit log entries")
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
    "/{project_id}/diagnostico-pe",
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


@router.get(
    "/{project_id}/calendario-operacional",
    summary="Get weekly operational calendar factors (climate x calendar x total)",
)
def get_calendario_operacional(
    project_id: str,
    version: str | None = Query(None),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return service.get_calendario_operacional(project_id, version=version)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/{project_id}/calendario-operacional/simular",
    summary="Simulate weekly calendar overrides and resulting total factor",
)
def simulate_calendario_operacional(
    project_id: str,
    req: SimulateCalendarioOperacionalRequest,
    version: str | None = Query(None),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return service.simulate_calendario_operacional(project_id, req.model_dump(), version=version)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Cubo analítico (ADR-058 / NEP-024) ────────────────────────────────────────


@router.get(
    "/{project_id}/cubo-analitico",
    summary="Get analytical cube and derived temporal/nature aggregations",
)
def get_cubo_analitico(
    project_id: str,
    version: str | None = Query(None),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return service.get_cubo_analitico(project_id, version=version)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/{project_id}/cubo-analitico/projecao",
    summary="Project analytical cube into filtered faces for UX exploration",
)
def get_cubo_analitico_projecao(
    project_id: str,
    version: str | None = Query(None),
    face: Literal[
        "tempo_natureza",
        "tempo_componente",
        "categoria_componente",
        "atividade_componente",
        "diesel_temporal",
        "abc_curva",
        "s_curve_custo",
        "recursos_ativos_tempo",
    ] = Query("tempo_natureza"),
    granularidade: Literal["semana", "mes", "bimestre", "trimestre", "semestre", "ano"] = Query("mes"),
    categoria: Literal["mao_obra", "equipamento", "diesel", "material"] | None = Query(None),
    componente_bdi: Literal[
        "custo_direto",
        "overhead_ac",
        "overhead_df",
        "overhead_r",
        "overhead_cr",
        "margem_l",
        "tributo_cofins",
        "tributo_iss",
        "tributo_pis",
        "tributo_cssl",
        "tributo_ir",
    ]
    | None = Query(None),
    measure_profile: Literal["financial_default", "abc_custo_direto", "recursos_ativos"] | None = Query(None),
    aggregation_mode: Literal["sum", "count_distinct", "cumulative", "pareto"] | None = Query(None),
    abc_threshold_a: float = Query(0.80, gt=0.0, lt=1.0),
    abc_threshold_b: float = Query(0.95, gt=0.0, lt=1.0),
    atividade_id: str | None = Query(None),
    top_n: int = Query(300, ge=1, le=2000),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return service.get_cubo_analitico_projection(
            project_id,
            version=version,
            face=face,
            granularidade=granularidade,
            categoria=categoria,
            componente_bdi=componente_bdi,
            atividade_id=atividade_id,
            top_n=top_n,
            measure_profile=measure_profile,
            aggregation_mode=aggregation_mode,
            abc_threshold_a=abc_threshold_a,
            abc_threshold_b=abc_threshold_b,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/{project_id}/cubo-analitico/projecao/contrato",
    summary="Get analytical projection contract matrix (faces x measure x aggregation)",
)
def get_cubo_analitico_projecao_contrato(
    project_id: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    _ = project_id
    return service.get_cubo_projection_contract()


@router.get(
    "/{project_id}/cubo-pool/projecao",
    summary="ADR-086: Explore the resource-pool decomposition (instance/temporal/causal faces)",
)
def get_cubo_pool_projecao(
    project_id: str,
    version: str | None = Query(None),
    face: Literal[
        "utilizacao_temporal",
        "custo_estado_componente",
        "instancia_ciclo_vida",
        "atividade_instancia",
        "causa_custo",
        "economia_pool",
        "cadeia_perpetuacao",
    ] = Query("instancia_ciclo_vida"),
    granularidade: Literal["semana", "mes", "trimestre", "ano"] = Query("mes"),
    atividade_id: str | None = Query(None),
    instancia_id: str | None = Query(None),
    top_n: int = Query(300, ge=1, le=2000),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return service.get_cubo_pool_projection(
            project_id,
            version=version,
            face=face,
            granularidade=granularidade,
            atividade_id=atividade_id,
            instancia_id=instancia_id,
            top_n=top_n,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/{project_id}/cubo-pool/projecao/contrato",
    summary="ADR-086: Get resource-pool projection contract (faces x natureza x granularidade)",
)
def get_cubo_pool_projecao_contrato(
    project_id: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    _ = project_id
    return service.get_cubo_pool_projection_contract()


@router.get(
    "/{project_id}/cubo-estoque-consumivel/projecao",
    summary="ADR-128 F6: Explore consumable-resource stock accounting (resumo/temporal/fluxo/causa faces)",
)
def get_cubo_estoque_consumivel_projecao(
    project_id: str,
    version: str | None = Query(None),
    face: Literal[
        "resumo_por_recurso",
        "estoque_temporal",
        "fluxo_componente",
        "causa_atraso",
    ] = Query("resumo_por_recurso"),
    granularidade: Literal["semana", "mes", "trimestre", "ano"] = Query("mes"),
    resource_id: str | None = Query(None),
    top_n: int = Query(300, ge=1, le=2000),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return service.get_cubo_estoque_consumivel_projection(
            project_id,
            version=version,
            face=face,
            granularidade=granularidade,
            resource_id=resource_id,
            top_n=top_n,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/{project_id}/cubo-estoque-consumivel/projecao/contrato",
    summary="ADR-128 F6: Get consumable-resource stock projection contract (faces x natureza x granularidade)",
)
def get_cubo_estoque_consumivel_projecao_contrato(
    project_id: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    _ = project_id
    return service.get_cubo_estoque_consumivel_projection_contract()


@router.get(
    "/{project_id}/cubo-roster-real/projecao",
    summary="ADR-174: Explore real roster cost by instance (categoria/grupo/instancia faces)",
)
def get_cubo_roster_real_projecao(
    project_id: str,
    version: str | None = Query(None),
    escopo_id: str = Query("default"),
    face: Literal[
        "resumo_por_instancia",
        "resumo_por_grupo",
        "resumo_por_categoria",
        "custo_temporal",
    ] = Query("resumo_por_instancia"),
    granularidade: Literal["semana", "mes", "trimestre", "ano"] = Query("mes"),
    categoria: Literal["MAO_OBRA", "EQUIPAMENTO"] | None = Query(None),
    grupo_id: str | None = Query(None),
    instancia_id: str | None = Query(None),
    top_n: int = Query(300, ge=1, le=2000),
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    try:
        return service.get_cubo_roster_real_projection(
            project_id,
            version=version,
            escopo_id=escopo_id,
            face=face,
            granularidade=granularidade,
            categoria=categoria,
            grupo_id=grupo_id,
            instancia_id=instancia_id,
            top_n=top_n,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/{project_id}/cubo-roster-real/projecao/contrato",
    summary="ADR-174: Get real roster cost projection contract (faces x natureza x granularidade)",
)
def get_cubo_roster_real_projecao_contrato(
    project_id: str,
    service: ConciliumService = Depends(get_concilium_service),
) -> dict[str, Any]:
    _ = project_id
    return service.get_cubo_roster_real_projection_contract()
