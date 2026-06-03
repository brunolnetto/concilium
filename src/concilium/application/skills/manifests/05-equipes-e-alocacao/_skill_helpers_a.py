"""Skill 03 — Equipes e Alocação (Consolidado).

Consolida:
1. Dimensionamento de Equipes (antiga 03)
2. Derivação de Requisitos (antiga 03A)
3. Alocação de Recursos (antiga 03B)
4. Validação de Compartilhamento (antiga 03C)

Objetivo: Reduzir fragmentação e garantir consistência atômica entre dimensionamento e alocação.
"""

from __future__ import annotations

from concilium.domain.constants import (
    ENCARGOS_CLT,
    ENCARGOS_MENSALISTA,
    SEMANAS_POR_MES,
)
from concilium.domain.models.canonical import (
    CanonicalModel,
    EquipamentoEquipeDireta,
    EquipeDireta,
    FuncaoEquipeDireta,
    ValidacaoItem,
)

# --- Utils de Dimensionamento (da Skill 03) ---


def _resolve_preco(ctx: _RepoCtx, codigo: str, fallback: float = 0.0) -> float:
    preco, _fonte = ctx.repo.resolver_preco(
        codigo,
        jurisdicao_id=ctx.jurisdicao_id,
        overrides=ctx.overrides,
        data_referencia=ctx.data_base,
    )
    return float(preco or fallback)


def _fallback_cpu_comp(comp: dict, cpu: dict, prod_id_ref, validacoes: list) -> dict:
    """Aplica fallback legado ADR-053: lê composição direto do CPU se produtividade vazia."""
    if not isinstance(comp, dict) or (not comp.get("funcoes") and not comp.get("equipamentos")):
        cpu_comp = cpu.get("composicao_padrao_equipe")
        if cpu_comp and isinstance(cpu_comp, dict) and (cpu_comp.get("funcoes") or cpu_comp.get("equipamentos")):
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-EQUIP-LEGADO-053",
                    status="AVISO",
                    mensagem=(
                        f"CPU '{cpu.get('codigo', '?')}': composicao_padrao_equipe lida diretamente do CPU "
                        f"(legado ADR-053). Migre o catálogo para Produtividade via producao_id_ref."
                    ),
                )
            )
            comp = cpu_comp
    if not isinstance(comp, dict):
        comp = {}
    return comp


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


def _resolve_consumo_equip(atrib: dict, consumo_override_proj, consumo_override_cpu, preco_diesel: float) -> tuple:
    """Resolve consumo de combustível e código de validação (ADR-030 D1)."""
    consumo_insumo = atrib.get("consumo_litros_hora") or 0.0
    decomposicao = atrib.get("decomposicao_equip") or {}
    consumo_decomposicao = _consumo_from_decomposicao(decomposicao, preco_diesel) if decomposicao else 0.0
    if consumo_override_proj is not None:
        return consumo_override_proj, "VAL-EQUIP-COMB-01"
    if consumo_override_cpu is not None:
        return consumo_override_cpu, "VAL-EQUIP-COMB-01"
    if consumo_insumo > 0:
        return consumo_insumo, "VAL-EQUIP-COMB-02"
    if consumo_decomposicao > 0:
        return consumo_decomposicao, "VAL-EQUIP-COMB-04"
    return 0.0, "VAL-EQUIP-COMB-03"


def _calcular_custo_equipamento(
    insumo,
    num_unidades,
    horas_dia,
    dias_uteis,
    preco_diesel,
    consumo_override_proj=None,
    consumo_override_cpu=None,
    custo_mensal_override=None,
    custo_comb_override=None,
):
    custo_base = _converter_preco_equip(insumo, horas_dia, dias_uteis)
    horas_mes_calculadas = horas_dia * dias_uteis
    atrib = insumo.get("atributos_especificos") or {}
    consumo, val_code = _resolve_consumo_equip(atrib, consumo_override_proj, consumo_override_cpu, preco_diesel)
    if custo_mensal_override is not None:
        custo_base = float(custo_mensal_override)
    custo_comb = (
        float(custo_comb_override) if custo_comb_override is not None else consumo * horas_mes_calculadas * preco_diesel
    )
    return (
        EquipamentoEquipeDireta(
            equip_id=insumo["codigo"],
            descricao=insumo["descricao"],
            num_unidades=num_unidades,
            custo_mensal=round(custo_base, 2),
            consumo_litros_hora=consumo if consumo > 0 else None,
            custo_combustivel_mensal=round(custo_comb, 2),
            custo_mensal_total=round(custo_base + custo_comb, 2),
        ),
        val_code,
    )


def _validar_comp_vazia(comp: dict, cpu: dict, prod_id_ref, validacoes: list) -> None:
    """Adiciona aviso se composição permanece vazia após todos os fallbacks."""
    if not comp.get("funcoes") and not comp.get("equipamentos"):
        if prod_id_ref:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-EQUIP-DADOS-01",
                    status="AVISO",
                    mensagem=f"CPU '{cpu['codigo']}' com producao_id_ref='{prod_id_ref}' sem composicao_padrao_equipe na produtividade.",  # noqa: E501
                )
            )
        else:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-EQUIP-DADOS-02",
                    status="AVISO",
                    mensagem=f"CPU '{cpu['codigo']}' sem producao_id_ref.",
                )
            )


def _build_comp_para_item(cpu: dict, prod_lookup: dict, validacoes: list) -> dict:
    """Retorna composição (funcoes/equipamentos) para o CPU, com fallback legado ADR-053."""
    comp: dict = {}
    prod_id_ref = cpu.get("producao_id_ref")
    if prod_id_ref:
        prod = prod_lookup.get(prod_id_ref) or {}
        comp = prod.get("composicao_padrao_equipe") or {}
    comp = _fallback_cpu_comp(comp, cpu, prod_id_ref, validacoes)
    _validar_comp_vazia(comp, cpu, prod_id_ref, validacoes)
    return comp


def _processar_funcoes_item(
    comp: dict,
    item_id: str,
    item_custom: dict,
    ctx: _RepoCtx,
    perc_horista: float,
    perc_mensalista: float,
    validacoes: list,
) -> tuple:
    """Processa funcoes da composicao e retorna (funcoes_mod, custo_mo)."""
    funcoes_mod: list[FuncaoEquipeDireta] = []
    custo_mo = 0.0
    for f in comp.get("funcoes", []):
        insumo = ctx.repo.obter_insumo(f["funcao_id"])
        if not insumo:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-EQUIP-FUNCAO",
                    status="AVISO",
                    mensagem=f"Função '{f['funcao_id']}' não encontrada no catálogo (item {item_id}).",
                )
            )
            continue
        func_custom = (item_custom.get("funcoes", {}) or {}).get(f["funcao_id"], {})
        he_override = func_custom.get("horas_extras_pct", f.get("horas_extras_pct"))
        enc_override = func_custom.get("percentual_encargos")
        sal_override = func_custom.get("salario_base")
        unit_override = func_custom.get("custo_mensal_unitario")
        insumo_f = {
            **insumo,
            "preco_unitario": _resolve_preco(ctx, f["funcao_id"], float(insumo.get("preco_unitario", 0.0) or 0.0)),
        }
        sal, he, unit = _calcular_custo_funcao(
            insumo_f,
            f["num_pessoas"],
            perc_horista,
            he_override,
            perc_mensalista,
            salario_override=sal_override,
            encargo_override=enc_override,
            custo_unitario_override=unit_override,
        )
        enc_field = float(enc_override) if enc_override is not None else perc_horista
        funcoes_mod.append(
            FuncaoEquipeDireta(
                funcao_id=insumo["codigo"],
                descricao=insumo["descricao"],
                num_pessoas=f["num_pessoas"],
                salario_base=sal,
                percentual_encargos=enc_field,
                horas_extras_pct=he,
                custo_mensal_unitario=unit,
            )
        )
        custo_mo += unit * f["num_pessoas"]
    return funcoes_mod, custo_mo


def _processar_equipamentos_item(
    comp: dict,
    item_id: str,
    item_custom: dict,
    cpu: dict,
    horas_dia: float,
    dias_uteis: float,
    preco_diesel: float,
    ctx: _RepoCtx,
    validacoes: list,
) -> tuple:
    """Processa equipamentos da composicao e retorna (equips_mod, custo_eq, custo_comb, modo_est)."""
    equips_mod: list[EquipamentoEquipeDireta] = []
    custo_eq = 0.0
    custo_comb = 0.0
    modo_est = "inicial"
    for e in comp.get("equipamentos", []):
        insumo = ctx.repo.obter_insumo(e["equip_id"])
        if not insumo:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-EQUIP-EQUIP",
                    status="AVISO",
                    mensagem=f"Equipamento '{e['equip_id']}' não encontrado no catálogo (item {item_id}).",
                )
            )
            continue
        equip_custom = item_custom.get("equipamentos", {}).get(e["equip_id"], {})
        consumo_proj = equip_custom.get("consumo_litros_hora")
        consumo_cpu = e.get("consumo_litros_hora_estimado")
        custo_mensal_override = equip_custom.get("custo_mensal")
        custo_comb_override = equip_custom.get("custo_combustivel_mensal")
        if consumo_proj is not None:
            modo_est = "refinado"
        insumo_e = {
            **insumo,
            "preco_unitario": _resolve_preco(ctx, e["equip_id"], float(insumo.get("preco_unitario", 0.0) or 0.0)),
        }
        eq_mod, val_comb_code = _calcular_custo_equipamento(
            insumo_e,
            e["num_unidades"],
            horas_dia,
            dias_uteis,
            preco_diesel,
            consumo_proj,
            consumo_cpu,
            custo_mensal_override=custo_mensal_override,
            custo_comb_override=custo_comb_override,
        )
        equips_mod.append(eq_mod)
        custo_eq += eq_mod.custo_mensal * e["num_unidades"]
        custo_comb += eq_mod.custo_combustivel_mensal * e["num_unidades"]
        status_comb = "AVISO" if val_comb_code == "VAL-EQUIP-COMB-03" else "OK"
        msg_comb = None
        if val_comb_code == "VAL-EQUIP-COMB-03":
            msg_comb = (
                f"Equipamento '{e['equip_id']}': consumo_litros_hora não encontrado em nenhuma fonte; "
                "custo_combustivel_mensal=0"
            )
        elif val_comb_code == "VAL-EQUIP-COMB-04":
            msg_comb = f"Equipamento '{e['equip_id']}': consumo derivado de decomposicao_equip.custo_diesel_h"
        validacoes.append(ValidacaoItem(codigo=val_comb_code, status=status_comb, mensagem=msg_comb))
    return equips_mod, custo_eq, custo_comb, modo_est


def _validar_materiais_item(comp: dict, cpu: dict, validacoes: list) -> None:
    """Emite VAL-EQUIP-MAT-01/02 para inconsistências entre MaterialEquipe e composicao_itens."""
    materiais_cpu_ids = {m["insumo_id"] for m in comp.get("materiais", [])}
    itens_material_ids = {
        it["insumo_id"] for it in cpu.get("composicao_itens", []) if it.get("categoria_custo") == "MATERIAL"
    }
    for mat_id in materiais_cpu_ids - itens_material_ids:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-EQUIP-MAT-01",
                status="AVISO",
                mensagem=f"CPU '{cpu['codigo']}': MaterialEquipe insumo_id='{mat_id}' não encontrado em composicao_itens",  # noqa: E501
            )
        )
    for mat_id in itens_material_ids - materiais_cpu_ids:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-EQUIP-MAT-02",
                status="AVISO",
                mensagem=f"CPU '{cpu['codigo']}': composicao_itens MATERIAL insumo_id='{mat_id}' sem cobertura em MaterialEquipe",  # noqa: E501
            )
        )


def _calc_custo_cron(cron, custo_mo: float, custo_eq: float, custo_comb: float) -> tuple:
    """Calcula custo total e permanência a partir do cronograma."""
    periodos = cron.distribuicao_semanal
    ativos = sum(1 for d in periodos.values() if d.num_equipes > 0)
    fixo_sem_comb_semanal = (custo_mo + custo_eq) / SEMANAS_POR_MES
    comb_nominal_semanal = custo_comb / SEMANAS_POR_MES
    custo_total = sum(
        (fixo_sem_comb_semanal + comb_nominal_semanal * (getattr(d, "eficiencia", 1.0) or 1.0)) * d.num_equipes
        for d in periodos.values()
    )
    team_weeks = sum(d.num_equipes for d in periodos.values())
    if team_weeks > 0:
        comb_efetivo_total = sum(
            comb_nominal_semanal * (getattr(d, "eficiencia", 1.0) or 1.0) * d.num_equipes for d in periodos.values()
        )
        custo_comb_efetivo = comb_efetivo_total / (team_weeks / SEMANAS_POR_MES)
    else:
        custo_comb_efetivo = custo_comb
    fixo_mensal = round(custo_mo + custo_eq + custo_comb_efetivo, 2)
    return custo_total, ativos, custo_comb_efetivo, fixo_mensal, team_weeks


def _setup_dimensionamento_context(
    canonical_in: CanonicalModel,
    inputs: dict,
    catalogo: dict,
    ctx: _RepoCtx,
) -> tuple:
    """Resolve parâmetros, preço de diesel e tabelas de lookup para dimensionamento."""
    perc_horista = inputs.get("percentual_encargos", ENCARGOS_CLT)
    perc_mensalista = inputs.get("percentual_encargos_mensalista", ENCARGOS_MENSALISTA)
    preco_diesel = inputs.get("preco_diesel", 6.20)
    for i in catalogo.get("insumos", []):
        if i["codigo"] == "DIESEL-S10":
            preco_diesel = _resolve_preco(
                ctx, "DIESEL-S10", float(i.get("preco_unitario", preco_diesel) or preco_diesel)
            )
            break
    horas_dia = canonical_in.projeto.regime_trabalho.horas_dia
    dias_uteis = 30.0 * (canonical_in.projeto.regime_trabalho.dias_semana / 7)
    cpu_lookup = {c["codigo"]: c for c in catalogo.get("cpus", [])}
    prod_lookup = {
        p.get("id"): p for p in (catalogo.get("produtividades", []) or catalogo.get("producoes", [])) if p.get("id")
    }
    sched_acts = canonical_in.cronograma.scheduled_activities if canonical_in.cronograma else []
    cron_lookup = {sa.activity_id: sa for sa in sched_acts}
    return perc_horista, perc_mensalista, preco_diesel, horas_dia, dias_uteis, cpu_lookup, prod_lookup, cron_lookup


def _build_dimensionamento(
    canonical_in: CanonicalModel,
    inputs: dict,
    catalogo: dict,
    ctx: _RepoCtx,
    validacoes: list,
) -> list[EquipeDireta]:
    """Seção 1: Dimensionamento de equipes (Antiga Skill 03)."""
    perc_horista, perc_mensalista, preco_diesel, horas_dia, dias_uteis, cpu_lookup, prod_lookup, cron_lookup = (
        _setup_dimensionamento_context(canonical_in, inputs, catalogo, ctx)
    )
    composicao_customizada = inputs.get("composicao_customizada", {})

    equipes: list[EquipeDireta] = []
    for item in canonical_in.eap:
        cpu = cpu_lookup.get(item.cpu_id)
        cron = cron_lookup.get(item.item_id)
        if not cpu or not cron:
            continue
        comp = _build_comp_para_item(cpu, prod_lookup, validacoes)
        item_custom = composicao_customizada.get(item.item_id, {})
        funcoes_mod, custo_mo = _processar_funcoes_item(
            comp, item.item_id, item_custom, ctx, perc_horista, perc_mensalista, validacoes
        )
        equips_mod, custo_eq, custo_comb, modo_est = _processar_equipamentos_item(
            comp, item.item_id, item_custom, cpu, horas_dia, dias_uteis, preco_diesel, ctx, validacoes
        )
        _validar_materiais_item(comp, cpu, validacoes)
        custo_total, ativos, custo_comb_efetivo, fixo_mensal, team_weeks = _calc_custo_cron(
            cron, custo_mo, custo_eq, custo_comb
        )
        equipes.append(
            EquipeDireta(
                equipe_id=f"eq-{item.item_id}",
                item_id=item.item_id,
                cpu_id=item.cpu_id,
                nome=f"Equipe {cpu['descricao'][:30]}",
                num_equipes_base=1,
                funcoes=funcoes_mod,
                equipamentos=equips_mod,
                custo_mao_obra_mensal=round(custo_mo, 2),
                custo_equipamentos_mensal=round(custo_eq, 2),
                custo_combustivel_total_mensal=round(custo_comb_efetivo, 2),
                custo_fixo_mensal=fixo_mensal,
                permanencia_meses=round(ativos / SEMANAS_POR_MES, 2),
                permanencia_efetiva_meses=round(team_weeks / SEMANAS_POR_MES, 4),
                custo_total=round(custo_total, 2),
                modo_estimativa=modo_est,
            )
        )
    if not equipes:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-EQUIP-MODO-INICIAL",
                status="INFO",
                mensagem="Nenhuma equipe dimensionada — pipeline sem atividades elegíveis.",
            )
        )
    return equipes
