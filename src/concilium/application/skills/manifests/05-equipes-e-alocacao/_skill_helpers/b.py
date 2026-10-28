"""Skill 05 — Equipes e Alocação (Consolidado).

Consolida:
1. Dimensionamento de Equipes (antiga 03)
2. Derivação de Requisitos (antiga 03A)
3. Alocação de Recursos (antiga 03B)
4. Validação de Compartilhamento (antiga 03C)

Objetivo: Reduzir fragmentação e garantir consistência atômica entre dimensionamento e alocação.
"""

from __future__ import annotations

import uuid

from concilium.domain.models.canonical import (
    Alocacao,
    CanonicalModel,
    EquipeDireta,
    RecursoPool,
    RequisitoRecurso,
    TipoRecurso,
    ValidacaoItem,
)

# --- Utils de Dimensionamento (da Skill 05) ---


def _processar_funcoes_requisitos(eq, d_ini, d_fim, atvs_por_item: dict, tipos: dict, requisitos: list) -> None:
    """Adiciona tipos e requisitos de funções de uma equipe."""
    for f in eq.funcoes:
        tid = f"FUNC-{f.funcao_id}"
        if tid not in tipos:
            tipos[tid] = TipoRecurso(
                id=tid,
                nome=f.descricao,
                categoria="EQUIPE",
                custo_unitario_dia=round(f.custo_mensal_unitario / 26, 2),
                proveniencia="DERIVADO_SKILL05",
            )
        for atv in atvs_por_item[eq.item_id]:
            requisitos.append(
                RequisitoRecurso(
                    requisito_id=str(uuid.uuid4()),
                    atividade_id=atv.atividade_id,
                    tipo_recurso_id=tid,
                    descricao=f.descricao,
                    quantidade=float(f.num_pessoas),
                    data_inicio=d_ini,
                    data_termino=d_fim,
                )
            )


def _processar_equipamentos_requisitos(eq, d_ini, d_fim, atvs_por_item: dict, tipos: dict, requisitos: list) -> None:
    """Adiciona tipos e requisitos de equipamentos de uma equipe."""
    for e in eq.equipamentos:
        tid = f"EQUIP-{e.equip_id}"
        if tid not in tipos:
            tipos[tid] = TipoRecurso(
                id=tid,
                nome=e.descricao,
                categoria="EQUIPAMENTO",
                custo_unitario_dia=round(e.custo_mensal / 26, 2),
                proveniencia="DERIVADO_SKILL05",
            )
        for atv in atvs_por_item[eq.item_id]:
            requisitos.append(
                RequisitoRecurso(
                    requisito_id=str(uuid.uuid4()),
                    atividade_id=atv.atividade_id,
                    tipo_recurso_id=tid,
                    descricao=e.descricao,
                    quantidade=float(e.num_unidades),
                    data_inicio=d_ini,
                    data_termino=d_fim,
                )
            )


def _build_requisitos_e_tipos(
    equipes: list[EquipeDireta],
    canonical_in: CanonicalModel,
    cron_lookup: dict,
    validacoes: list,
) -> tuple:
    """Seção 2 (Antiga 03A): Deriva requisitos e tipos de recurso a partir das equipes."""
    from collections import defaultdict as _defaultdict
    from datetime import date as _date

    legacy_inferred_type_ids = {
        pool.tipo_id
        for pool in (canonical_in.recurso_pool or [])
        if pool.proveniencia == "DERIVADO_SKILL05"
        and pool.tipo_id.startswith(("FUNC-", "EQUIP-"))
    }
    tipos: dict[str, TipoRecurso] = {
        t.id: t
        for t in canonical_in.tipos_recurso
        if t.proveniencia != "DERIVADO_SKILL05"
        and not (
            t.id in legacy_inferred_type_ids
            and "proveniencia" not in t.model_fields_set
        )
    }
    requisitos: list[RequisitoRecurso] = []
    atvs_por_item: dict = _defaultdict(list)
    for atv in canonical_in.atividades or []:
        atvs_por_item[atv.eap_item_id].append(atv)

    for eq in equipes:
        cron = cron_lookup.get(eq.item_id)
        if not cron or not cron.distribuicao_semanal:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-EQUIP-SEM-CRON",
                    status="AVISO",
                    mensagem=(
                        f"Item '{eq.item_id}': sem distribuicao_semanal no cronograma. "
                        "Execute Skill 04 (cronograma) ou configure WMP antes de Skill 05. "
                        "Usando duração mínima de 1 semana para evitar inflação de custo."
                    ),
                )
            )
            d_ini = canonical_in.projeto.data_inicio
            d_fim = canonical_in.projeto.data_inicio
        else:
            pers = sorted(cron.distribuicao_semanal.keys())
            d_ini = _date.fromisoformat(pers[0].split("-W")[0] + "-01-01")
            d_fim = _date.fromisoformat(pers[-1].split("-W")[0] + "-12-31")
        _processar_funcoes_requisitos(eq, d_ini, d_fim, atvs_por_item, tipos, requisitos)
        _processar_equipamentos_requisitos(eq, d_ini, d_fim, atvs_por_item, tipos, requisitos)
    return requisitos, tipos


def _build_alocacoes_pool(
    requisitos: list[RequisitoRecurso],
    canonical_in: CanonicalModel,
    tipos: dict,
) -> tuple:
    """Seção 3 (Antiga 03B): Aloca requisitos no pool de recursos."""
    pool_dict = {
        p.tipo_id: p.model_copy()
        for p in canonical_in.recurso_pool
        if p.proveniencia == "CONFIGURADO"
    }
    for tid, tipo in tipos.items():
        # Only Skill 05-inferred types get a synthetic allocation pool. A declared
        # type without an explicit physical pool must not receive fake capacity.
        if tid not in pool_dict and tipo.proveniencia == "DERIVADO_SKILL05":
            pool_dict[tid] = RecursoPool(
                id=str(uuid.uuid4()),
                tipo_id=tid,
                projeto_id=str(canonical_in.projeto.id),
                quantidade_total=1000,
                quantidade_disponivel=1000,
                proveniencia="DERIVADO_SKILL05",
            )
    alocacoes: list[Alocacao] = []
    for req in sorted(requisitos, key=lambda r: r.data_inicio):
        pool = pool_dict.get(req.tipo_recurso_id)
        if pool:
            alocacoes.append(
                Alocacao(
                    id=str(uuid.uuid4()),
                    atividade_id=req.atividade_id,
                    recurso_id=pool.id,
                    quantidade_alocada=req.quantidade,
                    data_inicio=req.data_inicio,
                    data_termino=req.data_termino,
                    status="PLANEJADA",
                )
            )
    return alocacoes, pool_dict
