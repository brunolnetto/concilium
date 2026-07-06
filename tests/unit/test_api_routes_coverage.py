"""Tests for API route handlers to boost coverage."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

# ─── Mobilization routes ────────────────────────────────────────────────────


class TestMobilizationRoutes:
    def _svc(self):
        return MagicMock()

    def test_get_mobilizacao_policies_happy(self):
        from concilium.presentation.api.routes.mobilization import get_mobilizacao_policies

        svc = self._svc()
        svc.get_mobilizacao_policies.return_value = [{"item_id": "act-1"}]
        result = get_mobilizacao_policies("proj-1", service=svc)
        assert result["items"] == [{"item_id": "act-1"}]

    def test_get_mobilizacao_policies_not_found(self):
        from concilium.presentation.api.routes.mobilization import get_mobilizacao_policies

        svc = self._svc()
        svc.get_mobilizacao_policies.side_effect = FileNotFoundError("not found")
        with pytest.raises(HTTPException) as exc:
            get_mobilizacao_policies("proj-1", service=svc)
        assert exc.value.status_code == 404

    def test_upsert_mobilizacao_policy_ok(self):
        from concilium.presentation.api.routes.mobilization import upsert_mobilizacao_policy

        svc = self._svc()
        req = MagicMock()
        req.item_id = "act-1"
        req.policy.model_dump.return_value = {}
        result = upsert_mobilizacao_policy("proj-1", req, x_user="eng", service=svc)
        assert result["status"] == "ok"
        assert result["item_id"] == "act-1"

    def test_upsert_mobilizacao_policy_error(self):
        from concilium.presentation.api.routes.mobilization import upsert_mobilizacao_policy

        svc = self._svc()
        svc.upsert_mobilizacao_policy.side_effect = ValueError("bad policy")
        req = MagicMock()
        req.item_id = "act-1"
        req.policy.model_dump.return_value = {}
        with pytest.raises(HTTPException) as exc:
            upsert_mobilizacao_policy("proj-1", req, x_user="eng", service=svc)
        assert exc.value.status_code == 400

    def test_delete_mobilizacao_policy_ok(self):
        from concilium.presentation.api.routes.mobilization import delete_mobilizacao_policy

        svc = self._svc()
        result = delete_mobilizacao_policy("proj-1", "act-1", x_user="eng", service=svc)
        assert result["status"] == "ok"
        assert result["item_id"] == "act-1"

    def test_delete_mobilizacao_policy_not_found(self):
        from concilium.presentation.api.routes.mobilization import delete_mobilizacao_policy

        svc = self._svc()
        svc.delete_mobilizacao_policy.side_effect = FileNotFoundError("not found")
        with pytest.raises(HTTPException) as exc:
            delete_mobilizacao_policy("proj-1", "act-1", x_user="eng", service=svc)
        assert exc.value.status_code == 404

    def test_validate_mobilizacao_policies_ok(self):
        from concilium.presentation.api.routes.mobilization import validate_mobilizacao_policies

        svc = self._svc()
        svc.validate_mobilizacao_policies.return_value = [{"status": "OK"}]
        result = validate_mobilizacao_policies("proj-1", service=svc)
        assert result["status"] == "OK"

    def test_validate_mobilizacao_policies_error_status(self):
        from concilium.presentation.api.routes.mobilization import validate_mobilizacao_policies

        svc = self._svc()
        svc.validate_mobilizacao_policies.return_value = [{"status": "ERRO"}]
        result = validate_mobilizacao_policies("proj-1", service=svc)
        assert result["status"] == "ERRO"

    def test_validate_mobilizacao_policies_warning_status(self):
        from concilium.presentation.api.routes.mobilization import validate_mobilizacao_policies

        svc = self._svc()
        svc.validate_mobilizacao_policies.return_value = [{"status": "AVISO"}]
        result = validate_mobilizacao_policies("proj-1", service=svc)
        assert result["status"] == "AVISO"

    def test_validate_not_found(self):
        from concilium.presentation.api.routes.mobilization import validate_mobilizacao_policies

        svc = self._svc()
        svc.validate_mobilizacao_policies.side_effect = FileNotFoundError("not found")
        with pytest.raises(HTTPException) as exc:
            validate_mobilizacao_policies("proj-1", service=svc)
        assert exc.value.status_code == 404

    def test_simulate_mobilizacao_policy_ok(self):
        from concilium.presentation.api.routes.mobilization import simulate_mobilizacao_policy

        svc = self._svc()
        svc.simulate_mobilizacao_policy.return_value = {"weeks": 10}
        req = MagicMock()
        req.model_dump.return_value = {}
        result = simulate_mobilizacao_policy("proj-1", req, service=svc)
        assert result["weeks"] == 10

    def test_simulate_value_error(self):
        from concilium.presentation.api.routes.mobilization import simulate_mobilizacao_policy

        svc = self._svc()
        svc.simulate_mobilizacao_policy.side_effect = ValueError("bad")
        req = MagicMock()
        req.model_dump.return_value = {}
        with pytest.raises(HTTPException) as exc:
            simulate_mobilizacao_policy("proj-1", req, service=svc)
        assert exc.value.status_code == 422

    def test_simulate_not_found(self):
        from concilium.presentation.api.routes.mobilization import simulate_mobilizacao_policy

        svc = self._svc()
        svc.simulate_mobilizacao_policy.side_effect = FileNotFoundError("no project")
        req = MagicMock()
        req.model_dump.return_value = {}
        with pytest.raises(HTTPException) as exc:
            simulate_mobilizacao_policy("proj-1", req, service=svc)
        assert exc.value.status_code == 404

    def test_get_deliverables_config(self):
        from concilium.presentation.api.routes.mobilization import get_deliverables_config

        svc = self._svc()
        svc.get_deliverables_config.return_value = {"pdf": True}
        result = get_deliverables_config("proj-1", service=svc)
        assert result["pdf"] is True

    def test_get_deliverables_config_not_found(self):
        from concilium.presentation.api.routes.mobilization import get_deliverables_config

        svc = self._svc()
        svc.get_deliverables_config.side_effect = FileNotFoundError("nope")
        with pytest.raises(HTTPException) as exc:
            get_deliverables_config("proj-1", service=svc)
        assert exc.value.status_code == 404

    def test_put_deliverables_config(self):
        from concilium.presentation.api.routes.mobilization import put_deliverables_config

        svc = self._svc()
        svc.put_deliverables_config.return_value = {"pdf": False}
        req = MagicMock()
        req.model_dump.return_value = {}
        result = put_deliverables_config("proj-1", req, x_user="eng", service=svc)
        assert result["pdf"] is False

    def test_put_deliverables_config_error(self):
        from concilium.presentation.api.routes.mobilization import put_deliverables_config

        svc = self._svc()
        svc.put_deliverables_config.side_effect = ValueError("bad")
        req = MagicMock()
        req.model_dump.return_value = {}
        with pytest.raises(HTTPException) as exc:
            put_deliverables_config("proj-1", req, x_user="eng", service=svc)
        assert exc.value.status_code == 400


# ─── Benchmark routes ────────────────────────────────────────────────────────


class TestBenchmarkRoutes:
    def _svc(self):
        return MagicMock()

    def test_list_benchmarks(self):
        from concilium.presentation.api.routes.benchmarks import list_benchmarks

        svc = self._svc()
        svc.list_benchmarks.return_value = [{"slug": "AGIS"}]
        result = list_benchmarks(service=svc)
        assert result["items"][0]["slug"] == "AGIS"

    def test_list_project_benchmarks_with_slug(self):
        from concilium.presentation.api.routes.benchmarks import list_project_benchmarks

        svc = self._svc()
        svc.get_project.return_value = {"benchmark_slug": "AGIS"}
        result = list_project_benchmarks("proj-1", service=svc)
        assert "AGIS" in result["items"]

    def test_list_project_benchmarks_no_slug(self):
        from concilium.presentation.api.routes.benchmarks import list_project_benchmarks

        svc = self._svc()
        svc.get_project.return_value = {}
        result = list_project_benchmarks("proj-1", service=svc)
        assert result["items"] == []

    def test_list_project_benchmarks_not_found(self):
        from concilium.presentation.api.routes.benchmarks import list_project_benchmarks

        svc = self._svc()
        svc.get_project.side_effect = FileNotFoundError("not found")
        with pytest.raises(HTTPException) as exc:
            list_project_benchmarks("proj-1", service=svc)
        assert exc.value.status_code == 404

    def test_trigger_project_pack_benchmark_queues(self):
        from fastapi import BackgroundTasks

        from concilium.presentation.api.routes.benchmarks import trigger_project_pack_benchmark

        svc = self._svc()
        svc.config_root = MagicMock()
        bg = BackgroundTasks()
        result = trigger_project_pack_benchmark("proj-1", "AGIS", bg, charts=True, service=svc)
        assert result["status"] == "queued"
        assert result["slug"] == "AGIS"
        assert "download" in result

    def test_download_project_benchmark_not_found(self):
        from concilium.presentation.api.routes.benchmarks import download_project_benchmark_zip

        svc = self._svc()
        svc.config_root = MagicMock()
        with patch(
            "concilium.application.benchmarks.charts.output_packager.empacotar_outputs",
            side_effect=FileNotFoundError("no zip"),
        ):
            with pytest.raises(HTTPException) as exc:
                download_project_benchmark_zip("proj-1", "AGIS", charts=True, cenarios=False, service=svc)
        assert exc.value.status_code == 404

    def test_download_project_benchmark_success(self):
        from pathlib import Path

        from concilium.presentation.api.routes.benchmarks import download_project_benchmark_zip

        svc = self._svc()
        svc.config_root = MagicMock()
        fake_zip = Path("/tmp/benchmark_AGIS_20260101.zip")
        with patch(
            "concilium.application.benchmarks.charts.output_packager.empacotar_outputs",
            return_value=fake_zip,
        ):
            with patch(
                "concilium.presentation.api.routes.benchmarks.FileResponse",
                side_effect=lambda **kwargs: kwargs,
            ):
                result = download_project_benchmark_zip("proj-1", "agis", charts=True, cenarios=False, service=svc)
        assert result["filename"] == "benchmark_AGIS_20260101.zip"

    def test_trigger_project_pack_benchmark_background_success(self):
        from fastapi import BackgroundTasks

        from concilium.presentation.api.routes.benchmarks import trigger_project_pack_benchmark

        svc = self._svc()
        svc.config_root = MagicMock()
        bg = BackgroundTasks()
        with patch(
            "concilium.application.benchmarks.charts.output_packager.empacotar_outputs",
        ) as mock_pack:
            trigger_project_pack_benchmark("proj-1", "AGIS", bg, charts=True, service=svc)
            assert len(bg.tasks) == 1
            bg.tasks[0].func()
            mock_pack.assert_called_once()

    def test_trigger_project_pack_benchmark_background_swallows_exception(self):
        from fastapi import BackgroundTasks

        from concilium.presentation.api.routes.benchmarks import trigger_project_pack_benchmark

        svc = self._svc()
        svc.config_root = MagicMock()
        bg = BackgroundTasks()
        with patch(
            "concilium.application.benchmarks.charts.output_packager.empacotar_outputs",
            side_effect=RuntimeError("boom"),
        ):
            trigger_project_pack_benchmark("proj-1", "AGIS", bg, charts=True, service=svc)
            # Should not raise even though empacotar_outputs fails.
            bg.tasks[0].func()

    def test_download_project_benchmark_server_error(self):
        from concilium.presentation.api.routes.benchmarks import download_project_benchmark_zip

        svc = self._svc()
        svc.config_root = MagicMock()
        with patch(
            "concilium.application.benchmarks.charts.output_packager.empacotar_outputs",
            side_effect=RuntimeError("pack failed"),
        ):
            with pytest.raises(HTTPException) as exc:
                download_project_benchmark_zip("proj-1", "AGIS", charts=True, cenarios=False, service=svc)
        assert exc.value.status_code == 500
