"""Skill 06 (_consolidacao) — Consolidação Financeira (parte extraída de _skill_helpers_a.py)."""

from __future__ import annotations

from typing import Any

from concilium.domain.models.canonical import CanonicalModel


def _resolve_custo_equipe_agregado(equipe: Any) -> float:
    """Issue #139 (parte 2): custo agregado real (todas as frentes) desta equipe,
    consistente com a cobertura de pool.

    - Coberta por pool (`contrato_tipo_id` preenchido): `custo_total` já É o custo real
      agregado ajustado pelo contrato (corrigido na issue #139 — pode diferir do custo
      autônomo por economia de escala compartilhada ou ociosidade imputada; usar o
      agregado autônomo aqui reintroduziria o mesmo tipo de inconsistência).
    - Sem pool: `custo_total` continua "1 frente" (ADR-091/ADR-162 D4) — usa
      `custo_operacional_agregado` (ADR-172, integral semana a semana, robusto a rampa),
      com fallback nominal (`custo_total × num_equipes_base`) quando o campo novo não
      está disponível (dados antigos/testes).
    """
    custo_total = float(getattr(equipe, "custo_total", 0.0) or 0.0)
    if getattr(equipe, "contrato_tipo_id", ""):
        return custo_total
    agregado = float(getattr(equipe, "custo_operacional_agregado", 0.0) or 0.0)
    if agregado > 0:
        return agregado
    n_frentes = max(1, int(getattr(equipe, "num_equipes_base", 1) or 1))
    return custo_total * n_frentes


def _cat_find_part_by_item(canonical_in: CanonicalModel) -> dict[str, Any]:
    """1. Itens com partição instancial categorial (pool, ADR-085 ativo)."""
    part_by_item: dict[str, Any] = {}
    for contrato in canonical_in.contratos_recurso:
        for part in contrato.particao_por_item:
            if part.custo_inst_mo or part.custo_inst_eq or part.custo_inst_comb or part.custo_inst_mat:
                part_by_item[part.item_id] = part
    return part_by_item


def _cat_accumulate_particao(
    cat: dict[str, float], part_by_item: dict[str, Any], nfrentes_por_item: dict[str, int]
) -> set[str]:
    contados: set[str] = set()
    for item_id, part in part_by_item.items():
        _nf = nfrentes_por_item.get(item_id, 1)
        _mo = float(part.custo_inst_mo or 0.0) * _nf
        _eq = float(part.custo_inst_eq or 0.0) * _nf
        _comb = float(part.custo_inst_comb or 0.0) * _nf
        _mat = float(part.custo_inst_mat or 0.0) * _nf
        # Mob+demob+idle: custo contratual além do produtivo — vai para eq_aluguel (BDI_servicos)
        _mob = float(getattr(part, "custo_mob_imputado", 0.0) or 0.0) * _nf
        _demob = float(getattr(part, "custo_demob_imputado", 0.0) or 0.0) * _nf
        _idle = float(getattr(part, "custo_ocioso_imputado", 0.0) or 0.0) * _nf
        cat["mao_obra"] += _mo
        cat["eq_aluguel"] += _eq + _mob + _demob + _idle
        cat["material"] += _mat + _comb  # ADR-090: combustivel funde em material
        cat["eq_combustivel"] += _comb  # diagnóstico granular
        contados.add(item_id)
    return contados


def _cat_accumulate_equipe_inst(cat: dict[str, float], eq: Any) -> None:
    """ADR-106 F7: usar custo_inst_* diretamente quando preenchidos (F3 garantiu isso)."""
    _ct_mo = float(eq.custo_inst_mo or 0.0)
    _ct_eq = float(getattr(eq, "custo_inst_eq", 0.0) or 0.0)
    _ct_comb = float(getattr(eq, "custo_inst_comb", 0.0) or 0.0)
    _ct_mat = float(getattr(eq, "custo_inst_mat", 0.0) or 0.0)
    cat["mao_obra"] += _ct_mo
    cat["eq_aluguel"] += _ct_eq
    cat["material"] += _ct_mat + _ct_comb  # ADR-090: combustivel funde em material
    cat["eq_combustivel"] += _ct_comb


def _cat_accumulate_equipe_heuristica(cat: dict[str, float], eq: Any, ct: float) -> None:
    """Fallback heurístico (legado) para equipes sem custo_inst_* preenchido.

    NEP-037: incluir encargos na fração de MO para decomposição (encargos ficam em mao_obra).
    """
    _mo_mais_enc = float(eq.custo_mao_obra_mensal or 0.0) + float(getattr(eq, "custo_encargos_mensal", 0.0) or 0.0)
    base = (
        _mo_mais_enc
        + float(eq.custo_equipamentos_mensal or 0.0)
        + float(eq.custo_combustivel_total_mensal or 0.0)
        + float(eq.custo_material_mensal or 0.0)
    )
    if base <= 0:
        cat["mao_obra"] += ct
        return
    _ct_mo = ct * _mo_mais_enc / base
    _ct_eq = ct * float(eq.custo_equipamentos_mensal or 0.0) / base
    _ct_comb = ct * float(eq.custo_combustivel_total_mensal or 0.0) / base
    _ct_mat = ct * float(eq.custo_material_mensal or 0.0) / base
    cat["mao_obra"] += _ct_mo
    cat["eq_aluguel"] += _ct_eq
    cat["material"] += _ct_mat + _ct_comb  # ADR-090: combustivel funde em material
    cat["eq_combustivel"] += _ct_comb


def _cat_accumulate_equipes_sem_particao(
    cat: dict[str, float], canonical_in: CanonicalModel, contados: set[str]
) -> None:
    """2. Demais itens: prioriza custo_inst_* se disponível (ADR-106 F7), senão heurística proporcional.

    Issue #139 (parte 2): o fallback heurístico usa `_resolve_custo_equipe_agregado`
    (agregado real, todas as frentes, pool-aware) em vez de `eq.custo_total` puro — que é
    "1 frente" para itens sem pool (ADR-091/ADR-162 D4).
    """
    for eq in canonical_in.equipes_diretas:
        if eq.item_id in contados:
            continue
        ct = _resolve_custo_equipe_agregado(eq)
        if getattr(eq, "custo_inst_mo", None) is not None:
            _cat_accumulate_equipe_inst(cat, eq)
            continue
        _cat_accumulate_equipe_heuristica(cat, eq, ct)


def _build_custo_categorial_bottom_up(canonical_in: CanonicalModel) -> dict[str, float]:
    """ADR-085 D4/D5 / ADR-089: custo instancial por sub-propriedade (base bottom-up para BDI).

    Retorna ``{"mao_obra", "eq_aluguel", "eq_combustivel", "material"}`` em R$ (sem BDI).
    "eq_aluguel" = aluguel + manutenção (BDI_servicos); "eq_combustivel" = diesel (BDI_diesel).
    Compatibilidade com consumidores legados via chaves "equipamentos" e "diesel".
    """
    cat = {
        "mao_obra": 0.0,
        "eq_aluguel": 0.0,  # aluguel + manutencao → BDI_servicos
        "material": 0.0,  # consumivel + combustivel → BDI_material (ADR-090)
        # Aliases legados (retrocompat)
        "equipamentos": 0.0,  # = eq_aluguel
        "diesel": 0.0,  # = parcela de material.combustivel
        # Mantido para granularidade de diagnóstico (não usado no BDI)
        "eq_combustivel": 0.0,
    }

    # ADR-091: custo_total já é o custo total de todas as frentes — não multiplicar por
    # num_equipes_base para evitar dupla contagem (mesma correção de _br_build_venda_custo).
    nfrentes_por_item: dict[str, int] = {
        eq.item_id: 1  # custo_inst_* já incluem todas as frentes
        for eq in canonical_in.equipes_diretas
    }

    part_by_item = _cat_find_part_by_item(canonical_in)
    contados = _cat_accumulate_particao(cat, part_by_item, nfrentes_por_item)
    _cat_accumulate_equipes_sem_particao(cat, canonical_in, contados)

    # Aliases legados (retrocompat)
    cat["equipamentos"] = cat["eq_aluguel"]
    cat["diesel"] = cat["eq_combustivel"]
    return {k: round(v, 2) for k, v in cat.items()}


