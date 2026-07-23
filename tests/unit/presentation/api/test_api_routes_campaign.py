"""Coverage tests for concilium.presentation.api.routes.campaign.

This module had zero prior test coverage. Its handlers do most of their
imports lazily inside the function bodies, so collaborators are patched at
their *defining* module (that's where `from x import y` resolves at call
time), while simple dataclasses (ParametroSweep, PerfilExpectativas,
GoResearchCampaignBundle) and the real CampaignRunStore (backed by a tmp_path
directory) are used as-is to keep the tests meaningful.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import BackgroundTasks, HTTPException


def _svc(project_dict=None):
    svc = MagicMock()
    svc.get_project.return_value = project_dict or {}
    return svc


class TestGetStore:
    def test_get_store_project_not_found_raises_404(self, tmp_path):
        from concilium.presentation.api.routes.campaign import _get_store

        svc = _svc()
        svc.get_project.side_effect = FileNotFoundError("no such project")
        storage = MagicMock(projects_root=tmp_path)
        with patch("concilium.infrastructure.settings.get_storage", return_value=storage):
            with pytest.raises(HTTPException) as exc:
                _get_store(svc, "proj-1")
        assert exc.value.status_code == 404

    def test_get_store_uses_tools_root_when_projects_root_none(self, tmp_path):
        from concilium.presentation.api.routes.campaign import _get_store

        svc = _svc()
        storage = MagicMock(projects_root=None)
        with (
            patch("concilium.infrastructure.settings.get_storage", return_value=storage),
            patch("concilium.presentation.cli.shared._tools_root", return_value=tmp_path),
        ):
            store = _get_store(svc, "proj-1")
        assert store.run_path("run-001").parent.parent.parent == tmp_path / "projetos" / "PROJ-1"

    def test_get_store_happy_path(self, tmp_path):
        from concilium.presentation.api.routes.campaign import _get_store

        svc = _svc()
        storage = MagicMock(projects_root=tmp_path)
        with patch("concilium.infrastructure.settings.get_storage", return_value=storage):
            store = _get_store(svc, "proj-1")
        assert store is not None


class TestListCampaignRuns:
    def test_list_campaign_runs_empty(self, tmp_path):
        from concilium.presentation.api.routes.campaign import list_campaign_runs

        svc = _svc()
        storage = MagicMock(projects_root=tmp_path)
        with patch("concilium.infrastructure.settings.get_storage", return_value=storage):
            items = list_campaign_runs("proj-1", service=svc)
        assert items == []

    def test_list_campaign_runs_reversed_with_meta(self, tmp_path):
        from concilium.presentation.api.routes.campaign import _get_store, list_campaign_runs

        svc = _svc()
        storage = MagicMock(projects_root=tmp_path)
        with patch("concilium.infrastructure.settings.get_storage", return_value=storage):
            store = _get_store(svc, "proj-1")
            run_a = store.new_run()
            store.save_meta(
                run_a,
                {
                    "campaign_version": "v1",
                    "status": "DONE",
                    "n_avaliados": 3,
                    "n_viaveis": 1,
                    "gerado_em": "2026-01-01",
                },
            )
            run_b = store.new_run()
            # No meta saved for run_b -> load_meta returns falsy/None -> {} branch.

            items = list_campaign_runs("proj-1", service=svc)

        assert [item["run_id"] for item in items] == [run_b, run_a]
        assert items[1]["campaign_version"] == "v1"
        assert items[0]["campaign_version"] is None


class TestGetCampaignRun:
    def test_run_not_found_raises_404(self, tmp_path):
        from concilium.presentation.api.routes.campaign import get_campaign_run

        svc = _svc()
        storage = MagicMock(projects_root=tmp_path)
        with patch("concilium.infrastructure.settings.get_storage", return_value=storage):
            with pytest.raises(HTTPException) as exc:
                get_campaign_run("proj-1", "run-999", service=svc)
        assert exc.value.status_code == 404

    def test_run_found_bundle_none_still_running(self, tmp_path):
        from concilium.presentation.api.routes.campaign import _get_store, get_campaign_run

        svc = _svc()
        storage = MagicMock(projects_root=tmp_path)
        with patch("concilium.infrastructure.settings.get_storage", return_value=storage):
            store = _get_store(svc, "proj-1")
            run_id = store.new_run()
            store.save_meta(run_id, {"status": "RUNNING"})
            result = get_campaign_run("proj-1", run_id, service=svc)
        assert result["bundle"] is None
        assert result["meta"]["status"] == "RUNNING"

    def test_run_found_with_bundle(self, tmp_path):
        from concilium.presentation.api.routes.campaign import _get_store, get_campaign_run

        svc = _svc()
        storage = MagicMock(projects_root=tmp_path)
        with patch("concilium.infrastructure.settings.get_storage", return_value=storage):
            store = _get_store(svc, "proj-1")
            run_id = store.new_run()
            store.save_meta(run_id, {"status": "DONE"})
            store.save_bundle(run_id, {"foo": "bar"})
            result = get_campaign_run("proj-1", run_id, service=svc)
        assert result["bundle"] == {"foo": "bar"}


class TestGetCampaignRunReport:
    def test_run_not_found_raises_404(self, tmp_path):
        from concilium.presentation.api.routes.campaign import get_campaign_run_report

        svc = _svc()
        storage = MagicMock(projects_root=tmp_path)
        with patch("concilium.infrastructure.settings.get_storage", return_value=storage):
            with pytest.raises(HTTPException) as exc:
                get_campaign_run_report("proj-1", "run-999", format="json", service=svc)
        assert exc.value.status_code == 404

    def test_json_report_not_yet_available(self, tmp_path):
        from concilium.presentation.api.routes.campaign import _get_store, get_campaign_run_report

        svc = _svc()
        storage = MagicMock(projects_root=tmp_path)
        with patch("concilium.infrastructure.settings.get_storage", return_value=storage):
            store = _get_store(svc, "proj-1")
            run_id = store.new_run()
            store.save_meta(run_id, {"status": "RUNNING"})
            with pytest.raises(HTTPException) as exc:
                get_campaign_run_report("proj-1", run_id, format="json", service=svc)
        assert exc.value.status_code == 404

    def test_json_report_available(self, tmp_path):
        from concilium.presentation.api.routes.campaign import _get_store, get_campaign_run_report

        svc = _svc()
        storage = MagicMock(projects_root=tmp_path)
        with patch("concilium.infrastructure.settings.get_storage", return_value=storage):
            store = _get_store(svc, "proj-1")
            run_id = store.new_run()
            store.save_meta(run_id, {"status": "DONE"})
            store.save_report(run_id, {"ok": True}, "# md", b"%PDF-1.4")
            response = get_campaign_run_report("proj-1", run_id, format="json", service=svc)
        assert b'"ok"' in response.body

    def test_md_report_not_yet_available(self, tmp_path):
        from concilium.presentation.api.routes.campaign import _get_store, get_campaign_run_report

        svc = _svc()
        storage = MagicMock(projects_root=tmp_path)
        with patch("concilium.infrastructure.settings.get_storage", return_value=storage):
            store = _get_store(svc, "proj-1")
            run_id = store.new_run()
            store.save_meta(run_id, {"status": "RUNNING"})
            with pytest.raises(HTTPException) as exc:
                get_campaign_run_report("proj-1", run_id, format="md", service=svc)
        assert exc.value.status_code == 404

    def test_md_report_available(self, tmp_path):
        from concilium.presentation.api.routes.campaign import _get_store, get_campaign_run_report

        svc = _svc()
        storage = MagicMock(projects_root=tmp_path)
        with patch("concilium.infrastructure.settings.get_storage", return_value=storage):
            store = _get_store(svc, "proj-1")
            run_id = store.new_run()
            store.save_meta(run_id, {"status": "DONE"})
            store.save_report(run_id, {"ok": True}, "# hello", b"%PDF-1.4")
            response = get_campaign_run_report("proj-1", run_id, format="md", service=svc)
        assert response.body == b"# hello"

    def test_pdf_report_not_yet_available(self, tmp_path):
        from concilium.presentation.api.routes.campaign import _get_store, get_campaign_run_report

        svc = _svc()
        storage = MagicMock(projects_root=tmp_path)
        with patch("concilium.infrastructure.settings.get_storage", return_value=storage):
            store = _get_store(svc, "proj-1")
            run_id = store.new_run()
            store.save_meta(run_id, {"status": "RUNNING"})
            with pytest.raises(HTTPException) as exc:
                get_campaign_run_report("proj-1", run_id, format="pdf", service=svc)
        assert exc.value.status_code == 404

    def test_pdf_report_available(self, tmp_path):
        from concilium.presentation.api.routes.campaign import _get_store, get_campaign_run_report

        svc = _svc()
        storage = MagicMock(projects_root=tmp_path)
        with patch("concilium.infrastructure.settings.get_storage", return_value=storage):
            store = _get_store(svc, "proj-1")
            run_id = store.new_run()
            store.save_meta(run_id, {"status": "DONE"})
            store.save_report(run_id, {"ok": True}, "# hello", b"%PDF-1.4")
            response = get_campaign_run_report("proj-1", run_id, format="pdf", service=svc)
        assert response.body == b"%PDF-1.4"
        assert "campaign_report_" in response.headers["content-disposition"]


class TestRunCampaign:
    def _req(self, **kwargs):
        from concilium.presentation.api.routes.campaign import CampaignRunRequest

        return CampaignRunRequest(**kwargs)

    def test_project_not_found_raises_404(self, tmp_path):
        from concilium.presentation.api.routes.campaign import run_campaign

        svc = _svc()
        svc.get_project.side_effect = FileNotFoundError("nope")
        storage = MagicMock(projects_root=tmp_path, config_root=tmp_path)
        with patch("concilium.infrastructure.settings.get_storage", return_value=storage):
            with pytest.raises(HTTPException) as exc:
                run_campaign("proj-1", self._req(), BackgroundTasks(), service=svc)
        assert exc.value.status_code == 404

    def test_projects_root_none_falls_back_to_tools_root(self, tmp_path):
        """Branch 124->125: storage.projects_root is None → usa _tools_root()/projetos
        (linhas 125,127)."""
        from concilium.presentation.api.routes.campaign import run_campaign

        svc = _svc()
        svc.get_project.side_effect = FileNotFoundError("nope")
        storage = MagicMock(projects_root=None, config_root=tmp_path)
        with (
            patch("concilium.infrastructure.settings.get_storage", return_value=storage),
            patch("concilium.presentation.cli.shared._tools_root", return_value=tmp_path),
        ):
            with pytest.raises(HTTPException) as exc:
                run_campaign("proj-1", self._req(), BackgroundTasks(), service=svc)
        assert exc.value.status_code == 404

    def test_intent_not_rfp_raises_422(self, tmp_path):
        from concilium.presentation.api.routes.campaign import run_campaign

        svc = _svc()
        storage = MagicMock(projects_root=tmp_path, config_root=tmp_path)
        with patch("concilium.infrastructure.settings.get_storage", return_value=storage):
            with pytest.raises(HTTPException) as exc:
                run_campaign("proj-1", self._req(procurement_intent="rfi"), BackgroundTasks(), service=svc)
        assert exc.value.status_code == 422

    def test_explicit_campaign_file_missing_raises_404(self, tmp_path):
        from concilium.presentation.api.routes.campaign import run_campaign

        svc = _svc()
        storage = MagicMock(projects_root=tmp_path, config_root=tmp_path)
        missing = tmp_path / "nope.json"
        with patch("concilium.infrastructure.settings.get_storage", return_value=storage):
            with pytest.raises(HTTPException) as exc:
                run_campaign(
                    "proj-1",
                    self._req(campaign_file=str(missing)),
                    BackgroundTasks(),
                    service=svc,
                )
        assert exc.value.status_code == 404

    def test_default_campaign_file_candidates_missing_raises_404(self, tmp_path):
        from concilium.presentation.api.routes.campaign import run_campaign

        svc = _svc()
        storage = MagicMock(projects_root=tmp_path, config_root=tmp_path)
        with patch("concilium.infrastructure.settings.get_storage", return_value=storage):
            with pytest.raises(HTTPException) as exc:
                run_campaign("proj-1", self._req(), BackgroundTasks(), service=svc)
        assert exc.value.status_code == 404

    def test_base_spec_none_raises_422(self, tmp_path):
        from concilium.presentation.api.routes.campaign import run_campaign

        svc = _svc()
        storage = MagicMock(projects_root=tmp_path, config_root=tmp_path)
        campaign_file = tmp_path / "PROJ-1" / "campaigns" / "campaign_v1.json"
        campaign_file.parent.mkdir(parents=True)
        campaign_file.write_text("{}", encoding="utf-8")
        with (
            patch("concilium.infrastructure.settings.get_storage", return_value=storage),
            patch(
                "concilium.presentation.cli.commands_campaign._load_project_base_spec",
                return_value=None,
            ),
        ):
            with pytest.raises(HTTPException) as exc:
                run_campaign("proj-1", self._req(), BackgroundTasks(), service=svc)
        assert exc.value.status_code == 422

    def test_happy_path_queues_background_task(self, tmp_path):
        from concilium.presentation.api.routes.campaign import run_campaign

        svc = _svc()
        storage = MagicMock(projects_root=tmp_path, config_root=tmp_path)
        campaign_file = tmp_path / "PROJ-1" / "campaigns" / "campaign_v1.json"
        campaign_file.parent.mkdir(parents=True)
        campaign_file.write_text(
            '{"perfil_expectativas": {"meta_margem_pct": 0.15}, "sweep": [{"campo": "x", "valores": [1, 2]}],'
            ' "top_k": 3, "campaign_version": "v2"}',
            encoding="utf-8",
        )
        bg = BackgroundTasks()
        with (
            patch("concilium.infrastructure.settings.get_storage", return_value=storage),
            patch(
                "concilium.presentation.cli.commands_campaign._load_project_base_spec",
                return_value={"foo": "bar"},
            ),
        ):
            result = run_campaign("proj-1", self._req(), bg, service=svc)

        assert result["status"] == "RUNNING"
        assert "run_id" in result
        assert len(bg.tasks) == 1

        # Meta was saved eagerly with RUNNING status.
        from concilium.infrastructure.storage.campaign_store import CampaignRunStore

        store = CampaignRunStore(tmp_path / "PROJ-1")
        meta = store.load_meta(result["run_id"])
        assert meta["status"] == "RUNNING"
        assert meta["campaign_version"] == "v2"

    def test_background_task_success_persists_report(self, tmp_path):
        from concilium.presentation.api.routes.campaign import run_campaign

        svc = _svc()
        storage = MagicMock(projects_root=tmp_path, config_root=tmp_path)
        campaign_file = tmp_path / "PROJ-1" / "campaigns" / "campaign_v1.json"
        campaign_file.parent.mkdir(parents=True)
        campaign_file.write_text("{}", encoding="utf-8")
        bg = BackgroundTasks()

        fake_result = MagicMock(
            campaign_version="v1",
            status="CONCLUIDO",
            n_cenarios_avaliados=10,
            n_cenarios_viaveis=4,
            n_falhas=0,
        )
        with (
            patch("concilium.infrastructure.settings.get_storage", return_value=storage),
            patch(
                "concilium.presentation.cli.commands_campaign._load_project_base_spec",
                return_value={"foo": "bar"},
            ),
            patch(
                "concilium.application.services.campaign.campaign_service.executar_campanha",
                return_value=fake_result,
            ),
            patch(
                "concilium.application.services.campaign.campaign_service.construir_cubo",
                return_value={"cube": True},
            ),
            patch(
                "concilium.application.services.campaign.campaign_report.serialize_campaign_report",
                return_value={"cubo": {"cube": True}, "ok": True},
            ),
            patch(
                "concilium.application.services.campaign.campaign_report.render_campaign_report_md",
                return_value="# report",
            ),
            patch(
                "concilium.application.services.campaign.campaign_report.render_campaign_report_pdf",
                return_value=b"%PDF-1.4",
            ),
        ):
            result = run_campaign("proj-1", self._req(), bg, service=svc)
            bg.tasks[0].func()

        from concilium.infrastructure.storage.campaign_store import CampaignRunStore

        store = CampaignRunStore(tmp_path / "PROJ-1")
        meta = store.load_meta(result["run_id"])
        assert meta["status"] == "CONCLUIDO"
        assert meta["n_avaliados"] == 10

    def test_background_task_exception_saves_abortado(self, tmp_path):
        from concilium.presentation.api.routes.campaign import run_campaign

        svc = _svc()
        storage = MagicMock(projects_root=tmp_path, config_root=tmp_path)
        campaign_file = tmp_path / "PROJ-1" / "campaigns" / "campaign_v1.json"
        campaign_file.parent.mkdir(parents=True)
        campaign_file.write_text("{}", encoding="utf-8")
        bg = BackgroundTasks()

        with (
            patch("concilium.infrastructure.settings.get_storage", return_value=storage),
            patch(
                "concilium.presentation.cli.commands_campaign._load_project_base_spec",
                return_value={"foo": "bar"},
            ),
            patch(
                "concilium.application.services.campaign.campaign_service.executar_campanha",
                side_effect=RuntimeError("boom"),
            ),
        ):
            result = run_campaign("proj-1", self._req(), bg, service=svc)
            bg.tasks[0].func()

        from concilium.infrastructure.storage.campaign_store import CampaignRunStore

        store = CampaignRunStore(tmp_path / "PROJ-1")
        meta = store.load_meta(result["run_id"])
        assert meta["status"] == "ABORTADO"
        assert meta["erro"] == "boom"
