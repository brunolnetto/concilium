"""Testes para CuboMetricas — primeiro consumidor real da projeção dimensional
de metrics (ADR-146). Gold nunca usou metrics antes deste cubo."""

from __future__ import annotations

import pytest

from concilium.infrastructure.observability.cubo_metricas import CelulaMetrica, CuboMetricas


def _silver_metric(**overrides):
    base = {
        "metric_name": "concilium.mcp.tool.calls",
        "ts": "2026-07-21T10:00:00.000000Z",
        "value": 1.0,
        "skill_id": "05",
        "project_id": "AGIS",
        "tool_name": "executar_pipeline",
    }
    base.update(overrides)
    return base


class TestFromSilver:
    def test_maps_all_dimensions_and_value(self):
        cel = CuboMetricas.from_silver([_silver_metric()]).celulas[0]

        assert cel.metric_name == "concilium.mcp.tool.calls"
        assert cel.skill_id == "05"
        assert cel.project_id == "AGIS"
        assert cel.tool_name == "executar_pipeline"
        assert cel.date == "2026-07-21"
        assert cel.value == 1.0

    def test_missing_optional_dimensions_default_to_none(self):
        record = _silver_metric()
        for key in ("skill_id", "project_id", "tool_name"):
            record.pop(key)

        cel = CuboMetricas.from_silver([record]).celulas[0]

        assert cel.skill_id is None
        assert cel.project_id is None
        assert cel.tool_name is None


class TestQueryIntegration:
    def test_tool_usage_by_status_query(self):
        cubo = CuboMetricas.from_silver(
            [
                _silver_metric(tool_name="listar_projetos", value=1.0),
                _silver_metric(tool_name="listar_projetos", value=1.0),
                _silver_metric(tool_name="criar_projeto", value=1.0),
            ]
        )

        rows = cubo.query(group_by=["tool_name"], aggs={"total": "sum(value)"})

        by_tool = {r["tool_name"]: r["total"] for r in rows}
        assert by_tool["listar_projetos"] == 2.0
        assert by_tool["criar_projeto"] == 1.0

    def test_slice_by_project(self):
        cubo = CuboMetricas.from_silver(
            [_silver_metric(project_id="AGIS"), _silver_metric(project_id="OUTRO")]
        )

        result = cubo.slice(project_id="AGIS")

        assert len(result.celulas) == 1


class TestCelulaMetricaIsPlainDataclass:
    def test_construct_directly(self):
        cel = CelulaMetrica(
            metric_name="m", skill_id=None, project_id=None, tool_name=None, date="2026-07-21", value=1.0
        )
        assert cel.value == 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
