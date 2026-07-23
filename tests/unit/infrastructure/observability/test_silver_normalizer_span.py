"""Testes focados em silver_normalizer.normalize_span_record — campos tool_name/user_id/request_id.

Cobertura ampla dos normalizers (logs/traces/metrics) já existe via testes de integração
(test_adr112_observability_pipeline.py, test_adr112_observability_api.py). Este arquivo cobre
especificamente os campos novos que a Silver descartava por não estarem no schema de projeção.
"""

from __future__ import annotations

from concilium.infrastructure.observability.silver_normalizer import normalize_span_record


class TestNormalizeSpanRecordEnrichedFields:
    def test_passes_through_tool_name_user_id_request_id(self):
        record = {
            "span_id": "s1",
            "trace_id": "t1",
            "operation": "mcp.tool.listar_projetos",
            "tool_name": "listar_projetos",
            "user_id": "AGIS-user-1",
            "request_id": "req-abc123",
        }

        result = normalize_span_record(record)

        assert result["tool_name"] == "listar_projetos"
        assert result["user_id"] == "AGIS-user-1"
        assert result["request_id"] == "req-abc123"

    def test_fields_default_to_none_when_absent(self):
        record = {"span_id": "s1", "trace_id": "t1", "operation": "concilium.skill.05"}

        result = normalize_span_record(record)

        assert result["tool_name"] is None
        assert result["user_id"] is None
        assert result["request_id"] is None
