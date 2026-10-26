"""Skill 05 — Equipes e Alocação (parte extraída de skill.py).

Instâncias de recurso e mapa de utilização (ADR-077).
"""

from __future__ import annotations

from typing import Any

from concilium.domain.models.canonical import (
    RecursoContrato,
    ValidacaoItem,
)

from ._custo_instancial_composicional import (  # ty: ignore[unresolved-import]
    _aplicar_custo_instancial,
)
from ._enrich_equipe_decomposicao import (  # ty: ignore[unresolved-import]
    _enrich_equipes_com_decomposicao_instancial,
)
from ._enrich_overhead_ocioso import (  # ty: ignore[unresolved-import]
    _enrich_particao_overhead,
)
from ._resource_instance_build import (  # ty: ignore[unresolved-import]
    _build_instancias_recurso,
)
from .planejamento import _plan_custo_sem_bdi_total  # ty: ignore[unresolved-import]


def _validar_instancia_recurso_ok(
    instancias_recurso: list, resumo_utilizacao_contratos: list, validacoes: list[ValidacaoItem]
) -> None:
    """ADR-077: emite a validação OK do mapeamento instancial, se houver contratos resumidos."""
    if not resumo_utilizacao_contratos:
        return
    n_ok = sum(1 for r in resumo_utilizacao_contratos if r.status_utilizacao == "OK")
    taxa_media = round(
        sum(r.taxa_utilizacao_pct for r in resumo_utilizacao_contratos) / len(resumo_utilizacao_contratos),
        1,
    )
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-INSTANCIA-RECURSO-OK",
            status="OK",
            mensagem=(
                f"ADR-077: {len(instancias_recurso)} instância(s) mapeadas em "
                f"{len(resumo_utilizacao_contratos)} contrato(s) — "
                f"{n_ok}/{len(resumo_utilizacao_contratos)} OK, "
                f"taxa média {taxa_media:.1f}%."
            ),
        )
    )


def _reconciliar_decomposicao_apos_teto_benchmark(eq: Any, capped: float) -> None:
    """Allocate benchmark-capped instancial K/V cents without losing a cent.

    Only pool-backed teams enter this cap stage; non-pool F3 components are
    populated later. Mob/demob is an *informational subcomponent* of the pool
    decomposition, not a fifth direct cost to count again.
    """
    names = ("custo_inst_mo", "custo_inst_eq", "custo_inst_mat", "custo_inst_comb")
    amounts = [getattr(eq, name, None) for name in names]
    if any(amount is None for amount in amounts):
        return
    values = [float(amount) for amount in amounts]
    total = sum(values)
    if total <= 0 or any(value < 0 for value in values):
        # Keep incomplete evidence visible, rather than manufacturing a new
        # itemized operational cost out of an unallocated benchmark limit.
        return

    cents_total = int(round(float(capped) * 100))
    component_cents = [int(round(value * 100)) for value in values]
    denominator = sum(component_cents)
    if denominator <= 0:
        return
    # All operations are in integer cents to avoid float drift in the
    # apportionment. A positive cap produces exactly its monetary cents.
    products = [cents_total * cents for cents in component_cents]
    allocations = [product // denominator for product in products]
    remaining = cents_total - sum(allocations)
    by_remainder = sorted(
        range(len(names)), key=lambda i: (-(products[i] % denominator), i)
    )
    for i in by_remainder[:remaining]:
        allocations[i] += 1
    for name, cents in zip(names, allocations):
        setattr(eq, name, cents / 100)

    mob = getattr(eq, "custo_inst_mob_demob", None)
    if mob is not None:
        # Mob/demob was included in the original instancial partition and
        # should not continue displaying an unadjusted pre-cap amount.
        eq.custo_inst_mob_demob = round(float(mob) * capped / total, 2)


def _limitar_custo_por_planejamento_benchmark(
    equipes: list,
    benchmark_mode: bool,
    planejamento_map: dict[str, Any],
    planejamento_ref_map: dict[str, float],
) -> None:
    """Em benchmark, limita custo_total instancial ao custo de referência do planejamento."""
    if not (benchmark_mode and (planejamento_map or planejamento_ref_map)):
        return
    for eq in equipes:
        custo_ref = 0.0
        plan = planejamento_map.get(eq.item_id)
        if plan is not None:
            custo_ref = _plan_custo_sem_bdi_total(plan)
        elif eq.item_id in planejamento_ref_map:
            custo_ref = planejamento_ref_map[eq.item_id]
        if custo_ref > 0:
            capped = min(eq.custo_total, round(custo_ref, 2))
            if capped < eq.custo_total:
                # The instancial breakdown was populated *before* this
                # benchmark-only cap. It must be adjusted together with the
                # authoritative total; otherwise Skill06 bills the uncapped
                # components against an expense that has been capped.
                _reconciliar_decomposicao_apos_teto_benchmark(eq, capped)
                eq.custo_total = capped


def _validar_estagio4_inst_missing(
    equipes: list, contratos_recurso: list[RecursoContrato], validacoes: list[ValidacaoItem]
) -> None:
    """ADR-104 Checkpoint 3: Estágio 4 — custo_inst_* deve estar preenchido para items em contratos."""
    items_em_contratos = {item_id for c in contratos_recurso for item_id in c.items_cobertos}
    for eq in equipes:
        if eq.item_id in items_em_contratos and eq.custo_inst_mo is None:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-ESTAG4-INST-MISSING",
                    status="ERRO",
                    mensagem=f"Item {eq.item_id}: custo_inst_* deve estar preenchido no Estágio 4",
                )
            )


def _processar_instancias_recurso(
    contratos_recurso: list[RecursoContrato],
    rcpsp_spec: dict | None,
    cron_lookup: dict,
    validacoes: list[ValidacaoItem],
    cadeias_perpetuacao: list,
    equipes: list,
    benchmark_mode: bool,
    planejamento_map: dict[str, Any],
    planejamento_ref_map: dict[str, float],
) -> tuple[list, list, list]:
    """ADR-077/083/085: mapa instancial de utilização e custo instancial composicional."""
    instancias_recurso: list = []
    composicao_equipes_atividade: list = []
    resumo_utilizacao_contratos: list = []
    if not (contratos_recurso and rcpsp_spec):
        return instancias_recurso, composicao_equipes_atividade, resumo_utilizacao_contratos

    instancias_recurso, composicao_equipes_atividade, resumo_utilizacao_contratos = _build_instancias_recurso(
        contratos_recurso, rcpsp_spec, cron_lookup, validacoes
    )
    _validar_instancia_recurso_ok(instancias_recurso, resumo_utilizacao_contratos, validacoes)

    # ADR-083: enriquece overhead_ocioso / custo_ocioso_imputado com gaps instanciais reais
    if instancias_recurso and cadeias_perpetuacao:
        _enrich_particao_overhead(contratos_recurso, cadeias_perpetuacao, instancias_recurso)

    # ADR-085: substitui custo_total_contrato pelo custo instancial composicional
    # (mob tardia + taxa ociosa por componente + desmob antecipada efetiva).
    # Executado por último: reescala atribuição/partição preservando a invariante
    # Σ custo_total_particionado == custo_total_contrato e atualiza eq.custo_total (N4).
    if instancias_recurso:
        _aplicar_custo_instancial(contratos_recurso, instancias_recurso, equipes, validacoes)
        _enrich_equipes_com_decomposicao_instancial(equipes, contratos_recurso, validacoes)
        _limitar_custo_por_planejamento_benchmark(equipes, benchmark_mode, planejamento_map, planejamento_ref_map)
        _validar_estagio4_inst_missing(equipes, contratos_recurso, validacoes)

    return instancias_recurso, composicao_equipes_atividade, resumo_utilizacao_contratos


def _preencher_custo_inst_estagio_f3(equipes: list) -> None:
    """ADR-106 F3: preenche custo_inst_* para equipes sem pool contract (best-effort)."""
    try:
        from concilium.domain.services.financial.equipe_custo_engine import _fill_custo_inst_sem_pool

        _fill_custo_inst_sem_pool(equipes)
    except Exception:
        pass  # F3 é best-effort; não bloqueia o pipeline


