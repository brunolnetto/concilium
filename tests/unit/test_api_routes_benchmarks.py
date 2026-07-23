"""Tests for formulario route, mcp/__main__, api/routes/benchmarks, concilium_service gaps."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# ─── presentation/api/routes/benchmarks.py (6 missing: 76-77, 104-107) ────────


class TestBenchmarkRoutes:
    def _client(self, svc=None):
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient

        try:
            from concilium.presentation.api.app import create_app
            from concilium.presentation.api.container import get_concilium_service
        except TypeError:
            pytest.skip("FastAPI incompatível")
        app = create_app()
        if svc:
            app.dependency_overrides[get_concilium_service] = lambda: svc
        return TestClient(app, raise_server_exceptions=False)

    def test_run_benchmark_not_found(self):
        svc = MagicMock()
        svc.run_benchmark.side_effect = FileNotFoundError("not found")
        c = self._client(svc)
        resp = c.post("/api/benchmarks/AGIS/run", json={})
        assert resp.status_code == 404

    def test_get_benchmark_report_not_found(self):
        svc = MagicMock()
        svc.get_benchmark_report.side_effect = FileNotFoundError("not found")
        c = self._client(svc)
        resp = c.get("/api/benchmarks/AGIS/report")
        assert resp.status_code == 404



