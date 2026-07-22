"""Testes para silver_normalizer.normalize_tool_invocation_record (ADR-112 extensão).

Schema de saída usa "event_id" (não "id") deliberadamente — reaproveita o
fallback já existente em silver_normalizer.record_key()/dedupe_records(), que
prioriza "event_id" para dedup entre arquivos Silver. Sem esse mapeamento,
tool_invocations cairia no fallback genérico (str(id(rec))), que nunca dedupa
nada — cada leitura geraria uma chave diferente.
"""

from __future__ import annotations

from concilium.infrastructure.observability.silver_normalizer import (
    normalize_tool_invocation_record,
    record_key,
)


class TestNormalizeToolInvocationRecord:
    def test_maps_all_fields(self):
        record = {
            "id": "inv-1",
            "tool_name": "listar_projetos",
            "user_id": "AGIS-user-1",
            "tenant_id": "tenant-x",
            "status": "success",
            "started_at": "2026-07-20T10:00:00Z",
            "finished_at": "2026-07-20T10:00:01Z",
            "error_type": None,
            "device_id": "device-1",
            "mcp_session_id": "sess-abc",
        }

        result = normalize_tool_invocation_record(record)

        assert result["event_id"] == "inv-1"
        assert result["tool_name"] == "listar_projetos"
        assert result["user_id"] == "AGIS-user-1"
        assert result["tenant_id"] == "tenant-x"
        assert result["status"] == "success"
        assert result["started_at"] == "2026-07-20T10:00:00Z"
        assert result["finished_at"] == "2026-07-20T10:00:01Z"
        assert result["error_type"] is None
        assert result["device_id"] == "device-1"
        assert result["mcp_session_id"] == "sess-abc"

    def test_defaults_for_missing_optional_fields(self):
        record = {"id": "inv-2", "tool_name": "ping", "status": "success"}

        result = normalize_tool_invocation_record(record)

        assert result["user_id"] is None
        assert result["tenant_id"] is None
        assert result["error_type"] is None
        assert result["device_id"] is None
        assert result["mcp_session_id"] is None

    def test_event_id_feeds_existing_dedup_key(self):
        """record_key() já prioriza event_id — sem reimplementar dedup para este sinal."""
        record = {"id": "inv-3", "tool_name": "ping", "status": "success"}

        result = normalize_tool_invocation_record(record)

        assert record_key(result) == "inv-3"
