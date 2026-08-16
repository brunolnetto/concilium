"""Coverage tests for pure helper functions in skill 04-cronograma/skill.py.

Import strategy: use `from concilium.application.skills import run_cronograma`
so that coverage.py can track the real module (_concilium_skillpkg_04_cronograma.skill).
All patches must reference _MOD_NAME so they target the correct namespace.
"""

import sys
from datetime import date, timedelta

import pytest

_MOD_NAME = "_concilium_skillpkg_04_cronograma.skill"
_MOD = sys.modules[_MOD_NAME]

_iso_week_key = _MOD._iso_week_key
_week_offset = _MOD._week_offset
_semanas_entre = _MOD._semanas_entre
_event_occurs_on_day = _MOD._event_occurs_on_day
_build_fator_calendario_semanal = _MOD._build_fator_calendario_semanal
_week_to_month = _MOD._week_to_month
_infer_teams_from_resources = _MOD._infer_teams_from_resources
_find_item_by_id = _MOD._find_item_by_id
_compute_ramp_profile = _MOD._compute_ramp_profile
_mean_praticabilidade = _MOD._mean_praticabilidade
_build_cpu_lookup = _MOD._build_cpu_lookup
_build_producao_lookup = _MOD._build_producao_lookup
_build_insumos_lookup = _MOD._build_insumos_lookup
_custo_hora_equipe = _MOD._custo_hora_equipe


# ===========================================================================
# _iso_week_key
# ===========================================================================


class TestIsoWeekKey:
    def test_monday_of_known_week(self):
        # 2024-W01 Monday is 2024-01-01
        d = date(2024, 1, 1)
        assert _iso_week_key(d) == "2024-W01"

    def test_mid_week(self):
        d = date(2024, 3, 15)  # Friday, 2024-W11
        assert _iso_week_key(d) == "2024-W11"

    def test_end_of_year_iso_week(self):
        # 2020-12-31 belongs to 2020-W53
        d = date(2020, 12, 31)
        key = _iso_week_key(d)
        assert key.startswith("2020-W")

    def test_format_has_two_digit_week(self):
        d = date(2025, 1, 6)  # first week of 2025
        key = _iso_week_key(d)
        assert "-W" in key
        _, wpart = key.split("-W")
        assert len(wpart) == 2


# ===========================================================================
# _week_offset
# ===========================================================================


class TestWeekOffset:
    def _make_semanas(self, start: date, n: int):
        semanas = []
        seen = set()
        d = start
        while len(semanas) < n:
            key = _iso_week_key(d)
            if key not in seen:
                seen.add(key)
                semanas.append(key)
            d += timedelta(days=7)
        return semanas

    def test_present_in_list_returns_index(self):
        start = date(2025, 1, 6)
        semanas = self._make_semanas(start, 5)
        for i, key in enumerate(semanas):
            assert _week_offset(key, semanas, start) == i

    def test_not_in_list_arithmetic_fallback(self):
        start = date(2025, 1, 6)
        semanas = self._make_semanas(start, 4)
        # Week 5 (not in list)
        future_monday = start + timedelta(weeks=10)
        key = _iso_week_key(future_monday)
        result = _week_offset(key, semanas, start)
        assert result == 10

    def test_not_in_list_before_start_clamps_to_zero(self):
        start = date(2025, 6, 2)
        semanas = self._make_semanas(start, 3)
        # A week before start
        past_monday = start - timedelta(weeks=2)
        key = _iso_week_key(past_monday)
        # Remove it from semanas just in case
        semanas_filtered = [s for s in semanas if s != key]
        result = _week_offset(key, semanas_filtered, start)
        assert result == 0  # max(0, negative) -> 0

    def test_first_week_returns_zero(self):
        start = date(2025, 1, 6)
        semanas = self._make_semanas(start, 8)
        assert _week_offset(semanas[0], semanas, start) == 0

    def test_last_week_returns_correct_index(self):
        start = date(2025, 1, 6)
        n = 8
        semanas = self._make_semanas(start, n)
        assert _week_offset(semanas[-1], semanas, start) == n - 1


# ===========================================================================
# _semanas_entre
# ===========================================================================


class TestSemantasEntre:
    def test_same_day_returns_one_week(self):
        d = date(2025, 3, 10)
        result = _semanas_entre(d, d)
        assert len(result) == 1

    def test_same_week_different_days(self):
        mon = date(2025, 3, 10)
        fri = date(2025, 3, 14)
        result = _semanas_entre(mon, fri)
        assert len(result) == 1
        assert result[0] == _iso_week_key(mon)

    def test_two_consecutive_weeks(self):
        mon1 = date(2025, 3, 10)
        mon2 = date(2025, 3, 17)
        result = _semanas_entre(mon1, mon2)
        assert len(result) == 2

    def test_spanning_month_boundary(self):
        start = date(2025, 1, 27)  # crosses Jan-Feb boundary
        end = date(2025, 2, 10)
        result = _semanas_entre(start, end)
        assert len(result) >= 2

    def test_no_duplicates(self):
        start = date(2025, 1, 6)
        end = date(2025, 3, 31)
        result = _semanas_entre(start, end)
        assert len(result) == len(set(result))

    def test_keys_are_iso_format(self):
        start = date(2025, 4, 1)
        end = date(2025, 4, 30)
        result = _semanas_entre(start, end)
        for key in result:
            assert "-W" in key
            year, week = key.split("-W")
            assert year.isdigit() and week.isdigit()

    def test_order_is_ascending(self):
        start = date(2025, 1, 6)
        end = date(2025, 6, 30)
        result = _semanas_entre(start, end)
        assert result == sorted(result)


# ===========================================================================
# _event_occurs_on_day
# ===========================================================================


class TestEventOccursOnDay:
    def _evt(self, inicio, fim, recorrencia=None, fator=None):
        e = {"inicio": inicio, "fim": fim}
        if recorrencia is not None:
            e["recorrencia"] = recorrencia
        if fator is not None:
            e["fator_operacao"] = fator
        return e

    # --- invalid dates (lines 365-366) ---
    def test_invalid_inicio_returns_false(self):
        e = {"inicio": "not-a-date", "fim": "2025-01-10"}
        assert _event_occurs_on_day(e, date(2025, 1, 5)) is False

    def test_invalid_fim_returns_false(self):
        e = {"inicio": "2025-01-01", "fim": "bad"}
        assert _event_occurs_on_day(e, date(2025, 1, 5)) is False

    def test_none_dates_returns_false(self):
        e = {"inicio": None, "fim": None}
        assert _event_occurs_on_day(e, date(2025, 1, 5)) is False

    def test_missing_dates_returns_false(self):
        assert _event_occurs_on_day({}, date(2025, 1, 5)) is False

    # --- anual same-year window (line 379) ---
    def test_anual_same_year_in_range(self):
        e = self._evt("2000-06-01", "2000-06-30", "anual")
        assert _event_occurs_on_day(e, date(2025, 6, 15)) is True

    def test_anual_same_year_out_of_range(self):
        e = self._evt("2000-06-01", "2000-06-30", "anual")
        assert _event_occurs_on_day(e, date(2025, 7, 1)) is False

    def test_anual_same_year_boundary_start(self):
        e = self._evt("2000-06-01", "2000-06-30", "anual")
        assert _event_occurs_on_day(e, date(2025, 6, 1)) is True

    def test_anual_same_year_boundary_end(self):
        e = self._evt("2000-06-01", "2000-06-30", "anual")
        assert _event_occurs_on_day(e, date(2025, 6, 30)) is True

    def test_anual_default_recorrencia(self):
        # recorrencia defaults to "anual" when absent
        e = {"inicio": "2000-07-04", "fim": "2000-07-04"}
        assert _event_occurs_on_day(e, date(2025, 7, 4)) is True
        assert _event_occurs_on_day(e, date(2025, 7, 5)) is False

    # --- anual cross-year window (lines 372-376) ---
    def test_anual_cross_year_in_window_current_year(self):
        # 20/12 to 10/01 — Christmas/New Year period
        e = self._evt("2000-12-20", "2001-01-10", "anual")
        # 2025-12-25 should be in window (start_ref=2025-12-20 <= 2025-12-25 <= end_ref=2026-01-10)
        assert _event_occurs_on_day(e, date(2025, 12, 25)) is True

    def test_anual_cross_year_in_window_prev_year(self):
        e = self._evt("2000-12-20", "2001-01-10", "anual")
        # 2026-01-05: prev_start=2025-12-20 <= 2026-01-05 <= prev_end=2026-01-10
        assert _event_occurs_on_day(e, date(2026, 1, 5)) is True

    def test_anual_cross_year_out_of_window(self):
        e = self._evt("2000-12-20", "2001-01-10", "anual")
        # July is not in the Dec-Jan window
        assert _event_occurs_on_day(e, date(2025, 7, 15)) is False

    def test_anual_cross_year_boundary_end(self):
        e = self._evt("2000-12-20", "2001-01-10", "anual")
        assert _event_occurs_on_day(e, date(2026, 1, 10)) is True

    # --- non-anual recurrence (line 403) ---
    def test_unica_in_range(self):
        e = self._evt("2025-03-01", "2025-03-31", "unica")
        assert _event_occurs_on_day(e, date(2025, 3, 15)) is True

    def test_unica_out_of_range(self):
        e = self._evt("2025-03-01", "2025-03-31", "unica")
        assert _event_occurs_on_day(e, date(2025, 4, 1)) is False

    def test_unica_before_start(self):
        e = self._evt("2025-03-01", "2025-03-31", "unica")
        assert _event_occurs_on_day(e, date(2025, 2, 28)) is False

    def test_unica_single_day(self):
        e = self._evt("2025-05-01", "2025-05-01", "unica")
        assert _event_occurs_on_day(e, date(2025, 5, 1)) is True
        assert _event_occurs_on_day(e, date(2025, 5, 2)) is False

    def test_mensal_recurrence_as_non_anual(self):
        # Any non-"anual" string uses range check
        e = self._evt("2025-01-01", "2025-12-31", "mensal")
        assert _event_occurs_on_day(e, date(2025, 6, 15)) is True
        assert _event_occurs_on_day(e, date(2026, 1, 1)) is False


# ===========================================================================
# _build_fator_calendario_semanal
# ===========================================================================


class TestBuildFatorCalendarioSemanal:
    def _make_semanas(self, start: date, n: int):
        semanas = []
        seen = set()
        d = start
        while len(semanas) < n:
            key = _iso_week_key(d)
            if key not in seen:
                seen.add(key)
                semanas.append(key)
            d += timedelta(days=7)
        return semanas

    def test_no_eventos_fator_is_one(self):
        start = date(2025, 1, 6)
        semanas = self._make_semanas(start, 4)
        fatores, artefato = _build_fator_calendario_semanal(semanas, start, 5, None)
        for key in semanas:
            assert fatores[key] == 1.0

    def test_returns_all_semanas_keys(self):
        start = date(2025, 1, 6)
        semanas = self._make_semanas(start, 3)
        fatores, _ = _build_fator_calendario_semanal(semanas, start, 5, {})
        for key in semanas:
            assert key in fatores

    def test_feriado_zero_reduces_fator(self):
        start = date(2025, 1, 6)  # Monday
        semanas = self._make_semanas(start, 2)
        # Event covering the whole first week (unica)
        eventos = [
            {
                "id": "feriado-1",
                "inicio": "2025-01-06",
                "fim": "2025-01-06",
                "recorrencia": "unica",
                "fator_operacao": 0.0,
            }
        ]
        fatores, _ = _build_fator_calendario_semanal(semanas, start, 5, {"eventos": eventos})
        # First week has one day with factor 0 → 4/5 = 0.8
        assert fatores[semanas[0]] == pytest.approx(0.8, abs=0.001)
        # Second week unaffected
        assert fatores[semanas[1]] == 1.0

    def test_full_week_shutdown_fator_zero(self):
        start = date(2025, 1, 6)
        semanas = self._make_semanas(start, 2)
        # Event covers the entire 5-day first week
        eventos = [
            {
                "id": "parada",
                "inicio": "2025-01-06",
                "fim": "2025-01-10",
                "recorrencia": "unica",
                "fator_operacao": 0.0,
            }
        ]
        fatores, _ = _build_fator_calendario_semanal(semanas, start, 5, {"eventos": eventos})
        assert fatores[semanas[0]] == pytest.approx(0.0, abs=0.001)

    def test_partial_fator_applied(self):
        start = date(2025, 1, 6)
        semanas = self._make_semanas(start, 1)
        # One day at 50% work
        eventos = [
            {
                "id": "evt",
                "inicio": "2025-01-06",
                "fim": "2025-01-06",
                "recorrencia": "unica",
                "fator_operacao": 0.5,
            }
        ]
        fatores, _ = _build_fator_calendario_semanal(semanas, start, 5, {"eventos": eventos})
        # 4 full days + 1 half day = 4.5/5 = 0.9
        assert fatores[semanas[0]] == pytest.approx(0.9, abs=0.001)

    def test_non_dict_evento_skipped(self):
        start = date(2025, 1, 6)
        semanas = self._make_semanas(start, 1)
        eventos = ["not-a-dict", None, 42]
        fatores, _ = _build_fator_calendario_semanal(semanas, start, 5, {"eventos": eventos})
        assert fatores[semanas[0]] == 1.0

    def test_artefato_length_matches_semanas(self):
        start = date(2025, 1, 6)
        semanas = self._make_semanas(start, 5)
        _, artefato = _build_fator_calendario_semanal(semanas, start, 5, {})
        assert len(artefato) == len(semanas)

    def test_ponto_facultativo_sem_fator_explicito_usa_default_nao_observa(self):
        """Evento tipo=ponto_facultativo sem fator_operacao (ex.: vindo de
        config/calendarios/, ADR-068) usa OBSERVAR_PONTOS_FACULTATIVOS_DEFAULT
        (False) -> dia normal, sem impacto."""
        start = date(2025, 1, 6)
        semanas = self._make_semanas(start, 1)
        eventos = [
            {
                "id": "facultativo-1",
                "tipo": "ponto_facultativo",
                "inicio": "2025-01-06",
                "fim": "2025-01-06",
                "recorrencia": "unica",
                "fator_operacao": None,
            }
        ]
        fatores, _ = _build_fator_calendario_semanal(semanas, start, 5, {"eventos": eventos})
        assert fatores[semanas[0]] == 1.0

    def test_ponto_facultativo_sem_fator_explicito_respeita_override_do_projeto(self):
        """`observar_pontos_facultativos=True` (escolha de projeto, ajustável
        entre versões) trata o ponto facultativo como parada integral,
        igual a um feriado — binário, sem meio-termo."""
        start = date(2025, 1, 6)
        semanas = self._make_semanas(start, 1)
        eventos = [
            {
                "id": "facultativo-1",
                "tipo": "ponto_facultativo",
                "inicio": "2025-01-06",
                "fim": "2025-01-06",
                "recorrencia": "unica",
                "fator_operacao": None,
            }
        ]
        fatores, _ = _build_fator_calendario_semanal(
            semanas, start, 5, {"eventos": eventos}, observar_pontos_facultativos=True
        )
        # tratado como parada integral: 4/5 = 0.8
        assert fatores[semanas[0]] == pytest.approx(0.8, abs=0.001)

    def test_feriado_sem_fator_explicito_e_sempre_zero_nao_configuravel(self):
        """tipo=feriado sem fator_operacao explícito é sempre 0.0, mesmo com
        observar_pontos_facultativos=False — parada integral não é uma escolha."""
        start = date(2025, 1, 6)
        semanas = self._make_semanas(start, 1)
        eventos = [
            {
                "id": "feriado-1",
                "tipo": "feriado",
                "inicio": "2025-01-06",
                "fim": "2025-01-06",
                "recorrencia": "unica",
                "fator_operacao": None,
            }
        ]
        fatores, _ = _build_fator_calendario_semanal(
            semanas, start, 5, {"eventos": eventos}, observar_pontos_facultativos=False
        )
        assert fatores[semanas[0]] == pytest.approx(0.8, abs=0.001)


# ===========================================================================
# _week_to_month
# ===========================================================================


class TestWeekToMonth:
    def test_first_week_maps_to_jan(self):
        result = _week_to_month("2025-W01")
        assert result == "01-2025"

    def test_week_13_maps_to_q1_q2_boundary(self):
        result = _week_to_month("2025-W13")
        month_num = int(result.split("-")[0])
        assert 1 <= month_num <= 12

    def test_week_52_maps_to_december(self):
        result = _week_to_month("2025-W52")
        month_num = int(result.split("-")[0])
        assert month_num == 12

    def test_format_mm_yyyy(self):
        result = _week_to_month("2025-W05")
        parts = result.split("-")
        assert len(parts) == 2
        assert parts[0].isdigit() and len(parts[0]) == 2
        assert parts[1] == "2025"


# ===========================================================================
# _infer_teams_from_resources
# ===========================================================================


class TestInferTeamsFromResources:
    def test_empty_resources_returns_one(self):
        assert _infer_teams_from_resources({}, {}, 0, 10) == 1

    def test_single_resource_type(self):
        assert _infer_teams_from_resources({"EQUIPE-A": 3}, {}, 0, 10) == 3

    def test_multiple_resource_types_summed(self):
        result = _infer_teams_from_resources({"EQUIPE-A": 2, "EQUIPE-B": 1}, {}, 0, 10)
        assert result == 3

    def test_ramp_profile_scales_peak(self):
        # ramp_profile[0] = 0.5 → 4 * 0.5 = 2
        result = _infer_teams_from_resources({"EQUIPE-A": 4}, {}, 0, 10, ramp_profile=[0.5, 1.0])
        assert result == 2

    def test_ramp_profile_at_peak(self):
        result = _infer_teams_from_resources({"EQUIPE-A": 4}, {}, 1, 10, ramp_profile=[0.5, 1.0])
        assert result == 4

    def test_ramp_profile_offset_beyond_profile_ignores_profile(self):
        result = _infer_teams_from_resources({"EQUIPE-A": 4}, {}, 5, 10, ramp_profile=[0.5, 1.0])
        assert result == 4

    def test_ramp_profile_zero_factor_returns_zero(self):
        result = _infer_teams_from_resources({"EQUIPE-A": 4}, {}, 0, 10, ramp_profile=[0.0, 1.0])
        assert result == 0


# ===========================================================================
# _find_item_by_id
# ===========================================================================


class TestFindItemById:
    def _item(self, item_id):
        class FakeItem:
            def __init__(self, id_):
                self.item_id = id_

        return FakeItem(item_id)

    def test_found(self):
        items = [self._item("A"), self._item("B"), self._item("C")]
        result = _find_item_by_id(items, "B")
        assert result is not None
        assert result.item_id == "B"

    def test_not_found_returns_none(self):
        items = [self._item("A"), self._item("B")]
        assert _find_item_by_id(items, "Z") is None

    def test_empty_list_returns_none(self):
        assert _find_item_by_id([], "A") is None

    def test_first_match_returned(self):
        items = [self._item("A"), self._item("A")]
        result = _find_item_by_id(items, "A")
        assert result is not None


# ===========================================================================
# _compute_ramp_profile
# ===========================================================================


class TestComputeRampProfile:
    def test_zero_duration_returns_empty(self):
        result = _compute_ramp_profile(0, {}, 5)
        assert result == []

    def test_zero_n_pico_returns_zeros(self):
        result = _compute_ramp_profile(4, {}, 0)
        assert result == [0.0, 0.0, 0.0, 0.0]

    def test_instant_ramp_profile_length(self):
        # Default taxa_mobilizacao = n_pico (instant ramp up in 1 step),
        # taxa_desmobilizacao defaults to same so last step ramps down.
        result = _compute_ramp_profile(4, {}, 3)
        assert len(result) == 4
        # First value is plateau (instant ramp)
        assert result[0] == pytest.approx(1.0)

    def test_instant_ramp_no_demob_all_at_peak(self):
        params = {"n_inicial": 0, "taxa_mobilizacao": 4.0, "taxa_desmobilizacao": 0.0}
        result = _compute_ramp_profile(4, params, 4)
        assert len(result) == 4
        assert all(v == pytest.approx(1.0) for v in result)

    def test_ramp_up_then_plateau(self):
        # n_pico=4, n_inicial=0, taxa_mobilizacao=2 → t_up=2, no ramp_down
        params = {"n_inicial": 0, "taxa_mobilizacao": 2.0, "taxa_desmobilizacao": 0.0}
        result = _compute_ramp_profile(5, params, 4)
        assert len(result) == 5
        # Week 0: min(4, ceil(0 + 2*1)) = 2 → 2/4 = 0.5
        assert result[0] == pytest.approx(0.5)
        # Week 1: min(4, ceil(0 + 2*2)) = 4 → 1.0
        assert result[1] == pytest.approx(1.0)
        # Weeks 2-4: plateau → 1.0
        assert all(v == pytest.approx(1.0) for v in result[2:])

    def test_ramp_down(self):
        # n_pico=4, instant ramp up, ramp down with taxa=2
        params = {"n_inicial": 4, "taxa_mobilizacao": 4.0, "taxa_desmobilizacao": 2.0}
        result = _compute_ramp_profile(4, params, 4)
        assert len(result) == 4
        # With n_inicial=4=n_pico, t_up=0
        # t_down = ceil(4/2) = 2
        # t_plateau = 4 - 0 - 2 = 2
        # weeks 0,1 → plateau → 1.0
        assert result[0] == pytest.approx(1.0)
        assert result[1] == pytest.approx(1.0)
        # weeks 2,3 → ramp down: offset=0 → max(0, floor(4-2*1))=2 → 2/4=0.5
        assert result[2] == pytest.approx(0.5)
        # offset=1 → max(0, floor(4-2*2))=0 → 0.0
        assert result[3] == pytest.approx(0.0)

    def test_profile_length_matches_duration(self):
        params = {"taxa_mobilizacao": 1.0, "taxa_desmobilizacao": 1.0}
        for n in [1, 3, 7, 10]:
            result = _compute_ramp_profile(n, params, 4)
            assert len(result) == n

    def test_all_values_in_zero_one_range(self):
        params = {"n_inicial": 0, "taxa_mobilizacao": 1.0, "taxa_desmobilizacao": 1.0}
        result = _compute_ramp_profile(8, params, 4)
        assert all(0.0 <= v <= 1.0 for v in result)


# ===========================================================================
# _mean_praticabilidade
# ===========================================================================


class TestMeanPraticabilidade:
    def _mock_canonical(self, prat_value):
        class FakeCanonical:
            praticabilidade = prat_value

        return FakeCanonical()

    def test_no_praticabilidade_returns_one(self):
        canonical = self._mock_canonical(None)
        assert _mean_praticabilidade(canonical) == pytest.approx(1.0)

    def test_dict_percentual_produtivo_semanal(self):
        class FakeCanonical:
            praticabilidade = {"percentual_produtivo_semanal": {"2025-W01": 0.8, "2025-W02": 0.6}}

        result = _mean_praticabilidade(FakeCanonical())
        assert result == pytest.approx(0.7)

    def test_attr_percentual_produtivo_semanal(self):
        class FakePrat:
            percentual_produtivo_semanal = {"2025-W01": 0.9, "2025-W02": 0.9}

        class FakeCanonical:
            praticabilidade = FakePrat()

        result = _mean_praticabilidade(FakeCanonical())
        assert result == pytest.approx(0.9)

    def test_all_zeros_returns_one(self):
        class FakeCanonical:
            praticabilidade = {"percentual_produtivo_semanal": {"2025-W01": 0.0}}

        result = _mean_praticabilidade(FakeCanonical())
        assert result == pytest.approx(1.0)

    def test_empty_dict_percentual_returns_one(self):
        class FakeCanonical:
            praticabilidade = {"percentual_produtivo_semanal": {}}

        result = _mean_praticabilidade(FakeCanonical())
        assert result == pytest.approx(1.0)

    def test_clamps_to_min_0_05(self):
        class FakeCanonical:
            praticabilidade = {"percentual_produtivo_semanal": {"2025-W01": 0.001}}

        result = _mean_praticabilidade(FakeCanonical())
        assert result == pytest.approx(0.05)

    def test_clamps_to_max_1(self):
        class FakeCanonical:
            praticabilidade = {"percentual_produtivo_semanal": {"2025-W01": 2.0}}

        result = _mean_praticabilidade(FakeCanonical())
        assert result == pytest.approx(1.0)

    def test_non_dict_sem_returns_one(self):
        class FakePrat:
            percentual_produtivo_semanal = "not-a-dict"

        class FakeCanonical:
            praticabilidade = FakePrat()

        result = _mean_praticabilidade(FakeCanonical())
        assert result == pytest.approx(1.0)


# ===========================================================================
# _build_cpu_lookup / _build_producao_lookup / _build_insumos_lookup
# ===========================================================================


class TestCatalogLookupBuilders:
    def test_build_cpu_lookup_indexes_by_codigo(self):
        catalogo = {"cpus": [{"codigo": "CPU-01", "desc": "A"}, {"codigo": "CPU-02", "desc": "B"}]}
        result = _build_cpu_lookup(catalogo)
        assert "CPU-01" in result
        assert result["CPU-02"]["desc"] == "B"

    def test_build_cpu_lookup_empty(self):
        assert _build_cpu_lookup({}) == {}

    def test_build_producao_lookup_produtividades(self):
        catalogo = {"produtividades": [{"id": "P-01"}, {"id": "P-02"}]}
        result = _build_producao_lookup(catalogo)
        assert "P-01" in result and "P-02" in result

    def test_build_producao_lookup_producoes_fallback(self):
        catalogo = {"producoes": [{"id": "P-X"}]}
        result = _build_producao_lookup(catalogo)
        assert "P-X" in result

    def test_build_producao_lookup_prefers_produtividades(self):
        catalogo = {"produtividades": [{"id": "P-A"}], "producoes": [{"id": "P-B"}]}
        result = _build_producao_lookup(catalogo)
        assert "P-A" in result
        assert "P-B" not in result

    def test_build_insumos_lookup_indexes_by_codigo(self):
        catalogo = {"insumos": [{"codigo": "INS-01"}, {"codigo": "INS-02"}, {"descricao": "no code"}]}
        result = _build_insumos_lookup(catalogo)
        assert "INS-01" in result
        assert "INS-02" in result
        # item without codigo should be skipped
        assert len(result) == 2

    def test_build_insumos_lookup_empty(self):
        assert _build_insumos_lookup({}) == {}


# ===========================================================================
# _custo_hora_equipe
# ===========================================================================


class TestCustoHoraEquipe:
    def test_funcao_mes_converts_to_hourly(self):
        composicao = {"funcoes": [{"funcao_id": "MO-01", "num_pessoas": 1}]}
        insumos = {"MO-01": {"preco_unitario": 1600.0, "unidade": "mes"}}
        # 1 * (1600/160) * (1+0) = 10.0
        result = _custo_hora_equipe(composicao, insumos, 160.0, 0.0)
        assert result == pytest.approx(10.0)

    def test_funcao_hora_applies_encargos(self):
        composicao = {"funcoes": [{"funcao_id": "MO-01", "num_pessoas": 1}]}
        insumos = {"MO-01": {"preco_unitario": 10.0, "unidade": "h"}}
        # 1 * 10.0 * (1 + 0.5) = 15.0
        result = _custo_hora_equipe(composicao, insumos, 160.0, 0.5)
        assert result == pytest.approx(15.0)

    def test_funcao_not_in_insumos_skipped(self):
        composicao = {"funcoes": [{"funcao_id": "MISSING", "num_pessoas": 1}]}
        result = _custo_hora_equipe(composicao, {}, 160.0, 0.0)
        assert result == pytest.approx(0.0)

    def test_multiple_funcoes_summed(self):
        composicao = {
            "funcoes": [
                {"funcao_id": "MO-01", "num_pessoas": 2},
                {"funcao_id": "MO-02", "num_pessoas": 1},
            ]
        }
        insumos = {
            "MO-01": {"preco_unitario": 800.0, "unidade": "mes"},
            "MO-02": {"preco_unitario": 1600.0, "unidade": "mes"},
        }
        # 2*(800/160) + 1*(1600/160) = 10 + 10 = 20
        result = _custo_hora_equipe(composicao, insumos, 160.0, 0.0)
        assert result == pytest.approx(20.0)

    def test_empty_composicao_returns_zero(self):
        result = _custo_hora_equipe({}, {}, 160.0, 0.0)
        assert result == pytest.approx(0.0)

    def test_funcao_hora_with_encargos_incluidos(self):
        """ADR-182: metodo_custo_total (campo estruturado) substitui o texto
        livre "inclui encargos" em nota."""
        composicao = {"funcoes": [{"funcao_id": "FN-01", "num_pessoas": 1}]}
        insumos = {
            "FN-01": {
                "preco_unitario": 10.0,
                "unidade": "h",
                "atributos_especificos": {"metodo_custo_total": "custo_total_ja_incluido"},
            }
        }
        # encargos already included: 1 * 10.0 * (1 + 0) = 10.0 even with taxa=0.5
        result = _custo_hora_equipe(composicao, insumos, 160.0, 0.5)
        assert result == pytest.approx(10.0)

    def test_funcao_mensal_com_metodo_custo_total_nao_aplica_encargos(self):
        """ADR-182: metodo_custo_total agora vale também para unidade mensal
        (antes só unidade h/hora era verificada)."""
        composicao = {"funcoes": [{"funcao_id": "FN-02", "num_pessoas": 1}]}
        insumos = {
            "FN-02": {
                "preco_unitario": 1600.0,
                "unidade": "mes",
                "atributos_especificos": {"metodo_custo_total": "custo_total_ja_incluido"},
            }
        }
        # já all-in: (1600/160) * (1+0) = 10.0, mesmo com taxa=0.5
        result = _custo_hora_equipe(composicao, insumos, 160.0, 0.5)
        assert result == pytest.approx(10.0)
