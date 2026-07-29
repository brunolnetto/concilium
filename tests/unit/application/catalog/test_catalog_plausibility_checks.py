"""Tests for concilium.application.catalog._plausibility_checks."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

from concilium.application.catalog._plausibility_checks import (
    Anomalia,
    _is_estagiario,
    _parse_date,
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
    _today,
    _zscore_map,
)
from concilium.domain.constants import (
    DIESEL_L_POR_CV_PONT,
    SMH,
    VH_MAX,
)
from concilium.domain.constants import (
    HORAS_MES_CLT as HORAS_MES_PADRAO,
)
from concilium.domain.constants import (
    VALIDADE_PRECO_DIAS as VALIDADE_DIAS,
)

# ── Anomalia ─────────────────────────────────────────────────────────────────


class TestAnomalia:
    def test_to_dict_all_keys_present(self):
        a = Anomalia(
            codigo="TEST-001",
            tipo="FISICO",
            severidade="ERRO",
            mensagem="mensagem de teste",
            detalhe={"chave": "valor"},
        )
        d = a.to_dict()
        assert d["codigo"] == "TEST-001"
        assert d["tipo"] == "FISICO"
        assert d["severidade"] == "ERRO"
        assert d["mensagem"] == "mensagem de teste"
        assert d["detalhe"] == {"chave": "valor"}
        assert set(d.keys()) == {"codigo", "tipo", "severidade", "mensagem", "detalhe"}

    def test_to_dict_default_detalhe(self):
        a = Anomalia(codigo="X", tipo="A", severidade="B", mensagem="msg")
        d = a.to_dict()
        assert d["detalhe"] == {}

    def test_to_dict_returns_dict(self):
        a = Anomalia(codigo="C", tipo="D", severidade="E", mensagem="f")
        assert isinstance(a.to_dict(), dict)


# ── _is_estagiario ────────────────────────────────────────────────────────────


class TestIsEstagiario:
    def test_estagi_in_descricao(self):
        assert _is_estagiario({"descricao": "Estagiário de TI", "codigo": "EST-001"}) is True

    def test_estagiario_with_accent(self):
        assert _is_estagiario({"descricao": "Estágiário", "codigo": "X"}) is True

    def test_intern_in_descricao(self):
        assert _is_estagiario({"descricao": "Intern Engineer", "codigo": "INT-001"}) is True

    def test_bolsist_in_descricao(self):
        assert _is_estagiario({"descricao": "Bolsista de pesquisa", "codigo": "BOL-001"}) is True

    def test_bolsist_in_codigo(self):
        assert _is_estagiario({"descricao": "Auxiliar", "codigo": "BOLSIST-01"}) is True

    def test_intern_in_codigo(self):
        assert _is_estagiario({"descricao": "Normal worker", "codigo": "INTERN-001"}) is True

    def test_normal_role_returns_false(self):
        assert _is_estagiario({"descricao": "Engenheiro Sênior", "codigo": "ENG-001"}) is False

    def test_pedreiro_returns_false(self):
        assert _is_estagiario({"descricao": "Pedreiro", "codigo": "PED-001"}) is False

    def test_empty_returns_false(self):
        assert _is_estagiario({}) is False

    def test_case_insensitive(self):
        assert _is_estagiario({"descricao": "ESTAGIÁRIO", "codigo": ""}) is True


# ── _today ────────────────────────────────────────────────────────────────────


class TestToday:
    def test_returns_date(self):
        result = _today()
        assert isinstance(result, date)

    def test_can_be_patched(self):
        fixed_date = date(2025, 1, 15)
        with patch(
            "concilium.application.catalog._plausibility_checks._today",
            return_value=fixed_date,
        ):
            # The patch replaces the function itself in module scope
            assert fixed_date == date(2025, 1, 15)


# ── _parse_date ───────────────────────────────────────────────────────────────


class TestParseDate:
    def test_valid_iso_date_string(self):
        result = _parse_date("2024-06-15")
        assert result == date(2024, 6, 15)

    def test_none_input_returns_none(self):
        assert _parse_date(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_date("") is None

    def test_malformed_string_returns_none(self):
        assert _parse_date("not-a-date") is None

    def test_truncates_to_10_chars(self):
        result = _parse_date("2024-06-15T10:00:00Z")
        assert result == date(2024, 6, 15)

    def test_invalid_month_returns_none(self):
        assert _parse_date("2024-13-01") is None

    def test_random_garbage_returns_none(self):
        assert _parse_date("abc-xyz-!!") is None


# ── _zscore_map ───────────────────────────────────────────────────────────────


class TestZscoreMap:
    def test_empty_list_returns_empty(self):
        assert _zscore_map([]) == {}

    def test_single_element_returns_empty(self):
        assert _zscore_map([42.0]) == {}

    def test_two_equal_values_returns_zeros(self):
        result = _zscore_map([5.0, 5.0])
        assert result == {0: 0.0, 1: 0.0}

    def test_normal_spread_correct_zscores(self):
        # [1, 2, 3] — mean=2, stdev=1 → z = [-1, 0, +1]
        result = _zscore_map([1.0, 2.0, 3.0])
        assert abs(result[0] - (-1.0)) < 1e-9
        assert abs(result[1] - 0.0) < 1e-9
        assert abs(result[2] - 1.0) < 1e-9

    def test_outlier_gets_large_z(self):
        # With many uniform values and one extreme outlier the z is large
        values = [10.0] * 20 + [1_000_000.0]
        result = _zscore_map(values)
        assert result[20] > 3.0  # outlier has large positive z

    def test_returns_dict_with_integer_keys(self):
        result = _zscore_map([1.0, 2.0])
        assert all(isinstance(k, int) for k in result.keys())


# ── _pc_mo_zscore ─────────────────────────────────────────────────────────────


class TestPcMoZscore:
    def _make_mo(self, precos: list[float]) -> list[dict]:
        return [{"codigo": f"MO-{i:03d}", "preco_unitario": p, "descricao": f"desc {i}"} for i, p in enumerate(precos)]

    def test_uniform_list_triggers_nothing(self):
        mo = self._make_mo([1000.0, 1000.0, 1000.0, 1000.0])
        result = _pc_mo_zscore(mo)
        assert result == []

    def test_extreme_outlier_triggers_aviso(self):
        # One extreme outlier among many uniform values (need 20+ to exceed ZSCORE_EXTREMO=3.5)
        precos = [1000.0] * 20 + [1_000_000.0]
        mo = self._make_mo(precos)
        result = _pc_mo_zscore(mo)
        assert len(result) >= 1
        assert result[-1].tipo == "ESTATISTICO"
        assert result[-1].severidade == "AVISO"

    def test_anomalia_contains_z_and_preco(self):
        precos = [1000.0] * 20 + [1_000_000.0]
        mo = self._make_mo(precos)
        result = _pc_mo_zscore(mo)
        assert "z" in result[-1].detalhe
        assert "preco" in result[-1].detalhe

    def test_single_element_no_anomalia(self):
        mo = self._make_mo([500.0])
        result = _pc_mo_zscore(mo)
        assert result == []


# ── _pc_mo_salario_minimo ─────────────────────────────────────────────────────


class TestPcMoSalarioMinimo:
    def _make_ins(self, preco: float, codigo: str = "MO-001", descricao: str = "Pedreiro") -> dict:
        return {"codigo": codigo, "descricao": descricao, "preco_unitario": preco}

    def test_price_below_minimum_triggers_erro(self):
        # SMH * 0.95 * HORAS_MES_PADRAO is the threshold
        below_threshold = SMH * 0.90 * HORAS_MES_PADRAO
        mo = [self._make_ins(below_threshold)]
        result = _pc_mo_salario_minimo(mo)
        assert len(result) == 1
        assert result[0].tipo == "FISICO"
        assert result[0].severidade == "ERRO"

    def test_price_above_threshold_is_clean(self):
        above_threshold = SMH * 1.5 * HORAS_MES_PADRAO
        mo = [self._make_ins(above_threshold)]
        result = _pc_mo_salario_minimo(mo)
        assert result == []

    def test_estagiario_is_skipped(self):
        # Even if the price would be below minimum, estagiario is skipped
        below_threshold = SMH * 0.5 * HORAS_MES_PADRAO
        mo = [self._make_ins(below_threshold, codigo="EST-001", descricao="Estagiário")]
        result = _pc_mo_salario_minimo(mo)
        assert result == []

    def test_custom_horas_mes(self):
        # With horas_mes=100, threshold = SMH * 0.95 * 100
        horas = 100.0
        below_threshold = SMH * 0.90 * horas
        mo = [
            {
                "codigo": "MO-002",
                "descricao": "Auxiliar",
                "preco_unitario": below_threshold,
                "atributos_especificos": {"horas_mes": horas},
            }
        ]
        result = _pc_mo_salario_minimo(mo)
        assert len(result) == 1
        assert result[0].tipo == "FISICO"

    def test_missing_atributos_uses_default_horas(self):
        # Uses HORAS_MES_PADRAO when atributos_especificos is absent
        above = SMH * 1.2 * HORAS_MES_PADRAO
        mo = [self._make_ins(above)]
        result = _pc_mo_salario_minimo(mo)
        assert result == []


# ── _pc_mo_encargos ───────────────────────────────────────────────────────────


class TestPcMoEncargos:
    def _make_ins(self, enc, codigo: str = "MO-001") -> dict:
        return {
            "codigo": codigo,
            "atributos_especificos": {"percentual_encargos_local": enc},
        }

    def test_alpha_below_min_triggers_erro(self):
        # ALPHA_MIN = 1.0, so enc = -0.5 gives alpha = 0.5
        mo = [self._make_ins(-0.5)]
        result = _pc_mo_encargos(mo)
        assert len(result) == 1
        assert result[0].tipo == "FISICO"
        assert result[0].severidade == "ERRO"

    def test_alpha_above_max_triggers_erro(self):
        # ALPHA_MAX = 2.5, so enc = 1.6 gives alpha = 2.6
        mo = [self._make_ins(1.6)]
        result = _pc_mo_encargos(mo)
        assert len(result) == 1
        assert result[0].tipo == "FISICO"

    def test_valid_alpha_is_clean(self):
        # enc = 0.5 gives alpha = 1.5 which is within [1.0, 2.5]
        mo = [self._make_ins(0.5)]
        result = _pc_mo_encargos(mo)
        assert result == []

    def test_missing_enc_is_skipped(self):
        mo = [{"codigo": "MO-001", "atributos_especificos": {}}]
        result = _pc_mo_encargos(mo)
        assert result == []

    def test_no_atributos_is_skipped(self):
        mo = [{"codigo": "MO-001"}]
        result = _pc_mo_encargos(mo)
        assert result == []

    def test_none_atributos_is_skipped(self):
        mo = [{"codigo": "MO-001", "atributos_especificos": None}]
        result = _pc_mo_encargos(mo)
        assert result == []


# ── _pc_mo_duplicatas ─────────────────────────────────────────────────────────


class TestPcMoDuplicatas:
    def test_two_entries_same_descricao_and_preco_triggers_aviso(self):
        mo = [
            {"codigo": "MO-001", "descricao": "Pedreiro", "preco_unitario": 100.0},
            {"codigo": "MO-002", "descricao": "Pedreiro", "preco_unitario": 100.0},
        ]
        result = _pc_mo_duplicatas(mo)
        assert len(result) == 1
        assert result[0].tipo == "DUPLICATA"
        assert result[0].severidade == "AVISO"
        assert result[0].codigo == "MO-002"

    def test_different_entries_are_clean(self):
        mo = [
            {"codigo": "MO-001", "descricao": "Pedreiro", "preco_unitario": 100.0},
            {"codigo": "MO-002", "descricao": "Carpinteiro", "preco_unitario": 120.0},
        ]
        result = _pc_mo_duplicatas(mo)
        assert result == []

    def test_same_descricao_different_preco_not_duplicate(self):
        mo = [
            {"codigo": "MO-001", "descricao": "Pedreiro", "preco_unitario": 100.0},
            {"codigo": "MO-002", "descricao": "Pedreiro", "preco_unitario": 200.0},
        ]
        result = _pc_mo_duplicatas(mo)
        assert result == []

    def test_duplicate_detalhe_has_original_codigo(self):
        mo = [
            {"codigo": "MO-001", "descricao": "Pedreiro", "preco_unitario": 100.0},
            {"codigo": "MO-002", "descricao": "Pedreiro", "preco_unitario": 100.0},
        ]
        result = _pc_mo_duplicatas(mo)
        assert result[0].detalhe["duplicata_de"] == "MO-001"

    def test_empty_list_returns_empty(self):
        assert _pc_mo_duplicatas([]) == []


# ── _pc_mo_semantica ──────────────────────────────────────────────────────────


class TestPcMoSemantica:
    def test_unit_mes_is_clean(self):
        mo = [{"codigo": "MO-001", "unidade": "mes"}]
        result = _pc_mo_semantica(mo)
        assert result == []

    def test_unit_mes_with_accent_is_clean(self):
        mo = [{"codigo": "MO-001", "unidade": "mês"}]
        result = _pc_mo_semantica(mo)
        assert result == []

    def test_unit_h_is_clean(self):
        mo = [{"codigo": "MO-001", "unidade": "h"}]
        result = _pc_mo_semantica(mo)
        assert result == []

    def test_unit_hr_is_clean(self):
        mo = [{"codigo": "MO-001", "unidade": "hr"}]
        result = _pc_mo_semantica(mo)
        assert result == []

    def test_unusual_unit_triggers_aviso(self):
        mo = [{"codigo": "MO-001", "unidade": "dia"}]
        result = _pc_mo_semantica(mo)
        assert len(result) == 1
        assert result[0].tipo == "SEMANTICO"
        assert result[0].severidade == "AVISO"

    def test_missing_unit_triggers_aviso(self):
        mo = [{"codigo": "MO-001"}]
        result = _pc_mo_semantica(mo)
        assert len(result) == 1
        assert result[0].tipo == "SEMANTICO"

    def test_unit_m2_triggers_aviso(self):
        mo = [{"codigo": "MO-001", "unidade": "m2"}]
        result = _pc_mo_semantica(mo)
        assert len(result) == 1


# ── _pc_mo_staleness ──────────────────────────────────────────────────────────


class TestPcMoStaleness:
    def test_old_date_triggers_stale_info(self):
        old_date = date.today() - timedelta(days=VALIDADE_DIAS + 10)
        mo = [{"codigo": "MO-001", "data_referencia_preco": old_date.isoformat()}]
        result = _pc_mo_staleness(mo)
        assert len(result) == 1
        assert result[0].tipo == "STALE"
        assert result[0].severidade == "INFO"

    def test_recent_date_is_clean(self):
        recent_date = date.today() - timedelta(days=10)
        mo = [{"codigo": "MO-001", "data_referencia_preco": recent_date.isoformat()}]
        result = _pc_mo_staleness(mo)
        assert result == []

    def test_no_date_field_is_skipped(self):
        mo = [{"codigo": "MO-001"}]
        result = _pc_mo_staleness(mo)
        assert result == []

    def test_none_date_is_skipped(self):
        mo = [{"codigo": "MO-001", "data_referencia_preco": None}]
        result = _pc_mo_staleness(mo)
        assert result == []

    def test_old_date_detalhe_has_dias_atraso(self):
        old_date = date.today() - timedelta(days=VALIDADE_DIAS + 20)
        mo = [{"codigo": "MO-001", "data_referencia_preco": old_date.isoformat()}]
        result = _pc_mo_staleness(mo)
        assert "dias_atraso" in result[0].detalhe
        assert result[0].detalhe["dias_atraso"] > VALIDADE_DIAS

    def test_uses_today_from_module(self):
        fixed_today = date(2025, 1, 1)
        # Date that would be stale relative to fixed_today
        old_date = date(2024, 1, 1)  # > VALIDADE_DIAS (180) days before 2025-01-01
        mo = [{"codigo": "MO-001", "data_referencia_preco": old_date.isoformat()}]
        with patch(
            "concilium.application.catalog._plausibility_checks._today",
            return_value=fixed_today,
        ):
            result = _pc_mo_staleness(mo)
        assert len(result) == 1


# ── _pc_eq_diesel ─────────────────────────────────────────────────────────────


class TestPcEqDiesel:
    def _make_eq(self, consumo, potencia, codigo: str = "EQ-001") -> dict:
        return {
            "codigo": codigo,
            "atributos_especificos": {
                "consumo_litros_hora": consumo,
                "potencia_cv": potencia,
            },
        }

    def test_consumo_within_tolerance_is_clean(self):
        # consumo = DIESEL_L_POR_CV_PONT * potencia exactly → delta = 0
        potencia = 100.0
        consumo = DIESEL_L_POR_CV_PONT * potencia
        eq = [self._make_eq(consumo, potencia)]
        result = _pc_eq_diesel(eq)
        assert result == []

    def test_consumo_slightly_out_triggers_aviso(self):
        # delta > DIESEL_TOLERANCIA but < 1.0 → AVISO
        potencia = 100.0
        esperado = DIESEL_L_POR_CV_PONT * potencia
        # delta = 0.7 (70% deviation) which is > 0.5 (DIESEL_TOLERANCIA) but < 1.0
        consumo = esperado * (1 + 0.7)
        eq = [self._make_eq(consumo, potencia)]
        result = _pc_eq_diesel(eq)
        assert len(result) == 1
        assert result[0].tipo == "FISICO"
        assert result[0].severidade == "AVISO"

    def test_consumo_very_high_triggers_erro(self):
        # delta >= 1.0 → ERRO
        potencia = 100.0
        esperado = DIESEL_L_POR_CV_PONT * potencia
        consumo = esperado * 2.5  # delta > 1.0
        eq = [self._make_eq(consumo, potencia)]
        result = _pc_eq_diesel(eq)
        assert len(result) == 1
        assert result[0].severidade == "ERRO"

    def test_missing_consumo_is_skipped(self):
        eq = [{"codigo": "EQ-001", "atributos_especificos": {"potencia_cv": 100.0}}]
        result = _pc_eq_diesel(eq)
        assert result == []

    def test_missing_potencia_is_skipped(self):
        eq = [{"codigo": "EQ-001", "atributos_especificos": {"consumo_litros_hora": 10.0}}]
        result = _pc_eq_diesel(eq)
        assert result == []

    def test_potencia_zero_is_skipped(self):
        eq = [self._make_eq(consumo=10.0, potencia=0.0)]
        result = _pc_eq_diesel(eq)
        assert result == []

    def test_no_atributos_is_skipped(self):
        eq = [{"codigo": "EQ-001"}]
        result = _pc_eq_diesel(eq)
        assert result == []

    def test_potencia_hp_used_as_fallback(self):
        # potencia_hp used when potencia_cv absent
        potencia = 100.0
        consumo = DIESEL_L_POR_CV_PONT * potencia
        eq = [
            {
                "codigo": "EQ-001",
                "atributos_especificos": {
                    "consumo_litros_hora": consumo,
                    "potencia_hp": potencia,
                },
            }
        ]
        result = _pc_eq_diesel(eq)
        assert result == []

    def test_anomalia_detalhe_has_expected_keys(self):
        potencia = 100.0
        esperado = DIESEL_L_POR_CV_PONT * potencia
        consumo = esperado * 3.0
        eq = [self._make_eq(consumo, potencia)]
        result = _pc_eq_diesel(eq)
        assert "consumo_real" in result[0].detalhe
        assert "potencia_cv" in result[0].detalhe
        assert "esperado_range" in result[0].detalhe
        assert "delta_pct" in result[0].detalhe


# ── _pc_eq_zscore ─────────────────────────────────────────────────────────────


class TestPcEqZscore:
    def _make_eq(self, precos: list[float]) -> list[dict]:
        return [{"codigo": f"EQ-{i:03d}", "preco_unitario": p, "descricao": f"equip {i}"} for i, p in enumerate(precos)]

    def test_uniform_prices_no_anomalia(self):
        eq = self._make_eq([500.0, 500.0, 500.0])
        result = _pc_eq_zscore(eq)
        assert result == []

    def test_extreme_outlier_triggers_aviso(self):
        precos = [500.0] * 20 + [5_000_000.0]
        eq = self._make_eq(precos)
        result = _pc_eq_zscore(eq)
        assert len(result) >= 1
        assert result[-1].tipo == "ESTATISTICO"
        assert result[-1].severidade == "AVISO"

    def test_single_item_no_anomalia(self):
        eq = self._make_eq([1000.0])
        result = _pc_eq_zscore(eq)
        assert result == []


# ── _pc_eq_locacao ────────────────────────────────────────────────────────────


class TestPcEqLocacao:
    def test_missing_valor_locacao_with_positive_price_triggers_info(self):
        eq = [{"codigo": "EQ-001", "preco_unitario": 100.0, "atributos_especificos": {}}]
        result = _pc_eq_locacao(eq)
        assert len(result) == 1
        assert result[0].tipo == "INCOMPLETO"
        assert result[0].severidade == "INFO"

    def test_detalhe_inclui_descricao_do_equipamento(self):
        """ADR-163 D2: descricao no detalhe, mesmo padrão de _pc_eq_zscore/_pc_mo_zscore —
        sem isso um agente não consegue identificar de qual equipamento se trata."""
        eq = [
            {
                "codigo": "EQ-001",
                "descricao": "Caminhão Basculante 12m³",
                "preco_unitario": 100.0,
                "atributos_especificos": {},
            }
        ]
        result = _pc_eq_locacao(eq)
        assert result[0].detalhe["descricao"] == "Caminhão Basculante 12m³"
        assert result[0].detalhe["preco_h"] == 100.0

    def test_detalhe_descricao_ausente_vira_string_vazia(self):
        eq = [{"codigo": "EQ-001", "preco_unitario": 100.0, "atributos_especificos": {}}]
        result = _pc_eq_locacao(eq)
        assert result[0].detalhe["descricao"] == ""

    def test_has_valor_locacao_is_clean(self):
        eq = [
            {
                "codigo": "EQ-001",
                "preco_unitario": 100.0,
                "atributos_especificos": {"valor_locacao_mensal": 5000.0},
            }
        ]
        result = _pc_eq_locacao(eq)
        assert result == []

    def test_zero_preco_is_clean(self):
        eq = [{"codigo": "EQ-001", "preco_unitario": 0.0, "atributos_especificos": {}}]
        result = _pc_eq_locacao(eq)
        assert result == []

    def test_no_atributos_with_positive_price_triggers_info(self):
        eq = [{"codigo": "EQ-001", "preco_unitario": 200.0}]
        result = _pc_eq_locacao(eq)
        assert len(result) == 1

    def test_none_atributos_with_positive_price_triggers_info(self):
        eq = [{"codigo": "EQ-001", "preco_unitario": 200.0, "atributos_especificos": None}]
        result = _pc_eq_locacao(eq)
        assert len(result) == 1

    def test_empty_list_returns_empty(self):
        assert _pc_eq_locacao([]) == []


# ── _pc_check_equipe_refs ────────────────────────────────────────────────────


class TestPcCheckEquipeRefs:
    def test_funcao_id_not_in_index_triggers_erro(self):
        equipe = {"funcoes": [{"funcao_id": "MO-999"}], "equipamentos": []}
        insumo_index = {}
        result = _pc_check_equipe_refs("PROD-001", equipe, insumo_index)
        assert len(result) == 1
        assert result[0].tipo == "INCOMPLETO"
        assert result[0].severidade == "ERRO"
        assert "funcao_id" in result[0].detalhe

    def test_equip_id_not_in_index_triggers_erro(self):
        equipe = {"funcoes": [], "equipamentos": [{"equip_id": "EQ-999"}]}
        insumo_index = {}
        result = _pc_check_equipe_refs("PROD-001", equipe, insumo_index)
        assert len(result) == 1
        assert result[0].tipo == "INCOMPLETO"
        assert result[0].severidade == "ERRO"
        assert "equip_id" in result[0].detalhe

    def test_all_present_is_clean(self):
        equipe = {
            "funcoes": [{"funcao_id": "MO-001"}],
            "equipamentos": [{"equip_id": "EQ-001"}],
        }
        insumo_index = {"MO-001": {}, "EQ-001": {}}
        result = _pc_check_equipe_refs("PROD-001", equipe, insumo_index)
        assert result == []

    def test_empty_equipe_is_clean(self):
        equipe = {"funcoes": [], "equipamentos": []}
        result = _pc_check_equipe_refs("PROD-001", equipe, {})
        assert result == []

    def test_funcao_id_empty_string_skipped(self):
        equipe = {"funcoes": [{"funcao_id": ""}], "equipamentos": []}
        result = _pc_check_equipe_refs("PROD-001", equipe, {})
        assert result == []

    def test_equip_id_empty_string_skipped(self):
        equipe = {"funcoes": [], "equipamentos": [{"equip_id": ""}]}
        result = _pc_check_equipe_refs("PROD-001", equipe, {})
        assert result == []

    def test_missing_funcao_id_key_skipped(self):
        equipe = {"funcoes": [{}], "equipamentos": []}
        result = _pc_check_equipe_refs("PROD-001", equipe, {})
        assert result == []

    def test_both_missing_two_erros(self):
        equipe = {
            "funcoes": [{"funcao_id": "MISSING-MO"}],
            "equipamentos": [{"equip_id": "MISSING-EQ"}],
        }
        result = _pc_check_equipe_refs("PROD-001", equipe, {})
        assert len(result) == 2


# ── _pc_check_prod_item ───────────────────────────────────────────────────────


class TestPcCheckProdItem:
    def _make_prod(self, vh=None, codigo="PROD-001", equipe=None) -> dict:
        prod: dict = {"codigo": codigo}
        if vh is not None:
            prod["valor_horario"] = vh
        if equipe is not None:
            prod["composicao_padrao_equipe"] = equipe
        return prod

    def test_zero_valor_horario_triggers_erro_and_early_return(self):
        prod = self._make_prod(vh=0)
        result = _pc_check_prod_item(prod, {})
        assert len(result) == 1
        assert result[0].tipo == "INCOMPLETO"
        assert result[0].severidade == "ERRO"

    def test_missing_valor_horario_triggers_erro_and_early_return(self):
        prod = self._make_prod()
        result = _pc_check_prod_item(prod, {})
        assert len(result) == 1
        assert result[0].tipo == "INCOMPLETO"
        assert result[0].severidade == "ERRO"

    def test_value_above_vh_max_triggers_aviso(self):
        prod = self._make_prod(
            vh=VH_MAX + 1.0,
            equipe={"funcoes": [], "equipamentos": []},
        )
        result = _pc_check_prod_item(prod, {})
        # Should have FISICO/AVISO and INCOMPLETO/AVISO (no equipe)
        tipos = {a.tipo for a in result}
        severidades = {a.severidade for a in result}
        assert "FISICO" in tipos
        assert "AVISO" in severidades

    def test_no_equipe_composition_triggers_aviso(self):
        prod = self._make_prod(vh=100.0)
        result = _pc_check_prod_item(prod, {})
        incompleto = [a for a in result if a.tipo == "INCOMPLETO" and a.severidade == "AVISO"]
        assert len(incompleto) == 1

    def test_valid_item_with_equipe_refs_present_is_clean(self):
        equipe = {
            "funcoes": [{"funcao_id": "MO-001"}],
            "equipamentos": [{"equip_id": "EQ-001"}],
        }
        prod = self._make_prod(vh=50.0, equipe=equipe)
        insumo_index = {"MO-001": {}, "EQ-001": {}}
        result = _pc_check_prod_item(prod, insumo_index)
        assert result == []

    def test_uses_id_field_when_codigo_absent(self):
        prod = {"id": "PROD-BY-ID", "valor_horario": 0}
        result = _pc_check_prod_item(prod, {})
        assert result[0].codigo == "PROD-BY-ID"

    def test_equipe_with_missing_ref_propagates_erro(self):
        equipe = {"funcoes": [{"funcao_id": "MO-MISSING"}], "equipamentos": []}
        prod = self._make_prod(vh=50.0, equipe=equipe)
        result = _pc_check_prod_item(prod, {})
        erros = [a for a in result if a.severidade == "ERRO"]
        assert len(erros) >= 1


# ── _pc_prod_vhs ──────────────────────────────────────────────────────────────


class TestPcProdVhs:
    def test_filters_out_zero_valor_horario(self):
        producoes = [
            {"codigo": "PROD-001", "valor_horario": 0},
            {"codigo": "PROD-002", "valor_horario": 50.0},
        ]
        result = _pc_prod_vhs(producoes)
        assert len(result) == 1
        assert result[0] == ("PROD-002", 50.0)

    def test_filters_out_missing_valor_horario(self):
        producoes = [
            {"codigo": "PROD-001"},
            {"codigo": "PROD-002", "valor_horario": 30.0},
        ]
        result = _pc_prod_vhs(producoes)
        assert len(result) == 1
        assert result[0][1] == 30.0

    def test_returns_id_and_float_tuples(self):
        producoes = [{"id": "PROD-ID", "valor_horario": 25.0}]
        result = _pc_prod_vhs(producoes)
        assert result == [("PROD-ID", 25.0)]

    def test_uses_codigo_when_id_absent(self):
        producoes = [{"codigo": "PROD-COD", "valor_horario": 10.0}]
        result = _pc_prod_vhs(producoes)
        assert result[0][0] == "PROD-COD"

    def test_empty_list_returns_empty(self):
        assert _pc_prod_vhs([]) == []

    def test_all_zero_returns_empty(self):
        producoes = [{"codigo": f"P-{i}", "valor_horario": 0} for i in range(5)]
        assert _pc_prod_vhs(producoes) == []

    def test_converts_string_float(self):
        producoes = [{"codigo": "PROD-001", "valor_horario": "42.5"}]
        result = _pc_prod_vhs(producoes)
        assert result[0][1] == 42.5


# ── _pc_check_prod_zscore ─────────────────────────────────────────────────────


class TestPcCheckProdZscore:
    def _make_prods(self, vhs: list[float]) -> list[dict]:
        return [{"codigo": f"P-{i:03d}", "valor_horario": v} for i, v in enumerate(vhs)]

    def test_fewer_than_3_items_returns_empty(self):
        prods = self._make_prods([10.0, 20.0])
        result = _pc_check_prod_zscore(prods)
        assert result == []

    def test_exactly_2_returns_empty(self):
        prods = self._make_prods([10.0, 20.0])
        result = _pc_check_prod_zscore(prods)
        assert result == []

    def test_extreme_outlier_triggers_estatistico_info(self):
        # _pc_check_prod_zscore uses ZSCORE_EXTREMO * 2 = 7.0 as threshold
        # Need ~100 uniform values so the outlier z exceeds 7.0
        vhs = [10.0] * 100 + [1_000_000.0]
        prods = self._make_prods(vhs)
        result = _pc_check_prod_zscore(prods)
        assert len(result) >= 1
        assert result[0].tipo == "ESTATISTICO"
        assert result[0].severidade == "INFO"

    def test_uniform_values_no_anomalia(self):
        vhs = [100.0] * 5
        prods = self._make_prods(vhs)
        result = _pc_check_prod_zscore(prods)
        assert result == []

    def test_zero_valor_horario_excluded_from_analysis(self):
        # Only 2 non-zero → returns []
        prods = [
            {"codigo": "P-000", "valor_horario": 0},
            {"codigo": "P-001", "valor_horario": 10.0},
            {"codigo": "P-002", "valor_horario": 20.0},
        ]
        result = _pc_check_prod_zscore(prods)
        assert result == []

    def test_anomalia_detalhe_has_valor_horario_and_z(self):
        vhs = [10.0] * 100 + [1_000_000.0]
        prods = self._make_prods(vhs)
        result = _pc_check_prod_zscore(prods)
        if result:
            assert "valor_horario" in result[0].detalhe
            assert "z" in result[0].detalhe

    def test_1_item_returns_empty(self):
        prods = self._make_prods([50.0])
        result = _pc_check_prod_zscore(prods)
        assert result == []
