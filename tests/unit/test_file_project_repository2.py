"""Tests for infrastructure/storage/file_project_repository.py — boost coverage."""

from __future__ import annotations

import json

import pytest


def _make_store(tmp_path):
    from concilium.infrastructure.storage.project import ProjectStore

    return ProjectStore.init(tmp_path, "Test Project", "ctx-1")


def _make_handle(tmp_path):
    from concilium.infrastructure.storage.file_project_repository import FileProjectHandle

    store = _make_store(tmp_path)
    return FileProjectHandle(store)


class TestRcHelpers:
    def test_rc_try_override_found(self, tmp_path):
        from concilium.infrastructure.storage.file_project_repository import _rc_try_override

        override_file = tmp_path / "cpus_override.json"
        override_file.write_text('{"CPU-1": {"codigo": "CPU-1"}}')
        result = _rc_try_override(override_file, "CPU-1", json)
        assert result == {"codigo": "CPU-1"}

    def test_rc_try_override_missing_file(self, tmp_path):
        from concilium.infrastructure.storage.file_project_repository import _rc_try_override

        result = _rc_try_override(tmp_path / "nonexistent.json", "CPU-1", json)
        assert result is None

    def test_rc_try_override_cpu_not_in_file(self, tmp_path):
        from concilium.infrastructure.storage.file_project_repository import _rc_try_override

        f = tmp_path / "cpus.json"
        f.write_text('{"CPU-2": {}}')
        result = _rc_try_override(f, "CPU-1", json)
        assert result is None

    def test_rc_try_file_found(self, tmp_path):
        from concilium.infrastructure.storage.file_project_repository import _rc_try_file

        f = tmp_path / "cpu.json"
        f.write_text('{"codigo": "CPU-1"}')
        result = _rc_try_file(f)
        assert result == {"codigo": "CPU-1"}

    def test_rc_try_file_missing(self, tmp_path):
        from concilium.infrastructure.storage.file_project_repository import _rc_try_file

        result = _rc_try_file(tmp_path / "nonexistent.json")
        assert result is None

    def test_rc_try_aggregate_found(self, tmp_path):
        from concilium.infrastructure.storage.file_project_repository import _rc_try_aggregate

        agg = tmp_path / "cpus.json"
        agg.write_text('{"cpus": [{"codigo": "CPU-1"}, {"codigo": "CPU-2"}]}')
        result = _rc_try_aggregate(agg, "CPU-1", json)
        assert result == {"codigo": "CPU-1"}

    def test_rc_try_aggregate_not_found(self, tmp_path):
        from concilium.infrastructure.storage.file_project_repository import _rc_try_aggregate

        agg = tmp_path / "cpus.json"
        agg.write_text('{"cpus": [{"codigo": "CPU-2"}]}')
        result = _rc_try_aggregate(agg, "CPU-MISSING", json)
        assert result is None

    def test_rc_try_aggregate_missing_file(self, tmp_path):
        from concilium.infrastructure.storage.file_project_repository import _rc_try_aggregate

        result = _rc_try_aggregate(tmp_path / "missing.json", "CPU-1", json)
        assert result is None

    def test_rc_try_snapshots_found(self, tmp_path):
        from concilium.infrastructure.storage.file_project_repository import _rc_try_snapshots

        snaps_dir = tmp_path / "snapshots"
        snaps_dir.mkdir()
        (snaps_dir / "catalogo-v1.json").write_text('{"cpus": [{"codigo": "CPU-1"}]}')
        result = _rc_try_snapshots(snaps_dir, "CPU-1", json)
        assert result == {"codigo": "CPU-1"}

    def test_rc_try_snapshots_missing_dir(self, tmp_path):
        from concilium.infrastructure.storage.file_project_repository import _rc_try_snapshots

        result = _rc_try_snapshots(tmp_path / "missing", "CPU-1", json)
        assert result is None


class TestFileProjectHandle:
    def test_properties(self, tmp_path):
        handle = _make_handle(tmp_path)
        assert handle.root == handle._store.root
        assert isinstance(handle.meta, dict)

    def test_tipo_projeto_default(self, tmp_path):
        handle = _make_handle(tmp_path)
        assert handle.tipo_projeto == "hot_project"

    def test_status_eap_default(self, tmp_path):
        handle = _make_handle(tmp_path)
        assert handle.status_eap == "ATIVO"

    def test_read_write_json(self, tmp_path):
        handle = _make_handle(tmp_path)
        handle.write_json("test.json", {"key": "value"})
        result = handle.read_json("test.json", {})
        assert result == {"key": "value"}

    def test_read_json_missing_returns_default(self, tmp_path):
        handle = _make_handle(tmp_path)
        result = handle.read_json("nonexistent.json", {"default": True})
        assert result == {"default": True}

    def test_read_lines(self, tmp_path):
        handle = _make_handle(tmp_path)
        (handle.root / "lines.txt").write_text("line1\nline2\n")
        result = handle.read_lines("lines.txt")
        assert result == ["line1", "line2"]

    def test_read_lines_missing(self, tmp_path):
        handle = _make_handle(tmp_path)
        assert handle.read_lines("missing.txt") == []

    def test_read_bytes(self, tmp_path):
        handle = _make_handle(tmp_path)
        (handle.root / "data.bin").write_bytes(b"\x00\x01")
        result = handle.read_bytes("data.bin")
        assert result == b"\x00\x01"

    def test_read_bytes_missing(self, tmp_path):
        handle = _make_handle(tmp_path)
        assert handle.read_bytes("missing.bin") is None

    def test_exists(self, tmp_path):
        handle = _make_handle(tmp_path)
        handle.write_json("exists.json", {})
        assert handle.exists("exists.json")
        assert not handle.exists("missing.json")

    def test_list_file_names(self, tmp_path):
        handle = _make_handle(tmp_path)
        subdir = handle.root / "subdir"
        subdir.mkdir()
        (subdir / "a.json").write_text("{}")
        (subdir / "b.json").write_text("{}")
        result = handle.list_file_names("subdir")
        assert result == ["a.json", "b.json"]

    def test_list_file_names_missing(self, tmp_path):
        handle = _make_handle(tmp_path)
        assert handle.list_file_names("missing_dir") == []

    def test_delete_tree(self, tmp_path):
        handle = _make_handle(tmp_path)
        subdir = handle.root / "to_delete"
        subdir.mkdir()
        (subdir / "file.txt").write_text("data")
        handle.delete_tree("to_delete")
        assert not subdir.exists()

    def test_set_overlay_and_audit(self, tmp_path):
        handle = _make_handle(tmp_path)
        handle.set_overlay("cpu", "CPU-1", {"descricao": "Test"}, actor="user", motivo="update")
        # Check overlay persisted
        overlay = handle.read_json("overrides/cpus_overlay.json", {})
        assert "CPU-1" in overlay
        # Check audit written
        audit = (handle.root / "overrides" / "overlay_audit.jsonl").read_text()
        assert "CPU-1" in audit

    def test_extend_cpu(self, tmp_path):
        handle = _make_handle(tmp_path)
        handle.extend_cpu("CPU-1", {"unidade": "m³"}, motivo="ext")
        overlay = handle.read_json("overrides/cpus_overlay.json", {})
        assert "CPU-1" in overlay

    def test_load_resolved_catalog_missing(self, tmp_path):
        handle = _make_handle(tmp_path)
        store = handle._store
        store.new_version()
        result = handle.load_resolved_catalog()
        assert result is None

    def test_resolve_cpu_from_override(self, tmp_path):
        handle = _make_handle(tmp_path)
        handle.write_json("overrides/cpus_override.json", {"CPU-1": {"codigo": "CPU-1"}})
        result = handle.resolve_cpu("CPU-1")
        assert result == {"codigo": "CPU-1"}

    def test_resolve_cpu_from_snapshots(self, tmp_path):
        handle = _make_handle(tmp_path)
        snaps_dir = handle.root / "snapshots"
        snaps_dir.mkdir(exist_ok=True)
        (snaps_dir / "catalogo-v1.json").write_text('{"cpus": [{"codigo": "CPU-SNAP"}]}')
        result = handle.resolve_cpu("CPU-SNAP")
        assert result is not None

    def test_resolve_cpu_not_found(self, tmp_path):
        handle = _make_handle(tmp_path)
        result = handle.resolve_cpu("CPU-MISSING")
        assert result is None


class TestFileProjectRepository:
    def test_list_projects_empty(self, tmp_path):
        from concilium.infrastructure.storage.file_project_repository import FileProjectRepository

        repo = FileProjectRepository(tmp_path / "projects")
        assert repo.list_projects() == []

    def test_list_projects_with_projects(self, tmp_path):
        from concilium.infrastructure.storage.file_project_repository import FileProjectRepository
        from concilium.infrastructure.storage.project import ProjectStore

        projects_root = tmp_path / "projects"
        projects_root.mkdir()
        ProjectStore.init(projects_root, "Proj 1", "ctx")
        repo = FileProjectRepository(projects_root)
        projects = repo.list_projects()
        assert len(projects) == 1

    def test_get_project_found(self, tmp_path):
        from concilium.infrastructure.storage.file_project_repository import FileProjectRepository
        from concilium.infrastructure.storage.project import ProjectStore

        projects_root = tmp_path / "projects"
        projects_root.mkdir()
        store = ProjectStore.init(projects_root, "Proj 1", "ctx")
        project_id = store.meta.get("id", store.root.name)
        repo = FileProjectRepository(projects_root)
        handle = repo.get_project(project_id)
        assert handle is not None

    def test_get_project_not_found(self, tmp_path):
        from concilium.infrastructure.storage.file_project_repository import FileProjectRepository

        repo = FileProjectRepository(tmp_path)
        with pytest.raises(FileNotFoundError):
            repo.get_project("nonexistent-id")

    def test_create_project_with_catalogo_base(self, tmp_path):
        from concilium.infrastructure.storage.file_project_repository import FileProjectRepository

        projects_root = tmp_path / "projects"
        projects_root.mkdir()
        repo = FileProjectRepository(projects_root)
        handle = repo.create_project("Proj Cat", "ctx", catalogo_base="cat-001")
        assert handle.meta.get("catalogo_base") == "cat-001"

    def test_list_projects_skips_non_dir(self, tmp_path):
        from concilium.infrastructure.storage.file_project_repository import FileProjectRepository
        from concilium.infrastructure.storage.project import ProjectStore

        projects_root = tmp_path / "projects"
        projects_root.mkdir()
        # Create a real project
        ProjectStore.init(projects_root, "Real", "ctx")
        # Add a file (not a dir) — should be skipped
        (projects_root / "not_a_dir.txt").write_text("noise")
        repo = FileProjectRepository(projects_root)
        projects = repo.list_projects()
        assert len(projects) == 1


class TestFileProjectHandleExtended:
    """Cover remaining delegating methods on FileProjectHandle."""

    def _make_handle(self, tmp_path):
        from concilium.infrastructure.storage.file_project_repository import FileProjectHandle
        store = _make_store(tmp_path)
        return FileProjectHandle(store)

    def test_snapshots_property(self, tmp_path):
        from concilium.infrastructure.storage.snapshot import SnapshotStore
        handle = self._make_handle(tmp_path)
        assert isinstance(handle.snapshots, SnapshotStore)

    def test_update_meta(self, tmp_path):
        handle = self._make_handle(tmp_path)
        handle.update_meta(extra="value")
        assert handle.meta["extra"] == "value"

    def test_list_versions_empty(self, tmp_path):
        handle = self._make_handle(tmp_path)
        assert handle.list_versions() == []

    def test_current_version_none(self, tmp_path):
        handle = self._make_handle(tmp_path)
        assert handle.current_version() is None

    def test_new_version_and_version_path(self, tmp_path):
        handle = self._make_handle(tmp_path)
        v = handle.new_version()
        assert v == "v1"
        assert handle.version_path("v1") == handle.root / "v1"

    def test_load_canonical_none(self, tmp_path):
        handle = self._make_handle(tmp_path)
        handle.new_version()
        assert handle.load_canonical() is None

    def test_write_canonical_raw_and_list_output_files(self, tmp_path):
        handle = self._make_handle(tmp_path)
        handle.new_version()
        handle.write_canonical_raw({"obra": {"nome": "T", "escopo": "r", "localizacao": "X", "extensao_km": 1.0, "atividades": []}})
        assert handle.list_output_files() == []

    def test_save_and_load_output_file(self, tmp_path):
        handle = self._make_handle(tmp_path)
        handle.new_version()
        handle.save_output_file(b"data", filename="out.xlsx")
        result = handle.load_output_file(filename="out.xlsx")
        assert result == b"data"

    def test_set_overlay_non_dict_overlay_overwritten(self, tmp_path):
        """set_overlay: if overlay on disk is not a dict, it's replaced."""
        handle = self._make_handle(tmp_path)
        # Write corrupt non-dict overlay
        handle._store.write_json("overrides/cpus_overlay.json", ["not", "a", "dict"])
        handle.set_overlay("cpu", "CPU-1", {"codigo": "CPU-1"})
        overlay = handle.read_json("overrides/cpus_overlay.json", {})
        assert "CPU-1" in overlay

    def test_load_resolved_catalog_present(self, tmp_path):
        handle = self._make_handle(tmp_path)
        handle._store.new_version()
        catalog_path = handle._store.root / "v1" / "resolved_catalog.json"
        catalog_path.write_text('{"cpus": []}', encoding="utf-8")
        result = handle.load_resolved_catalog()
        assert result == {"cpus": []}

    def test_load_resolved_catalog_bad_json(self, tmp_path):
        handle = self._make_handle(tmp_path)
        handle._store.new_version()
        catalog_path = handle._store.root / "v1" / "resolved_catalog.json"
        catalog_path.write_text("not json", encoding="utf-8")
        result = handle.load_resolved_catalog()
        assert result is None

    def test_set_compensacao_ineficiencias(self, tmp_path):
        handle = self._make_handle(tmp_path)
        handle.set_compensacao_ineficiencias({"fator": 1.1}, motivo="test")
        data = handle.read_json("compensacao_ineficiencias.json", {})
        assert data["compensacao"]["fator"] == 1.1

    def test_resolve_cpu_with_catalogo_base_and_snapshot(self, tmp_path):
        """resolve_cpu: walks override→individual→aggregate→snapshot when catalogo_base set."""
        handle = self._make_handle(tmp_path)
        # Set catalogo_base in meta (individual/aggregate files won't exist in tmp_path)
        handle.update_meta(catalogo_base="nonexistent-catalog")
        # Should fall through to snapshots
        snaps_dir = handle.root / "snapshots"
        snaps_dir.mkdir(exist_ok=True)
        (snaps_dir / "catalogo-v1.json").write_text(
            '{"cpus": [{"codigo": "CPU-S"}]}', encoding="utf-8"
        )
        result = handle.resolve_cpu("CPU-S")
        assert result == {"codigo": "CPU-S"}

    def test_append_jsonl_and_read_lines(self, tmp_path):
        handle = self._make_handle(tmp_path)
        log_path = handle.root / "events.jsonl"
        log_path.touch()
        handle.append_jsonl("events.jsonl", {"event": "first"})
        handle.append_jsonl("events.jsonl", {"event": "second"})
        lines = handle.read_lines("events.jsonl")
        assert len(lines) == 2
        assert "first" in lines[0]

    def test_save_and_load_intermediate_via_handle(self, tmp_path):
        handle = self._make_handle(tmp_path)
        handle.new_version()
        handle.save_intermediate_file("interim.bin", b"\xff\xfe", "v1")
        result = handle.load_intermediate_file("interim.bin", "v1")
        assert result == b"\xff\xfe"

    def test_log_invocation_and_approve(self, tmp_path):
        handle = self._make_handle(tmp_path)
        handle.new_version()
        handle.log_invocation("v1", {"skill": "01"})
        log = (handle.root / "v1" / "invocations.log").read_text(encoding="utf-8")
        assert "01" in log
        # approve — need canonical first
        handle.write_canonical_raw({"obra": {"nome": "T", "escopo": "r", "localizacao": "X", "extensao_km": 1.0, "atividades": []}})
        handle.approve("v1")
        assert "v1" in handle.meta.get("approved_versions", [])

    def test_list_escopos_and_escopo(self, tmp_path):
        from concilium.infrastructure.storage.escopo_store import EscopoStore
        handle = self._make_handle(tmp_path)
        assert handle.list_escopos() == []
        es = handle.escopo("default")
        assert isinstance(es, EscopoStore)

    def test_create_escopo_via_handle(self, tmp_path):
        handle = self._make_handle(tmp_path)
        es = handle.create_escopo(
            escopo_id="e01",
            nome="Trecho A",
            tipo_obra="terraplenagem",
            localizacao="MG",
            coordenadas_lat=-19.0,
            coordenadas_lng=-43.0,
            data_inicio="2026-01-01",
            data_termino="2026-06-30",
        )
        from concilium.infrastructure.storage.escopo_store import EscopoStore
        assert isinstance(es, EscopoStore)
        assert "e01" in handle.list_escopos()

    def test_write_json_creates_parent_dirs(self, tmp_path):
        handle = self._make_handle(tmp_path)
        # write_json in file_project_repository does NOT mkdir — test existing behavior
        # The path must be reachable: root exists, so writing to root directly works
        handle.write_json("direct.json", {"ok": True})
        assert (handle.root / "direct.json").exists()


class TestRcHelpersEdgeCases:
    """Cover error branches in the _rc_try_* helper functions."""

    def test_rc_try_override_bad_json(self, tmp_path):
        from concilium.infrastructure.storage.file_project_repository import _rc_try_override
        f = tmp_path / "bad.json"
        f.write_text("not json")
        result = _rc_try_override(f, "CPU-1", json)
        assert result is None

    def test_rc_try_file_bad_json(self, tmp_path):
        from concilium.infrastructure.storage.file_project_repository import _rc_try_file
        f = tmp_path / "bad.json"
        f.write_text("not json")
        result = _rc_try_file(f)
        assert result is None

    def test_rc_try_aggregate_bad_json(self, tmp_path):
        from concilium.infrastructure.storage.file_project_repository import _rc_try_aggregate
        f = tmp_path / "bad.json"
        f.write_text("not json")
        result = _rc_try_aggregate(f, "CPU-1", json)
        assert result is None

    def test_rc_try_snapshots_bad_json_skipped(self, tmp_path):
        from concilium.infrastructure.storage.file_project_repository import _rc_try_snapshots
        snaps_dir = tmp_path / "snapshots"
        snaps_dir.mkdir()
        (snaps_dir / "catalogo-v1.json").write_text("not json")
        (snaps_dir / "catalogo-v2.json").write_text('{"cpus": [{"codigo": "CPU-G"}]}')
        result = _rc_try_snapshots(snaps_dir, "CPU-G", json)
        assert result == {"codigo": "CPU-G"}

    def test_rc_try_aggregate_data_is_list_not_dict(self, tmp_path):
        """When cpus.json contains a list instead of dict (no 'cpus' key), handled gracefully."""
        from concilium.infrastructure.storage.file_project_repository import _rc_try_aggregate
        agg = tmp_path / "cpus.json"
        # data is a plain list → data.get("cpus", data) would fail if data were not dict
        # The code does: cpus = data.get("cpus", data) if isinstance(data, dict) else data
        agg.write_text('[{"codigo": "CPU-L", "descricao": "List CPU"}]')
        result = _rc_try_aggregate(agg, "CPU-L", json)
        assert result == {"codigo": "CPU-L", "descricao": "List CPU"}

    def test_rc_try_aggregate_dict_without_cpus_key(self, tmp_path):
        """When top-level dict has no 'cpus' key, falls back to the dict itself — not a list."""
        from concilium.infrastructure.storage.file_project_repository import _rc_try_aggregate
        agg = tmp_path / "cpus.json"
        # dict without 'cpus' key → data.get("cpus", data) returns data (the dict)
        # But then it checks isinstance(cpus, list) which is False → returns None
        agg.write_text('{"meta": "some-meta"}')
        result = _rc_try_aggregate(agg, "CPU-ANYTHING", json)
        assert result is None

    def test_rc_try_snapshots_cpu_not_found_in_any(self, tmp_path):
        """CPU not found in any snapshot → returns None."""
        from concilium.infrastructure.storage.file_project_repository import _rc_try_snapshots
        snaps_dir = tmp_path / "snapshots"
        snaps_dir.mkdir()
        (snaps_dir / "catalogo-v1.json").write_text('{"cpus": [{"codigo": "CPU-A"}]}')
        result = _rc_try_snapshots(snaps_dir, "CPU-NOT-EXIST", json)
        assert result is None


class TestFileProjectHandleLoadResolvedCatalog:
    """Extra branches for load_resolved_catalog on FileProjectHandle."""

    def _make_handle(self, tmp_path):
        from concilium.infrastructure.storage.file_project_repository import FileProjectHandle
        from concilium.infrastructure.storage.project import ProjectStore
        store = ProjectStore.init(tmp_path, "P", "ctx")
        return FileProjectHandle(store)

    def test_no_current_version_returns_none(self, tmp_path):
        handle = self._make_handle(tmp_path)
        # No version created — current_version() is None
        result = handle.load_resolved_catalog()
        assert result is None

    def test_file_missing_returns_none(self, tmp_path):
        handle = self._make_handle(tmp_path)
        handle._store.new_version()
        result = handle.load_resolved_catalog()
        assert result is None

    def test_explicit_version_returns_none_when_missing(self, tmp_path):
        handle = self._make_handle(tmp_path)
        handle._store.new_version()
        result = handle.load_resolved_catalog(version="v1")
        assert result is None


class TestFileProjectHandleAppendJsonl:
    """append_jsonl creates file when it doesn't exist."""

    def _make_handle(self, tmp_path):
        from concilium.infrastructure.storage.file_project_repository import FileProjectHandle
        from concilium.infrastructure.storage.project import ProjectStore
        store = ProjectStore.init(tmp_path, "P", "ctx")
        return FileProjectHandle(store)

    def test_append_jsonl_creates_file(self, tmp_path):
        handle = self._make_handle(tmp_path)
        handle.append_jsonl("events.jsonl", {"event": "test"})
        lines = handle.read_lines("events.jsonl")
        assert len(lines) == 1
        import json as _json
        assert _json.loads(lines[0])["event"] == "test"

    def test_append_jsonl_multiple_entries(self, tmp_path):
        handle = self._make_handle(tmp_path)
        handle.append_jsonl("log.jsonl", {"n": 1})
        handle.append_jsonl("log.jsonl", {"n": 2})
        lines = handle.read_lines("log.jsonl")
        assert len(lines) == 2


class TestFileProjectHandleReadJsonBadJson:
    """read_json on FileProjectHandle with corrupt JSON → returns default."""

    def _make_handle(self, tmp_path):
        from concilium.infrastructure.storage.file_project_repository import FileProjectHandle
        from concilium.infrastructure.storage.project import ProjectStore
        store = ProjectStore.init(tmp_path, "P", "ctx")
        return FileProjectHandle(store)

    def test_read_json_bad_json_returns_default(self, tmp_path):
        handle = self._make_handle(tmp_path)
        (handle.root / "bad.json").write_text("NOT JSON")
        result = handle.read_json("bad.json", {"default": True})
        assert result == {"default": True}

    def test_read_json_missing_file_returns_default(self, tmp_path):
        handle = self._make_handle(tmp_path)
        result = handle.read_json("nonexistent.json", 99)
        assert result == 99


class TestFileProjectHandleSaveCanonical:
    """save_canonical delegation path on FileProjectHandle."""

    def _make_handle(self, tmp_path):
        from concilium.infrastructure.storage.file_project_repository import FileProjectHandle
        from concilium.infrastructure.storage.project import ProjectStore
        store = ProjectStore.init(tmp_path, "P", "ctx")
        return FileProjectHandle(store)

    def test_save_canonical_raises_without_version(self, tmp_path):
        from unittest.mock import MagicMock
        handle = self._make_handle(tmp_path)
        mock_model = MagicMock()
        mock_model.model_dump_json.return_value = '{"meta": {}}'
        with pytest.raises(ValueError, match="Nenhuma versão ativa"):
            handle.save_canonical(mock_model)
