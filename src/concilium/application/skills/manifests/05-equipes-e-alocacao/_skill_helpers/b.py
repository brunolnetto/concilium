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

    tipos: dict[str, TipoRecurso] = {t.id: t for t in canonical_in.tipos_recurso}
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
    pool_dict = {p.tipo_id: p.model_copy() for p in canonical_in.recurso_pool}
    for tid in tipos:
        if tid not in pool_dict:
            pool_dict[tid] = RecursoPool(
                id=str(uuid.uuid4()),
                tipo_id=tid,
                projeto_id=str(canonical_in.projeto.id),
                quantidade_total=1000,
                quantidade_disponivel=1000,
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


def _resolve_salario(preco, unidade: str, salario_override) -> float:
    """Converte preço unitário do insumo para salário mensal (ADR-034)."""
    if salario_override is not None:
        return float(salario_override)
    from concilium.domain.services.conversor_unidades import ConversorUnidades

    try:
        return ConversorUnidades.converter_preco(preco, unidade, "mes")
    except Exception:
        return preco


def _resolve_encargo_funcao(
    atrib: dict, encargo_override, enc_horista: float, enc_mensalista: float, categoria: str
) -> float:
    """Resolve percentual de encargo a aplicar (ADR-034)."""
    if encargo_override is not None:
        return float(encargo_override)
    enc_local = atrib.get("percentual_encargos_local")
    if enc_local is not None:
        return float(enc_local)
    return enc_horista if categoria.startswith("horista") else (enc_mensalista or enc_horista)


def _calcular_custo_funcao(
    insumo,
    num_pessoas,
    enc_horista,
    he_override,
    enc_mensalista,
    salario_override=None,
    encargo_override=None,
    custo_unitario_override=None,
):
    preco = insumo["preco_unitario"]
    unidade = insumo.get("unidade", "mes")
    salario = _resolve_salario(preco, unidade, salario_override)
    atrib = insumo.get("atributos_especificos", {}) or {}
    categoria = (atrib.get("categoria_sindical") or "").lower()
    he_pct = he_override if he_override is not None else (atrib.get("horas_extras_pct_padrao", 0.0) or 0.0)
    if custo_unitario_override is not None:
        return salario, he_pct, round(float(custo_unitario_override), 2)
    if categoria.startswith("pj"):
        custo_unit = salario
    else:
        custo_com_encargos = atrib.get("custo_com_encargos")
        if custo_com_encargos and custo_com_encargos > 0:
            custo_unit = custo_com_encargos * (1 + he_pct)
        else:
            enc = _resolve_encargo_funcao(atrib, encargo_override, enc_horista, enc_mensalista, categoria)
            custo_unit = salario * (1 + enc) * (1 + he_pct)
    return salario, he_pct, round(custo_unit, 2)


def _converter_preco_equip(insumo: dict, horas_dia: float, dias_uteis: float) -> float:
    """Converte preco_unitario do equipamento para base mensal (ADR-034)."""
    import logging

    from concilium.domain.services.conversor_unidades import ConversorUnidades

    preco = insumo["preco_unitario"]
    unidade = insumo.get("unidade", "h")
    try:
        return ConversorUnidades.converter_preco(preco, unidade, "mes")
    except Exception as e_conv:
        logger = logging.getLogger(__name__)
        horas_mes = horas_dia * dias_uteis
        codigo = insumo.get("codigo", "DESCONHECIDO")
        if unidade == "h":
            base = preco * horas_mes
            logger.warning(
                f"[VAL-EQUIP-CONV-FALLBACK] Conversão falhou para {codigo}: "
                f"unidade={unidade} -> fallback h*horas_mes ({preco} R$/h x {horas_mes} h = {base} R$/mes). "
                f"Erro: {str(e_conv)}"
            )
            return base
        logger.error(
            f"[VAL-EQUIP-CONV-BLOQUEADO] Conversão falhou para {codigo}: "
            f"unidade='{unidade}' não mapeada e != 'h'. Usando preço bruto sem ajuste ({preco} R$). "
            f"AVISO: Valor pode estar incorreto! Revise catálogo. Erro: {str(e_conv)}"
        )
        return preco


def _consumo_from_decomposicao(decomposicao: dict, preco_diesel: float) -> float:
    """Deriva consumo L/h a partir da decomposição de custo do equipamento."""
    custo_diesel_h = float(decomposicao.get("custo_diesel_h", 0.0) or 0.0)
    if custo_diesel_h > 0 and preco_diesel > 0:
        return custo_diesel_h / preco_diesel
    return 0.0
