"""Testes para CuboSpans — substitui a leitura ad-hoc em GoldAggregator.build_sli_diario."""

from __future__ import annotations

import pytest

from concilium.infrastructure.observability.cubo_spans import CelulaSpan, CuboSpans


def _silver_span(**overrides):
    base = {
        "span_id": "s1",
        "trace_id": "t1",
        "start_ts": "2026-07-21T10:00:00.000000Z",
        "end_ts": "2026-07-21T10:00:00.150000Z",
        "duration_ms": 150,
        "status": "OK",
        "project_id": "AGIS",
        "skill_id": "05",
        "tool_name": "executar_pipeline",
        "user_id": "u1",
    }
    base.update(overrides)
    return base


class TestFromSilver:
    def test_maps_all_dimensions_and_duration(self):
        cubo = CuboSpans.from_silver([_silver_span()])

        cel = cubo.celulas[0]
        assert cel.skill_id == "05"
        assert cel.project_id == "AGIS"
        assert cel.tool_name == "executar_pipeline"
        assert cel.user_id == "u1"
        assert cel.status == "OK"
        assert cel.date == "2026-07-21"
        assert cel.duration_ms == 150

    def test_missing_optional_dimensions_default_to_none(self):
        record = _silver_span()
        for key in ("project_id", "skill_id", "tool_name", "user_id"):
            record.pop(key)

        cel = CuboSpans.from_silver([record]).celulas[0]

        assert cel.skill_id is None
        assert cel.project_id is None
        assert cel.tool_name is None
        assert cel.user_id is None

    def test_multiple_records_produce_multiple_cells(self):
        cubo = CuboSpans.from_silver([_silver_span(span_id="s1"), _silver_span(span_id="s2")])

        assert len(cubo.celulas) == 2


class TestQueryIntegration:
    def test_sli_style_query(self):
        """Reproduz build_sli_diario de hoje: percentis de duration_ms por (date, skill_id)."""
        cubo = CuboSpans.from_silver(
            [
                _silver_span(span_id="s1", duration_ms=100),
                _silver_span(span_id="s2", duration_ms=200),
                _silver_span(span_id="s3", duration_ms=300),
            ]
        )

        rows = cubo.query(
            group_by=["date", "skill_id"],
            aggs={
                "p50_ms": "PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY duration_ms)",
                "n_spans": "count(*)",
            },
            where="skill_id IS NOT NULL",
        )

        assert len(rows) == 1
        assert rows[0]["p50_ms"] == 200
        assert rows[0]["n_spans"] == 3

    def test_slice_by_tool_name(self):
        cubo = CuboSpans.from_silver([_silver_span(tool_name="a"), _silver_span(tool_name="b")])

        result = cubo.slice(tool_name="a")

        assert len(result.celulas) == 1


class TestCelulaSpanIsPlainDataclass:
    def test_construct_directly(self):
        cel = CelulaSpan(
            skill_id="05",
            project_id="AGIS",
            tool_name="t",
            user_id="u1",
            status="OK",
            date="2026-07-21",
            duration_ms=100,
        )
        assert cel.duration_ms == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
