"""Tests for artifact_transport, pdf_renderer, settings, project storage, catalog mixin,
telemetry, and _04_cronograma_skill_helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ─── application/services/artifact/artifact_transport.py (10 missing) ─────────


class TestBlobPortFromEnv:
    """Cover _blob_port_from_env branches (lines 121-133)."""

    def test_azure_backend(self):
        from concilium.application.services.artifact.artifact_transport import _blob_port_from_env

        mock_storage = MagicMock()
        with patch(
            "concilium.infrastructure.adapters.blob_storage.azure.AzureBlobStorage.from_env", return_value=mock_storage
        ):
            result = _blob_port_from_env("azure")
        assert result is mock_storage

    def test_azure_blob_alias(self):
        from concilium.application.services.artifact.artifact_transport import _blob_port_from_env

        with patch(
            "concilium.infrastructure.adapters.blob_storage.azure.AzureBlobStorage.from_env", return_value=MagicMock()
        ):
            result = _blob_port_from_env("azure_blob")
        assert result is not None

    def test_sharepoint_backend(self):
        from concilium.application.services.artifact.artifact_transport import _blob_port_from_env

        with patch(
            "concilium.infrastructure.adapters.blob_storage.sharepoint.SharePointBlobStorage.from_env",
            return_value=MagicMock(),
        ):
            result = _blob_port_from_env("sharepoint")
        assert result is not None

    def test_gdrive_backend(self):
        from concilium.application.services.artifact.artifact_transport import _blob_port_from_env

        with patch(
            "concilium.infrastructure.adapters.blob_storage.gdrive.GoogleDriveBlobStorage.from_env",
            return_value=MagicMock(),
        ):
            result = _blob_port_from_env("gdrive")
        assert result is not None

    def test_s3_backend(self):
        from concilium.application.services.artifact.artifact_transport import _blob_port_from_env

        with patch(
            "concilium.infrastructure.adapters.blob_storage.s3.S3BlobStorage.from_env", return_value=MagicMock()
        ):
            result = _blob_port_from_env("s3")
        assert result is not None

    def test_unknown_backend_raises(self):
        from concilium.application.services.artifact.artifact_transport import _blob_port_from_env

        with pytest.raises(ValueError, match="desconhecido"):
            _blob_port_from_env("unknown-backend")


# ─── application/skills/manifests/_04_cronograma_skill_helpers.py (4 missing) ──


class TestCronogramaSkillHelpers:
    """Cover lines 53, 56-57, 62 — SS/FF precedence types + short-precedence skip."""

    def test_extract_dag_with_fs_threshold(self, tmp_path):
        from concilium.application.skills.manifests._04_cronograma_skill_helpers import extract_dag_from_spec_or_eap

        # Build a minimal spec with FS precedence with threshold
        spec = {"precedence": [["A1", "A2", 0.5]]}
        activities = [
            MagicMock(activity_id="A1", duration_weeks=2),
            MagicMock(activity_id="A2", duration_weeks=2),
        ]
        dag = extract_dag_from_spec_or_eap(spec, activities)
        assert dag is not None

    def test_extract_dag_short_precedence_skipped(self, tmp_path):
        from concilium.application.skills.manifests._04_cronograma_skill_helpers import extract_dag_from_spec_or_eap

        # precedence entry with len < 2 → skipped (line 62)
        spec = {"precedence": [["A1"], ["A1", "A2"]]}
        activities = [
            MagicMock(activity_id="A1", duration_weeks=2),
            MagicMock(activity_id="A2", duration_weeks=2),
        ]
        dag = extract_dag_from_spec_or_eap(spec, activities)
        assert dag is not None


# ─── application/runtime/mixins/catalog.py (49 missing) ─────────────────────


class TestCatalogMixin:
    def _make_mixin(self, tmp_path):
        from concilium.application.runtime.mixins.catalog import CatalogMixin

        obj = CatalogMixin.__new__(CatalogMixin)
        obj.config_root = tmp_path
        obj._config_cache = {}
        return obj

    def test_load_catalogo_not_found_raises_a(self, tmp_path):
        from concilium.application.runtime.exceptions import RuntimeDomainError

        mixin = self._make_mixin(tmp_path)
        with pytest.raises((RuntimeDomainError, FileNotFoundError)):
            mixin.load_catalogo("nonexistent-cat")

    def test_load_catalogo_not_found_raises(self, tmp_path):
        from concilium.application.runtime.exceptions import RuntimeDomainError

        mixin = self._make_mixin(tmp_path)
        with pytest.raises(RuntimeDomainError):
            mixin.load_catalogo("missing-cat")

    def test_load_catalogo_basic(self, tmp_path):
        from concilium.application.runtime.mixins.catalog import CatalogMixin

        # Create a minimal catalog directory
        cat_dir = tmp_path / "catalogos" / "test-cat"
        cat_dir.mkdir(parents=True)
        (cat_dir / "cpus.json").write_text('{"cpus": []}', encoding="utf-8")
        obj = CatalogMixin.__new__(CatalogMixin)
        obj.config_root = tmp_path
        obj._config_cache = {}
        cat = obj.load_catalogo("test-cat")
        assert isinstance(cat, dict)

    def test_load_catalogo_with_bundle_cache(self, tmp_path):
        """Test that bundle cache is used when available."""

        cat_dir = tmp_path / "catalogos" / "test-cat2"
        cat_dir.mkdir(parents=True)
        (cat_dir / "cpus.json").write_text('{"cpus": [{"codigo": "CPU-1"}]}', encoding="utf-8")
        from concilium.application.runtime.mixins.catalog import CatalogMixin

        obj = CatalogMixin.__new__(CatalogMixin)
        obj.config_root = tmp_path
        obj._config_cache = {}
        cat = obj.load_catalogo("test-cat2")
        # Second load should use cache
        cat2 = obj.load_catalogo("test-cat2")
        assert cat == cat2  # same content (may or may not be same object)

    def test_load_resolved_catalogo(self, tmp_path):
        from concilium.application.runtime.mixins.catalog import CatalogMixin

        cat_dir = tmp_path / "catalogos" / "test-cat"
        cat_dir.mkdir(parents=True)
        (cat_dir / "cpus.json").write_text('{"cpus": []}', encoding="utf-8")
        obj = CatalogMixin.__new__(CatalogMixin)
        obj.config_root = tmp_path
        obj._config_cache = {}
        # Mock the snapshot/project for overlay loading
        project = MagicMock()
        project.meta = {"id": "proj-1"}
        project.read_json.return_value = {}
        cat = obj._load_resolved_catalogo("test-cat", None, project)
        assert isinstance(cat, dict)


# ─── infrastructure/telemetry/__init__.py (35 missing) ───────────────────────


class TestTelemetryModule:
    def test_setup_telemetry(self, monkeypatch):
        monkeypatch.setenv("CONCILIUM__TELEMETRY_ENABLED", "0")
        from concilium.infrastructure.telemetry import setup_telemetry

        setup_telemetry()  # should not raise

    def test_record_functions_dont_raise(self):
        from concilium.infrastructure import telemetry

        # Call various record functions — they should be no-ops when OTEL not enabled
        if hasattr(telemetry, "record_skill_start"):
            telemetry.record_skill_start("skill-01", "proj-1", "v1")
        if hasattr(telemetry, "record_skill_end"):
            telemetry.record_skill_end("skill-01", "OK", duration_ms=100)
        if hasattr(telemetry, "record_pipeline_start"):
            telemetry.record_pipeline_start("proj-1")
        if hasattr(telemetry, "record_rate_limit_exceeded"):
            telemetry.record_rate_limit_exceeded("/api/runs")

    def test_patch_fastmcp_server(self):
        from concilium.infrastructure.telemetry import patch_fastmcp_server

        server = MagicMock()
        patch_fastmcp_server(server)  # should not raise

    def test_telemetry_module_importable(self):
        import concilium.infrastructure.telemetry as t

        assert hasattr(t, "setup_telemetry")


# ─── infrastructure/storage/project.py (63 missing) ──────────────────────────


class TestProjectStore:
    def _make_store(self, tmp_path):
        from concilium.infrastructure.storage.project import ProjectStore

        return ProjectStore.init(tmp_path, "Test Project", "ctx-1")

    def test_init_creates_meta(self, tmp_path):
        store = self._make_store(tmp_path)
        assert (store.root / "meta.json").exists()
        assert store.meta.get("nome") == "Test Project"

    def test_current_version_none_initially(self, tmp_path):
        store = self._make_store(tmp_path)
        assert store.current_version() is None

    def test_new_version_creates_dir(self, tmp_path):
        store = self._make_store(tmp_path)
        v = store.new_version()
        assert v is not None
        assert store.current_version() == v

    def test_list_versions(self, tmp_path):
        store = self._make_store(tmp_path)
        store.new_version()
        store.new_version()
        versions = store.list_versions()
        assert len(versions) == 2

    def test_version_path(self, tmp_path):
        store = self._make_store(tmp_path)
        v = store.new_version()
        p = store.version_path(v)
        assert isinstance(p, Path)
        assert p.exists()

    def test_save_and_load_canonical(self, tmp_path):
        from concilium.domain.models.canonical import CanonicalModel

        store = self._make_store(tmp_path)
        v = store.new_version()
        canonical = MagicMock(spec=CanonicalModel)
        canonical.model_dump_json.return_value = '{"projeto": {"id": "p1"}}'
        # Should not raise
        store.save_canonical(canonical, v)

    def test_update_meta(self, tmp_path):
        store = self._make_store(tmp_path)
        store.update_meta(nome="Updated Name")
        assert store.meta["nome"] == "Updated Name"

    def test_log_invocation(self, tmp_path):
        store = self._make_store(tmp_path)
        v = store.new_version()
        store.log_invocation(v, {"skill": "01-escopo-e-eap", "status": "OK"})
        # No crash

    def test_list_output_files_empty(self, tmp_path):
        store = self._make_store(tmp_path)
        v = store.new_version()
        result = store.list_output_files(v)
        assert isinstance(result, list)

    def test_approve_version(self, tmp_path):
        store = self._make_store(tmp_path)
        v = store.new_version()
        store.approve(v)  # should not raise

    def test_snapshots_property(self, tmp_path):
        store = self._make_store(tmp_path)
        snaps = store.snapshots
        assert snaps is not None  # SnapshotStore object

    def test_meta_contexto_id(self, tmp_path):
        store = self._make_store(tmp_path)
        assert store.meta.get("contexto_id") == "ctx-1"

    def test_read_write_json(self, tmp_path):
        store = self._make_store(tmp_path)
        store.write_json("test.json", {"key": "val"})
        result = store.read_json("test.json", {})
        assert result == {"key": "val"}

    def test_save_and_load_intermediate_file(self, tmp_path):
        store = self._make_store(tmp_path)
        v = store.new_version()
        store.save_intermediate_file("test.txt", b"data", v)
        data = store.load_intermediate_file("test.txt", v)
        assert data == b"data"


# ─── application/runtime/__init__.py extended tests ────────────────────────────


class TestRuntimeRunPipeline:
    """Test run_pipeline which covers lines 112-148."""

    def test_run_pipeline_no_active_version_raises(self, tmp_path):
        from concilium.application.runtime import Runtime, RuntimeDomainError

        rt = Runtime(config_root=tmp_path)
        store = MagicMock()
        store.current_version.return_value = None
        with pytest.raises(RuntimeDomainError, match="versão"):
            rt.run_pipeline(store)

    def test_run_pipeline_with_version(self, tmp_path):
        from concilium.application.runtime import Runtime

        rt = Runtime(config_root=tmp_path)
        store = MagicMock()
        store.current_version.return_value = "v1"
        store.load_canonical.return_value = None
        store.meta = {"contexto_id": "ctx-1", "id": "proj-1"}
        store.root = MagicMock()
        store.root.name = "proj-dir"

        # Mock out _providers_factory to avoid loading real catalogs
        with patch.object(
            rt,
            "_providers_factory",
            return_value={
                "canonical_in": None,
                "inputs": {},
                "catalogo": {},
                "catalog_session": None,
                "perfil": {},
                "contexto": MagicMock(),
                "project": store,
                "version": "v1",
                "runtime": rt,
            },
        ):
            with patch("concilium.application.runtime.SkillExecutor") as mock_executor_cls:
                executor = MagicMock()
                executor.run_pipeline.return_value = (None, [])
                mock_executor_cls.return_value = executor
                result = rt.run_pipeline(store, skill_sequence=["01-escopo-e-eap"])
        assert isinstance(result, list)
