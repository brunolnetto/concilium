"""Tests for campaign_store.py and cube_projection_views.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ─── infrastructure/storage/campaign_store.py ─────────────────────────────────

def _make_store(tmp_path):
    from concilium.infrastructure.storage.campaign_store import CampaignRunStore
    project_root = tmp_path / "projetos" / "AGIS"
    project_root.mkdir(parents=True)
    return CampaignRunStore(project_root)


class TestCampaignRunStore:
    def test_new_run_creates_directories(self, tmp_path):
        store = _make_store(tmp_path)
        run = store.new_run()
        assert run == "run-001"

    def test_new_run_increments(self, tmp_path):
        store = _make_store(tmp_path)
        store.new_run()
        run = store.new_run()
        assert run == "run-002"

    def test_list_runs_empty(self, tmp_path):
        store = _make_store(tmp_path)
        assert store.list_runs() == []

    def test_list_runs_after_new(self, tmp_path):
        store = _make_store(tmp_path)
        store.new_run()
        runs = store.list_runs()
        assert runs == ["run-001"]

    def test_current_run_none_when_empty(self, tmp_path):
        store = _make_store(tmp_path)
        assert store.current_run() is None

    def test_current_run_returns_latest(self, tmp_path):
        store = _make_store(tmp_path)
        store.new_run()
        assert store.current_run() == "run-001"

    def test_save_and_load_config(self, tmp_path):
        store = _make_store(tmp_path)
        run = store.new_run()
        store.save_config(run, {"sweep": [{"campo": "dias_semana"}]})
        loaded = store.load_config(run)
        assert loaded["sweep"][0]["campo"] == "dias_semana"

    def test_save_and_load_bundle(self, tmp_path):
        store = _make_store(tmp_path)
        run = store.new_run()
        store.save_bundle(run, {"shortlist": []})
        loaded = store.load_bundle(run)
        assert loaded == {"shortlist": []}

    def test_load_bundle_missing_returns_none(self, tmp_path):
        store = _make_store(tmp_path)
        store.new_run()
        assert store.load_bundle("run-999") is None

    def test_save_and_load_meta(self, tmp_path):
        store = _make_store(tmp_path)
        run = store.new_run()
        store.save_meta(run, {"status": "OK", "n_avaliados": 4})
        meta = store.load_meta(run)
        assert meta["status"] == "OK"
        assert "gerado_em" in meta

    def test_save_report_with_pdf(self, tmp_path):
        store = _make_store(tmp_path)
        run = store.new_run()
        store.save_report(run, {"data": "report"}, "# Report", pdf=b"%PDF-1.4")
        loaded = store.load_report_json(run)
        assert loaded["data"] == "report"

    def test_save_report_without_pdf(self, tmp_path):
        store = _make_store(tmp_path)
        run = store.new_run()
        store.save_report(run, {"result": "ok"}, "# MD", pdf=None)
        loaded = store.load_report_json(run)
        assert loaded is not None

    def test_list_run_files(self, tmp_path):
        store = _make_store(tmp_path)
        run = store.new_run()
        store.save_config(run, {"key": "val"})
        files = store.list_run_files(run)
        assert len(files) > 0

    def test_list_run_files_no_current(self, tmp_path):
        store = _make_store(tmp_path)
        # No runs yet
        files = store.list_run_files()
        assert files == []

    def test_run_path_returns_path(self, tmp_path):
        store = _make_store(tmp_path)
        run = store.new_run()
        p = store.run_path(run)
        assert isinstance(p, Path)

    def test_from_project_root_classmethod(self, tmp_path):
        from concilium.infrastructure.storage.campaign_store import CampaignRunStore
        proj = tmp_path / "proj"
        proj.mkdir()
        store = CampaignRunStore.from_project_root(proj)
        assert store is not None

    def test_from_project_root_with_slug(self, tmp_path):
        from concilium.infrastructure.storage.campaign_store import CampaignRunStore
        store = CampaignRunStore.from_project_root(tmp_path, slug="AGIS")
        assert store is not None

    def test_save_cube(self, tmp_path):
        store = _make_store(tmp_path)
        run = store.new_run()
        store.save_cube(run, {"pivot": {}})
        # No crash


# ─── application/services/analytics/cube_projection_views.py ──────────────────

class TestCubeProjectionViews:
    def test_bucket_from_week_iso(self):
        from concilium.application.services.analytics.cube_projection_views import bucket_from_week_iso
        result = bucket_from_week_iso("2026-W10", "mes")
        assert isinstance(result, str)

    def test_bucket_from_week_iso_semana(self):
        from concilium.application.services.analytics.cube_projection_views import bucket_from_week_iso
        result = bucket_from_week_iso("2026-W10", "semana")
        assert result == "2026-W10"

    def test_resolve_cubo_projection_rows_with_canonical(self):
        from concilium.application.services.analytics.cube_projection_views import resolve_cubo_projection_rows
        canonical = MagicMock()
        canonical.cronograma.scheduled_activities = []
        canonical.cronograma.makespan_weeks = 0
        canonical.equipes_diretas = []
        rows, cols, label = resolve_cubo_projection_rows(None, face="tempo_natureza", granularidade="semana", top_n=10, canonical=canonical)
        assert isinstance(rows, list)

    def test_resolve_recursos_ativos_rows_mock_canonical(self):
        from concilium.application.services.analytics.cube_projection_views import resolve_recursos_ativos_rows
        canonical = MagicMock()
        canonical.cronograma.scheduled_activities = []
        canonical.cronograma.makespan_weeks = 0
        canonical.equipes_diretas = []
        rows, cols, label, meta, extra = resolve_recursos_ativos_rows(canonical, granularidade="semana", top_n=10)
        assert isinstance(rows, list)

    def test_resolve_s_curve_rows_mock_canonical(self):
        from concilium.application.services.analytics.cube_projection_views import resolve_s_curve_rows
        canonical = MagicMock()
        canonical.cronograma.scheduled_activities = []
        canonical.cronograma.makespan_weeks = 0
        canonical.equipes_diretas = []
        canonical.resultado = None
        rows, cols, label, meta, extra = resolve_s_curve_rows(canonical, granularidade="semana", top_n=10)
        assert isinstance(rows, list)

    def test_resolve_abc_curva_rows_mock_canonical(self):
        from concilium.application.services.analytics.cube_projection_views import resolve_abc_curva_rows
        canonical = MagicMock()
        canonical.equipes_diretas = []
        rows, cols, label, meta, extra = resolve_abc_curva_rows(canonical, top_n=10, threshold_a=0.8, threshold_b=0.95)
        assert isinstance(rows, list)

    def test_build_cube_projection_payload_empty(self):
        from concilium.application.services.analytics.cube_projection_views import build_cube_projection_payload
        canonical = MagicMock()
        canonical.cronograma.scheduled_activities = []
        canonical.cronograma.makespan_weeks = 0
        canonical.equipes_diretas = []
        canonical.resultado = None
        result = build_cube_projection_payload(canonical=canonical, cubo=None, face="tempo_natureza", granularidade="semana", top_n=5)
        assert isinstance(result, dict)
