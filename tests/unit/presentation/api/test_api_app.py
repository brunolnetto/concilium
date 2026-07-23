"""Tests for formulario route, mcp/__main__, api/routes/benchmarks, concilium_service gaps."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ─── presentation/api/app.py — instrumentation, exception handlers, main() ────


class TestAppCreateAppGaps:
    def _create_app_with_telemetry(self, *, otel_sdk_disabled: bool):
        from unittest.mock import MagicMock

        telemetry_mock = MagicMock()
        telemetry_mock.otel_sdk_disabled = otel_sdk_disabled

        with (
            patch("concilium.presentation.api.app.setup_telemetry"),
            patch("concilium.presentation.api.app.configure_logging"),
            patch("concilium.presentation.api.app.get_telemetry", return_value=telemetry_mock),
        ):
            from concilium.presentation.api.app import create_app

            return create_app()

    def test_instrumentation_enabled_calls_instrument_app(self):
        """Lines 79-82: otel habilitado → FastAPIInstrumentor.instrument_app é chamado."""
        with patch("opentelemetry.instrumentation.fastapi.FastAPIInstrumentor.instrument_app") as mock_instrument:
            self._create_app_with_telemetry(otel_sdk_disabled=False)
        mock_instrument.assert_called_once()

    def test_instrumentation_import_error_is_swallowed(self):
        """Lines 83-84: ImportError na instrumentação não propaga."""
        import sys

        with patch.dict(sys.modules, {"opentelemetry.instrumentation.fastapi": None}):
            app = self._create_app_with_telemetry(otel_sdk_disabled=False)
        assert app is not None

    def test_permission_error_handler_returns_403(self):
        """Linha 92: handler de PermissionError retorna 403."""
        import asyncio

        app = self._create_app_with_telemetry(otel_sdk_disabled=True)
        handler = app.exception_handlers[PermissionError]
        response = asyncio.run(handler(MagicMock(), PermissionError("nope")))
        assert response.status_code == 403

    def test_storage_unavailable_handler_returns_503(self):
        """Linha 104: handler de StorageUnavailableError retorna 503."""
        import asyncio

        from concilium.domain.repositories.blob_storage_port import StorageUnavailableError

        app = self._create_app_with_telemetry(otel_sdk_disabled=True)
        handler = app.exception_handlers[StorageUnavailableError]
        response = asyncio.run(handler(MagicMock(), StorageUnavailableError("down")))
        assert response.status_code == 503

    def test_rate_limit_handler_delegates_for_rate_limit_exceeded(self):
        """Linhas 117-119: RateLimitExceeded → delega para rate_limit_exceeded_handler."""
        import asyncio

        from slowapi.errors import RateLimitExceeded

        app = self._create_app_with_telemetry(otel_sdk_disabled=True)
        handler = app.exception_handlers[RateLimitExceeded]
        exc = RateLimitExceeded(MagicMock())
        with patch("concilium.presentation.api.app.rate_limit_exceeded_handler", return_value="handled") as mocked:
            result = asyncio.run(handler(MagicMock(), exc))
        mocked.assert_called_once()
        assert result == "handled"

    def test_rate_limit_handler_reraises_other_exceptions(self):
        """Linhas 117-118: exceção que não é RateLimitExceeded é relançada."""
        import asyncio

        from slowapi.errors import RateLimitExceeded

        app = self._create_app_with_telemetry(otel_sdk_disabled=True)
        handler = app.exception_handlers[RateLimitExceeded]
        with pytest.raises(RuntimeError, match="unexpected"):
            asyncio.run(handler(MagicMock(), RuntimeError("unexpected")))

    def test_main_runs_startup_and_uvicorn(self):
        """Lines 149-160: main() executa startup checks e chama uvicorn.run."""
        with (
            patch("concilium.infrastructure.settings.startup_check") as mock_startup,
            patch("concilium.infrastructure.storage.store_factory.ensure_storage_root") as mock_ensure,
            patch("concilium.presentation.api.app.resolve_api_bind", return_value=("0.0.0.0", 8000)),
            patch("concilium.infrastructure.settings.get_api") as mock_get_api,
            patch("concilium.infrastructure.settings.get_catalog_digest") as mock_get_digest,
            patch("uvicorn.run") as mock_run,
        ):
            mock_get_api.return_value.reload = False
            mock_get_digest.return_value.enabled = False

            from concilium.presentation.api.app import main

            main()

        mock_startup.assert_called_once()
        mock_ensure.assert_called_once()
        mock_run.assert_called_once_with("concilium.presentation.api.app:app", host="0.0.0.0", port=8000, reload=False)

    def test_main_starts_draft_digest_scheduler_when_enabled(self):
        """ADR-141 D6: CATALOG_DIGEST_ENABLED=True → scheduler.start() é chamado em main()."""
        with (
            patch("concilium.infrastructure.settings.startup_check"),
            patch("concilium.infrastructure.storage.store_factory.ensure_storage_root"),
            patch("concilium.presentation.api.app.resolve_api_bind", return_value=("0.0.0.0", 8000)),
            patch("concilium.infrastructure.settings.get_api") as mock_get_api,
            patch("concilium.infrastructure.settings.get_catalog_digest") as mock_get_digest,
            patch(
                "concilium.application.services.catalog.draft_digest_scheduler.get_draft_digest_scheduler"
            ) as mock_get_scheduler,
            patch("uvicorn.run"),
        ):
            mock_get_api.return_value.reload = False
            mock_get_digest.return_value.enabled = True

            from concilium.presentation.api.app import main

            main()

        mock_get_scheduler.return_value.start.assert_called_once()

    def test_main_does_not_start_draft_digest_scheduler_when_disabled(self):
        """ADR-141 D6: CATALOG_DIGEST_ENABLED=False (default) → scheduler nunca é sequer importado/iniciado."""
        with (
            patch("concilium.infrastructure.settings.startup_check"),
            patch("concilium.infrastructure.storage.store_factory.ensure_storage_root"),
            patch("concilium.presentation.api.app.resolve_api_bind", return_value=("0.0.0.0", 8000)),
            patch("concilium.infrastructure.settings.get_api") as mock_get_api,
            patch("concilium.infrastructure.settings.get_catalog_digest") as mock_get_digest,
            patch(
                "concilium.application.services.catalog.draft_digest_scheduler.get_draft_digest_scheduler"
            ) as mock_get_scheduler,
            patch("uvicorn.run"),
        ):
            mock_get_api.return_value.reload = False
            mock_get_digest.return_value.enabled = False

            from concilium.presentation.api.app import main

            main()

        mock_get_scheduler.assert_not_called()

