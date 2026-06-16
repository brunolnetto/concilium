"""Tests for infrastructure/storage/file_project_repository.py — boost coverage."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

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
