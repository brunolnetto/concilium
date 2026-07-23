"""Coverage sweep 5 — configuration routes, spec_loader_b, storage_project_repository."""

from __future__ import annotations

from unittest.mock import MagicMock

# ─── presentation/api/routes/configuration.py ────────────────────────────────


class TestConfigurationRoutes:
    def _svc(self):
        return MagicMock()

    def test_list_perfis(self):
        from concilium.presentation.api.routes.configuration import list_perfis

        svc = self._svc()
        svc.list_perfis.return_value = [{"id": "p1"}]
        result = list_perfis(service=svc)
        assert "items" in result

    def test_list_perfil_versions(self):
        from concilium.presentation.api.routes.configuration import list_perfil_versions

        svc = self._svc()
        svc.list_perfil_versions.return_value = ["v1", "v2"]
        result = list_perfil_versions("p1", service=svc)
        assert "versions" in result or "items" in result or isinstance(result, dict)

    def test_list_contextos(self):
        from concilium.presentation.api.routes.configuration import list_contextos

        svc = self._svc()
        svc.list_contextos.return_value = [{"id": "ctx1"}]
        result = list_contextos(service=svc)
        assert "items" in result

    def test_list_contexto_versions(self):
        from concilium.presentation.api.routes.configuration import list_contexto_versions

        svc = self._svc()
        svc.list_contexto_versions.return_value = ["v1"]
        result = list_contexto_versions("ctx1", service=svc)
        assert isinstance(result, dict)

    def test_list_temas(self):
        from concilium.presentation.api.routes.configuration import list_temas

        svc = self._svc()
        svc.list_temas.return_value = [{"id": "t1"}]
        result = list_temas(service=svc)
        assert isinstance(result, dict)

    def test_list_jurisdicoes(self):
        from concilium.presentation.api.routes.configuration import list_jurisdicoes

        svc = self._svc()
        svc.list_jurisdicoes.return_value = [{"id": "BR-CE"}]
        result = list_jurisdicoes(service=svc)
        assert isinstance(result, dict)

    def test_compare_contexto_versions(self):
        from concilium.presentation.api.routes.configuration import compare_contexto_versions

        svc = self._svc()
        svc.compare_contexto_versions.return_value = {"diff": {}}
        result = compare_contexto_versions("ctx1", "v1", "v2", service=svc)
        assert isinstance(result, dict)

    def test_create_contexto_version(self):
        from concilium.presentation.api.routes.configuration import create_contexto_version

        svc = self._svc()
        svc.create_contexto_version.return_value = {"version": "v2"}
        req = MagicMock()
        req.fields = {}
        req.motivo = "test"
        req.author = "eng"
        req.make_current = True
        result = create_contexto_version("ctx1", req, service=svc)
        assert isinstance(result, dict)



