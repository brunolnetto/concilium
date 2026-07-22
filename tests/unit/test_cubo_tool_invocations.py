"""Testes para CuboToolInvocations — primeiro cubo sobre o 4º signal_type (gap 3, ADR-112 extensão)."""

from __future__ import annotations

import pytest

from concilium.infrastructure.observability.cubo_tool_invocations import (
    CelulaToolInvocation,
    CuboToolInvocations,
)


def _silver_invocation(**overrides):
    base = {
        "tool_name": "listar_projetos",
        "user_id": "u1",
        "device_id": "device-1",
        "status": "success",
        "started_at": "2026-07-21T10:00:00.000000Z",
        "finished_at": "2026-07-21T10:00:01.500000Z",
    }
    base.update(overrides)
    return base


class TestFromSilver:
    def test_maps_dimensions_and_computes_duration(self):
        cel = CuboToolInvocations.from_silver([_silver_invocation()]).celulas[0]

        assert cel.tool_name == "listar_projetos"
        assert cel.user_id == "u1"
        assert cel.device_id == "device-1"
        assert cel.status == "success"
        assert cel.date == "2026-07-21"
        assert cel.duration_ms == 1500

    def test_missing_optional_dimensions_default_to_none(self):
        record = _silver_invocation()
        for key in ("user_id", "device_id"):
            record.pop(key)

        cel = CuboToolInvocations.from_silver([record]).celulas[0]

        assert cel.user_id is None
        assert cel.device_id is None

    def test_missing_timestamps_yield_zero_duration_not_crash(self):
        record = _silver_invocation()
        record.pop("finished_at")

        cel = CuboToolInvocations.from_silver([record]).celulas[0]

        assert cel.duration_ms == 0

    def test_malformed_timestamp_yields_zero_duration_not_crash(self):
        record = _silver_invocation(started_at="not-a-timestamp")

        cel = CuboToolInvocations.from_silver([record]).celulas[0]

        assert cel.duration_ms == 0


class TestQueryIntegration:
    def test_avg_duration_by_tool(self):
        cubo = CuboToolInvocations.from_silver(
            [
                _silver_invocation(
                    tool_name="a", started_at="2026-07-21T10:00:00Z", finished_at="2026-07-21T10:00:01Z"
                ),
                _silver_invocation(
                    tool_name="a", started_at="2026-07-21T10:00:00Z", finished_at="2026-07-21T10:00:03Z"
                ),
            ]
        )

        rows = cubo.query(group_by=["tool_name"], aggs={"avg_ms": "avg(duration_ms)", "n": "count(*)"})

        assert rows[0]["avg_ms"] == 2000.0
        assert rows[0]["n"] == 2

    def test_slice_by_device(self):
        cubo = CuboToolInvocations.from_silver(
            [_silver_invocation(device_id="d1"), _silver_invocation(device_id="d2")]
        )

        result = cubo.slice(device_id="d1")

        assert len(result.celulas) == 1


class TestCelulaToolInvocationIsPlainDataclass:
    def test_construct_directly(self):
        cel = CelulaToolInvocation(
            tool_name="t", user_id=None, device_id=None, status="success", date="2026-07-21", duration_ms=100
        )
        assert cel.duration_ms == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
