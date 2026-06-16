"""Tests for MCP campaign tools coverage."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP


_CAMPAIGN_MOD = "concilium.presentation.mcp.tools.campaign"


def _register_tools(monkeypatch, tmp_path: Path) -> dict:
    import importlib
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CONCILIUM__CONFIG_ROOT", str(config_dir))
    monkeypatch.setenv("CONCILIUM__PROJECTS_ROOT", str(tmp_path / "projetos"))

    mod = importlib.import_module(_CAMPAIGN_MOD)
    server = FastMCP("test-campaign")
    mod.register(server)

    tools: dict = {}
    for t in server._tool_manager.list_tools():
        fn = getattr(t, "fn", None) or getattr(t, "func", None)
        tools[t.name] = fn
    return tools


class TestExplorarConfiguracoesGo:
    def test_explorar_project_not_found_returns_erro(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)

        storage_mock = MagicMock()
        storage_mock.projects_root = tmp_path / "projetos"
        storage_mock.config_root = tmp_path / "config"

        with (
            patch(f"concilium.infrastructure.settings.get_storage", return_value=storage_mock),
            patch(
                "concilium.presentation.cli.commands_campaign._load_project_base_spec",
                return_value=None,
            ),
        ):
            result = tools["explorar_configuracoes_go"](
                project_id="MISSING",
                parametros_sweep=[{"campo": "a", "valores": [1, 2]}],
            )
        assert "erro" in result

    def test_explorar_exception_returns_erro(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)

        storage_mock = MagicMock()
        storage_mock.projects_root = None
        storage_mock.config_root = tmp_path / "config"

        with (
            patch("concilium.infrastructure.settings.get_storage", return_value=storage_mock),
            patch(
                "concilium.presentation.cli.shared._tools_root",
                side_effect=RuntimeError("env not set"),
            ),
        ):
            result = tools["explorar_configuracoes_go"](
                project_id="PROJ",
                parametros_sweep=[],
            )
        assert "erro" in result

    def test_explorar_happy_path(self, monkeypatch, tmp_path):
        # Imports inside the function body are patched at their source modules
        tools = _register_tools(monkeypatch, tmp_path)

        storage_mock = MagicMock()
        storage_mock.projects_root = tmp_path / "projetos"
        storage_mock.config_root = tmp_path / "config"

        base_spec = MagicMock()

        campaign_result = MagicMock()
        campaign_result.campaign_version = "v1"
        campaign_result.status = "OK"
        campaign_result.n_cenarios_avaliados = 4
        campaign_result.n_cenarios_viaveis = 2
        campaign_result.n_falhas = 0
        campaign_result.shortlist = []

        store_mock = MagicMock()
        store_mock.new_run.return_value = "run-001"

        with (
            patch("concilium.infrastructure.settings.get_storage", return_value=storage_mock),
            patch("concilium.presentation.cli.commands_campaign._load_project_base_spec", return_value=base_spec),
            patch("concilium.application.services.campaign.campaign_service.executar_campanha", return_value=campaign_result),
            patch("concilium.application.services.campaign.campaign_service.construir_cubo", return_value={}),
            patch("concilium.application.services.campaign.campaign_report.serialize_campaign_report", return_value={"cubo": {}}),
            patch("concilium.application.services.campaign.campaign_report.render_campaign_report_md", return_value="# report"),
            patch("concilium.application.services.campaign.campaign_report.render_campaign_report_pdf", return_value=b""),
            patch("concilium.infrastructure.storage.campaign_store.CampaignRunStore", return_value=store_mock),
        ):
            result = tools["explorar_configuracoes_go"](
                project_id="PROJ",
                parametros_sweep=[{"campo": "dias_semana", "valores": [5, 6]}],
            )
        assert result.get("run_id") == "run-001"
        assert result.get("status") == "OK"


class TestListarRunsCampanha:
    def test_listar_runs_happy(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)

        storage_mock = MagicMock()
        storage_mock.projects_root = tmp_path / "projetos"

        store_mock = MagicMock()
        store_mock.list_runs.return_value = ["run-001", "run-002"]
        store_mock.load_meta.side_effect = lambda r: {"status": "OK", "n_avaliados": 4}

        with (
            patch("concilium.infrastructure.settings.get_storage", return_value=storage_mock),
            patch("concilium.infrastructure.storage.campaign_store.CampaignRunStore", return_value=store_mock),
        ):
            result = tools["listar_runs_campanha"](project_id="PROJ")
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["run_id"] == "run-002"  # reversed

    def test_listar_runs_empty(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)

        storage_mock = MagicMock()
        storage_mock.projects_root = tmp_path / "projetos"
        store_mock = MagicMock()
        store_mock.list_runs.return_value = []

        with (
            patch("concilium.infrastructure.settings.get_storage", return_value=storage_mock),
            patch("concilium.infrastructure.storage.campaign_store.CampaignRunStore", return_value=store_mock),
        ):
            result = tools["listar_runs_campanha"](project_id="PROJ")
        assert result == []

    def test_listar_runs_exception_returns_erro(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        storage_mock = MagicMock()
        storage_mock.projects_root = None
        with (
            patch("concilium.infrastructure.settings.get_storage", return_value=storage_mock),
            patch("concilium.presentation.cli.shared._tools_root", side_effect=RuntimeError("env")),
        ):
            result = tools["listar_runs_campanha"](project_id="PROJ")
        assert any("erro" in item for item in result)


class TestObterResultadoCampanha:
    def test_no_runs_returns_erro(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)

        storage_mock = MagicMock()
        storage_mock.projects_root = tmp_path / "projetos"
        store_mock = MagicMock()
        store_mock.current_run.return_value = None

        with (
            patch("concilium.infrastructure.settings.get_storage", return_value=storage_mock),
            patch("concilium.infrastructure.storage.campaign_store.CampaignRunStore", return_value=store_mock),
        ):
            result = tools["obter_resultado_campanha"](project_id="PROJ")
        assert "erro" in result

    def test_run_not_found_returns_erro(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)

        storage_mock = MagicMock()
        storage_mock.projects_root = tmp_path / "projetos"
        store_mock = MagicMock()
        store_mock.current_run.return_value = "run-001"
        store_mock.list_runs.return_value = []  # run-001 not in list

        with (
            patch("concilium.infrastructure.settings.get_storage", return_value=storage_mock),
            patch("concilium.infrastructure.storage.campaign_store.CampaignRunStore", return_value=store_mock),
        ):
            result = tools["obter_resultado_campanha"](project_id="PROJ", run_id="run-001")
        assert "erro" in result

    def test_bundle_none_returns_aviso(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)

        storage_mock = MagicMock()
        storage_mock.projects_root = tmp_path / "projetos"
        store_mock = MagicMock()
        store_mock.current_run.return_value = "run-001"
        store_mock.list_runs.return_value = ["run-001"]
        store_mock.load_meta.return_value = {"status": "OK"}
        store_mock.load_bundle.return_value = None

        with (
            patch("concilium.infrastructure.settings.get_storage", return_value=storage_mock),
            patch("concilium.infrastructure.storage.campaign_store.CampaignRunStore", return_value=store_mock),
        ):
            result = tools["obter_resultado_campanha"](project_id="PROJ")
        assert "aviso" in result

    def test_happy_path_with_bundle(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)

        storage_mock = MagicMock()
        storage_mock.projects_root = tmp_path / "projetos"
        store_mock = MagicMock()
        store_mock.current_run.return_value = "run-001"
        store_mock.list_runs.return_value = ["run-001"]
        store_mock.load_meta.return_value = {"status": "OK", "n_avaliados": 4}
        store_mock.load_bundle.return_value = {
            "shortlist": [{"rank": 1, "cenario": {"cenario_id": "c1", "viabilidade": "VIAVEL"}}],
            "cenarios": [{}],
        }

        with (
            patch("concilium.infrastructure.settings.get_storage", return_value=storage_mock),
            patch("concilium.infrastructure.storage.campaign_store.CampaignRunStore", return_value=store_mock),
        ):
            result = tools["obter_resultado_campanha"](project_id="PROJ")
        assert result["run_id"] == "run-001"
        assert result["n_cenarios"] == 1
        assert len(result["shortlist"]) == 1

    def test_exception_returns_erro(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        storage_mock = MagicMock()
        storage_mock.projects_root = None
        with (
            patch("concilium.infrastructure.settings.get_storage", return_value=storage_mock),
            patch("concilium.presentation.cli.shared._tools_root", side_effect=RuntimeError("env")),
        ):
            result = tools["obter_resultado_campanha"](project_id="PROJ")
        assert "erro" in result
