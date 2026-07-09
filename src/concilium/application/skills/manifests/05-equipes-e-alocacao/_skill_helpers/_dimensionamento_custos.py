"""Skill 05 — Equipes e Alocação (helpers A, parte extraída de _dimensionamento_equipe.py)."""

from __future__ import annotations

import unicodedata

from concilium.domain.models.canonical import (
    EquipamentoEquipeDireta,
    ValidacaoItem,
)


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
        if _cpu_comp_is_valid(cpu_comp) and isinstance(cpu_comp, dict):
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


def _score_desc_overlap(desc_key: str, desc_i: str) -> float:
    """Pontua a sobreposição textual entre a descrição buscada e a do insumo candidato."""
    if not (desc_key and desc_i):
        return 0.0
    if desc_i == desc_key:
        return 40.0
    a = set(desc_key.split())
    b = set(desc_i.split())
    inter = len(a & b)
    union = len(a | b) or 1
    return 25.0 * (inter / union)


def _score_alias_candidate(ins: dict, equip_id: str, desc_key: str) -> tuple[float, dict] | None:
    """Pontua um insumo candidato a alias; retorna None se não elegível (não-equipamento ou sem consumo)."""
    if str(ins.get("tipo") or "").upper() != "EQUIPAMENTO":
        return None
    attrs = ins.get("atributos_especificos") or {}
    consumo = _to_positive_float_or_none(attrs.get("consumo_litros_hora"))
    if consumo is None:
        return None

    score = 0.0
    cod_plan = str(attrs.get("codigo_planilha") or "").upper().strip()
    if cod_plan and cod_plan == str(equip_id or "").upper().strip():
        score += 50.0
    desc_i = _normalize_text_key(ins.get("descricao") or "")
    score += _score_desc_overlap(desc_key, desc_i)
    return score, attrs


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
        result = _score_alias_candidate(ins, equip_id, desc_key)
        if result is None:
            continue
        score, attrs = result
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


def _resolve_tipo_combustivel(atrib: dict, tipo_combustivel_override, consumo: float) -> str:
    """Resolve o rótulo do tipo de combustível, com fallback 'Diesel S10' quando há consumo."""
    tipo_comb = str(
        tipo_combustivel_override or atrib.get("tipo_combustivel") or atrib.get("combustivel") or ""
    ).strip()
    if not tipo_comb and (consumo and consumo > 0):
        tipo_comb = "Diesel S10"
    return tipo_comb


def _resolve_manutencao_locacao(atrib: dict, custo_base: float, horas_mes: float) -> tuple[float, float, float]:
    """ADR-088: sub-decompõe custo_base em manutenção (horária × horas_mes) e locação (resto)."""
    custo_manut_hora = float(atrib.get("custo_manutencao_hora", 0.0) or 0.0)
    custo_manut = round(custo_manut_hora * horas_mes, 2)
    custo_locacao = round(max(0.0, custo_base - custo_manut), 2)
    return custo_manut_hora, custo_manut, custo_locacao


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
    _tipo_comb = _resolve_tipo_combustivel(_atrib, tipo_combustivel_override, consumo)
    _rental_unit = (_atrib.get("rental_unit") or "hora_produtiva").strip().lower()
    _num_un_int = max(1, round(float(num_unidades)))

    _custo_manut_hora, _custo_manut, _custo_locacao = _resolve_manutencao_locacao(
        _atrib, custo_base, horas_mes_calculadas
    )

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


