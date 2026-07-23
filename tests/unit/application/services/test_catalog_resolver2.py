"""Tests for CatalogResolver to boost coverage."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch


class TestCatalogResolutionTrace:
    def test_record_and_to_dict(self):
        from concilium.application.services.catalog.catalog_resolver import CatalogResolutionTrace

        t = CatalogResolutionTrace()
        t.record("cpu-1", "master")
        t.record("cpu-2", "project")
        d = t.to_dict()
        assert d["cpu-1"] == "master"
        assert d["cpu-2"] == "project"

    def test_to_dict_empty(self):
        from concilium.application.services.catalog.catalog_resolver import CatalogResolutionTrace

        t = CatalogResolutionTrace()
        assert t.to_dict() == {}


def _make_project(tmp_path, cpu_overlay=None, insumo_overlay=None, producao_overlay=None):
    proj = MagicMock()
    proj.meta = {"id": "proj-test"}
    proj.root = str(tmp_path / "projects" / "proj-test")

    def read_json(path, default=None):
        if default is None:
            default = {}
        if "cpus_overlay" in path:
            return cpu_overlay if cpu_overlay is not None else default
        if "insumos_overlay" in path:
            return insumo_overlay if insumo_overlay is not None else default
        if "producoes_overlay" in path:
            return producao_overlay if producao_overlay is not None else default
        return default

    proj.read_json.side_effect = read_json
    return proj


class TestLoadOverlays:
    def test_cpu_overlay_cached(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        resolver = CatalogResolver(config_root=tmp_path)
        proj = _make_project(tmp_path, cpu_overlay={"CPU-1": {"descricao": "v"}})
        r1 = resolver._load_project_cpu_overlay(proj)
        r2 = resolver._load_project_cpu_overlay(proj)
        assert r1 is r2

    def test_cpu_overlay_exception_returns_empty(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        resolver = CatalogResolver(config_root=tmp_path)
        proj = MagicMock()
        proj.meta = {"id": "x"}
        proj.read_json.side_effect = OSError("fail")
        result = resolver._load_project_cpu_overlay(proj)
        assert result == {}

    def test_cpu_overlay_invalid_type_returns_empty(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        resolver = CatalogResolver(config_root=tmp_path)
        proj = _make_project(tmp_path, cpu_overlay="not-a-dict")
        result = resolver._load_project_cpu_overlay(proj)
        assert result == {}

    def test_insumo_overlay_cached(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        resolver = CatalogResolver(config_root=tmp_path)
        proj = _make_project(tmp_path, insumo_overlay={"INS-1": {"preco": 100}})
        r1 = resolver._load_project_insumo_overlay(proj)
        r2 = resolver._load_project_insumo_overlay(proj)
        assert r1 is r2

    def test_insumo_overlay_exception_returns_empty(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        resolver = CatalogResolver(config_root=tmp_path)
        proj = MagicMock()
        proj.meta = {"id": "x"}
        proj.read_json.side_effect = OSError("fail")
        result = resolver._load_project_insumo_overlay(proj)
        assert result == {}

    def test_producao_overlay_cached(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        resolver = CatalogResolver(config_root=tmp_path)
        proj = _make_project(tmp_path, producao_overlay={"P1": {"ref": 50}})
        r1 = resolver._load_project_producao_overlay(proj)
        r2 = resolver._load_project_producao_overlay(proj)
        assert r1 is r2

    def test_producao_overlay_exception_returns_empty(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        resolver = CatalogResolver(config_root=tmp_path)
        proj = MagicMock()
        proj.meta = {"id": "x"}
        proj.read_json.side_effect = OSError("fail")
        result = resolver._load_project_producao_overlay(proj)
        assert result == {}

    def test_jurisdiction_overlay_missing_returns_empty(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        resolver = CatalogResolver(config_root=tmp_path)
        result = resolver._load_jurisdiction_overlay("jur-nonexistent")
        assert result == {}

    def test_jurisdiction_overlay_cached(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        jur_dir = tmp_path / "jurisdicoes" / "jur-1"
        jur_dir.mkdir(parents=True)
        (jur_dir / "overlay.json").write_text('{"cpus": {"CPU-A": {}}}', encoding="utf-8")
        resolver = CatalogResolver(config_root=tmp_path)
        r1 = resolver._load_jurisdiction_overlay("jur-1")
        r2 = resolver._load_jurisdiction_overlay("jur-1")
        assert r1 is r2
        assert "cpus" in r1

    def test_jurisdiction_overlay_invalid_json_returns_empty(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        jur_dir = tmp_path / "jurisdicoes" / "jur-bad"
        jur_dir.mkdir(parents=True)
        (jur_dir / "overlay.json").write_text("NOT JSON", encoding="utf-8")
        resolver = CatalogResolver(config_root=tmp_path)
        result = resolver._load_jurisdiction_overlay("jur-bad")
        assert result == {}


class TestResolveCpuInsumo:
    def test_resolve_cpu_from_project_overlay(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        resolver = CatalogResolver(config_root=tmp_path)
        proj = _make_project(tmp_path, cpu_overlay={"CPU-1": {"descricao": "FromProject"}})
        item, source = resolver.resolve_cpu("CPU-1", "cat-test", proj)
        assert item == {"descricao": "FromProject"}
        assert source == "project"

    def test_resolve_cpu_from_jurisdiction_overlay(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        jur_dir = tmp_path / "jurisdicoes" / "jur-1"
        jur_dir.mkdir(parents=True)
        (jur_dir / "overlay.json").write_text('{"cpus": {"CPU-J": {"tag": "jur"}}}', encoding="utf-8")
        resolver = CatalogResolver(config_root=tmp_path)
        proj = _make_project(tmp_path)
        with patch.object(resolver, "_resolve_from_master", return_value=None):
            item, source = resolver.resolve_cpu("CPU-J", "cat-test", proj, jurisdicao_id="jur-1")
        assert item == {"tag": "jur"}
        assert source == "jurisdiction"

    def test_resolve_cpu_not_found_returns_none(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        resolver = CatalogResolver(config_root=tmp_path)
        proj = _make_project(tmp_path)
        with patch.object(resolver, "_resolve_from_master", return_value=None):
            item, source = resolver.resolve_cpu("CPU-MISSING", "cat-test", proj)
        assert item is None
        assert source == "master"

    def test_resolve_cpu_from_master(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        resolver = CatalogResolver(config_root=tmp_path)
        proj = _make_project(tmp_path)
        with patch.object(resolver, "_resolve_from_master", return_value={"codigo": "CPU-M"}):
            item, source = resolver.resolve_cpu("CPU-M", "cat-test", proj)
        assert item == {"codigo": "CPU-M"}
        assert source == "master"

    def test_resolve_insumo_from_project_overlay(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        resolver = CatalogResolver(config_root=tmp_path)
        proj = _make_project(tmp_path, insumo_overlay={"INS-1": {"preco_unitario": 999}})
        item, source = resolver.resolve_insumo("INS-1", "cat-test", proj)
        assert item["preco_unitario"] == 999
        assert source == "project"

    def test_resolve_insumo_from_jurisdiction(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        jur_dir = tmp_path / "jurisdicoes" / "jur-2"
        jur_dir.mkdir(parents=True)
        (jur_dir / "overlay.json").write_text('{"insumos": {"INS-J": {"tag": "j"}}}', encoding="utf-8")
        resolver = CatalogResolver(config_root=tmp_path)
        proj = _make_project(tmp_path)
        with patch.object(resolver, "_resolve_from_master", return_value=None):
            item, source = resolver.resolve_insumo("INS-J", "cat-test", proj, jurisdicao_id="jur-2")
        assert item == {"tag": "j"}
        assert source == "jurisdiction"

    def test_resolve_insumo_not_found(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        resolver = CatalogResolver(config_root=tmp_path)
        proj = _make_project(tmp_path)
        with patch.object(resolver, "_resolve_from_master", return_value=None):
            item, source = resolver.resolve_insumo("INS-MISSING", "cat-test", proj)
        assert item is None
        assert source == "master"

    def test_resolve_cpu_jurisdiction_present_but_id_missing_falls_to_master(self, tmp_path):
        # jurisdicao_id is given and the overlay loads fine, but the cpu isn't
        # in it → must fall through to master (covers the false branch of
        # `if cpu_id in jur_cpus`).
        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        jur_dir = tmp_path / "jurisdicoes" / "jur-1"
        jur_dir.mkdir(parents=True)
        (jur_dir / "overlay.json").write_text('{"cpus": {"CPU-OTHER": {"tag": "jur"}}}', encoding="utf-8")
        resolver = CatalogResolver(config_root=tmp_path)
        proj = _make_project(tmp_path)
        with patch.object(resolver, "_resolve_from_master", return_value={"codigo": "CPU-M"}):
            item, source = resolver.resolve_cpu("CPU-M", "cat-test", proj, jurisdicao_id="jur-1")
        assert item == {"codigo": "CPU-M"}
        assert source == "master"

    def test_resolve_insumo_jurisdiction_present_but_id_missing_falls_to_master(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        jur_dir = tmp_path / "jurisdicoes" / "jur-2"
        jur_dir.mkdir(parents=True)
        (jur_dir / "overlay.json").write_text('{"insumos": {"INS-OTHER": {"tag": "j"}}}', encoding="utf-8")
        resolver = CatalogResolver(config_root=tmp_path)
        proj = _make_project(tmp_path)
        with patch.object(resolver, "_resolve_from_master", return_value={"codigo": "INS-M"}):
            item, source = resolver.resolve_insumo("INS-M", "cat-test", proj, jurisdicao_id="jur-2")
        assert item == {"codigo": "INS-M"}
        assert source == "master"


class TestApplyOverlaysAndBuild:
    def test_apply_overlays_no_overlays(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        resolver = CatalogResolver(config_root=tmp_path)
        proj = _make_project(tmp_path)
        master = {
            "cpus": [{"codigo": "CPU-1", "descricao": "Base"}],
            "insumos": [{"id": "INS-1", "preco_unitario": 100}],
            "producoes": [],
        }
        resolved, trace = resolver.apply_overlays(master, proj)
        assert any(c["codigo"] == "CPU-1" for c in resolved["cpus"])

    def test_apply_overlays_with_project_cpu_overlay(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        resolver = CatalogResolver(config_root=tmp_path)
        proj = _make_project(tmp_path, cpu_overlay={"CPU-1": {"descricao": "Overridden"}})
        master = {"cpus": [{"codigo": "CPU-1", "descricao": "Base"}], "insumos": [], "producoes": []}
        resolved, trace = resolver.apply_overlays(master, proj)
        cpu = next(c for c in resolved["cpus"] if c["codigo"] == "CPU-1")
        assert cpu["descricao"] == "Overridden"
        assert trace.to_dict().get("CPU-1") == "project"

    def test_apply_overlays_with_jurisdiction(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        jur_dir = tmp_path / "jurisdicoes" / "jur-1"
        jur_dir.mkdir(parents=True)
        (jur_dir / "overlay.json").write_text('{"cpus": {"CPU-J": {"tag": "jur"}}}', encoding="utf-8")
        resolver = CatalogResolver(config_root=tmp_path)
        proj = _make_project(tmp_path)
        master = {"cpus": [{"codigo": "CPU-J", "tag": "base"}], "insumos": [], "producoes": []}
        resolved, trace = resolver.apply_overlays(master, proj, jurisdicao_id="jur-1")
        cpu = next(c for c in resolved["cpus"] if c["codigo"] == "CPU-J")
        assert cpu["tag"] == "jur"

    def test_apply_overlays_project_adds_new_cpu(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        resolver = CatalogResolver(config_root=tmp_path)
        proj = _make_project(tmp_path, cpu_overlay={"CPU-NEW": {"codigo": "CPU-NEW"}})
        master = {"cpus": [], "insumos": [], "producoes": []}
        resolved, trace = resolver.apply_overlays(master, proj)
        assert any(c.get("codigo") == "CPU-NEW" for c in resolved["cpus"])

    def test_build_resolved_catalog_filters_by_eap(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        resolver = CatalogResolver(config_root=tmp_path)
        proj = _make_project(tmp_path)
        master = {
            "cpus": [{"codigo": "CPU-1"}, {"codigo": "CPU-2"}],
            "insumos": [],
            "producoes": [],
        }
        resolved, _ = resolver.build_resolved_catalog(master, proj, None, eap_cpu_ids={"CPU-1"})
        assert len(resolved["cpus"]) == 1
        assert resolved["cpus"][0]["codigo"] == "CPU-1"

    def test_build_resolved_catalog_no_filter(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        resolver = CatalogResolver(config_root=tmp_path)
        proj = _make_project(tmp_path)
        master = {
            "cpus": [{"codigo": "CPU-1"}, {"codigo": "CPU-2"}],
            "insumos": [],
            "producoes": [],
        }
        resolved, _ = resolver.build_resolved_catalog(master, proj, None, eap_cpu_ids=None)
        assert len(resolved["cpus"]) == 2

    def test_apply_overlays_produtividades(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        resolver = CatalogResolver(config_root=tmp_path)
        proj = _make_project(tmp_path, producao_overlay={"P1": {"id": "P1", "valor": 99}})
        master = {
            "cpus": [],
            "insumos": [],
            "producoes": [],
            "produtividades": [{"id": "P1", "valor": 50}],
        }
        resolved, trace = resolver.apply_overlays(master, proj)
        p = next(x for x in resolved["produtividades"] if x.get("id") == "P1")
        assert p["valor"] == 99
        assert trace.to_dict().get("P1") == "project"


class TestRfmHelpers:
    def test_rfm_try_individual_missing(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import _rfm_try_individual

        result = _rfm_try_individual(tmp_path, "cpus", "CPU-MISSING")
        assert result is None

    def test_rfm_try_individual_found(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import _rfm_try_individual

        cpus_dir = tmp_path / "cpus"
        cpus_dir.mkdir()
        (cpus_dir / "CPU-1.json").write_text('{"codigo": "CPU-1"}', encoding="utf-8")
        result = _rfm_try_individual(tmp_path, "cpus", "CPU-1")
        assert result is not None
        assert result.get("codigo") == "CPU-1"

    def test_rfm_try_individual_invalid_json(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import _rfm_try_individual

        cpus_dir = tmp_path / "cpus"
        cpus_dir.mkdir()
        (cpus_dir / "CPU-BAD.json").write_text("NOT JSON", encoding="utf-8")
        result = _rfm_try_individual(tmp_path, "cpus", "CPU-BAD")
        assert result is None

    def test_rfm_try_aggregate_not_found(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import _rfm_try_aggregate

        result = _rfm_try_aggregate(tmp_path, "cpus", "CPU-MISSING")
        assert result is None

    def test_rfm_try_aggregate_found_by_codigo(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import _rfm_try_aggregate

        data = {"cpus": [{"codigo": "CPU-A"}, {"codigo": "CPU-B"}]}
        (tmp_path / "cpus.json").write_text(json.dumps(data), encoding="utf-8")
        result = _rfm_try_aggregate(tmp_path, "cpus", "CPU-A")
        assert result is not None
        assert result["codigo"] == "CPU-A"

    def test_rfm_try_aggregate_not_in_list(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import _rfm_try_aggregate

        data = [{"codigo": "CPU-X"}]
        (tmp_path / "cpus.json").write_text(json.dumps(data), encoding="utf-8")
        result = _rfm_try_aggregate(tmp_path, "cpus", "CPU-MISSING")
        assert result is None

    def test_rfm_try_aggregate_invalid_json(self, tmp_path):
        from concilium.application.services.catalog.catalog_resolver import _rfm_try_aggregate

        (tmp_path / "cpus.json").write_text("NOT JSON", encoding="utf-8")
        result = _rfm_try_aggregate(tmp_path, "cpus", "CPU-A")
        assert result is None

    def test_rfm_try_aggregate_non_list_items_returns_none(self, tmp_path):
        # data is a dict without a `subdir` key → data.get(subdir, data) falls
        # back to `data` itself, which is a dict, not a list → isinstance
        # check is False and the function must return None without looping.
        from concilium.application.services.catalog.catalog_resolver import _rfm_try_aggregate

        data = {"unrelated_key": "value"}
        (tmp_path / "cpus.json").write_text(json.dumps(data), encoding="utf-8")
        result = _rfm_try_aggregate(tmp_path, "cpus", "CPU-A")
        assert result is None

    def test_resolve_from_master_falls_back_to_aggregate_when_individual_missing(self, tmp_path):
        # Individual file doesn't exist for this cpu, but the aggregate file
        # has it → _resolve_from_master must fall through to the aggregate lookup.
        from concilium.application.services.catalog.catalog_resolver import CatalogResolver

        cat_base = tmp_path / "config" / "catalogos" / "cat-test"
        cpus_dir = cat_base / "cpus"
        cpus_dir.mkdir(parents=True)
        agg_data = {"cpus": [{"codigo": "CPU-AGG", "descricao": "From aggregate"}]}
        (cpus_dir.parent / "cpus.json").write_text(json.dumps(agg_data), encoding="utf-8")
        resolver = CatalogResolver(config_root=tmp_path)
        proj = _make_project(tmp_path)
        result = resolver._resolve_from_master("CPU-AGG", "cat-test", "cpu", proj)
        assert result == {"codigo": "CPU-AGG", "descricao": "From aggregate"}


class TestDeepMerge:
    def test_deep_merge_scalars(self):
        from concilium.application.services.catalog.catalog_resolver import _deep_merge

        result = _deep_merge({"a": 1, "b": 2}, {"b": 99, "c": 3})
        assert result == {"a": 1, "b": 99, "c": 3}

    def test_deep_merge_nested(self):
        from concilium.application.services.catalog.catalog_resolver import _deep_merge

        base = {"a": 1, "b": {"c": 2, "d": 3}}
        overlay = {"b": {"c": 99}, "e": 5}
        result = _deep_merge(base, overlay)
        assert result["b"]["c"] == 99
        assert result["b"]["d"] == 3
        assert result["e"] == 5

    def test_deep_merge_does_not_mutate_base(self):
        from concilium.application.services.catalog.catalog_resolver import _deep_merge

        base = {"x": {"y": 1}}
        _deep_merge(base, {"x": {"y": 2}})
        assert base["x"]["y"] == 1
