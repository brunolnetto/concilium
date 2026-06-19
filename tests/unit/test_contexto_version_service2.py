"""Tests for application/services/catalog/contexto_version_service.py."""

from __future__ import annotations

import json


def _make_svc(tmp_path, subdir="contextos", include_flat_files=False):
    from concilium.application.services.catalog.contexto_version_service import ConfigVersionService

    return ConfigVersionService(tmp_path, subdir, include_flat_files=include_flat_files)


def _setup_entity(root, subdir, entity_id, versions=None, flat_content=None, current="v1"):
    """Helper to set up versioned entity structure."""
    entity_dir = root / subdir / entity_id
    if versions:
        versions_dir = entity_dir / "versions"
        versions_dir.mkdir(parents=True)
        for vname, data in versions.items():
            (versions_dir / f"{vname}.json").write_text(json.dumps(data), encoding="utf-8")
        (entity_dir / "current").write_text(current, encoding="utf-8")
    elif flat_content is not None:
        entity_dir.mkdir(parents=True, exist_ok=True)
        flat_file = root / subdir / f"{entity_id}.json"
        flat_file.write_text(json.dumps(flat_content), encoding="utf-8")
    return entity_dir


class TestConfigVersionServiceResolve:
    def test_resolve_versioned_current(self, tmp_path):
        svc = _make_svc(tmp_path)
        _setup_entity(tmp_path, "contextos", "ctx-1", versions={"v1": {"id": "ctx-1", "nome": "Test"}})
        result = svc.resolve("ctx-1")
        assert result["id"] == "ctx-1"

    def test_resolve_specific_version(self, tmp_path):
        svc = _make_svc(tmp_path)
        _setup_entity(
            tmp_path,
            "contextos",
            "ctx-1",
            versions={
                "v1": {"id": "ctx-1", "nome": "v1"},
                "v2": {"id": "ctx-1", "nome": "v2"},
            },
            current="v2",
        )
        result = svc.resolve("ctx-1", version="v1")
        assert result["nome"] == "v1"

    def test_resolve_falls_back_to_latest_version(self, tmp_path):
        svc = _make_svc(tmp_path)
        _setup_entity(tmp_path, "contextos", "ctx-1", versions={"v3": {"id": "ctx-1", "nome": "Latest"}}, current="v99")
        result = svc.resolve("ctx-1")
        assert result["nome"] == "Latest"

    def test_resolve_flat_file_fallback(self, tmp_path):
        svc = _make_svc(tmp_path)
        flat = tmp_path / "contextos" / "ctx-flat.json"
        flat.parent.mkdir(parents=True, exist_ok=True)
        flat.write_text('{"id": "ctx-flat"}', encoding="utf-8")
        result = svc.resolve("ctx-flat")
        assert result["id"] == "ctx-flat"

    def test_resolve_missing_returns_none(self, tmp_path):
        svc = _make_svc(tmp_path)
        (tmp_path / "contextos").mkdir(exist_ok=True)
        assert svc.resolve("nonexistent") is None

    def test_resolve_flat_file_invalid_json_returns_none(self, tmp_path):
        svc = _make_svc(tmp_path)
        flat = tmp_path / "contextos" / "ctx-bad.json"
        flat.parent.mkdir(parents=True, exist_ok=True)
        flat.write_text("NOT JSON", encoding="utf-8")
        assert svc.resolve("ctx-bad") is None


class TestListVersions:
    def test_list_versions_versioned(self, tmp_path):
        svc = _make_svc(tmp_path)
        _setup_entity(
            tmp_path,
            "contextos",
            "ctx-1",
            versions={
                "v1": {"id": "ctx-1", "version": "v1", "motivo": "initial"},
                "v2": {"id": "ctx-1", "version": "v2", "motivo": "update"},
            },
        )
        result = svc.list_versions("ctx-1")
        assert len(result) == 2
        assert result[0]["version"] == "v1"

    def test_list_versions_flat_file(self, tmp_path):
        svc = _make_svc(tmp_path)
        flat = tmp_path / "contextos" / "ctx-flat.json"
        flat.parent.mkdir(parents=True, exist_ok=True)
        flat.write_text('{"created_by": "user", "motivo": "initial"}', encoding="utf-8")
        result = svc.list_versions("ctx-flat")
        assert len(result) == 1
        assert result[0]["version"] == "v1"
        assert result[0]["created_by"] == "user"

    def test_list_versions_missing_returns_base(self, tmp_path):
        svc = _make_svc(tmp_path)
        (tmp_path / "contextos").mkdir(exist_ok=True)
        result = svc.list_versions("nonexistent")
        assert result == [{"version": "v1", "motivo": "base"}]


class TestCurrentVersion:
    def test_current_from_file(self, tmp_path):
        svc = _make_svc(tmp_path)
        _setup_entity(tmp_path, "contextos", "ctx-1", versions={"v2": {}}, current="v2")
        assert svc.current_version("ctx-1") == "v2"

    def test_current_defaults_to_v1(self, tmp_path):
        svc = _make_svc(tmp_path)
        (tmp_path / "contextos").mkdir(exist_ok=True)
        assert svc.current_version("missing") == "v1"


class TestCreateVersion:
    def test_create_first_version(self, tmp_path):
        svc = _make_svc(tmp_path)
        (tmp_path / "contextos").mkdir(exist_ok=True)
        result = svc.create_version("ctx-new", {"id": "ctx-new", "nome": "New"}, motivo="initial")
        assert result["version"] == "v1"
        assert result["nome"] == "New"
        assert result["motivo"] == "initial"

    def test_create_second_version_increments(self, tmp_path):
        svc = _make_svc(tmp_path)
        _setup_entity(tmp_path, "contextos", "ctx-1", versions={"v1": {"id": "ctx-1", "nome": "v1"}})
        result = svc.create_version("ctx-1", {"nome": "v2"}, motivo="update", author="admin")
        assert result["version"] == "v2"
        assert result["nome"] == "v2"
        assert result["created_by"] == "admin"

    def test_create_version_bootstraps_from_flat(self, tmp_path):
        svc = _make_svc(tmp_path)
        flat = tmp_path / "contextos" / "ctx-1.json"
        flat.parent.mkdir(parents=True, exist_ok=True)
        flat.write_text('{"id": "ctx-1", "nome": "Base", "catalogo_id": "cat-1"}', encoding="utf-8")
        result = svc.create_version("ctx-1", {"nome": "Updated"}, motivo="migration")
        assert result["catalogo_id"] == "cat-1"
        assert result["nome"] == "Updated"

    def test_create_version_updates_current_file(self, tmp_path):
        svc = _make_svc(tmp_path)
        (tmp_path / "contextos").mkdir(exist_ok=True)
        svc.create_version("ctx-1", {"id": "ctx-1"}, motivo="init")
        assert svc.current_version("ctx-1") == "v1"


class TestCompare:
    def test_compare_same_versions(self, tmp_path):
        svc = _make_svc(tmp_path)
        _setup_entity(
            tmp_path,
            "contextos",
            "ctx-1",
            versions={
                "v1": {"id": "ctx-1", "nome": "Test"},
                "v2": {"id": "ctx-1", "nome": "Test"},  # same nome
            },
        )
        result = svc.compare("ctx-1", "v1", "v2")
        assert "nome" not in result["changed"]

    def test_compare_different_versions(self, tmp_path):
        svc = _make_svc(tmp_path)
        _setup_entity(
            tmp_path,
            "contextos",
            "ctx-1",
            versions={
                "v1": {"id": "ctx-1", "nome": "Old"},
                "v2": {"id": "ctx-1", "nome": "New"},
            },
        )
        result = svc.compare("ctx-1", "v1", "v2")
        assert "nome" in result["changed"]
        assert result["changed"]["nome"]["de"] == "Old"
        assert result["changed"]["nome"]["para"] == "New"

    def test_compare_nested_diff(self, tmp_path):
        svc = _make_svc(tmp_path)
        _setup_entity(
            tmp_path,
            "contextos",
            "ctx-1",
            versions={
                "v1": {"config": {"a": 1, "b": 2}},
                "v2": {"config": {"a": 1, "b": 99}},
            },
        )
        result = svc.compare("ctx-1", "v1", "v2")
        assert "config.b" in result["changed"]


class TestListEntitiesWithFlatFiles:
    def test_list_entities_includes_flat_files(self, tmp_path):
        svc = _make_svc(tmp_path, include_flat_files=True)
        jur_dir = tmp_path / "contextos"
        jur_dir.mkdir()
        (jur_dir / "jur-1.json").write_text('{"id": "jur-1", "nome": "Jurisdicao 1"}', encoding="utf-8")
        result = svc.list_entities()
        assert any(e["id"] == "jur-1" for e in result)

    def test_list_entities_skips_invalid_flat_json(self, tmp_path):
        svc = _make_svc(tmp_path, include_flat_files=True)
        jur_dir = tmp_path / "contextos"
        jur_dir.mkdir()
        (jur_dir / "bad.json").write_text("NOT JSON", encoding="utf-8")
        result = svc.list_entities()
        assert not any(e.get("id") == "bad" for e in result)


class TestConcreteServices:
    def test_contexto_version_service(self, tmp_path):
        from concilium.application.services.catalog.contexto_version_service import ContextoVersionService

        (tmp_path / "contextos").mkdir()
        svc = ContextoVersionService(tmp_path)
        result = svc.list_contexts()
        assert isinstance(result, list)

    def test_perfil_version_service(self, tmp_path):
        from concilium.application.services.catalog.contexto_version_service import PerfilVersionService

        (tmp_path / "perfis").mkdir()
        svc = PerfilVersionService(tmp_path)
        assert isinstance(svc.list_perfis(), list)

    def test_jurisdiction_version_service(self, tmp_path):
        from concilium.application.services.catalog.contexto_version_service import JurisdictionVersionService

        (tmp_path / "jurisdicoes").mkdir()
        svc = JurisdictionVersionService(tmp_path)
        assert isinstance(svc.list_jurisdicoes(), list)


class TestDiffValues:
    def test_same_values_no_diff(self):
        from concilium.application.services.catalog.contexto_version_service import _diff_values

        out: dict = {}
        _diff_values("key", 1, 1, out)
        assert out == {}

    def test_scalar_diff(self):
        from concilium.application.services.catalog.contexto_version_service import _diff_values

        out: dict = {}
        _diff_values("key", "old", "new", out)
        assert out["key"] == {"de": "old", "para": "new"}

    def test_list_diff(self):
        from concilium.application.services.catalog.contexto_version_service import _diff_values

        out: dict = {}
        _diff_values("items", [1, 2], [1, 3], out)
        assert "items" in out

    def test_dict_recursive(self):
        from concilium.application.services.catalog.contexto_version_service import _diff_values

        out: dict = {}
        _diff_values("parent", {"a": 1, "b": 2}, {"a": 1, "b": 99}, out)
        assert "parent.b" in out
        assert "parent.a" not in out
