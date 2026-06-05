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
    def create_contexto_version(
        self,
        contexto_id: str,
        fields: dict,
        motivo: str,
        *,
        author: str,
        make_current: bool | None,
    ):
        assert contexto_id == "mendeslobo"
        assert motivo == "ajuste"
        assert author == "tester"
        assert make_current is False
        assert fields == {"catalogo_id": "cat_v2", "tema_id": "tema_x"}
        return {"version": "v2", "id": contexto_id}


def test_contexto_create_version_accepts_typed_top_level_and_make_current_alias():
    app = create_app()
    app.dependency_overrides[get_concilium_service] = lambda: _FakeService()
    client = TestClient(app)

    response = client.post(
        "/api/contextos/mendeslobo/versions",
        json={
            "motivo": "ajuste",
            "catalogo_id": "cat_v2",
            "tema_id": "tema_x",
            "_make_current": False,
        },
        headers={"X-User": "tester"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "v2"


def test_perfil_create_version_rejects_invalid_range_contract():
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/api/perfis/mendeslobo/versions",
        json={
            "motivo": "ajuste",
            "faixa_margem_alvo": {"min": 0.2, "max": 0.1},
        },
        headers={"X-User": "tester"},
    )

    assert response.status_code == 422
