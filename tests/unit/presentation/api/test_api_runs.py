from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi", reason="fastapi nao instalado - pule este modulo de teste")
from fastapi.testclient import TestClient  # noqa: E402

try:
    from concilium.presentation.api.app import create_app
    from concilium.presentation.api.container import get_concilium_service
except TypeError as exc:  # FastAPI/Starlette version mismatch in local env
    pytest.skip(f"Ambiente FastAPI incompatível para teste de rota: {exc}", allow_module_level=True)


class _FakeService:
    def start_run_project(
        self,
        project_id: str,
        *,
        base_version: str | None,
        fork_version: bool,
        procurement_intent: str,
        skill_inputs_override: dict,
        use_saved_overrides: bool,
        use_mobilizacao_policy: bool,
        use_strict_catalog_baseline: bool,
        actor: str,
    ):
        assert project_id == "proj-123"
        assert actor == "tester"
        assert use_mobilizacao_policy is False
        assert use_strict_catalog_baseline is True
        return {
            "project_id": project_id,
            "run_id": "run-abc",
            "status": "queued",
            "procurement_intent": procurement_intent,
            "use_mobilizacao_policy": use_mobilizacao_policy,
            "use_strict_catalog_baseline": use_strict_catalog_baseline,
        }


def test_start_run_project_route_accepts_post_on_runs_start_path():
    app = create_app()
    app.dependency_overrides[get_concilium_service] = lambda: _FakeService()
    client = TestClient(app)

    response = client.post(
        "/api/projects/proj-123/runs/start",
        json={
            "base_version": "v1",
            "fork_version": True,
            "skill_inputs_override": {},
            "use_saved_overrides": True,
            "use_mobilizacao_policy": False,
            "use_strict_catalog_baseline": True,
        },
        headers={"X-User": "tester"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == "proj-123"
    assert body["run_id"] == "run-abc"
    assert body["status"] == "queued"
    assert body["use_mobilizacao_policy"] is False
    assert body["use_strict_catalog_baseline"] is True
