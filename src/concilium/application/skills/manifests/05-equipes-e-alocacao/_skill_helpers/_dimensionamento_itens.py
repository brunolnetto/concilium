"""Skill 05 — Equipes e Alocação (helpers A, parte extraída de _dimensionamento_equipe.py)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from concilium.domain.constants import SEMANAS_POR_MES
from concilium.domain.models.canonical import (
    EquipamentoEquipeDireta,
    FuncaoEquipeDireta,
    ValidacaoItem,
)
from concilium.domain.models.catalog.catalogo import ComposicaoPadraoEquipe
from concilium.domain.models.catalog.producao import (
    AuditoriaProducao,
    CondicoesCalibração,
    GrafoSinergiaEquipe,
    OrigemProducao,
    Producao,
    QualidadeProducao,
)
from concilium.domain.services.sinergia_equipe import resolver_producao_efetiva

from ._dimensionamento_custos import (  # ty: ignore[unresolved-import]
    _best_alias_equip_attrs,
    _calcular_custo_equipamento,
    _calcular_custo_funcao,
    _fallback_cpu_comp,
    _getfloat_d,
    _getlist_d,
    _RepoCtx,
    _resolve_preco,
    _to_positive_float_or_none,
    _validar_comp_vazia,
)

# ADR-130 F3: chaves reconhecidas pelos modelos tipados de composição (extra="forbid").
# O catálogo bruto (dict) carrega chaves adicionais legadas por elemento (ex.:
# "consumo_litros_hora" em vez de "consumo_litros_hora_estimado") que não pertencem
# ao contrato de `EquipamentoEquipe`/`FuncaoEquipe` — descartadas aqui para permitir
# a reconstrução tipada usada apenas pela derivação de sinergia (não afeta o pipeline
# de custo, que continua dict-based e usa `comp` diretamente).
_FUNCAO_KEYS_SINERGIA = {"funcao_id", "num_pessoas", "horas_extras_pct", "papel"}
_EQUIP_KEYS_SINERGIA = {"equip_id", "num_unidades", "consumo_litros_hora_estimado"}
_MATERIAL_KEYS_SINERGIA = {"insumo_id", "consumo_por_hora", "unidade", "descricao"}


def _filtrar_itens_por_chaves(itens: list | None, chaves: set[str]) -> list[dict]:
    return [{k: v for k, v in item.items() if k in chaves} for item in itens or []]


def _sanitize_comp_para_sinergia(comp_raw: dict) -> dict:
    """Filtra `comp_raw` para as chaves aceitas pelos modelos tipados (ADR-130 F3)."""
    return {
        "funcoes": _filtrar_itens_por_chaves(comp_raw.get("funcoes", []), _FUNCAO_KEYS_SINERGIA),
        "equipamentos": _filtrar_itens_por_chaves(comp_raw.get("equipamentos", []), _EQUIP_KEYS_SINERGIA),
        "materiais": _filtrar_itens_por_chaves(comp_raw.get("materiais", []), _MATERIAL_KEYS_SINERGIA),
    }


def _build_producao_para_sinergia(prod: dict) -> Producao | None:
    """ADR-130 F3: constrói um `Producao` mínimo só para acionar `resolver_producao_efetiva`.

    O pipeline de skill-05 é inteiramente dict-based e nunca instancia `Producao` Pydantic
    hoje; campos de rastreabilidade (`qualidade`, `auditoria`, `condicoes_calibracao`) não
    existem no catálogo bruto e não são lidos por `resolver_producao_efetiva` — preenchidos
    com placeholders válidos apenas para satisfazer a validação do modelo. `origem.tipo`
    também é sintético (o valor real do catálogo, ex. "calibrado_agis_rfi", não pertence ao
    Literal do modelo) — isso não afeta VAL-SINERGIA-02/03, calculadas antes do branch de
    precedência D3 que olha `origem.tipo`.

    Retorna None quando `prod` não tem `grafo_sinergia` populado (a vasta maioria do
    catálogo hoje) ou quando os dados não validam — garante no-op silencioso.
    """
    grafo_raw = prod.get("grafo_sinergia")
    if not grafo_raw:
        return None
    comp_raw = _sanitize_comp_para_sinergia(prod.get("composicao_padrao_equipe") or {})
    agora = datetime.now(UTC)
    # ADR-179: 119/169 produções do mendeslobo hoje têm `origem` como string solta
    # (ex.: "PROPRIA") em vez do dict rico {tipo, fonte_id, ...} — legado de como
    # foram enriquecidas com grafo_sinergia. `referencia` aceita o texto original
    # nesse caso (perde o mínimo de informação); dict é lido normalmente.
    origem_raw = prod.get("origem")
    referencia = origem_raw.get("referencia", "") if isinstance(origem_raw, dict) else str(origem_raw or "")
    try:
        return Producao(
            id=prod.get("id", ""),
            codigo=prod.get("codigo", ""),
            descricao=prod.get("descricao", ""),
            producao_horaria=float(prod.get("producao_horaria") or 0.0),
            unidade=prod.get("unidade", ""),
            origem=OrigemProducao(
                tipo="tabela_referencia",
                fonte_id=prod.get("id", ""),
                data_calibracao=agora,
                referencia=referencia,
            ),
            condicoes_calibracao=CondicoesCalibração(),
            qualidade=QualidadeProducao(
                confianca_pct=0, intervalo_confianca=(0.0, 0.0), quantidade_amostras=1, desvio_padrao=0.0
            ),
            equipe=ComposicaoPadraoEquipe(**comp_raw),
            auditoria=AuditoriaProducao(
                criado_por="", data_criacao=agora, ultima_modificacao=agora, modificado_por="", versao=""
            ),
            grafo_sinergia=GrafoSinergiaEquipe(**grafo_raw),
        )
    except (ValidationError, TypeError, ValueError, AttributeError):
        return None


def _validar_sinergia_producao(prod: dict, validacoes: list) -> None:
    """ADR-130 F3: expõe VAL-SINERGIA-02/03 quando a Producao tem GrafoSinergiaEquipe.

    Nunca altera o `valor_horario`/custo usado no dimensionamento (D3/A3 — sobrescrita
    silenciosa rejeitada); apenas acrescenta validações informativas/avisos à lista já
    surfaced pelo skill-05. No-op (comportamento idêntico ao anterior) quando a Producao
    não tem `grafo_sinergia` — o caso da vasta maioria do catálogo hoje.
    """
    producao = _build_producao_para_sinergia(prod)
    if producao is None:
        return
    resolucao = resolver_producao_efetiva(producao)
    validacoes.extend(resolucao.validacoes)


def _promote_materiais_from_cpu(comp: dict, cpu: dict) -> dict:
    materiais = []
    for it in _getlist_d(cpu, "composicao_itens"):
        if not isinstance(it, dict):
            continue
        if str(it.get("categoria_custo") or "").upper() != "MATERIAL":
            continue
        insumo_id = it.get("insumo_id")
        if not insumo_id:
            continue
        materiais.append(
            {
                "insumo_id": insumo_id,
                "coeficiente": float(it.get("coeficiente") or 0.0),
                "fonte": "cpu.composicao_itens",
            }
        )
    return {**comp, "materiais": materiais} if materiais else comp


def _build_comp_para_item(cpu: dict, prod_lookup: dict, validacoes: list) -> dict:
    """Retorna composição (funcoes/equipamentos) para o CPU, com fallback legado ADR-053."""
    comp: dict = {}
    prod_id_ref = cpu.get("producao_id_ref")
    prod: dict = {}
    if prod_id_ref:
        # isinstance(..., dict): prod_lookup vem de catálogo/overlay resolvido sem validação de
        # schema (CatalogResolver) — uma entrada malformada (ex.: string em vez do dict de
        # Producao) não pode travar o dimensionamento inteiro, só essa referência específica.
        resolved = prod_lookup.get(prod_id_ref)
        prod = resolved if isinstance(resolved, dict) else {}
        comp = prod.get("composicao_padrao_equipe") or {}
    comp = _fallback_cpu_comp(comp, cpu, prod_id_ref, validacoes)
    if not comp.get("materiais"):
        comp = _promote_materiais_from_cpu(comp, cpu)
    _validar_comp_vazia(comp, cpu, prod_id_ref, validacoes)
    # ADR-130 F3: expõe VAL-SINERGIA-02/03 quando a Producao referenciada tem
    # GrafoSinergiaEquipe — no-op quando ausente (retrocompatibilidade total).
    _validar_sinergia_producao(prod, validacoes)
    return comp


def _build_funcao_missing_validacao(funcao_id: str, item_id: str) -> ValidacaoItem:
    return ValidacaoItem(
        codigo="VAL-EQUIP-FUNCAO",
        status="AVISO",
        mensagem=f"Função '{funcao_id}' não encontrada no catálogo (item {item_id}).",
    )


def _finalize_funcao(
    insumo: dict,
    insumo_f: dict,
    sal: float,
    he: float,
    unit: float,
    enc_override: Any,
    perc_horista: float,
    num_p_raw: float,
) -> tuple[FuncaoEquipeDireta, float, float]:
    """Monta o FuncaoEquipeDireta final e calcula deltas de custo base/encargos.

    NEP-037 / NEP-043: custo base (sem encargos) e encargos separados por função.
    Quando a taxa já é all-in (ADR-097 D1, `metodo_custo_total`), enc_unit = 0 —
    evitar dupla contagem.
    """
    from concilium.domain.services.financial.encargo_resolver import custo_ja_inclui_encargos

    enc_field = float(enc_override) if enc_override is not None else perc_horista
    _atrib_f = insumo_f.get("atributos_especificos") or {}
    _taxa_allin = custo_ja_inclui_encargos(_atrib_f)
    sal_base_unit = round(sal * (1.0 + float(he or 0.0)), 2)
    enc_unit = 0.0 if _taxa_allin else round(sal * enc_field * (1.0 + float(he or 0.0)), 2)
    # Canônico representa equipe física → int (ex: 0.5 encarregado compartilhado = 1).
    # Custo calculado usa o coeficiente original (float) para precisão financeira.
    funcao = FuncaoEquipeDireta(
        funcao_id=insumo["codigo"],
        descricao=insumo["descricao"],
        num_pessoas=max(1, round(num_p_raw)),
        salario_base=sal,
        percentual_encargos=enc_field,
        horas_extras_pct=he,
        custo_mensal_unitario=unit,
        custo_encargos_mensal_unitario=enc_unit,
    )
    return funcao, sal_base_unit * num_p_raw, enc_unit * num_p_raw


def _process_one_funcao(
    f: dict,
    item_id: str,
    item_custom: dict,
    ctx: _RepoCtx,
    perc_horista: float,
    perc_mensalista: float,
) -> tuple[FuncaoEquipeDireta | None, float, float, ValidacaoItem | None]:
    """Processa uma função da composição.

    Retorna (funcao|None, delta_custo_mo_base, delta_custo_encargos, validacao|None).
    Quando o insumo não é encontrado, retorna (None, 0.0, 0.0, validacao).
    """
    insumo = ctx.repo.obter_insumo(f["funcao_id"])
    if not insumo:
        return None, 0.0, 0.0, _build_funcao_missing_validacao(f["funcao_id"], item_id)

    func_custom = (item_custom.get("funcoes", {}) or {}).get(f["funcao_id"], {})
    he_override = func_custom.get("horas_extras_pct", f.get("horas_extras_pct"))
    enc_override = func_custom.get("percentual_encargos")
    sal_override = func_custom.get("salario_base")
    unit_override = func_custom.get("custo_mensal_unitario")
    insumo_f: dict[str, Any] = dict(insumo)
    insumo_f["preco_unitario"] = _resolve_preco(ctx, f["funcao_id"], float(insumo.get("preco_unitario", 0.0) or 0.0))
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
    num_p_raw = float(f.get("num_pessoas", 1) or 1)
    funcao, delta_mo_base, delta_encargos = _finalize_funcao(
        insumo, insumo_f, sal, he, unit, enc_override, perc_horista, num_p_raw
    )
    return funcao, delta_mo_base, delta_encargos, None


def _processar_funcoes_item(
    comp: dict,
    item_id: str,
    item_custom: dict,
    ctx: _RepoCtx,
    perc_horista: float,
    perc_mensalista: float,
    validacoes: list,
) -> tuple:
    """Processa funcoes da composicao.

    Retorna (funcoes_mod, custo_mo_base, custo_encargos) onde:
    - custo_mo_base   = Σ salario_base × num_pessoas (sem encargos)
    - custo_encargos  = Σ salario_base × percentual_encargos × num_pessoas
    NEP-037 D1: separação para reconciliar fe_nec com PU_sbdi (que não inclui encargos).
    """
    funcoes_mod: list[FuncaoEquipeDireta] = []
    custo_mo_base = 0.0
    custo_encargos = 0.0
    for f in comp.get("funcoes", []):
        funcao, delta_mo_base, delta_encargos, validacao = _process_one_funcao(
            f, item_id, item_custom, ctx, perc_horista, perc_mensalista
        )
        if validacao is not None:
            validacoes.append(validacao)
            continue
        # _process_one_funcao garante funcao não-None exatamente quando validacao é None.
        assert funcao is not None
        funcoes_mod.append(funcao)
        custo_mo_base += delta_mo_base
        custo_encargos += delta_encargos
    return funcoes_mod, custo_mo_base, custo_encargos


def _build_comb_validacao(equip_id: str, val_comb_code: str) -> ValidacaoItem:
    """Returns a ValidacaoItem for the combustivel validation code."""
    if val_comb_code == "VAL-EQUIP-COMB-03":
        return ValidacaoItem(
            codigo=val_comb_code,
            status="AVISO",
            mensagem=f"Equipamento '{equip_id}': consumo_litros_hora não encontrado em nenhuma fonte; "
            f"custo_combustivel_mensal=0",
        )
    if val_comb_code == "VAL-EQUIP-COMB-04":
        return ValidacaoItem(
            codigo=val_comb_code,
            status="OK",
            mensagem=f"Equipamento '{equip_id}': consumo derivado de decomposicao_equip.custo_diesel_h",
        )
    return ValidacaoItem(codigo=val_comb_code, status="OK", mensagem=None)


def _build_equip_missing_validacao(equip_id: str, item_id: str) -> ValidacaoItem:
    return ValidacaoItem(
        codigo="VAL-EQUIP-EQUIP",
        status="AVISO",
        mensagem=f"Equipamento '{equip_id}' não encontrado no catálogo (item {item_id}).",
    )


def _resolve_equip_attrs_and_tipo(ctx: _RepoCtx, e: dict, equip_custom: dict, insumo: dict) -> tuple[dict, Any]:
    """Enriquece atributos via alias (catálogos híbridos) e resolve o tipo de combustível."""
    # Enriquecimento robusto: quando o insumo principal não traz consumo/tipo,
    # tenta alias por codigo_planilha/descrição (catálogos híbridos AGIS/EQ-*).
    _attrs = insumo.get("atributos_especificos") or {}
    if _to_positive_float_or_none(_attrs.get("consumo_litros_hora")) is None:
        alias_attrs = _best_alias_equip_attrs(ctx, e.get("equip_id", ""), insumo.get("descricao", ""))
        if alias_attrs:
            _attrs = {**alias_attrs, **_attrs}
    tipo_combustivel = (
        equip_custom.get("tipo_combustivel")
        or e.get("tipo_combustivel")
        or _attrs.get("tipo_combustivel")
        or _attrs.get("combustivel")
    )
    return _attrs, tipo_combustivel


def _resolve_equip_custo_mensal_override(
    e: dict, equip_custom: dict, horas_dia: float, dias_uteis: float
) -> float | None:
    # ADR-132: preco_h_unitario na composição sobrepõe preco_unitario do catálogo.
    # Armazenado em R$/h para evitar ambiguidade de horas_mes entre regimes.
    # Convertemos para custo_mensal usando as horas efetivas do regime do projeto.
    _preco_h_comp = e.get("preco_h_unitario")
    _custo_mensal_comp = (
        float(_preco_h_comp) * horas_dia * dias_uteis
        if _preco_h_comp is not None and float(_preco_h_comp) > 0
        else None
    )
    return equip_custom.get("custo_mensal") or _custo_mensal_comp


def _process_one_equipamento(
    e: dict,
    item_id: str,
    item_custom: dict,
    horas_dia: float,
    dias_uteis: float,
    preco_diesel: float,
    ctx: _RepoCtx,
) -> tuple[EquipamentoEquipeDireta | None, float, float, bool, list[ValidacaoItem]]:
    """Processa um equipamento da composição.

    Retorna (eq_mod|None, delta_custo_eq, delta_custo_comb, refinado, validacoes_a_adicionar).
    Quando o insumo não é encontrado, eq_mod é None (chamador deve `continue`).
    """
    insumo = ctx.repo.obter_insumo(e["equip_id"])
    if not insumo:
        return None, 0.0, 0.0, False, [_build_equip_missing_validacao(e["equip_id"], item_id)]

    equip_custom = item_custom.get("equipamentos", {}).get(e["equip_id"], {})
    # Ignora overrides zerados: zero explícito não deve bloquear fallback de catálogo.
    consumo_proj = _to_positive_float_or_none(equip_custom.get("consumo_litros_hora"))
    if consumo_proj is None:
        consumo_proj = _to_positive_float_or_none(e.get("consumo_litros_hora"))
    consumo_cpu = _to_positive_float_or_none(e.get("consumo_litros_hora_estimado"))

    _attrs, tipo_combustivel = _resolve_equip_attrs_and_tipo(ctx, e, equip_custom, insumo)

    custo_mensal_override = _resolve_equip_custo_mensal_override(e, equip_custom, horas_dia, dias_uteis)
    custo_comb_override = equip_custom.get("custo_combustivel_mensal")
    refinado = consumo_proj is not None
    num_un_raw = float(e.get("num_unidades", 1) or 1)
    insumo_e = {
        **insumo,
        "atributos_especificos": _attrs,
        "preco_unitario": _resolve_preco(ctx, e["equip_id"], float(insumo.get("preco_unitario", 0.0) or 0.0)),
    }
    # _calcular_custo_equipamento usa num_un_raw (float) para custo preciso.
    # EquipamentoEquipeDireta.num_unidades arredonda para int (equipe física).
    eq_mod, val_comb_code = _calcular_custo_equipamento(
        insumo_e,
        num_un_raw,
        horas_dia,
        dias_uteis,
        preco_diesel,
        consumo_proj,
        consumo_cpu,
        custo_mensal_override=custo_mensal_override,
        custo_comb_override=custo_comb_override,
        tipo_combustivel_override=tipo_combustivel,
    )
    delta_custo_eq = eq_mod.custo_mensal * num_un_raw  # float para custo preciso
    delta_custo_comb = eq_mod.custo_combustivel_mensal * num_un_raw
    return eq_mod, delta_custo_eq, delta_custo_comb, refinado, [_build_comb_validacao(e["equip_id"], val_comb_code)]


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
        eq_mod, delta_custo_eq, delta_custo_comb, refinado, novas_validacoes = _process_one_equipamento(
            e, item_id, item_custom, horas_dia, dias_uteis, preco_diesel, ctx
        )
        validacoes.extend(novas_validacoes)
        if eq_mod is None:
            continue
        equips_mod.append(eq_mod)
        custo_eq += delta_custo_eq
        custo_comb += delta_custo_comb
        if refinado:
            modo_est = "refinado"
    return equips_mod, custo_eq, custo_comb, modo_est


def _mat_fonte1(materiais_equipe: list, ctx, horas_mes: float) -> float:
    custo = 0.0
    for m in materiais_equipe:
        insumo = ctx.repo.obter_insumo(m.get("insumo_id", ""))
        if insumo:
            custo += _getfloat_d(m, "consumo_por_hora") * _getfloat_d(insumo, "preco_unitario") * horas_mes
    return round(custo, 2)


def _mat_fonte2_item(ci: dict, ctx, producao_horaria: float, horas_mes: float) -> float:
    if (ci.get("categoria_custo") or "").upper() != "MATERIAL":
        return 0.0
    insumo = ctx.repo.obter_insumo(ci.get("insumo_id", ""))
    if not insumo:
        return 0.0
    return _getfloat_d(insumo, "preco_unitario") * _getfloat_d(ci, "coeficiente") * producao_horaria * horas_mes


def _calc_custo_material_item(
    comp: dict,
    cpu: dict,
    prod_lookup: dict,
    ctx: _RepoCtx,
    horas_dia: float,
    dias_uteis: float,
) -> float:
    """NEP-029 D4: custo de material mensal da equipe (R$/mês por frente)."""
    horas_mes = horas_dia * dias_uteis
    materiais_equipe = _getlist_d(comp, "materiais")
    if materiais_equipe:
        return _mat_fonte1(materiais_equipe, ctx, horas_mes)
    prod_id = cpu.get("producao_id_ref")
    prod = prod_lookup.get(prod_id) if prod_id else None
    producao_horaria = float((prod or {}).get("producao_horaria", 0.0) or 0.0)
    if producao_horaria <= 0:
        return 0.0
    return round(
        sum(_mat_fonte2_item(ci, ctx, producao_horaria, horas_mes) for ci in _getlist_d(cpu, "composicao_itens")), 2
    )


def _count_transitions(seq: list) -> tuple:
    n_mob = n_desmob = 0
    prev = 0
    for cur in seq:
        if prev == 0:
            if cur > 0:
                n_mob += 1
        elif cur == 0:
            n_desmob += 1
        prev = cur
    n_desmob += int(prev > 0)
    return n_mob, n_desmob


def _accum_mob_costs_list(items_list: list, num_key: str) -> tuple:
    custo_mob = custo_desmob = 0.0
    for item in items_list:
        n = float(item.get(num_key, 1) or 1)
        custo_mob += _getfloat_d(item, "custo_mobilizacao") * n
        custo_desmob += _getfloat_d(item, "custo_desmobilizacao") * n
    return custo_mob, custo_desmob


def _calc_custo_mob_desmob_split(comp: dict, cron: object) -> tuple[float, float]:
    """NEP-031 L3 / ADR-106 F2-bis: custo de mobilização e desmobilização, separados.

    Mesma lógica de `_calc_custo_mob_desmob` (contagem de transições 0→N e N→0 em
    `cron.distribuicao_semanal`), mas retorna (custo_mob, custo_demob) em vez do
    agregado — permite alimentar `EquipeDireta.custo_mobilizacao_mensal`/
    `.custo_desmobilizacao_mensal` (ADR-106 F2-bis) com valores reais em vez de
    deixá-los mortos (nunca atribuídos), que era o caso antes desta ADR.
    """
    if cron is None:
        return 0.0, 0.0
    periodos = getattr(cron, "distribuicao_semanal", None)
    if not periodos:
        return 0.0, 0.0
    seq = [int(d.num_equipes) for d in periodos.values()]
    if not seq:
        return 0.0, 0.0
    n_mob, n_desmob = _count_transitions(seq)
    c_mob_fn, c_desmob_fn = _accum_mob_costs_list(_getlist_d(comp, "funcoes"), "num_pessoas")
    c_mob_eq, c_desmob_eq = _accum_mob_costs_list(_getlist_d(comp, "equipamentos"), "num_unidades")
    return round(n_mob * (c_mob_fn + c_mob_eq), 2), round(n_desmob * (c_desmob_fn + c_desmob_eq), 2)


def _calc_custo_mob_desmob(comp: dict, cron: object) -> float:
    """NEP-031 L3: custo de mobilização/desmobilização por evento de transição de recurso (§8)."""
    custo_mob, custo_demob = _calc_custo_mob_desmob_split(comp, cron)
    return round(custo_mob + custo_demob, 2)


def _calc_custo_mob_janela(item: Any, custo_mo_mensal: float, custo_eq_mensal: float) -> tuple[float, float]:
    """ADR-106 F5: custo da janela de pré-ativação/pós-atividade por override explícito
    de EapItem.leadtime_mob_semanas/lag_demob_semanas.

    Fórmula: (c_mo + c_eq) semanais × leadtime_mob_semanas / lag_demob_semanas — mesma
    lógica de LifecycleEngine.calcular() (equipe_custo_engine.py), aplicada diretamente
    aqui pois o dimensionamento de equipes diretas (skill-05) não passa pelo engine.
    None (sem override) = 0 — backward compat, nenhuma janela extra de custo.
    """
    leadtime = item.leadtime_mob_semanas
    lag = item.lag_demob_semanas
    if not leadtime and not lag:
        return 0.0, 0.0
    c_semanal = (custo_mo_mensal + custo_eq_mensal) / SEMANAS_POR_MES
    custo_mob = round(c_semanal * leadtime, 2) if leadtime else 0.0
    custo_demob = round(c_semanal * lag, 2) if lag else 0.0
    return custo_mob, custo_demob


def _validar_materiais_item(comp: dict, cpu: dict, validacoes: list) -> None:
    """Emite VAL-EQUIP-MAT-01/02 para inconsistências entre MaterialEquipe e composicao_itens."""
    # Ignora entradas promovidas automaticamente de cpu.composicao_itens — apenas MaterialEquipe explícitas.
    # isinstance(..., dict): dado de catálogo/overlay malformado (ex.: item solto como string
    # em vez de {insumo_id, categoria_custo, ...}) não pode travar o dimensionamento inteiro —
    # ver _promote_materiais_from_cpu, mesmo padrão.
    materiais_cpu_ids = {
        m["insumo_id"]
        for m in comp.get("materiais", [])
        if isinstance(m, dict) and m.get("fonte") != "cpu.composicao_itens"
    }
    itens_material_ids = {
        it["insumo_id"]
        for it in cpu.get("composicao_itens", [])
        if isinstance(it, dict) and it.get("categoria_custo") == "MATERIAL"
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


def _sum_eq_weeks_and_cron_cost(periodos_lista, fixo_sem_comb: float, comb_nominal: float) -> tuple:
    custo = 0.0
    team_weeks = 0
    for d in periodos_lista:
        eff = getattr(d, "eficiencia", 1.0) or 1.0
        custo += (fixo_sem_comb + comb_nominal * eff) * d.num_equipes
        team_weeks += d.num_equipes
    return custo, team_weeks


def _sum_1frente_cost(periodos_lista, fixo_sem_comb: float, comb_nominal: float) -> float:
    """ADR-162 D4: custo de UMA frente de referência, semana a semana — soma a taxa
    semanal (não multiplicada por num_equipes) uma vez por semana ATIVA, em vez de
    dividir o agregado multi-frente por um único num_equipes_paralelas constante
    (`_resolve_permanencia_e_custo_total_ajustados`, versão anterior). Robusto a rampa
    (num_equipes variando semana a semana) — dividir o agregado por uma constante só
    reconstrói exatamente 1 frente quando num_equipes é constante em todas as semanas
    ativas; com rampa, subestima a duração/custo de referência (verificado: rampa
    1→3→1 ao longo de 7 semanas ativas subestimava a permanência em ~40%)."""
    custo = 0.0
    for d in periodos_lista:
        if d.num_equipes <= 0:
            continue
        eff = getattr(d, "eficiencia", 1.0) or 1.0
        custo += fixo_sem_comb + comb_nominal * eff
    return custo


def _calcular_permanencia_e_custo_total(cron, custo_fixo_mensal: float) -> tuple[float, float]:
    """Permanência em meses e custo total a partir da distribuição do cronograma."""
    mensal = getattr(cron, "distribuicao_mensal", None) or {}
    if mensal:
        entries = list(mensal.values())
        permanencia = float(len(entries))
        custo_total = round(sum(d.num_equipes * custo_fixo_mensal for d in entries), 2)
        return permanencia, custo_total
    dist = getattr(cron, "distribuicao_semanal", {}) or {}
    periodos = [d for d in dist.values() if d.num_equipes > 0]
    permanencia = round(len(periodos) / SEMANAS_POR_MES, 2)
    fixo_sem = custo_fixo_mensal / SEMANAS_POR_MES
    custo_total = round(sum(d.num_equipes * fixo_sem for d in periodos), 2)
    return permanencia, custo_total


def _comb_efetivo_mensal(periodos_lista, comb_nominal: float, team_weeks: int, custo_comb: float) -> float:
    if not team_weeks:
        return custo_comb
    # Combustível é proporcional à presença (num_equipes > 0), não à utilização de capacidade.
    # eta_w representa utilização de capacidade de produção, não uso de diesel.
    comb_total = sum(comb_nominal * d.num_equipes for d in periodos_lista if d.num_equipes > 0)
    return comb_total / (team_weeks / SEMANAS_POR_MES)


def _idle_idle_indices(periodos_lista: list, i_first: int, i_last: int) -> int:
    return sum(1 for i in range(i_first, i_last + 1) if periodos_lista[i].num_equipes == 0)


def _custo_ocioso_eq(periodos_lista: list, custo_eq_semanal: float, ativos: int) -> float:
    if not custo_eq_semanal or not ativos:
        return 0.0
    indices_ativos = [i for i, d in enumerate(periodos_lista) if d.num_equipes > 0]
    if not indices_ativos:
        return 0.0
    i_first, i_last = indices_ativos[0], indices_ativos[-1]
    return custo_eq_semanal * _idle_idle_indices(periodos_lista, i_first, i_last)


def _calc_custo_cron(cron, custo_mo: float, custo_eq: float, custo_comb: float) -> tuple:
    """Calcula custo total e permanência a partir do cronograma.

    ADR-162 D4: `custo_1frente` (semana a semana, ver `_sum_1frente_cost`) é o custo de
    referência de UMA frente robusto a rampa — substitui `custo_total / num_equipes_paralelas`
    em `_resolve_permanencia_e_custo_total_ajustados`.
    """
    periodos_lista = list(cron.distribuicao_semanal.values())
    ativos = sum(1 for d in periodos_lista if d.num_equipes > 0)
    fixo_sem_comb_semanal = (custo_mo + custo_eq) / SEMANAS_POR_MES
    comb_nominal_semanal = custo_comb / SEMANAS_POR_MES
    custo_total, team_weeks = _sum_eq_weeks_and_cron_cost(periodos_lista, fixo_sem_comb_semanal, comb_nominal_semanal)
    custo_1frente = _sum_1frente_cost(periodos_lista, fixo_sem_comb_semanal, comb_nominal_semanal)
    custo_comb_efetivo = _comb_efetivo_mensal(periodos_lista, comb_nominal_semanal, team_weeks, custo_comb)
    custo_ocioso_total = _custo_ocioso_eq(periodos_lista, custo_eq / SEMANAS_POR_MES, ativos)
    fixo_mensal = round(custo_mo + custo_eq + custo_comb_efetivo, 2)
    return custo_total, ativos, custo_comb_efetivo, fixo_mensal, team_weeks, round(custo_ocioso_total, 2), custo_1frente


