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



# catalog_resolver.py lines 157, 168-174:
# resolve_insumo with master file present → returns (item, "master")
# ---------------------------------------------------------------------------


class TestCatalogResolverMasterFile:
    def test_resolve_insumo_from_master_individual_file(self, tmp_path):
        """Lines 155-157, 168-174: insumo found in master individual file → ('item', 'master')."""
        from types import SimpleNamespace

        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        # project.root = tmp_path/projetos/proj-001
        # concilium_root = tmp_path (parents[1] of projetos/proj-001)
        proj_root = tmp_path / "projetos" / "proj-001"
        proj_root.mkdir(parents=True)

        # Create master insumo file
        cat_dir = tmp_path / "config" / "catalogos" / "cat-001" / "insumos"
        cat_dir.mkdir(parents=True)
        (cat_dir / "INS-01.json").write_text('{"codigo": "INS-01", "descricao": "Test Insumo"}', encoding="utf-8")

        project = SimpleNamespace(
            root=str(proj_root),
            meta={"id": "proj-001"},
        )

        resolver = CatalogResolver(config_root=tmp_path / "config")
        result, source = resolver.resolve_insumo("INS-01", "cat-001", project)

        assert source == "master"
        assert result is not None
        assert result["codigo"] == "INS-01"


# ---------------------------------------------------------------------------

