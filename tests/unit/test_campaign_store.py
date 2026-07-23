"""CampaignRunStore — testes unitários."""

from __future__ import annotations

from pathlib import Path

import pytest

from concilium.infrastructure.storage.campaign_store import CampaignRunStore


@pytest.fixture
def store(tmp_path: Path) -> CampaignRunStore:
    return CampaignRunStore(project_root=tmp_path / "AGIS")


class TestCampaignRunStore:
    def test_new_run_creates_medallion_structure(self, store: CampaignRunStore):
        run = store.new_run()
        assert run == "run-001"
        assert (store.root / run).is_dir()
        assert (store.root / run / "inputs").is_dir()
        assert (store.root / run / "outputs" / "reports").is_dir()

    def test_sequential_runs(self, store: CampaignRunStore):
        r1 = store.new_run()
        r2 = store.new_run()
        r3 = store.new_run()
        assert r1 == "run-001"
        assert r2 == "run-002"
        assert r3 == "run-003"

    def test_current_run_tracks_latest(self, store: CampaignRunStore):
        assert store.current_run() is None
        store.new_run()
        store.new_run()
        assert store.current_run() == "run-002"

    def test_list_runs_order(self, store: CampaignRunStore):
        store.new_run()
        store.new_run()
        store.new_run()
        assert store.list_runs() == ["run-001", "run-002", "run-003"]

    def test_save_and_load_bundle(self, store: CampaignRunStore):
        run = store.new_run()
        data = {"campaign_id": "test", "status": "SUCESSO", "cenarios": []}
        store.save_bundle(run, data)
        loaded = store.load_bundle(run)
        assert loaded["campaign_id"] == "test"

    def test_load_bundle_current(self, store: CampaignRunStore):
        run = store.new_run()
        store.save_bundle(run, {"status": "INFEASIBLE"})
        assert store.load_bundle()["status"] == "INFEASIBLE"

    def test_save_and_load_report_json(self, store: CampaignRunStore):
        run = store.new_run()
        report = {"meta": {"campaign_id": "x"}, "shortlist": []}
        store.save_report(run, report, md="# Relatório\n", pdf=None)
        loaded = store.load_report_json(run)
        assert loaded["meta"]["campaign_id"] == "x"

    def test_save_report_pdf(self, store: CampaignRunStore):
        run = store.new_run()
        store.save_report(run, {}, md="md", pdf=b"%PDF-1.4 fake")
        assert (store.run_path(run) / "outputs" / "reports" / "campaign_report.pdf").exists()

    def test_save_report_no_pdf(self, store: CampaignRunStore):
        run = store.new_run()
        store.save_report(run, {}, md="md", pdf=None)
        assert not (store.run_path(run) / "campaign_report.pdf").exists()

    def test_save_and_load_meta(self, store: CampaignRunStore):
        run = store.new_run()
        store.save_meta(run, {"status": "SUCESSO", "n_avaliados": 12})
        meta = store.load_meta(run)
        assert meta["status"] == "SUCESSO"
        assert meta["n_avaliados"] == 12
        assert "gerado_em" in meta  # injetado automaticamente

    def test_meta_gerado_em_injected(self, store: CampaignRunStore):
        run = store.new_run()
        store.save_meta(run, {"status": "OK"})
        meta = store.load_meta()
        assert "gerado_em" in meta
        assert "T" in meta["gerado_em"]  # ISO 8601 format

    def test_save_and_load_config(self, store: CampaignRunStore):
        run = store.new_run()
        cfg = {"campaign_version": "v1", "sweep": [{"campo": "n_max", "valores": [1, 2]}]}
        store.save_config(run, cfg)
        loaded = store.load_config(run)
        assert loaded["campaign_version"] == "v1"
        assert loaded["sweep"][0]["campo"] == "n_max"

    def test_list_run_files_medallion_paths(self, store: CampaignRunStore):
        run = store.new_run()
        store.save_config(run, {"version": "v1"})
        store.save_bundle(run, {})
        store.save_meta(run, {"status": "OK"})
        files = store.list_run_files(run)
        assert "inputs/campaign_config.json" in files
        assert "outputs/bundle.json" in files
        assert "meta.json" in files

    def test_runs_are_independent(self, store: CampaignRunStore):
        r1 = store.new_run()
        r2 = store.new_run()
        store.save_meta(r1, {"status": "SUCESSO"})
        store.save_meta(r2, {"status": "INFEASIBLE"})
        assert store.load_meta(r1)["status"] == "SUCESSO"
        assert store.load_meta(r2)["status"] == "INFEASIBLE"

    def test_load_returns_none_when_empty(self, store: CampaignRunStore):
        assert store.load_bundle() is None
        assert store.load_report_json() is None
        assert store.load_meta() is None

    def test_run_path_correct(self, store: CampaignRunStore):
        run = store.new_run()
        assert store.run_path(run) == store.root / run



from unittest.mock import MagicMock  # noqa: E402

# campaign_store.py line 89: raise ValueError when _path is None
# campaign_store.py line 188: non-LocalBlobStorage run_path
# campaign_store.py line 269: load_config returns None when no current run
# ---------------------------------------------------------------------------


class TestCampaignStoreMissingLines:
    def test_init_raises_when_no_path_and_no_storage(self):
        """Line 89: neither storage nor path → ValueError."""
        from concilium.infrastructure.storage.campaign_store import CampaignRunStore

        with pytest.raises(ValueError, match="Forneça"):
            CampaignRunStore()

    def test_run_path_non_local_storage_returns_logical_path(self):
        """Line 188: non-LocalBlobStorage backend → return Path(prefix) / runs / run."""
        from concilium.infrastructure.storage.campaign_store import CampaignRunStore

        mock_storage = MagicMock()
        mock_storage.blob_existe.return_value = False
        store = CampaignRunStore(storage=mock_storage, prefix="campaigns")
        path = store.run_path("run-001")
        assert str(path).endswith("run-001")

    def test_load_config_no_current_run_returns_none(self):
        """Line 269: no current run → return None."""
        from concilium.infrastructure.storage.campaign_store import CampaignRunStore

        mock_storage = MagicMock()
        mock_storage.blob_existe.return_value = False  # no current blob
        mock_storage.listar_blobs.return_value = []  # no runs
        store = CampaignRunStore(storage=mock_storage, prefix="campaigns")
        result = store.load_config(run=None)
        assert result is None


# ---------------------------------------------------------------------------

