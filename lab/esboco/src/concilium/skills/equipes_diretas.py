"""Skill 03 — Equipes Diretas.

Dimensiona equipe direta (mão de obra + equipamentos) para cada item da EAP a partir
da composição-padrão da CPU. Calcula custo mensal e custo total da permanência.

DEC-09: equipes múltiplas idênticas — num_equipes_base é sempre 1; a multiplicação
mês a mês está no cronograma (DistribuicaoMensal.num_equipes).

DEC-19: horas extras replicam a fórmula da planilha — usa horas_extras_pct_padrao
do insumo, ou override via composicao_padrao_equipe.funcoes[].horas_extras_pct.

Inputs (no dict 'inputs'):
    composicao_customizada: dict[str, dict] | None
        Override por item da EAP. Se ausente, usa composicao_padrao_equipe da CPU.
"""

from typing import Any

from concilium.models.canonical import (
    CanonicalModel,
    EquipamentoEquipeDireta,
    EquipeDireta,
    FuncaoEquipeDireta,
    ValidacaoItem,
)
from concilium.skills.escopo import SkillResult


def _build_lookups(catalogo: dict[str, Any]) -> tuple[dict[str, dict], dict[str, dict]]:
    cpus = {c["codigo"]: c for c in catalogo.get("cpus", [])}
    insumos = {i["codigo"]: i for i in catalogo.get("insumos", [])}
    return cpus, insumos


HORAS_MES = 208  # 26 dias × 8h — base de conversão h ↔ mês


def _calcular_custo_funcao(
    insumo: dict[str, Any],
    num_pessoas: int,
    perc_encargos_horista: float,
    he_pct_override: float | None,
    perc_encargos_mensalista: float | None = None,
) -> tuple[float, float, float]:
    """Retorna (salario_base_mensal, he_pct_efetivo, custo_mensal_unitario).

    Diferencia encargos por categoria_sindical do insumo:
    - "pj_*"      -> sem encargos, sem HE
    - "horista_*" -> perc_encargos_horista (~177% AGIS)
    - demais      -> perc_encargos_mensalista (~106%) ou horista se não informado
    """
    preco_unitario = insumo["preco_unitario"]
    unidade = insumo.get("unidade", "mes")
    salario_mensal = preco_unitario * HORAS_MES if unidade == "h" else preco_unitario
    atributos = insumo.get("atributos_especificos", {}) or {}
    categoria = (atributos.get("categoria_sindical") or "").lower()
    he_pct = he_pct_override if he_pct_override is not None else (
        atributos.get("horas_extras_pct_padrao", 0.0) or 0.0
    )
    if categoria.startswith("pj"):
        enc = 0.0
        he_pct = 0.0
    elif categoria.startswith("horista"):
        enc = perc_encargos_horista
    else:
        enc = perc_encargos_mensalista if perc_encargos_mensalista is not None else perc_encargos_horista
    custo_unit = salario_mensal * (1 + enc) * (1 + he_pct)
    return salario_mensal, he_pct, round(custo_unit, 2)


def _calcular_custo_equipamento(
    insumo: dict[str, Any],
    num_unidades: int,
    horas_dia: int,
    dias_uteis_medio_mes: float,
    preco_diesel: float,
) -> EquipamentoEquipeDireta:
    preco_unitario = insumo["preco_unitario"]
    unidade = insumo.get("unidade", "h")
    # Custo base mensal: preco/h × horas_mes, ou preco/mes direto
    horas_mes = horas_dia * dias_uteis_medio_mes
    custo_mensal_base = preco_unitario * horas_mes if unidade == "h" else preco_unitario
    atributos = insumo.get("atributos_especificos", {}) or {}
    consumo = atributos.get("consumo_litros_hora") or 0.0
    custo_combustivel = consumo * horas_mes * preco_diesel
    custo_total_unitario = custo_mensal_base + custo_combustivel

    return EquipamentoEquipeDireta(
        equip_id=insumo["codigo"],
        descricao=insumo["descricao"],
        num_unidades=num_unidades,
        custo_mensal=round(custo_mensal_base, 2),
        consumo_litros_hora=consumo if consumo > 0 else None,
        preco_diesel_litro=preco_diesel if consumo > 0 else None,
        custo_combustivel_mensal=round(custo_combustivel, 2),
        custo_mensal_total=round(custo_total_unitario, 2),
    )


def _calcular_permanencia_e_custo_total(
    cronograma_item, custo_fixo_mensal: float
) -> tuple[float, float]:
    """Permanência = nº de meses com num_equipes > 0.
    Custo total considera multiplicador mês a mês (DEC-09)."""
    permanencia = 0
    custo_total = 0.0
    for _mes, d in cronograma_item.distribuicao_mensal.items():
        if d.num_equipes > 0:
            permanencia += 1
            custo_total += custo_fixo_mensal * d.num_equipes
    return float(permanencia), round(custo_total, 2)


def run_equipes_diretas(
    canonical_in: CanonicalModel,
    inputs: dict[str, Any],
    catalogo: dict[str, Any],
    perfil: dict[str, Any],
) -> SkillResult:
    """Popula seção 'equipes_diretas' do canônico.

    Pré-condições:
        - cronograma populado (skill 02)
        - eap populada (skill 00)

    perfil deve fornecer:
        - jurisdicao via runtime — ou diretamente perc_encargos
        Para esta implementação, lemos perc_encargos de inputs ou usamos default 0.92.
    """
    validacoes: list[ValidacaoItem] = []

    if not canonical_in.cronograma:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-EQUIP-PRECONDICAO",
                status="ERRO",
                mensagem="Skill 03 requer cronograma populado",
            )
        )
        return SkillResult(canonical_in, validacoes)

    cpu_lookup, insumo_lookup = _build_lookups(catalogo)
    cron_lookup = {c.item_id: c for c in canonical_in.cronograma}

    # Parâmetros do regime
    horas_dia = canonical_in.projeto.regime_trabalho.horas_dia
    dias_semana = canonical_in.projeto.regime_trabalho.dias_semana
    dias_uteis_medio_mes = 30.0 * (dias_semana / 7)

    # Encargos: vem dos inputs (injetado pelo runtime via jurisdição)
    # horistas (operadores, motoristas): ~177%  |  mensalistas/PJ: ~106%
    perc_encargos_horista = inputs.get("percentual_encargos", 1.777)
    perc_encargos_mensalista = inputs.get("percentual_encargos_mensalista", 1.06)
    preco_diesel = inputs.get("preco_diesel", _buscar_preco_diesel(catalogo))

    composicao_custom = inputs.get("composicao_customizada", {})

    erros_funcao: list[str] = []
    erros_equip: list[str] = []
    equipes_out: list[EquipeDireta] = []

    for item in canonical_in.eap:
        cpu = cpu_lookup.get(item.cpu_id)
        if cpu is None:
            continue  # já validado em skill anterior

        cron = cron_lookup.get(item.item_id)
        if cron is None or cron.pct_completude < 0.001:
            continue  # sem cronograma, sem equipe

        # Composição: customizada ou padrão da CPU
        composicao = composicao_custom.get(item.item_id) or cpu["composicao_padrao_equipe"]

        funcoes_modeladas: list[FuncaoEquipeDireta] = []
        custo_mo_mensal = 0.0
        for f in composicao["funcoes"]:
            insumo = insumo_lookup.get(f["funcao_id"])
            if insumo is None:
                erros_funcao.append(f["funcao_id"])
                continue
            salario, he_pct, custo_unit = _calcular_custo_funcao(
                insumo,
                f["num_pessoas"],
                perc_encargos_horista,
                f.get("horas_extras_pct"),
                perc_encargos_mensalista,
            )
            funcoes_modeladas.append(
                FuncaoEquipeDireta(
                    funcao_id=insumo["codigo"],
                    descricao=insumo["descricao"],
                    num_pessoas=f["num_pessoas"],
                    salario_base=salario,
                    percentual_encargos=perc_encargos_horista,
                    horas_extras_pct=he_pct,
                    custo_mensal_unitario=custo_unit,
                )
            )
            custo_mo_mensal += custo_unit * f["num_pessoas"]

        equipamentos_modelados: list[EquipamentoEquipeDireta] = []
        custo_eq_mensal = 0.0
        for e in composicao["equipamentos"]:
            insumo = insumo_lookup.get(e["equip_id"])
            if insumo is None:
                erros_equip.append(e["equip_id"])
                continue
            equip_modelo = _calcular_custo_equipamento(
                insumo, e["num_unidades"], horas_dia, dias_uteis_medio_mes, preco_diesel
            )
            equipamentos_modelados.append(equip_modelo)
            custo_eq_mensal += equip_modelo.custo_mensal_total * e["num_unidades"]

        custo_fixo_mensal = round(custo_mo_mensal + custo_eq_mensal, 2)
        permanencia, custo_total = _calcular_permanencia_e_custo_total(cron, custo_fixo_mensal)

        equipes_out.append(
            EquipeDireta(
                equipe_id=f"eq-{item.item_id}",
                item_id=item.item_id,
                cpu_id=item.cpu_id,
                nome=f"Equipe {cpu['descricao'][:40]}",
                num_equipes_base=1,
                funcoes=funcoes_modeladas,
                equipamentos=equipamentos_modelados,
                custo_mao_obra_mensal=round(custo_mo_mensal, 2),
                custo_equipamentos_mensal=round(custo_eq_mensal, 2),
                custo_fixo_mensal=custo_fixo_mensal,
                permanencia_meses=permanencia,
                custo_total=custo_total,
            )
        )

    if erros_funcao:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-EQUIP-01",
                status="ERRO",
                mensagem=f"Funções não encontradas no catálogo: {', '.join(set(erros_funcao))}",
            )
        )
    else:
        validacoes.append(ValidacaoItem(codigo="VAL-EQUIP-01", status="OK"))

    if erros_equip:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-EQUIP-02",
                status="ERRO",
                mensagem=f"Equipamentos não encontrados no catálogo: {', '.join(set(erros_equip))}",
            )
        )
    else:
        validacoes.append(ValidacaoItem(codigo="VAL-EQUIP-02", status="OK"))

    novo = canonical_in.model_copy(update={"equipes_diretas": equipes_out})
    return SkillResult(novo, validacoes)


def _buscar_preco_diesel(catalogo: dict[str, Any]) -> float:
    """Busca preço do diesel no catálogo de insumos. Default 6.20 se não encontrado."""
    for i in catalogo.get("insumos", []):
        if i["codigo"] == "DIESEL-S10":
            return i["preco_unitario"]
    return 6.20
