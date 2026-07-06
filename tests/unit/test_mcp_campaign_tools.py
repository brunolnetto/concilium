"""Tests for MCP campaign tools coverage."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

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


class _RaisingOnSecondGetDict(dict):
    """Dict cujo .get() para uma chave específica funciona normalmente na 1a
    chamada (usada por ToolManager.add_tool ao registrar a tool) mas levanta
    na 2a chamada (usada pelo loop de _ui_metas em register())."""

    def __init__(self, *a, raise_for_key: str, **kw):
        super().__init__(*a, **kw)
        self._raise_for_key = raise_for_key
        self._get_count = 0

    def get(self, key, default=None):
        if key == self._raise_for_key:
            self._get_count += 1
            if self._get_count >= 2:
                raise RuntimeError("boom")
        return super().get(key, default)


class TestRegisterUiMetaExceptionSwallowed:
    def test_register_swallows_exception_when_tool_manager_lookup_fails(self):
        """Lines 306-307: falha ao acessar server._tool_manager._tools é engolida silenciosamente."""
        import importlib

        mod = importlib.import_module(_CAMPAIGN_MOD)

        server = FastMCP("test-campaign-broken")
        server._tool_manager._tools = _RaisingOnSecondGetDict(raise_for_key="explorar_configuracoes_go")

        # Não deve levantar exceção mesmo com o 2o lookup de _tools.get() falhando.
        mod.register(server)

    def test_register_skips_meta_assignment_when_tool_not_found(self):
        """Line 301->304: quando `_tools.get(tool_name)` retorna None (ferramenta
        não encontrada), o `if tool is not None` é falso e o loop segue sem
        atribuir `.meta`, sem levantar exceção."""
        import importlib

        class _AlwaysNoneForKeyDict(dict):
            """dict normal, exceto que .get() para uma chave específica
            sempre retorna None (mesmo que a chave exista de fato)."""

            def __init__(self, *a, none_for_key: str, **kw):
                super().__init__(*a, **kw)
                self._none_for_key = none_for_key

            def get(self, key, default=None):
                if key == self._none_for_key:
                    return None
                return super().get(key, default)

        mod = importlib.import_module(_CAMPAIGN_MOD)

        server = FastMCP("test-campaign-missing-tool")
        server._tool_manager._tools = _AlwaysNoneForKeyDict(none_for_key="explorar_configuracoes_go")

        # Não deve levantar, mesmo com o lookup de `_ui_metas` retornando None.
        mod.register(server)


class TestExplorarConfiguracoesGo:
    def test_explorar_project_not_found_returns_erro(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)

        storage_mock = MagicMock()
        storage_mock.projects_root = tmp_path / "projetos"
        storage_mock.config_root = tmp_path / "config"

        with (
            patch("concilium.infrastructure.settings.get_storage", return_value=storage_mock),
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
            patch(
                "concilium.application.services.campaign.campaign_service.executar_campanha",
                return_value=campaign_result,
            ),
            patch("concilium.application.services.campaign.campaign_service.construir_cubo", return_value={}),
            patch(
                "concilium.application.services.campaign.campaign_report.serialize_campaign_report",
                return_value={"cubo": {}},
            ),
            patch(
                "concilium.application.services.campaign.campaign_report.render_campaign_report_md",
                return_value="# report",
            ),
            patch(
                "concilium.application.services.campaign.campaign_report.render_campaign_report_pdf", return_value=b""
            ),
            patch("concilium.infrastructure.storage.campaign_store.CampaignRunStore", return_value=store_mock),
        ):
            result = tools["explorar_configuracoes_go"](
                project_id="PROJ",
                parametros_sweep=[{"campo": "dias_semana", "valores": [5, 6]}],
            )
        assert result.get("run_id") == "run-001"
        assert result.get("status") == "OK"

    def test_explorar_happy_path_with_non_empty_shortlist(self, monkeypatch, tmp_path):
        """Lines 148-150: shortlist não vazio → itens são serializados no loop."""
        tools = _register_tools(monkeypatch, tmp_path)

        storage_mock = MagicMock()
        storage_mock.projects_root = tmp_path / "projetos"
        storage_mock.config_root = tmp_path / "config"

        base_spec = MagicMock()

        rank_item = MagicMock()
        rank_item.rank = 1
        rank_item.cenario.cenario_id = "c1"
        rank_item.cenario.viabilidade = "APROVADO"
        rank_item.cenario.classificacao_O = "BOM"
        rank_item.cenario.classificacao_EF = "BOM"
        rank_item.cenario.pareto_intersecao = True
        rank_item.cenario.parametros_variados = {"a": 1}
        rank_item.justificativa.motivo_inclusao = "melhor margem"
        rank_item.justificativa.destaques_EF = ["ef1"]
        rank_item.justificativa.destaques_O = ["o1"]
        rank_item.justificativa.alertas = []

        campaign_result = MagicMock()
        campaign_result.campaign_version = "v1"
        campaign_result.status = "OK"
        campaign_result.n_cenarios_avaliados = 4
        campaign_result.n_cenarios_viaveis = 2
        campaign_result.n_falhas = 0
        campaign_result.shortlist = [rank_item]

        store_mock = MagicMock()
        store_mock.new_run.return_value = "run-002"

        with (
            patch("concilium.infrastructure.settings.get_storage", return_value=storage_mock),
            patch("concilium.presentation.cli.commands_campaign._load_project_base_spec", return_value=base_spec),
            patch(
                "concilium.application.services.campaign.campaign_service.executar_campanha",
                return_value=campaign_result,
            ),
            patch("concilium.application.services.campaign.campaign_service.construir_cubo", return_value={}),
            patch(
                "concilium.application.services.campaign.campaign_report.serialize_campaign_report",
                return_value={"cubo": {}},
            ),
            patch(
                "concilium.application.services.campaign.campaign_report.render_campaign_report_md",
                return_value="# report",
            ),
            patch(
                "concilium.application.services.campaign.campaign_report.render_campaign_report_pdf", return_value=b""
            ),
            patch("concilium.infrastructure.storage.campaign_store.CampaignRunStore", return_value=store_mock),
        ):
            result = tools["explorar_configuracoes_go"](
                project_id="PROJ",
                parametros_sweep=[{"campo": "dias_semana", "valores": [5, 6]}],
            )
        assert result.get("run_id") == "run-002"
        assert len(result["shortlist"]) == 1
        assert result["shortlist"][0]["cenario_id"] == "c1"
        assert result["shortlist"][0]["motivo_inclusao"] == "melhor margem"


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
