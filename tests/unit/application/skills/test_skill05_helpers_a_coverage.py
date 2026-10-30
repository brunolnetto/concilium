"""Coverage tests for pure helper functions in _skill_helpers_a.py (skill 05).

Covers missing lines: 47-48, 102, 109, 114-115, 138, 159, 169-172, 177-178,
183, 218-221, 241-242, 287, 308, 353-354, 362, 375, 380, 493, 541, 589-594,
598-603, 615-624, 655, 658, 661, 737, 796-802, 805-806, 809-811, 814-816,
819-822, 824, 990-991, 993-996, 1037, 1079, 1082, 1104, 1111, 1120, 1416,
1451-1452, 1456, 1459, 1486, 1496, 1498-1499, 1550, 1570, 1574, 1577, 1653,
1730, 1744, 1761, 1858, 1865, 1882, 1967-1969, 1972-1978, 2002-2003, 2006-2009,
2011, 2013-2016, 2019, 2022-2025, 2028-2029, 2031, 2034, 2039, 2045, 2064,
2255, 2260, 2277, 2434, 2583, 2586, 2688, 2770, 2787, 2879, 2899-2905, 2907,
2918, 2938-2943, 2948-2953, 2958-2962, 2993, 3006, 3008-3010
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module loading via proper import (enables coverage tracking)
# ---------------------------------------------------------------------------
import concilium.application.skills as _skills_pkg

_ = _skills_pkg.run_equipes_e_alocacao  # trigger lazy load so _skill_helpers lands in sys.modules

_MOD = sys.modules["_concilium_skillpkg_05_equipes_e_alocacao._skill_helpers"]

# Pull names we want to test
_getfloat_d = _MOD._getfloat_d
_getlist_d = _MOD._getlist_d
_comp_is_empty = _MOD._comp_is_empty
_cpu_comp_is_valid = _MOD._cpu_comp_is_valid
_fallback_cpu_comp = _MOD._fallback_cpu_comp
_resolve_salario = _MOD._resolve_salario
_resolve_encargo_funcao = _MOD._resolve_encargo_funcao
_resolve_custo_unit_funcao = _MOD._resolve_custo_unit_funcao
_calcular_custo_funcao = _MOD._calcular_custo_funcao
_consumo_from_decomposicao = _MOD._consumo_from_decomposicao
_to_positive_float_or_none = _MOD._to_positive_float_or_none
_normalize_text_key = _MOD._normalize_text_key
_resolve_consumo_equip = _MOD._resolve_consumo_equip
_converter_preco_equip = _MOD._converter_preco_equip
_converter_preco_equip_fallback = _MOD._converter_preco_equip_fallback
_validar_comp_vazia = _MOD._validar_comp_vazia
_promote_materiais_from_cpu = _MOD._promote_materiais_from_cpu
_build_comb_validacao = _MOD._build_comb_validacao
_mat_fonte1 = _MOD._mat_fonte1
_mat_fonte2_item = _MOD._mat_fonte2_item
_calc_custo_material_item = _MOD._calc_custo_material_item
_count_transitions = _MOD._count_transitions
_accum_mob_costs_list = _MOD._accum_mob_costs_list
_calc_custo_mob_desmob = _MOD._calc_custo_mob_desmob
_sum_eq_weeks_and_cron_cost = _MOD._sum_eq_weeks_and_cron_cost
_comb_efetivo_mensal = _MOD._comb_efetivo_mensal
_custo_ocioso_eq = _MOD._custo_ocioso_eq
_week_idx = _MOD._week_idx
_eq_comp_floats = _MOD._eq_comp_floats
_accum_week_demand = _MOD._accum_week_demand
_get_active_weeks = _MOD._get_active_weeks
_resolve_prod_lookup = _MOD._resolve_prod_lookup
_process_item_tipo_map = _MOD._process_item_tipo_map
_build_resumo_e_validacoes = _MOD._build_resumo_e_validacoes
_build_perpetuation_chains = _MOD._build_perpetuation_chains
_build_predecessor_map = _MOD._build_predecessor_map
_init_item_float_maps = _MOD._init_item_float_maps
_compute_ocioso_para_item = _MOD._compute_ocioso_para_item
_compute_particao_por_tipo = _MOD._compute_particao_por_tipo
_compress_to_segments = _MOD._compress_to_segments
_compute_desmob_antecipada = _MOD._compute_desmob_antecipada
_build_demand_per_week = _MOD._build_demand_per_week
_item_demand_for_tipo = _MOD._item_demand_for_tipo
_collect_items_data_for_tipo = _MOD._collect_items_data_for_tipo
_build_item_resource_maps = _MOD._build_item_resource_maps
_sum_inst_categories = _MOD._sum_inst_categories
_last_week_idx_for_act = _MOD._last_week_idx_for_act
_first_week_idx_for_act = _MOD._first_week_idx_for_act
_compute_gap_for_inst = _MOD._compute_gap_for_inst
_processar_equipamentos_item = _MOD._processar_equipamentos_item
_derive_rcpsp_from_canonical = _MOD._derive_rcpsp_from_canonical


# ---------------------------------------------------------------------------
# Helpers for making fake canonical objects
# ---------------------------------------------------------------------------


def _make_seg(activity_id, semana_inicio, semana_fim, machine_weeks=1):
    from concilium.domain.models.canonical import SegmentoAtividade

    return SegmentoAtividade(
        activity_id=activity_id,
        semana_inicio=semana_inicio,
        semana_fim=semana_fim,
        machine_weeks=machine_weeks,
    )


def _make_validacao_item(**kwargs):
    from concilium.domain.models.canonical import ValidacaoItem

    return ValidacaoItem(**kwargs)


def _make_cadeia(**kwargs):
    from concilium.domain.models.canonical import CadeiaPerpetuacao

    defaults = dict(
        cadeia_id="cadeia-test-1",
        tipo_id="TIPO-A",
        item_ids=["A"],
        semana_inicio="S001",
        semana_fim="S004",
        semanas_ativas=4,
        semanas_ociosas=0,
        n_mobilizacoes=1,
        n_desmobilizacoes=1,
        custo_standby=0.0,
        machine_weeks_ativas=4,
        delta_aplicado_semanas=2,
    )
    defaults.update(kwargs)
    return CadeiaPerpetuacao(**defaults)


# ===========================================================================
# 1. _getfloat_d
# ===========================================================================


class TestGetfloatD:
    def test_existing_numeric_key(self):
        assert _getfloat_d({"a": 3.5}, "a") == pytest.approx(3.5)

    def test_missing_key_returns_zero(self):
        assert _getfloat_d({}, "x") == 0.0

    def test_none_value_returns_zero(self):
        assert _getfloat_d({"a": None}, "a") == 0.0

    def test_falsy_zero_value(self):
        assert _getfloat_d({"a": 0}, "a") == 0.0

    def test_string_number(self):
        assert _getfloat_d({"a": "2.5"}, "a") == pytest.approx(2.5)

    def test_integer_value(self):
        assert _getfloat_d({"a": 7}, "a") == pytest.approx(7.0)


# ===========================================================================
# 2. _getlist_d
# ===========================================================================


class TestGetlistD:
    def test_existing_list(self):
        assert _getlist_d({"items": [1, 2]}, "items") == [1, 2]

    def test_missing_key_returns_empty_list(self):
        assert _getlist_d({}, "items") == []

    def test_none_value_returns_empty_list(self):
        assert _getlist_d({"items": None}, "items") == []

    def test_empty_list_returns_empty_list(self):
        assert _getlist_d({"items": []}, "items") == []


# ===========================================================================
# 3. _comp_is_empty
# ===========================================================================


class TestCompIsEmpty:
    def test_empty_comp(self):
        assert _comp_is_empty({}) is True

    def test_comp_with_funcoes(self):
        assert _comp_is_empty({"funcoes": [{"funcao_id": "ENG"}]}) is False

    def test_comp_with_equipamentos(self):
        assert _comp_is_empty({"equipamentos": [{"equip_id": "EQ1"}]}) is False

    def test_comp_with_none_funcoes(self):
        assert _comp_is_empty({"funcoes": None}) is True

    def test_comp_with_empty_funcoes_list(self):
        assert _comp_is_empty({"funcoes": []}) is True


# ===========================================================================
# 4. _cpu_comp_is_valid
# ===========================================================================


class TestCpuCompIsValid:
    def test_none_is_invalid(self):
        assert _cpu_comp_is_valid(None) is False

    def test_empty_dict_is_invalid(self):
        assert _cpu_comp_is_valid({}) is False

    def test_dict_with_funcoes_is_valid(self):
        assert _cpu_comp_is_valid({"funcoes": [{"funcao_id": "ENG"}]}) is True

    def test_dict_with_equipamentos_is_valid(self):
        assert _cpu_comp_is_valid({"equipamentos": [{"equip_id": "EQ1"}]}) is True

    def test_dict_with_no_funcoes_no_equipamentos_is_invalid(self):
        assert _cpu_comp_is_valid({"foo": "bar"}) is False

    def test_non_dict_is_invalid(self):
        assert _cpu_comp_is_valid("not a dict") is False

    def test_empty_funcoes_list(self):
        assert _cpu_comp_is_valid({"funcoes": [], "equipamentos": []}) is False


# ===========================================================================
# 5. _fallback_cpu_comp
# ===========================================================================


class TestFallbackCpuComp:
    def test_empty_comp_valid_cpu_comp_uses_cpu_comp(self):
        """Line 102: comp = cpu_comp when cpu_comp is valid."""
        cpu_comp = {"funcoes": [{"funcao_id": "ENG", "num_pessoas": 1}]}
        cpu = {"codigo": "CPU-01", "composicao_padrao_equipe": cpu_comp}
        validacoes = []
        result = _fallback_cpu_comp({}, cpu, "PROD-001", validacoes)
        assert result == cpu_comp
        assert len(validacoes) == 1
        assert validacoes[0].codigo == "VAL-EQUIP-LEGADO-053"

    def test_empty_comp_invalid_cpu_comp_returns_empty_dict(self):
        """No valid cpu_comp → returns {} (line 102 branch not taken)."""
        cpu = {"codigo": "CPU-01", "composicao_padrao_equipe": {}}
        validacoes = []
        result = _fallback_cpu_comp({}, cpu, None, validacoes)
        assert result == {}
        assert len(validacoes) == 0

    def test_valid_comp_unchanged(self):
        """Comp already valid → returned unchanged, no fallback."""
        comp = {"funcoes": [{"funcao_id": "MESTRE", "num_pessoas": 1}]}
        cpu = {"codigo": "CPU-02", "composicao_padrao_equipe": {"funcoes": [{"funcao_id": "OUTRO"}]}}
        validacoes = []
        result = _fallback_cpu_comp(comp, cpu, None, validacoes)
        assert result == comp
        assert len(validacoes) == 0

    def test_none_comp_without_cpu_comp_returns_empty_dict(self):
        """Line 101-102: if not isinstance(comp, dict) → comp = {}."""
        cpu = {"codigo": "CPU-03"}
        validacoes = []
        result = _fallback_cpu_comp(None, cpu, None, validacoes)
        assert result == {}

    def test_missing_cpu_comp_returns_empty_dict(self):
        """cpu has no composicao_padrao_equipe → returns {}."""
        cpu = {"codigo": "CPU-04"}
        validacoes = []
        result = _fallback_cpu_comp({}, cpu, None, validacoes)
        assert result == {}


# ===========================================================================
# 6. _resolve_salario
# ===========================================================================


class TestResolveSalario:
    def test_override_wins(self):
        """Line 109: salario_override is not None → return float(salario_override)."""
        result = _resolve_salario(999.0, "h", 1234.56)
        assert result == pytest.approx(1234.56)

    def test_override_zero_is_used(self):
        """Zero override still overrides."""
        result = _resolve_salario(999.0, "h", 0.0)
        assert result == 0.0

    def test_no_override_converts_from_mes(self):
        """For unidade='mes', ConversorUnidades should return preco directly."""
        result = _resolve_salario(5000.0, "mes", None)
        assert result == pytest.approx(5000.0)

    def test_exception_returns_preco(self):
        """Lines 114-115: exception in converter → return preco."""
        with patch(
            "concilium.domain.services.conversor_unidades.ConversorUnidades.converter_preco",
            side_effect=ValueError("bad unit"),
        ):
            result = _resolve_salario(3000.0, "INVALID_UNIT", None)
        assert result == pytest.approx(3000.0)


# ===========================================================================
# 7. _resolve_custo_unit_funcao
# ===========================================================================


class TestResolveCustoUnitFuncao:
    def test_pj_returns_salario(self):
        """PJ category: cost = salario (no encargos)."""
        result = _resolve_custo_unit_funcao("pj_normal", 5000.0, {}, 0.70, 0.0)
        assert result == pytest.approx(5000.0)

    def test_custo_com_encargos_legado_e_ignorado(self):
        """ADR-182: campo legado `custo_com_encargos` (removido do catálogo pela
        ADR-009, 0 uso confirmado em qualquer catálogo) não é mais lido — cai
        no cálculo padrão."""
        atrib = {"custo_com_encargos": 4000.0}
        result = _resolve_custo_unit_funcao("clt", 3000.0, atrib, 0.70, 0.10)
        assert result == pytest.approx(3000.0 * 1.70 * 1.10)

    def test_metodo_custo_total_ja_incluido(self):
        """ADR-182 D1: metodo_custo_total (campo estruturado) → salario × (1+he_pct)."""
        atrib = {"metodo_custo_total": "custo_total_ja_incluido"}
        result = _resolve_custo_unit_funcao("clt", 100.0, atrib, 0.70, 0.05)
        assert result == pytest.approx(100.0 * 1.05)

    def test_texto_livre_nota_nao_e_mais_reconhecido(self):
        """ADR-182: o texto livre "inclui encargos" sozinho não basta mais —
        substituído por `metodo_custo_total`. Sem o campo, cai no cálculo padrão."""
        atrib = {"nota": "taxa horaria — inclui encargos e beneficios"}
        result = _resolve_custo_unit_funcao("clt", 100.0, atrib, 0.70, 0.05)
        assert result == pytest.approx(100.0 * 1.70 * 1.05)

    def test_texto_livre_nota_encargos_nao_e_mais_reconhecido(self):
        atrib = {"nota_encargos": "valor inclui encargos"}
        result = _resolve_custo_unit_funcao("clt", 100.0, atrib, 0.70, 0.0)
        assert result == pytest.approx(100.0 * 1.70)

    def test_regressao_bug_horista_ce_ja_all_in(self):
        """ADR-182 P1: reproduz o bug original (MO-ENCARREGADO-DE-FRENT e afins) —
        horista_CE + metodo_custo_total + horas_extras_pct_padrao não deve mais
        sofrer dupla contagem de encargo (custo × 3,47 em vez de custo × 1,25)."""
        atrib = {
            "categoria_sindical": "horista_CE",
            "metodo_custo_total": "custo_total_ja_incluido",
            "horas_extras_pct_padrao": 0.25,
        }
        result = _resolve_custo_unit_funcao("horista_ce", 7500.0, atrib, 1.777, 0.25)
        assert result == pytest.approx(7500.0 * 1.25)

    def test_standard_clt(self):
        """Normal CLT: salario × (1+enc) × (1+he)."""
        result = _resolve_custo_unit_funcao("clt", 1000.0, {}, 0.70, 0.10)
        assert result == pytest.approx(1000.0 * 1.70 * 1.10)

    def test_pj_prefix_match(self):
        """'pj_' prefix but not 'pj' alone still returns salario."""
        result = _resolve_custo_unit_funcao("pj_terceirizado", 2000.0, {}, 0.70, 0.0)
        assert result == pytest.approx(2000.0)


# ===========================================================================
# 8. _calcular_custo_funcao
# ===========================================================================


class TestCalcularCustoFuncao:
    def _make_insumo(self, preco=5000.0, unidade="mes", atributos=None):
        return {
            "preco_unitario": preco,
            "unidade": unidade,
            "atributos_especificos": atributos or {},
        }

    def test_custo_unitario_override(self):
        """Line 159: custo_unitario_override is not None → return (sal, he, round(override))."""
        insumo = self._make_insumo()
        sal, he, unit = _calcular_custo_funcao(insumo, 1, 0.70, None, 0.60, custo_unitario_override=9999.99)
        assert unit == pytest.approx(9999.99)
        assert sal == pytest.approx(5000.0)

    def test_standard_calc(self):
        insumo = self._make_insumo(preco=4000.0)
        sal, he, unit = _calcular_custo_funcao(insumo, 2, 0.70, None, 0.60)
        assert sal == pytest.approx(4000.0)
        assert he == pytest.approx(0.0)
        assert unit > 0

    def test_he_override_used(self):
        insumo = self._make_insumo()
        sal, he, unit = _calcular_custo_funcao(insumo, 1, 0.70, 0.15, 0.60)
        assert he == pytest.approx(0.15)


# ===========================================================================
# 9. _consumo_from_decomposicao
# ===========================================================================


class TestConsumoFromDecomposicao:
    def test_positive_diesel_and_price(self):
        """Lines 218-220: derives consumo = custo_diesel_h / preco_diesel."""
        decomp = {"custo_diesel_h": 30.0}
        result = _consumo_from_decomposicao(decomp, 6.0)
        assert result == pytest.approx(5.0)

    def test_zero_diesel_cost(self):
        """Line 221: custo_diesel_h == 0 → returns 0."""
        result = _consumo_from_decomposicao({"custo_diesel_h": 0.0}, 6.0)
        assert result == 0.0

    def test_zero_preco_diesel(self):
        """preco_diesel == 0 → no division, returns 0."""
        result = _consumo_from_decomposicao({"custo_diesel_h": 30.0}, 0.0)
        assert result == 0.0

    def test_missing_custo_diesel(self):
        result = _consumo_from_decomposicao({}, 6.0)
        assert result == 0.0

    def test_none_custo_diesel(self):
        result = _consumo_from_decomposicao({"custo_diesel_h": None}, 6.0)
        assert result == 0.0


# ===========================================================================
# 10. _to_positive_float_or_none
# ===========================================================================


class TestToPositiveFloatOrNone:
    def test_positive_value(self):
        assert _to_positive_float_or_none(5.0) == pytest.approx(5.0)

    def test_zero_returns_none(self):
        assert _to_positive_float_or_none(0.0) is None

    def test_negative_returns_none(self):
        assert _to_positive_float_or_none(-1.0) is None

    def test_none_returns_none(self):
        assert _to_positive_float_or_none(None) is None

    def test_string_number(self):
        assert _to_positive_float_or_none("3.5") == pytest.approx(3.5)

    def test_invalid_string_returns_none(self):
        assert _to_positive_float_or_none("abc") is None

    def test_integer(self):
        assert _to_positive_float_or_none(7) == pytest.approx(7.0)


# ===========================================================================
# 11. _normalize_text_key
# ===========================================================================


class TestNormalizeTextKey:
    def test_basic_ascii(self):
        assert _normalize_text_key("hello world") == "hello world"

    def test_accents_removed(self):
        result = _normalize_text_key("Açúcar")
        assert "acucar" in result.lower() or result == "acucar"

    def test_lowercase(self):
        assert _normalize_text_key("UPPER") == "upper"

    def test_special_chars_become_spaces(self):
        result = _normalize_text_key("hello-world_foo")
        assert "hello" in result
        assert "world" in result

    def test_extra_spaces_collapsed(self):
        result = _normalize_text_key("  hello   world  ")
        assert result == "hello world"

    def test_empty_string(self):
        assert _normalize_text_key("") == ""

    def test_none_like_empty(self):
        # mod passes str(txt or "") so None-like gives ""
        result = _normalize_text_key(None)
        assert result == ""


# ===========================================================================
# 12. _resolve_consumo_equip
# ===========================================================================


class TestResolveConsumoEquip:
    def test_proj_override_wins(self):
        """Lines 279-281: proj override → VAL-EQUIP-COMB-01."""
        atrib = {"consumo_litros_hora": 5.0}
        consumo, code = _resolve_consumo_equip(atrib, 3.0, None, 6.0)
        assert consumo == pytest.approx(3.0)
        assert code == "VAL-EQUIP-COMB-01"

    def test_cpu_override_second(self):
        """Lines 282-283: cpu override (positive) → VAL-EQUIP-COMB-01."""
        atrib = {}
        consumo, code = _resolve_consumo_equip(atrib, None, 4.0, 6.0)
        assert consumo == pytest.approx(4.0)
        assert code == "VAL-EQUIP-COMB-01"

    def test_insumo_consumo_used(self):
        """Lines 284-285: falls back to atrib.consumo_litros_hora → VAL-EQUIP-COMB-02."""
        atrib = {"consumo_litros_hora": 2.5}
        consumo, code = _resolve_consumo_equip(atrib, None, None, 6.0)
        assert consumo == pytest.approx(2.5)
        assert code == "VAL-EQUIP-COMB-02"

    def test_decomposicao_fallback(self):
        """Line 287: decomposicao → VAL-EQUIP-COMB-04."""
        atrib = {"decomposicao_equip": {"custo_diesel_h": 12.0}}
        consumo, code = _resolve_consumo_equip(atrib, None, None, 6.0)
        assert consumo == pytest.approx(2.0)
        assert code == "VAL-EQUIP-COMB-04"

    def test_no_combustivel_data(self):
        """Lines 288: no data → 0.0, VAL-EQUIP-COMB-03."""
        atrib = {}
        consumo, code = _resolve_consumo_equip(atrib, None, None, 6.0)
        assert consumo == 0.0
        assert code == "VAL-EQUIP-COMB-03"

    def test_proj_override_zero_explicit(self):
        """Zero is a valid explicit override (not treated as missing)."""
        atrib = {"consumo_litros_hora": 5.0}
        consumo, code = _resolve_consumo_equip(atrib, 0.0, None, 6.0)
        assert consumo == 0.0
        assert code == "VAL-EQUIP-COMB-01"


# ===========================================================================
# 13. _converter_preco_equip_fallback
# ===========================================================================


class TestConverterPrecoEquipFallback:
    def _fake_conversor(self, raises=False):

        if raises:
            mock = MagicMock(side_effect=Exception("bad unit"))
        else:
            mock = MagicMock(return_value=100.0)
        return mock

    def test_success_path(self):
        """Lines 168: normal conversion works."""
        insumo = {"codigo": "EQ1", "unidade": "h"}
        with patch(
            "concilium.domain.services.conversor_unidades.ConversorUnidades.converter_preco",
            return_value=800.0,
        ):
            result = _converter_preco_equip_fallback(
                insumo,
                10.0,
                176.0,
                __import__(
                    "concilium.domain.services.conversor_unidades", fromlist=["ConversorUnidades"]
                ).ConversorUnidades,
                MagicMock(),
            )
        assert result == pytest.approx(800.0)

    def test_fallback_h_unit(self):
        """Lines 169-177: conversion fails for h → fallback = preco × horas_mes."""
        from concilium.domain.services.conversor_unidades import ConversorUnidades

        insumo = {"codigo": "EQ2", "unidade": "h"}
        logger = MagicMock()

        with patch.object(ConversorUnidades, "converter_preco", side_effect=Exception("conv error")):
            result = _converter_preco_equip_fallback(insumo, 5.0, 176.0, ConversorUnidades, logger)

        assert result == pytest.approx(5.0 * 176.0)
        logger.warning.assert_called_once()

    def test_fallback_non_h_unit(self):
        """Lines 178-183: non-h unit, conv fails → return raw preco."""
        from concilium.domain.services.conversor_unidades import ConversorUnidades

        insumo = {"codigo": "EQ3", "unidade": "semana"}
        logger = MagicMock()

        with patch.object(ConversorUnidades, "converter_preco", side_effect=Exception("bad")):
            result = _converter_preco_equip_fallback(insumo, 300.0, 176.0, ConversorUnidades, logger)

        assert result == pytest.approx(300.0)
        logger.error.assert_called_once()


# ===========================================================================
# 14. _converter_preco_equip
# ===========================================================================


class TestConverterPrecoEquip:
    def test_rental_unit_dia_calendario(self):
        insumo = {
            "preco_unitario": 100.0,
            "atributos_especificos": {"rental_unit": "dia_calendario"},
        }
        result = _converter_preco_equip(insumo, 8.0, 20.0)
        assert result == pytest.approx(100.0 * 20.0)

    def test_rental_unit_mes(self):
        insumo = {
            "preco_unitario": 5000.0,
            "atributos_especificos": {"rental_unit": "mes"},
        }
        result = _converter_preco_equip(insumo, 8.0, 22.0)
        assert result == pytest.approx(5000.0)

    def test_rental_unit_hora_produtiva(self):
        insumo = {
            "preco_unitario": 10.0,
            "atributos_especificos": {"rental_unit": "hora_produtiva"},
        }
        result = _converter_preco_equip(insumo, 8.0, 22.0)
        assert result == pytest.approx(10.0 * 8.0 * 22.0)

    def test_no_rental_unit_calls_fallback(self):
        """No rental_unit → calls ConversorUnidades fallback path."""
        insumo = {
            "preco_unitario": 50.0,
            "unidade": "mes",
            "atributos_especificos": {},
        }
        # 'mes' should convert cleanly
        result = _converter_preco_equip(insumo, 8.0, 22.0)
        assert result > 0


# ===========================================================================
# 15. _validar_comp_vazia
# ===========================================================================


class TestValidarCompVazia:
    def test_empty_comp_with_prod_id_ref(self):
        """Lines 353-360: adds VAL-EQUIP-DADOS-01."""
        validacoes = []
        _validar_comp_vazia({}, {"codigo": "CPU-01"}, "PROD-001", validacoes)
        assert len(validacoes) == 1
        assert validacoes[0].codigo == "VAL-EQUIP-DADOS-01"

    def test_empty_comp_without_prod_id_ref(self):
        """Lines 362-368: adds VAL-EQUIP-DADOS-02."""
        validacoes = []
        _validar_comp_vazia({}, {"codigo": "CPU-01"}, None, validacoes)
        assert len(validacoes) == 1
        assert validacoes[0].codigo == "VAL-EQUIP-DADOS-02"

    def test_non_empty_comp_no_validation(self):
        """No validation added when comp is valid."""
        validacoes = []
        _validar_comp_vazia(
            {"funcoes": [{"funcao_id": "ENG"}]},
            {"codigo": "CPU-01"},
            None,
            validacoes,
        )
        assert len(validacoes) == 0


# ===========================================================================
# 16. _promote_materiais_from_cpu
# ===========================================================================


class TestPromoveMateriaisDoCpu:
    def test_promotes_material_items(self):
        """Line 375: material items added to comp."""
        comp = {"funcoes": []}
        cpu = {
            "composicao_itens": [
                {"categoria_custo": "MATERIAL", "insumo_id": "MAT-001", "coeficiente": 2.0},
                {"categoria_custo": "MO", "insumo_id": "FN-001", "coeficiente": 1.0},
            ]
        }
        result = _promote_materiais_from_cpu(comp, cpu)
        assert "materiais" in result
        assert len(result["materiais"]) == 1
        assert result["materiais"][0]["insumo_id"] == "MAT-001"

    def test_no_material_items(self):
        """Line 380: no MATERIAL items → comp returned unchanged."""
        comp = {"funcoes": []}
        cpu = {"composicao_itens": [{"categoria_custo": "MO", "insumo_id": "FN-001"}]}
        result = _promote_materiais_from_cpu(comp, cpu)
        assert "materiais" not in result

    def test_empty_cpu(self):
        comp = {}
        result = _promote_materiais_from_cpu(comp, {})
        assert result == {}

    def test_item_without_insumo_id_skipped(self):
        comp = {}
        cpu = {"composicao_itens": [{"categoria_custo": "MATERIAL"}]}
        result = _promote_materiais_from_cpu(comp, cpu)
        assert result == {}

    def test_non_dict_item_skipped(self):
        """Line 386: non-dict entries in composicao_itens are skipped."""
        comp = {}
        cpu = {"composicao_itens": ["not-a-dict", {"categoria_custo": "MATERIAL", "insumo_id": "MAT-002"}]}
        result = _promote_materiais_from_cpu(comp, cpu)
        assert result["materiais"][0]["insumo_id"] == "MAT-002"


# ===========================================================================
# 17. _build_comb_validacao
# ===========================================================================


class TestBuildCombValidacao:
    def test_comb_03_is_aviso(self):
        """Line 493: VAL-EQUIP-COMB-03 → status=AVISO."""
        val = _build_comb_validacao("EQ-001", "VAL-EQUIP-COMB-03")
        assert val.codigo == "VAL-EQUIP-COMB-03"
        assert val.status == "AVISO"

    def test_comb_04_is_ok(self):
        val = _build_comb_validacao("EQ-001", "VAL-EQUIP-COMB-04")
        assert val.codigo == "VAL-EQUIP-COMB-04"
        assert val.status == "OK"

    def test_comb_01_is_ok(self):
        val = _build_comb_validacao("EQ-001", "VAL-EQUIP-COMB-01")
        assert val.status == "OK"

    def test_comb_02_is_ok(self):
        val = _build_comb_validacao("EQ-001", "VAL-EQUIP-COMB-02")
        assert val.status == "OK"


# ===========================================================================
# 18. _mat_fonte1
# ===========================================================================


class TestMatFonte1:
    def test_basic_material_cost(self):
        """Lines 589-594: custo = consumo × preco × horas_mes."""
        ctx = SimpleNamespace(repo=MagicMock())
        ctx.repo.obter_insumo.return_value = {"preco_unitario": 5.0}
        materiais = [{"insumo_id": "MAT-1", "consumo_por_hora": 2.0}]
        result = _mat_fonte1(materiais, ctx, 100.0)
        assert result == pytest.approx(1000.0)

    def test_missing_insumo_skipped(self):
        ctx = SimpleNamespace(repo=MagicMock())
        ctx.repo.obter_insumo.return_value = None
        materiais = [{"insumo_id": "MISSING", "consumo_por_hora": 2.0}]
        result = _mat_fonte1(materiais, ctx, 100.0)
        assert result == 0.0


# ===========================================================================
# 19. _mat_fonte2_item
# ===========================================================================


class TestMatFonte2Item:
    def test_non_material_returns_zero(self):
        """Lines 598-599: not MATERIAL → 0."""
        ctx = SimpleNamespace(repo=MagicMock())
        ci = {"categoria_custo": "MO", "insumo_id": "FN-001", "coeficiente": 1.0}
        result = _mat_fonte2_item(ci, ctx, 10.0, 100.0)
        assert result == 0.0

    def test_missing_insumo_returns_zero(self):
        """Lines 600-602: insumo not found → 0."""
        ctx = SimpleNamespace(repo=MagicMock())
        ctx.repo.obter_insumo.return_value = None
        ci = {"categoria_custo": "MATERIAL", "insumo_id": "MAT-MISSING", "coeficiente": 1.0}
        result = _mat_fonte2_item(ci, ctx, 10.0, 100.0)
        assert result == 0.0

    def test_material_cost_computed(self):
        """Line 603: preco × coeficiente × producao_horaria × horas_mes."""
        ctx = SimpleNamespace(repo=MagicMock())
        ctx.repo.obter_insumo.return_value = {"preco_unitario": 2.0}
        ci = {"categoria_custo": "MATERIAL", "insumo_id": "MAT-001", "coeficiente": 3.0}
        result = _mat_fonte2_item(ci, ctx, 5.0, 20.0)
        assert result == pytest.approx(2.0 * 3.0 * 5.0 * 20.0)


# ===========================================================================
# 19b. _calc_custo_material_item (NEP-029 D4) — note: not referenced anywhere
# else in src/ or tests/ as of this writing; appears to be dead code kept for
# a future integration. Tested here directly since it's a pure function.
# ===========================================================================


class TestCalcCustoMaterialItem:
    def test_uses_fonte1_when_comp_has_materiais(self):
        """Lines 627-630: materiais_equipe present → delegates to _mat_fonte1."""
        ctx = SimpleNamespace(repo=MagicMock())
        ctx.repo.obter_insumo.return_value = {"preco_unitario": 5.0}
        comp = {"materiais": [{"insumo_id": "MAT-1", "consumo_por_hora": 2.0}]}
        result = _calc_custo_material_item(comp, {}, {}, ctx, 8.0, 21.0)
        assert result == pytest.approx(2.0 * 5.0 * (8.0 * 21.0))

    def test_no_materiais_and_no_producao_returns_zero(self):
        """Lines 631-635: no materiais_equipe, producao_horaria <= 0 → 0.0."""
        ctx = SimpleNamespace(repo=MagicMock())
        comp = {}
        cpu = {"producao_id_ref": "P1"}
        prod_lookup = {"P1": {"producao_horaria": 0.0}}
        result = _calc_custo_material_item(comp, cpu, prod_lookup, ctx, 8.0, 21.0)
        assert result == 0.0

    def test_no_materiais_falls_back_to_composicao_itens(self):
        """Line 636-638: fallback to summing _mat_fonte2_item over composicao_itens."""
        ctx = SimpleNamespace(repo=MagicMock())
        ctx.repo.obter_insumo.return_value = {"preco_unitario": 2.0}
        comp = {}
        cpu = {
            "producao_id_ref": "P1",
            "composicao_itens": [{"categoria_custo": "MATERIAL", "insumo_id": "MAT-1", "coeficiente": 3.0}],
        }
        prod_lookup = {"P1": {"producao_horaria": 5.0}}
        result = _calc_custo_material_item(comp, cpu, prod_lookup, ctx, 8.0, 21.0)
        assert result == pytest.approx(round(2.0 * 3.0 * 5.0 * (8.0 * 21.0), 2))


# ===========================================================================
# 20. _count_transitions
# ===========================================================================


class TestCountTransitions:
    def test_single_block(self):
        seq = [0, 1, 1, 1, 0]
        n_mob, n_desmob = _count_transitions(seq)
        assert n_mob == 1
        assert n_desmob == 1

    def test_two_separate_blocks(self):
        seq = [0, 1, 0, 1, 0]
        n_mob, n_desmob = _count_transitions(seq)
        assert n_mob == 2
        assert n_desmob == 2

    def test_empty_seq(self):
        n_mob, n_desmob = _count_transitions([])
        assert n_mob == 0
        assert n_desmob == 0

    def test_ending_active(self):
        """When sequence ends with active, desmob is still counted."""
        seq = [0, 1, 1]
        n_mob, n_desmob = _count_transitions(seq)
        assert n_mob == 1
        assert n_desmob == 1  # implicit desmob at end


# ===========================================================================
# 21. _accum_mob_costs_list
# ===========================================================================


class TestAccumMobCostsList:
    def test_single_item(self):
        items = [{"num_pessoas": 2, "custo_mobilizacao": 500.0, "custo_desmobilizacao": 250.0}]
        mob, demob = _accum_mob_costs_list(items, "num_pessoas")
        assert mob == pytest.approx(1000.0)
        assert demob == pytest.approx(500.0)

    def test_multiple_items(self):
        items = [
            {"num_pessoas": 1, "custo_mobilizacao": 100.0, "custo_desmobilizacao": 50.0},
            {"num_pessoas": 2, "custo_mobilizacao": 200.0, "custo_desmobilizacao": 100.0},
        ]
        mob, demob = _accum_mob_costs_list(items, "num_pessoas")
        assert mob == pytest.approx(100.0 + 400.0)
        assert demob == pytest.approx(50.0 + 200.0)

    def test_empty_list(self):
        mob, demob = _accum_mob_costs_list([], "num_pessoas")
        assert mob == 0.0
        assert demob == 0.0


# ===========================================================================
# 22. _calc_custo_mob_desmob
# ===========================================================================


class TestCalcCustoMobDesmob:
    def test_none_cron_returns_zero(self):
        """Line 655: cron is None → 0."""
        assert _calc_custo_mob_desmob({}, None) == 0.0

    def test_no_periodos_returns_zero(self):
        """Line 658: no distribuicao_semanal → 0."""
        cron = SimpleNamespace(distribuicao_semanal=None)
        assert _calc_custo_mob_desmob({}, cron) == 0.0

    def test_empty_periodos_returns_zero(self):
        """Line 661: distribuicao_semanal falsy ({}) → 0 (short-circuits before seq)."""
        cron = SimpleNamespace(distribuicao_semanal={})
        assert _calc_custo_mob_desmob({}, cron) == 0.0

    def test_periodos_truthy_but_seq_empty_returns_zero(self):
        """Line 673: `periodos` is truthy (non-empty mapping-like object) but
        `.values()` yields nothing → seq ends up empty → returns 0.0."""

        class _TruthyEmptyMapping:
            def __bool__(self):
                return True

            def values(self):
                return []

        cron = SimpleNamespace(distribuicao_semanal=_TruthyEmptyMapping())
        assert _calc_custo_mob_desmob({}, cron) == 0.0

    def test_basic_mob_desmob_cost(self):
        """One transition, one function with mob costs."""
        d1 = SimpleNamespace(num_equipes=0)
        d2 = SimpleNamespace(num_equipes=1)
        d3 = SimpleNamespace(num_equipes=0)
        cron = SimpleNamespace(distribuicao_semanal={"S1": d1, "S2": d2, "S3": d3})
        comp = {
            "funcoes": [{"num_pessoas": 1, "custo_mobilizacao": 1000.0, "custo_desmobilizacao": 500.0}],
            "equipamentos": [],
        }
        result = _calc_custo_mob_desmob(comp, cron)
        # 1 mob × 1000 + 1 demob × 500
        assert result == pytest.approx(1500.0)


# ===========================================================================
# 23. _sum_eq_weeks_and_cron_cost
# ===========================================================================


class TestSumEqWeeksAndCronCost:
    def test_basic(self):
        d1 = SimpleNamespace(num_equipes=2, eficiencia=1.0)
        d2 = SimpleNamespace(num_equipes=1, eficiencia=0.5)
        custo, team_weeks = _sum_eq_weeks_and_cron_cost([d1, d2], 1000.0, 200.0)
        # d1: (1000 + 200*1.0)*2 = 2400
        # d2: (1000 + 200*0.5)*1 = 1100
        assert custo == pytest.approx(3500.0)
        assert team_weeks == 3

    def test_empty_list(self):
        custo, team_weeks = _sum_eq_weeks_and_cron_cost([], 1000.0, 200.0)
        assert custo == 0.0
        assert team_weeks == 0


# ===========================================================================
# 24. _comb_efetivo_mensal
# ===========================================================================


class TestCombEfetivoMensal:
    def test_no_team_weeks_returns_custo_comb(self):
        """Line 737: team_weeks == 0 → returns custo_comb."""
        result = _comb_efetivo_mensal([], 100.0, 0, 999.0)
        assert result == 999.0

    def test_basic_calc(self):
        d1 = SimpleNamespace(num_equipes=2)
        d2 = SimpleNamespace(num_equipes=0)
        from concilium.domain.constants import SEMANAS_POR_MES

        result = _comb_efetivo_mensal([d1, d2], 50.0, 2, 0.0)
        # comb_total = 50 * 2 = 100
        # result = 100 / (2 / SEMANAS_POR_MES)
        expected = 100.0 / (2 / SEMANAS_POR_MES)
        assert result == pytest.approx(expected)


# ===========================================================================
# 25. _custo_ocioso_eq
# ===========================================================================


class TestCustoOciosoEq:
    def test_no_ativos_returns_zero(self):
        """Line 737 guard: ativos == 0 → 0."""
        result = _custo_ocioso_eq([], 100.0, 0)
        assert result == 0.0

    def test_no_idle_weeks(self):
        d1 = SimpleNamespace(num_equipes=1)
        d2 = SimpleNamespace(num_equipes=1)
        result = _custo_ocioso_eq([d1, d2], 100.0, 2)
        assert result == 0.0

    def test_idle_between_active(self):
        d1 = SimpleNamespace(num_equipes=1)
        d2 = SimpleNamespace(num_equipes=0)
        d3 = SimpleNamespace(num_equipes=1)
        result = _custo_ocioso_eq([d1, d2, d3], 100.0, 2)
        # 1 idle week between first and last active
        assert result == pytest.approx(100.0)

    def test_all_weeks_inactive_returns_zero(self):
        """Line 749: custo_eq_semanal and ativos truthy, but every period has
        num_equipes == 0 → indices_ativos empty → returns 0.0."""
        d1 = SimpleNamespace(num_equipes=0)
        d2 = SimpleNamespace(num_equipes=0)
        result = _custo_ocioso_eq([d1, d2], 100.0, 2)
        assert result == 0.0


# ===========================================================================
# 26. _week_idx
# ===========================================================================


class TestWeekIdx:
    def test_s_format(self):
        assert _week_idx("S052") == 52
        assert _week_idx("S001") == 1

    def test_iso_format(self):
        """Lines 990-991: ISO format parsed."""
        idx = _week_idx("2026-W01")
        assert isinstance(idx, int)
        assert idx > 0

    def test_invalid_iso_raises_instead_of_aliasing_week_zero(self):
        """Malformed ISO keys must not silently corrupt pool-gap calculations."""
        with pytest.raises(ValueError, match="invalid ISO week format"):
            _week_idx("2026-WINVALID")

    def test_numeric_string(self):
        assert _week_idx("10") == 10

    def test_invalid_string_raises(self):
        """Unsupported week labels must not silently alias week zero."""
        with pytest.raises(ValueError, match="unsupported week index"):
            _week_idx("abc")

    def test_s_leading_zeros(self):
        assert _week_idx("S007") == 7


# ===========================================================================
# 27. _eq_comp_floats
# ===========================================================================


class TestEqCompFloats:
    def test_all_fields_present(self):
        eq = SimpleNamespace(
            custo_mao_obra_mensal=1000.0,
            custo_equipamentos_mensal=500.0,
            custo_combustivel_total_mensal=100.0,
            custo_material_mensal=50.0,
        )
        mo, eq_c, comb, mat = _eq_comp_floats(eq)
        assert mo == 1000.0
        assert eq_c == 500.0
        assert comb == 100.0
        assert mat == 50.0

    def test_missing_fields_default_to_zero(self):
        eq = SimpleNamespace()
        mo, eq_c, comb, mat = _eq_comp_floats(eq)
        assert mo == 0.0
        assert eq_c == 0.0
        assert comb == 0.0
        assert mat == 0.0


# ===========================================================================
# 28. _accum_week_demand
# ===========================================================================


class TestAccumWeekDemand:
    def test_basic_accumulation(self):
        """Line 1037: actual_mw = 0 → fallback required × len(active_weeks)."""
        tipo_week_demand = {}
        d1 = SimpleNamespace(num_equipes=2)
        dist = {"S1": d1}
        _accum_week_demand(tipo_week_demand, "TIPO-A", ["S1"], dist, 2, 2)
        assert tipo_week_demand["TIPO-A"]["S1"] == 2

    def test_accumulates_across_weeks(self):
        tipo_week_demand = {}
        d1 = SimpleNamespace(num_equipes=2)
        d2 = SimpleNamespace(num_equipes=3)
        dist = {"S1": d1, "S2": d2}
        _accum_week_demand(tipo_week_demand, "TIPO-A", ["S1", "S2"], dist, 3, 3, profile={"per_front": 1})
        assert tipo_week_demand["TIPO-A"] == {"S1": 2, "S2": 3}


# ===========================================================================
# 29. _get_active_weeks
# ===========================================================================


class TestGetActiveWeeks:
    def test_returns_only_active_weeks(self):
        d_active = SimpleNamespace(num_equipes=2)
        d_zero = SimpleNamespace(num_equipes=0)
        sa = SimpleNamespace(distribuicao_semanal={"S1": d_active, "S2": d_zero, "S3": d_active})
        result = _get_active_weeks(sa)
        assert "S1" in result
        assert "S3" in result
        assert "S2" not in result

    def test_no_distribution_returns_empty(self):
        sa = SimpleNamespace(distribuicao_semanal=None)
        assert _get_active_weeks(sa) == []

    def test_sorted_by_week_idx(self):
        d = SimpleNamespace(num_equipes=1)
        sa = SimpleNamespace(distribuicao_semanal={"S3": d, "S1": d, "S2": d})
        result = _get_active_weeks(sa)
        assert result == ["S1", "S2", "S3"]


# ===========================================================================
# 30b. _process_item_tipo_map
# ===========================================================================


class TestProcessItemTipoMap:
    def test_missing_equipe_appends_val_pool_contrato_01(self):
        """Lines 1117-1124: eq or sa missing → VAL-POOL-CONTRATO-01 + early return."""
        validacoes: list = []
        tipo_items: dict = {}
        tipo_week_demand: dict = {}
        _process_item_tipo_map(
            "ITEM-1",
            {"OPERADOR": 2},
            equipe_map={},
            pool={"OPERADOR": {}},
            sched_lookup={},
            tipo_items=tipo_items,
            tipo_week_demand=tipo_week_demand,
            validacoes=validacoes,
        )
        assert len(validacoes) == 1
        assert validacoes[0].codigo == "VAL-POOL-CONTRATO-01"
        assert tipo_items == {}
        assert tipo_week_demand == {}

    def test_tipo_not_in_pool_skipped(self):
        """Line 1133: tipo not present in pool → continue without appending."""
        d1 = SimpleNamespace(num_equipes=1)
        sa = SimpleNamespace(distribuicao_semanal={"S1": d1})
        eq = SimpleNamespace(custo_total=100.0, custo_mo=0.0, custo_eq=0.0, custo_comb=0.0, custo_mat=0.0)
        validacoes: list = []
        tipo_items: dict = {}
        tipo_week_demand: dict = {}
        _process_item_tipo_map(
            "ITEM-1",
            {"OPERADOR": 1},
            equipe_map={"ITEM-1": eq},
            pool={},  # OPERADOR not in pool
            sched_lookup={"ITEM-1": sa},
            tipo_items=tipo_items,
            tipo_week_demand=tipo_week_demand,
            validacoes=validacoes,
        )
        assert tipo_items == {}
        assert tipo_week_demand == {}
        assert validacoes == []

    def test_type_counts_do_not_share_an_invalid_heterogeneous_denominator(self):
        """Required values of different resource types cannot be added as fronts."""
        d1 = SimpleNamespace(num_equipes=1)
        sa = SimpleNamespace(distribuicao_semanal={"S1": d1})
        eq = SimpleNamespace(custo_total=100.0, custo_mo=25.0, custo_eq=25.0, custo_comb=25.0, custo_mat=25.0)
        validacoes: list = []
        tipo_items: dict = {}
        tipo_week_demand: dict = {}
        # OTHER is a separate physical dimension; OPERADOR still requires 1 unit.
        _process_item_tipo_map(
            "ITEM-1",
            {"OPERADOR": 1, "OUTRO": 2},
            equipe_map={"ITEM-1": eq},
            pool={"OPERADOR": {}},  # só OPERADOR é processado; OUTRO seria pulado (não testado aqui)
            sched_lookup={"ITEM-1": sa},
            tipo_items=tipo_items,
            tipo_week_demand=tipo_week_demand,
            validacoes=validacoes,
        )
        assert tipo_items["OPERADOR"][0]["machine_weeks"] == 1
        assert tipo_week_demand["OPERADOR"] == {"S1": 1}


# ===========================================================================
# 31. _resolve_prod_lookup
# ===========================================================================


class TestResolveProdLookup:
    def test_uses_produtividades(self):
        catalogo = {"produtividades": [{"id": "P1", "valor": 1.0}, {"id": "P2"}]}
        result = _resolve_prod_lookup(catalogo)
        assert "P1" in result
        assert "P2" in result

    def test_falls_back_to_producoes(self):
        catalogo = {"producoes": [{"id": "Q1"}]}
        result = _resolve_prod_lookup(catalogo)
        assert "Q1" in result

    def test_entries_without_id_skipped(self):
        catalogo = {"produtividades": [{"id": None, "v": 1}, {"id": "P3"}]}
        result = _resolve_prod_lookup(catalogo)
        assert None not in result
        assert "P3" in result


# ===========================================================================
# 33. _build_perpetuation_chains
# ===========================================================================


class TestBuildPerpetuationChains:
    def _make_item(self, item_id, start, end, required=1, active_weeks=None):
        if active_weeks is None:
            active_weeks = [f"S{start:03d}"]
        return {
            "item_id": item_id,
            "start_idx": start,
            "end_idx": end,
            "required": required,
            "active_weeks": active_weeks,
            "machine_weeks": end - start,
            "semana_inicio": f"S{start:03d}",
            "semana_fim": f"S{end:03d}",
        }

    def test_empty_items_returns_empty(self):
        """Line 1653: items empty → []."""
        result = _build_perpetuation_chains("TIPO-A", [])
        assert result == []

    def test_single_item_forms_single_chain(self):
        items = [self._make_item("A", 1, 5)]
        result = _build_perpetuation_chains("TIPO-A", items)
        assert len(result) == 1
        assert "A" in result[0].item_ids

    def test_close_items_merged_into_one_chain(self):
        """Gap ≤ delta_max → single chain."""
        items = [
            self._make_item("A", 1, 5),
            self._make_item("B", 6, 10),  # gap = 1
        ]
        result = _build_perpetuation_chains("TIPO-A", items, delta_max=2)
        assert len(result) == 1
        assert "A" in result[0].item_ids
        assert "B" in result[0].item_ids

    def test_far_items_form_separate_chains(self):
        """Gap > delta_max → two chains."""
        items = [
            self._make_item("A", 1, 5),
            self._make_item("B", 15, 20),  # gap = 10
        ]
        result = _build_perpetuation_chains("TIPO-A", items, delta_max=2)
        assert len(result) == 2

    def test_gap_max_prevents_perpetuation(self):
        """ADR-079: gap > gap_max → no perpetuation even if gap <= delta_max."""
        items = [
            self._make_item("A", 1, 5),
            self._make_item("B", 6, 10),
        ]
        result = _build_perpetuation_chains("TIPO-A", items, delta_max=10, gap_max=0)
        assert len(result) == 2

    def test_cost_based_perpetuation(self):
        """When mob+demob > 0, use cost threshold."""
        items = [
            self._make_item("A", 1, 5, required=1),
            self._make_item("B", 6, 10, required=1),
        ]
        # standby cost for gap=1 week: 0 * 1 = 0, mob+demob = 1000 → perpetuate
        result = _build_perpetuation_chains(
            "TIPO-A", items, custo_mob_unit=500.0, custo_demob_unit=500.0, custo_standby_unit=0.0
        )
        assert len(result) == 1


class TestBuildPerpetuationChainsAninhamento:
    """ADR-073 fix: gap deve ser medido contra a cobertura máxima já vista na
    cadeia (running max de end_idx), não contra o último item adicionado em
    ordem de start_idx — bug exposto por atividades aninhadas/escalonadas de
    forma não-monotônica em end_idx (ex.: B aninhado dentro de A, termina antes).
    """

    def _item(self, item_id, start, end, required=1):
        return {
            "item_id": item_id,
            "start_idx": start,
            "end_idx": end,
            "required": required,
            "active_weeks": [f"S{w:03d}" for w in range(start, end)],
            "machine_weeks": end - start,
            "semana_inicio": f"S{start:03d}",
            "semana_fim": f"S{end - 1:03d}",
        }

    def test_nested_item_does_not_create_spurious_gap(self):
        """A=[0,10) cobre B=[2,4). C começa 2 semanas após o fim REAL da
        cobertura (10), não 8 semanas após o fim do último item processado
        por start_idx (B, fim=4)."""
        items = [self._item("A", 0, 10), self._item("B", 2, 4), self._item("C", 12, 20)]
        result = _build_perpetuation_chains("TIPO-X", items, delta_max=5)
        assert len(result) == 1
        assert set(result[0].item_ids) == {"A", "B", "C"}
        assert result[0].semanas_ociosas == 2  # gap real 12-10, NÃO 12-4=8

    def test_nested_item_gap_still_breaks_when_real_gap_exceeds_delta(self):
        """O fix não super-funde: o gap real (2 semanas) ainda quebra a cadeia
        quando delta_max é menor que ele."""
        items = [self._item("A", 0, 10), self._item("B", 2, 4), self._item("C", 12, 20)]
        result = _build_perpetuation_chains("TIPO-X", items, delta_max=1)
        assert len(result) == 2
        assert set(result[0].item_ids) == {"A", "B"}
        assert set(result[1].item_ids) == {"C"}

    def test_nested_item_boundary_uses_week_demand_when_provided(self):
        """Quando week_demand é fornecido, o custo de standby usa a demanda
        agregada real na borda do gap, não o `required` isolado do item
        aninhado (que termina cedo e não reflete a demanda real no fim da
        cobertura)."""
        items = [
            self._item("A", 0, 10, required=3),
            self._item("B", 2, 4, required=7),  # required maior, mas termina antes
            self._item("C", 12, 20, required=2),
        ]
        week_demand = {
            **{f"S{w:03d}": 3 for w in range(0, 10)},
            **{f"S{w:03d}": 2 for w in range(12, 20)},
        }
        result = _build_perpetuation_chains(
            "TIPO-X",
            items,
            custo_mob_unit=1000.0,
            custo_demob_unit=1000.0,
            custo_standby_unit=10.0,
            week_demand=week_demand,
        )
        assert len(result) == 1
        assert result[0].custo_standby == pytest.approx(2 * 10.0 * 2)  # min(3,2)=2, não required de B (7)


# ===========================================================================
# 34. _build_predecessor_map
# ===========================================================================


class TestBuildPredecessorMap:
    def test_single_item_no_predecessor(self):
        items = [{"item_id": "A"}]
        cadeia = _make_cadeia(item_ids=["A"])
        result = _build_predecessor_map(items, [cadeia])
        assert result["A"] is None

    def test_chain_with_two_items(self):
        items = [{"item_id": "A"}, {"item_id": "B"}]
        cadeia = _make_cadeia(item_ids=["A", "B"])
        result = _build_predecessor_map(items, [cadeia])
        assert result["A"] is None
        assert result["B"] == "A"

    def test_empty_cadeias(self):
        items = [{"item_id": "A"}]
        result = _build_predecessor_map(items, [])
        assert result["A"] is None


# ===========================================================================
# 35. _init_item_float_maps
# ===========================================================================


class TestInitItemFloatMaps:
    def test_returns_correct_number_of_dicts(self):
        items = [{"item_id": "A"}, {"item_id": "B"}]
        result = _init_item_float_maps(items, "x", "y", "z")
        assert len(result) == 3
        for d in result:
            assert d == {"A": 0.0, "B": 0.0}

    def test_empty_items(self):
        result = _init_item_float_maps([], "k1", "k2")
        assert result == ({}, {})


# ===========================================================================
# 36. _compute_ocioso_para_item
# ===========================================================================


class TestComputeOciosoParaItem:
    def test_no_cadeia_returns_zero(self):
        """Lines 1967-1968: cadeia is None → 0."""
        result = _compute_ocioso_para_item("B", None, {}, 100.0, 1)
        assert result == 0.0

    def test_first_item_in_chain_no_ocioso(self):
        """First item in chain (k==0) → no ocioso."""
        item_a = {"item_id": "A", "start_idx": 1, "end_idx": 5, "machine_weeks": 4}
        item_b = {"item_id": "B", "start_idx": 7, "end_idx": 10, "machine_weeks": 3}
        cadeia = _make_cadeia(item_ids=["A", "B"])
        item_by_id = {"A": item_a, "B": item_b}
        # A is first — no ocioso
        result = _compute_ocioso_para_item("A", cadeia, item_by_id, 100.0, 1)
        assert result == 0.0

    def test_successor_gets_gap_cost(self):
        """Lines 1972-1978: successor B gets cost for gap weeks."""
        item_a = {"item_id": "A", "start_idx": 1, "end_idx": 5, "machine_weeks": 4}
        item_b = {"item_id": "B", "start_idx": 8, "end_idx": 12, "machine_weeks": 4}
        cadeia = _make_cadeia(item_ids=["A", "B"])
        item_by_id = {"A": item_a, "B": item_b}
        # gap = 8 - 5 = 3 weeks
        result = _compute_ocioso_para_item("B", cadeia, item_by_id, 100.0, 1)
        assert result == pytest.approx(300.0)


# ===========================================================================
# 37. _compute_particao_por_tipo
# ===========================================================================


class TestComputeParticaoPorTipo:
    def _make_items(self):
        return [
            {
                "item_id": "A",
                "machine_weeks": 4,
                "required": 1,
                "T_start": 1.0,
                "T_end": 5.0,
                "start_idx": 1,
                "end_idx": 5,
                "active_weeks": ["S1", "S2", "S3", "S4"],
                "semana_inicio": "S1",
                "semana_fim": "S4",
            },
            {
                "item_id": "B",
                "machine_weeks": 3,
                "required": 1,
                "T_start": 7.0,
                "T_end": 10.0,
                "start_idx": 7,
                "end_idx": 10,
                "active_weeks": ["S7", "S8", "S9"],
                "semana_inicio": "S7",
                "semana_fim": "S9",
            },
        ]

    def test_basic_partition(self):
        """Lines 2002-2064: basic partition creates CustoParticionadoItem per item."""
        items = self._make_items()
        atribuicao = {"A": (400.0, "TIPO-A", 0.5), "B": (300.0, "TIPO-A", 0.5)}
        cadeia = _make_cadeia(item_ids=["A", "B"])
        result = _compute_particao_por_tipo(items, [cadeia], atribuicao, 100.0, 2, 50.0, 25.0)
        assert len(result) == 2
        ids = {r.item_id for r in result}
        assert ids == {"A", "B"}

    def test_custo_total_particionado_from_atribuicao(self):
        """Lines 2034: custo_total_particionado = atribuicao[iid][0]."""
        items = self._make_items()
        atribuicao = {"A": (999.0, "TIPO-A", 0.5), "B": (777.0, "TIPO-A", 0.5)}
        result = _compute_particao_por_tipo(items, [], atribuicao, 100.0, 1, 0.0, 0.0)
        a_part = next(r for r in result if r.item_id == "A")
        b_part = next(r for r in result if r.item_id == "B")
        assert a_part.custo_total_particionado == pytest.approx(999.0)
        assert b_part.custo_total_particionado == pytest.approx(777.0)

    def test_empty_items_returns_empty(self):
        result = _compute_particao_por_tipo([], [], {}, 100.0, 1, 0.0, 0.0)
        assert result == []


# ===========================================================================
# 38. _compress_to_segments
# ===========================================================================


class TestCompressToSegments:
    def test_empty_week_map_returns_empty(self):
        assert _compress_to_segments({}) == []

    def test_single_activity_single_segment(self):
        week_map = {"S1": "ACT-A", "S2": "ACT-A", "S3": "ACT-A"}
        result = _compress_to_segments(week_map)
        assert len(result) == 1
        assert result[0].activity_id == "ACT-A"
        assert result[0].machine_weeks == 3

    def test_two_activities_two_segments(self):
        week_map = {"S1": "ACT-A", "S2": "ACT-B", "S3": "ACT-B"}
        result = _compress_to_segments(week_map)
        assert len(result) == 2
        act_ids = [s.activity_id for s in result]
        assert "ACT-A" in act_ids
        assert "ACT-B" in act_ids

    def test_alternating_activities(self):
        week_map = {"S1": "A", "S2": "B", "S3": "A"}
        result = _compress_to_segments(week_map)
        assert len(result) == 3


# ===========================================================================
# 39. _compute_desmob_antecipada
# ===========================================================================


class TestComputeDesmobAntecipada:
    def test_no_ultima_atividade_returns_zero(self):
        """Line 2229: empty ultima_atividade → (0, 0.0)."""
        result = _compute_desmob_antecipada("", 100.0, 200.0, 10)
        assert result == (0, 0.0)

    def test_c_idle_zero_returns_zero(self):
        result = _compute_desmob_antecipada("S008", 0.0, 200.0, 10)
        assert result == (0, 0.0)

    def test_no_trailing_weeks_returns_zero(self):
        """Line 2233: trailing == 0 → (0, 0.0)."""
        result = _compute_desmob_antecipada("S010", 100.0, 200.0, 10)
        assert result == (0, 0.0)

    def test_positive_economia(self):
        """c_idle × trailing > c_demob → returns (trailing, economia)."""
        # trailing = 10 - 5 = 5
        # economia = 100 * 5 - 50 = 450
        trailing, econ = _compute_desmob_antecipada("S005", 100.0, 50.0, 10)
        assert trailing == 5
        assert econ == pytest.approx(450.0)

    def test_negative_economia_returns_zero(self):
        """If standing by is more expensive, no anticipation."""
        # c_idle=10, trailing=2, c_demob=100 → 10*2 - 100 = -80 < 0
        result = _compute_desmob_antecipada("S008", 10.0, 100.0, 10)
        assert result == (0, 0.0)


# ===========================================================================
# 40. _build_demand_per_week
# ===========================================================================


class TestBuildDemandPerWeek:
    def test_basic_demand(self):
        d = SimpleNamespace(num_equipes=4)
        dist = {"S1": d}
        result = _build_demand_per_week(dist, 2, 4)
        assert result["S1"] == 2  # round(4 * 2/4) = 2

    def test_zero_equipes_excluded(self):
        d_zero = SimpleNamespace(num_equipes=0)
        d_pos = SimpleNamespace(num_equipes=2)
        dist = {"S1": d_zero, "S2": d_pos}
        result = _build_demand_per_week(dist, 1, 2)
        assert "S1" not in result
        assert "S2" in result

    def test_empty_dist(self):
        result = _build_demand_per_week({}, 1, 1)
        assert result == {}


# ===========================================================================
# 40b. _item_demand_for_tipo / _collect_items_data_for_tipo
# ===========================================================================


class TestItemDemandForTipo:
    def test_tipo_not_in_map_returns_none(self):
        """Line 2270-2271: tipo_id absent from tipo_map → None."""
        result = _item_demand_for_tipo("ITEM-1", "T-X", {"T-Y": 1}, {}, {})
        assert result is None

    def test_no_schedule_returns_none(self):
        """Line 2275-2276: iid not found in sched_lookup → None."""
        result = _item_demand_for_tipo("ITEM-1", "T-X", {"T-X": 1}, {"ITEM-1": 4}, {})
        assert result is None

    def test_empty_demand_returns_none(self):
        """demand_per_week empty (no active weeks) → None."""
        sa = SimpleNamespace(distribuicao_semanal={})
        result = _item_demand_for_tipo("ITEM-1", "T-X", {"T-X": 1}, {"ITEM-1": 4}, {"ITEM-1": sa})
        assert result is None

    def test_valid_demand_returned(self):
        d = SimpleNamespace(num_equipes=4)
        sa = SimpleNamespace(distribuicao_semanal={"S1": d})
        result = _item_demand_for_tipo("ITEM-1", "T-X", {"T-X": 2}, {"ITEM-1": 4}, {"ITEM-1": sa})
        assert result == {"S1": 2}


class TestCollectItemsDataForTipo:
    def test_tipo_missing_from_item_map_skipped(self):
        """Line 2289-2290: tipo_id not in item's tipo_map → item skipped."""
        result = _collect_items_data_for_tipo("T-X", {"ITEM-1": {"T-OTHER": 1}}, {}, {})
        assert result == []

    def test_empty_demand_skips_item(self):
        """Line 2292-2293: _item_demand_for_tipo returns None/empty → skip."""
        sa = SimpleNamespace(distribuicao_semanal={})
        result = _collect_items_data_for_tipo("T-X", {"ITEM-1": {"T-X": 1}}, {"ITEM-1": 4}, {"ITEM-1": sa})
        assert result == []

    def test_valid_item_included(self):
        d = SimpleNamespace(num_equipes=4)
        sa = SimpleNamespace(distribuicao_semanal={"S1": d})
        result = _collect_items_data_for_tipo("T-X", {"ITEM-1": {"T-X": 2}}, {"ITEM-1": 4}, {"ITEM-1": sa})
        assert len(result) == 1
        assert result[0]["item_id"] == "ITEM-1"


# ===========================================================================
# 41. _build_item_resource_maps
# ===========================================================================


class TestBuildItemResourceMaps:
    def test_basic(self):
        activities = [
            {"item_id": "A", "required_resources": {"TIPO-X": 2, "TIPO-Y": 1}},
            {"item_id": "B", "required_resources": {"TIPO-X": 3}},
        ]
        tipo_req, total_peak = _build_item_resource_maps(activities)
        assert tipo_req["A"]["TIPO-X"] == 2
        assert tipo_req["A"]["TIPO-Y"] == 1
        assert total_peak["A"] == 3  # sum(2, 1)
        assert total_peak["B"] == 3

    def test_missing_item_id_skipped(self):
        activities = [{"required_resources": {"TIPO-X": 1}}]
        tipo_req, total_peak = _build_item_resource_maps(activities)
        assert len(tipo_req) == 0

    def test_empty_activities(self):
        assert _build_item_resource_maps([]) == ({}, {})


# ===========================================================================
# 42. _last_week_idx_for_act / _first_week_idx_for_act
# ===========================================================================


class TestWeekIdxForAct:
    def test_last_week_idx(self):
        """Lines 2938-2943."""
        segs = [
            _make_seg("ACT-A", "S001", "S005"),
            _make_seg("ACT-A", "S003", "S008"),
            _make_seg("ACT-B", "S002", "S010"),
        ]
        result = _last_week_idx_for_act(segs, "ACT-A")
        assert result == _week_idx("S008")

    def test_last_week_idx_not_found(self):
        segs = [_make_seg("ACT-A", "S001", "S005")]
        result = _last_week_idx_for_act(segs, "MISSING")
        assert result is None

    def test_first_week_idx(self):
        """Lines 2948-2953."""
        segs = [
            _make_seg("ACT-A", "S003", "S007"),
            _make_seg("ACT-A", "S001", "S004"),
        ]
        result = _first_week_idx_for_act(segs, "ACT-A")
        assert result == _week_idx("S001")

    def test_first_week_idx_not_found(self):
        segs = [_make_seg("ACT-A", "S001", "S005")]
        result = _first_week_idx_for_act(segs, "MISSING")
        assert result is None


# ===========================================================================
# 43. _compute_gap_for_inst
# ===========================================================================


class TestComputeGapForInst:
    def test_gap_computed(self):
        """Lines 2958-2962."""
        segs = [
            _make_seg("PRED", "S001", "S005"),
            _make_seg("SUCC", "S008", "S010"),
        ]
        inst = SimpleNamespace(segmentos_atividade=segs)
        result = _compute_gap_for_inst(inst, "PRED", "SUCC")
        # last of PRED = 5, first of SUCC = 8 → gap = 8 - 5 - 1 = 2
        assert result == 2

    def test_no_pred_segments_returns_zero(self):
        segs = [_make_seg("SUCC", "S008", "S010")]
        inst = SimpleNamespace(segmentos_atividade=segs)
        result = _compute_gap_for_inst(inst, "PRED", "SUCC")
        assert result == 0

    def test_adjacent_no_gap(self):
        segs = [
            _make_seg("PRED", "S001", "S004"),
            _make_seg("SUCC", "S005", "S008"),
        ]
        inst = SimpleNamespace(segmentos_atividade=segs)
        result = _compute_gap_for_inst(inst, "PRED", "SUCC")
        # 5 - 4 - 1 = 0
        assert result == 0

    def test_overlap_returns_zero(self):
        """Overlap (negative gap) clamped to 0."""
        segs = [
            _make_seg("PRED", "S001", "S007"),
            _make_seg("SUCC", "S005", "S010"),
        ]
        inst = SimpleNamespace(segmentos_atividade=segs)
        result = _compute_gap_for_inst(inst, "PRED", "SUCC")
        assert result == 0


# ===========================================================================
# 44. _sum_inst_categories
# ===========================================================================


class TestSumInstCategories:
    def _make_inst(self, mo=0.0, eq=0.0, comb=0.0, mat=0.0, idle_mo=0.0, idle_eq=0.0, mob=0.0, demob=0.0):
        return SimpleNamespace(
            custo_ativo_mo=mo,
            custo_ativo_eq=eq,
            custo_ativo_comb=comb,
            custo_ativo_mat=mat,
            custo_idle_mo=idle_mo,
            custo_idle_eq=idle_eq,
            custo_mob_instancia=mob,
            custo_demob_instancia=demob,
        )

    def test_single_instance(self):
        inst = self._make_inst(
            mo=100.0, eq=200.0, comb=50.0, mat=10.0, idle_mo=20.0, idle_eq=30.0, mob=8.0, demob=5.0
        )
        tot_mo, tot_eq, tot_comb, tot_mat = _sum_inst_categories([inst])
        assert tot_mo == pytest.approx(120.0)  # 100 + 20
        assert tot_eq == pytest.approx(243.0)  # 200 + 30 + 8 + 5 (ADR-136 F3: mob também entra em EQ)
        assert tot_comb == pytest.approx(50.0)
        assert tot_mat == pytest.approx(10.0)

    def test_multiple_instances(self):
        i1 = self._make_inst(mo=100.0, eq=50.0, comb=20.0, mat=5.0)
        i2 = self._make_inst(mo=100.0, eq=50.0, comb=20.0, mat=5.0)
        tot_mo, tot_eq, tot_comb, tot_mat = _sum_inst_categories([i1, i2])
        assert tot_mo == pytest.approx(200.0)
        assert tot_eq == pytest.approx(100.0)

    def test_empty_list(self):
        tot_mo, tot_eq, tot_comb, tot_mat = _sum_inst_categories([])
        assert tot_mo == 0.0
        assert tot_eq == 0.0
        assert tot_comb == 0.0
        assert tot_mat == 0.0


# ===========================================================================
# _build_resumo_e_validacoes — status_utilizacao thresholds (ADR-077)
# ===========================================================================


class TestBuildResumoEValidacoes:
    def _contrato(self, semanas_contrato=10):
        return SimpleNamespace(contrato_id="CTR-1", semanas_contrato=semanas_contrato)

    def test_taxa_alta_status_ok(self):
        """taxa_geral >= 65.0 -> status OK."""
        contrato = self._contrato(semanas_contrato=10)
        instance_active = {1: 8}
        instance_standby = {1: 0}
        validacoes: list = []
        resumo = _build_resumo_e_validacoes("T1", contrato, 1, instance_active, instance_standby, 100.0, validacoes)
        assert resumo.status_utilizacao == "OK"

    def test_taxa_media_status_aviso(self):
        """35.0 <= taxa_geral < 65.0 -> status AVISO."""
        contrato = self._contrato(semanas_contrato=10)
        instance_active = {1: 4}
        instance_standby = {1: 0}
        validacoes: list = []
        resumo = _build_resumo_e_validacoes("T1", contrato, 1, instance_active, instance_standby, 100.0, validacoes)
        assert resumo.status_utilizacao == "AVISO"

    def test_taxa_baixa_status_critico(self):
        """Line 2451: taxa_geral < 35.0 -> status CRITICO."""
        contrato = self._contrato(semanas_contrato=10)
        instance_active = {1: 1}
        instance_standby = {1: 0}
        validacoes: list = []
        resumo = _build_resumo_e_validacoes("T1", contrato, 1, instance_active, instance_standby, 100.0, validacoes)
        assert resumo.status_utilizacao == "CRITICO"

    def test_taxa_baixa_com_standby_alto_gera_validacao_erro(self):
        """CRITICO + instância com standby alto -> VAL-SLOT-STANDBY-ALTO com status ERRO."""
        contrato = self._contrato(semanas_contrato=10)
        instance_active = {1: 1}
        instance_standby = {1: 9}  # standby ratio 90% > _STANDBY_THRESHOLD_PCT
        validacoes: list = []
        resumo = _build_resumo_e_validacoes("T1", contrato, 1, instance_active, instance_standby, 100.0, validacoes)
        assert resumo.status_utilizacao == "CRITICO"
        assert any(v.status == "ERRO" for v in validacoes)


# ===========================================================================
# 40. _processar_equipamentos_item — alias enrichment path (line 553)
# ===========================================================================


class TestProcessarEquipamentosItemAliasEnrichment:
    def test_alias_attrs_merged_when_primary_insumo_lacks_consumo(self):
        """O insumo principal do equipamento não traz consumo_litros_hora nos
        seus atributos_especificos; _best_alias_equip_attrs() encontra um alias
        no catálogo (via codigo_planilha) com o consumo, e ele é mesclado em
        _attrs (branch true de `if alias_attrs:`, linha 553)."""
        repo = MagicMock()
        repo.obter_insumo.return_value = {
            "codigo": "E0027",
            "descricao": "Rolo compactador liso",
            "preco_unitario": 500.0,
            "atributos_especificos": {},  # sem consumo_litros_hora
        }
        repo._insumos = {
            "EQ-ROLO-LISO": {
                "codigo": "EQ-ROLO-LISO",
                "tipo": "EQUIPAMENTO",
                "descricao": "Rolo compactador liso",
                "atributos_especificos": {
                    "codigo_planilha": "E0027",
                    "consumo_litros_hora": 7.0,
                    "tipo_combustivel": "Diesel S10",
                },
            }
        }
        repo.resolver_preco.return_value = (500.0, "catalogo")
        ctx = SimpleNamespace(repo=repo, jurisdicao_id="mendeslobo", overrides={}, data_base=None)

        comp = {"equipamentos": [{"equip_id": "E0027", "num_unidades": 1}]}
        validacoes: list = []
        equips_mod, custo_eq, custo_comb, modo_est = _processar_equipamentos_item(
            comp, "1.1", {}, {}, 8.0, 21.0, 6.20, ctx, validacoes
        )

        assert len(equips_mod) == 1
        assert equips_mod[0].consumo_litros_hora == 7.0
        assert equips_mod[0].tipo_combustivel == "Diesel S10"
        assert custo_comb > 0.0


# ===========================================================================
# 41. _derive_rcpsp_from_canonical
# ===========================================================================


class TestDeriveRcpspFromCanonical:
    def test_empty_eap_returns_none(self):
        """Linha 1429: cronograma tem atividades mas eap está vazio → None."""
        sched_act = SimpleNamespace(activity_id="A1", distribuicao_semanal={})
        canonical_in = SimpleNamespace(
            cronograma=SimpleNamespace(scheduled_activities=[sched_act]),
            eap=[],
        )
        result = _derive_rcpsp_from_canonical(canonical_in, {})
        assert result is None

    def test_item_not_scheduled_is_skipped(self):
        """Linha 1469: item da EAP sem entrada correspondente no cronograma é
        pulado; um segundo item, agendado e com composição válida, ainda
        produz um spec derivado normalmente."""
        dist = {"2026-W01": SimpleNamespace(num_equipes=2)}
        sched_act = SimpleNamespace(activity_id="SCHEDULED-1", distribuicao_semanal=dist)
        canonical_in = SimpleNamespace(
            cronograma=SimpleNamespace(scheduled_activities=[sched_act]),
            eap=[
                SimpleNamespace(item_id="NOT-SCHEDULED", cpu_id="CPU-X"),
                SimpleNamespace(item_id="SCHEDULED-1", cpu_id="CPU-1"),
            ],
        )
        catalogo = {
            "cpus": [{"codigo": "CPU-1", "producao_id_ref": "PROD-1"}],
            "producoes": [
                {
                    "id": "PROD-1",
                    "composicao_padrao_equipe": {"equipamentos": [{"equip_id": "EQ-1", "num_unidades": 1}]},
                }
            ],
        }
        result = _derive_rcpsp_from_canonical(canonical_in, catalogo)
        assert result is not None
        item_ids = {a["item_id"] for a in result["activities"]}
        assert item_ids == {"SCHEDULED-1"}


# ===========================================================================
# 42. _build_contratos_recurso — total_mw==0 e tipo_costs não-dict
# ===========================================================================


class TestBuildContratosRecursoEdgeCases:
    def _mk_sched(self, item_id, weeks):
        from concilium.domain.models.canonical import DistribuicaoSemanal, ScheduledActivityCanonical

        dist = {
            w: DistribuicaoSemanal(
                num_equipes=1,
                qtd_executada=10.0,
                qtd_acumulada=10.0,
                pct=1.0,
                eficiencia=1.0,
                fator_clima=1.0,
                fator_calendario=1.0,
            )
            for w in weeks
        }
        return ScheduledActivityCanonical(
            activity_id=item_id, start_week=0, end_week=len(weeks), duration_weeks=len(weeks), distribuicao_semanal=dist
        )

    def _mk_equipe(self, item_id, custo_total=1000.0):
        from concilium.domain.models.canonical import EquipeDireta

        return EquipeDireta(
            equipe_id=f"eq-{item_id}",
            item_id=item_id,
            cpu_id="CPU-X",
            custo_mao_obra_mensal=100.0,
            custo_total=custo_total,
        )

    def test_total_mw_zero_skips_tipo(self):
        """Linha 1587: required_resources=0 para o único tipo → machine_weeks=0
        em todos os itens do tipo → total_mw==0 → tipo não vira contrato."""
        equipes = [self._mk_equipe("eap-Z")]
        sched = {"eap-Z": self._mk_sched("eap-Z", ["S001"])}
        rcpsp = {
            "resource_pool": {"ZERO": 1},
            "activities": [{"item_id": "eap-Z", "required_resources": {"ZERO": 0}}],
        }
        contratos, atrib, cadeias = _MOD._build_contratos_recurso(equipes, rcpsp, sched, [])
        assert contratos == []
        assert atrib == {}

    def test_tipo_costs_non_dict_normalized_to_empty(self):
        """Linha 1590: resource_costs[tipo] não é dict (payload malformado) —
        normalizado para {} em vez de propagar erro para _build_tipo_contrato."""
        equipes = [self._mk_equipe("eap-Y")]
        sched = {"eap-Y": self._mk_sched("eap-Y", ["S001", "S002"])}
        rcpsp = {
            "resource_pool": {"OPERADOR": 1},
            "activities": [{"item_id": "eap-Y", "required_resources": {"OPERADOR": 1}}],
            "resource_costs": {"OPERADOR": "nao-e-um-dict"},
        }
        contratos, atrib, cadeias = _MOD._build_contratos_recurso(equipes, rcpsp, sched, [])
        assert len(contratos) == 1
        assert contratos[0].tipo_id == "OPERADOR"


# ===========================================================================
# 43. _sucessor_critico_id / _impute_euler_regions (ADR-084)
# ===========================================================================


class TestSucessorCriticoId:
    def test_finds_first_activity_starting_at_or_after_gap_end(self):
        """Linha 1757: encontra a primeira atividade cujo T_start >= gap_end."""
        atividades_sorted = [
            {"item_id": "A", "T_start": 1.0},
            {"item_id": "B", "T_start": 5.0},
            {"item_id": "C", "T_start": 8.0},
        ]
        result = _MOD._sucessor_critico_id(4.0, atividades_sorted)
        assert result == "B"

    def test_returns_none_when_no_activity_starts_after_gap(self):
        atividades_sorted = [{"item_id": "A", "T_start": 1.0}]
        result = _MOD._sucessor_critico_id(10.0, atividades_sorted)
        assert result is None


class TestImputeEulerRegions:
    def test_skips_active_id_not_in_items_com_janela(self):
        """Linha 1774: região do diagrama de Euler referencia um item_id que não
        está em items_com_janela (fora da janela de análise) — é ignorado."""
        items_com_janela = [{"item_id": "A"}]
        region = SimpleNamespace(measure=lambda: 2.0)
        diagram = {frozenset({"A", "OUTSIDE"}): region}
        phi, custo_excl, custo_comp, overlap_sem = _MOD._impute_euler_regions(diagram, items_com_janela, 10.0, 1)
        assert set(phi.keys()) == {"A"}
        # custo = duracao(2.0) * c_unit_semana(10.0) * qt(1) = 20.0; dividido pelas
        # 2 ids ativas (A e OUTSIDE) -> parcela=10.0; OUTSIDE é ignorado (não em phi).
        assert phi["A"] == pytest.approx(10.0)


# ===========================================================================
# 44. ImportError fallback do eule/interval_sets (linhas 48-49)
# ===========================================================================


class TestEuleImportErrorFallback:
    def test_eule_unavailable_sets_flag_false(self):
        """Linhas 48-49: quando eule/interval_sets não estão instaláveis, o módulo
        define _EULE_AVAILABLE=False em vez de propagar o ImportError."""
        import importlib
        import sys as _sys

        real_import = __import__

        def _fake_import(name, *args, **kwargs):
            if name in ("eule", "interval_sets"):
                raise ImportError(f"simulado: {name} indisponível")
            return real_import(name, *args, **kwargs)

        mod_name = _MOD.__name__
        submod_name = f"{mod_name}._causal_cost_partition"
        saved = _sys.modules.pop(mod_name, None)
        saved_submod = _sys.modules.pop(submod_name, None)
        try:
            import builtins

            builtins.__import__ = _fake_import
            try:
                reloaded = importlib.import_module(mod_name)
            finally:
                builtins.__import__ = real_import
            assert reloaded._causal_cost_partition._EULE_AVAILABLE is False
        finally:
            if saved is not None:
                _sys.modules[mod_name] = saved
            else:
                _sys.modules.pop(mod_name, None)
            if saved_submod is not None:
                _sys.modules[submod_name] = saved_submod
            else:
                _sys.modules.pop(submod_name, None)
            importlib.import_module(mod_name)


# ===========================================================================
# 45. _build_dimensionamento — num_equipes_paralelas via assigned_resources /
#     fallback pela distribuicao_semanal (ADR-091)
# ===========================================================================


class TestBuildDimensionamentoNumEquipesParalelas:
    def _make_canonical(self, item_id="EAP-01", cpu_id="CPU-T"):
        from datetime import UTC, datetime

        from concilium.domain.models.canonical import (
            CanonicalModel,
            Coordenadas,
            EapItem,
            Meta,
            Praticabilidade,
            Projeto,
            RegimeTrabalho,
        )

        meta = Meta(gerado_em=datetime.now(UTC), contexto_id="test")
        proj = Projeto(
            id="p1",
            nome="proj",
            tipo_obra="terraplenagem",
            localizacao="x",
            coordenadas=Coordenadas(lat=0.0, lng=0.0),
            regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
            data_inicio="2026-06-01",
            data_termino="2026-07-31",
            snapshot_catalogo_id="s",
            snapshot_perfil_id="s",
        )
        prat = Praticabilidade(
            fonte="test",
            limiar_inviabilidade_mm=0,
            calculada_em=datetime.now(UTC),
            percentual_produtivo_mensal={"06": 1.0, "07": 1.0},
        )
        eap = [EapItem(item_id=item_id, ordem=1, cpu_id=cpu_id, descricao="Test", unidade="m3", quantitativo=100.0)]
        return CanonicalModel(meta=meta, projeto=proj, eap=eap, praticabilidade=prat)

    def _catalogo(self, cpu_id="CPU-T"):
        return {
            "cpus": [
                {
                    "codigo": cpu_id,
                    "descricao": "Test CPU",
                    "unidade": "m3",
                    "origem": "PROPRIA",
                    "categoria": "TERRAPLENAGEM",
                    "producao_horaria": 10,
                    "composicao_itens": [],
                    "composicao_padrao_equipe": {
                        "funcoes": [{"funcao_id": "OP-01", "num_pessoas": 1}],
                        "equipamentos": [{"equip_id": "EQ-01", "num_unidades": 1}],
                        "materiais": [],
                    },
                }
            ],
            "insumos": [
                {
                    "codigo": "OP-01",
                    "tipo": "MAO_OBRA",
                    "descricao": "Operador",
                    "unidade": "mes",
                    "preco_unitario": 2000.0,
                    "fonte_preco": "catalogo",
                    "atributos_especificos": {},
                },
                {
                    "codigo": "EQ-01",
                    "tipo": "EQUIPAMENTO",
                    "descricao": "Escavadeira",
                    "unidade": "h",
                    "preco_unitario": 100.0,
                    "fonte_preco": "catalogo",
                    "atributos_especificos": {},
                },
            ],
        }

    def test_assigned_resources_sum_gt1_skips_dist_fallback(self):
        """ADR-091: assigned_resources com soma > 1 já define num_equipes_paralelas
        > 1 — o bloco de dedução via distribuicao_semanal é pulado (branch False
        de `if not num_equipes_paralelas or num_equipes_paralelas == 1`)."""
        from concilium.application.skills import run_cronograma, run_equipes_e_alocacao

        item_id = "EAP-01"
        can = self._make_canonical(item_id=item_id)
        cat = self._catalogo()
        cron_inputs = {"num_equipes_por_item": {item_id: {"2026-W23": 1}}}
        can_cron = run_cronograma(can, cron_inputs, cat).canonical
        sa = can_cron.cronograma.scheduled_activities[0]
        sa.assigned_resources = {"EQ-01": 3}
        result = run_equipes_e_alocacao(can_cron, {"preco_diesel": 6.20}, cat)
        eq = result.canonical.equipes_diretas[0]
        assert eq.num_equipes_base == 3

    def test_dist_semanal_vazia_mantem_num_equipes_paralelas_1(self):
        """assigned_resources vazio (sum=1 default) e distribuicao_semanal vazia
        (falsy) — ramo False de `if dist_semanal and isinstance(dist_semanal, dict)`
        — num_equipes_paralelas permanece 1."""
        from concilium.application.skills import run_cronograma, run_equipes_e_alocacao

        item_id = "EAP-01"
        can = self._make_canonical(item_id=item_id)
        cat = self._catalogo()
        cron_inputs = {"num_equipes_por_item": {item_id: {"2026-W23": 1}}}
        can_cron = run_cronograma(can, cron_inputs, cat).canonical
        sa = can_cron.cronograma.scheduled_activities[0]
        sa.distribuicao_semanal = {}
        result = run_equipes_e_alocacao(can_cron, {"preco_diesel": 6.20}, cat)
        eq = result.canonical.equipes_diretas[0]
        assert eq.num_equipes_base == 1


# ===========================================================================
# 46. _tipo_recurso_fungivel (closure interna de _derive_rcpsp_from_canonical)
# ===========================================================================


class TestTipoRecursoFungivel:
    def _canonical_com_composicao(self, equipamentos, funcoes):
        dist = {"2026-W01": SimpleNamespace(num_equipes=1)}
        sched_act = SimpleNamespace(activity_id="ITEM-1", distribuicao_semanal=dist)
        canonical_in = SimpleNamespace(
            cronograma=SimpleNamespace(scheduled_activities=[sched_act]),
            eap=[SimpleNamespace(item_id="ITEM-1", cpu_id="CPU-1")],
        )
        catalogo = {
            "cpus": [{"codigo": "CPU-1", "producao_id_ref": "PROD-1"}],
            "producoes": [
                {
                    "id": "PROD-1",
                    "composicao_padrao_equipe": {"equipamentos": equipamentos, "funcoes": funcoes},
                }
            ],
        }
        return canonical_in, catalogo

    def test_tokens_com_ids_vazios_intercalados_continua_loop(self):
        """Funções/equipamentos com id vazio são ignorados mas o loop continua
        para os próximos — cobre os ramos `if fid:`/`if eid:` False seguidos de
        continuação (loops de tokens)."""
        funcoes = [{"funcao_id": None, "num_pessoas": 1}, {"funcao_id": "OP1", "num_pessoas": 2}]
        equipamentos = [{"equip_id": "", "num_unidades": 1}, {"equip_id": "EQ1", "num_unidades": 1}]
        canonical_in, catalogo = self._canonical_com_composicao(equipamentos, funcoes)
        result = _derive_rcpsp_from_canonical(canonical_in, catalogo)
        assert result is not None
        tipo = next(iter(result["resource_pool"].keys()))
        assert tipo.startswith("EQUIPE-COMP-")

    def test_todos_ids_vazios_cai_no_fallback_por_cpu_id(self):
        """Linhas 1464-1465: equipamentos/funcoes presentes mas todos com id vazio
        → tokens fica vazio → fallback usa cpu_id (`EQUIPE-CPU-<...>`)."""
        funcoes = [{"funcao_id": "", "num_pessoas": 1}]
        equipamentos = [{"equip_id": "", "num_unidades": 1}]
        canonical_in, catalogo = self._canonical_com_composicao(equipamentos, funcoes)
        result = _derive_rcpsp_from_canonical(canonical_in, catalogo)
        assert result is not None
        tipo = next(iter(result["resource_pool"].keys()))
        assert tipo == "EQUIPE-CPU-CPU-1"


# ===========================================================================
# 47. _build_item_tipo_map — ids/required_resources falsy intercalados
# ===========================================================================


class TestBuildItemTipoMap:
    def test_skips_falsy_and_continues_loop(self):
        """Atividades sem item_id ou sem required_resources são ignoradas, mas o
        loop continua e processa as atividades subsequentes normalmente."""
        activities = [
            {"item_id": None, "required_resources": {"A": 1}},
            {"item_id": "X", "required_resources": {}},
            {"item_id": "Y", "required_resources": {"B": 2}},
        ]
        result = _MOD._build_item_tipo_map(activities)
        assert result == {"Y": {"B": 2}}


# ===========================================================================
# 48. _build_contrato_entry — fallback de custo_idle quando cus_mo+cus_locacao<=0
# ===========================================================================


class TestBuildContratoEntryCIdleFallback:
    def _mk_sched(self, item_id, weeks):
        from concilium.domain.models.canonical import DistribuicaoSemanal, ScheduledActivityCanonical

        dist = {
            w: DistribuicaoSemanal(
                num_equipes=1,
                qtd_executada=10.0,
                qtd_acumulada=10.0,
                pct=1.0,
                eficiencia=1.0,
                fator_clima=1.0,
                fator_calendario=1.0,
            )
            for w in weeks
        }
        return ScheduledActivityCanonical(
            activity_id=item_id, start_week=0, end_week=len(weeks), duration_weeks=len(weeks), distribuicao_semanal=dist
        )

    def _mk_equipe(self, item_id, custo_total=0.0):
        from concilium.domain.models.canonical import EquipeDireta

        return EquipeDireta(
            equipe_id=f"eq-{item_id}",
            item_id=item_id,
            cpu_id="CPU-X",
            custo_mao_obra_mensal=100.0,
            custo_total=custo_total,
        )

    def test_c_idle_fallback_not_positive_stays_zero(self):
        """Quando custo_total do item é 0, cus_mo e cus_locacao ficam 0 — o
        fallback `_c_idle_fallback = cus_mo + cus_locacao` não é > 0, então
        c_idle permanece 0 (branch False de `if _c_idle_fallback > 0.0`)."""
        equipes = [self._mk_equipe("eap-W", custo_total=0.0)]
        sched = {"eap-W": self._mk_sched("eap-W", ["S001"])}
        rcpsp = {
            "resource_pool": {"OPERADOR": 1},
            "activities": [{"item_id": "eap-W", "required_resources": {"OPERADOR": 1}}],
        }
        contratos, atrib, cadeias = _MOD._build_contratos_recurso(equipes, rcpsp, sched, [])
        assert len(contratos) == 1
        assert contratos[0].custo_idle_semanal_unit == 0.0


# ===========================================================================
# 49. _impute_gaps — gap sem sucessor crítico (fim de contrato)
# ===========================================================================


@pytest.mark.skipif(not _MOD._EULE_AVAILABLE, reason="eule[interval] não instalado")
class TestImputeGapsSemSucessor:
    def test_gap_final_sem_sucessor_nao_e_imputado(self):
        """Gap após a última atividade não tem sucessor crítico (nenhuma atividade
        com T_start >= gap_end) — ramo False de `if critico_id and critico_id in phi`
        (a atribuição do custo do gap é pulada, mas o processamento continua)."""
        items = [{"item_id": "a1", "T_start": 0.0, "T_end": 3.0, "machine_weeks": 3}]
        atrib = {"a1": (0.0, "produtivo", 3.0)}
        result = _MOD.particionar_contrato(
            items_com_janela=items,
            c_mob=0.0,
            c_demob=0.0,
            c_unit_semana=1.0,
            quantidade_contratada=1,
            T_contrato_start=0.0,
            T_contrato_end=7.0,
            atribuicao=atrib,
            cadeias=[],
        )
        by_id = {it.item_id: it for it in result}
        # gap [3,7] não tem sucessor -> custo do gap não é imputado a ninguém
        assert by_id["a1"].custo_ocioso_imputado == 0.0


# ===========================================================================
# 50. _build_demand_per_week — demand arredondado para 0 é excluído
# ===========================================================================


class TestBuildDemandPerWeekDemandZero:
    def test_demand_rounds_to_zero_excluded(self):
        """ne > 0 mas demand arredondado para 0 (required pequeno vs total_peak) —
        ramo False de `if demand > 0`; a semana não entra no resultado."""
        d_tiny = SimpleNamespace(num_equipes=1)
        d_pos = SimpleNamespace(num_equipes=100)
        dist = {"S1": d_tiny, "S2": d_pos}
        result = _build_demand_per_week(dist, 1, 100)
        assert "S1" not in result
        assert result["S2"] == 1


# ===========================================================================
# 51. _build_instancias_for_tipo — early returns (n<=0 / items_data vazio)
# ===========================================================================


class TestBuildInstanciasForTipoEarlyReturns:
    def test_n_zero_or_negative_returns_empty(self):
        contrato = SimpleNamespace(quantidade_contratada=0)
        result = _MOD._build_instancias_for_tipo("T1", contrato, {}, {}, {}, [])
        assert result == ([], [], [])

    def test_items_data_empty_returns_empty(self):
        contrato = SimpleNamespace(quantidade_contratada=2)
        result = _MOD._build_instancias_for_tipo("T1", contrato, {}, {}, {}, [])
        assert result == ([], [], [])


# ===========================================================================
# 51b. _build_instancias_recurso — early return sem contratos/activities
# ===========================================================================


class TestBuildInstanciasRecursoEarlyReturn:
    def test_sem_contratos_retorna_listas_vazias(self):
        result = _MOD._build_instancias_recurso([], {"activities": [{"item_id": "x"}]}, {}, [])
        assert result == ([], [], [])

    def test_sem_activities_retorna_listas_vazias(self):
        contrato = SimpleNamespace(tipo_id="T1")
        result = _MOD._build_instancias_recurso([contrato], {"activities": []}, {}, [])
        assert result == ([], [], [])


# ===========================================================================
# 52. _reescalar_particao / _apply_instancial_to_contrato — casos vazios
# ===========================================================================


class TestReescalarParticaoEApplyInstancial:
    def test_reescalar_particao_sem_particoes_apenas_atualiza_total(self):
        """particao_por_item vazio → nada a reescalar, mas custo_total_contrato
        do contrato ainda é atualizado para o novo valor."""
        contrato = SimpleNamespace(custo_total_contrato=100.0, particao_por_item=[], tipo_id="T1")
        validacoes: list = []
        _MOD._reescalar_particao(contrato, 50.0, [], {}, validacoes)
        assert contrato.custo_total_contrato == 50.0
        assert validacoes == []

    def test_apply_instancial_novo_total_zero_e_no_op(self):
        """Sem instâncias associadas ao contrato, novo_total=0 → early return sem
        alterar custo_total_contrato nem emitir validações."""
        contrato = SimpleNamespace(contrato_id="C1", custo_total_contrato=100.0)
        validacoes: list = []
        _MOD._apply_instancial_to_contrato(contrato, [], {}, validacoes)
        assert contrato.custo_total_contrato == 100.0
        assert validacoes == []

    def test_apply_instancial_antigo_total_zero_e_no_op(self):
        """novo_total > 0 (há instâncias com custo), mas custo_total_contrato
        original é 0/None → segundo early return (`if antigo_total <= 0`)."""
        contrato = SimpleNamespace(contrato_id="C1", custo_total_contrato=0.0)
        inst = SimpleNamespace(contrato_id="C1", custo_instancia_total=500.0)
        validacoes: list = []
        _MOD._apply_instancial_to_contrato(contrato, [inst], {}, validacoes)
        assert contrato.custo_total_contrato == 0.0
        assert validacoes == []


# ===========================================================================
# 53. _enrich_equipes_com_decomposicao_instancial — casos de desvio/reescala
# ===========================================================================


class TestEnrichEquipesDecomposicaoInstancial:
    def test_contrato_sem_particoes_nao_gera_erro(self):
        """Loop `for part in contrato.particao_por_item` não é executado quando a
        lista está vazia — nenhuma equipe é tocada, nenhuma validação emitida."""
        contrato = SimpleNamespace(particao_por_item=[])
        validacoes: list = []
        _MOD._enrich_equipes_com_decomposicao_instancial([], [contrato], validacoes)
        assert validacoes == []

    def test_desvio_grande_soma_positiva_reescala_proporcionalmente(self):
        """desvio > 1.0 e soma > 0 → reescala custo_inst_* proporcionalmente e
        emite VAL-DECOMP-REESCALA. Usa dois contratos, o primeiro com uma
        partição de item sem equipe correspondente (cobre o `continue` do
        `if eq is None`) para exercitar a continuação dos loops aninhados
        (múltiplos contratos e múltiplas partições)."""
        from concilium.domain.models.canonical import CustoParticionadoItem, EquipeDireta

        eq = EquipeDireta(equipe_id="eq-A", item_id="A", cpu_id="CPU-X", custo_total=1000.0)
        part_sem_equipe = CustoParticionadoItem(item_id="ZZZ")
        contrato_sem_equipe = SimpleNamespace(particao_por_item=[part_sem_equipe])
        part = CustoParticionadoItem(item_id="A", custo_inst_mo=10.0)
        contrato = SimpleNamespace(particao_por_item=[part])
        validacoes: list = []
        _MOD._enrich_equipes_com_decomposicao_instancial([eq], [contrato_sem_equipe, contrato], validacoes)
        assert eq.custo_inst_mo == pytest.approx(1000.0)
        assert any(v.codigo == "VAL-DECOMP-REESCALA" for v in validacoes)

    def test_desvio_grande_soma_zero_emite_invariante_sem_reescalar(self):
        """desvio > 1.0 e soma <= 0 (todos custo_inst_* zerados) → não há como
        reescalar; emite VAL-DECOMP-INVARIANTE."""
        from concilium.domain.models.canonical import CustoParticionadoItem, EquipeDireta

        eq = EquipeDireta(equipe_id="eq-B", item_id="B", cpu_id="CPU-X", custo_total=50.0)
        part = CustoParticionadoItem(item_id="B")
        contrato = SimpleNamespace(particao_por_item=[part])
        validacoes: list = []
        _MOD._enrich_equipes_com_decomposicao_instancial([eq], [contrato], validacoes)
        assert eq.custo_inst_mo == 0.0
        assert any(v.codigo == "VAL-DECOMP-INVARIANTE" for v in validacoes)


# ===========================================================================
# 54. _enrich_particao_overhead (ADR-083) — gap real entre segmentos de slot
# ===========================================================================


class TestEnrichParticaoOverhead:
    def test_gap_entre_predecessor_e_sucessor_gera_overhead(self):
        """Item sem predecessor na cadeia não recebe overhead (continue); item
        com predecessor tem overhead_ocioso calculado a partir do gap real entre
        os segmentos de atividade do slot instancial."""
        from concilium.domain.models.canonical import CadeiaPerpetuacao, CustoParticionadoItem

        cadeia = CadeiaPerpetuacao(
            cadeia_id="c1", item_ids=["A", "B"], tipo_id="T1", semana_inicio="S001", semana_fim="S010"
        )
        part_a = CustoParticionadoItem(item_id="A")
        part_b = CustoParticionadoItem(item_id="B")
        contrato = SimpleNamespace(tipo_id="T1", custo_unit_semanal=10.0, particao_por_item=[part_a, part_b])
        inst = SimpleNamespace(
            tipo_id="T1",
            segmentos_atividade=[
                SimpleNamespace(activity_id="A", semana_inicio="S001", semana_fim="S003"),
                SimpleNamespace(activity_id="B", semana_inicio="S005", semana_fim="S007"),
            ],
        )
        _MOD._enrich_particao_overhead([contrato], [cadeia], [inst])
        assert part_a.custo_ocioso_imputado == 0.0
        # gap entre S003 (fim de A) e S005 (início de B) = 1 semana ociosa
        assert part_b.custo_ocioso_imputado == pytest.approx(10.0)


# ===========================================================================
# 55. _best_alias_equip_attrs — pontuação por descrição pulada quando vazia
# ===========================================================================


class TestBestAliasEquipAttrsDescVazia:
    def test_desc_key_ou_desc_i_vazio_pula_pontuacao_por_descricao(self):
        """Quando desc_key ou desc_i está vazio, o bloco de pontuação por
        descrição (linhas 270-278) é pulado — mas o score por codigo_planilha
        já é suficiente para ultrapassar o limiar de 35.0 (branch False de
        `if desc_key and desc_i`)."""
        ctx_repo = MagicMock()
        ctx_repo._insumos = {
            "EQ-01": {
                "tipo": "EQUIPAMENTO",
                "descricao": "",  # desc_i fica vazio após normalização
                "atributos_especificos": {
                    "codigo_planilha": "COD-01",
                    "consumo_litros_hora": 5.0,
                },
            }
        }
        ctx = SimpleNamespace(repo=ctx_repo)
        result = _MOD._best_alias_equip_attrs(ctx, "COD-01", "Alguma descricao")
        assert result["consumo_litros_hora"] == 5.0


# ===========================================================================
# 56. _scale_part_entry / _aplicar_custo_instancial — branches residuais
# ===========================================================================


class TestScalePartEntryNoMatchingEquipe:
    def test_item_id_sem_equipe_correspondente_nao_atualiza_custo_total(self):
        """eq_by_item.get(part.item_id) retorna None -> pula a atualização de
        eq.custo_total (branch False de `if eq is not None`)."""
        part = SimpleNamespace(
            item_id="ITEM-SEM-EQUIPE",
            custo_produtivo=100.0,
            custo_mob_imputado=0.0,
            custo_ocioso_imputado=0.0,
            overhead_ocioso=0.0,
            custo_produtivo_exclusivo=100.0,
            custo_produtivo_compartilhado=0.0,
            custo_demob_imputado=0.0,
            custo_total_particionado=100.0,
            custo_total_autonomo=100.0,
            custo_inst_mo=0.0,
            custo_inst_eq=0.0,
            custo_inst_comb=0.0,
            custo_inst_mat=0.0,
        )
        _MOD._scale_part_entry(part, 1.0, 100.0, 0.0, 0.0, 0.0, 0.0, eq_by_item={})
        assert part.custo_total_particionado == pytest.approx(100.0)


class TestAplicarCustoInstancialPoolTotalPorItem:
    def test_item_sem_equipe_ou_total_zero_nao_interrompe_loop(self):
        """Um item_id sem equipe correspondente (ou com total<=0) não deve
        impedir que o próximo item_id do loop seja processado normalmente
        (branch False de `if eq is not None and total > 0`, volta ao loop)."""
        part_sem_equipe = SimpleNamespace(item_id="ITEM-ORFAO", custo_total_particionado=50.0)
        part_com_equipe = SimpleNamespace(item_id="ITEM-OK", custo_total_particionado=200.0)
        contrato = SimpleNamespace(particao_por_item=[part_sem_equipe, part_com_equipe])
        eq_ok = SimpleNamespace(item_id="ITEM-OK", custo_total=0.0)

        with patch.object(_MOD._custo_instancial_composicional, "_apply_instancial_to_contrato", lambda *a, **k: None):
            _MOD._aplicar_custo_instancial([contrato], instancias=[], equipes=[eq_ok], validacoes=[])

        assert eq_ok.custo_total == pytest.approx(200.0)
