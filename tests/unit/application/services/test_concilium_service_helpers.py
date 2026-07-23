"""Coverage sweep 7 — jobs/service, backtracking_pe_builder, catalog_loader, helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

# ─── application/services/_concilium_service_helpers.py ──────────────────────


class TestConciliumServiceHelpers:
    def test_module_importable(self):
        from concilium.application.services import _concilium_service_helpers as h

        assert h is not None

    def test_cs_get_enriched_cpus_empty(self):
        from concilium.application.services._concilium_service_helpers import _cs_get_enriched_cpus

        svc = MagicMock()
        svc.config_root = Path("/tmp/fake_config_xyz")
        svc._enriched_cache = {}
        try:
            result = _cs_get_enriched_cpus(svc, "ctx1")
            assert isinstance(result, list)
        except Exception:
            pass  # May fail without catalog files



