"""Testes da API de projeção dos cubos Gold (ADR-147 — expor via API, padrão
/cubo-analitico/projecao + /projecao/contrato, ADR-087/093).

Diferença deliberada de .query() interno (GoldAggregator/CrossDomainBuilder):
group_by/medidas aqui vêm de query params do cliente, então são validados contra
um whitelist por cubo (_CUBO_DIMENSOES/_CUBO_MEDIDAS) em vez de aceitar SQL bruto
— nenhuma expressão de agregação chega do cliente, só nomes de preset.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.slow  # create_app() por fixture = ~3.5s por teste


@pytest.fixture(scope="module")
def _cubo_api_app():
    from concilium.presentation.api.app import create_app

    with (
        patch("concilium.presentation.api.app.setup_telemetry"),
        patch("concilium.presentation.api.app.configure_logging"),
    ):
        app = create_app()
    yield app


@pytest.fixture
def storage(tmp_path):
    from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage

    return LocalBlobStorage(tmp_path)


@pytest.fixture
def client(_cubo_api_app, storage):
    from concilium.presentation.api.routes.observability import _get_storage

    _cubo_api_app.dependency_overrides[_get_storage] = lambda: storage
    with TestClient(_cubo_api_app, raise_server_exceptions=True) as c:
        yield c
    _cubo_api_app.dependency_overrides.pop(_get_storage, None)


def _seed_silver_traces(storage, records):
    from concilium.infrastructure.observability.pipeline import ObservabilityWorker
    from concilium.infrastructure.observability.silver_normalizer import normalize_span_record

    worker = ObservabilityWorker(storage)
    worker._upsert_silver("traces", [normalize_span_record(r) for r in records], "2026-07-21")


def _seed_silver_metrics(storage, records):
    from concilium.infrastructure.observability.pipeline import ObservabilityWorker
    from concilium.infrastructure.observability.silver_normalizer import normalize_metric_record

    worker = ObservabilityWorker(storage)
    worker._upsert_silver("metrics", [normalize_metric_record(r) for r in records], "2026-07-21")


# ── /observability/gold/tool-usage ────────────────────────────────────────────


class TestToolUsageEndpoint:
    def test_returns_paginated_usage(self, client, storage):
        _seed_silver_metrics(
            storage,
            [
                {
                    "metric_name": "concilium.mcp.tool.calls",
                    "ts": "2026-07-21T10:00:00Z",
                    "value": 2.0,
                    "labels": {"tool": "listar_projetos", "status": "OK"},
                },
                {
                    "metric_name": "concilium.mcp.tool.calls",
                    "ts": "2026-07-21T10:05:00Z",
                    "value": 1.0,
                    "labels": {"tool": "listar_projetos", "status": "ERROR"},
                },
            ],
        )

        resp = client.get("/observability/gold/tool-usage")

        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 2

    def test_filter_by_status(self, client, storage):
        _seed_silver_metrics(
            storage,
            [
                {
                    "metric_name": "concilium.mcp.tool.calls",
                    "ts": "2026-07-21T10:00:00Z",
                    "value": 1.0,
                    "labels": {"tool": "a", "status": "OK"},
                },
                {
                    "metric_name": "concilium.mcp.tool.calls",
                    "ts": "2026-07-21T10:05:00Z",
                    "value": 1.0,
                    "labels": {"tool": "b", "status": "ERROR"},
                },
            ],
        )

        resp = client.get("/observability/gold/tool-usage", params={"status": "ERROR"})

        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["status"] == "ERROR"

    def test_empty_silver_returns_empty_items(self, client):
        resp = client.get("/observability/gold/tool-usage")

        assert resp.status_code == 200
        assert resp.json()["items"] == []


# ── /observability/gold/cubo/contrato ─────────────────────────────────────────


class TestCuboContrato:
    def test_lists_all_four_cubos(self, client):
        resp = client.get("/observability/gold/cubo/contrato")

        assert resp.status_code == 200
        cubos = resp.json()["cubos"]
        assert set(cubos.keys()) == {"spans", "logs", "metricas", "tool_invocations"}

    def test_spans_contrato_has_expected_dimensoes_e_medidas(self, client):
        resp = client.get("/observability/gold/cubo/contrato")

        spans = resp.json()["cubos"]["spans"]
        assert "skill_id" in spans["dimensoes"]
        assert "p95_ms" in spans["medidas"]


# ── /observability/gold/cubo/{cubo}/projecao ──────────────────────────────────


class TestCuboProjecaoSpans:
    def test_group_by_skill_with_percentile(self, client, storage):
        _seed_silver_traces(
            storage,
            [
                {
                    "span_id": "s1",
                    "trace_id": "t1",
                    "start_ts": "2026-07-21T10:00:00.000000Z",
                    "duration_ms": 100,
                    "status": "OK",
                    "skill_id": "05",
                },
                {
                    "span_id": "s2",
                    "trace_id": "t1",
                    "start_ts": "2026-07-21T10:00:00.000000Z",
                    "duration_ms": 200,
                    "status": "OK",
                    "skill_id": "05",
                },
            ],
        )

        resp = client.get(
            "/observability/gold/cubo/spans/projecao",
            params={"group_by": "skill_id", "medidas": "p50_ms,n"},
        )

        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["skill_id"] == "05"
        assert items[0]["p50_ms"] == 150
        assert items[0]["n"] == 2

    def test_filter_by_status(self, client, storage):
        _seed_silver_traces(
            storage,
            [
                {
                    "span_id": "s1",
                    "trace_id": "t1",
                    "start_ts": "2026-07-21T10:00:00Z",
                    "duration_ms": 100,
                    "status": "OK",
                },
                {
                    "span_id": "s2",
                    "trace_id": "t1",
                    "start_ts": "2026-07-21T10:00:00Z",
                    "duration_ms": 500,
                    "status": "ERROR",
                },
            ],
        )

        resp = client.get(
            "/observability/gold/cubo/spans/projecao",
            params={"group_by": "status", "medidas": "n", "status": "ERROR"},
        )

        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["status"] == "ERROR"
        assert items[0]["n"] == 1

    def test_invalid_dimension_returns_400(self, client):
        resp = client.get(
            "/observability/gold/cubo/spans/projecao",
            params={"group_by": "campo_inexistente", "medidas": "n"},
        )

        assert resp.status_code == 400
        assert "campo_inexistente" in resp.json()["detail"]

    def test_invalid_medida_returns_400(self, client):
        resp = client.get(
            "/observability/gold/cubo/spans/projecao",
            params={"group_by": "skill_id", "medidas": "medida_inexistente"},
        )

        assert resp.status_code == 400
        assert "medida_inexistente" in resp.json()["detail"]

    def test_invalid_cubo_name_returns_422(self, client):
        resp = client.get(
            "/observability/gold/cubo/nao_existe/projecao",
            params={"group_by": "date", "medidas": "n"},
        )

        assert resp.status_code == 422  # FastAPI Literal validation

    def test_empty_silver_returns_empty_items(self, client):
        resp = client.get(
            "/observability/gold/cubo/spans/projecao",
            params={"group_by": "skill_id", "medidas": "n"},
        )

        assert resp.status_code == 200
        assert resp.json()["items"] == []


class TestCuboProjecaoMetricas:
    def test_group_by_tool_and_status(self, client, storage):
        _seed_silver_metrics(
            storage,
            [
                {
                    "metric_name": "concilium.mcp.tool.calls",
                    "ts": "2026-07-21T10:00:00Z",
                    "value": 3.0,
                    "labels": {"tool": "listar_projetos", "status": "OK"},
                },
                {
                    "metric_name": "concilium.mcp.tool.calls",
                    "ts": "2026-07-21T10:05:00Z",
                    "value": 1.0,
                    "labels": {"tool": "listar_projetos", "status": "ERROR"},
                },
            ],
        )

        resp = client.get(
            "/observability/gold/cubo/metricas/projecao",
            params={"group_by": "tool_name,status", "medidas": "sum_value"},
        )

        by_status = {r["status"]: r["sum_value"] for r in resp.json()["items"]}
        assert by_status["OK"] == 3.0
        assert by_status["ERROR"] == 1.0

    def test_filter_by_metric_name_and_project(self, client, storage):
        _seed_silver_metrics(
            storage,
            [
                {
                    "metric_name": "concilium.mcp.tool.calls",
                    "ts": "2026-07-21T10:00:00Z",
                    "value": 1.0,
                    "labels": {"tool": "a", "project.id": "AGIS"},
                },
                {
                    "metric_name": "concilium.pipeline.skill.duration_ms",
                    "ts": "2026-07-21T10:00:00Z",
                    "value": 120.0,
                    "labels": {"skill": "05", "project.id": "AGIS"},
                },
            ],
        )

        resp = client.get(
            "/observability/gold/cubo/metricas/projecao",
            params={
                "group_by": "metric_name",
                "medidas": "n",
                "metric_name": "concilium.mcp.tool.calls",
                "project_id": "AGIS",
            },
        )

        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["metric_name"] == "concilium.mcp.tool.calls"


class TestCuboProjecaoPagination:
    def test_pagination_params_applied(self, client, storage):
        _seed_silver_traces(
            storage,
            [
                {
                    "span_id": f"s{i}",
                    "trace_id": "t1",
                    "start_ts": "2026-07-21T10:00:00Z",
                    "duration_ms": 100,
                    "status": "OK",
                    "skill_id": str(i).zfill(2),
                }
                for i in range(5)
            ],
        )

        resp = client.get(
            "/observability/gold/cubo/spans/projecao",
            params={"group_by": "skill_id", "medidas": "n", "page": 1, "page_size": 2},
        )

        body = resp.json()
        assert len(body["items"]) == 2
        assert body["total"] == 5
        assert body["pages"] == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
