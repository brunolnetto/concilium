"""Tests for BlobStoragePort-backed stores and store factory — refactoring verification."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage
from concilium.infrastructure.storage.campaign_store import CampaignRunStore

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def blob_storage(tmp_path: Path) -> LocalBlobStorage:
    return LocalBlobStorage(root_dir=tmp_path / "store")


@pytest.fixture()
def campaign_store(blob_storage: LocalBlobStorage) -> CampaignRunStore:
    return CampaignRunStore(storage=blob_storage, prefix="PROJ/campaigns")


# ── CampaignStore via BlobStoragePort ────────────────────────────────────────


class TestCampaignStoreNewRunPersists:
    def test_new_run_creates_run_001(self, campaign_store: CampaignRunStore):
        run = campaign_store.new_run()
        assert run == "run-001"

    def test_new_run_persists_to_blob_storage(self, blob_storage: LocalBlobStorage, campaign_store: CampaignRunStore):
        run = campaign_store.new_run()
        campaign_store.save_meta(run, {"status": "SUCESSO"})
        # The meta.json blob should exist in the storage
        expected_blob = f"PROJ/campaigns/runs/{run}/meta.json"
        assert blob_storage.blob_existe(expected_blob)

    def test_new_run_saves_and_loads_config(self, campaign_store: CampaignRunStore):
        run = campaign_store.new_run()
        cfg = {"campaign_version": "v1", "sweep": [{"campo": "x", "valores": [1, 2]}]}
        campaign_store.save_config(run, cfg)
        loaded = campaign_store.load_config(run)
        assert loaded is not None
        assert loaded["campaign_version"] == "v1"


class TestCampaignStoreListRuns:
    def test_list_runs_returns_three_after_three_new_runs(self, campaign_store: CampaignRunStore):
        campaign_store.new_run()
        campaign_store.new_run()
        campaign_store.new_run()
        assert campaign_store.list_runs() == ["run-001", "run-002", "run-003"]

    def test_list_runs_empty_when_no_runs(self, campaign_store: CampaignRunStore):
        assert campaign_store.list_runs() == []

    def test_list_runs_sorted_numerically(self, campaign_store: CampaignRunStore):
        for _ in range(5):
            campaign_store.new_run()
        runs = campaign_store.list_runs()
        assert runs == sorted(runs, key=lambda r: int(r.split("-")[1]))


class TestCampaignStoreCurrentRun:
    def test_current_run_none_when_empty(self, campaign_store: CampaignRunStore):
        assert campaign_store.current_run() is None

    def test_current_run_returns_latest_after_new_run(self, campaign_store: CampaignRunStore):
        campaign_store.new_run()
        campaign_store.new_run()
        assert campaign_store.current_run() == "run-002"

    def test_current_run_updates_on_each_new_run(self, campaign_store: CampaignRunStore):
        r1 = campaign_store.new_run()
        assert campaign_store.current_run() == r1
        r2 = campaign_store.new_run()
        assert campaign_store.current_run() == r2

    def test_current_run_persisted_to_blob(self, blob_storage: LocalBlobStorage, campaign_store: CampaignRunStore):
        campaign_store.new_run()
        cur_blob = "PROJ/campaigns/runs/current"
        assert blob_storage.blob_existe(cur_blob)
        assert blob_storage.ler_blob(cur_blob).decode() == "run-001"


class TestCampaignStoreBundleAndReport:
    def test_save_and_load_bundle(self, campaign_store: CampaignRunStore):
        run = campaign_store.new_run()
        bundle = {"status": "SUCESSO", "cenarios": []}
        campaign_store.save_bundle(run, bundle)
        loaded = campaign_store.load_bundle(run)
        assert loaded is not None
        assert loaded["status"] == "SUCESSO"

    def test_load_bundle_uses_current_run(self, campaign_store: CampaignRunStore):
        run = campaign_store.new_run()
        campaign_store.save_bundle(run, {"status": "OK"})
        # load_bundle() without arg uses current_run()
        assert campaign_store.load_bundle()["status"] == "OK"

    def test_save_and_load_report_json(self, campaign_store: CampaignRunStore):
        run = campaign_store.new_run()
        report = {"shortlist": [{"rank": 1}]}
        campaign_store.save_report(run, report, md="# Report", pdf=None)
        loaded = campaign_store.load_report_json(run)
        assert loaded is not None
        assert loaded["shortlist"][0]["rank"] == 1

    def test_list_run_files_includes_written_blobs(self, campaign_store: CampaignRunStore):
        run = campaign_store.new_run()
        campaign_store.save_config(run, {"v": "1"})
        campaign_store.save_bundle(run, {})
        campaign_store.save_meta(run, {"status": "OK"})
        files = campaign_store.list_run_files(run)
        assert "inputs/campaign_config.json" in files
        assert "outputs/bundle.json" in files
        assert "meta.json" in files


# ── store_factory: build_blob_storage ────────────────────────────────────────


class TestBuildBlobStorageFilesystem:
    def test_build_blob_storage_returns_local_blob_storage(self, tmp_path: Path, monkeypatch):
        """build_blob_storage() returns LocalBlobStorage for the filesystem backend."""
        import concilium.infrastructure.settings as _settings

        class _FakeStorage:
            root = tmp_path
            config_root = tmp_path
            projects_root = tmp_path / "projetos"
            benchmark_projects_root = None
            backend = "filesystem"
            projects_prefix = "projetos"

            class sharepoint:
                cache_dir = ""

        monkeypatch.setattr(_settings, "get_storage", lambda: _FakeStorage())

        from concilium.infrastructure.storage.store_factory import build_blob_storage

        storage = build_blob_storage()
        assert isinstance(storage, LocalBlobStorage)


class TestEnsureStorageRoot:
    def test_noop_for_non_sharepoint_backend(self, monkeypatch):
        import concilium.infrastructure.storage.store_factory as _sf

        monkeypatch.setattr(_sf, "resolve_store_backend", lambda: "filesystem")
        called = []
        monkeypatch.setattr(_sf, "build_blob_storage", lambda: called.append(True))

        _sf.ensure_storage_root()
        assert called == []

    def test_calls_ensure_root_path_for_sharepoint_backend(self, monkeypatch):
        import concilium.infrastructure.storage.store_factory as _sf
        from concilium.infrastructure.adapters.blob_storage.sharepoint import SharePointBlobStorage

        mock_storage = MagicMock(spec=SharePointBlobStorage)
        system_mock_storage = MagicMock(spec=SharePointBlobStorage)
        monkeypatch.setattr(_sf, "resolve_store_backend", lambda: "sharepoint")
        monkeypatch.setattr(_sf, "build_blob_storage", lambda: mock_storage)
        monkeypatch.setattr(_sf, "build_system_blob_storage", lambda: system_mock_storage)

        _sf.ensure_storage_root()
        mock_storage.ensure_root_path.assert_called_once()
        system_mock_storage.ensure_root_path.assert_called_once()

    def test_noop_when_sharepoint_backend_but_storage_is_not_sharepoint_instance(self, monkeypatch):
        """Guarda defensiva: resolve_store_backend() diz sharepoint mas build_blob_storage()
        retorna outro tipo (config inconsistente) — não deve chamar ensure_root_path."""
        import concilium.infrastructure.storage.store_factory as _sf

        other_storage = MagicMock(spec=LocalBlobStorage)
        monkeypatch.setattr(_sf, "resolve_store_backend", lambda: "sharepoint")
        monkeypatch.setattr(_sf, "build_blob_storage", lambda: other_storage)
        monkeypatch.setattr(_sf, "build_system_blob_storage", lambda: other_storage)

        # Não deve levantar AttributeError nem tentar chamar ensure_root_path,
        # que nem existe em LocalBlobStorage.
        _sf.ensure_storage_root()


class TestStoreFactoryGetCampaignStore:
    def test_get_campaign_store_returns_campaign_run_store(self, tmp_path: Path, monkeypatch):
        """get_campaign_store() returns a CampaignRunStore backed by BlobStoragePort."""
        import concilium.infrastructure.settings as _settings

        class _FakeStorage:
            root = tmp_path
            config_root = tmp_path
            projects_root = tmp_path / "projetos"
            benchmark_projects_root = None
            backend = "filesystem"
            projects_prefix = "projetos"

            class sharepoint:
                cache_dir = ""

        monkeypatch.setattr(_settings, "get_storage", lambda: _FakeStorage())

        from concilium.infrastructure.storage.store_factory import get_campaign_store

        store = get_campaign_store("MYPROJ")
        assert isinstance(store, CampaignRunStore)
        assert store._prefix == "MYPROJ/campaigns"

    def test_get_campaign_store_is_functional(self, tmp_path: Path, monkeypatch):
        """get_campaign_store() returns a store that can create runs and persist data."""
        import concilium.infrastructure.settings as _settings

        class _FakeStorage:
            root = tmp_path
            config_root = tmp_path
            projects_root = tmp_path / "projetos"
            benchmark_projects_root = None
            backend = "filesystem"
            projects_prefix = "projetos"

            class sharepoint:
                cache_dir = ""

        monkeypatch.setattr(_settings, "get_storage", lambda: _FakeStorage())

        from concilium.infrastructure.storage.store_factory import get_campaign_store

        store = get_campaign_store("TESTPROJ")
        run = store.new_run()
        assert run == "run-001"
        store.save_meta(run, {"status": "SUCESSO"})
        meta = store.load_meta(run)
        assert meta is not None
        assert meta["status"] == "SUCESSO"
