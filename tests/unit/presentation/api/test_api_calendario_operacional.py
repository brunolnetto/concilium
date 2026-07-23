from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi", reason="fastapi nao instalado")
from fastapi.testclient import TestClient  # noqa: E402

try:
    from concilium.presentation.api.app import create_app
    from concilium.presentation.api.container import get_concilium_service
except TypeError as exc:
    pytest.skip(f"Ambiente FastAPI incompatível: {exc}", allow_module_level=True)

_app_cache: list = []


def _get_app():
    if not _app_cache:
        _app_cache.append(create_app())
    return _app_cache[0]


class _FakeService:
    def get_calendario_operacional(self, project_id: str, version: str | None = None):
        assert project_id == "proj-123"
        return {
            "version": version or "v1",
            "semanas": [
                {
                    "semana_iso": "2026-W23",
                    "fator_clima": 0.8,
                    "fator_calendario": 0.9,
                    "fator_total": 0.72,
                }
            ],
        }

    def simulate_calendario_operacional(self, project_id: str, payload: dict, version: str | None = None):
        assert payload["fator_calendario_semanal"]["2026-W23"] == 0.5
        return {
            "version": version or "v1",
            "simulado": [{"semana_iso": "2026-W23", "fator_total": 0.4}],
        }


def test_get_calendario_operacional():
    app = _get_app()
    app.dependency_overrides[get_concilium_service] = lambda: _FakeService()
    client = TestClient(app)

    resp = client.get("/api/projects/proj-123/calendario-operacional")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == "v1"
    assert body["semanas"][0]["fator_total"] == 0.72


def test_post_simular_calendario_operacional():
    app = _get_app()
    app.dependency_overrides[get_concilium_service] = lambda: _FakeService()
    client = TestClient(app)

    resp = client.post(
        "/api/projects/proj-123/calendario-operacional/simular",
        json={"fator_calendario_semanal": {"2026-W23": 0.5}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["simulado"][0]["fator_total"] == 0.4
