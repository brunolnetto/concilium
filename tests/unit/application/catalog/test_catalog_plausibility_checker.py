"""Tests for concilium.application.catalog.plausibility_checker."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from concilium.application.catalog._plausibility_checks import (
    Anomalia,
    _pc_check_equipe_refs,
    _pc_check_prod_item,
    _pc_check_prod_zscore,
    _pc_eq_diesel,
    _pc_eq_locacao,
    _pc_eq_zscore,
    _pc_mo_duplicatas,
    _pc_mo_encargos,
    _pc_mo_salario_minimo,
    _pc_mo_semantica,
    _pc_mo_staleness,
    _pc_mo_zscore,
    _pc_prod_vhs,
)
from concilium.application.catalog.plausibility_checker import (
    _check_equipamento,
    _check_mao_obra,
    _check_produtividades,
    _count_severidades,
    verificar_plausibilidade,
)
from concilium.domain.constants import (
    DIESEL_L_POR_CV_PONT,
    HORAS_MES_CLT,
    SMH,
    VALIDADE_PRECO_DIAS,
    VH_MAX,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TODAY_PATH = "concilium.application.catalog._plausibility_checks._today"

# Price that is comfortably above the minimum wage floor
_PRECO_MO_OK = round(SMH * HORAS_MES_CLT * 2, 2)  # 2× minimum → always valid

# Price that is well below the minimum wage floor (10% of minimum)
_PRECO_MO_LOW = round(SMH * HORAS_MES_CLT * 0.1, 2)


def _mo(
    codigo: str = "MO-001",
    descricao: str = "Servente",
    preco: float = _PRECO_MO_OK,
    unidade: str = "mes",
    data_ref: str | None = None,
    encargos: float | None = None,
) -> dict:
    attrs: dict = {}
    if encargos is not None:
        attrs["percentual_encargos_local"] = encargos
    ins: dict = {
        "tipo": "MAO_OBRA",
        "codigo": codigo,
        "descricao": descricao,
        "preco_unitario": preco,
        "unidade": unidade,
    }
    if attrs:
        ins["atributos_especificos"] = attrs
    if data_ref:
        ins["data_referencia_preco"] = data_ref
    return ins


def _eq(
    codigo: str = "EQ-001",
    preco: float = 50.0,
    consumo: float | None = None,
    pot_cv: float | None = None,
    locacao: float | None = None,
) -> dict:
    attrs: dict = {}
    if consumo is not None:
        attrs["consumo_litros_hora"] = consumo
    if pot_cv is not None:
        attrs["potencia_cv"] = pot_cv
    if locacao is not None:
        attrs["valor_locacao_mensal"] = locacao
    ins: dict = {
        "tipo": "EQUIPAMENTO",
        "codigo": codigo,
        "preco_unitario": preco,
        "descricao": "Equipamento",
    }
    if attrs:
        ins["atributos_especificos"] = attrs
    return ins


def _prod(
    codigo: str = "PROD-001",
    vh: float | None = 100.0,
    funcoes: list | None = None,
    equipamentos: list | None = None,
) -> dict:
    equipe: dict = {}
    if funcoes is not None:
        equipe["funcoes"] = funcoes
    if equipamentos is not None:
        equipe["equipamentos"] = equipamentos
    p: dict = {
        "id": codigo,
        "codigo": codigo,
    }
    if vh is not None:
        p["producao_horaria"] = vh
    if equipe:
        p["composicao_padrao_equipe"] = equipe
    return p


# ===========================================================================
# 1. verificar_plausibilidade — happy path with empty lists
# ===========================================================================


def test_verificar_plausibilidade_empty_lists():
    result = verificar_plausibilidade([], [])
    assert result["ok"] is True
    resumo = result["resumo"]
    assert resumo["total_insumos"] == 0
    assert resumo["total_producoes"] == 0
    assert resumo["anomalias_total"] == 0
    assert resumo["erros"] == 0
    assert resumo["avisos"] == 0
    assert resumo["infos"] == 0
    assert result["anomalias"] == []
    assert result["por_tipo"] == {}


# ===========================================================================
# 2. _pc_mo_salario_minimo
# ===========================================================================


def test_pc_mo_salario_minimo_below_floor():
    ins = _mo(preco=_PRECO_MO_LOW)
    result = _pc_mo_salario_minimo([ins])
    assert len(result) == 1
    a = result[0]
    assert a.severidade == "ERRO"
    assert a.tipo == "FISICO"
    assert a.codigo == ins["codigo"]


def test_pc_mo_salario_minimo_above_floor():
    ins = _mo(preco=_PRECO_MO_OK)
    result = _pc_mo_salario_minimo([ins])
    assert result == []


def test_pc_mo_salario_minimo_estagiario_skipped():
    # Estagiário keyword → should be skipped even with very low price
    ins = _mo(codigo="MO-ESTAGI", descricao="Estagiário", preco=1.0)
    result = _pc_mo_salario_minimo([ins])
    assert result == []


def test_pc_mo_salario_minimo_uses_custom_horas_mes():
    # horas_mes=44 → floor is tiny; a low price might pass
    ins = _mo(preco=100.0)
    ins["atributos_especificos"] = {"horas_mes": 1}
    # preco/horas_mes = 100 >> SMH * 0.95 → no error
    result = _pc_mo_salario_minimo([ins])
    assert result == []


# ===========================================================================
# 3. _pc_mo_encargos
# ===========================================================================


def test_pc_mo_encargos_below_alpha_min():
    # alpha = 1 + (-0.5) = 0.5 < ALPHA_MIN → ERRO
    ins = _mo(encargos=-0.5)
    result = _pc_mo_encargos([ins])
    assert len(result) == 1
    assert result[0].severidade == "ERRO"
    assert result[0].tipo == "FISICO"


def test_pc_mo_encargos_above_alpha_max():
    # alpha = 1 + 5.0 = 6.0 > ALPHA_MAX → ERRO
    ins = _mo(encargos=5.0)
    result = _pc_mo_encargos([ins])
    assert len(result) == 1
    assert result[0].severidade == "ERRO"


def test_pc_mo_encargos_within_range():
    # alpha = 1 + 0.5 = 1.5 → valid
    ins = _mo(encargos=0.5)
    result = _pc_mo_encargos([ins])
    assert result == []


def test_pc_mo_encargos_missing_field():
    # no percentual_encargos_local → no anomaly
    ins = _mo()
    result = _pc_mo_encargos([ins])
    assert result == []


# ===========================================================================
# 4. _pc_mo_duplicatas
# ===========================================================================


def test_pc_mo_duplicatas_same_descricao_preco():
    ins1 = _mo(codigo="MO-A", descricao="Servente", preco=1000.0)
    ins2 = _mo(codigo="MO-B", descricao="Servente", preco=1000.0)
    result = _pc_mo_duplicatas([ins1, ins2])
    assert len(result) == 1
    a = result[0]
    assert a.tipo == "DUPLICATA"
    assert a.severidade == "AVISO"
    assert a.codigo == "MO-B"


def test_pc_mo_duplicatas_different_preco_na_faixa_de_encargos_e_flagueado():
    """ADR-179: mesma descrição + razão de preço (2,0x) dentro da faixa plausível de
    α de encargos não é mais silenciosamente ignorado — mesmo padrão do caso real
    P0058/MO-SALA-TEC (razão 2,06x) que o dedup exato antigo perdia."""
    ins1 = _mo(codigo="MO-A", descricao="Servente", preco=1000.0)
    ins2 = _mo(codigo="MO-B", descricao="Servente", preco=2000.0)
    result = _pc_mo_duplicatas([ins1, ins2])
    assert len(result) == 1
    assert result[0].detalhe["classificacao"] in ("revisar", "duplicata_provavel")


def test_pc_mo_duplicatas_different_descricao_e_preco_fora_da_faixa_fica_limpo():
    ins1 = _mo(codigo="MO-A", descricao="Operador de Escavadeira", preco=1000.0)
    ins2 = _mo(codigo="MO-B", descricao="Operador de Motoniveladora", preco=9000.0)
    result = _pc_mo_duplicatas([ins1, ins2])
    assert result == []


def test_pc_mo_duplicatas_different_descricao():
    ins1 = _mo(codigo="MO-A", descricao="Servente", preco=1000.0)
    ins2 = _mo(codigo="MO-B", descricao="Pedreiro", preco=1000.0)
    result = _pc_mo_duplicatas([ins1, ins2])
    assert result == []


# ===========================================================================
# 5. _pc_mo_semantica
# ===========================================================================


@pytest.mark.parametrize("unidade", ["mes", "mês", "h", "hr"])
def test_pc_mo_semantica_valid_units(unidade):
    ins = _mo(unidade=unidade)
    result = _pc_mo_semantica([ins])
    assert result == []


@pytest.mark.parametrize("unidade", ["dia", "semana", "kg", "un"])
def test_pc_mo_semantica_unusual_unit(unidade):
    ins = _mo(unidade=unidade)
    result = _pc_mo_semantica([ins])
    assert len(result) == 1
    assert result[0].severidade == "AVISO"
    assert result[0].tipo == "SEMANTICO"


# ===========================================================================
# 6. _pc_mo_staleness
# ===========================================================================


def test_pc_mo_staleness_stale(monkeypatch):
    from datetime import timedelta

    ref_date = date(2024, 1, 1)
    today_date = ref_date + timedelta(days=VALIDADE_PRECO_DIAS + 20)  # 200 days later
    monkeypatch.setattr("concilium.application.catalog._plausibility_checks._today", lambda: today_date)
    ins = _mo(data_ref=str(ref_date))
    result = _pc_mo_staleness([ins])
    assert len(result) == 1
    a = result[0]
    assert a.tipo == "STALE"
    assert a.severidade == "INFO"
    assert a.detalhe["dias_atraso"] > VALIDADE_PRECO_DIAS


def test_pc_mo_staleness_fresh(monkeypatch):
    from datetime import timedelta

    ref_date = date(2024, 6, 1)
    today_date = ref_date + timedelta(days=49)  # 49 days later → well within VALIDADE_DIAS
    monkeypatch.setattr("concilium.application.catalog._plausibility_checks._today", lambda: today_date)
    ins = _mo(data_ref=str(ref_date))
    result = _pc_mo_staleness([ins])
    assert result == []


def test_pc_mo_staleness_no_date():
    ins = _mo()  # no data_referencia_preco
    result = _pc_mo_staleness([ins])
    assert result == []


# ===========================================================================
# 7. _pc_mo_zscore — outlier detection
# ===========================================================================


def test_pc_mo_zscore_extreme_outlier():
    # Need ≥15 items so outlier z > ZSCORE_EXTREMO (3.5); see _zscore_map
    # For n=15 the maximum achievable z ≈ 3.61 when outlier >> normal
    normal = [_mo(codigo=f"MO-{i:02d}", preco=1000.0) for i in range(14)]
    outlier = _mo(codigo="MO-OUT", preco=1_000_000_000.0)
    result = _pc_mo_zscore(normal + [outlier])
    codes = [a.codigo for a in result]
    assert "MO-OUT" in codes
    for a in result:
        assert a.severidade == "AVISO"
        assert a.tipo == "ESTATISTICO"


def test_pc_mo_zscore_uniform_prices():
    # All same price → z=0 → no anomalies
    items = [_mo(codigo=f"MO-{i}", preco=1500.0) for i in range(5)]
    result = _pc_mo_zscore(items)
    assert result == []


def test_pc_mo_zscore_single_item():
    # Only 1 item → _zscore_map returns {} → no anomalies
    result = _pc_mo_zscore([_mo()])
    assert result == []


# ===========================================================================
# 8. _check_mao_obra integration
# ===========================================================================


def test_check_mao_obra_empty():
    result = _check_mao_obra([])
    assert result == []


def test_check_mao_obra_no_mao_obra_type():
    ins = {"tipo": "MATERIAL", "codigo": "MAT-001", "preco_unitario": 500.0}
    result = _check_mao_obra([ins])
    assert result == []


def test_check_mao_obra_zero_price_excluded():
    ins = _mo(preco=0.0)
    result = _check_mao_obra([ins])
    assert result == []


def test_check_mao_obra_returns_anomalias_for_low_salary():
    ins = _mo(preco=_PRECO_MO_LOW, unidade="mes")
    result = _check_mao_obra([ins])
    # Should find at least the salario_minimo ERRO
    erros = [a for a in result if a.severidade == "ERRO" and a.tipo == "FISICO"]
    assert len(erros) >= 1


# ===========================================================================
# 9. _pc_eq_diesel
# ===========================================================================


def test_pc_eq_diesel_missing_consumo():
    eq = _eq(pot_cv=100.0)  # no consumo
    result = _pc_eq_diesel([eq])
    assert result == []


def test_pc_eq_diesel_missing_pot_cv():
    eq = _eq(consumo=10.0)  # no pot_cv
    result = _pc_eq_diesel([eq])
    assert result == []


def test_pc_eq_diesel_within_range():
    pot = 100.0
    # consumo at the pontual value → delta=0 → no anomaly
    consumo_ok = pot * DIESEL_L_POR_CV_PONT
    eq = _eq(consumo=consumo_ok, pot_cv=pot)
    result = _pc_eq_diesel([eq])
    assert result == []


def test_pc_eq_diesel_aviso_delta_moderate():
    # delta > DIESEL_TOLERANCIA but < 1.0 → AVISO
    pot = 100.0
    esperado = pot * DIESEL_L_POR_CV_PONT
    # 80% above expected → delta = 0.8 < 1.0 but > DIESEL_TOLERANCIA (0.5)
    consumo_high = esperado * 1.8
    eq = _eq(consumo=consumo_high, pot_cv=pot)
    result = _pc_eq_diesel([eq])
    assert len(result) == 1
    assert result[0].severidade == "AVISO"
    assert result[0].tipo == "FISICO"


def test_pc_eq_diesel_erro_delta_large():
    # delta >= 1.0 → ERRO
    pot = 100.0
    esperado = pot * DIESEL_L_POR_CV_PONT
    consumo_huge = esperado * 10.0  # delta >> 1.0
    eq = _eq(consumo=consumo_huge, pot_cv=pot)
    result = _pc_eq_diesel([eq])
    assert len(result) == 1
    assert result[0].severidade == "ERRO"


# ===========================================================================
# 10. _pc_eq_zscore
# ===========================================================================


def test_pc_eq_zscore_extreme_outlier():
    # Same minimum-n reasoning as mo_zscore: need 14 normal + 1 huge outlier
    normal = [_eq(codigo=f"EQ-{i:02d}", preco=100.0) for i in range(14)]
    outlier = _eq(codigo="EQ-OUT", preco=1_000_000_000.0)
    result = _pc_eq_zscore(normal + [outlier])
    codes = [a.codigo for a in result]
    assert "EQ-OUT" in codes


def test_pc_eq_zscore_uniform():
    items = [_eq(codigo=f"EQ-{i}", preco=200.0) for i in range(5)]
    result = _pc_eq_zscore(items)
    assert result == []


# ===========================================================================
# 11. _pc_eq_locacao
# ===========================================================================


def test_pc_eq_locacao_missing():
    eq = _eq()  # no locacao
    result = _pc_eq_locacao([eq])
    assert len(result) == 1
    a = result[0]
    assert a.tipo == "INCOMPLETO"
    assert a.severidade == "INFO"


def test_pc_eq_locacao_present():
    eq = _eq(locacao=5000.0)
    result = _pc_eq_locacao([eq])
    assert result == []


# ===========================================================================
# 12. _check_equipamento integration
# ===========================================================================


def test_check_equipamento_empty():
    result = _check_equipamento([])
    assert result == []


def test_check_equipamento_no_equipamento_type():
    ins = {"tipo": "MAO_OBRA", "codigo": "MO-001", "preco_unitario": 500.0}
    result = _check_equipamento([ins])
    assert result == []


def test_check_equipamento_zero_price_excluded():
    eq = _eq(preco=0.0)
    result = _check_equipamento([eq])
    assert result == []


def test_check_equipamento_produces_locacao_info():
    eq = _eq()  # missing locacao → INFO
    result = _check_equipamento([eq])
    tipos = [a.tipo for a in result]
    assert "INCOMPLETO" in tipos


# ===========================================================================
# 13. _pc_check_prod_item
# ===========================================================================


def test_pc_check_prod_item_zero_vh():
    prod = _prod(vh=0)
    result = _pc_check_prod_item(prod, {})
    assert len(result) == 1
    a = result[0]
    assert a.severidade == "ERRO"
    assert a.tipo == "INCOMPLETO"


def test_pc_check_prod_item_none_vh():
    prod = _prod(vh=None)
    result = _pc_check_prod_item(prod, {})
    assert len(result) == 1
    assert result[0].severidade == "ERRO"


def test_pc_check_prod_item_vh_above_max():
    prod = _prod(vh=VH_MAX + 1.0, funcoes=[{"funcao_id": "MO-001"}])
    insumo_index = {"MO-001": _mo()}
    result = _pc_check_prod_item(prod, insumo_index)
    avisos = [a for a in result if a.tipo == "FISICO" and a.severidade == "AVISO"]
    assert len(avisos) >= 1


def test_pc_check_prod_item_no_equipe():
    # Valid vh but no equipe → AVISO INCOMPLETO
    prod = _prod(vh=100.0)
    result = _pc_check_prod_item(prod, {})
    avisos = [a for a in result if a.tipo == "INCOMPLETO" and a.severidade == "AVISO"]
    assert len(avisos) >= 1


def test_pc_check_prod_item_missing_funcao_id_in_index():
    prod = _prod(vh=100.0, funcoes=[{"funcao_id": "MO-MISSING"}])
    result = _pc_check_prod_item(prod, {})
    erros = [a for a in result if a.tipo == "INCOMPLETO" and a.severidade == "ERRO"]
    assert len(erros) >= 1


def test_pc_check_prod_item_valid():
    # vh valid, funcao_id present in index, no VH_MAX issue
    prod = _prod(vh=100.0, funcoes=[{"funcao_id": "MO-001"}])
    insumo_index = {"MO-001": _mo()}
    result = _pc_check_prod_item(prod, insumo_index)
    # No ERRO expected; only possibly an AVISO if equipe is present
    erros = [a for a in result if a.severidade == "ERRO"]
    assert erros == []


# ===========================================================================
# 14. _pc_check_equipe_refs
# ===========================================================================


def test_pc_check_equipe_refs_funcao_missing():
    equipe = {"funcoes": [{"funcao_id": "MO-MISSING"}], "equipamentos": []}
    result = _pc_check_equipe_refs("PROD-001", equipe, {})
    assert len(result) == 1
    assert result[0].severidade == "ERRO"
    assert result[0].tipo == "INCOMPLETO"


def test_pc_check_equipe_refs_equip_missing():
    equipe = {"funcoes": [], "equipamentos": [{"equip_id": "EQ-MISSING"}]}
    result = _pc_check_equipe_refs("PROD-001", equipe, {})
    assert len(result) == 1
    assert result[0].severidade == "ERRO"


def test_pc_check_equipe_refs_all_present():
    insumo_index = {"MO-001": _mo(), "EQ-001": _eq()}
    equipe = {
        "funcoes": [{"funcao_id": "MO-001"}],
        "equipamentos": [{"equip_id": "EQ-001"}],
    }
    result = _pc_check_equipe_refs("PROD-001", equipe, insumo_index)
    assert result == []


def test_pc_check_equipe_refs_empty_equipe():
    result = _pc_check_equipe_refs("PROD-001", {}, {})
    assert result == []


# ===========================================================================
# 15. _pc_check_prod_zscore
# ===========================================================================


def test_pc_check_prod_zscore_fewer_than_3():
    prods = [_prod(codigo=f"P-{i}", vh=100.0) for i in range(2)]
    result = _pc_check_prod_zscore(prods)
    assert result == []


def test_pc_check_prod_zscore_extreme_outlier():
    # prod zscore uses ZSCORE_EXTREMO * 2 threshold; still need n≥15 for z>7
    # With 30 normal + 1 extreme outlier the z approaches sqrt(30) ≈ 5.47,
    # which is below ZSCORE_EXTREMO*2=7. Use a very large multiplier to ensure
    # the outlier stands out and we get well past the sqrt(n-1) limit.
    # At n=50 the max z ≈ sqrt(49)=7.0, exactly at threshold.
    # Use n=51 (50 normal + 1 outlier) to guarantee z > 7.
    normal = [_prod(codigo=f"P-{i:02d}", vh=10.0) for i in range(50)]
    outlier = _prod(codigo="P-OUT", vh=1_000_000_000.0)
    result = _pc_check_prod_zscore(normal + [outlier])
    codes = [a.codigo for a in result]
    assert "P-OUT" in codes
    for a in result:
        assert a.tipo == "ESTATISTICO"
        assert a.severidade == "INFO"


def test_pc_check_prod_zscore_uniform():
    prods = [_prod(codigo=f"P-{i}", vh=100.0) for i in range(5)]
    result = _pc_check_prod_zscore(prods)
    assert result == []


# ===========================================================================
# 16. _pc_prod_vhs
# ===========================================================================


def test_pc_prod_vhs_filters_zero_and_none():
    prods = [
        _prod(codigo="P1", vh=100.0),
        _prod(codigo="P2", vh=0.0),
        _prod(codigo="P3", vh=None),
    ]
    result = _pc_prod_vhs(prods)
    assert len(result) == 1
    assert result[0][0] == "P1"


# ===========================================================================
# 17. _check_produtividades
# ===========================================================================


def test_check_produtividades_empty():
    result = _check_produtividades([], {})
    assert result == []


def test_check_produtividades_with_valid_prod():
    insumo_index = {"MO-001": _mo()}
    prod = _prod(vh=100.0, funcoes=[{"funcao_id": "MO-001"}])
    result = _check_produtividades([prod], insumo_index)
    # No errors expected
    erros = [a for a in result if a.severidade == "ERRO"]
    assert erros == []


def test_check_produtividades_with_bad_prod():
    prod = _prod(vh=0.0)
    result = _check_produtividades([prod], {})
    erros = [a for a in result if a.severidade == "ERRO"]
    assert len(erros) >= 1


# ===========================================================================
# 18. _count_severidades
# ===========================================================================


def test_count_severidades_empty():
    erros, avisos, infos = _count_severidades([])
    assert erros == avisos == infos == 0


def test_count_severidades_mixed():
    anomalias = [
        Anomalia("A", "T", "ERRO", "msg"),
        Anomalia("B", "T", "ERRO", "msg"),
        Anomalia("C", "T", "AVISO", "msg"),
        Anomalia("D", "T", "INFO", "msg"),
        Anomalia("E", "T", "INFO", "msg"),
        Anomalia("F", "T", "INFO", "msg"),
    ]
    erros, avisos, infos = _count_severidades(anomalias)
    assert erros == 2
    assert avisos == 1
    assert infos == 3


def test_count_severidades_unknown_severity():
    # Unknown severidade should not be counted
    anomalias = [Anomalia("A", "T", "DESCONHECIDO", "msg")]
    erros, avisos, infos = _count_severidades(anomalias)
    assert erros == avisos == infos == 0


# ===========================================================================
# 19. Anomalia.to_dict
# ===========================================================================


def test_anomalia_to_dict():
    a = Anomalia(
        codigo="X-001",
        tipo="FISICO",
        severidade="ERRO",
        mensagem="Alguma coisa errada",
        detalhe={"key": "value"},
    )
    d = a.to_dict()
    assert d["codigo"] == "X-001"
    assert d["tipo"] == "FISICO"
    assert d["severidade"] == "ERRO"
    assert d["mensagem"] == "Alguma coisa errada"
    assert d["detalhe"] == {"key": "value"}


# ===========================================================================
# 20. verificar_plausibilidade — integration with errors
# ===========================================================================


def test_verificar_plausibilidade_ok_false_on_erro():
    # An MO item with price below minimum wage → ERRO → ok=False
    ins = _mo(preco=_PRECO_MO_LOW, unidade="mes")
    result = verificar_plausibilidade([ins], [])
    assert result["ok"] is False
    assert result["resumo"]["erros"] >= 1


def test_verificar_plausibilidade_por_tipo_grouping():
    # Force a FISICO ERRO and check por_tipo
    ins = _mo(preco=_PRECO_MO_LOW, unidade="mes")
    result = verificar_plausibilidade([ins], [])
    assert "FISICO" in result["por_tipo"]
    for item in result["por_tipo"]["FISICO"]:
        assert "codigo" in item
        assert "severidade" in item


def test_verificar_plausibilidade_anomalias_list_populated():
    ins = _mo(preco=_PRECO_MO_LOW, unidade="mes")
    result = verificar_plausibilidade([ins], [])
    assert len(result["anomalias"]) >= 1
    for a in result["anomalias"]:
        assert "codigo" in a
        assert "tipo" in a
        assert "severidade" in a
        assert "mensagem" in a


def test_verificar_plausibilidade_counts_match_anomalias():
    ins = _mo(preco=_PRECO_MO_LOW, unidade="mes")
    result = verificar_plausibilidade([ins], [])
    resumo = result["resumo"]
    total = resumo["erros"] + resumo["avisos"] + resumo["infos"]
    assert total == resumo["anomalias_total"]
    assert resumo["anomalias_total"] == len(result["anomalias"])


def test_verificar_plausibilidade_with_cpus_param():
    # cpus param is accepted but not processed currently
    result = verificar_plausibilidade([], [], cpus=[{"id": "CPU-001"}])
    assert result["ok"] is True


def test_verificar_plausibilidade_insumo_index_uses_codigo():
    # Verify that insumo_index is built from 'codigo' field
    mo_ins = _mo(codigo="MO-001")
    prod = _prod(vh=100.0, funcoes=[{"funcao_id": "MO-001"}])
    result = verificar_plausibilidade([mo_ins], [prod])
    # MO-001 is in index, so no INCOMPLETO ERRO for funcao_id
    incompleto_erros = [
        a
        for a in result["anomalias"]
        if a["tipo"] == "INCOMPLETO" and a["severidade"] == "ERRO" and "funcao_id" in a.get("detalhe", {})
    ]
    assert incompleto_erros == []


def test_verificar_plausibilidade_resumo_counts():
    mo = _mo(preco=_PRECO_MO_OK, unidade="mes")
    prod = _prod(vh=100.0, funcoes=[{"funcao_id": "MO-001"}])
    result = verificar_plausibilidade([mo], [prod])
    assert result["resumo"]["total_insumos"] == 1
    assert result["resumo"]["total_producoes"] == 1


# ===========================================================================
# 21. Mixed scenario — equipamento + mao_obra + producoes
# ===========================================================================


def test_verificar_plausibilidade_mixed():
    mo_good = _mo(codigo="MO-GOOD", preco=_PRECO_MO_OK, unidade="mes")
    mo_bad = _mo(codigo="MO-BAD", preco=_PRECO_MO_LOW, unidade="mes")
    eq_no_locacao = _eq(codigo="EQ-001")
    prod_no_vh = _prod(codigo="PROD-NO-VH", vh=0.0)

    result = verificar_plausibilidade(
        [mo_good, mo_bad, eq_no_locacao],
        [prod_no_vh],
    )

    # mo_bad → ERRO FISICO; prod_no_vh → ERRO INCOMPLETO
    assert result["ok"] is False
    assert result["resumo"]["erros"] >= 2
    # eq_no_locacao → INFO INCOMPLETO
    assert result["resumo"]["infos"] >= 1


# ===========================================================================
# 22. _pc_mo_staleness patch via unittest.mock.patch
# ===========================================================================


def test_pc_mo_staleness_with_patch():
    ref_date = "2023-01-01"
    fixed_today = date(2023, 7, 30)  # 210 days after 2023-01-01 → stale
    with patch(_TODAY_PATH, return_value=fixed_today):
        ins = _mo(data_ref=ref_date)
        result = _pc_mo_staleness([ins])
    assert len(result) == 1
    assert result[0].tipo == "STALE"
    assert result[0].detalhe["dias_atraso"] > VALIDADE_PRECO_DIAS


# _plausibility_checks.py line 210: p <= 0 → continue in _pc_eq_diesel
# ---------------------------------------------------------------------------


class TestPcEqDieselZeroPotencia:
    def test_continues_when_potencia_cv_is_zero(self):
        """Line 210: p=0 → p <= 0 → continue (skipped, no anomalia added)."""
        from concilium.application.catalog._plausibility_checks import _pc_eq_diesel

        equipamentos = [
            {
                "codigo": "EQ-TRATOR-01",
                "atributos_especificos": {
                    "consumo_litros_hora": 5.0,
                    "potencia_cv": 0.0,  # p=0 → continue
                },
            }
        ]
        result = _pc_eq_diesel(equipamentos)
        assert result == []  # no anomalia, skipped

    def test_continues_when_potencia_cv_is_negative(self):
        """Line 210: p < 0 → p <= 0 → continue."""
        from concilium.application.catalog._plausibility_checks import _pc_eq_diesel

        equipamentos = [
            {
                "codigo": "EQ-INVALID",
                "atributos_especificos": {
                    "consumo_litros_hora": 5.0,
                    "potencia_cv": -10.0,  # negative → continue
                },
            }
        ]
        result = _pc_eq_diesel(equipamentos)
        assert result == []

