"""Tests for several small modules to boost coverage."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ─── API routes/system ──────────────────────────────────────────────────────


class TestSystemRoutes:
    def test_health_returns_ok(self):
        from concilium.presentation.api.routes.system import health

        result = health()
        assert result["status"] in ("ok", "degraded")
        assert "storage" in result
        assert result["storage"]["status"] in ("ok", "error")

    def test_root_redirects(self):
        from fastapi.responses import RedirectResponse

        from concilium.presentation.api.routes.system import root

        result = root()
        assert isinstance(result, RedirectResponse)

    def test_health_storage_exception_returns_degraded(self):
        from concilium.presentation.api.routes.system import health

        with patch("concilium.infrastructure.storage.store_factory.build_blob_storage") as mock_build:
            mock_build.side_effect = RuntimeError("storage unreachable")
            result = health()
        assert result["status"] == "degraded"
        assert result["storage"]["status"] == "error"
        assert "storage unreachable" in result["storage"]["message"]

    def test_reload_catalog_handles_exception(self):
        from concilium.presentation.api.routes.system import reload_catalog

        with patch("concilium.presentation.api.routes.system.ServiceContainer") as mock_sc:
            mock_sc.instance.side_effect = Exception("no container")
            result = reload_catalog()
        assert result["status"] == "error"
        assert "message" in result

    def test_reload_catalog_happy_path(self):
        from concilium.presentation.api.routes.system import reload_catalog

        mock_runtime = MagicMock()
        mock_runtime._config_cache = {"catalogo:x": 1, "other": 2}
        mock_container = MagicMock()
        mock_container.concilium_service._dependencies.pipeline_service._runtime_factory.return_value = mock_runtime
        mock_cfg_path = MagicMock()
        mock_cfg_path.rglob.return_value = []
        with (
            patch("concilium.presentation.api.routes.system.ServiceContainer") as mock_sc,
            patch("concilium.presentation.cli.shared.config_root", return_value=mock_cfg_path),
        ):
            mock_sc.instance.return_value = mock_container
            result = reload_catalog()
        assert result["status"] == "ok"
        assert result["catalog_cache_keys_cleared"] == 1

    def test_reload_catalog_deletes_bundles_on_disk(self):
        from concilium.presentation.api.routes.system import reload_catalog

        mock_runtime = MagicMock()
        mock_runtime._config_cache = {"catalogo:x": 1}
        mock_container = MagicMock()
        mock_container.concilium_service._dependencies.pipeline_service._runtime_factory.return_value = mock_runtime

        bundle_path = MagicMock()
        bundle_path.relative_to.return_value = "catalogos/cat1/.catalog_bundle.json"

        mock_cfg_path = MagicMock()
        mock_cfg_path.rglob.return_value = [bundle_path]
        with (
            patch("concilium.presentation.api.routes.system.ServiceContainer") as mock_sc,
            patch("concilium.presentation.cli.shared.config_root", return_value=mock_cfg_path),
        ):
            mock_sc.instance.return_value = mock_container
            result = reload_catalog()
        assert result["status"] == "ok"
        bundle_path.unlink.assert_called_once_with(missing_ok=True)
        assert result["bundles_deleted"] == ["catalogos/cat1/.catalog_bundle.json"]


class TestReloadCatalogAttributeChain:
    def test_dependencies_attribute_chain_exists_on_real_classes(self):
        """Regressão: o endpoint usava container.concilium_service.deps (atributo
        inexistente — o real é _dependencies), então /catalog/reload sempre caía
        no except e devolvia status=error. O mock de MagicMock engolia o erro."""
        import inspect

        from concilium.application.services.concilium_service import ConciliumDependencies, ConciliumService
        from concilium.presentation.api.routes.system import reload_catalog

        source = inspect.getsource(reload_catalog)
        assert ".deps." not in source, "endpoint referencia .deps, que não existe em ConciliumService"
        assert "_dependencies" in source

        # O atributo real existe na classe e o campo pipeline_service existe no container de deps
        assert "pipeline_service" in {f.name for f in ConciliumDependencies.__dataclass_fields__.values()} or hasattr(
            ConciliumDependencies, "pipeline_service"
        )
        assert not hasattr(ConciliumService, "deps")



