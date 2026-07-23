"""Tests for campaign API routes and MCP tools — ADR-070."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

fastapi = pytest.importorskip("fastapi", reason="fastapi nao instalado - pule este modulo de teste")

try:
    from fastapi.testclient import TestClient

    from concilium.presentation.api.app import create_app
    from concilium.presentation.api.container import get_concilium_service
except TypeError as exc:
    pytest.skip(f"Ambiente FastAPI incompatível: {exc}", allow_module_level=True)


# ── Fake service ──────────────────────────────────────────────────────────────


class _FakeService:
    """Minimal ConciliumService stub for campaign route tests."""

    def __init__(self, project_id: str = "PROJ-TEST"):
        self._project_id = project_id

    def get_project(self, project_id: str) -> dict[str, Any]:
        if project_id.upper() != self._project_id.upper():
            raise FileNotFoundError(f"Projeto '{project_id}' não encontrado.")
        return {"id": project_id, "nome": "Projeto Teste"}


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def tmp_projects_root(tmp_path: Path) -> Path:
    root = tmp_path / "projetos"
    root.mkdir()
    return root


@pytest.fixture()
def project_dir(tmp_projects_root: Path) -> Path:
    """Create the project directory under projetos/PROJ-TEST."""
    d = tmp_projects_root / "PROJ-TEST"
    d.mkdir()
    return d


@pytest.fixture()
def campaign_store(project_dir: Path):
    """Return a CampaignRunStore rooted at project_dir."""
    from concilium.infrastructure.storage.campaign_store import CampaignRunStore

    return CampaignRunStore(project_dir)


@pytest.fixture(scope="module")
def _shared_app():
    """App FastAPI criado uma vez por módulo — ~1.5s poupado por teste."""
    from unittest.mock import patch as _patch

    with (
        _patch("concilium.presentation.api.app.setup_telemetry"),
        _patch("concilium.presentation.api.app.configure_logging"),
    ):
        app = create_app()
    return app


@pytest.fixture()
def client_factory(tmp_projects_root: Path, monkeypatch, _shared_app):
    """Factory que reutiliza a app module-scoped, trocando apenas service e storage por teste."""

    def _make(project_id: str = "PROJ-TEST") -> TestClient:
        from concilium.infrastructure import settings as _settings

        class _FakeStorage:
            root = tmp_projects_root.parent
            config_root = tmp_projects_root.parent
            projects_root = tmp_projects_root
            benchmark_projects_root = None

        monkeypatch.setattr(_settings, "get_storage", lambda: _FakeStorage())

        _shared_app.dependency_overrides[get_concilium_service] = lambda: _FakeService(project_id)
        return TestClient(_shared_app)

    return _make


# ── API: list runs ─────────────────────────────────────────────────────────────


class TestListCampaignRuns:
    def test_list_runs_empty(self, project_dir, client_factory):
        """GET /api/projects/{id}/campaign/runs returns [] when no runs exist."""
        client = client_factory()
        resp = client.get("/api/projects/PROJ-TEST/campaign/runs")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_runs_after_store_write(self, project_dir, campaign_store, client_factory):
        """After saving a run, it appears in the list."""
        run_id = campaign_store.new_run()
        campaign_store.save_meta(
            run_id,
            {
                "campaign_version": "v1",
                "status": "SUCESSO",
                "n_avaliados": 4,
                "n_viaveis": 2,
                "n_falhas": 0,
            },
        )

        client = client_factory()
        resp = client.get("/api/projects/PROJ-TEST/campaign/runs")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["run_id"] == run_id
        assert items[0]["status"] == "SUCESSO"
        assert items[0]["n_avaliados"] == 4
        assert items[0]["n_viaveis"] == 2

    def test_list_runs_project_not_found(self, client_factory):
        """Returns 404 when project does not exist."""
        client = client_factory()
        resp = client.get("/api/projects/NO-SUCH-PROJECT/campaign/runs")
        assert resp.status_code == 404

    def test_list_runs_most_recent_first(self, project_dir, campaign_store, client_factory):
        """Multiple runs are returned most-recent first (reversed order)."""
        for i, status in enumerate(["SUCESSO", "SUCESSO_PARCIAL", "ABORTADO"]):
            run_id = campaign_store.new_run()
            campaign_store.save_meta(run_id, {"status": status, "n_avaliados": i})

        client = client_factory()
        resp = client.get("/api/projects/PROJ-TEST/campaign/runs")
        assert resp.status_code == 200
        items = resp.json()
        # Most recent (run-003) is first
        assert items[0]["run_id"] == "run-003"
        assert items[-1]["run_id"] == "run-001"


# ── API: get run ───────────────────────────────────────────────────────────────


class TestGetCampaignRun:
    def test_get_run_not_found(self, project_dir, client_factory):
        """GET /api/projects/{id}/campaign/runs/{run_id} returns 404 for unknown run."""
        client = client_factory()
        resp = client.get("/api/projects/PROJ-TEST/campaign/runs/run-999")
        assert resp.status_code == 404

    def test_get_run_returns_bundle(self, project_dir, campaign_store, client_factory):
        """Returns bundle JSON after writing one."""
        run_id = campaign_store.new_run()
        bundle_data = {
            "campaign_id": "campaign-abc123",
            "campaign_version": "v1",
            "status": "SUCESSO",
            "n_cenarios_avaliados": 9,
            "n_cenarios_viaveis": 4,
            "shortlist": [],
            "cenarios": [],
        }
        campaign_store.save_bundle(run_id, bundle_data)
        campaign_store.save_meta(
            run_id,
            {"campaign_version": "v1", "status": "SUCESSO", "n_avaliados": 9, "n_viaveis": 4},
        )

        client = client_factory()
        resp = client.get(f"/api/projects/PROJ-TEST/campaign/runs/{run_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["run_id"] == run_id
        assert body["bundle"]["campaign_id"] == "campaign-abc123"
        assert body["meta"]["status"] == "SUCESSO"

    def test_get_run_still_running_no_bundle(self, project_dir, campaign_store, client_factory):
        """A run that has meta but no bundle yet returns bundle=None (RUNNING state)."""
        run_id = campaign_store.new_run()
        campaign_store.save_meta(
            run_id,
            {"campaign_version": "v1", "status": "RUNNING", "n_avaliados": 0},
        )

        client = client_factory()
        resp = client.get(f"/api/projects/PROJ-TEST/campaign/runs/{run_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["bundle"] is None
        assert body["meta"]["status"] == "RUNNING"


# ── API: get report ────────────────────────────────────────────────────────────


class TestGetCampaignRunReport:
    def test_get_report_json(self, project_dir, campaign_store, client_factory):
        """GET .../{run_id}/report?format=json returns the JSON report."""
        run_id = campaign_store.new_run()
        report = {"shortlist": [], "status": "SUCESSO"}
        md = "# Campaign Report\n\nNo items."
        campaign_store.save_report(run_id, report, md, pdf=None)

        client = client_factory()
        resp = client.get(f"/api/projects/PROJ-TEST/campaign/runs/{run_id}/report?format=json")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")
        body = resp.json()
        assert body["status"] == "SUCESSO"

    def test_get_report_md(self, project_dir, campaign_store, client_factory):
        """GET .../{run_id}/report?format=md returns the Markdown report."""
        run_id = campaign_store.new_run()
        report = {"status": "SUCESSO"}
        md = "# My Campaign\n\nHello."
        campaign_store.save_report(run_id, report, md, pdf=None)

        client = client_factory()
        resp = client.get(f"/api/projects/PROJ-TEST/campaign/runs/{run_id}/report?format=md")
        assert resp.status_code == 200
        assert "My Campaign" in resp.text

    def test_get_report_not_found_run(self, project_dir, client_factory):
        """Returns 404 for an unknown run."""
        client = client_factory()
        resp = client.get("/api/projects/PROJ-TEST/campaign/runs/run-999/report?format=json")
        assert resp.status_code == 404

    def test_get_report_invalid_format(self, project_dir, campaign_store, client_factory):
        """Returns 422 for an invalid format param."""
        run_id = campaign_store.new_run()
        client = client_factory()
        resp = client.get(f"/api/projects/PROJ-TEST/campaign/runs/{run_id}/report?format=xlsx")
        assert resp.status_code == 422


# ── MCP tools ─────────────────────────────────────────────────────────────────


class TestMcpCampaignTools:
    @pytest.fixture(scope="class")
    def _server(self):
        """FastMCP com campaign tools — criado uma vez por classe (~2s)."""
        from mcp.server.fastmcp import FastMCP

        from concilium.presentation.mcp.tools import campaign

        server = FastMCP("test-concilium")
        campaign.register(server)
        return server

    def _build_server(self):
        from mcp.server.fastmcp import FastMCP

        from concilium.presentation.mcp.tools import campaign

        server = FastMCP("test-concilium")
        campaign.register(server)
        return server

    def test_explorar_configuracoes_go_registered(self, _server):
        """explorar_configuracoes_go is registered in the server."""
        tools = _server._tool_manager._tools
        assert "explorar_configuracoes_go" in tools

    def test_listar_runs_campanha_registered(self, _server):
        """listar_runs_campanha is registered in the server."""
        server = _server
        tools = server._tool_manager._tools
        assert "listar_runs_campanha" in tools

    def test_obter_resultado_campanha_registered(self, _server):
        """obter_resultado_campanha is registered in the server."""
        tools = _server._tool_manager._tools
        assert "obter_resultado_campanha" in tools

    def test_listar_runs_campanha_empty(self, _server, tmp_path: Path, monkeypatch):
        """listar_runs_campanha returns [] for a project with no runs."""
        _projects_root = tmp_path / "projetos"
        (_projects_root / "PROJ-EMPTY").mkdir(parents=True)

        import concilium.infrastructure.settings as _settings

        def _fake_storage():
            class _S:
                root = tmp_path
                config_root = tmp_path
                projects_root = _projects_root
                benchmark_projects_root = None

            return _S()

        monkeypatch.setattr(_settings, "get_storage", _fake_storage)

        fn = _server._tool_manager._tools["listar_runs_campanha"].fn
        result = fn(project_id="PROJ-EMPTY")
        assert result == []

    def test_obter_resultado_campanha_no_runs(self, _server, tmp_path: Path, monkeypatch):
        """obter_resultado_campanha returns an error dict when no runs exist."""
        _projects_root = tmp_path / "projetos"
        (_projects_root / "PROJ-EMPTY").mkdir(parents=True)

        import concilium.infrastructure.settings as _settings

        def _fake_storage():
            class _S:
                root = tmp_path
                config_root = tmp_path
                projects_root = _projects_root
                benchmark_projects_root = None

            return _S()

        monkeypatch.setattr(_settings, "get_storage", _fake_storage)

        fn = _server._tool_manager._tools["obter_resultado_campanha"].fn
        result = fn(project_id="PROJ-EMPTY")
        assert "erro" in result
        assert "PROJ-EMPTY" in result["erro"] or "dica" in result

    def test_listar_runs_campanha_with_data(self, _server, tmp_path: Path, monkeypatch):
        """listar_runs_campanha returns the stored run metadata."""
        from concilium.infrastructure.storage.campaign_store import CampaignRunStore

        _projects_root = tmp_path / "projetos"
        project_dir = _projects_root / "PROJ-DATA"
        project_dir.mkdir(parents=True)

        store = CampaignRunStore(project_dir)
        run_id = store.new_run()
        store.save_meta(
            run_id,
            {
                "campaign_version": "v2",
                "status": "SUCESSO",
                "n_avaliados": 6,
                "n_viaveis": 3,
            },
        )

        import concilium.infrastructure.settings as _settings

        def _fake_storage():
            class _S:
                root = tmp_path
                config_root = tmp_path
                projects_root = _projects_root
                benchmark_projects_root = None

            return _S()

        monkeypatch.setattr(_settings, "get_storage", _fake_storage)

        fn = _server._tool_manager._tools["listar_runs_campanha"].fn
        result = fn(project_id="PROJ-DATA")
        assert len(result) == 1
        assert result[0]["run_id"] == run_id
        assert result[0]["status"] == "SUCESSO"
        assert result[0]["n_avaliados"] == 6

    def test_obter_resultado_campanha_with_bundle(self, _server, tmp_path: Path, monkeypatch):
        """obter_resultado_campanha returns shortlist summary when bundle exists."""
        from concilium.infrastructure.storage.campaign_store import CampaignRunStore

        _projects_root = tmp_path / "projetos"
        project_dir = _projects_root / "PROJ-BUNDLE"
        project_dir.mkdir(parents=True)

        store = CampaignRunStore(project_dir)
        run_id = store.new_run()
        bundle = {
            "campaign_id": "campaign-xyz",
            "status": "SUCESSO",
            "shortlist": [
                {
                    "rank": 1,
                    "cenario": {
                        "cenario_id": "c-001",
                        "viabilidade": "APROVADO",
                        "classificacao_O": "IDEAL",
                        "classificacao_EF": "DENTRO_EXPECTATIVA",
                        "pareto_intersecao": True,
                        "parametros_variados": {"dias_semana": 6},
                    },
                    "justificativa": {"motivo_inclusao": "Pareto O+EF"},
                }
            ],
            "cenarios": [],
        }
        store.save_bundle(run_id, bundle)
        store.save_meta(run_id, {"status": "SUCESSO", "n_avaliados": 3})

        import concilium.infrastructure.settings as _settings

        def _fake_storage():
            class _S:
                root = tmp_path
                config_root = tmp_path
                projects_root = _projects_root
                benchmark_projects_root = None

            return _S()

        monkeypatch.setattr(_settings, "get_storage", _fake_storage)

        fn = _server._tool_manager._tools["obter_resultado_campanha"].fn
        result = fn(project_id="PROJ-BUNDLE")
        assert result["run_id"] == run_id
        assert len(result["shortlist"]) == 1
        assert result["shortlist"][0]["rank"] == 1
        assert result["shortlist"][0]["viabilidade"] == "APROVADO"


class TestCampaignIntentEligibility:
    def test_api_run_campaign_rejects_rfi(self, client_factory):
        client = client_factory()
        resp = client.post(
            "/api/projects/PROJ-TEST/campaign/run",
            json={"procurement_intent": "rfi"},
        )
        assert resp.status_code == 422
        assert "RFP" in resp.json()["detail"]

    def test_mcp_explorar_rejects_rfi(self, tmp_path: Path, monkeypatch):
        _projects_root = tmp_path / "projetos"
        (_projects_root / "PROJ-EMPTY").mkdir(parents=True)

        import concilium.infrastructure.settings as _settings

        def _fake_storage():
            class _S:
                root = tmp_path
                config_root = tmp_path
                projects_root = _projects_root
                benchmark_projects_root = None

            return _S()

        monkeypatch.setattr(_settings, "get_storage", _fake_storage)

        server = TestMcpCampaignTools()._build_server()
        fn = server._tool_manager._tools["explorar_configuracoes_go"].fn
        result = fn(project_id="PROJ-EMPTY", parametros_sweep=[], procurement_intent="rfi")
        assert "erro" in result
        assert "RFP" in result["erro"]
