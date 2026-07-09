"""Skill 05 — Equipes e Alocação (parte extraída de skill.py).

Pool setup, rcpsp spec e pool contracts (ADR-071/073).
"""

from __future__ import annotations

from typing import Any

from concilium.domain.models.canonical import (
    CanonicalModel,
    RecursoContrato,
    ValidacaoItem,
)

from ._pool_contrato_construcao import (  # ty: ignore[unresolved-import]
    _build_contratos_recurso,
    _derive_rcpsp_from_canonical,
)


def _validar_estagio1_inst_none(equipes: list, validacoes: list[ValidacaoItem]) -> None:
    """ADR-104 Checkpoint 1: Estágio 1 — custo_inst_* deve estar None (sem pool contracts ainda)."""
    for eq in equipes:
        if eq.custo_inst_mo is not None:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-ESTAG1-INST-NONE",
                    status="ERRO",
                    mensagem=f"Item {eq.item_id}: custo_inst_* deve estar None no Estágio 1",
                )
            )


def _build_pool_setup(canonical_in: CanonicalModel, catalogo: dict[str, Any]) -> tuple[dict, dict, dict, float]:
    """Monta os lookups de cronograma/catálogo e horas/semana usados na derivação de contratos de pool."""
    sched_acts = canonical_in.cronograma.scheduled_activities if canonical_in.cronograma else []
    cron_lookup = {sa.activity_id: sa for sa in sched_acts}
    # Indexes para custo_hora_total_referencia do catálogo → custo_unit_semanal de catálogo
    cpu_lookup: dict = {c["codigo"]: c for c in catalogo.get("cpus", []) if c.get("codigo")}
    prod_lookup: dict = {
        p.get("id") or p.get("codigo", ""): p
        for p in (catalogo.get("producoes") or catalogo.get("produtividades") or [])
    }
    regime = canonical_in.projeto.regime_trabalho
    horas_semana = float(regime.horas_dia * regime.dias_semana)
    return cron_lookup, cpu_lookup, prod_lookup, horas_semana


def _resolve_rcpsp_spec(
    inputs: dict[str, Any], canonical_in: CanonicalModel, catalogo: dict[str, Any]
) -> tuple[dict | None, bool]:
    """Resolve o rcpsp_spec explícito ou o deriva automaticamente do canônico."""
    rcpsp_spec = inputs.get("rcpsp_spec") if isinstance(inputs.get("rcpsp_spec"), dict) else None
    rcpsp_derivado = False
    if rcpsp_spec is None:
        rcpsp_spec = _derive_rcpsp_from_canonical(canonical_in, catalogo)
        rcpsp_derivado = rcpsp_spec is not None
    return rcpsp_spec, rcpsp_derivado


def _atualizar_custo_via_atribuicao(equipes: list, atribuicao: dict, benchmark_mode: bool) -> None:
    """Atualiza custo_total de cada equipe coberta pelo pool contract."""
    for eq in equipes:
        if eq.item_id in atribuicao:
            custo_attr, tipo_id, frac = atribuicao[eq.item_id]
            eq.custo_total_autonomo = eq.custo_total
            # Em benchmark, preservar comparabilidade com baseline de catálogo
            # (ADR-085): custo instancial não deve exceder o custo planejado.
            if benchmark_mode:
                eq.custo_total = min(custo_attr, eq.custo_total)
            else:
                eq.custo_total = custo_attr
            eq.contrato_tipo_id = tipo_id
            eq.fracao_atribuicao = frac


def _validar_pool_contrato_ok(
    contratos_recurso: list[RecursoContrato],
    cadeias_perpetuacao: list,
    rcpsp_spec: dict,
    rcpsp_derivado: bool,
    validacoes: list[ValidacaoItem],
) -> None:
    """Emite as validações OK de contrato de pool (ADR-071) e perpetuação (ADR-073)."""
    tipos_ids = ", ".join(c.tipo_id for c in contratos_recurso)
    total_contratos = sum(c.custo_total_contrato for c in contratos_recurso)
    n_cadeias = sum(c.n_cadeias for c in contratos_recurso)
    if rcpsp_derivado:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-POOL-SPEC-DERIVADO",
                status="OK",
                mensagem=(
                    "rcpsp_spec não fornecido — derivado automaticamente do canônico "
                    f"(EAP+catálogo). {len(rcpsp_spec.get('activities', []))} atividades, "
                    f"{len(rcpsp_spec.get('resource_pool', {}))} tipos de recurso."
                ),
            )
        )
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-POOL-CONTRATO-OK",
            status="OK",
            mensagem=(
                f"ADR-071: {len(contratos_recurso)} contrato(s) de pool gerado(s) "
                f"[{tipos_ids}] — custo total R$ {total_contratos:,.2f}."
            ),
        )
    )
    if cadeias_perpetuacao:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PERPETUACAO-OK",
                status="OK",
                mensagem=(
                    f"ADR-073: {len(cadeias_perpetuacao)} cadeia(s) de perpetuação "
                    f"({n_cadeias} total mob/demob vs "
                    f"{sum(len(c.items_cobertos) for c in contratos_recurso)} naive)."
                ),
            )
        )


def _validar_estagio3_inst_none(equipes: list, atribuicao: dict, validacoes: list[ValidacaoItem]) -> None:
    """ADR-104 Checkpoint 2: Estágio 3 — custo_total atualizado, mas custo_inst_* ainda None."""
    for eq in equipes:
        if eq.item_id in atribuicao and eq.custo_inst_mo is not None:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-ESTAG3-INST-NONE",
                    status="AVISO",
                    mensagem=f"Item {eq.item_id}: custo_inst_* preenchido antes de ADR-085?",
                )
            )


def _processar_pool_contratos(
    equipes: list,
    rcpsp_spec: dict,
    rcpsp_derivado: bool,
    cron_lookup: dict,
    validacoes: list[ValidacaoItem],
    cpu_lookup: dict,
    prod_lookup: dict,
    horas_semana: float,
    benchmark_mode: bool,
) -> tuple[list[RecursoContrato], list]:
    """ADR-071/073: deriva contratos de pool e cadeias de perpetuação a partir do rcpsp_spec."""
    contratos_recurso, atribuicao, cadeias_perpetuacao = _build_contratos_recurso(
        equipes,
        rcpsp_spec,
        cron_lookup,
        validacoes,
        cpu_lookup=cpu_lookup,
        prod_lookup=prod_lookup,
        horas_semana=horas_semana,
    )
    _atualizar_custo_via_atribuicao(equipes, atribuicao, benchmark_mode)
    if contratos_recurso:
        _validar_pool_contrato_ok(contratos_recurso, cadeias_perpetuacao, rcpsp_spec, rcpsp_derivado, validacoes)
        _validar_estagio3_inst_none(equipes, atribuicao, validacoes)
    return contratos_recurso, cadeias_perpetuacao


