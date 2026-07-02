"""Skill 03 — Equipes e Alocação (Consolidado).

Consolida:
1. Dimensionamento de Equipes (antiga 03)
2. Derivação de Requisitos (antiga 03A)
3. Alocação de Recursos (antiga 03B)
4. Validação de Compartilhamento (antiga 03C)

Objetivo: Reduzir fragmentação e garantir consistência atômica entre dimensionamento e alocação.
"""

from __future__ import annotations

import math
import unicodedata
from hashlib import sha1

from concilium.application.skills.manifests._05_equipes_custo_helpers import (
    calcular_custo_instancia_composicional,
)
from concilium.domain.constants import (
    ENCARGOS_CLT,
    ENCARGOS_MENSALISTA,
    SEMANAS_POR_MES,
)
from concilium.domain.models.canonical import (
    CadeiaPerpetuacao,
    CanonicalModel,
    ComposicaoEquipeAtividade,
    CustoParticionadoItem,
    EquipamentoEquipeDireta,
    EquipeDireta,
    FuncaoEquipeDireta,
    InstanciaRecurso,
    RecursoContrato,
    ResumoUtilizacaoContrato,
    SegmentoAtividade,
    ValidacaoItem,
)
from concilium.domain.services.planning.week_sequence import enumerar_semanas

try:
    from eule import euler as _euler
    from interval_sets import Interval, IntervalSet

    _EULE_AVAILABLE = True
except ImportError:
    _EULE_AVAILABLE = False

# --- Utils de Dimensionamento (da Skill 03) ---

# ---------------------------------------------------------------------------
# Micro-helpers
# ---------------------------------------------------------------------------



class _RepoCtx:
    """Contexto para lookups rápidos durante dimensionamento."""

    def __init__(self, repo, jurisdicao_id, overrides, data_base):
        self.repo = repo
        self.jurisdicao_id = jurisdicao_id
        self.overrides = overrides or {}
        self.data_base = data_base


def _getfloat_d(d: dict, key: str) -> float:
    return float(d.get(key) or 0.0)


def _getlist_d(d: dict, key: str) -> list:
    return d.get(key) or []


def _resolve_preco(ctx: _RepoCtx, codigo: str, fallback: float = 0.0) -> float:
    preco, _fonte = ctx.repo.resolver_preco(
        codigo,
        jurisdicao_id=ctx.jurisdicao_id,
        overrides=ctx.overrides,
        data_referencia=ctx.data_base,
    )
    return float(preco or fallback)


def _comp_is_empty(comp: dict) -> bool:
    """Returns True if comp has no funcoes and no equipamentos."""
    return not comp.get("funcoes") and not comp.get("equipamentos")


def _cpu_comp_is_valid(cpu_comp) -> bool:
    """Returns True if cpu_comp is a non-empty dict with funcoes or equipamentos."""
    return bool(cpu_comp and isinstance(cpu_comp, dict) and (cpu_comp.get("funcoes") or cpu_comp.get("equipamentos")))


def _fallback_cpu_comp(comp: dict, cpu: dict, prod_id_ref, validacoes: list) -> dict:
    """Aplica fallback legado ADR-053: lê composição direto do CPU se produtividade vazia."""
    if not isinstance(comp, dict) or _comp_is_empty(comp):
        cpu_comp = cpu.get("composicao_padrao_equipe")
        if _cpu_comp_is_valid(cpu_comp):
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
    """Resolve percentual de encargo a aplicar (ADR-034). Delega para encargo_resolver."""
    from concilium.domain.services.financial.encargo_resolver import resolver_encargo

    return resolver_encargo(atrib, enc_horista, enc_mensalista, encargo_override=encargo_override)


def _resolve_custo_unit_funcao(categoria: str, salario: float, atrib: dict, enc: float, he_pct: float) -> float:
    if categoria.startswith("pj"):
        return salario
    # Insumo com custo pré-computado (campo legado)
    custo_com_encargos = atrib.get("custo_com_encargos")
    if custo_com_encargos and custo_com_encargos > 0:
        return custo_com_encargos * (1 + he_pct)
    # ADR-097 §D3 / NEP-043: taxa horária all-in embute encargos — aplicar enc adicional = dupla contagem.
    # Checa tanto "nota" quanto "nota_encargos" para robustez de naming entre catálogos.
    nota = " ".join(str(atrib.get(k) or "") for k in ("nota", "nota_encargos")).lower()
    if "inclui encargos" in nota:
        return salario * (1 + he_pct)
    return salario * (1 + enc) * (1 + he_pct)


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
    enc = _resolve_encargo_funcao(atrib, encargo_override, enc_horista, enc_mensalista, categoria)
    return salario, he_pct, round(_resolve_custo_unit_funcao(categoria, salario, atrib, enc, he_pct), 2)


def _converter_preco_equip_fallback(insumo: dict, preco: float, horas_mes: float, ConversorUnidades, logger) -> float:
    unidade = insumo.get("unidade", "h")
    codigo = insumo.get("codigo", "DESCONHECIDO")
    try:
        return ConversorUnidades.converter_preco(preco, unidade, "mes")
    except Exception as e_conv:
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


def _converter_preco_equip(insumo: dict, horas_dia: float, dias_uteis: float) -> float:
    """Converte preco_unitario do equipamento para base mensal (ADR-034, NEP-031 L1).

    NEP-031 L1: suporte a rental_unit (§6.1 do enunciado):
        hora_produtiva (default) : preco × horas_dia × dias_uteis
        dia_calendario           : preco × dias_uteis
        mes                      : preco  (já mensal)

    rental_unit é lido de atributos_especificos.rental_unit. Quando ausente,
    usa a conversão padrão via ConversorUnidades (backward-compatible).
    """
    import logging

    from concilium.domain.services.conversor_unidades import ConversorUnidades

    preco = float(insumo["preco_unitario"])
    atrib = insumo.get("atributos_especificos") or {}
    rental_unit = (atrib.get("rental_unit") or "").strip().lower()
    horas_mes = horas_dia * dias_uteis

    if rental_unit == "dia_calendario":
        return round(preco * dias_uteis, 4)
    if rental_unit == "mes":
        return round(preco, 4)
    if rental_unit == "hora_produtiva":
        return round(preco * horas_mes, 4)

    return _converter_preco_equip_fallback(insumo, preco, horas_mes, ConversorUnidades, logging.getLogger(__name__))


def _consumo_from_decomposicao(decomposicao: dict, preco_diesel: float) -> float:
    """Deriva consumo L/h a partir da decomposição de custo do equipamento."""
    custo_diesel_h = float(decomposicao.get("custo_diesel_h", 0.0) or 0.0)
    if custo_diesel_h > 0 and preco_diesel > 0:
        return custo_diesel_h / preco_diesel
    return 0.0


def _to_positive_float_or_none(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0.0 else None


def _normalize_text_key(txt: str) -> str:
    base = unicodedata.normalize("NFKD", str(txt or "")).encode("ascii", "ignore").decode("ascii")
    return " ".join("".join(ch if ch.isalnum() else " " for ch in base).lower().split())


def _best_alias_equip_attrs(ctx: _RepoCtx, equip_id: str, descricao: str) -> dict:
    """Busca atributos de consumo em aliases quando o código principal está incompleto."""
    try:
        insumos_all = list(getattr(ctx.repo, "_insumos", {}).values())
    except Exception:
        return {}

    desc_key = _normalize_text_key(descricao)
    best_score = -1.0
    best_attrs: dict = {}
    for ins in insumos_all:
        if str(ins.get("tipo") or "").upper() != "EQUIPAMENTO":
            continue
        attrs = ins.get("atributos_especificos") or {}
        consumo = _to_positive_float_or_none(attrs.get("consumo_litros_hora"))
        if consumo is None:
            continue
        score = 0.0
        cod_plan = str(attrs.get("codigo_planilha") or "").upper().strip()
        if cod_plan and cod_plan == str(equip_id or "").upper().strip():
            score += 50.0
        desc_i = _normalize_text_key(ins.get("descricao") or "")
        if desc_key and desc_i:
            if desc_i == desc_key:
                score += 40.0
            else:
                a = set(desc_key.split())
                b = set(desc_i.split())
                inter = len(a & b)
                union = len(a | b) or 1
                score += 25.0 * (inter / union)
        if score > best_score:
            best_score = score
            best_attrs = attrs
    return best_attrs if best_score >= 35.0 else {}


def _resolve_consumo_equip(atrib: dict, consumo_override_proj, consumo_override_cpu, preco_diesel: float) -> tuple:
    """Resolve consumo de combustível e código de validação (ADR-030 D1)."""
    consumo_insumo = _to_positive_float_or_none(atrib.get("consumo_litros_hora")) or 0.0
    decomposicao = atrib.get("decomposicao_equip") or {}
    consumo_decomposicao = _consumo_from_decomposicao(decomposicao, preco_diesel) if decomposicao else 0.0
    if consumo_override_proj is not None:
        # None = "sem override"; 0.0 = "sem combustível neste contexto" (override explícito)
        return float(consumo_override_proj), "VAL-EQUIP-COMB-01"
    if _to_positive_float_or_none(consumo_override_cpu) is not None:
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
    tipo_combustivel_override=None,
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
    _atrib = insumo.get("atributos_especificos") or {}
    _tipo_comb = str(
        tipo_combustivel_override or _atrib.get("tipo_combustivel") or _atrib.get("combustivel") or ""
    ).strip()
    if not _tipo_comb and (consumo and consumo > 0):
        _tipo_comb = "Diesel S10"
    _rental_unit = (_atrib.get("rental_unit") or "hora_produtiva").strip().lower()
    _num_un_int = max(1, round(float(num_unidades)))

    # ADR-088: sub-decomposição aluguel | manutencao por equipamento.
    # custo_manutencao = custo_manutencao_hora × horas_mes (NEP-031 L5, já disponível).
    # custo_locacao = custo_base − custo_manutencao (aluguel puro do ativo).
    _custo_manut_hora = float(_atrib.get("custo_manutencao_hora", 0.0) or 0.0)
    _custo_manut = round(_custo_manut_hora * horas_mes_calculadas, 2)
    _custo_locacao = round(max(0.0, custo_base - _custo_manut), 2)

    return (
        EquipamentoEquipeDireta(
            equip_id=insumo["codigo"],
            descricao=insumo["descricao"],
            num_unidades=_num_un_int,
            custo_mensal=round(custo_base, 2),
            consumo_litros_hora=consumo if consumo > 0 else None,
            tipo_combustivel=_tipo_comb or None,
            custo_combustivel_mensal=round(custo_comb, 2),
            custo_mensal_total=round(custo_base + custo_comb, 2),
            rental_unit=_rental_unit,
            custo_manutencao_hora=_custo_manut_hora,
            # ADR-088: sub-campos de aluguel | manutencao
            custo_locacao_mensal=_custo_locacao,
            custo_manutencao_mensal=_custo_manut,
            custo_locacao_idle_mensal=_custo_locacao,  # aluguel integral em standby
            custo_manutencao_idle_mensal=0.0,  # manutenção zero em standby
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
    if prod_id_ref:
        prod = prod_lookup.get(prod_id_ref) or {}
        comp = prod.get("composicao_padrao_equipe") or {}
    comp = _fallback_cpu_comp(comp, cpu, prod_id_ref, validacoes)
    if not comp.get("materiais"):
        comp = _promote_materiais_from_cpu(comp, cpu)
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
        num_p_raw = float(f.get("num_pessoas", 1) or 1)
        # Taxa horária all-in (preco_unitario já inclui encargos — convenção planilha AGIS e similares).
        # Checar tanto "nota" quanto "nota_encargos" para robustez de naming.
        _atrib_f = insumo_f.get("atributos_especificos") or {}
        _nota = " ".join(str(_atrib_f.get(k) or "") for k in ("nota", "nota_encargos")).lower()
        _taxa_allin = "inclui encargos" in _nota
        # NEP-037 / NEP-043: custo base (sem encargos) e encargos separados por função.
        # Quando taxa já é all-in, enc_unit = 0 — evitar dupla contagem.
        sal_base_unit = round(sal * (1.0 + float(he or 0.0)), 2)
        enc_unit = 0.0 if _taxa_allin else round(sal * enc_field * (1.0 + float(he or 0.0)), 2)
        # Canônico representa equipe física → int (ex: 0.5 encarregado compartilhado = 1).
        # Custo calculado usa o coeficiente original (float) para precisão financeira.
        funcoes_mod.append(
            FuncaoEquipeDireta(
                funcao_id=insumo["codigo"],
                descricao=insumo["descricao"],
                num_pessoas=max(1, round(num_p_raw)),
                salario_base=sal,
                percentual_encargos=enc_field,
                horas_extras_pct=he,
                custo_mensal_unitario=unit,
                custo_encargos_mensal_unitario=enc_unit,
            )
        )
        custo_mo_base += sal_base_unit * num_p_raw
        custo_encargos += enc_unit * num_p_raw
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
        # Ignora overrides zerados: zero explícito não deve bloquear fallback de catálogo.
        consumo_proj = _to_positive_float_or_none(equip_custom.get("consumo_litros_hora"))
        if consumo_proj is None:
            consumo_proj = _to_positive_float_or_none(e.get("consumo_litros_hora"))
        consumo_cpu = _to_positive_float_or_none(e.get("consumo_litros_hora_estimado"))

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
        # ADR-108: preco_h_unitario na composição sobrepõe preco_unitario do catálogo.
        # Armazenado em R$/h para evitar ambiguidade de horas_mes entre regimes.
        # Convertemos para custo_mensal usando as horas efetivas do regime do projeto.
        _preco_h_comp = e.get("preco_h_unitario")
        _custo_mensal_comp = (
            float(_preco_h_comp) * horas_dia * dias_uteis
            if _preco_h_comp is not None and float(_preco_h_comp) > 0
            else None
        )
        custo_mensal_override = equip_custom.get("custo_mensal") or _custo_mensal_comp
        custo_comb_override = equip_custom.get("custo_combustivel_mensal")
        if consumo_proj is not None:
            modo_est = "refinado"
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
        equips_mod.append(eq_mod)
        custo_eq += eq_mod.custo_mensal * num_un_raw  # float para custo preciso
        custo_comb += eq_mod.custo_combustivel_mensal * num_un_raw
        validacoes.append(_build_comb_validacao(e["equip_id"], val_comb_code))
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
    producao_horaria = float((prod or {}).get("valor_horario", 0.0) or 0.0)
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


def _calc_custo_mob_desmob(comp: dict, cron: object) -> float:
    """NEP-031 L3: custo de mobilização/desmobilização por evento de transição de recurso (§8)."""
    if cron is None:
        return 0.0
    periodos = getattr(cron, "distribuicao_semanal", None)
    if not periodos:
        return 0.0
    seq = [int(d.num_equipes) for d in periodos.values()]
    if not seq:
        return 0.0
    n_mob, n_desmob = _count_transitions(seq)
    c_mob_fn, c_desmob_fn = _accum_mob_costs_list(_getlist_d(comp, "funcoes"), "num_pessoas")
    c_mob_eq, c_desmob_eq = _accum_mob_costs_list(_getlist_d(comp, "equipamentos"), "num_unidades")
    return round(n_mob * (c_mob_fn + c_mob_eq) + n_desmob * (c_desmob_fn + c_desmob_eq), 2)


def _validar_materiais_item(comp: dict, cpu: dict, validacoes: list) -> None:
    """Emite VAL-EQUIP-MAT-01/02 para inconsistências entre MaterialEquipe e composicao_itens."""
    # Ignora entradas promovidas automaticamente de cpu.composicao_itens — apenas MaterialEquipe explícitas.
    materiais_cpu_ids = {m["insumo_id"] for m in comp.get("materiais", []) if m.get("fonte") != "cpu.composicao_itens"}
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


def _sum_eq_weeks_and_cron_cost(periodos_lista, fixo_sem_comb: float, comb_nominal: float) -> tuple:
    custo = 0.0
    team_weeks = 0
    for d in periodos_lista:
        eff = getattr(d, "eficiencia", 1.0) or 1.0
        custo += (fixo_sem_comb + comb_nominal * eff) * d.num_equipes
        team_weeks += d.num_equipes
    return custo, team_weeks


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
    """Calcula custo total e permanência a partir do cronograma."""
    periodos_lista = list(cron.distribuicao_semanal.values())
    ativos = sum(1 for d in periodos_lista if d.num_equipes > 0)
    fixo_sem_comb_semanal = (custo_mo + custo_eq) / SEMANAS_POR_MES
    comb_nominal_semanal = custo_comb / SEMANAS_POR_MES
    custo_total, team_weeks = _sum_eq_weeks_and_cron_cost(periodos_lista, fixo_sem_comb_semanal, comb_nominal_semanal)
    custo_comb_efetivo = _comb_efetivo_mensal(periodos_lista, comb_nominal_semanal, team_weeks, custo_comb)
    custo_ocioso_total = _custo_ocioso_eq(periodos_lista, custo_eq / SEMANAS_POR_MES, ativos)
    fixo_mensal = round(custo_mo + custo_eq + custo_comb_efetivo, 2)
    return custo_total, ativos, custo_comb_efetivo, fixo_mensal, team_weeks, round(custo_ocioso_total, 2)


def _resolve_preco_diesel(inputs: dict, catalogo: dict, ctx: _RepoCtx) -> float:
    """Returns resolved diesel price from catalog or inputs fallback."""
    preco_diesel = inputs.get("preco_diesel", 6.20)
    for i in catalogo.get("insumos", []):
        if i["codigo"] == "DIESEL-S10":
            return _resolve_preco(ctx, "DIESEL-S10", float(i.get("preco_unitario", preco_diesel) or preco_diesel))
    return preco_diesel


def _resolve_prod_lookup(catalogo: dict) -> dict:
    """Returns {id: producao_dict} from catalog produtividades or producoes."""
    fonte = catalogo.get("produtividades", []) or catalogo.get("producoes", [])
    return {p.get("id"): p for p in fonte if p.get("id")}


def _calibrar_custos_por_cref(
    cpu: dict,
    prod_lookup: dict,
    horas_dia: float,
    custo_mo: float,
    custo_encargos: float,
    custo_mo_base: float,
    custo_eq: float,
    custo_comb: float,
) -> tuple[float, float, float, float, float]:
    """NEP-029/S1: recalibra custos mensais usando custo_hora_total_referencia do catálogo.

    Os preços individuais de insumos do catálogo divergem do custo calibrado pela planilha
    (custo_hora_total_referencia), gerando custo autônomo inconsistente com o pool.
    Usando precos_unitarios_sbdi como frações e C_ref como base, a equipe autônoma
    fica alinhada com o pool (mesmo custo_unit_semanal).

    Retorna (custo_mo, custo_encargos, custo_mo_base, custo_eq, custo_comb) calibrados.
    Sem alteração quando C_ref ausente ou insumos zerados (fallback silencioso).
    """
    prod_id = cpu.get("producao_id_ref") or ""
    prod = prod_lookup.get(prod_id) or {}
    C_ref = float(prod.get("custo_hora_total_referencia") or 0.0)
    if C_ref <= 0.0:
        return custo_mo, custo_encargos, custo_mo_base, custo_eq, custo_comb

    sbdi = cpu.get("precos_unitarios_sbdi") or {}
    pu_mo = float(sbdi.get("mo", 0.0) or 0.0)
    pu_eq = float(sbdi.get("equipamentos", 0.0) or 0.0)
    pu_diesel = float(sbdi.get("diesel", 0.0) or 0.0)
    pu_total = pu_mo + pu_eq + pu_diesel
    if pu_total <= 0.0:
        return custo_mo, custo_encargos, custo_mo_base, custo_eq, custo_comb

    # Custo total por mês calibrado = C_ref × horas_semana × SEMANAS_POR_MES
    horas_semana = horas_dia * 6  # dias_semana fixo via regime
    custo_mes_ref = C_ref * horas_semana * SEMANAS_POR_MES

    # Decompor pelas frações do PU_sbdi
    frac_mo = pu_mo / pu_total
    frac_eq = pu_eq / pu_total
    frac_diesel = pu_diesel / pu_total

    # O PU_sbdi de MO já inclui encargos (B_base × (1+enc)) — manter enc proporcional
    custo_mo_cal = custo_mes_ref * frac_mo  # inclui encargos
    custo_eq_cal = custo_mes_ref * frac_eq
    custo_comb_cal = custo_mes_ref * frac_diesel

    # Derivar custo_mo_base e custo_encargos mantendo a proporção original
    mo_total_orig = custo_mo if custo_mo > 0 else custo_mo_cal
    frac_enc = custo_encargos / mo_total_orig if mo_total_orig > 0 else 0.0
    custo_mo_base_cal = round(custo_mo_cal * (1.0 - frac_enc), 2)
    custo_encargos_cal = round(custo_mo_cal * frac_enc, 2)

    return (
        round(custo_mo_cal, 2),
        custo_encargos_cal,
        custo_mo_base_cal,
        round(custo_eq_cal, 2),
        round(custo_comb_cal, 2),
    )


def _setup_dimensionamento_context(
    canonical_in: CanonicalModel,
    inputs: dict,
    catalogo: dict,
    ctx: _RepoCtx,
) -> tuple:
    """Resolve parâmetros, preço de diesel e tabelas de lookup para dimensionamento."""
    perc_horista = inputs.get("percentual_encargos", ENCARGOS_CLT)
    perc_mensalista = inputs.get("percentual_encargos_mensalista", ENCARGOS_MENSALISTA)
    preco_diesel = _resolve_preco_diesel(inputs, catalogo, ctx)
    horas_dia = canonical_in.projeto.regime_trabalho.horas_dia
    dias_uteis = 30.0 * (canonical_in.projeto.regime_trabalho.dias_semana / 7)
    cpu_lookup = {c["codigo"]: c for c in catalogo.get("cpus", [])}
    prod_lookup = _resolve_prod_lookup(catalogo)
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
        funcoes_mod, custo_mo_base, custo_encargos = _processar_funcoes_item(
            comp, item.item_id, item_custom, ctx, perc_horista, perc_mensalista, validacoes
        )
        # NEP-037: custo_mo para cron = base + encargos (custo_total inalterado)
        custo_mo = custo_mo_base + custo_encargos
        equips_mod, custo_eq, custo_comb, modo_est = _processar_equipamentos_item(
            comp, item.item_id, item_custom, cpu, horas_dia, dias_uteis, preco_diesel, ctx, validacoes
        )
        _validar_materiais_item(comp, cpu, validacoes)
        # custo_material_mensal é responsabilidade de etapas posteriores (skill-06+).
        # Skill-05 apenas valida cobertura via VAL-EQUIP-MAT-01/02.
        custo_mat = 0.0

        # NEP-029/S1: calibrar custos mensais pelo custo_hora_total_referencia do catálogo.
        # precos_unitarios_sbdi fornece as frações mo/eq/diesel já calculadas pela planilha.
        # Sem esta calibração, os insumos individuais divergem do C_ref e o custo autônomo
        # fica ~2.5× menor que o pool, gerando "economia negativa" espúria no painel.
        custo_mo, custo_encargos, custo_mo_base, custo_eq, custo_comb = _calibrar_custos_por_cref(
            cpu, prod_lookup, horas_dia, custo_mo, custo_encargos, custo_mo_base, custo_eq, custo_comb
        )

        # NEP-031 L3: custo de mob/desmob por evento de transição de recursos
        custo_mob_desmob = _calc_custo_mob_desmob(comp, cron)
        custo_total, ativos, custo_comb_efetivo, fixo_mensal, team_weeks, custo_ocioso = _calc_custo_cron(
            cron, custo_mo, custo_eq, custo_comb
        )
        # ADR-091: Dividir permanência pelo número de equipes paralelas alocadas para evitar duplicação de custos
        # assigned_resources é propagado por skill-04 em modo AUTO; em MANUAL_ALLOCATION fica vazio.
        # Para ambos os casos, inferimos o número de equipes paralelas do cronograma:
        # max(num_equipes) na distribuição semanal
        assigned_resources = getattr(cron, "assigned_resources", None) or {}
        num_equipes_paralelas = sum(assigned_resources.values()) if assigned_resources else 1

        # Se assigned_resources está vazio, deduzir do cronograma (MANUAL_ALLOCATION case)
        if not num_equipes_paralelas or num_equipes_paralelas == 1:
            dist_semanal = getattr(cron, "distribuicao_semanal", {}) or {}
            if dist_semanal and isinstance(dist_semanal, dict):
                values_list = list(dist_semanal.values())
                max_num_eq = max((getattr(d, "num_equipes", 0) for d in values_list), default=1)
                if max_num_eq > 1:
                    num_equipes_paralelas = max_num_eq

        # CRÍTICO: team_weeks já vem do cronograma SOMANDO o num_equipes para cada semana
        # Então se há 3 equipes × 32 semanas, vem como 96 weeks
        # Precisamos dividir por num_equipes para obter a permanência de UMA equipe

        team_weeks_ajustado = team_weeks / max(num_equipes_paralelas, 1)
        permanencia_efetiva = round(team_weeks_ajustado / SEMANAS_POR_MES, 4)
        # custo_total_ajustado = custo total / n_frentes = custo de 1 frente (ADR-091)
        custo_total_ajustado = custo_total / max(num_equipes_paralelas, 1) if num_equipes_paralelas > 1 else custo_total
        custo_total_final = round(
            custo_total_ajustado + custo_mat * permanencia_efetiva + custo_ocioso + custo_mob_desmob, 2
        )
        # NEP-037: custo_fixo_mensal usa custo_mo_base (sem encargos) — encargos ficam em custo_encargos_mensal.
        fixo_mensal_total = round(custo_mo_base + custo_eq + custo_comb_efetivo + custo_mat, 2)
        equipes.append(
            EquipeDireta(
                equipe_id=f"eq-{item.item_id}",
                item_id=item.item_id,
                cpu_id=item.cpu_id,
                nome=f"Equipe {cpu['descricao'][:30]}",
                num_equipes_base=num_equipes_paralelas,
                funcoes=funcoes_mod,
                equipamentos=equips_mod,
                custo_mao_obra_mensal=round(custo_mo_base, 2),
                custo_encargos_mensal=round(custo_encargos, 2),
                custo_equipamentos_mensal=round(custo_eq, 2),
                custo_combustivel_total_mensal=round(custo_comb_efetivo, 2),
                custo_material_mensal=round(custo_mat, 2),
                custo_fixo_mensal=fixo_mensal_total,
                permanencia_meses=round(ativos / SEMANAS_POR_MES, 2),
                permanencia_efetiva_meses=permanencia_efetiva,
                custo_total=custo_total_final,
                modo_estimativa=modo_est,
                custo_ocioso_equipamentos=custo_ocioso,
                custo_mob_desmob=custo_mob_desmob,
                # ADR-088: sub-campos de equipamento agregados da equipe
                custo_locacao_mensal=round(sum(e.custo_locacao_mensal * e.num_unidades for e in equips_mod), 2),
                custo_manutencao_mensal=round(sum(e.custo_manutencao_mensal * e.num_unidades for e in equips_mod), 2),
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


# ---------------------------------------------------------------------------
# ADR-071: Pool Contract Model
# ---------------------------------------------------------------------------


def _week_idx(semana: str) -> int:
    """Converte chave de semana para índice inteiro comparável.

    Suporta dois formatos:
    - "S052"      → 52  (índice sequencial do benchmark)
    - "2026-W48"  → número de semanas desde época fixa (ISO 8601)
    """
    s = str(semana).strip()
    # Formato S-index: "S001", "S052", etc.
    if s.startswith("S") and s[1:].isdigit():
        return int(s[1:])
    # Formato ISO: "2026-W48" ou "2026-W08"
    if "-W" in s:
        try:
            import datetime

            parts = s.split("-W")
            year, week = int(parts[0]), int(parts[1])
            monday = datetime.datetime.strptime(f"{year}-W{week:02d}-1", "%G-W%V-%u")
            epoch = datetime.datetime(2000, 1, 3)  # segunda-feira da semana 1 de 2000
            return (monday - epoch).days // 7
        except Exception:
            return 0
    # Fallback: tenta int direto
    try:
        return int(s.lstrip("0") or "0")
    except ValueError:
        return 0


def _eq_comp_floats(eq) -> tuple:
    """Returns (comp_mo, comp_eq, comp_comb, comp_mat) floats from equipe."""
    return (
        float(getattr(eq, "custo_mao_obra_mensal", 0.0) or 0.0),
        float(getattr(eq, "custo_equipamentos_mensal", 0.0) or 0.0),
        float(getattr(eq, "custo_combustivel_total_mensal", 0.0) or 0.0),
        float(getattr(eq, "custo_material_mensal", 0.0) or 0.0),
    )


def _accum_week_demand(
    tipo_week_demand: dict, tipo: str, active_weeks: list, dist: dict, required: int, total_required_peak: int
) -> None:
    """Accumulates week demand entries into tipo_week_demand[tipo]."""
    week_demand = tipo_week_demand.setdefault(tipo, {})
    for w in active_weeks:
        raw = (getattr(dist[w], "num_equipes", 0) or 0) * required / total_required_peak
        demand_w = max(0, math.ceil(raw))
        week_demand[w] = week_demand.get(w, 0) + demand_w


def _add_tipo_item_demand(
    tipo: str,
    iid: str,
    required: int,
    total_required_peak: int,
    active_weeks: list,
    eq,
    dist: dict,
    tipo_items: dict,
    tipo_week_demand: dict,
    custo_hora_ref_sem: float = 0.0,
) -> None:
    """Appends item entry and week demand for a single tipo."""
    actual_mw = sum(
        max(0, round((getattr(dist[w], "num_equipes", 0) or 0) * required / total_required_peak)) for w in active_weeks
    )
    if actual_mw == 0:
        actual_mw = required * len(active_weeks)
    comp_mo, comp_eq, comp_comb, comp_mat = _eq_comp_floats(eq)
    tipo_items.setdefault(tipo, []).append(
        {
            "item_id": iid,
            "required": required,
            "active_weeks": active_weeks,
            "custo_total_item": eq.custo_total,
            "machine_weeks": actual_mw,
            "start_idx": _week_idx(active_weeks[0]),
            "end_idx": _week_idx(active_weeks[-1]) + 1,
            "semana_inicio": active_weeks[0],
            "semana_fim": active_weeks[-1],
            "comp_mo": comp_mo,
            "comp_eq": comp_eq,
            "comp_comb": comp_comb,
            "comp_mat": comp_mat,
            # Custo de 1 equipe por 1 semana de trabalho ativo (custo_hora_total_referencia × horas).
            # Quando disponível (via catálogo), sobrepõe custo_total_item/machine_weeks que pode ser
            # afetado por distorções do schedule (n_frentes × durações ainda não convergidas).
            "custo_hora_ref_sem": custo_hora_ref_sem,
        }
    )
    _accum_week_demand(tipo_week_demand, tipo, active_weeks, dist, required, total_required_peak)


def _get_active_weeks(sa) -> list:
    """Returns sorted list of weeks with positive num_equipes from scheduled activity."""
    dist = getattr(sa, "distribuicao_semanal", None) or {}
    return sorted([w for w, d in dist.items() if (getattr(d, "num_equipes", 0) or 0) > 0], key=_week_idx)


def _resolve_custo_hora_ref_sem(eq, cpu_lookup: dict | None, prod_lookup: dict | None, horas_semana: float) -> float:
    """Resolve custo_hora_total_referencia × horas_semana do catálogo para a equipe.

    Retorna 0.0 quando o lookup não está disponível ou o campo está ausente —
    nesse caso _compute_custo_unit_fracs usa o fallback (custo_total_item/machine_weeks).
    """
    if not cpu_lookup or not prod_lookup:
        return 0.0
    cpu = cpu_lookup.get(getattr(eq, "cpu_id", "") or "")
    if not cpu:
        return 0.0
    prod = prod_lookup.get(cpu.get("producao_id_ref") or "")
    if not prod:
        return 0.0
    c_ref = float(prod.get("custo_hora_total_referencia") or 0.0)
    return round(c_ref * horas_semana, 4) if c_ref > 0.0 else 0.0


def _process_item_tipo_map(
    iid: str,
    tipo_map: dict,
    equipe_map: dict,
    pool: dict,
    sched_lookup: dict,
    tipo_items: dict,
    tipo_week_demand: dict,
    validacoes: list,
    cpu_lookup: dict | None = None,
    prod_lookup: dict | None = None,
    horas_semana: float = 48.0,
) -> None:
    """Processes one iid from item_tipo_map, appending to tipo_items/tipo_week_demand."""
    eq = equipe_map.get(iid)
    sa = sched_lookup.get(iid)
    if not eq or not sa:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-POOL-CONTRATO-01",
                status="INFO",
                mensagem=(f"Item '{iid}' tem required_resources mas sem equipe ou schedule — mantendo custo autônomo."),
            )
        )
        return
    active_weeks = _get_active_weeks(sa)
    if not active_weeks:
        return
    dist = getattr(sa, "distribuicao_semanal", None) or {}
    total_required_peak = sum(tipo_map.values()) or 1
    custo_hora_ref_sem = _resolve_custo_hora_ref_sem(eq, cpu_lookup, prod_lookup, horas_semana)
    for tipo, required in tipo_map.items():
        if tipo not in pool:
            continue
        _add_tipo_item_demand(
            tipo,
            iid,
            required,
            total_required_peak,
            active_weeks,
            eq,
            dist,
            tipo_items,
            tipo_week_demand,
            custo_hora_ref_sem=custo_hora_ref_sem,
        )


def _collect_tipo_items_and_demands(
    item_tipo_map: dict,
    equipe_map: dict,
    pool: dict,
    sched_lookup: dict,
    validacoes: list,
    cpu_lookup: dict | None = None,
    prod_lookup: dict | None = None,
    horas_semana: float = 48.0,
) -> tuple[dict, dict]:
    """Itera items e constrói tipo_items / tipo_week_demand."""
    tipo_items: dict[str, list[dict]] = {}
    tipo_week_demand: dict[str, dict[str, int]] = {}
    for iid, tipo_map in item_tipo_map.items():
        _process_item_tipo_map(
            iid,
            tipo_map,
            equipe_map,
            pool,
            sched_lookup,
            tipo_items,
            tipo_week_demand,
            validacoes,
            cpu_lookup=cpu_lookup,
            prod_lookup=prod_lookup,
            horas_semana=horas_semana,
        )
    return tipo_items, tipo_week_demand


def _compute_custo_unit_fracs(mw_list: list) -> tuple:
    """Retorna (custo_unit_semanal, frac_mo, frac_eq, frac_comb, frac_mat) via média ponderada.

    custo_unit_semanal é o custo de 1 recurso-tipo por 1 semana de trabalho ativo.
    Quando ``custo_hora_ref_sem`` está disponível (derivado de producao.custo_hora_total_referencia),
    usa esse valor autoritativo de catálogo — garante que o pool usa o mesmo preço base do PUxQ,
    independente de distorções do schedule em equipe.custo_total.
    Fallback: custo_total_item / machine_weeks (estimativa a partir da equipe dimensionada).
    """
    total_mw = sum(mw for _, mw, _ in mw_list)
    # Preferir custo_hora_ref_sem (catálogo) quando disponível
    custo_unit_semanal = (
        sum(
            (
                it.get("custo_hora_ref_sem")
                or (it["custo_total_item"] / it["machine_weeks"] if it["machine_weeks"] > 0 else 0.0)
            )
            * mw
            for _, mw, it in mw_list
        )
        / total_mw
        if total_mw > 0
        else 0.0
    )
    _acc = {"mo": 0.0, "eq": 0.0, "comb": 0.0, "mat": 0.0}
    for _, mw, it in mw_list:
        base_i = it["comp_mo"] + it["comp_eq"] + it["comp_comb"] + it["comp_mat"]
        if base_i <= 0 or mw <= 0:
            continue
        _acc["mo"] += (it["comp_mo"] / base_i) * mw
        _acc["eq"] += (it["comp_eq"] / base_i) * mw
        _acc["comb"] += (it["comp_comb"] / base_i) * mw
        _acc["mat"] += (it["comp_mat"] / base_i) * mw
    _soma = sum(_acc.values())
    if _soma > 0:
        fmo, feq, fcomb, fmat = _acc["mo"] / _soma, _acc["eq"] / _soma, _acc["comb"] / _soma, _acc["mat"] / _soma
    else:
        fmo, feq, fcomb, fmat = 1.0, 0.0, 0.0, 0.0
    return custo_unit_semanal, fmo, feq, fcomb, fmat


def _compute_fracs_locacao_manut(mw_list: list, equipe_map: dict, cus_eq: float) -> tuple:
    """Retorna (cus_locacao, cus_manutencao) com sub-decomposição ADR-088."""
    _acc_loc = 0.0
    _acc_manut = 0.0
    for _, mw, it in mw_list:
        _eq_i = it.get("comp_eq", 0.0)
        if _eq_i <= 0 or mw <= 0:
            continue
        _loc_i = getattr(equipe_map.get(it["item_id"]), "custo_locacao_mensal", _eq_i) or _eq_i
        _manut_i = getattr(equipe_map.get(it["item_id"]), "custo_manutencao_mensal", 0.0) or 0.0
        _base_eq = max(_loc_i + _manut_i, _eq_i)
        _acc_loc += (_loc_i / _base_eq) * mw
        _acc_manut += (_manut_i / _base_eq) * mw
    _soma_eq = _acc_loc + _acc_manut
    if _soma_eq > 0 and cus_eq > 0:
        _frac_loc = _acc_loc / _soma_eq
        return round(cus_eq * _frac_loc, 4), round(cus_eq * (1.0 - _frac_loc), 4)
    return cus_eq, 0.0


def _fill_atribuicao(atribuicao: dict, mw_list: list, custo_total_contrato: float, tipo: str) -> None:
    """Fills atribuicao[iid] = (cost, tipo, frac) para este contrato específico.

    IMPORTANTE: sobrescreve a entrada anterior — o acumulado multi-contrato é feito em
    _build_contratos_recurso após todos os contratos serem construídos (TD-1 fix).
    """
    total_mw = sum(mw for _, mw, _ in mw_list) or 1
    for iid, mw, _ in mw_list:
        frac = round(mw / total_mw, 6)
        atribuicao[iid] = (round(custo_total_contrato * frac, 2), tipo, frac)


def _build_contrato_entry(
    tipo: str,
    items: list,
    week_demand: dict,
    pool: dict,
    mw_list: list,
    total_mw: float,
    custo_unit_semanal: float,
    cus_mo: float,
    cus_eq: float,
    cus_comb: float,
    cus_mat: float,
    cus_locacao: float,
    cus_manutencao: float,
    tipo_costs: dict,
    resource_costs: dict,
    atribuicao: dict,
    delta_max: int,
    todas_cadeias: list,
    equipe_map: dict,
    resource_costs_absent: bool = False,
) -> RecursoContrato:
    """Constrói um RecursoContrato completo para o tipo dado."""
    import math as _math

    all_weeks_sorted = sorted(week_demand.keys(), key=_week_idx)
    semana_inicio = all_weeks_sorted[0]
    semana_fim = all_weeks_sorted[-1]
    semanas_contrato = _week_idx(semana_fim) - _week_idx(semana_inicio) + 1
    peak_demand = max(week_demand.values())
    pool_cap = int(pool.get(tipo, peak_demand))
    quantidade_contratada = min(peak_demand, pool_cap)
    custo_total_contrato = quantidade_contratada * custo_unit_semanal * semanas_contrato
    c_mob = float(tipo_costs.get("custo_mob_unit", 0.0))
    c_demob = float(tipo_costs.get("custo_demob_unit", 0.0))
    c_idle = float(tipo_costs.get("custo_idle_semanal_unit", 0.0))
    # ADR-085: quando resource_costs não fornece taxa ociosa explícita, deriva do custo
    # fixo da própria composição — mas SOMENTE se a chave resource_costs estava ausente
    # no spec (catálogo sem custos explícitos). Se resource_costs={} foi passado
    # explicitamente, preserva o comportamento monolítico ADR-071.
    if c_idle <= 0.0 and resource_costs_absent:
        _c_idle_fallback = round(cus_mo + cus_locacao, 4)
        if _c_idle_fallback > 0.0:
            c_idle = _c_idle_fallback
    gap_max = int(_math.ceil((c_mob + c_demob) / c_idle) - 1) if c_idle > 0 else 9999
    cadeias = _build_perpetuation_chains(
        tipo_id=tipo,
        items=items,
        custo_mob_unit=c_mob,
        custo_demob_unit=c_demob,
        custo_standby_unit=c_idle,
        delta_max=delta_max,
        gap_max=gap_max,
    )
    todas_cadeias.extend(cadeias)
    _fill_atribuicao(atribuicao, mw_list, custo_total_contrato, tipo)
    r_naive = sum(it["required"] for it in items)
    custo_mob_desmob = (
        round(len(cadeias) * (c_mob + c_demob) * quantidade_contratada, 2) if (c_mob + c_demob) > 0 else 0.0
    )
    return RecursoContrato(
        contrato_id=f"contrato-{tipo.lower().replace('-', '_')}",
        tipo_id=tipo,
        quantidade_contratada=quantidade_contratada,
        semana_inicio=semana_inicio,
        semana_fim=semana_fim,
        semanas_contrato=semanas_contrato,
        custo_unit_semanal=round(custo_unit_semanal, 4),
        custo_total_contrato=round(custo_total_contrato, 2),
        items_cobertos=[iid for iid, _, _ in mw_list],
        n_cadeias=len(cadeias),
        custo_mob_desmob_contrato=custo_mob_desmob,
        custo_standby_total=round(sum(c.custo_standby for c in cadeias), 2),
        r_naive=r_naive,
        custo_mob_unit=c_mob,
        custo_demob_unit=c_demob,
        custo_idle_semanal_unit=c_idle,
        unidade_faturamento=str(tipo_costs.get("unidade_faturamento", "hora_prod")),
        gap_max_economico=gap_max,
        custo_unit_semanal_mo=cus_mo,
        custo_unit_semanal_eq=cus_eq,
        custo_unit_semanal_comb=cus_comb,
        custo_unit_semanal_mat=cus_mat,
        rho_idle_eq=round(c_idle / cus_eq, 4) if cus_eq > 0 else 1.0,
        custo_unit_semanal_locacao=cus_locacao,
        custo_unit_semanal_manutencao=cus_manutencao,
        particao_por_item=particionar_contrato(
            items_com_janela=[{**it, "T_start": float(it["start_idx"]), "T_end": float(it["end_idx"])} for it in items],
            c_mob=c_mob,
            c_demob=c_demob,
            c_unit_semana=custo_unit_semanal,
            quantidade_contratada=quantidade_contratada,
            T_contrato_start=float(_week_idx(semana_inicio)),
            T_contrato_end=float(_week_idx(semana_fim) + 1),
            atribuicao=atribuicao,
            cadeias=cadeias,
        ),
    )


def _build_tipo_contrato(
    tipo: str,
    items: list,
    week_demand: dict,
    pool: dict,
    mw_list: list,
    total_mw: int,
    tipo_costs: dict,
    resource_costs: dict,
    equipe_map: dict,
    atribuicao: dict,
    delta_max: int,
    todas_cadeias: list,
    resource_costs_absent: bool = False,
) -> RecursoContrato:
    """Builds one RecursoContrato entry from tipo/items data."""
    custo_unit_semanal, fmo, feq, fcomb, fmat = _compute_custo_unit_fracs(mw_list)
    cus_mo = round(custo_unit_semanal * fmo, 4)
    cus_eq = round(custo_unit_semanal * feq, 4)
    cus_comb = round(custo_unit_semanal * fcomb, 4)
    cus_mat = round(custo_unit_semanal * fmat, 4)
    cus_locacao, cus_manutencao = _compute_fracs_locacao_manut(mw_list, equipe_map, cus_eq)
    return _build_contrato_entry(
        tipo,
        items,
        week_demand,
        pool,
        mw_list,
        total_mw,
        custo_unit_semanal,
        cus_mo,
        cus_eq,
        cus_comb,
        cus_mat,
        cus_locacao,
        cus_manutencao,
        tipo_costs,
        resource_costs,
        atribuicao,
        delta_max,
        todas_cadeias,
        equipe_map,
        resource_costs_absent=resource_costs_absent,
    )


def _build_item_tipo_map(activities: list) -> dict:
    """Returns {item_id: {tipo: required}} from rcpsp activities."""
    item_tipo_map: dict[str, dict[str, int]] = {}
    for act in activities:
        iid = act.get("item_id")
        rr = act.get("required_resources", {})
        if iid and rr:
            item_tipo_map[iid] = {k: int(v) for k, v in rr.items()}
    return item_tipo_map


def _derive_rcpsp_from_canonical(canonical_in: object, catalogo: dict) -> dict | None:
    """Deriva rcpsp_spec a partir do canônico quando não fornecido nos inputs.

    Convenção de tipo_id: família fungível da equipe, derivada da assinatura da
    composição padrão (funções + equipamentos + quantidades). Assim, CPUs iguais
    ou com mesma composição compartilham recurso sem depender de regex sobre cpu_id.

    resource_costs é omitido propositalmente → custo_unit_semanal derivado de
    custo_hora_total_referencia do catálogo via _resolve_custo_hora_ref_sem.

    Capacidades declaradas explicitamente em canonical_in.recurso_pool (skill 03) são
    respeitadas quando o tipo_id coincide com o equip_id (convenção natural).

    Retorna None quando não há cronograma ou EAP suficientes para derivar o spec.
    """
    sched_acts = canonical_in.cronograma.scheduled_activities if canonical_in.cronograma else []  # type: ignore[union-attr]
    if not sched_acts:
        return None

    eap_items = canonical_in.eap  # type: ignore[union-attr]
    if not eap_items:
        return None

    sched_lookup = {sa.activity_id: sa for sa in sched_acts}
    sched_ids = set(sched_lookup)

    cpu_lookup: dict = {c["codigo"]: c for c in catalogo.get("cpus", []) if c.get("codigo")}
    prod_lookup: dict = {
        p.get("id") or p.get("codigo", ""): p
        for p in (catalogo.get("producoes") or catalogo.get("produtividades") or [])
    }

    item_tipo_ids: dict[str, tuple[str, int]] = {}
    pool_caps: dict[str, int] = {}

    def _tipo_recurso_fungivel(cpu_id: str, composicao: dict[str, object]) -> str:
        equip = composicao.get("equipamentos") or []
        funcs = composicao.get("funcoes") or []
        if equip or funcs:
            tokens: list[str] = []
            for f in sorted(funcs, key=lambda x: str((x or {}).get("funcao_id") or "")):
                f_safe = f or {}
                fid = str(f_safe.get("funcao_id") or "").strip().upper()
                qtd = round(float(f_safe.get("num_pessoas", 1) or 1), 4)
                if fid:
                    tokens.append(f"F:{fid}:{qtd}")
            for e in sorted(equip, key=lambda x: str((x or {}).get("equip_id") or "")):
                e_safe = e or {}
                eid = str(e_safe.get("equip_id") or "").strip().upper()
                qtd = round(float(e_safe.get("num_unidades", 1) or 1), 4)
                if eid:
                    tokens.append(f"E:{eid}:{qtd}")
            if tokens:
                signature = "|".join(tokens)
                digest = sha1(signature.encode("utf-8")).hexdigest()[:12]
                return f"EQUIPE-COMP-{digest}"
        raw = str(cpu_id or "").strip().upper()
        return f"EQUIPE-CPU-{raw}" if raw else "EQUIPE"

    for item in eap_items:
        if item.item_id not in sched_ids:
            continue
        sa = sched_lookup.get(item.item_id)
        if sa is None:
            continue
        cpu = cpu_lookup.get(item.cpu_id, {})
        prod_id = cpu.get("producao_id_ref")
        prod = prod_lookup.get(prod_id or "", {})
        equipe = prod.get("composicao_padrao_equipe", {}) if prod else {}
        if not (equipe.get("equipamentos") or equipe.get("funcoes")):
            continue
        dist = getattr(sa, "distribuicao_semanal", None) or {}
        required = max((int(math.ceil(float(getattr(d, "num_equipes", 0) or 0.0))) for d in dist.values()), default=1)
        required = max(1, required)
        tipo = _tipo_recurso_fungivel(str(item.cpu_id or ""), equipe)
        item_tipo_ids[item.item_id] = (tipo, required)
        pool_caps[tipo] = max(pool_caps.get(tipo, 0), required)

    if not pool_caps:
        return None

    resource_pool = dict(pool_caps)
    activities = [
        {
            "item_id": iid,
            "required_resources": {tipo: required},
        }
        for iid, (tipo, required) in item_tipo_ids.items()
    ]

    if not activities:
        return None

    return {"resource_pool": resource_pool, "activities": activities}


def _setup_contratos_context(equipes: list, rcpsp_spec: dict) -> tuple:
    """Extracts pool/activities/item_tipo_map/equipe_map/delta_max/resource_costs from rcpsp_spec."""
    pool = rcpsp_spec.get("resource_pool", {})
    activities = rcpsp_spec.get("activities", [])
    if not pool and activities:
        from concilium.application.scheduling import inferir_pool_minimo_from_spec

        pool, _diag = inferir_pool_minimo_from_spec(rcpsp_spec)
        rcpsp_spec["resource_pool"] = dict(pool)
    item_tipo_map = _build_item_tipo_map(activities)
    equipe_map: dict[str, EquipeDireta] = {eq.item_id: eq for eq in equipes}
    delta_max = int(rcpsp_spec.get("delta_perpetuacao_semanas", 2))
    _raw = rcpsp_spec.get("resource_costs", {})
    resource_costs: dict = _raw if isinstance(_raw, dict) else {}
    # True quando a chave está ausente no spec (catálogo sem custos explícitos — usa fallback).
    # False quando resource_costs={} foi passado explicitamente (retrocompatibilidade ADR-071).
    resource_costs_absent = "resource_costs" not in rcpsp_spec
    return pool, activities, item_tipo_map, equipe_map, delta_max, resource_costs, resource_costs_absent


def _build_contratos_recurso(
    equipes: list[EquipeDireta],
    rcpsp_spec: dict,
    sched_lookup: dict,
    validacoes: list,
    cpu_lookup: dict | None = None,
    prod_lookup: dict | None = None,
    horas_semana: float = 48.0,
) -> tuple[list[RecursoContrato], dict[str, tuple[float, str, float]], list[CadeiaPerpetuacao]]:
    """Calcula contratos de pool e retorna (contratos, atribuicao_por_item, cadeias).

    ADR-071: O custo real do contrato de um tipo de recurso é:

        peak_demand × custo_unit_semanal × semanas_contrato

    onde peak_demand = max demanda simultânea observada no cronograma RCPSP
    (≤ pool_size, que é o limite superior de capacidade).

    O custo por item é uma atribuição proporcional ao uso (machine-weeks):

        custo_item = custo_contrato × (R_i × active_weeks_i) / total_machine_weeks

    Parâmetros
    ----------
    equipes       : lista de EquipeDireta com custo_total já calculado (passo anterior)
    rcpsp_spec    : dict com 'resource_pool' e 'activities[].required_resources'
    sched_lookup  : {activity_id: ScheduledActivity} do cronograma RCPSP
    validacoes    : lista acumulada de validações (append de INFOs/AVISOs)

    Retorna
    -------
    contratos    : list[RecursoContrato] — um por tipo de pool com atividades ativas
    atribuicao   : {item_id: (custo_atribuido, tipo_id, fracao)} — por item coberto
    cadeias      : list[CadeiaPerpetuacao] — cadeias de perpetuação ADR-073
    """
    pool, activities, item_tipo_map, equipe_map, delta_max, resource_costs, resource_costs_absent = (
        _setup_contratos_context(equipes, rcpsp_spec)
    )
    if not pool or not activities:
        return [], {}, []

    tipo_items, tipo_week_demand = _collect_tipo_items_and_demands(
        item_tipo_map,
        equipe_map,
        pool,
        sched_lookup,
        validacoes,
        cpu_lookup=cpu_lookup,
        prod_lookup=prod_lookup,
        horas_semana=horas_semana,
    )

    contratos: list[RecursoContrato] = []
    atribuicao: dict[str, tuple[float, str, float]] = {}
    todas_cadeias: list[CadeiaPerpetuacao] = []

    for tipo, items in tipo_items.items():
        week_demand = tipo_week_demand.get(tipo, {})
        if not week_demand:
            continue
        mw_list: list[tuple[str, int, dict]] = [(it["item_id"], it["machine_weeks"], it) for it in items]
        total_mw = sum(mw for _, mw, _ in mw_list)
        if total_mw == 0:
            continue
        tipo_costs = resource_costs.get(tipo, {})
        if not isinstance(tipo_costs, dict):
            tipo_costs = {}
        contratos.append(
            _build_tipo_contrato(
                tipo,
                items,
                week_demand,
                pool,
                mw_list,
                total_mw,
                tipo_costs,
                resource_costs,
                equipe_map,
                atribuicao,
                delta_max,
                todas_cadeias,
                resource_costs_absent=resource_costs_absent,
            )
        )

    # TD-1: acumular atribuição total por item sobre todos os contratos.
    # _fill_atribuicao sobrescreve por contrato (correto para particao_por_item).
    # Aqui somamos as contribuições de cada contrato para cada item.
    atribuicao_total: dict[str, tuple[float, str, float]] = {}
    for contrato in contratos:
        for part in contrato.particao_por_item:
            iid = part.item_id
            custo_part = float(getattr(part, "custo_total_particionado", 0.0) or 0.0)
            prev_custo, prev_tipo, prev_frac = atribuicao_total.get(iid, (0.0, contrato.tipo_id, 0.0))
            novo_tipo = contrato.tipo_id if custo_part >= prev_custo else prev_tipo
            atribuicao_total[iid] = (
                round(prev_custo + custo_part, 2),
                novo_tipo,
                round(prev_frac, 6),
            )

    return contratos, atribuicao_total, todas_cadeias


# ---------------------------------------------------------------------------
# ADR-073: Perpetuation Chain Builder
# ---------------------------------------------------------------------------


def _build_perpetuation_chains(
    tipo_id: str,
    items: list[dict],
    custo_mob_unit: float = 0.0,
    custo_demob_unit: float = 0.0,
    custo_standby_unit: float = 0.0,
    delta_max: int = 2,
    gap_max: int = 9999,
) -> list[CadeiaPerpetuacao]:
    """Build perpetuation chains for a resource type (ADR-073).

    Groups consecutive activities that use the same resource type into chains
    where the fleet is kept mobilized between activities (no intermediate
    mob/demob events).

    Parameters
    ----------
    tipo_id         : resource type identifier (e.g. "DESMAT")
    items           : list of dicts {item_id, start_idx, end_idx, required,
                      active_weeks, machine_weeks}; already sorted or unsorted
    custo_mob_unit  : unit mob cost (e.g. per machine); 0 → use time threshold
    custo_demob_unit: unit demob cost; 0 → use time threshold
    custo_standby_unit: cost per machine-week during gap (often 0 in early catalogs)
    delta_max       : max gap (weeks) to trigger perpetuation when cost data absent
    gap_max         : ADR-079 G_r^viável — hard upper bound on gap; perpetuation
                      is NEVER allowed when gap > gap_max, regardless of cost
                      threshold. Default 9999 preserves pre-ADR-079 behaviour.

    Returns
    -------
    list[CadeiaPerpetuacao] — one entry per chain
    """
    if not items:
        return []

    # Sort by start, then by end
    sorted_items = sorted(items, key=lambda x: (x["start_idx"], x["end_idx"]))

    use_cost_threshold = (custo_mob_unit + custo_demob_unit) > 0

    chains: list[CadeiaPerpetuacao] = []
    chain_items = [sorted_items[0]]

    def _flush_chain(chain_items: list[dict], chain_n: int) -> CadeiaPerpetuacao:
        """Convert an accumulated list of items into a CadeiaPerpetuacao."""
        semanas_ativas = sum(len(it["active_weeks"]) for it in chain_items)
        machine_weeks_ativas = sum(it["machine_weeks"] for it in chain_items)

        # Gaps: between consecutive items in chain
        semanas_ociosas = 0
        custo_standby = 0.0
        for k in range(1, len(chain_items)):
            gap = max(0, chain_items[k]["start_idx"] - chain_items[k - 1]["end_idx"])
            semanas_ociosas += gap
            if custo_standby_unit > 0 and gap > 0:
                # Standby cost = gap × standby_unit × min(demand of preceding end, following start)
                demand_end = chain_items[k - 1]["required"]
                demand_start = chain_items[k]["required"]
                custo_standby += gap * custo_standby_unit * min(demand_end, demand_start)

        return CadeiaPerpetuacao(
            cadeia_id=f"cadeia-{tipo_id.lower().replace('-', '_')}-{chain_n}",
            tipo_id=tipo_id,
            item_ids=[it["item_id"] for it in chain_items],
            semana_inicio=chain_items[0].get("semana_inicio", ""),
            semana_fim=chain_items[-1].get("semana_fim", ""),
            semanas_ativas=semanas_ativas,
            semanas_ociosas=semanas_ociosas,
            n_mobilizacoes=1,
            n_desmobilizacoes=1,
            custo_standby=round(custo_standby, 2),
            machine_weeks_ativas=machine_weeks_ativas,
            delta_aplicado_semanas=delta_max,
        )

    for item in sorted_items[1:]:
        last = chain_items[-1]
        gap = item["start_idx"] - last["end_idx"]  # may be negative (overlap)

        if use_cost_threshold:
            # Cost-based: perpetuate if standby is cheaper than mob+demob
            standby_cost = max(0, gap) * custo_standby_unit * min(last["required"], item["required"])
            perpetuate = standby_cost < (custo_mob_unit + custo_demob_unit)
        else:
            # Time-based: perpetuate if gap ≤ delta_max (overlaps always perpetuate)
            perpetuate = gap <= delta_max

        # ADR-079: G_r^viável hard constraint — never perpetuate beyond gap_max
        if gap > gap_max:
            perpetuate = False

        if perpetuate:
            chain_items.append(item)
        else:
            chains.append(_flush_chain(chain_items, len(chains) + 1))
            chain_items = [item]

    # Flush final chain
    chains.append(_flush_chain(chain_items, len(chains) + 1))
    return chains


# ---------------------------------------------------------------------------
# ADR-083: Causal Cost Partition for Pool Items
# ---------------------------------------------------------------------------


def _iter_intervals(obj) -> list:
    """Normaliza Interval | IntervalSet para lista de Interval — ADR-084 D2."""
    if not _EULE_AVAILABLE:
        return []
    if isinstance(obj, IntervalSet):
        return [] if obj.is_empty() else list(obj)
    try:
        return [] if obj.is_empty() else [obj]
    except Exception:
        return []


def _sucessor_critico_id(gap_end: float, atividades_sorted: list[dict]) -> str | None:
    """Primeira atividade que inicia em ou após gap_end — ADR-084 D2."""
    for a in atividades_sorted:
        if a["T_start"] >= gap_end - 1e-9:
            return a["item_id"]
    return None


def _init_item_float_maps(items_com_janela: list, *keys) -> tuple:
    """Returns N dicts {item_id: 0.0} — one per key."""
    return tuple({it["item_id"]: 0.0 for it in items_com_janela} for _ in keys)


def _impute_euler_regions(diagram, items_com_janela, c_unit_semana: float, qt: int) -> tuple:
    """Pass 1: produtivas. Returns (phi, custo_excl, custo_comp, overlap_sem)."""
    phi, custo_excl, custo_comp, overlap_sem = _init_item_float_maps(items_com_janela, 1, 2, 3, 4)
    for ids_ativas, region in diagram.items():
        duracao = region.measure()
        custo = duracao * c_unit_semana * qt
        n_ativas = len(ids_ativas)
        for aid in ids_ativas:
            if aid not in phi:
                continue
            parcela = custo / n_ativas
            phi[aid] += parcela
            if n_ativas == 1:
                custo_excl[aid] += parcela
            else:
                custo_comp[aid] += parcela
                overlap_sem[aid] += duracao
    return phi, custo_excl, custo_comp, overlap_sem


def _impute_mob_demob(cadeias, items_com_janela, phi: dict, c_mob: float, c_demob: float, qt: int) -> tuple:
    """Pass 2: mob/demob Shapley. Returns (mob_imputado, demob_imputado)."""
    item_to_cadeia = {}
    for cadeia in cadeias:
        for iid in cadeia.item_ids:
            item_to_cadeia[iid] = cadeia
    mob_imputado = {}
    demob_imputado = {}
    for it in items_com_janela:
        iid = it["item_id"]
        cadeia = item_to_cadeia.get(iid)
        n_members = len(cadeia.item_ids) if cadeia else 1
        mob_imputado[iid] = round(c_mob * qt / n_members, 2) if n_members > 0 else 0.0
        demob_imputado[iid] = round(c_demob * qt / n_members, 2) if n_members > 0 else 0.0
        phi[iid] += mob_imputado[iid] + demob_imputado[iid]
    return mob_imputado, demob_imputado


def _impute_gaps(
    diagram, items_com_janela, phi: dict, c_unit_semana: float, qt: int, T_contrato_start: float, T_contrato_end: float
) -> tuple:
    """Pass 3: gap imputation to critical successor. Returns (custo_ocioso, uniao_produtiva)."""
    all_ivs = [iv for _, region in diagram.items() for iv in region]
    uniao_produtiva = IntervalSet(all_ivs) if all_ivs else IntervalSet([])
    janela = IntervalSet([Interval(T_contrato_start, T_contrato_end)])
    gaps_obj = janela - uniao_produtiva
    custo_ocioso = {it["item_id"]: 0.0 for it in items_com_janela}
    items_sorted = sorted(items_com_janela, key=lambda x: x["T_start"])
    for gap_iv in _iter_intervals(gaps_obj):
        critico_id = _sucessor_critico_id(gap_iv.end, items_sorted)
        if critico_id and critico_id in phi:
            custo_gap = gap_iv.length() * c_unit_semana * qt
            phi[critico_id] += custo_gap
            custo_ocioso[critico_id] += custo_gap
    return custo_ocioso


def _build_predecessor_map(items_com_janela: list, cadeias: list) -> dict:
    """Returns {item_id: predecessor_id or None} from cadeias."""
    predecessor_map: dict[str, str | None] = {it["item_id"]: None for it in items_com_janela}
    for cadeia in cadeias:
        for k, iid in enumerate(cadeia.item_ids):
            if k > 0:
                predecessor_map[iid] = cadeia.item_ids[k - 1]
    return predecessor_map


def particionar_contrato(
    items_com_janela: list[dict],
    c_mob: float,
    c_demob: float,
    c_unit_semana: float,
    quantidade_contratada: int,
    T_contrato_start: float,
    T_contrato_end: float,
    atribuicao: dict[str, tuple[float, str, float]],
    cadeias: list[CadeiaPerpetuacao],
) -> list[CustoParticionadoItem]:
    """Partição exata de custo por atividade via diagrama de Euler — ADR-084 D2.

    Usa eule[interval] para computar regiões produtivas (exclusivas e de sobreposição)
    e complemento para identificar gaps causalmente imputados ao sucessor crítico.

    Invariante: Σ custo_total_particionado == C_contrato_total  (via atribuicao ADR-071 D3).

    Três fontes de custo atribuídas por atividade (ADR-084):
      1. Produtivo exclusivo  — custo em regiões onde só esta atividade está ativa
      2. Produtivo compartilhado (overlap) — custo em regiões de sobreposição com outra atividade,
           dividido igualmente (Shapley simétrico) entre os participantes da região
      3. Ocioso (gap) — custo imputado ao sucessor crítico pelos períodos de gap causados pela
           predecessão na DAG

    Parâmetros
    ----------
    items_com_janela   : lista de dicts com item_id, T_start, T_end, machine_weeks, required
    c_mob, c_demob     : custo de mobilização/desmobilização do contrato
    c_unit_semana      : custo unitário por máquina-semana
    quantidade_contratada : pool_size (número de unidades do recurso)
    T_contrato_start   : início do contrato em índice de semana
    T_contrato_end     : fim do contrato em índice de semana
    atribuicao         : {item_id: (custo_total, tipo, machine_weeks)} — ADR-071 D3
    cadeias            : cadeias de perpetuação para calcular predecessor_critico_id
    """
    qt = quantidade_contratada
    n = len(items_com_janela)
    if n == 0:
        return []

    # Predecessor por item (da cadeia de perpetuação)
    predecessor_map = _build_predecessor_map(items_com_janela, cadeias)

    # Se eule não disponível, delega ao caminho Fase 2
    if not _EULE_AVAILABLE:
        return _compute_particao_por_tipo(
            items=items_com_janela,
            cadeias=cadeias,
            atribuicao=atribuicao,
            custo_unit_semanal=c_unit_semana,
            quantidade_contratada=qt,
            c_mob=c_mob,
            c_demob=c_demob,
        )

    # Construir IntervalSet por atividade
    sets = {
        it["item_id"]: IntervalSet([Interval(it["T_start"], it["T_end"])])
        for it in items_com_janela
        if it["T_end"] > it["T_start"]
    }
    if not sets:
        return _compute_particao_por_tipo(
            items=items_com_janela,
            cadeias=cadeias,
            atribuicao=atribuicao,
            custo_unit_semanal=c_unit_semana,
            quantidade_contratada=qt,
            c_mob=c_mob,
            c_demob=c_demob,
        )

    diagram = _euler(sets)

    phi, custo_excl, custo_comp, overlap_sem = _impute_euler_regions(diagram, items_com_janela, c_unit_semana, qt)
    mob_imputado, demob_imputado = _impute_mob_demob(cadeias, items_com_janela, phi, c_mob, c_demob, qt)
    custo_ocioso = _impute_gaps(diagram, items_com_janela, phi, c_unit_semana, qt, T_contrato_start, T_contrato_end)

    # 4. Montar CustoParticionadoItem
    result = [
        _build_particionado_item(
            it,
            it["item_id"],
            custo_excl,
            custo_comp,
            mob_imputado,
            demob_imputado,
            custo_ocioso,
            atribuicao,
            predecessor_map,
            overlap_sem,
            c_mob,
            c_demob,
            c_unit_semana,
            qt,
        )
        for it in items_com_janela
    ]

    return result


def _build_particionado_item(
    it: dict,
    iid: str,
    custo_excl: dict,
    custo_comp: dict,
    mob_imputado: dict,
    demob_imputado: dict,
    custo_ocioso: dict,
    atribuicao: dict,
    predecessor_map: dict,
    overlap_sem: dict,
    c_mob: float,
    c_demob: float,
    c_unit_semana: float,
    qt: int,
) -> CustoParticionadoItem:
    """Builds one CustoParticionadoItem from partitioned cost dicts."""
    required_i = it.get("required", qt)
    custo_autonomo = round(
        (it["T_end"] - it["T_start"]) * c_unit_semana * required_i + (c_mob + c_demob) * required_i, 2
    )
    mob_standalone = round((c_mob + c_demob) * required_i, 2)
    economia_mob_i = round(max(0.0, mob_standalone - mob_imputado[iid] - demob_imputado[iid]), 2)
    custo_total = round(atribuicao.get(iid, (0.0, "", 0.0))[0], 2)
    oci = round(custo_ocioso[iid], 2)
    return CustoParticionadoItem(
        item_id=iid,
        custo_produtivo=round(custo_excl[iid] + custo_comp[iid], 2),
        custo_mob_imputado=round(mob_imputado[iid] + demob_imputado[iid], 2),
        custo_ocioso_imputado=oci,
        custo_total_particionado=custo_total,
        economia_mob=economia_mob_i,
        overhead_ocioso=oci,
        custo_produtivo_exclusivo=round(custo_excl[iid], 2),
        custo_produtivo_compartilhado=round(custo_comp[iid], 2),
        custo_demob_imputado=demob_imputado[iid],
        custo_total_autonomo=custo_autonomo,
        economia_vs_autonomo=round(custo_autonomo - custo_total, 2),
        predecessor_critico_id=predecessor_map.get(iid),
        overlap_semanas=round(overlap_sem[iid], 4),
    )


def _compute_ocioso_para_item(iid: str, cadeia, item_by_id: dict, custo_unit_semanal: float, qt: int) -> float:
    """Computes idle gap cost for iid as successor in cadeia."""
    if cadeia is None:
        return 0.0
    chain_sorted = sorted(
        [item_by_id[x] for x in cadeia.item_ids if x in item_by_id], key=lambda x: (x["start_idx"], x["end_idx"])
    )
    total = 0.0
    for k, chain_it in enumerate(chain_sorted):
        if chain_it["item_id"] == iid and k > 0:
            prev = chain_sorted[k - 1]
            gap_weeks = max(0, chain_it["start_idx"] - prev["end_idx"])
            total += custo_unit_semanal * qt * gap_weeks
    return round(total, 2)


def _compute_particao_por_tipo(
    items: list[dict],
    cadeias: list[CadeiaPerpetuacao],
    atribuicao: dict[str, tuple[float, str, float]],
    custo_unit_semanal: float,
    quantidade_contratada: int,
    c_mob: float,
    c_demob: float,
) -> list[CustoParticionadoItem]:
    """Computa CustoParticionadoItem para cada item do tipo — ADR-083.

    Cada item recebe:
    - custo_produtivo: machine_weeks × custo_unit (custo de tempo produtivo direto)
    - custo_mob_imputado: Shapley igualitário do mob/demob da cadeia de perpetuação
    - custo_ocioso_imputado: custo do idle gap antes deste item (causalidade do sucessor)
    - custo_total_particionado: = custo_atribuido_i (ADR-071 D3 — autoridade de faturamento)
    - economia_mob: mob_standalone − mob_imputado (>0 quando pool economiza mob/demob)
    - overhead_ocioso: = custo_ocioso_imputado (custo de gap atribuído causalmente)

    Invariante: Σ custo_total_particionado = custo_total_contrato (via ADR-071 D3).
    """
    item_by_id = {it["item_id"]: it for it in items}
    qt = quantidade_contratada

    # Build item_id → chain lookup
    item_to_cadeia: dict[str, CadeiaPerpetuacao] = {}
    for cadeia in cadeias:
        for iid in cadeia.item_ids:
            item_to_cadeia[iid] = cadeia

    result: list[CustoParticionadoItem] = []

    for it in items:
        iid = it["item_id"]
        machine_weeks_i = it["machine_weeks"]
        required_i = it["required"]

        # Custo produtivo: tempo produtivo ao custo unitário do contrato
        custo_produtivo = round(custo_unit_semanal * machine_weeks_i, 2)

        # Mob/demob: Shapley igualitário dentro da cadeia
        cadeia = item_to_cadeia.get(iid)
        n_members = len(cadeia.item_ids) if cadeia else 1
        mob_chain_total = (c_mob + c_demob) * qt
        custo_mob_imputado = round(mob_chain_total / n_members, 2) if n_members > 0 else 0.0

        # Economia de mob vs. standalone (item teria pago c_mob+c_demob sozinho)
        mob_standalone = round((c_mob + c_demob) * required_i, 2)
        economia_mob = round(max(0.0, mob_standalone - custo_mob_imputado), 2)

        custo_ocioso_imputado = _compute_ocioso_para_item(iid, cadeia, item_by_id, custo_unit_semanal, qt)

        # custo_total_particionado = atribuição autoritativa (ADR-071 D3)
        custo_total_particionado = round(atribuicao.get(iid, (0.0, "", 0.0))[0], 2)

        # Baseline autônomo: custo se o item contratasse o recurso sozinho.
        # Mesma fórmula do caminho Euler (particionar_contrato) — garante que
        # gap_pool_overhead e economia_vs_autonomo sejam corretos mesmo sem eule.
        custo_autonomo = round(
            (it.get("T_end", 0.0) - it.get("T_start", 0.0)) * custo_unit_semanal * required_i
            + (c_mob + c_demob) * required_i,
            2,
        )

        result.append(
            CustoParticionadoItem(
                item_id=iid,
                custo_produtivo=custo_produtivo,
                custo_mob_imputado=custo_mob_imputado,
                custo_ocioso_imputado=custo_ocioso_imputado,
                custo_total_particionado=custo_total_particionado,
                economia_mob=economia_mob,
                overhead_ocioso=custo_ocioso_imputado,
                # Fase 3 — disponível mesmo no fallback sem eule (ADR-083/089 §historical-fix)
                # custo_produtivo_exclusivo = produtivo puro (sem sobreposição no fallback)
                custo_produtivo_exclusivo=custo_produtivo,
                custo_produtivo_compartilhado=0.0,
                custo_demob_imputado=round(custo_mob_imputado / 2, 2),  # 50/50 Shapley
                custo_total_autonomo=custo_autonomo,
                economia_vs_autonomo=round(custo_autonomo - custo_total_particionado, 2),
            )
        )

    return result


# ---------------------------------------------------------------------------
# ADR-077: Resource Instance Utilization Map
# ---------------------------------------------------------------------------

# Threshold: instância com standby > 35% é marcada como "alto standby"
_STANDBY_THRESHOLD_PCT = 35.0


def _compress_to_segments(week_map: dict) -> list:
    """Comprime {semana: activity_id} em segmentos contínuos por atividade — ADR-083."""
    if not week_map:
        return []
    sorted_w = sorted(week_map.keys(), key=_week_idx)
    segs: list[SegmentoAtividade] = []
    cur_act = week_map[sorted_w[0]]
    cur_start = sorted_w[0]
    cur_end = sorted_w[0]
    count = 1
    for w in sorted_w[1:]:
        act = week_map[w]
        if act == cur_act:
            cur_end = w
            count += 1
        else:
            segs.append(
                SegmentoAtividade(activity_id=cur_act, semana_inicio=cur_start, semana_fim=cur_end, machine_weeks=count)
            )
            cur_act = act
            cur_start = w
            cur_end = w
            count = 1
    segs.append(
        SegmentoAtividade(activity_id=cur_act, semana_inicio=cur_start, semana_fim=cur_end, machine_weeks=count)
    )
    return segs


def _compute_instancia_idle_gaps(
    aw: list,
    contract_start_idx: int,
    contract_end_idx: int,
    c_mo: float,
    c_idle_unit: float,
    c_mob_unit: float,
    c_demob_unit: float,
) -> tuple:
    """Compute idle/off weeks and idle segments for ADR-085 per-instance lifecycle.

    Returns (idle_w, semanas_off, desmob_aplicada, idle_segs, sm_mob, sm_demob)
    """
    mob_idx = _week_idx(aw[0])
    last_idx = _week_idx(aw[-1])
    idle_week_cost = c_mo + c_idle_unit
    remob_cost = c_mob_unit + c_demob_unit
    idle_w = 0
    off_internal = 0
    idle_segs: list[SegmentoAtividade] = []
    for k in range(1, len(aw)):
        gap = _week_idx(aw[k]) - _week_idx(aw[k - 1]) - 1
        if gap <= 0:
            continue
        if idle_week_cost * gap <= remob_cost:
            idle_w += gap
            between = enumerar_semanas(aw[k - 1], aw[k])[1:-1]
            if between:
                idle_segs.append(
                    SegmentoAtividade(
                        activity_id="__idle__",
                        semana_inicio=between[0],
                        semana_fim=between[-1],
                        machine_weeks=len(between),
                    )
                )
        else:
            off_internal += gap
    leading_off = max(0, mob_idx - contract_start_idx)
    trailing_off = max(0, contract_end_idx - last_idx)
    semanas_off = leading_off + trailing_off + off_internal
    desmob_aplicada = trailing_off > 0
    return idle_w, semanas_off, desmob_aplicada, idle_segs


def _compute_instancia_lifecycle(
    i: int,
    instance_week_map: dict,
    contrato,
    contract_start_idx: int,
    contract_end_idx: int,
    apply_idle_gaps: bool,
    c_mo: float,
    c_eq: float,
    c_comb: float,
    c_mat: float,
    c_idle_unit: float,
    c_mob_unit: float,
    c_demob_unit: float,
    prod_w: int,
    mobilizacao_por_instancia: dict,
) -> tuple:
    """Compute ADR-085 lifecycle fields for one slot. Returns lifecycle tuple."""
    sm_mob = sm_demob = ""
    semanas_off = 0
    ca_mo = ca_eq = ca_comb = ca_mat = ci_mo = ci_eq = c_demob_i = custo_inst_total = 0.0
    desmob_aplicada = False
    idle_segs: list[SegmentoAtividade] = []
    if not (apply_idle_gaps and instance_week_map[i]):
        return (
            sm_mob,
            sm_demob,
            semanas_off,
            ca_mo,
            ca_eq,
            ca_comb,
            ca_mat,
            ci_mo,
            ci_eq,
            c_demob_i,
            desmob_aplicada,
            custo_inst_total,
            idle_segs,
        )
    aw = sorted(instance_week_map[i].keys(), key=_week_idx)
    idle_w, semanas_off, desmob_aplicada, idle_segs = _compute_instancia_idle_gaps(
        aw, contract_start_idx, contract_end_idx, c_mo, c_idle_unit, c_mob_unit, c_demob_unit
    )
    cc = calcular_custo_instancia_composicional(
        prod_weeks=prod_w,
        idle_weeks=idle_w,
        c_mo=c_mo,
        c_eq=c_eq,
        c_comb=c_comb,
        c_mat=c_mat,
        c_idle_eq=c_idle_unit,
        c_demob_efetivo=0.0,
    )
    ca_mo, ca_eq, ca_comb, ca_mat = cc["ativo_mo"], cc["ativo_eq"], cc["ativo_comb"], cc["ativo_mat"]
    ci_mo, ci_eq = cc["idle_mo"], cc["idle_eq"]
    custo_inst_total = cc["total"]
    sm_mob = aw[0]
    sm_demob = aw[-1] if desmob_aplicada else contrato.semana_fim
    mobilizacao_por_instancia[i] = sm_mob
    return (
        sm_mob,
        sm_demob,
        semanas_off,
        ca_mo,
        ca_eq,
        ca_comb,
        ca_mat,
        ci_mo,
        ci_eq,
        c_demob_i,
        desmob_aplicada,
        custo_inst_total,
        idle_segs,
    )


def _compute_desmob_antecipada(
    ultima_atividade: str, c_idle_unit: float, custo_demob_unit: float, contract_end_idx: int
) -> tuple:
    """Returns (semanas_antecipacao, economia_desmob) for ADR-079B."""
    if not ultima_atividade or c_idle_unit <= 0 or custo_demob_unit <= 0:
        return 0, 0.0
    trailing = contract_end_idx - _week_idx(ultima_atividade)
    if trailing <= 0:
        return 0, 0.0
    economia = c_idle_unit * trailing - custo_demob_unit
    return (trailing, round(economia, 2)) if economia > 0 else (0, 0.0)


def _build_demand_per_week(dist: dict, required: int, total_peak: int) -> dict:
    """Converts distribuicao_semanal into {week: demand_int} for a single tipo."""
    demand_per_week: dict[str, int] = {}
    for w, d in dist.items():
        ne = getattr(d, "num_equipes", 0) or 0
        if ne > 0:
            demand = max(0, round(ne * required / total_peak))
            if demand > 0:
                demand_per_week[w] = demand
    return demand_per_week


def _item_demand_for_tipo(
    iid: str, tipo_id: str, tipo_map: dict, item_total_peak: dict, sched_lookup: dict
) -> dict | None:
    """Returns demand_per_week dict for iid×tipo_id, or None to skip."""
    if tipo_id not in tipo_map:
        return None
    required = tipo_map[tipo_id]
    total_peak = item_total_peak.get(iid, 1) or 1
    sa = sched_lookup.get(iid)
    if not sa:
        return None
    dist = getattr(sa, "distribuicao_semanal", None) or {}
    demand_per_week = _build_demand_per_week(dist, required, total_peak)
    return demand_per_week if demand_per_week else None


def _collect_items_data_for_tipo(
    tipo_id: str, item_tipo_required: dict, item_total_peak: dict, sched_lookup: dict
) -> list:
    """Builds items_data list for a given tipo_id."""
    items_data = []
    for iid, tipo_map in item_tipo_required.items():
        required = tipo_map.get(tipo_id)
        if required is None:
            continue
        demand_per_week = _item_demand_for_tipo(iid, tipo_id, tipo_map, item_total_peak, sched_lookup)
        if not demand_per_week:
            continue
        active_weeks_sorted = sorted(demand_per_week.keys(), key=_week_idx)
        items_data.append(
            {
                "item_id": iid,
                "required": required,
                "demand_per_week": demand_per_week,
                "active_weeks": active_weeks_sorted,
                "machine_weeks": sum(demand_per_week.values()),
                "start_idx": _week_idx(active_weeks_sorted[0]),
                "end_idx": _week_idx(active_weeks_sorted[-1]),
            }
        )
    return items_data


def _assign_week(
    week: str,
    week_activity_demand: dict,
    span_by_item: dict,
    n: int,
    instance_active: dict,
    instance_activities: dict,
    instance_last_active_week: dict,
    instance_week_map: dict,
    instance_standby: dict,
) -> None:
    """Greedy-assigns one week's activities to instance slots, rest get standby."""
    activities_in_week = week_activity_demand.get(week, {})
    sorted_acts_w = sorted(activities_in_week.items(), key=lambda kv: -span_by_item.get(kv[0], 0))
    cursor = 1
    for act_id, demand in sorted_acts_w:
        for j in range(cursor, min(cursor + demand, n + 1)):
            instance_active[j] += 1
            instance_activities[j].add(act_id)
            instance_last_active_week[j] = week
            instance_week_map[j][week] = act_id
        cursor = min(cursor + demand, n + 1)
    for j in range(cursor, n + 1):
        instance_standby[j] += 1


def _build_week_demand_maps(items_data: list) -> tuple:
    """Returns (week_demand, week_activity_demand) aggregated from items_data."""
    week_demand: dict[str, int] = {}
    week_activity_demand: dict[str, dict[str, int]] = {}
    for item in items_data:
        for w, d in item["demand_per_week"].items():
            week_demand[w] = week_demand.get(w, 0) + d
            week_activity_demand.setdefault(w, {})[item["item_id"]] = d
    return week_demand, week_activity_demand


def _init_instance_slots(n: int) -> tuple:
    """Initializes per-instance tracking dicts for n slots."""
    return (
        {i: 0 for i in range(1, n + 1)},
        {i: 0 for i in range(1, n + 1)},
        {i: set() for i in range(1, n + 1)},
        {i: "" for i in range(1, n + 1)},
        {i: {} for i in range(1, n + 1)},
    )


def _assign_instances(items_data: list, n: int, semanas_contrato: int) -> tuple:
    """Runs greedy instance assignment. Returns (instance_active, instance_standby, instance_activities,
    instance_last_active_week, instance_week_map, all_weeks_sorted)."""
    week_demand, week_activity_demand = _build_week_demand_maps(items_data)
    all_weeks_sorted = sorted(week_demand.keys(), key=_week_idx)
    span_by_item = {it["item_id"]: it["end_idx"] - it["start_idx"] for it in items_data}
    instance_active, instance_standby, instance_activities, instance_last_active_week, instance_week_map = (
        _init_instance_slots(n)
    )
    for week in all_weeks_sorted:
        _assign_week(
            week,
            week_activity_demand,
            span_by_item,
            n,
            instance_active,
            instance_activities,
            instance_last_active_week,
            instance_week_map,
            instance_standby,
        )
    zero_demand_weeks = max(0, semanas_contrato - len(all_weeks_sorted))
    for i in range(1, n + 1):
        instance_standby[i] += zero_demand_weeks
    return (
        instance_active,
        instance_standby,
        instance_activities,
        instance_last_active_week,
        instance_week_map,
        all_weeks_sorted,
    )


def _emit_standby_validation(
    tipo_id: str,
    instancias_standby_alto: list,
    instance_active: dict,
    instance_standby: dict,
    n: int,
    taxa_geral: float,
    custo_standby_total: float,
    status_util: str,
    validacoes: list,
) -> None:
    """Emits VAL-SLOT-STANDBY-ALTO validation if there are high-standby instances."""
    if not instancias_standby_alto:
        return
    standby_detail = "; ".join(
        f"{tipo_id}-{i:02d}: {instance_standby[i]}w idle"
        for i in range(1, n + 1)
        if (instance_active[i] + instance_standby[i]) > 0
        and instance_standby[i] / (instance_active[i] + instance_standby[i]) * 100 > _STANDBY_THRESHOLD_PCT
    )
    val_status = "ERRO" if status_util == "CRITICO" else "AVISO"
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-SLOT-STANDBY-ALTO",
            status=val_status,
            mensagem=(
                f"ADR-077: Contrato {tipo_id} — {len(instancias_standby_alto)} instância(s) "
                f"com standby >{_STANDBY_THRESHOLD_PCT:.0f}%: {standby_detail}. "
                f"Taxa global: {taxa_geral:.1f}%. Custo standby: R$ {custo_standby_total:,.2f}."
            ),
        )
    )


def _build_resumo_e_validacoes(
    tipo_id: str,
    contrato,
    n: int,
    instance_active: dict,
    instance_standby: dict,
    custo_standby_rate: float,
    validacoes: list,
) -> ResumoUtilizacaoContrato:
    """Build ResumoUtilizacaoContrato and emit standby validations."""
    mw_disponiveis = n * contrato.semanas_contrato
    mw_usados = sum(instance_active.values())
    mw_standby = sum(instance_standby.values())
    taxa_geral = round(mw_usados / mw_disponiveis * 100, 1) if mw_disponiveis > 0 else 100.0
    custo_standby_total = round(custo_standby_rate * mw_standby, 2)
    instancias_standby_alto = [
        f"{tipo_id}-{i:02d}"
        for i in range(1, n + 1)
        if (instance_active[i] + instance_standby[i]) > 0
        and instance_standby[i] / (instance_active[i] + instance_standby[i]) * 100 > _STANDBY_THRESHOLD_PCT
    ]
    if taxa_geral >= 65.0:
        status_util = "OK"
    elif taxa_geral >= 35.0:
        status_util = "AVISO"
    else:
        status_util = "CRITICO"
    resumo = ResumoUtilizacaoContrato(
        contrato_id=contrato.contrato_id,
        tipo_id=tipo_id,
        quantidade_contratada=n,
        semanas_contrato=contrato.semanas_contrato,
        machine_weeks_disponiveis=mw_disponiveis,
        machine_weeks_usados=mw_usados,
        machine_weeks_standby=mw_standby,
        taxa_utilizacao_pct=taxa_geral,
        custo_standby_total=custo_standby_total,
        instancias_standby_alto=instancias_standby_alto,
        status_utilizacao=status_util,
    )
    _emit_standby_validation(
        tipo_id,
        instancias_standby_alto,
        instance_active,
        instance_standby,
        n,
        taxa_geral,
        custo_standby_total,
        status_util,
        validacoes,
    )
    return resumo


def _build_instancia_slot(
    i: int,
    tipo_id: str,
    contrato,
    instance_active: dict,
    instance_standby: dict,
    instance_activities: dict,
    instance_last_active_week: dict,
    instance_week_map: dict,
    custo_standby_rate: float,
    c_idle_unit: float,
    apply_idle_gaps: bool,
    contract_start_idx: int,
    contract_end_idx: int,
    _c_mo: float,
    _c_eq: float,
    _c_comb: float,
    _c_mat: float,
    _c_mob_unit: float,
    _c_demob_unit: float,
    mobilizacao_por_instancia: dict,
) -> InstanciaRecurso:
    """Builds one InstanciaRecurso for slot i."""
    s_ativas = instance_active[i]
    s_standby = instance_standby[i]
    total_w = s_ativas + s_standby
    taxa = round(s_ativas / total_w * 100, 1) if total_w > 0 else 100.0
    custo_sb = round(custo_standby_rate * s_standby, 2)
    ultima_atividade = instance_last_active_week[i]
    semanas_antecipacao, economia_desmob = _compute_desmob_antecipada(
        ultima_atividade, c_idle_unit, contrato.custo_demob_unit, contract_end_idx
    )
    (
        sm_mob,
        sm_demob,
        semanas_off,
        ca_mo,
        ca_eq,
        ca_comb,
        ca_mat,
        ci_mo,
        ci_eq,
        c_demob_i,
        desmob_aplicada,
        custo_inst_total,
        _idle_segs,
    ) = _compute_instancia_lifecycle(
        i,
        instance_week_map,
        contrato,
        contract_start_idx,
        contract_end_idx,
        apply_idle_gaps,
        _c_mo,
        _c_eq,
        _c_comb,
        _c_mat,
        c_idle_unit,
        _c_mob_unit,
        _c_demob_unit,
        s_ativas,
        mobilizacao_por_instancia,
    )
    return InstanciaRecurso(
        instancia_id=f"{tipo_id}-{i:02d}",
        contrato_id=contrato.contrato_id,
        tipo_id=tipo_id,
        numero=i,
        semana_entrada=contrato.semana_inicio,
        semana_saida=contrato.semana_fim,
        semanas_ativas=s_ativas,
        semanas_standby=s_standby,
        taxa_utilizacao_pct=taxa,
        custo_standby=custo_sb,
        atividades_cobertas=sorted(instance_activities[i]),
        semana_ultima_atividade=ultima_atividade,
        semanas_antecipacao_possivel=semanas_antecipacao,
        economia_desmobilizacao_antecipada=economia_desmob,
        desmob_antecipada_aplicada=desmob_aplicada,
        segmentos_atividade=_compress_to_segments(instance_week_map[i]),
        semana_mobilizacao=sm_mob,
        semana_desmobilizacao=sm_demob,
        semanas_off=semanas_off,
        custo_ativo_mo=ca_mo,
        custo_ativo_eq=ca_eq,
        custo_ativo_comb=ca_comb,
        custo_ativo_mat=ca_mat,
        custo_idle_mo=ci_mo,
        custo_idle_eq=ci_eq,
        custo_demob_instancia=c_demob_i,
        custo_instancia_total=custo_inst_total,
        segmentos_idle=_idle_segs,
    )


def _build_composicao_entry(
    item: dict, tipo_id: str, contrato, n: int, instance_activities: dict
) -> ComposicaoEquipeAtividade:
    """Builds ComposicaoEquipeAtividade for a single item."""
    iid = item["item_id"]
    inst_nums = sorted(i for i in range(1, n + 1) if iid in instance_activities[i])
    return ComposicaoEquipeAtividade(
        activity_id=iid,
        tipo_id=tipo_id,
        contrato_id=contrato.contrato_id,
        pool_size=n,
        n_instancias=len(inst_nums),
        required=item["required"],
        instancias_numeros=inst_nums,
        semana_inicio=item["active_weeks"][0] if item["active_weeks"] else "",
        semana_fim=item["active_weeks"][-1] if item["active_weeks"] else "",
        machine_weeks=item["machine_weeks"],
    )


def _build_instancias_for_tipo(
    tipo_id: str, contrato, item_tipo_required: dict, item_total_peak: dict, sched_lookup: dict, validacoes: list
) -> tuple:
    """Builds instancias/composicoes/resumo for a single tipo_id contrato."""
    n = contrato.quantidade_contratada
    if n <= 0:
        return [], [], []
    items_data = _collect_items_data_for_tipo(tipo_id, item_tipo_required, item_total_peak, sched_lookup)
    if not items_data:
        return [], [], []

    (
        instance_active,
        instance_standby,
        instance_activities,
        instance_last_active_week,
        instance_week_map,
        _all_weeks_sorted,
    ) = _assign_instances(items_data, n, contrato.semanas_contrato)
    c_idle_unit = contrato.custo_idle_semanal_unit
    custo_standby_rate = c_idle_unit if c_idle_unit > 0 else contrato.custo_unit_semanal
    contract_end_idx = _week_idx(contrato.semana_fim)
    apply_idle_gaps = c_idle_unit > 0
    contract_start_idx = _week_idx(contrato.semana_inicio)
    _c_mo = contrato.custo_unit_semanal_mo
    _c_eq = contrato.custo_unit_semanal_eq
    _c_comb = contrato.custo_unit_semanal_comb
    _c_mat = contrato.custo_unit_semanal_mat
    _c_mob_unit = contrato.custo_mob_unit
    _c_demob_unit = contrato.custo_demob_unit
    mobilizacao_por_instancia: dict[int, str] = {}

    instancias = [
        _build_instancia_slot(
            i,
            tipo_id,
            contrato,
            instance_active,
            instance_standby,
            instance_activities,
            instance_last_active_week,
            instance_week_map,
            custo_standby_rate,
            c_idle_unit,
            apply_idle_gaps,
            contract_start_idx,
            contract_end_idx,
            _c_mo,
            _c_eq,
            _c_comb,
            _c_mat,
            _c_mob_unit,
            _c_demob_unit,
            mobilizacao_por_instancia,
        )
        for i in range(1, n + 1)
    ]

    if mobilizacao_por_instancia:
        contrato.mobilizacao_por_instancia = dict(sorted(mobilizacao_por_instancia.items()))

    composicoes = [_build_composicao_entry(item, tipo_id, contrato, n, instance_activities) for item in items_data]

    resumo = _build_resumo_e_validacoes(
        tipo_id, contrato, n, instance_active, instance_standby, custo_standby_rate, validacoes
    )
    return instancias, composicoes, [resumo]


def _build_item_resource_maps(activities: list) -> tuple:
    """Returns (item_tipo_required, item_total_peak) from activities list."""
    item_tipo_required: dict[str, dict[str, int]] = {}
    item_total_peak: dict[str, int] = {}
    for act in activities:
        iid = act.get("item_id")
        rr = act.get("required_resources", {})
        if iid and rr:
            item_tipo_required[iid] = {k: int(v) for k, v in rr.items()}
            item_total_peak[iid] = sum(int(v) for v in rr.values()) or 1
    return item_tipo_required, item_total_peak


def _build_instancias_recurso(
    contratos: list[RecursoContrato],
    rcpsp_spec: dict,
    sched_lookup: dict,
    validacoes: list,
) -> tuple[list[InstanciaRecurso], list[ComposicaoEquipeAtividade], list[ResumoUtilizacaoContrato]]:
    """ADR-077: Constrói o mapa instancial de utilização de recursos.

    Para cada contrato de pool (tipo_id), cria N instâncias numeradas e rastreia
    seu ciclo de vida (ATIVO vs. STANDBY) baseado na demanda do cronograma RCPSP.

    Algoritmo de atribuição (guloso por prioridade):
    - Em cada semana, atividades são ordenadas por machine_weeks decrescentes.
    - Os slots de menor número são atribuídos às atividades de maior prioridade.
    - Slots restantes (além da demanda total) ficam STANDBY.

    Parâmetros
    ----------
    contratos    : contratos de pool já calculados por _build_contratos_recurso
    rcpsp_spec   : dict com 'resource_pool' e 'activities[].required_resources'
    sched_lookup : {activity_id: ScheduledActivityCanonical}
    validacoes   : lista acumulada — recebe VAL-SLOT-STANDBY-ALTO

    Retorna
    -------
    (instancias, composicoes, resumos) — um por slot, por atividade×tipo, por contrato
    """
    activities = rcpsp_spec.get("activities", [])
    if not contratos or not activities:
        return [], [], []

    item_tipo_required, item_total_peak = _build_item_resource_maps(activities)

    contrato_map = {c.tipo_id: c for c in contratos}
    all_instancias: list[InstanciaRecurso] = []
    all_composicoes: list[ComposicaoEquipeAtividade] = []
    all_resumos: list[ResumoUtilizacaoContrato] = []

    for tipo_id, contrato in contrato_map.items():
        insts, comps, resumos = _build_instancias_for_tipo(
            tipo_id, contrato, item_tipo_required, item_total_peak, sched_lookup, validacoes
        )
        all_instancias.extend(insts)
        all_composicoes.extend(comps)
        all_resumos.extend(resumos)

    return all_instancias, all_composicoes, all_resumos


# ---------------------------------------------------------------------------
# ADR-085: Custo instancial composicional — substitui custo monolítico do contrato
# ---------------------------------------------------------------------------


def _scale_part_entry(
    part,
    escala: float,
    novo_total: float,
    tot_mo: float,
    tot_eq: float,
    tot_comb: float,
    tot_mat: float,
    eq_by_item: dict,
) -> None:
    """Scales one CustoParticionadoItem in place for _reescalar_particao."""
    part.custo_produtivo = round(part.custo_produtivo * escala, 2)
    part.custo_mob_imputado = round(part.custo_mob_imputado * escala, 2)
    part.custo_ocioso_imputado = round(part.custo_ocioso_imputado * escala, 2)
    part.overhead_ocioso = round(part.overhead_ocioso * escala, 2)
    part.custo_produtivo_exclusivo = round(part.custo_produtivo_exclusivo * escala, 2)
    part.custo_produtivo_compartilhado = round(part.custo_produtivo_compartilhado * escala, 2)
    part.custo_demob_imputado = round(part.custo_demob_imputado * escala, 2)
    part.custo_total_particionado = round(part.custo_total_particionado * escala, 2)
    part.economia_vs_autonomo = round(part.custo_total_autonomo - part.custo_total_particionado, 2)
    frac_item = (part.custo_total_particionado / novo_total) if novo_total > 0 else 0.0
    part.custo_inst_eq = round(tot_eq * frac_item, 2)
    part.custo_inst_comb = round(tot_comb * frac_item, 2)
    part.custo_inst_mat = round(tot_mat * frac_item, 2)
    part.custo_inst_mo = round(
        part.custo_total_particionado - part.custo_inst_eq - part.custo_inst_comb - part.custo_inst_mat, 2
    )
    eq = eq_by_item.get(part.item_id)
    if eq is not None:
        eq.custo_total = part.custo_total_particionado


def _sum_inst_categories(insts_contrato: list) -> tuple:
    """Returns (tot_mo, tot_eq, tot_comb, tot_mat) sums from instancias list."""
    tot_mo = sum(i.custo_ativo_mo + i.custo_idle_mo for i in insts_contrato)
    tot_eq = sum(i.custo_ativo_eq + i.custo_idle_eq + i.custo_demob_instancia for i in insts_contrato)
    tot_comb = sum(i.custo_ativo_comb for i in insts_contrato)
    tot_mat = sum(i.custo_ativo_mat for i in insts_contrato)
    return tot_mo, tot_eq, tot_comb, tot_mat


def _reescalar_particao(contrato, novo_total: float, insts_contrato: list, eq_by_item: dict, validacoes: list) -> None:
    """Reescala partição_por_item e emite VAL-INST-CAT-SOMA."""
    antigo_total = float(contrato.custo_total_contrato or 0.0)
    escala = novo_total / antigo_total if antigo_total > 0 else 1.0
    contrato.custo_total_contrato = novo_total
    tot_mo, tot_eq, tot_comb, tot_mat = _sum_inst_categories(insts_contrato)
    for part in contrato.particao_por_item:
        _scale_part_entry(part, escala, novo_total, tot_mo, tot_eq, tot_comb, tot_mat, eq_by_item)
    _max_dev = max(
        (
            abs((p.custo_inst_mo + p.custo_inst_eq + p.custo_inst_comb + p.custo_inst_mat) - p.custo_total_particionado)
            for p in contrato.particao_por_item
        ),
        default=0.0,
    )
    if _max_dev > 0.05:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-INST-CAT-SOMA",
                status="ERRO",
                mensagem=f"ADR-085: Contrato {contrato.tipo_id} — decomposição categorial não fecha "
                f"(desvio máx R$ {_max_dev:.2f} > 0.05).",
            )
        )


def _apply_instancial_to_contrato(contrato, instancias: list, eq_by_item: dict, validacoes: list) -> None:
    """Applies ADR-085 instancial cost to one contrato if applicable."""
    insts_contrato = [i for i in instancias if i.contrato_id == contrato.contrato_id]
    novo_total = round(sum(inst.custo_instancia_total for inst in insts_contrato), 2)
    antigo_total = float(contrato.custo_total_contrato or 0.0)
    if novo_total <= 0:
        return
    if antigo_total <= 0:
        return
    _reescalar_particao(contrato, novo_total, insts_contrato, eq_by_item, validacoes)
    reducao_pct = round((1.0 - novo_total / antigo_total) * 100, 1)
    n_mob_tardia = len(contrato.mobilizacao_por_instancia)
    n_desmob = sum(1 for inst in insts_contrato if inst.desmob_antecipada_aplicada)
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-MOB-TARDIA-OK",
            status="OK",
            mensagem=(
                f"ADR-085: Contrato {contrato.tipo_id} — custo instancial composicional "
                f"R$ {novo_total:,.2f} (era R$ {antigo_total:,.2f}, −{reducao_pct:.1f}%). "
                f"{n_mob_tardia} instância(s) com mobilização tardia; "
                f"{n_desmob} com desmobilização antecipada efetiva."
            ),
        )
    )


def _aplicar_custo_instancial(
    contratos: list[RecursoContrato],
    instancias: list[InstanciaRecurso],
    equipes: list[EquipeDireta],
    validacoes: list,
) -> None:
    """Substitui custo_total_contrato pela soma dos custos instanciais — ADR-085 D3.

    Para cada contrato com custo instancial composicional ativo (c_idle > 0), o custo
    do contrato passa a ser Σ custo_instancia_total (mobilização tardia + taxa ociosa
    por componente + desmobilização antecipada efetiva), substituindo a fórmula
    monolítica `quantidade × custo_unit × semanas` do ADR-071.

    A atribuição por item (machine-weeks) é preservada (ADR-071 §3.1): apenas o custo
    total é reescalado, mantendo as frações. `eq.custo_total` e
    `CustoParticionadoItem.custo_total_particionado` são atualizados proporcionalmente.

    Mutação in-place de `contratos` e `equipes`. Retrocompatível: contratos sem custo
    instancial (Σ = 0) permanecem com a fórmula monolítica.
    """
    eq_by_item = {eq.item_id: eq for eq in equipes if eq.item_id}
    for contrato in contratos:
        _apply_instancial_to_contrato(contrato, instancias, eq_by_item, validacoes)

    # TD-1: recomputa eq.custo_total como Σ_r custo_total_particionado_ir após ADR-085.
    # Necessário porque _reescalar_particao sobrescreve em vez de acumular (por design —
    # ADR-085 reescala cada contrato independentemente). O acumulado correto é a soma de
    # todas as partições, já reescaladas ou monolíticas.
    pool_total_por_item: dict[str, float] = {}
    for c in contratos:
        for part in c.particao_por_item:
            pool_total_por_item[part.item_id] = pool_total_por_item.get(part.item_id, 0.0) + float(
                getattr(part, "custo_total_particionado", 0.0) or 0.0
            )
    for item_id, total in pool_total_por_item.items():
        eq = eq_by_item.get(item_id)
        if eq is not None and total > 0:
            eq.custo_total = round(total, 2)


# ---------------------------------------------------------------------------
# ADR-104: Enriquecimento de EquipeDireta com decomposição instancial
# ---------------------------------------------------------------------------


def _enrich_equipes_com_decomposicao_instancial(
    equipes: list[EquipeDireta],
    contratos: list[RecursoContrato],
    validacoes: list[ValidacaoItem],
) -> None:
    """Enriquece equipes com decomposição de custos instanciais após ADR-085.

    Copia custo_inst_* de contratos[].particao_por_item[] para equipes[].
    Valida invariante: custo_total == soma(custo_inst_*) com tolerância R$ 0.05.

    Mutação in-place de `equipes`. Apenas items em contratos receberão decomposição.
    """
    eq_by_id = {eq.item_id: eq for eq in equipes}
    # TD-1: reset custo_inst_* para items em contratos antes de acumular
    items_em_contratos = {part.item_id for c in contratos for part in c.particao_por_item}
    for item_id in items_em_contratos:
        eq = eq_by_id.get(item_id)
        if eq is not None:
            eq.custo_inst_mo = 0.0
            eq.custo_inst_eq = 0.0
            eq.custo_inst_comb = 0.0
            eq.custo_inst_mat = 0.0
            eq.custo_inst_mob_demob = 0.0

    for contrato in contratos:
        for part in contrato.particao_por_item:
            eq = eq_by_id.get(part.item_id)
            if eq is None:
                continue

            # TD-1: acumular custo_inst_* sobre todos os contratos (não sobrescrever)
            eq.custo_inst_mo = round((eq.custo_inst_mo or 0.0) + (part.custo_inst_mo or 0.0), 2)
            eq.custo_inst_eq = round((eq.custo_inst_eq or 0.0) + (part.custo_inst_eq or 0.0), 2)
            eq.custo_inst_comb = round((eq.custo_inst_comb or 0.0) + (part.custo_inst_comb or 0.0), 2)
            eq.custo_inst_mat = round((eq.custo_inst_mat or 0.0) + (part.custo_inst_mat or 0.0), 2)
            eq.custo_inst_mob_demob = round(
                (eq.custo_inst_mob_demob or 0.0) + part.custo_mob_imputado + part.custo_demob_imputado,
                2,
            )

            # Validar invariante (detecção precoce de bugs)
            # ADR-085: custo_total_particionado = custo_inst_mo + eq + comb + mat
            # (mob_demob já está incluído em custo_inst_mo como resíduo)
            soma = eq.custo_inst_mo + eq.custo_inst_eq + eq.custo_inst_comb + eq.custo_inst_mat
            desvio = abs(soma - eq.custo_total)

            # ADR-106: Se há desvio significativo, reescalar proporcionalmente para garantir invariante
            if desvio > 1.0:
                if soma > 0:
                    fator_reescala = eq.custo_total / soma
                    eq.custo_inst_mo = round(eq.custo_inst_mo * fator_reescala, 2)
                    eq.custo_inst_eq = round(eq.custo_inst_eq * fator_reescala, 2)
                    eq.custo_inst_comb = round(eq.custo_inst_comb * fator_reescala, 2)
                    eq.custo_inst_mat = round(eq.custo_inst_mat * fator_reescala, 2)
                    eq.custo_inst_mob_demob = round(eq.custo_inst_mob_demob * fator_reescala, 2)

                    validacoes.append(
                        ValidacaoItem(
                            codigo="VAL-DECOMP-REESCALA",
                            status="AVISO",
                            mensagem=(
                                f"Item {part.item_id}: breakdown reescalado proporcionalmente "
                                f"(desvio R$ {desvio:.2f}). Fator: {fator_reescala:.4f}"
                            ),
                        )
                    )
                else:
                    validacoes.append(
                        ValidacaoItem(
                            codigo="VAL-DECOMP-INVARIANTE",
                            status="AVISO",
                            mensagem=(
                                f"Item {part.item_id}: soma decomposição (R$ {soma:,.2f}) "
                                f"≠ custo_total (R$ {eq.custo_total:,.2f}). "
                                f"Desvio: R$ {desvio:.2f} — Não foi possível reescalar (soma = 0)"
                            ),
                        )
                    )


# ---------------------------------------------------------------------------
# ADR-083: Enriquecimento de overhead_ocioso via segmentos instanciais reais
# ---------------------------------------------------------------------------


def _last_week_idx_for_act(segmentos: list, activity_id: str) -> int | None:
    """Returns max week_idx of semana_fim for segments matching activity_id, or None."""
    result = None
    for seg in segmentos:
        if seg.activity_id == activity_id:
            idx = _week_idx(seg.semana_fim)
            result = idx if result is None else max(result, idx)
    return result


def _first_week_idx_for_act(segmentos: list, activity_id: str) -> int | None:
    """Returns min week_idx of semana_inicio for segments matching activity_id, or None."""
    result = None
    for seg in segmentos:
        if seg.activity_id == activity_id:
            idx = _week_idx(seg.semana_inicio)
            result = idx if result is None else min(result, idx)
    return result


def _compute_gap_for_inst(inst, pred_id: str, succ_id: str) -> int:
    """Returns idle weeks between pred and succ in this instance slot."""
    pred_last_idx = _last_week_idx_for_act(inst.segmentos_atividade, pred_id)
    succ_first_idx = _first_week_idx_for_act(inst.segmentos_atividade, succ_id)
    if pred_last_idx is not None and succ_first_idx is not None:
        return max(0, succ_first_idx - pred_last_idx - 1)
    return 0


def _enrich_particao_overhead(
    contratos: list[RecursoContrato],
    cadeias: list[CadeiaPerpetuacao],
    instancias: list[InstanciaRecurso],
) -> None:
    """Atualiza overhead_ocioso / custo_ocioso_imputado em CustoParticionadoItem — ADR-083.

    Usa os segmentos contínuos reais de cada slot (gerados por _build_instancias_recurso)
    para calcular os gaps efetivos entre atividades consecutivas na cadeia, imputando o
    custo de ociosidade ao item *sucessor* (princípio de causalidade do ADR-083).

    Parâmetros
    ----------
    contratos   : contratos de pool com particao_por_item já inicializada
    cadeias     : cadeias de perpetuação (ADR-073) — fornecem a ordem H → I
    instancias  : slots instanciais com segmentos_atividade preenchidos (ADR-077/083)
    """
    # tipo_id → list[InstanciaRecurso]
    insts_por_tipo: dict[str, list[InstanciaRecurso]] = {}
    for inst in instancias:
        insts_por_tipo.setdefault(inst.tipo_id, []).append(inst)

    # tipo_id → {item_id: predecessor_item_id} — apenas itens com antecessor na cadeia
    predecessor_por_tipo: dict[str, dict[str, str]] = {}
    for cadeia in cadeias:
        tipo = cadeia.tipo_id
        for k, iid in enumerate(cadeia.item_ids):
            if k > 0:
                predecessor_por_tipo.setdefault(tipo, {})[iid] = cadeia.item_ids[k - 1]

    for contrato in contratos:
        tipo = contrato.tipo_id
        insts = insts_por_tipo.get(tipo, [])
        preds = predecessor_por_tipo.get(tipo, {})
        unit_cost = contrato.custo_unit_semanal

        for part in contrato.particao_por_item:
            pred_id = preds.get(part.item_id)
            if pred_id is None:
                continue  # primeiro item da cadeia — sem gap para imputar

            total_idle_weeks = sum(_compute_gap_for_inst(inst, pred_id, part.item_id) for inst in insts)

            overhead = round(unit_cost * total_idle_weeks, 2)
            part.custo_ocioso_imputado = overhead
            part.overhead_ocioso = overhead
