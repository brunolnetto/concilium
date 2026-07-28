"""Skill 05 — Equipes e Alocação (Consolidado).

Consolida:
1. Dimensionamento de Equipes
2. Derivação de Requisitos
3. Alocação de Recursos
4. Validação de Compartilhamento

Objetivo: Reduzir fragmentação e garantir consistência atômica entre dimensionamento e alocação.
"""

from __future__ import annotations

from typing import Any

from concilium.application.skills.base import SkillResult
from concilium.domain.models.canonical import (
    CanonicalModel,
    ConflitoPico,
    RecursoContrato,
    ValidacaoItem,
)
from concilium.infrastructure.repositories.insumo import RepositorioInsumo

# --- Utils de Dimensionamento (da Skill 05) ---
# Import helper modules for test compatibility
from . import _skill_helpers  # ty: ignore[unresolved-import]
from ._skill_helpers import (  # ty: ignore[unresolved-import]
    _aplicar_reconciliacao_planejamento,
    _build_alocacoes_pool,
    _build_dimensionamento,
    _build_pool_setup,
    _build_pre_processamento_compartilhamento,
    _build_requisitos_e_tipos,
    _deve_processar_compartilhamento,
    _preencher_custo_inst_estagio_f3,
    _processar_instancias_recurso,
    _processar_oportunidades_paralelo,
    _processar_pool_contratos,
    _RepoCtx,
    _resolve_planejamento_maps,
    _resolve_rcpsp_spec,
    _validar_estagio1_inst_none,
    enriquecer_composicao_por_tipo,
)

_mod_compartilhamento = _skill_helpers.compartilhamento
_mod_instancias = _skill_helpers.instancias
_mod_planejamento = _skill_helpers.planejamento
_mod_pool = _skill_helpers.pool

# Re-export abaixo é consumido apenas por testes de cobertura que acessam a
# função interna do helper via este módulo (não usada por run_equipes_e_alocacao).
_calcular_permanencia_e_custo_total = _skill_helpers._calcular_permanencia_e_custo_total
_mod_a = None  # No longer used in new structure, kept for compatibility
_mod_b = None  # No longer used in new structure, kept for compatibility
_mod_pre = None  # No longer used in new structure, kept for compatibility

def run_equipes_e_alocacao(
    canonical_in: CanonicalModel,
    inputs: dict[str, Any],
    catalogo: dict[str, Any],
) -> SkillResult:
    """Consolida dimensionamento, requisitos e alocação de equipes diretas."""
    benchmark_mode = bool(inputs.get("benchmark_mode") or inputs.get("modo_benchmark"))
    validacoes: list[ValidacaoItem] = []
    repo = RepositorioInsumo(catalogo)
    data_base = canonical_in.projeto.data_base_orcamento
    overrides = inputs.get("insumos_override") if isinstance(inputs.get("insumos_override"), dict) else None
    jurisdicao_id = inputs.get("jurisdicao_id")
    ctx = _RepoCtx(repo, jurisdicao_id, overrides, data_base)

    equipes = _build_dimensionamento(canonical_in, inputs, catalogo, ctx, validacoes)

    # ADR-107: Reconciliar custo_total com planejamento (fonte de verdade)
    # Se spec.planejamento[item_id] existe, use seu custo_sem_bdi como custo_total
    planejamento_map, planejamento_ref_map = _resolve_planejamento_maps(canonical_in, inputs, benchmark_mode)
    _aplicar_reconciliacao_planejamento(equipes, planejamento_map, planejamento_ref_map, validacoes)

    # ADR-104 Checkpoint 1: Estágio 1 — custo_inst_* deve estar None (sem pool contracts ainda)
    _validar_estagio1_inst_none(equipes, validacoes)

    cron_lookup, cpu_lookup, prod_lookup = _build_pool_setup(canonical_in, catalogo)

    # ADR-071/073: Pool Contract Model + Perpetuation Chains
    contratos_recurso: list[RecursoContrato] = []
    cadeias_perpetuacao: list = []
    rcpsp_spec, rcpsp_derivado = _resolve_rcpsp_spec(inputs, canonical_in, catalogo)
    if rcpsp_spec:
        contratos_recurso, cadeias_perpetuacao = _processar_pool_contratos(
            equipes,
            rcpsp_spec,
            rcpsp_derivado,
            cron_lookup,
            validacoes,
            benchmark_mode,
        )
        # ADR-159: popula composicao_funcoes_mo/composicao_equipamentos_eq (ADR-156/157)
        # em cada RecursoContrato — puramente descritivo, não altera nenhum custo.
        enriquecer_composicao_por_tipo(contratos_recurso, canonical_in.eap, cron_lookup, cpu_lookup, prod_lookup)

    # ADR-077: mapa instancial de utilização — executado quando há pool contracts
    instancias_recurso, composicao_equipes_atividade, resumo_utilizacao_contratos = _processar_instancias_recurso(
        contratos_recurso,
        rcpsp_spec,
        cron_lookup,
        validacoes,
        cadeias_perpetuacao,
        equipes,
        benchmark_mode,
        planejamento_map,
        planejamento_ref_map,
    )

    # ADR-106 F3: preenche custo_inst_* para equipes sem pool contract (NEP-040 Fase 4 completa)
    _preencher_custo_inst_estagio_f3(equipes)

    # ADR-078: pré-processamento estrutural de compartilhamento
    relatorio_oportunidades = None
    if _deve_processar_compartilhamento(contratos_recurso, rcpsp_spec):
        relatorio_oportunidades = _build_pre_processamento_compartilhamento(
            contratos_recurso, rcpsp_spec, cron_lookup, validacoes
        )

    # ADR-133: detecção automática de oportunidades de compartilhamento paralelo
    # Executado quando há schedule, resource_costs e pool contracts disponíveis.
    relatorio_oportunidades = _processar_oportunidades_paralelo(
        relatorio_oportunidades, canonical_in, contratos_recurso, rcpsp_spec, validacoes
    )

    requisitos, tipos = _build_requisitos_e_tipos(equipes, canonical_in, cron_lookup, validacoes)
    alocacoes, pool_dict = _build_alocacoes_pool(requisitos, canonical_in, tipos)
    conflitos: list[ConflitoPico] = []
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-EQP-ALOC",
            status="OK",
            mensagem=f"Equipes ({len(equipes)}) e Alocações ({len(alocacoes)}) processadas.",
        )
    )
    novo = canonical_in.model_copy(
        update={
            "equipes_diretas": equipes,
            "contratos_recurso": contratos_recurso,
            "cadeias_perpetuacao": cadeias_perpetuacao,
            "instancias_recurso": instancias_recurso,
            "composicao_equipes_atividade": composicao_equipes_atividade,
            "resumo_utilizacao_contratos": resumo_utilizacao_contratos,
            "relatorio_oportunidades": relatorio_oportunidades,
            "tipos_recurso": list(tipos.values()),
            "recurso_pool": list(pool_dict.values()),
            "requisitos": requisitos,
            "alocacoes": alocacoes,
            "conflitos_pico": conflitos,
        }
    )
    return SkillResult(novo, validacoes)
