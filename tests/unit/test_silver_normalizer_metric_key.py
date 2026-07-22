"""Testes para a chave estável de dedup em normalize_metric_record (gap 4, ERD Gold).

Antes deste fix, record_key() caía no fallback `ts + metric_name` para metrics
(sem event_id/span_id) — duas séries do MESMO metric com labels DIFERENTES
caindo na mesma coleta periódica (mesmo ts) colidiam silenciosamente em
dedupe_records(), perdendo uma das duas. concilium.mcp.tool.calls com dois
tools distintos no mesmo ciclo é o caso real mais provável.
"""

from __future__ import annotations

from concilium.infrastructure.observability.silver_normalizer import (
    dedupe_records,
    normalize_metric_record,
    record_key,
)


def _bronze_metric(metric_name="concilium.mcp.tool.calls", ts="2026-07-21T10:00:00.000000Z", labels=None, value=1.0):
    return {
        "metric_name": metric_name,
        "ts": ts,
        "value": value,
        "labels": labels or {},
        "service": "concilium",
    }


class TestNormalizeMetricRecordEventId:
    def test_same_ts_and_metric_name_different_labels_get_different_event_id(self):
        a = normalize_metric_record(_bronze_metric(labels={"tool": "listar_projetos", "status": "OK"}))
        b = normalize_metric_record(_bronze_metric(labels={"tool": "criar_projeto", "status": "OK"}))

        assert a["event_id"] != b["event_id"]

    def test_same_input_is_idempotent(self):
        """Reprocessar o mesmo blob Bronze (backfill, replay) deve gerar o mesmo event_id."""
        record = _bronze_metric(labels={"tool": "ping", "status": "OK"})

        first = normalize_metric_record(record)
        second = normalize_metric_record(record)

        assert first["event_id"] == second["event_id"]

    def test_label_order_does_not_affect_event_id(self):
        a = normalize_metric_record(_bronze_metric(labels={"tool": "ping", "status": "OK"}))
        b = normalize_metric_record(_bronze_metric(labels={"status": "OK", "tool": "ping"}))

        assert a["event_id"] == b["event_id"]

    def test_different_ts_get_different_event_id(self):
        a = normalize_metric_record(_bronze_metric(ts="2026-07-21T10:00:00.000000Z"))
        b = normalize_metric_record(_bronze_metric(ts="2026-07-21T10:05:00.000000Z"))

        assert a["event_id"] != b["event_id"]

    def test_existing_schema_fields_preserved(self):
        result = normalize_metric_record(_bronze_metric(value=42.0))

        assert result["metric_name"] == "concilium.mcp.tool.calls"
        assert result["ts"] == "2026-07-21T10:00:00.000000Z"
        assert result["value"] == 42.0
        assert result["service"] == "concilium"


class TestRecordKeyUsesMetricEventId:
    def test_record_key_returns_event_id(self):
        result = normalize_metric_record(_bronze_metric(labels={"tool": "ping"}))

        assert record_key(result) == result["event_id"]


class TestDedupeRecordsNoLongerCollidesOnLabels:
    def test_two_distinct_label_combinations_at_same_ts_both_survive(self):
        """O bug real: sem este fix, os dois data points abaixo colapsavam em um só."""
        records = [
            normalize_metric_record(_bronze_metric(labels={"tool": "listar_projetos"}, value=3.0)),
            normalize_metric_record(_bronze_metric(labels={"tool": "criar_projeto"}, value=7.0)),
        ]

        deduped = dedupe_records(records)

        assert len(deduped) == 2
        values = {r["labels"]["tool"]: r["value"] for r in deduped}
        assert values == {"listar_projetos": 3.0, "criar_projeto": 7.0}

    def test_true_duplicate_still_collapses_to_one(self):
        """Mesmo (ts, metric_name, labels) reprocessado — dedup ainda deve colapsar."""
        record = _bronze_metric(labels={"tool": "ping"})
        records = [normalize_metric_record(record), normalize_metric_record(record)]

        deduped = dedupe_records(records)

        assert len(deduped) == 1
