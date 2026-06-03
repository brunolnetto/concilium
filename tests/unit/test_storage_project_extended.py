"""Tests for storage/project.py — missing coverage paths."""

from __future__ import annotations

import json
import stat
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from concilium.infrastructure.storage.project import ProjectStore

# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _init_store(tmp_path: Path) -> ProjectStore:
    return ProjectStore.init(tmp_path, nome="Teste", contexto_id="ctx-001")


def _make_minimal_canonical() -> dict:
    """Minimal dict that passes CanonicalModel validation."""
    return {
        "obra": {
            "nome": "Obra Teste",
            "escopo": "rodovia",
            "localizacao": "CE",
            "extensao_km": 10.0,
            "atividades": [],
        }
    }


# ─────────────────────────────────────────────────────────────────────────────
#  ProjectStore.init
# ─────────────────────────────────────────────────────────────────────────────


class TestProjectStoreInit:
    def test_init_creates_directory(self, tmp_path):
        """init() creates project directory."""
        store = _init_store(tmp_path)
        assert store.root.exists()
        assert store.root.is_dir()

    def test_init_creates_meta_json(self, tmp_path):
        """init() writes meta.json with project metadata."""
        store = _init_store(tmp_path)
        assert (store.root / "meta.json").exists()
        meta = json.loads((store.root / "meta.json").read_text())
        assert meta["nome"] == "Teste"
        assert meta["contexto_id"] == "ctx-001"

    def test_init_creates_snapshots_dir(self, tmp_path):
        """init() creates snapshots/ subdirectory."""
        store = _init_store(tmp_path)
        assert (store.root / "snapshots").exists()

    def test_meta_property(self, tmp_path):
        """meta property returns parsed meta.json dict."""
        store = _init_store(tmp_path)
        meta = store.meta
        assert "id" in meta
        assert "criado_em" in meta
        assert meta["current_version"] is None


# ─────────────────────────────────────────────────────────────────────────────
#  ProjectStore.new_version
# ─────────────────────────────────────────────────────────────────────────────


class TestNewVersion:
    def test_new_version_creates_v1(self, tmp_path):
        """new_version() creates v1 when no versions exist."""
        store = _init_store(tmp_path)
        version = store.new_version()
        assert version == "v1"
        assert (store.root / "v1").exists()

    def test_new_version_creates_v2_v3(self, tmp_path):
        """Successive new_version() calls create v2, v3..."""
        store = _init_store(tmp_path)
        assert store.new_version() == "v1"
        assert store.new_version() == "v2"
        assert store.new_version() == "v3"

    def test_new_version_updates_current_version(self, tmp_path):
        """new_version() updates current_version in meta."""
        store = _init_store(tmp_path)
        store.new_version()
        assert store.current_version() == "v1"
        store.new_version()
        assert store.current_version() == "v2"

    def test_new_version_creates_outputs_dir(self, tmp_path):
        """new_version() creates outputs/ subdirectory."""
        store = _init_store(tmp_path)
        store.new_version()
        assert (store.root / "v1" / "outputs").exists()

    def test_new_version_creates_invocations_log(self, tmp_path):
        """new_version() creates empty invocations.log."""
        store = _init_store(tmp_path)
        store.new_version()
        assert (store.root / "v1" / "invocations.log").exists()

    def test_new_version_copy_on_write(self, tmp_path):
        """new_version() copies canonical from prior version."""
        store = _init_store(tmp_path)
        store.new_version()
        # Write a canonical to v1
        (store.root / "v1" / "canonical.json").write_text(json.dumps(_make_minimal_canonical()), encoding="utf-8")
        store.new_version()  # creates v2, copies from v1
        assert (store.root / "v2" / "canonical.json").exists()


# ─────────────────────────────────────────────────────────────────────────────
#  ProjectStore.load_canonical / save_canonical / write_canonical_raw
# ─────────────────────────────────────────────────────────────────────────────


class TestCanonicalOperations:
    def test_load_canonical_none_when_no_version(self, tmp_path):
        """load_canonical() returns None when no version exists."""
        store = _init_store(tmp_path)
        result = store.load_canonical()
        assert result is None

    def test_load_canonical_none_when_no_file(self, tmp_path):
        """load_canonical() returns None when canonical.json doesn't exist."""
        store = _init_store(tmp_path)
        store.new_version()
        result = store.load_canonical()
        assert result is None

    def test_write_and_load_canonical_raw(self, tmp_path):
        """write_canonical_raw + load_canonical roundtrip."""
        store = _init_store(tmp_path)
        store.new_version()
        raw = _make_minimal_canonical()
        store.write_canonical_raw(raw)
        # Can read back as dict (not full CanonicalModel since minimal)
        content = json.loads((store.root / "v1" / "canonical.json").read_text(encoding="utf-8"))
        assert content["obra"]["nome"] == "Obra Teste"

    def test_write_canonical_raw_no_version_raises(self, tmp_path):
        """write_canonical_raw() raises ValueError when no version active."""
        store = _init_store(tmp_path)
        with pytest.raises(ValueError, match="Nenhuma versão"):
            store.write_canonical_raw({"key": "value"})

    def test_write_canonical_raw_readonly_raises(self, tmp_path):
        """write_canonical_raw() raises PermissionError on approved version."""
        store = _init_store(tmp_path)
        store.new_version()
        store.write_canonical_raw(_make_minimal_canonical())
        store.approve("v1")
        with pytest.raises(PermissionError):
            store.write_canonical_raw({"other": "data"})

    def test_save_canonical_no_version_raises(self, tmp_path):
        """save_canonical() raises ValueError when no version active."""
        store = _init_store(tmp_path)
        with pytest.raises(ValueError):
            store.save_canonical(MagicMock())

    def test_save_canonical_readonly_raises(self, tmp_path):
        """save_canonical() raises PermissionError on approved version."""
        store = _init_store(tmp_path)
        store.new_version()
        store.write_canonical_raw(_make_minimal_canonical())
        store.approve("v1")
        with pytest.raises(PermissionError):
            from unittest.mock import MagicMock

            store.save_canonical(MagicMock())


# ─────────────────────────────────────────────────────────────────────────────
#  ProjectStore.approve
# ─────────────────────────────────────────────────────────────────────────────


class TestApprove:
    def test_approve_marks_canonical_readonly(self, tmp_path):
        """approve() sets canonical.json to read-only (chmod 444)."""
        store = _init_store(tmp_path)
        store.new_version()
        store.write_canonical_raw(_make_minimal_canonical())
        store.approve("v1")

        cf = store.root / "v1" / "canonical.json"
        mode = cf.stat().st_mode
        assert not bool(mode & stat.S_IWUSR)

    def test_approve_nonexistent_version_raises(self, tmp_path):
        """approve() raises FileNotFoundError for non-existent version."""
        store = _init_store(tmp_path)
        with pytest.raises(FileNotFoundError):
            store.approve("v99")

    def test_approve_updates_meta_approved_versions(self, tmp_path):
        """approve() adds version to approved_versions in meta."""
        store = _init_store(tmp_path)
        store.new_version()
        store.write_canonical_raw(_make_minimal_canonical())
        store.approve("v1")
        assert "v1" in store.meta.get("approved_versions", [])

    def test_is_readonly_true_after_approve(self, tmp_path):
        """_is_readonly() returns True after approve()."""
        store = _init_store(tmp_path)
        store.new_version()
        store.write_canonical_raw(_make_minimal_canonical())
        store.approve("v1")
        assert store._is_readonly(store.root / "v1") is True

    def test_is_readonly_false_before_approve(self, tmp_path):
        """_is_readonly() returns False before approve()."""
        store = _init_store(tmp_path)
        store.new_version()
        store.write_canonical_raw(_make_minimal_canonical())
        assert store._is_readonly(store.root / "v1") is False


# ─────────────────────────────────────────────────────────────────────────────
#  ProjectStore.log_invocation
# ─────────────────────────────────────────────────────────────────────────────


class TestLogInvocation:
    def test_log_invocation_appends_jsonl(self, tmp_path):
        """log_invocation() appends a line to invocations.log."""
        store = _init_store(tmp_path)
        store.new_version()
        store.log_invocation("v1", {"skill": "01-escopo-e-eap", "status": "OK"})
        log_path = store.root / "v1" / "invocations.log"
        content = log_path.read_text(encoding="utf-8").strip()
        line = json.loads(content)
        assert line["skill"] == "01-escopo-e-eap"

    def test_log_invocation_multiple_appends(self, tmp_path):
        """log_invocation() appends multiple lines."""
        store = _init_store(tmp_path)
        store.new_version()
        store.log_invocation("v1", {"n": 1})
        store.log_invocation("v1", {"n": 2})
        log_path = store.root / "v1" / "invocations.log"
        lines = [ln for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) == 2


# ─────────────────────────────────────────────────────────────────────────────
#  ProjectStore.save/load/list output files
# ─────────────────────────────────────────────────────────────────────────────


class TestOutputFiles:
    def test_save_and_load_output_file(self, tmp_path):
        """save_output_file + load_output_file roundtrip."""
        store = _init_store(tmp_path)
        store.new_version()
        data = b"binary data content"
        store.save_output_file(data, filename="result.xlsx")
        loaded = store.load_output_file(filename="result.xlsx")
        assert loaded == data

    def test_load_output_file_none_when_no_version(self, tmp_path):
        """load_output_file() returns None when no version active."""
        store = _init_store(tmp_path)
        result = store.load_output_file()
        assert result is None

    def test_load_output_file_none_when_file_missing(self, tmp_path):
        """load_output_file() returns None when file doesn't exist."""
        store = _init_store(tmp_path)
        store.new_version()
        result = store.load_output_file(filename="nonexistent.xlsx")
        assert result is None

    def test_save_output_file_no_version_raises(self, tmp_path):
        """save_output_file() raises ValueError when no version active."""
        store = _init_store(tmp_path)
        with pytest.raises(ValueError):
            store.save_output_file(b"data")

    def test_list_output_files_empty(self, tmp_path):
        """list_output_files() returns [] when no files saved."""
        store = _init_store(tmp_path)
        store.new_version()
        assert store.list_output_files() == []

    def test_list_output_files_returns_names(self, tmp_path):
        """list_output_files() returns sorted list of file names."""
        store = _init_store(tmp_path)
        store.new_version()
        store.save_output_file(b"a", filename="file_b.xlsx")
        store.save_output_file(b"b", filename="file_a.xlsx")
        names = store.list_output_files()
        assert names == ["file_a.xlsx", "file_b.xlsx"]

    def test_list_output_files_no_version_returns_empty(self, tmp_path):
        """list_output_files() returns [] when no version active."""
        store = _init_store(tmp_path)
        result = store.list_output_files()
        assert result == []


# ─────────────────────────────────────────────────────────────────────────────
#  ProjectStore.list_versions / snapshots
# ─────────────────────────────────────────────────────────────────────────────


class TestListVersions:
    def test_list_versions_empty_initially(self, tmp_path):
        """list_versions() returns [] before any version created."""
        store = _init_store(tmp_path)
        assert store.list_versions() == []

    def test_list_versions_ordered(self, tmp_path):
        """list_versions() returns versions sorted numerically."""
        store = _init_store(tmp_path)
        store.new_version()
        store.new_version()
        store.new_version()
        assert store.list_versions() == ["v1", "v2", "v3"]

    def test_snapshots_property(self, tmp_path):
        """snapshots property returns SnapshotStore instance."""
        from concilium.infrastructure.storage.snapshot import SnapshotStore

        store = _init_store(tmp_path)
        assert isinstance(store.snapshots, SnapshotStore)

    def test_version_path(self, tmp_path):
        """version_path() returns correct path for a version."""
        store = _init_store(tmp_path)
        path = store.version_path("v1")
        assert path == store.root / "v1"

    def test_update_meta(self, tmp_path):
        """update_meta() updates meta.json fields."""
        store = _init_store(tmp_path)
        store.update_meta(custom_field="hello")
        assert store.meta["custom_field"] == "hello"
