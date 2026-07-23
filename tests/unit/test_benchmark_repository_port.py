"""Tests for small-gap files: benchmark repository port, week_sequence, config mixin,
permission_guard, rate_limit, jwt_auth, replan MCP tool."""

from __future__ import annotations


# ─── domain/benchmark/repository.py (abstract methods) ────────────────────────
class TestWeekIndex:
    def test_seq_format(self):
        from concilium.domain.services.planning.week_sequence import week_index

        assert week_index("S001") == 1
        assert week_index("S052") == 52

    def test_iso_format(self):
        from concilium.domain.services.planning.week_sequence import week_index

        assert week_index("2026-W01") > 0
        assert week_index("2026-W02") > week_index("2026-W01")

    def test_numeric_fallback(self):
        from concilium.domain.services.planning.week_sequence import week_index

        assert week_index("10") == 10

    def test_invalid_returns_zero(self):
        from concilium.domain.services.planning.week_sequence import week_index

        assert week_index("bad") == 0

    def test_iso_bad_date_returns_zero(self):
        from concilium.domain.services.planning.week_sequence import week_index

        assert week_index("2026-W99") == 0


class TestNextWeek:
    def test_seq_increments(self):
        from concilium.domain.services.planning.week_sequence import next_week

        assert next_week("S001") == "S002"
        assert next_week("S010") == "S011"

    def test_iso_increments(self):
        from concilium.domain.services.planning.week_sequence import next_week

        result = next_week("2026-W01")
        assert result == "2026-W02"

    def test_iso_year_rollover(self):
        from concilium.domain.services.planning.week_sequence import next_week

        result = next_week("2026-W52")
        assert "-W" in result

    def test_numeric_fallback(self):
        from concilium.domain.services.planning.week_sequence import next_week

        assert next_week("5") == "6"

    def test_invalid_returns_unchanged(self):
        from concilium.domain.services.planning.week_sequence import next_week

        assert next_week("bad") == "bad"


class TestEnumerarSemanas:
    def test_seq_range(self):
        from concilium.domain.services.planning.week_sequence import enumerar_semanas

        result = enumerar_semanas("S001", "S003")
        assert result == ["S001", "S002", "S003"]

    def test_iso_range(self):
        from concilium.domain.services.planning.week_sequence import enumerar_semanas

        result = enumerar_semanas("2026-W01", "2026-W03")
        assert len(result) == 3

    def test_empty_when_fim_before_inicio(self):
        from concilium.domain.services.planning.week_sequence import enumerar_semanas

        assert enumerar_semanas("S003", "S001") == []

    def test_empty_when_none(self):
        from concilium.domain.services.planning.week_sequence import enumerar_semanas

        assert enumerar_semanas(None, "S001") == []
        assert enumerar_semanas("S001", None) == []
        assert enumerar_semanas("", "S001") == []

    def test_single_week(self):
        from concilium.domain.services.planning.week_sequence import enumerar_semanas

        assert enumerar_semanas("S005", "S005") == ["S005"]



