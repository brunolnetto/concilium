"""Tests for API routes/configuration.py."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi", reason="fastapi not installed")
from fastapi.testclient import TestClient  # noqa: E402

try:
    from concilium.presentation.api.app import create_app
    from concilium.presentation.api.container import get_concilium_service
except TypeError as exc:
    pytest.skip(f"FastAPI incompatível: {exc}", allow_module_level=True)


class _FakeSvc:
    def list_perfis(self):
        return [{"perfil_id": "p1", "nome": "Test"}]

    def list_perfil_versions(self, perfil_id):
        return [{"version": "v1"}]

    def create_perfil_version(self, perfil_id, fields, motivo, author="system", make_current=True):
        return {"perfil_id": perfil_id, "version": "v2", "motivo": motivo}

    def compare_perfil_versions(self, perfil_id, va, vb):
        return {
            "entity_id": perfil_id,
            "subdir": "perfis",
            "version_a": va,
            "version_b": vb,
            "changed": {},
            "unchanged": [],
        }

    def list_contextos(self):
        return [{"contexto_id": "ctx1"}]

    def list_contexto_versions(self, contexto_id):
        return [{"version": "v1"}]

    def create_contexto_version(self, contexto_id, fields, motivo, author="system", make_current=True):
        return {"contexto_id": contexto_id, "version": "v2"}

    def compare_contexto_versions(self, contexto_id, va, vb):
        return {
            "entity_id": contexto_id,
            "subdir": "contextos",
            "version_a": va,
            "version_b": vb,
            "changed": {},
            "unchanged": [],
        }

    def list_temas(self):
        return [{"tema_id": "t1"}]

    def list_tema_versions(self, tema_id):
        return [{"version": "v1"}]

    def create_tema_version(self, tema_id, fields, motivo, author="system", make_current=True):
        return {"tema_id": tema_id, "version": "v2"}

    def compare_tema_versions(self, tema_id, va, vb):
        return {
            "entity_id": tema_id,
            "subdir": "temas",
            "version_a": va,
            "version_b": vb,
            "changed": {},
            "unchanged": [],
        }

    def list_jurisdicoes(self):
        return [{"jurisdicao_id": "j1"}]

    def list_jurisdicao_versions(self, jurisdicao_id):
        return [{"version": "v1"}]

    def create_jurisdicao_version(self, jurisdicao_id, fields, motivo, author="system", make_current=True):
        return {"jurisdicao_id": jurisdicao_id, "version": "v2"}

    def compare_jurisdicao_versions(self, jurisdicao_id, va, vb):
        return {
            "entity_id": jurisdicao_id,
            "subdir": "jurisdicoes",
            "version_a": va,
            "version_b": vb,
            "changed": {},
            "unchanged": [],
        }


class _ErrorSvc(_FakeSvc):
    def create_perfil_version(self, *a, **kw):
        raise ValueError("invalid")

    def create_contexto_version(self, *a, **kw):
        raise ValueError("invalid")

    def create_tema_version(self, *a, **kw):
        raise ValueError("invalid")

    def create_jurisdicao_version(self, *a, **kw):
        raise ValueError("invalid")


def _client(svc=None):
    app = create_app()
    app.dependency_overrides[get_concilium_service] = lambda: svc or _FakeSvc()
    return TestClient(app, raise_server_exceptions=False)


class TestPerfilRoutes:
    def test_list_perfis(self):
        c = _client()
        resp = c.get("/api/perfis")
        assert resp.status_code == 200
        assert "items" in resp.json()

    def test_list_perfil_versions(self):
        c = _client()
        resp = c.get("/api/perfis/p1/versions")
        assert resp.status_code == 200

    def test_create_perfil_version(self):
        c = _client()
        resp = c.post("/api/perfis/p1/versions", json={"motivo": "update"})
        assert resp.status_code == 200

    def test_create_perfil_version_error(self):
        c = _client(_ErrorSvc())
        resp = c.post("/api/perfis/p1/versions", json={"motivo": "bad"})
        assert resp.status_code == 400

    def test_compare_perfil_versions(self):
        c = _client()
        resp = c.get("/api/perfis/compare?id=p1&vA=v1&vB=v2")
        assert resp.status_code == 200


class TestContextoRoutes:
    def test_list_contextos(self):
        c = _client()
        resp = c.get("/api/contextos")
        assert resp.status_code == 200

    def test_list_contexto_versions(self):
        c = _client()
        resp = c.get("/api/contextos/ctx1/versions")
        assert resp.status_code == 200

    def test_create_contexto_version(self):
        c = _client()
        resp = c.post("/api/contextos/ctx1/versions", json={"motivo": "update"})
        assert resp.status_code == 200

    def test_create_contexto_version_error(self):
        c = _client(_ErrorSvc())
        resp = c.post("/api/contextos/ctx1/versions", json={"motivo": "bad"})
        assert resp.status_code == 400

    def test_compare_contexto_versions(self):
        c = _client()
        resp = c.get("/api/contextos/compare?id=ctx1&vA=v1&vB=v2")
        assert resp.status_code == 200


class TestTemaRoutes:
    def test_list_temas(self):
        c = _client()
        resp = c.get("/api/temas")
        assert resp.status_code == 200

    def test_list_tema_versions(self):
        c = _client()
        resp = c.get("/api/temas/t1/versions")
        assert resp.status_code == 200

    def test_create_tema_version(self):
        c = _client()
        resp = c.post("/api/temas/t1/versions", json={"motivo": "update"})
        assert resp.status_code == 200

    def test_create_tema_version_error(self):
        c = _client(_ErrorSvc())
        resp = c.post("/api/temas/t1/versions", json={"motivo": "bad"})
        assert resp.status_code == 400

    def test_compare_tema_versions(self):
        c = _client()
        resp = c.get("/api/temas/compare?id=t1&vA=v1&vB=v2")
        assert resp.status_code == 200


class TestJurisdictionRoutes:
    def test_list_jurisdicoes(self):
        c = _client()
        resp = c.get("/api/jurisdicoes")
        assert resp.status_code == 200

    def test_list_jurisdicao_versions(self):
        c = _client()
        resp = c.get("/api/jurisdicoes/j1/versions")
        assert resp.status_code == 200

    def test_create_jurisdicao_version(self):
        c = _client()
        resp = c.post("/api/jurisdicoes/j1/versions", json={"motivo": "update"})
        assert resp.status_code == 200

    def test_create_jurisdicao_version_error(self):
        c = _client(_ErrorSvc())
        resp = c.post("/api/jurisdicoes/j1/versions", json={"motivo": "bad"})
        assert resp.status_code == 400

    def test_compare_jurisdicao_versions(self):
        c = _client()
        resp = c.get("/api/jurisdicoes/compare?id=j1&vA=v1&vB=v2")
        assert resp.status_code == 200
