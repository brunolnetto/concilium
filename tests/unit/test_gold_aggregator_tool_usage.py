"""Testes para GoldAggregator.build_tool_usage_diario (ADR-147 D7 — decisão de
relatório Gold para CuboMetricas, primeiro consumidor real de metrics em Gold)."""

from __future__ import annotations

import pytest

from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage
from concilium.infrastructure.observability.gold_aggregator import GoldAggregator
from concilium.infrastructure.observability.pipeline import ObservabilityWorker
from concilium.infrastructure.observability.silver_normalizer import normalize_metric_record


@pytest.fixture
def storage(tmp_path):
    return LocalBlobStorage(tmp_path)


def _seed_silver_metrics(worker: ObservabilityWorker, records: list[dict], date: str = "2026-07-21") -> None:
    normalized = [normalize_metric_record(r) for r in records]
    worker._upsert_silver("metrics", normalized, date)


def _metric(tool_name: str, status: str, ts: str = "2026-07-21T10:00:00.000000Z", value: float = 1.0) -> dict:
    return {
        "metric_name": "concilium.mcp.tool.calls",
        "ts": ts,
        "value": value,
        "labels": {"tool": tool_name, "status": status},
        "service": "concilium",
    }


class TestBuildToolUsageDiario:
    def test_sums_calls_per_date_tool_status(self, storage):
        """`n` soma `value`, não conta linhas — cada data point de um Counter já é a
        soma de um intervalo de coleta, daí ts distintos por registro aqui: dois
        registros com o MESMO (ts, metric_name, labels) são o mesmo data point
        reprocessado (dedup do gap 4), não duas chamadas — bug do teste, não do código."""
        worker = ObservabilityWorker(storage)
        _seed_silver_metrics(
            worker,
            [
                _metric("listar_projetos", "OK", ts="2026-07-21T10:00:00.000000Z", value=1.0),
                _metric("listar_projetos", "OK", ts="2026-07-21T10:05:00.000000Z", value=2.0),
                _metric("listar_projetos", "ERROR", ts="2026-07-21T10:10:00.000000Z"),
                _metric("criar_projeto", "OK", ts="2026-07-21T10:15:00.000000Z"),
            ],
        )

        rows = GoldAggregator(storage).build_tool_usage_diario()

        by_key = {(r["tool_name"], r["status"]): r["n"] for r in rows}
        assert by_key[("listar_projetos", "OK")] == 3.0
        assert by_key[("listar_projetos", "ERROR")] == 1.0
        assert by_key[("criar_projeto", "OK")] == 1.0

    def test_ignores_metrics_other_than_tool_calls(self, storage):
        """Só concilium.mcp.tool.calls tem tool_name+status — outras métricas (ex. skill.duration_ms) não entram."""
        worker = ObservabilityWorker(storage)
        _seed_silver_metrics(
            worker,
            [
                _metric("listar_projetos", "OK"),
                {
                    "metric_name": "concilium.pipeline.skill.duration_ms",
                    "ts": "2026-07-21T10:00:00.000000Z",
                    "value": 120.0,
                    "labels": {"skill": "05", "status": "OK"},
                    "service": "concilium",
                },
            ],
        )

        rows = GoldAggregator(storage).build_tool_usage_diario()

        assert len(rows) == 1
        assert rows[0]["tool_name"] == "listar_projetos"

    def test_empty_silver_returns_empty_list(self, storage):
        rows = GoldAggregator(storage).build_tool_usage_diario()
        assert rows == []

    def test_write_gold_persists_tool_usage_diario(self, storage):
        worker = ObservabilityWorker(storage)
        _seed_silver_metrics(worker, [_metric("listar_projetos", "OK")])

        paths = GoldAggregator(storage).write_gold()

        assert "tool_usage_diario" in paths
        assert storage.ler_blob(paths["tool_usage_diario"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])






from unittest.mock import MagicMock  # noqa: E402

# gold_aggregator.py lines 39-40: _read_silver except block when ler_blob raises
# ---------------------------------------------------------------------------


class TestGoldAggregatorReadSilverException:
    def test_exception_in_ler_blob_is_swallowed(self):
        """Lines 39-40: ler_blob raises → except Exception: pass → returns []."""
        from concilium.infrastructure.observability.gold_aggregator import GoldAggregator

        storage = MagicMock()
        storage.listar_blobs.return_value = ["observability/silver/traces/file.jsonl"]
        storage.ler_blob.side_effect = OSError("Simulated read failure")

        agg = GoldAggregator(storage)
        records = agg._read_silver("traces")

        assert records == []

    def test_invalid_json_in_line_is_swallowed(self):
        """Lines 39-40: ler_blob returns invalid JSON → json.loads raises → except: pass."""
        from concilium.infrastructure.observability.gold_aggregator import GoldAggregator

        storage = MagicMock()
        storage.listar_blobs.return_value = ["observability/silver/traces/file.jsonl"]
        storage.ler_blob.return_value = b"NOTJSON{{{invalid\n"

        agg = GoldAggregator(storage)
        records = agg._read_silver("traces")

        assert records == []


# ---------------------------------------------------------------------------

