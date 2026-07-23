"""Testes para CuboLogs — substitui a leitura ad-hoc em GoldAggregator.build_fallback_rate_por_skill
e CrossDomainBuilder."""

from __future__ import annotations

import pytest

from concilium.infrastructure.observability.cubo_logs import CelulaLog, CuboLogs


def _silver_log(**overrides):
    base = {
        "event_id": "e1",
        "ts": "2026-07-21T10:00:00.000000Z",
        "severity": "ERROR",
        "project_id": "AGIS",
        "skill_id": "05",
        "fallback_type": None,
        "user_id": "u1",
    }
    base.update(overrides)
    return base


class TestFromSilver:
    def test_maps_all_dimensions(self):
        cel = CuboLogs.from_silver([_silver_log()]).celulas[0]

        assert cel.skill_id == "05"
        assert cel.project_id == "AGIS"
        assert cel.user_id == "u1"
        assert cel.severity == "ERROR"
        assert cel.fallback_type is None
        assert cel.date == "2026-07-21"

    def test_missing_optional_dimensions_default_to_none(self):
        record = _silver_log()
        for key in ("project_id", "skill_id", "user_id"):
            record.pop(key)

        cel = CuboLogs.from_silver([record]).celulas[0]

        assert cel.skill_id is None
        assert cel.project_id is None
        assert cel.user_id is None


class TestQueryIntegration:
    def test_fallback_rate_style_query(self):
        """Reproduz build_fallback_rate_por_skill de hoje."""
        cubo = CuboLogs.from_silver(
            [
                _silver_log(event_id="e1", fallback_type="preco_unitario"),
                _silver_log(event_id="e2", fallback_type=None),
                _silver_log(event_id="e3", fallback_type=None, skill_id=None),
            ]
        )

        rows = cubo.query(
            group_by=["date", "COALESCE(skill_id, 'unknown') AS skill_id"],
            aggs={
                "n_fallbacks": "count(*) FILTER (WHERE fallback_type IS NOT NULL)",
                "n_total": "count(*)",
            },
        )

        by_skill = {r["skill_id"]: r for r in rows}
        assert by_skill["05"]["n_fallbacks"] == 1
        assert by_skill["05"]["n_total"] == 2
        assert by_skill["unknown"]["n_total"] == 1

    def test_cross_domain_style_query_by_project(self):
        cubo = CuboLogs.from_silver(
            [
                _silver_log(event_id="e1", project_id="AGIS", fallback_type="x"),
                _silver_log(event_id="e2", project_id="AGIS", fallback_type=None),
                _silver_log(event_id="e3", project_id="OUTRO", fallback_type=None),
            ]
        )

        rows = cubo.query(
            group_by=["COALESCE(project_id, 'unknown') AS project_id"],
            aggs={"n_fallbacks": "count(*) FILTER (WHERE fallback_type IS NOT NULL)", "n_total": "count(*)"},
        )

        by_project = {r["project_id"]: r for r in rows}
        assert by_project["AGIS"]["n_total"] == 2
        assert by_project["AGIS"]["n_fallbacks"] == 1
        assert by_project["OUTRO"]["n_total"] == 1


class TestCelulaLogIsPlainDataclass:
    def test_construct_directly(self):
        cel = CelulaLog(
            skill_id="05", project_id="AGIS", user_id="u1", severity="INFO", fallback_type=None, date="2026-07-21"
        )
        assert cel.severity == "INFO"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
