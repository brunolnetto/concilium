"""Testes para validadores pydantic (`@model_validator`) e helpers de migração
definidos diretamente em canonical.py, sem lar semântico em outro arquivo de teste
específico de ADR/feature.
"""

from __future__ import annotations

import pytest

from concilium.domain.models.canonical import (
    VetorExposuraCpu,
    _extract_weeks_from_dist,
    _migrate_cron_item_to_dict,
    _migrate_cron_list_to_cronograma,
)


class TestMigrateCronItemToDict:
    def test_dict_returned_as_is(self):
        item = {"item_id": "1.1"}
        assert _migrate_cron_item_to_dict(item) is item

    def test_model_with_model_dump_is_converted(self):
        class _Fake:
            def model_dump(self):
                return {"item_id": "1.1"}

        assert _migrate_cron_item_to_dict(_Fake()) == {"item_id": "1.1"}

    def test_unrecognized_type_returns_none(self):
        assert _migrate_cron_item_to_dict("not-a-dict-or-model") is None


class TestExtractWeeksFromDist:
    def test_extracts_iso_week_numbers(self):
        assert _extract_weeks_from_dist({"2026-W01": {}, "2026-W05": {}}) == [1, 5]

    def test_ignores_keys_without_week_marker(self):
        assert _extract_weeks_from_dist({"2026-01": {}}) == []

    def test_ignores_malformed_week_marker(self):
        assert _extract_weeks_from_dist({"2026-Wxx": {}}) == []

    def test_empty_dist_returns_empty_list(self):
        assert _extract_weeks_from_dist({}) == []


class TestMigrateCronListToCronograma:
    def test_skips_unrecognized_items(self):
        result = _migrate_cron_list_to_cronograma(["not-a-dict-or-model"])
        assert result["scheduled_activities"] == []

    def test_falls_back_to_distribuicao_mensal_when_semanal_absent(self):
        cron = [{"item_id": "1.1", "distribuicao_mensal": {"2026-W01": {"num_equipes": 1}}}]
        result = _migrate_cron_list_to_cronograma(cron)
        assert result["scheduled_activities"][0]["activity_id"] == "1.1"

    def test_defaults_to_week_1_when_no_weeks_found(self):
        cron = [{"item_id": "1.1", "distribuicao_semanal": {}}]
        result = _migrate_cron_list_to_cronograma(cron)
        activity = result["scheduled_activities"][0]
        assert activity["start_week"] == 1
        assert activity["end_week"] == 1


class TestVetorExposuraCpuSimplexValidator:
    def test_valid_simplex_sums_to_one(self):
        v = VetorExposuraCpu(equip=0.25, mao_obra=0.25, material=0.25, outros=0.25)
        assert v.equip == 0.25

    def test_invalid_simplex_raises_value_error(self):
        with pytest.raises(ValueError, match="deve somar 1,0"):
            VetorExposuraCpu(equip=0.5, mao_obra=0.5, material=0.5, outros=0.5)
