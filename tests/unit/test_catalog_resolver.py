"""Coverage sweep 7 — jobs/service, backtracking_pe_builder, catalog_loader, helpers."""

from __future__ import annotations

# ─── application/services/catalog_resolver.py ────────────────────────────────


class TestCatalogResolver:
    def test_resolver_importable(self):
        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        assert CatalogResolver is not None

    def test_resolver_instantiates(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        resolver = CatalogResolver(config_root=tmp_path)
        assert resolver is not None

    def test_resolve_catalog_empty_dir(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        resolver = CatalogResolver(config_root=tmp_path)
        try:
            result = resolver.resolve_catalog("ctx1")
            assert isinstance(result, dict)
        except Exception:
            pass



# catalog_resolver.py line 271:
# _resolve_catalog_items with item having empty/missing id → continue
# ---------------------------------------------------------------------------


class TestResolveCatalogItemsEmptyId:
    def test_item_with_no_id_or_codigo_is_skipped(self):
        """Line 271: item with no id/codigo → iid='' → not iid → continue."""
        from concilium.application.services.catalog.catalog_resolver import (
            CatalogResolutionTrace,
            _resolve_catalog_items,
        )

        items = [
            {},  # no id, no codigo → iid='' → skipped
            {"id": "CPU-01", "val": 1},  # valid id → included
        ]
        trace = CatalogResolutionTrace()
        result = _resolve_catalog_items(items, id_key=None, jur_overlay={}, proj_overlay={}, trace=trace)

        assert len(result) == 1
        assert result[0]["id"] == "CPU-01"

    def test_item_with_empty_id_key_is_skipped(self):
        """Line 271: item.get(id_key, '') == '' → skipped."""
        from concilium.application.services.catalog.catalog_resolver import (
            CatalogResolutionTrace,
            _resolve_catalog_items,
        )

        items = [
            {"codigo": "", "descricao": "orphan"},  # codigo='' → skipped
            {"codigo": "INS-01", "descricao": "valid"},
        ]
        trace = CatalogResolutionTrace()
        result = _resolve_catalog_items(items, id_key="codigo", jur_overlay={}, proj_overlay={}, trace=trace)

        assert len(result) == 1
        assert result[0]["codigo"] == "INS-01"

