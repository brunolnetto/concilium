"""Testes das rotas de API de observabilidade — ADR-112 GET endpoints paginados."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.slow  # create_app() por fixture = ~3.5s por teste


@pytest.fixture
def storage(tmp_path):
    from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage

    return LocalBlobStorage(tmp_path)


@pytest.fixture
def client(storage):
    """TestClient com dependency_overrides para _get_storage → storage isolado.

    Mockamos setup_telemetry para evitar que PeriodicExportingMetricReader inicie
    threads de background que causam "I/O operation on closed file" ao encerrar pytest.
    """
    from concilium.presentation.api.app import create_app
    from concilium.presentation.api.routes.observability import _get_storage

    with (
        patch("concilium.presentation.api.app.setup_telemetry"),
        patch("concilium.presentation.api.app.configure_logging"),
    ):
        app = create_app()
    app.dependency_overrides[_get_storage] = lambda: storage
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


def _seed_silver_logs(storage, records):
    from concilium.infrastructure.observability.pipeline import ObservabilityWorker
    from concilium.infrastructure.observability.silver_normalizer import normalize_log_record

    worker = ObservabilityWorker(storage)
    worker._upsert_silver("logs", [normalize_log_record(r) for r in records])


def _seed_silver_traces(storage, records):
    from concilium.infrastructure.observability.pipeline import ObservabilityWorker
    from concilium.infrastructure.observability.silver_normalizer import normalize_span_record

    worker = ObservabilityWorker(storage)
    worker._upsert_silver("traces", [normalize_span_record(r) for r in records])


def _seed_bronze(storage, signal_type, records):
    from concilium.infrastructure.observability.bronze_writer import BronzeWriter

    BronzeWriter(storage, signal_type).write_batch(records, date="2026-06-19")


# ── /observability/status ─────────────────────────────────────────────────────


class TestStatusEndpoint:
    def test_status_returns_200(self, client):
        resp = client.get("/observability/status")
        assert resp.status_code == 200

    def test_status_has_checkpoints_key(self, client):
        data = client.get("/observability/status").json()
        assert "checkpoints" in data

    def test_status_shows_none_when_no_checkpoint(self, client):
        data = client.get("/observability/status").json()
        assert data["checkpoints"]["logs"] is None

    def test_status_shows_checkpoint_after_run(self, client, storage):
        from concilium.infrastructure.observability.checkpoint_store import Checkpoint, CheckpointStore

        CheckpointStore(storage).save(Checkpoint("logs", "path/batch.ndjson", "2026-06-19T10:00:00Z", 42))
        data = client.get("/observability/status").json()
        assert data["checkpoints"]["logs"]["records_processed"] == 42


# ── /observability/gold/sli ───────────────────────────────────────────────────


class TestGoldSLIEndpoint:
    def test_sli_returns_200(self, client):
        resp = client.get("/observability/gold/sli")
        assert resp.status_code == 200

    def test_sli_response_is_paginated(self, client):
        data = client.get("/observability/gold/sli").json()
        for key in ("items", "total", "page", "page_size", "pages"):
            assert key in data

    def test_sli_empty_when_no_data(self, client):
        data = client.get("/observability/gold/sli").json()
        assert data["total"] == 0

    def test_sli_returns_data_after_seeding(self, client, storage):
        _seed_silver_traces(
            storage,
            [
                {
                    "span_id": "t1",
                    "trace_id": "r1",
                    "parent_span_id": None,
                    "service": "c",
                    "operation": "concilium.skill.05",
                    "start_ts": "2026-06-19T10:00:00Z",
                    "end_ts": "2026-06-19T10:00:02Z",
                    "duration_ms": 2000,
                    "status": "OK",
                    "project_id": "AGIS",
                    "skill_id": "05",
                }
            ],
        )
        data = client.get("/observability/gold/sli").json()
        assert data["total"] >= 1
        assert data["items"][0]["skill_id"] == "05"

    def test_sli_filter_by_skill_id(self, client, storage):
        _seed_silver_traces(
            storage,
            [
                {
                    "span_id": "a",
                    "trace_id": "r1",
                    "parent_span_id": None,
                    "service": "c",
                    "operation": "concilium.skill.05",
                    "start_ts": "2026-06-19T10:00:00Z",
                    "end_ts": "2026-06-19T10:00:01Z",
                    "duration_ms": 1000,
                    "status": "OK",
                    "project_id": "AGIS",
                    "skill_id": "05",
                },
                {
                    "span_id": "b",
                    "trace_id": "r2",
                    "parent_span_id": None,
                    "service": "c",
                    "operation": "concilium.skill.06",
                    "start_ts": "2026-06-19T10:00:00Z",
                    "end_ts": "2026-06-19T10:00:02Z",
                    "duration_ms": 2000,
                    "status": "OK",
                    "project_id": "AGIS",
                    "skill_id": "06",
                },
            ],
        )
        data = client.get("/observability/gold/sli?skill_id=05").json()
        assert all(r["skill_id"] == "05" for r in data["items"])


# ── /observability/gold/fallback-rate ────────────────────────────────────────


class TestFallbackRateEndpoint:
    def test_fallback_rate_returns_200(self, client):
        assert client.get("/observability/gold/fallback-rate").status_code == 200

    def test_fallback_rate_paginated(self, client):
        data = client.get("/observability/gold/fallback-rate").json()
        assert "items" in data and "total" in data

    def test_fallback_rate_filter_by_min_rate(self, client, storage):
        _seed_silver_logs(
            storage,
            [
                {
                    "ts": "2026-06-19T10:00:00Z",
                    "severity": "WARNING",
                    "logger": "concilium.skills.06",
                    "message": "BDI sem taxa",
                    "trace_id": "",
                    "span_id": "l1",
                    "service": "c",
                },
            ],
        )
        data_all = client.get("/observability/gold/fallback-rate").json()
        data_filtered = client.get("/observability/gold/fallback-rate?min_rate=0.9").json()
        assert data_filtered["total"] <= data_all["total"]


# ── /observability/gold/alertas ───────────────────────────────────────────────


class TestAlertasEndpoint:
    def test_alertas_returns_200(self, client):
        assert client.get("/observability/gold/alertas").status_code == 200

    def test_alertas_has_total(self, client):
        data = client.get("/observability/gold/alertas").json()
        assert "total" in data and "alertas" in data

    def test_alertas_zero_when_nominal(self, client):
        data = client.get("/observability/gold/alertas").json()
        assert data["total"] == 0

    def test_alertas_filter_by_tipo(self, client):
        data = client.get("/observability/gold/alertas?tipo=p99_alto").json()
        assert all(a["tipo"] == "p99_alto" for a in data["alertas"])


# ── /observability/silver/{signal_type} ──────────────────────────────────────


class TestSilverEndpoint:
    def test_silver_logs_returns_200(self, client):
        assert client.get("/observability/silver/logs").status_code == 200

    def test_silver_invalid_signal_type_returns_400(self, client):
        assert client.get("/observability/silver/invalid").status_code == 400

    def test_silver_logs_paginated(self, client):
        data = client.get("/observability/silver/logs").json()
        assert "items" in data and "page" in data

    def test_silver_logs_shows_seeded_data(self, client, storage):
        _seed_silver_logs(
            storage,
            [
                {
                    "ts": "2026-06-19T10:00:00Z",
                    "severity": "WARNING",
                    "logger": "concilium.test",
                    "message": "BDI sem taxa",
                    "trace_id": "",
                    "span_id": "sl1",
                    "service": "c",
                },
            ],
        )
        data = client.get("/observability/silver/logs").json()
        assert data["total"] >= 1

    def test_silver_filter_by_fallback_type(self, client, storage):
        _seed_silver_logs(
            storage,
            [
                {
                    "ts": "2026-06-19T10:00:00Z",
                    "severity": "WARNING",
                    "logger": "x",
                    "message": "BDI sem taxa para 'mao_obra'",
                    "trace_id": "",
                    "span_id": "f1",
                    "service": "c",
                },
                {
                    "ts": "2026-06-19T10:00:01Z",
                    "severity": "INFO",
                    "logger": "x",
                    "message": "pipeline concluído",
                    "trace_id": "",
                    "span_id": "ok1",
                    "service": "c",
                },
            ],
        )
        data = client.get("/observability/silver/logs?fallback_type=bdi_ausente").json()
        assert data["total"] >= 1
        assert all(r.get("fallback_type") == "bdi_ausente" for r in data["items"])

    def test_silver_pagination_page_size(self, client, storage):
        for i in range(5):
            _seed_silver_logs(
                storage,
                [
                    {
                        "ts": f"2026-06-19T10:00:0{i}Z",
                        "severity": "INFO",
                        "logger": "x",
                        "message": f"msg {i}",
                        "trace_id": "",
                        "span_id": f"p{i}",
                        "service": "c",
                    }
                ],
            )
        data = client.get("/observability/silver/logs?page_size=2&page=1").json()
        assert len(data["items"]) <= 2
        assert data["pages"] >= 1


# ── /observability/bronze/{signal_type} ──────────────────────────────────────


class TestBronzeEndpoint:
    def test_bronze_logs_returns_200(self, client):
        assert client.get("/observability/bronze/logs").status_code == 200

    def test_bronze_invalid_signal_returns_400(self, client):
        assert client.get("/observability/bronze/xyz").status_code == 400

    def test_bronze_shows_raw_data(self, client, storage):
        _seed_bronze(storage, "logs", [{"severity": "WARNING", "message": "raw test", "ts": "2026-06-19T10:00:00Z"}])
        data = client.get("/observability/bronze/logs").json()
        assert data["total"] >= 1
        assert any("raw test" in str(r.get("message", "")) for r in data["items"])

    def test_bronze_filter_by_date(self, client, storage):
        _seed_bronze(storage, "logs", [{"msg": "today"}])
        data_today = client.get("/observability/bronze/logs?date=2026-06-19").json()
        data_other = client.get("/observability/bronze/logs?date=2020-01-01").json()
        assert data_today["total"] >= 1
        assert data_other["total"] == 0
