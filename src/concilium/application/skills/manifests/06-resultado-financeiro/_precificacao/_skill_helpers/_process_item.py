"""Skill 06 (_precificacao) — Planejamento e BDI.

Resolução do preço por categoria e processamento do item da EAP.
"""

from __future__ import annotations

from typing import Any

from concilium.domain.models.canonical import (
    ValidacaoItem,
)
from concilium.infrastructure.repositories.insumo import RepositorioInsumo

from ._cpu_fallback import (  # ty: ignore[unresolved-import]
    _preco_cat_fallback_composicao,
    _resolve_cpu_com_fallback,
    _validar_producao_id_ref,
)
from ._planejamento_entry import _build_planejamento_entry, _try_early_override  # ty: ignore[unresolved-import]
from ._preco_cpu import _compute_preco_cat_from_production  # ty: ignore[unresolved-import]
from ._validacao import (  # ty: ignore[unresolved-import]
    _apply_com_bdi_override,
    _apply_sem_bdi_override,
    _validate_encargos_separacao,
)


def _resolve_preco_cat_item(
    item: Any,
    cpu: dict,
    prod_lookup: dict,
    insumo_lookup: dict,
    repo: RepositorioInsumo,
    jurisdicao_id: str | None,
    overrides: dict | None,
    data_base: Any,
    erros_insumo: set,
    validacoes: list,
    preco_diesel: float,
    alpha_clt: float,
    alpha_mensalista: float,
    catalog_session: object | None,
) -> tuple[dict[str, float] | None, set[str], bool, float]:
    """NEP-032 D1: precificação bottom-up canônica, com fallback para composicao_itens.

    Hierarquia de fontes:
      1. derivar_precos_unitarios_sbdi(producao, insumos) — bottom-up via composição da equipe
      2. composicao_itens × preco_insumo — fallback para CPUs sem producao completa
      precos_unitarios_sbdi hard-coded nos JSONs é campo depreciado (emite VAL-PLAN-SBDI-LEGADO).

    Retorna também `usou_fallback_composicao` (issue #132): True quando a Fonte 1 (bottom-up,
    com base em produtividade) falhou e o preço caiu na Fonte 2 (composicao_itens × preco_insumo,
    sem relação com produtividade) — sinal de 1ª classe para correlacionar com o fallback de
    produtividade do schedule (skill-04) sobre o mesmo item.

    E `produtividade_catalogo` (ADR-162 D1): ρ_i resolvido na Fonte 1, 0.0 na Fonte 2 (não há
    produtividade catalogada quando o preço vem de composicao_itens).
    """
    # Fonte 1: bottom-up da composição da equipe (produção + insumos SICRO/SINAPI)
    preco_cat, produtividade_catalogo = _compute_preco_cat_from_production(
        cpu,
        prod_lookup,
        insumo_lookup,
        preco_diesel,
        alpha_clt,
        alpha_mensalista,
        validacoes,
        catalog_session=catalog_session,
    )

    if preco_cat is not None:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PLAN-BOTTOM-UP",
                status="INFO",
                mensagem=f"Item '{item.item_id}': preço unitário derivado de composição da equipe (NEP-032).",
            )
        )
        return preco_cat, set(), False, produtividade_catalogo

    preco_cat_fallback, equip_sem_decomp = _preco_cat_fallback_composicao(
        cpu, insumo_lookup, repo, jurisdicao_id, overrides, data_base, erros_insumo, validacoes
    )
    return preco_cat_fallback, equip_sem_decomp, True, 0.0


def _process_eap_item(
    item: Any,
    cpu_lookup: dict,
    insumo_lookup: dict,
    prod_lookup: dict,
    equipe_lookup: dict,
    planejamento_item_overrides: Any,
    bdi_aplicado: dict,
    repo: RepositorioInsumo,
    jurisdicao_id: str | None,
    overrides: dict | None,
    data_base: Any,
    plan_out: list,
    erros_eap: list,
    erros_insumo: set,
    equip_sem_decomp: set,
    validacoes: list,
    benchmark_mode: bool = False,
    preco_diesel: float = 6.20,
    alpha_clt: float = 1.777,
    alpha_mensalista: float = 1.060,
    catalog_session: object | None = None,  # ADR-100
) -> None:
    cpu = _resolve_cpu_com_fallback(item, cpu_lookup, validacoes, erros_eap)
    if cpu is None:
        return
    if not _validar_producao_id_ref(cpu, prod_lookup, validacoes):
        return
    early = _try_early_override(item, planejamento_item_overrides, bdi_aplicado, validacoes)
    if early is not None:
        plan_out.append(early)
        return

    preco_cat, equip_sem_decomp_item, usou_fallback_composicao, produtividade_catalogo = _resolve_preco_cat_item(
        item,
        cpu,
        prod_lookup,
        insumo_lookup,
        repo,
        jurisdicao_id,
        overrides,
        data_base,
        erros_insumo,
        validacoes,
        preco_diesel,
        alpha_clt,
        alpha_mensalista,
        catalog_session,
    )

    if preco_cat is None:
        return
    _validate_encargos_separacao(cpu.get("codigo", item.cpu_id), cpu, insumo_lookup, validacoes)
    equip_sem_decomp.update(equip_sem_decomp_item)
    item_override = (
        planejamento_item_overrides.get(item.item_id, {}) if isinstance(planejamento_item_overrides, dict) else {}
    )
    _apply_sem_bdi_override(item.item_id, item_override, preco_cat, validacoes)
    preco_cat_com_bdi = _apply_com_bdi_override(item.item_id, item_override, preco_cat, bdi_aplicado, validacoes)
    plan_out.append(
        _build_planejamento_entry(
            item,
            preco_cat,
            preco_cat_com_bdi,
            bdi_aplicado,
            precificacao_via_fallback_composicao=usou_fallback_composicao,
            produtividade_catalogo=produtividade_catalogo,
        )
    )


