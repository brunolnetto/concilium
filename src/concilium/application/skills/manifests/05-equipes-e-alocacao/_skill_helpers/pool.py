"""Skill 05 — Equipes e Alocação (parte extraída de skill.py).

Pool setup, rcpsp spec e pool contracts (ADR-071/073).
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any

from concilium.application.scheduling.exact_rcpsp_derivation import derive_exact_rcpsp_spec
from concilium.application.scheduling.p16_tariff_derivation import derive_p16_tariffs
from concilium.domain.models.canonical import (
    CanonicalModel,
    RecursoContrato,
    ValidacaoItem,
)

from ._pool_contrato_construcao import (  # ty: ignore[import-not-found]
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


def _build_pool_setup(canonical_in: CanonicalModel, catalogo: dict[str, Any]) -> tuple[dict, dict, dict]:
    """Monta os lookups de cronograma/catálogo usados na derivação de contratos de pool."""
    sched_acts = canonical_in.cronograma.scheduled_activities if canonical_in.cronograma else []
    cron_lookup = {sa.activity_id: sa for sa in sched_acts}
    # Indexes usados por enriquecer_composicao_por_tipo (ADR-159) — composição, não custo.
    cpu_lookup: dict = {c["codigo"]: c for c in catalogo.get("cpus", []) if c.get("codigo")}
    prod_lookup: dict = {
        p.get("id") or p.get("codigo", ""): p
        for p in (catalogo.get("producoes") or catalogo.get("produtividades") or [])
    }
    return cron_lookup, cpu_lookup, prod_lookup


def _resolve_rcpsp_spec(
    inputs: dict[str, Any],
    canonical_in: CanonicalModel,
    catalogo: dict[str, Any],
    validacoes: list[ValidacaoItem] | None = None,
) -> tuple[dict | None, bool]:
    """Resolve o rcpsp_spec explícito ou o deriva automaticamente do canônico.

    #206: without a caller-supplied spec, the per-resource spec is derived from
    the project's own data and its P16 tariffs come from the catalog rate plus
    the project's declared ``contract_terms`` (N8). Resources without complete
    declared terms get no tariff (UNKNOWN_CONTRACT, reported) — never an
    estimate. Only when the per-resource spec cannot be derived does the
    legacy team-family derivation remain (to be removed with the legacy path).
    """
    rcpsp_spec = inputs.get("rcpsp_spec") if isinstance(inputs.get("rcpsp_spec"), dict) else None
    if rcpsp_spec is not None:
        return rcpsp_spec, False

    exact_spec, _gaps = derive_exact_rcpsp_spec(canonical_in, catalogo)
    if exact_spec is not None:
        regime = canonical_in.projeto.regime_trabalho
        currency = catalogo.get("currency")
        tariffs, unknown = derive_p16_tariffs(
            exact_spec["resource_pool"],
            catalogo,
            dias_semana=int(regime.dias_semana),
            horas_dia=Fraction(str(regime.horas_dia)),
            declarations=inputs.get("contract_terms"),
            currency=currency if isinstance(currency, str) else "",
            catalog_reference=str(canonical_in.projeto.snapshot_catalogo_id or "catalog"),
        )
        if tariffs:
            exact_spec["p16_exact_tariffs"] = tariffs
        if unknown and validacoes is not None:
            sample = "; ".join(f"{k}: {v}" for k, v in list(sorted(unknown.items()))[:4])
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-P16-CONTRATO-DESCONHECIDO",
                    status="AVISO",
                    mensagem=(
                        f"{len(unknown)} tipo(s) de recurso sem termos contratuais completos "
                        f"(UNKNOWN_CONTRACT): custo não avaliado, sem estimativa. {sample}"
                    ),
                )
            )
        return exact_spec, False

    rcpsp_spec = _derive_rcpsp_from_canonical(canonical_in, catalogo)
    return rcpsp_spec, rcpsp_spec is not None


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
            # Mob/demob standalone não ocorre — pool gerencia via RecursoContrato.custo_mob_desmob_contrato.
            # Zerar evita que _transporte_ja_contabilizado_direto deduza o custo standalone
            # do bucket MOB indireto mesmo sem ele estar no custo direto.
            eq.custo_mobilizacao_mensal = 0.0
            eq.custo_desmobilizacao_mensal = 0.0
            eq.custo_mob_desmob = 0.0


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
    benchmark_mode: bool,
) -> tuple[list[RecursoContrato], list]:
    """ADR-071/073: deriva contratos de pool e cadeias de perpetuação a partir do rcpsp_spec."""
    contratos_recurso, atribuicao, cadeias_perpetuacao = _build_contratos_recurso(
        equipes,
        rcpsp_spec,
        cron_lookup,
        validacoes,
    )
    _atualizar_custo_via_atribuicao(equipes, atribuicao, benchmark_mode)
    if contratos_recurso:
        _validar_pool_contrato_ok(contratos_recurso, cadeias_perpetuacao, rcpsp_spec, rcpsp_derivado, validacoes)
        _validar_estagio3_inst_none(equipes, atribuicao, validacoes)
    return contratos_recurso, cadeias_perpetuacao


