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

_MOD = sys.modules["_concilium_skillpkg_05_equipes_e_alocacao._skill_helpers_a"]

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
_resolve_custo_hora_ref_sem = _MOD._resolve_custo_hora_ref_sem
_resolve_prod_lookup = _MOD._resolve_prod_lookup
_calibrar_custos_por_cref = _MOD._calibrar_custos_por_cref
_build_perpetuation_chains = _MOD._build_perpetuation_chains
_build_predecessor_map = _MOD._build_predecessor_map
_init_item_float_maps = _MOD._init_item_float_maps
_compute_ocioso_para_item = _MOD._compute_ocioso_para_item
_compute_particao_por_tipo = _MOD._compute_particao_por_tipo
_compress_to_segments = _MOD._compress_to_segments
_compute_desmob_antecipada = _MOD._compute_desmob_antecipada
_build_demand_per_week = _MOD._build_demand_per_week
_build_item_resource_maps = _MOD._build_item_resource_maps
_sum_inst_categories = _MOD._sum_inst_categories
_last_week_idx_for_act = _MOD._last_week_idx_for_act
_first_week_idx_for_act = _MOD._first_week_idx_for_act
_compute_gap_for_inst = _MOD._compute_gap_for_inst


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

    def test_custo_com_encargos_precomputed(self):
        """atrib.custo_com_encargos > 0 → use that × (1+he_pct)."""
        atrib = {"custo_com_encargos": 4000.0}
        result = _resolve_custo_unit_funcao("clt", 3000.0, atrib, 0.70, 0.10)
        assert result == pytest.approx(4000.0 * 1.10)

    def test_inclui_encargos_nota(self):
        """Line 138: 'inclui encargos' in nota → salario × (1+he_pct) only."""
        atrib = {"nota": "taxa horaria — inclui encargos e beneficios"}
        result = _resolve_custo_unit_funcao("clt", 100.0, atrib, 0.70, 0.05)
        assert result == pytest.approx(100.0 * 1.05)

    def test_inclui_encargos_nota_encargos_field(self):
        """'inclui encargos' in nota_encargos field also triggers."""
        atrib = {"nota_encargos": "valor inclui encargos"}
        result = _resolve_custo_unit_funcao("clt", 100.0, atrib, 0.70, 0.0)
        assert result == pytest.approx(100.0)

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
        """Line 661: seq empty → 0."""
        cron = SimpleNamespace(distribuicao_semanal={})
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

    def test_invalid_iso_returns_zero(self):
        """Lines 993-996: bad ISO → 0."""
        idx = _week_idx("2026-WINVALID")
        assert idx == 0

    def test_numeric_string(self):
        assert _week_idx("10") == 10

    def test_invalid_string_returns_zero(self):
        """Lines 995-996: ValueError → 0."""
        assert _week_idx("abc") == 0

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
        _accum_week_demand(tipo_week_demand, "TIPO-A", ["S1"], dist, 1, 1)
        assert tipo_week_demand["TIPO-A"]["S1"] >= 1

    def test_accumulates_across_weeks(self):
        tipo_week_demand = {}
        d1 = SimpleNamespace(num_equipes=2)
        d2 = SimpleNamespace(num_equipes=3)
        dist = {"S1": d1, "S2": d2}
        _accum_week_demand(tipo_week_demand, "TIPO-A", ["S1", "S2"], dist, 1, 3)
        assert "S1" in tipo_week_demand["TIPO-A"]
        assert "S2" in tipo_week_demand["TIPO-A"]


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
# 30. _resolve_custo_hora_ref_sem
# ===========================================================================


class TestResolveCustoHoraRefSem:
    def test_no_cpu_lookup_returns_zero(self):
        """Line 1079: cpu_lookup is None → 0."""
        eq = SimpleNamespace(cpu_id="CPU-01")
        result = _resolve_custo_hora_ref_sem(eq, None, {}, 48.0)
        assert result == 0.0

    def test_cpu_not_found_returns_zero(self):
        """Line 1082: cpu not in lookup → 0."""
        eq = SimpleNamespace(cpu_id="MISSING")
        result = _resolve_custo_hora_ref_sem(eq, {}, {"PROD-1": {}}, 48.0)
        assert result == 0.0

    def test_no_prod_returns_zero(self):
        """Line 1082: prod not found → 0."""
        eq = SimpleNamespace(cpu_id="CPU-01")
        cpu_lookup = {"CPU-01": {"producao_id_ref": "MISSING-PROD"}}
        prod_lookup = {}
        result = _resolve_custo_hora_ref_sem(eq, cpu_lookup, prod_lookup, 48.0)
        assert result == 0.0

    def test_c_ref_zero_returns_zero(self):
        """c_ref == 0 → 0."""
        eq = SimpleNamespace(cpu_id="CPU-01")
        cpu_lookup = {"CPU-01": {"producao_id_ref": "PROD-1"}}
        prod_lookup = {"PROD-1": {"custo_hora_total_referencia": 0.0}}
        result = _resolve_custo_hora_ref_sem(eq, cpu_lookup, prod_lookup, 48.0)
        assert result == 0.0

    def test_valid_returns_product(self):
        """Line 1084: returns c_ref × horas_semana."""
        eq = SimpleNamespace(cpu_id="CPU-01")
        cpu_lookup = {"CPU-01": {"producao_id_ref": "PROD-1"}}
        prod_lookup = {"PROD-1": {"custo_hora_total_referencia": 10.0}}
        result = _resolve_custo_hora_ref_sem(eq, cpu_lookup, prod_lookup, 48.0)
        assert result == pytest.approx(480.0)


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
# 32. _calibrar_custos_por_cref
# ===========================================================================


class TestCalibrarCustosPorCref:
    def test_no_c_ref_returns_unchanged(self):
        """Lines 793-794: C_ref <= 0 → return as-is."""
        cpu = {"producao_id_ref": "P1"}
        prod_lookup = {"P1": {"custo_hora_total_referencia": 0.0}}
        result = _calibrar_custos_por_cref(cpu, prod_lookup, 8.0, 100.0, 70.0, 30.0, 50.0, 10.0)
        assert result == (100.0, 70.0, 30.0, 50.0, 10.0)

    def test_no_pu_total_returns_unchanged(self):
        """Lines 800-802: pu_total <= 0 → return as-is."""
        cpu = {
            "producao_id_ref": "P1",
            "precos_unitarios_sbdi": {"mo": 0.0, "equipamentos": 0.0, "diesel": 0.0},
        }
        prod_lookup = {"P1": {"custo_hora_total_referencia": 50.0}}
        result = _calibrar_custos_por_cref(cpu, prod_lookup, 8.0, 100.0, 70.0, 30.0, 50.0, 10.0)
        assert result == (100.0, 70.0, 30.0, 50.0, 10.0)

    def test_calibration_applied(self):
        """Lines 804-824: C_ref × horas decomposes correctly."""

        cpu = {
            "producao_id_ref": "P1",
            "precos_unitarios_sbdi": {"mo": 60.0, "equipamentos": 30.0, "diesel": 10.0},
        }
        prod_lookup = {"P1": {"custo_hora_total_referencia": 10.0}}
        horas_dia = 8.0
        result = _calibrar_custos_por_cref(cpu, prod_lookup, horas_dia, 6000.0, 2000.0, 4000.0, 3000.0, 1000.0)
        mo_cal, enc_cal, mo_base_cal, eq_cal, comb_cal = result
        assert mo_cal > 0
        assert eq_cal > 0
        assert comb_cal > 0
        # Proportional fractions: mo=60%, eq=30%, diesel=10%
        assert mo_cal > eq_cal > comb_cal


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
    def _make_inst(self, mo=0.0, eq=0.0, comb=0.0, mat=0.0, idle_mo=0.0, idle_eq=0.0, demob=0.0):
        return SimpleNamespace(
            custo_ativo_mo=mo,
            custo_ativo_eq=eq,
            custo_ativo_comb=comb,
            custo_ativo_mat=mat,
            custo_idle_mo=idle_mo,
            custo_idle_eq=idle_eq,
            custo_demob_instancia=demob,
        )

    def test_single_instance(self):
        inst = self._make_inst(mo=100.0, eq=200.0, comb=50.0, mat=10.0, idle_mo=20.0, idle_eq=30.0, demob=5.0)
        tot_mo, tot_eq, tot_comb, tot_mat = _sum_inst_categories([inst])
        assert tot_mo == pytest.approx(120.0)  # 100 + 20
        assert tot_eq == pytest.approx(235.0)  # 200 + 30 + 5
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
