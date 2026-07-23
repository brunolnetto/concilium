"""Tests for several small modules to boost coverage."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ─── catalog_audit ──────────────────────────────────────────────────────────


class TestCatalogAudit:
    def test_perform_catalog_audit_healthy(self):
        from concilium.infrastructure.services.catalog_audit import perform_catalog_audit

        runtime = MagicMock()
        with patch("concilium.infrastructure.services.catalog_audit.assert_catalog_healthy"):
            perform_catalog_audit(runtime, "ctx1", {"cpus": []})

    def test_perform_catalog_audit_raises_on_governance_error(self):
        from concilium.application.orchestrators.catalog_governance import CatalogGovernanceError
        from concilium.infrastructure.services.catalog_audit import perform_catalog_audit

        runtime = MagicMock()
        with patch(
            "concilium.infrastructure.services.catalog_audit.assert_catalog_healthy",
            side_effect=CatalogGovernanceError("bad catalog"),
        ):
            with pytest.raises(RuntimeError, match="Erro de governança"):
                perform_catalog_audit(runtime, "ctx1", {})

    def test_load_and_audit_catalog_happy_path(self):
        from concilium.infrastructure.services.catalog_audit import load_and_audit_catalog

        runtime = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.catalogo_id = "cat1"
        runtime.load_contexto.return_value = mock_ctx
        runtime.load_catalogo.return_value = {"cpus": []}
        with patch("concilium.infrastructure.services.catalog_audit.assert_catalog_healthy"):
            load_and_audit_catalog(runtime, "ctx1")
        runtime.load_contexto.assert_called_once_with("ctx1")
        runtime.load_catalogo.assert_called_once_with("cat1")



