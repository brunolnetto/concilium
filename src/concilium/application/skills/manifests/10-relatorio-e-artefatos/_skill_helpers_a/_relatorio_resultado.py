"""Skill 07 — Adapter de Saída (gera JSON + Excel .xlsm) — seção RESULTADO e montagem do relatório."""

from datetime import UTC, datetime
from typing import Any

from ._compressao_cronograma import (  # ty: ignore[unresolved-import]
    _rra_build_compressao_cronograma,
    _rra_build_decomposicao_pool,
)
from ._planejamento import _build_tres_camadas_rows  # ty: ignore[unresolved-import]
from ._relatorio_pe import _rra_build_pe_rows  # ty: ignore[unresolved-import]


def _rrs_num(value: Any) -> float | None:
    """Converte para float, retornando None em caso de valor ausente ou inválido."""
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _rrs_delta_pct(tool: float, ref: float) -> float | None:
    """Calcula a variação percentual da ferramenta em relação à referência."""
    return round((tool - ref) / ref * 100, 2) if ref and ref > 0 else None


def _rrs_custo_indireto_calc(res: Any) -> float:
    """Soma os componentes de custo indireto (adm/top/lab/qsms/mob) do resultado."""
    return (
        float(res.custo.indireto_adm or 0.0)
        + float(res.custo.indireto_top or 0.0)
        + float(res.custo.indireto_lab or 0.0)
        + float(res.custo.indireto_qsms or 0.0)
        + float(res.custo.indireto_mob or 0.0)
    )


def _rrs_preco_venda_e_custo_total(
    res: Any, custo_direto_auth: float, custo_indireto_calc: float
) -> tuple[float, float]:
    """Calcula preco_venda_total (operacional) e custo_total_calc (canônico, com fallback local)."""
    # ADR-085/ADR-114: preço de venda é o OPERACIONAL (total_custo_plus = custo_instancial×BDI + indiretos),
    # NÃO o de catálogo (total_com_bdi = PU_catalogo×Q×BDI). A margem é calculada sobre o preço que
    # a empresa cobra pelo que realmente executa — o catálogo serve como referência de mercado, não
    # como base de precificação operacional.
    preco_venda_total = float(
        getattr(res.venda, "total_custo_plus", None) or getattr(res.venda, "total_com_bdi", None) or 0.0
    )
    # Usar custo.total do modelo como fonte autoritativa (inclui todos os componentes
    # calculados por skill-08). Fallback para recálculo local apenas quando ausente.
    custo_total_canonical = float(res.custo.total or 0.0) if res.custo.total else None
    custo_total_calc = (
        custo_total_canonical if custo_total_canonical is not None else custo_direto_auth + custo_indireto_calc
    )
    return preco_venda_total, custo_total_calc


def _rrs_compute_custos(res: Any) -> tuple[float, float, float, float, float]:
    """Calcula direto_equipes, custo_direto_auth, custo_indireto_calc, preco_venda_total e custo_total_calc."""
    direto_equipes = float(res.custo.direto_equipes or 0.0)
    # Fonte autoritativa única do relatório: custo direto operacional instancial (direto_equipes).
    custo_direto_auth = direto_equipes

    custo_indireto_calc = _rrs_custo_indireto_calc(res)
    preco_venda_total, custo_total_calc = _rrs_preco_venda_e_custo_total(res, custo_direto_auth, custo_indireto_calc)
    return direto_equipes, custo_direto_auth, custo_indireto_calc, preco_venda_total, custo_total_calc


def _rrs_compute_razao_margem(
    custo_direto_auth: float, custo_indireto_calc: float, preco_venda_total: float, custo_total_calc: float
) -> tuple[float, float]:
    """Calcula razao_indireto_direto e margem_pct a partir dos valores centrais do resultado."""
    # Valores calculados são sempre a fonte primária do relatório (NEP-030).
    # A referência fica armazenada separadamente para a seção de confronto.
    razao_id = custo_indireto_calc / custo_direto_auth if custo_direto_auth > 0 else 0
    margem_pct = (preco_venda_total - custo_total_calc) / preco_venda_total if preco_venda_total > 0 else 0
    return razao_id, margem_pct


def _rrs_compute_core(res: Any) -> tuple[float, float, float, float, float, float, float]:
    """Calcula os valores centrais (custos, preço de venda, razão e margem) do resultado."""
    direto_equipes, custo_direto_auth, custo_indireto_calc, preco_venda_total, custo_total_calc = _rrs_compute_custos(
        res
    )
    razao_id, margem_pct = _rrs_compute_razao_margem(
        custo_direto_auth, custo_indireto_calc, preco_venda_total, custo_total_calc
    )
    return (
        direto_equipes,
        custo_direto_auth,
        custo_indireto_calc,
        preco_venda_total,
        custo_total_calc,
        razao_id,
        margem_pct,
    )


def _rrs_build_referencia(
    benchmark_reference_projection: dict[str, Any] | None,
    custo_direto_auth: float,
    custo_indireto_calc: float,
    preco_venda_total: float,
) -> dict | None:
    """Extrai a seção de confronto (apenas exibição) a partir da projeção de referência."""
    if not isinstance(benchmark_reference_projection, dict):
        return None
    ref_direto = _rrs_num(benchmark_reference_projection.get("custo_direto"))
    ref_indireto = _rrs_num(benchmark_reference_projection.get("custo_indireto"))
    ref_total = _rrs_num(benchmark_reference_projection.get("custo_total"))
    ref_preco = _rrs_num(benchmark_reference_projection.get("preco_venda"))
    if not (ref_preco and ref_preco > 0):
        return None
    return {
        "custo_direto": ref_direto,
        "custo_indireto": ref_indireto,
        "custo_total": ref_total,
        "preco_venda": ref_preco,
        "delta_custo_direto_pct": _rrs_delta_pct(custo_direto_auth, ref_direto) if ref_direto else None,
        "delta_custo_indireto_pct": _rrs_delta_pct(custo_indireto_calc, ref_indireto) if ref_indireto else None,
        "delta_preco_venda_pct": _rrs_delta_pct(preco_venda_total, ref_preco),
    }


def _rra_build_resultado_section(
    res: Any,
    benchmark_mode: bool = False,
    benchmark_reference_projection: dict[str, Any] | None = None,
) -> dict:
    """Builds resultado section dict."""
    (
        direto_equipes,
        custo_direto_auth,
        custo_indireto_calc,
        preco_venda_total,
        custo_total_calc,
        razao_id,
        margem_pct,
    ) = _rrs_compute_core(res)
    custo_direto_fonte = "operacional_equipes"

    referencia = _rrs_build_referencia(
        benchmark_reference_projection, custo_direto_auth, custo_indireto_calc, preco_venda_total
    )

    return {
        "preco_venda_total": preco_venda_total,
        "custo_total": custo_total_calc,
        "custo_direto": custo_direto_auth,
        "custo_direto_equipes": direto_equipes,
        "custo_direto_fonte": custo_direto_fonte,
        "benchmark_guard_aplicado": False,  # guard removido (NEP-030)
        "custo_indireto": custo_indireto_calc,
        "razao_indireto_direto": razao_id,
        "resultado_bruto": preco_venda_total - custo_total_calc,
        "margem_pct": margem_pct,
        "status_margem": res.status_margem,
        "referencia": referencia,
    }


def _rra_build_actionable_insights(canonical_in: Any) -> dict:
    """Builds ACTIONABLE_INSIGHTS dict."""

    def _dump(obj: Any) -> Any:
        return obj.model_dump(mode="json") if obj else None

    return {
        "criticidade": _dump(canonical_in.relatorio_criticidade),
        "sensibilidade": _dump(canonical_in.relatorio_sensibilidade),
        "intervencao": _dump(canonical_in.relatorio_intervencao),
    }


def _rra_build_relatorio(
    canonical_in: Any,
    proj: Any,
    res: Any,
    planejamento_rows: list,
    equipe_rows: list,
    analise_composicional: list,
    indireto_rows: list,
    graficos: Any,
    eap_by_item_id: dict,
    project_months: list,
    benchmark_mode: bool = False,
    benchmark_reference_projection: dict[str, Any] | None = None,
) -> dict:
    """Assembles the full relatorio dict."""
    resultado_section = _rra_build_resultado_section(
        res,
        benchmark_mode=benchmark_mode,
        benchmark_reference_projection=benchmark_reference_projection,
    )
    validacoes_pipeline = [{"codigo": v.codigo, "status": v.status, "mensagem": v.mensagem} for v in res.validacoes]
    return {
        "meta": {
            "gerado_em": datetime.now(UTC).isoformat(),
            "framework": "concilium",
            "adapter": "relatorio_validacao_v1",
            "nota": "Relatório de validação na ausência do template .xlsm original.",
        },
        "resumo": {
            "projeto": proj.nome,
            "tipo_obra": proj.tipo_obra,
            "localizacao": (
                f"lat={proj.localizacao.lat:.5f}, lng={proj.localizacao.lng:.5f}"
                if hasattr(proj.localizacao, "lat")
                else proj.localizacao
            ),
            "periodo": f"{proj.data_inicio} -> {proj.data_termino}",
            "status": proj.status,
        },
        "PLANEJAMENTO": planejamento_rows,
        "EQUIPE": equipe_rows,
        "analise_composicional": analise_composicional,
        "INDIRETOS": indireto_rows,
        "RESULTADO": resultado_section,
        "GRAFICOS": graficos,
        "ponto_equilibrio": _rra_build_pe_rows(canonical_in, resultado_section),
        # NEP-042 D4: view consolidada das três camadas de precificação por item
        "PRECO_UNITARIO_TRES_CAMADAS": _build_tres_camadas_rows(canonical_in),
        "ACTIONABLE_INSIGHTS": _rra_build_actionable_insights(canonical_in),
        "validacoes_pipeline": validacoes_pipeline,
        # ADR-077: mapa instancial de utilização
        "resumo_utilizacao_contratos": [r.model_dump() for r in (canonical_in.resumo_utilizacao_contratos or [])],
        "instancias_recurso": [i.model_dump() for i in (canonical_in.instancias_recurso or [])],
        # ADR-086: decomposição explorável de pool (faces físicas + causais + narrativa honesta)
        "decomposicao_pool": _rra_build_decomposicao_pool(canonical_in),
        # ADR-078: pré-processamento estrutural de compartilhamento
        "relatorio_oportunidades": (
            canonical_in.relatorio_oportunidades.model_dump() if canonical_in.relatorio_oportunidades else None
        ),
        # NEP-038: análise de compressão de cronograma por k-scaling
        "COMPRESSAO_CRONOGRAMA": _rra_build_compressao_cronograma(canonical_in),
    }


