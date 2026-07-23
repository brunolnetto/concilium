"""Unit tests for week_mapper module (ADR-043).

All functions are pure transformations on plain dicts — no mocks needed.
"""

from __future__ import annotations

from concilium.application.benchmarks.input_derivation.week_mapper import (
    build_numeric_to_iso_map,
    is_numeric_week_scheme,
    normalize_referencia_weeks,
    remap_activity_semanas,
)

# ---------------------------------------------------------------------------
# is_numeric_week_scheme
# ---------------------------------------------------------------------------


class TestIsNumericWeekScheme:
    def test_empty_dict_returns_false(self):
        assert is_numeric_week_scheme({}) is False

    def test_all_digit_keys_returns_true(self):
        assert is_numeric_week_scheme({"1": {}, "2": {}, "10": {}}) is True

    def test_mixed_keys_returns_false(self):
        assert is_numeric_week_scheme({"1": {}, "2026-W02": {}}) is False

    def test_non_digit_keys_returns_false(self):
        assert is_numeric_week_scheme({"alpha": {}, "beta": {}}) is False

    def test_single_digit_key_returns_true(self):
        assert is_numeric_week_scheme({"1": "anything"}) is True

    def test_iso_week_keys_returns_false(self):
        assert is_numeric_week_scheme({"2026-W01": {}, "2026-W02": {}}) is False


# ---------------------------------------------------------------------------
# build_numeric_to_iso_map
# ---------------------------------------------------------------------------


class TestBuildNumericToIsoMap:
    def test_empty_dict_returns_empty(self):
        assert build_numeric_to_iso_map({}) == {}

    def test_valid_semanas_yields_iso_keys(self):
        # 2026-01-05 is Monday of ISO week 2 of 2026
        semanas = {
            "1": {"data_inicio": "2026-01-05"},
            "2": {"data_inicio": "2026-01-12"},
        }
        result = build_numeric_to_iso_map(semanas)
        assert result["1"] == "2026-W02"
        assert result["2"] == "2026-W03"

    def test_non_digit_keys_are_skipped(self):
        semanas = {
            "1": {"data_inicio": "2026-01-05"},
            "alpha": {"data_inicio": "2026-01-12"},
        }
        result = build_numeric_to_iso_map(semanas)
        assert "alpha" not in result
        assert "1" in result

    def test_non_dict_values_are_skipped(self):
        semanas = {
            "1": "not-a-dict",
            "2": {"data_inicio": "2026-01-05"},
        }
        result = build_numeric_to_iso_map(semanas)
        assert "1" not in result
        assert "2" in result

    def test_missing_data_inicio_skipped(self):
        semanas = {
            "1": {"data_fim": "2026-01-11"},
            "2": {"data_inicio": "2026-01-12"},
        }
        result = build_numeric_to_iso_map(semanas)
        assert "1" not in result
        assert "2" in result

    def test_invalid_date_string_skipped(self):
        semanas = {
            "1": {"data_inicio": "not-a-date"},
            "2": {"data_inicio": "2026-01-05"},
        }
        result = build_numeric_to_iso_map(semanas)
        assert "1" not in result
        assert "2" in result

    def test_iso_week_format_two_digit_zero_padded(self):
        # 2026-01-05 -> ISO week 2
        semanas = {"2": {"data_inicio": "2026-01-05"}}
        result = build_numeric_to_iso_map(semanas)
        assert result["2"] == "2026-W02"

    def test_week_across_year_boundary(self):
        # 2025-12-29 is in ISO week 1 of 2026
        semanas = {"1": {"data_inicio": "2025-12-29"}}
        result = build_numeric_to_iso_map(semanas)
        assert result["1"] == "2026-W01"

    def test_empty_data_inicio_value_skipped(self):
        semanas = {"1": {"data_inicio": ""}}
        result = build_numeric_to_iso_map(semanas)
        assert "1" not in result


# ---------------------------------------------------------------------------
# remap_activity_semanas
# ---------------------------------------------------------------------------


class TestRemapActivitySemanas:
    def test_numeric_keys_mapped_to_iso(self):
        activity_semanas = {"1": {"num_equipes": 2}, "2": {"num_equipes": 3}}
        num_to_iso = {"1": "2026-W02", "2": "2026-W03"}
        result = remap_activity_semanas(activity_semanas, num_to_iso)
        assert "2026-W02" in result
        assert "2026-W03" in result
        assert result["2026-W02"] == {"num_equipes": 2}
        assert result["2026-W03"] == {"num_equipes": 3}

    def test_unknown_keys_kept_as_is(self):
        activity_semanas = {"99": {"num_equipes": 1}}
        num_to_iso = {"1": "2026-W02"}
        result = remap_activity_semanas(activity_semanas, num_to_iso)
        # key "99" not in num_to_iso, so it should fall back to original
        assert "99" in result
        assert result["99"] == {"num_equipes": 1}

    def test_inner_values_preserved_unchanged(self):
        inner = {"num_equipes": 5, "qty_planejada": 100.0, "extra": [1, 2, 3]}
        activity_semanas = {"1": inner}
        num_to_iso = {"1": "2026-W02"}
        result = remap_activity_semanas(activity_semanas, num_to_iso)
        assert result["2026-W02"] is inner  # same object, not a copy

    def test_empty_activity_semanas_returns_empty(self):
        result = remap_activity_semanas({}, {"1": "2026-W02"})
        assert result == {}

    def test_empty_num_to_iso_keeps_original_keys(self):
        activity_semanas = {"1": {}, "2": {}}
        result = remap_activity_semanas(activity_semanas, {})
        assert "1" in result
        assert "2" in result

    def test_already_iso_keys_unchanged(self):
        activity_semanas = {"2026-W02": {"num_equipes": 4}}
        num_to_iso = {}
        result = remap_activity_semanas(activity_semanas, num_to_iso)
        assert "2026-W02" in result


# ---------------------------------------------------------------------------
# normalize_referencia_weeks
# ---------------------------------------------------------------------------


class TestNormalizeReferenciaWeeks:
    def _make_ref(self, **kwargs):
        """Build a minimal referencia dict with numeric semanas scheme."""
        return {
            "cronograma": {
                "semanas": {
                    "1": {"data_inicio": "2026-01-05", "data_fim": "2026-01-11"},
                    "2": {"data_inicio": "2026-01-12", "data_fim": "2026-01-18"},
                },
                "atividades": [],
            },
            **kwargs,
        }

    # -- basic guards --------------------------------------------------------

    def test_no_cronograma_key_returns_ref_unchanged(self):
        ref = {"foo": "bar"}
        result = normalize_referencia_weeks(ref)
        assert result is ref
        assert result == {"foo": "bar"}

    def test_cronograma_not_dict_returns_ref_unchanged(self):
        ref = {"cronograma": "not-a-dict"}
        result = normalize_referencia_weeks(ref)
        assert result is ref

    def test_non_numeric_semanas_returns_unchanged(self):
        ref = {
            "cronograma": {
                "semanas": {"2026-W02": {"data_inicio": "2026-01-05"}},
                "atividades": [],
            }
        }
        result = normalize_referencia_weeks(ref)
        # semanas are ISO already — function should return early
        assert "2026-W02" in result["cronograma"]["semanas"]

    def test_empty_semanas_returns_unchanged(self):
        ref = {"cronograma": {"semanas": {}, "atividades": []}}
        result = normalize_referencia_weeks(ref)
        assert result is ref

    # -- data_inicio / data_termino injection --------------------------------

    def test_data_inicio_injected_when_absent(self):
        ref = self._make_ref()
        result = normalize_referencia_weeks(ref)
        assert result["data_inicio"] == "2026-01-05"

    def test_data_inicio_not_overwritten_when_present(self):
        ref = self._make_ref(data_inicio="2000-01-01")
        result = normalize_referencia_weeks(ref)
        assert result["data_inicio"] == "2000-01-01"

    def test_data_termino_filled_from_data_fim_when_present(self):
        ref = self._make_ref()
        result = normalize_referencia_weeks(ref)
        assert result["data_termino"] == "2026-01-18"

    def test_data_termino_falls_back_to_data_inicio_of_last_week(self):
        ref = {
            "cronograma": {
                "semanas": {
                    "1": {"data_inicio": "2026-01-05"},
                    "2": {"data_inicio": "2026-01-12"},
                    # no data_fim
                },
                "atividades": [],
            }
        }
        result = normalize_referencia_weeks(ref)
        # last week is "2" -> data_inicio used as fallback for data_termino
        assert result["data_termino"] == "2026-01-12"

    def test_data_termino_not_overwritten_when_present(self):
        ref = self._make_ref(data_termino="2099-12-31")
        result = normalize_referencia_weeks(ref)
        assert result["data_termino"] == "2099-12-31"

    # -- atividades remapping ------------------------------------------------

    def test_numeric_semanas_pipeline_remaps_activities(self):
        ref = {
            "cronograma": {
                "semanas": {
                    "1": {"data_inicio": "2026-01-05", "data_fim": "2026-01-11"},
                },
                "atividades": [
                    {"nome": "Esc", "semanas": {"1": {"num_equipes": 2}}},
                ],
            }
        }
        result = normalize_referencia_weeks(ref)
        atividade = result["cronograma"]["atividades"][0]
        assert "2026-W02" in atividade["semanas"]
        assert "1" not in atividade["semanas"]

    def test_activity_already_iso_keyed_left_alone(self):
        ref = {
            "cronograma": {
                "semanas": {
                    "1": {"data_inicio": "2026-01-05"},
                },
                "atividades": [
                    # semanas already ISO — is_numeric_week_scheme returns False
                    {"semanas": {"2026-W02": {"num_equipes": 3}}},
                ],
            }
        }
        result = normalize_referencia_weeks(ref)
        atividade = result["cronograma"]["atividades"][0]
        assert "2026-W02" in atividade["semanas"]

    def test_atividades_list_with_non_dict_elements_skipped(self):
        ref = {
            "cronograma": {
                "semanas": {
                    "1": {"data_inicio": "2026-01-05"},
                },
                "atividades": [
                    "string-element",
                    None,
                    42,
                    {"semanas": {"1": {"num_equipes": 1}}},
                ],
            }
        }
        # Should not raise; non-dict elements are skipped
        result = normalize_referencia_weeks(ref)
        last = result["cronograma"]["atividades"][3]
        assert "2026-W02" in last["semanas"]

    def test_activity_with_non_dict_semanas_skipped(self):
        ref = {
            "cronograma": {
                "semanas": {
                    "1": {"data_inicio": "2026-01-05"},
                },
                "atividades": [
                    {"semanas": "not-a-dict"},
                    {"semanas": None},
                    {"semanas": [1, 2, 3]},
                ],
            }
        }
        # Should not raise; activities with non-dict semanas are skipped
        result = normalize_referencia_weeks(ref)
        for ativ in result["cronograma"]["atividades"]:
            # semanas should be unchanged (not a dict, was not remapped)
            assert not isinstance(ativ["semanas"], dict) or ativ["semanas"] == {}

    def test_no_atividades_key_does_not_raise(self):
        ref = {
            "cronograma": {
                "semanas": {
                    "1": {"data_inicio": "2026-01-05"},
                },
                # no "atividades" key at all
            }
        }
        result = normalize_referencia_weeks(ref)
        assert result["data_inicio"] == "2026-01-05"

    def test_atividades_not_a_list_does_not_raise(self):
        ref = {
            "cronograma": {
                "semanas": {
                    "1": {"data_inicio": "2026-01-05"},
                },
                "atividades": {"not": "a-list"},
            }
        }
        # should return without crashing
        result = normalize_referencia_weeks(ref)
        assert result is ref

    def test_returns_same_dict_object(self):
        ref = self._make_ref()
        result = normalize_referencia_weeks(ref)
        assert result is ref

    def test_multiple_activities_all_remapped(self):
        ref = {
            "cronograma": {
                "semanas": {
                    "1": {"data_inicio": "2026-01-05"},
                    "2": {"data_inicio": "2026-01-12"},
                },
                "atividades": [
                    {"semanas": {"1": {"v": 1}}},
                    {"semanas": {"2": {"v": 2}}},
                ],
            }
        }
        result = normalize_referencia_weeks(ref)
        assert "2026-W02" in result["cronograma"]["atividades"][0]["semanas"]
        assert "2026-W03" in result["cronograma"]["atividades"][1]["semanas"]

    def test_single_week_both_dates_from_first_and_last_same(self):
        ref = {
            "cronograma": {
                "semanas": {
                    "1": {"data_inicio": "2026-01-05", "data_fim": "2026-01-11"},
                },
                "atividades": [],
            }
        }
        result = normalize_referencia_weeks(ref)
        assert result["data_inicio"] == "2026-01-05"
        assert result["data_termino"] == "2026-01-11"




# week_mapper.py line 109:
# num_to_iso empty (numeric keys but no data_inicio) → return ref
# ---------------------------------------------------------------------------


class TestNormalizeReferenciaWeeksEmptyMap:
    def test_numeric_scheme_but_no_data_inicio_returns_ref_unchanged(self):
        """Line 109: build_numeric_to_iso_map returns {} → not num_to_iso → return ref."""
        from concilium.application.benchmarks.input_derivation.week_mapper import (
            normalize_referencia_weeks,
        )

        ref = {
            "cronograma": {
                "semanas": {"1": {}, "2": {}},  # numeric keys, but no data_inicio
                "atividades": [],
            }
        }
        result = normalize_referencia_weeks(ref)
        # Returned unchanged (same object)
        assert result is ref


# ---------------------------------------------------------------------------

