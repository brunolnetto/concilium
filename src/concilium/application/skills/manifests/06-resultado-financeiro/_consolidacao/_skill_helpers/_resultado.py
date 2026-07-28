"""Skill 06 (_consolidacao) — Consolidação Financeira (parte extraída de _skill_helpers_a.py)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from concilium.domain.models.canonical import (
    CanonicalModel,
    CustoTotal,
    Resultado,
    ValidacaoItem,
    Venda,
)

from ._venda_custo import (  # ty: ignore[unresolved-import]
    _br_append_gap_catalogo_validacao,
    _br_build_venda_custo,
    _calc_venda_com_bdi,
    _validate_ac_adm_sobreposicao,
)

if TYPE_CHECKING:
    from concilium.domain.models.financial.bdi import TabelaBdi

from ._bdi_resolucao import (  # ty: ignore[unresolved-import]
    _classificar_margem,
    _frac_locacao_equipamentos,
    _resolve_bdi_full,
)


def _build_resultado(
    canonical_in: CanonicalModel, inputs: dict, validacoes: list, perfil: dict
) -> tuple[
    Resultado,
    dict[str, float],
    TabelaBdi,
    str,
    str,
    bool,
    float,
    float,
    float,
    float,
    str,
    float,
    float,
    float,
]:
    """Computa resultado financeiro e retorna.

    Returns: (res, bdi_rates, bdi_tabela, bdi_fonte, bdi_regime, bdi_override,
    venda_sem_bdi, venda_catalogo_plus, margem, custo_direto_equipe, status_margem,
    venda_plus, custo_operacional_real, custo_total_catalogo).
    """
    venda_sem_bdi, venda_com_bdi, custo_direto_equipe, _custo_mat, custo_direto = _br_build_venda_custo(canonical_in)
    frac_locacao = _frac_locacao_equipamentos(canonical_in)
    bdi_rates, _bdi_tabela, _bdi_fonte, _bdi_regime, _bdi_override = _resolve_bdi_full(
        inputs, validacoes, frac_locacao
    )
    bdi_indireto_efetivo = inputs.get("bdi_indireto_efetivo")
    if not isinstance(bdi_indireto_efetivo, (int, float)):
        bdi_indireto_efetivo = None
    venda_direto_eq, venda_indireto, custo_indireto_total = _calc_venda_com_bdi(
        canonical_in,
        bdi_rates,
        bdi_indireto_efetivo,
    )
    custos_indiretos = {ind.categoria: ind.custo_total for ind in canonical_in.indiretos}

    venda_catalogo_plus = round(venda_com_bdi + venda_indireto, 2)  # N1×BDI — usado só na bridge
    venda_plus = round(venda_direto_eq + venda_indireto, 2)  # preço operacional (base do resultado)

    # ── Pricing consolidado ───────────────────────────────────────────────────────
    # custo_operacional_real: pool (produtivo + idle + mob/demob) + indiretos.
    # venda_plus: BDI aplicado sobre custo operacional real por componente.
    # Margem sempre sobre venda_plus — venda_catalogo_plus é referência de mercado (bridge/N1).
    custo_operacional_real = round(custo_direto + custo_indireto_total, 2)
    resultado_fin = round(venda_plus - custo_operacional_real, 2)
    margem = resultado_fin / venda_plus if venda_plus > 0 else 0.0

    # markup efetivo: venda_catalogo_plus / custo_real (para auditoria do consolidado)
    bdi_lucro = (venda_catalogo_plus / custo_operacional_real - 1) if custo_operacional_real > 0 else 0.0

    # custo_total_catalogo preservado para o confronto de benchmark (PU×Q + indireto)
    custo_total_catalogo = venda_sem_bdi + custo_indireto_total

    status_margem = _classificar_margem(margem, perfil["faixa_margem_alvo"], perfil["faixa_margem_aceitavel"])
    status_val = "OK" if status_margem != "VERMELHO" else "AVISO"
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-CONSOL-MARGEM",
            status=status_val,
            mensagem=(
                f"Margem operacional {margem * 100:.2f}% | status={status_margem} "
                f"| preço R$ {venda_plus:,.0f} (operacional) vs R$ {venda_catalogo_plus:,.0f} (catálogo)"
            ),
        )
    )
    _br_append_gap_catalogo_validacao(validacoes, venda_sem_bdi, custo_direto)
    _validate_ac_adm_sobreposicao(
        _bdi_tabela.indireto.ac,
        custo_indireto_total,
        custos_indiretos.get("ADM", 0.0),
        custo_operacional_real,
        validacoes,
    )
    indir_kwargs = {f"indireto_{k.lower()}": v for k, v in custos_indiretos.items() if k != "MOB"}
    res = Resultado(
        venda=Venda(
            total_sem_bdi=venda_sem_bdi,
            # total_com_bdi mantém contrato histórico de benchmark (PU×Q×BDI + indiretos).
            # A visão operacional (custo instancial × BDI) segue em total_custo_plus.
            total_com_bdi=venda_catalogo_plus,
            total_custo_plus=venda_plus,
            # total_custo_plus_catalogo: benchmark de mercado (PU×Q×BDI).
            # Lido por projection.py para o gate do confronto — benchmark estável.
            total_custo_plus_catalogo=venda_catalogo_plus,
            bdi_lucro_impostos=bdi_lucro,
        ),
        custo=CustoTotal(
            direto_equipes=custo_direto,
            # total agora é o custo operacional real (não o catálogo+indireto)
            total=custo_operacional_real,
            **indir_kwargs,
            indireto_mob=custos_indiretos.get("MOB", 0),
        ),
        resultado_financeiro=resultado_fin,
        margem_pct=margem,
        status_margem=status_margem,
        validacoes=[],
    )
    return (
        res,
        bdi_rates,
        _bdi_tabela,
        _bdi_fonte,
        _bdi_regime,
        _bdi_override,
        venda_sem_bdi,
        venda_catalogo_plus,
        margem,
        custo_direto_equipe,
        status_margem,
        venda_plus,
        custo_operacional_real,
        custo_total_catalogo,
    )


def _lesao_aggregates(dist: dict) -> tuple[float, int, float, float, int, float]:
    """Agrega team_weeks/active_weeks/somas de clima-calendário/semanas lesadas/eMW."""
    team_weeks = sum(d.num_equipes for d in dist.values())
    active_weeks = sum(1 for d in dist.values() if d.num_equipes > 0)
    soma_clima = sum(getattr(d, "fator_clima", 1.0) * d.num_equipes for d in dist.values())
    soma_cal = sum(getattr(d, "fator_calendario", 1.0) * d.num_equipes for d in dist.values())
    semanas_lesadas = sum(1 for d in dist.values() if getattr(d, "fator_clima", 1.0) < 0.90)
    # NEP-042 TD-3: eMW_i = Σ_j(m_{ij} × η_j) usando fator_total (= η_s·η_p·η_w)
    # Preferir fator_total quando disponível; fallback para fator_clima × fator_calendario
    emw = sum(
        d.num_equipes
        * float(
            getattr(d, "fator_total", None) or (getattr(d, "fator_clima", 1.0) * getattr(d, "fator_calendario", 1.0))
        )
        for d in dist.values()
    )
    return team_weeks, active_weeks, soma_clima, soma_cal, semanas_lesadas, emw


def _lesao_from_sched(sched: Any) -> dict:
    """Extrai fatores de lesão de produtividade de uma ScheduledActivityCanonical."""
    dist = getattr(sched, "distribuicao_semanal", None) or {}
    if not dist:
        return {}
    team_weeks, active_weeks, soma_clima, soma_cal, semanas_lesadas, emw = _lesao_aggregates(dist)
    if team_weeks == 0:
        return {}
    return {
        "team_weeks": team_weeks,
        "active_weeks": active_weeks,
        "effective_machine_weeks": round(emw, 4),
        "fator_clima": round(soma_clima / team_weeks, 4),
        "fator_cal": round(soma_cal / team_weeks, 4),
        "semanas_lesadas_clima": semanas_lesadas,
    }


def _build_diagnostico_lesao(
    n_equipes: float,
    fator_clima: float,
    semanas_lesadas: int,
    semanas_ativas: int,
    gap_escala: float,
    gap_pool: float,
) -> str:
    """Gera texto de justificativa de lesão para o campo diagnostico_lesao."""
    partes: list[str] = []

    # Lesão por escala de equipes
    if n_equipes > 1.05:
        partes.append(
            f"{n_equipes:.1f} equipes simultaneas (compressao de prazo): "
            f"+{(n_equipes - 1.0) * 100:.0f}% custo sobre 1 equipe."
        )

    # Lesão climática
    lesao_clima_pct = (1.0 - fator_clima) * 100
    if lesao_clima_pct > 0.5 and semanas_lesadas > 0:
        partes.append(
            f"{semanas_lesadas} sem. de {semanas_ativas} com clima < 90% "
            f"(f_clima={fator_clima:.3f}, lesao {lesao_clima_pct:.1f}% da produtividade horaria)."
        )

    # Pool overhead
    if gap_pool > 1_000:
        partes.append(f"Overhead de pool: R$ {gap_pool:,.0f} (ociosidade do contrato compartilhado).")

    if not partes:
        return "Sem desvio significativo identificado."
    return " | ".join(partes)


