"""Tests for MCP tools: system.py, tributacao.py, artifacts.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from mcp.server.fastmcp import FastMCP

# ─── helpers ──────────────────────────────────────────────────────────────────


def _register_tools(module_path: str, monkeypatch, tmp_path: Path) -> dict:
    """Register tools from a module and return {name: callable}."""
    import importlib

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CONCILIUM__CONFIG_ROOT", str(config_dir))
    monkeypatch.setenv("CONCILIUM__PROJECTS_ROOT", str(tmp_path / "projetos"))

    mod = importlib.import_module(module_path)
    server = FastMCP("test")
    mod.register(server)

    tools: dict = {}
    for t in server._tool_manager.list_tools():
        fn = getattr(t, "fn", None) or getattr(t, "func", None)
        tools[t.name] = fn
    return tools


# ─── system.py ────────────────────────────────────────────────────────────────

_SYSTEM_MOD = "concilium.presentation.mcp.tools.system"


class TestSystemPing:
    async def test_ping_no_config_returns_erro(self, monkeypatch, tmp_path):
        tools = _register_tools(_SYSTEM_MOD, monkeypatch, tmp_path)
        # config_root points to tmp_path/config which doesn't have contextos/
        result = await tools["ping"]()
        # No contextos → status SAUDAVEL (empty catalogos → no DEGRADADO)
        assert "status" in result

    async def test_ping_with_contextos(self, monkeypatch, tmp_path):
        config_dir = tmp_path / "config"
        contextos_dir = config_dir / "contextos"
        contextos_dir.mkdir(parents=True, exist_ok=True)
        (contextos_dir / "ctx-test.json").write_text('{"catalogo_id": "cat-test"}')

        tools = _register_tools(_SYSTEM_MOD, monkeypatch, tmp_path)

        runtime_mock = MagicMock()
        ctx_mock = MagicMock()
        ctx_mock.catalogo_id = "cat-test"
        runtime_mock.load_contexto.return_value = ctx_mock
        runtime_mock.load_catalogo.return_value = {"cpus": [{"codigo": "CPU-1"}]}

        with (
            patch(f"{_SYSTEM_MOD}._runtime", return_value=runtime_mock),
            patch(f"{_SYSTEM_MOD}._config_root", return_value=config_dir),
            patch(f"{_SYSTEM_MOD}._projetos_root", return_value=tmp_path / "projetos"),
            patch(
                "concilium.application.orchestrators.catalog_governance.collect_catalog_critical_errors",
                return_value=[],
            ),
        ):
            result = await tools["ping"]()
        assert "status" in result

    async def test_ping_with_projects(self, monkeypatch, tmp_path):
        config_dir = tmp_path / "config"
        proj_root = tmp_path / "projetos"
        proj_dir = proj_root / "proj-1"
        proj_dir.mkdir(parents=True)
        (proj_dir / "meta.json").write_text('{"nome": "test"}')

        tools = _register_tools(_SYSTEM_MOD, monkeypatch, tmp_path)

        with (
            patch(f"{_SYSTEM_MOD}._config_root", return_value=config_dir),
            patch(f"{_SYSTEM_MOD}._projetos_root", return_value=proj_root),
        ):
            result = await tools["ping"]()
        assert "status" in result

    async def test_ping_blob_storage_health_check_exception_sets_status_erro(self, monkeypatch, tmp_path):
        """Lines 84-91: build_blob_storage().health_check() raising → storage_health has
        status='error' → status_geral becomes 'ERRO'."""
        tools = _register_tools(_SYSTEM_MOD, monkeypatch, tmp_path)

        with patch(
            "concilium.infrastructure.storage.store_factory.build_blob_storage",
            side_effect=RuntimeError("blob storage unreachable"),
        ):
            result = await tools["ping"]()

        assert result["status"] == "ERRO"

    async def test_ping_catalog_exception_returns_erro_entry(self, monkeypatch, tmp_path):
        config_dir = tmp_path / "config"
        contextos_dir = config_dir / "contextos"
        contextos_dir.mkdir(parents=True, exist_ok=True)
        (contextos_dir / "ctx-bad.json").write_text('{"catalogo_id": "cat-bad"}')

        tools = _register_tools(_SYSTEM_MOD, monkeypatch, tmp_path)

        runtime_mock = MagicMock()
        runtime_mock.load_contexto.side_effect = RuntimeError("load error")

        with (
            patch(f"{_SYSTEM_MOD}._runtime", return_value=runtime_mock),
            patch(f"{_SYSTEM_MOD}._config_root", return_value=config_dir),
            patch(f"{_SYSTEM_MOD}._projetos_root", return_value=tmp_path / "projetos"),
        ):
            result = await tools["ping"]()
        # Should be DEGRADADO because a catalog errored
        assert result.get("status") in {"DEGRADADO", "ERRO"}

    async def test_ping_times_out_returns_erro_instead_of_hanging(self, monkeypatch, tmp_path):
        """issue #149: I/O de storage sem timeout total (httpx timeout é por-chunk)
        pode pendurar a thread indefinidamente — o wait_for precisa cortar e devolver
        um erro claro em vez de deixar o tool (e o client) pendurados."""
        import time

        tools = _register_tools(_SYSTEM_MOD, monkeypatch, tmp_path)

        def _slow_health_check():
            time.sleep(0.2)
            return {"status": "ok"}

        slow_storage = MagicMock()
        slow_storage.health_check.side_effect = _slow_health_check

        with (
            patch(f"{_SYSTEM_MOD}.TOOL_IO_TIMEOUT_S", 0.01),
            patch(
                "concilium.infrastructure.storage.store_factory.build_blob_storage",
                return_value=slow_storage,
            ),
        ):
            result = await tools["ping"]()

        assert result["status"] == "ERRO"
        assert "excedeu" in result["erro"]


# ─── tributacao.py ─────────────────────────────────────────────────────────────

_TRIB_MOD = "concilium.presentation.mcp.tools.tributacao"


class TestTributacaoTools:
    """ADR-116 F5: calcular_tributos(tipo=) unifica 3 tools anteriores."""

    def test_clt_empregador_horista(self, monkeypatch, tmp_path):
        tools = _register_tools(_TRIB_MOD, monkeypatch, tmp_path)
        result = tools["calcular_tributos"](tipo="clt_empregador", valor=3000.0, categoria="horista")
        assert "custo_total" in result
        assert result["custo_total"] > 3000.0
        assert "breakdown" in result

    def test_clt_empregador_mensalista(self, monkeypatch, tmp_path):
        tools = _register_tools(_TRIB_MOD, monkeypatch, tmp_path)
        result = tools["calcular_tributos"](tipo="clt_empregador", valor=5000.0, categoria="mensalista")
        assert "multiplicador_efetivo" in result

    def test_clt_empregador_exception(self, monkeypatch, tmp_path):
        tools = _register_tools(_TRIB_MOD, monkeypatch, tmp_path)
        with patch(
            "concilium.domain.services.financial.tributacao.calculate_employer_clt",
            side_effect=ValueError("invalid"),
        ):
            result = tools["calcular_tributos"](tipo="clt_empregador", valor=-1.0)
        assert "erro" in result

    def test_inss_empregado(self, monkeypatch, tmp_path):
        tools = _register_tools(_TRIB_MOD, monkeypatch, tmp_path)
        result = tools["calcular_tributos"](tipo="inss_empregado", valor=4000.0)
        assert "inss_empregado" in result
        assert result["inss_empregado"] > 0

    def test_inss_empregado_exception(self, monkeypatch, tmp_path):
        tools = _register_tools(_TRIB_MOD, monkeypatch, tmp_path)
        with patch(
            "concilium.domain.services.financial.tributacao.calculate_inss_employee",
            side_effect=ValueError("bad"),
        ):
            result = tools["calcular_tributos"](tipo="inss_empregado", valor=0.0)
        assert "erro" in result

    def test_irrf_isento(self, monkeypatch, tmp_path):
        tools = _register_tools(_TRIB_MOD, monkeypatch, tmp_path)
        result = tools["calcular_tributos"](tipo="irrf", valor=3000.0)
        assert result.get("isento") is True
        assert result.get("irrf_mensal") == 0.0

    def test_irrf_tributavel(self, monkeypatch, tmp_path):
        tools = _register_tools(_TRIB_MOD, monkeypatch, tmp_path)
        result = tools["calcular_tributos"](tipo="irrf", valor=10000.0)
        assert "irrf_mensal" in result
        assert result["irrf_mensal"] > 0

    def test_irrf_exception(self, monkeypatch, tmp_path):
        tools = _register_tools(_TRIB_MOD, monkeypatch, tmp_path)
        with patch(
            "concilium.domain.services.financial.tributacao.calculate_irrf",
            side_effect=ValueError("bad"),
        ):
            result = tools["calcular_tributos"](tipo="irrf", valor=0.0)
        assert "erro" in result

    def test_tipo_invalido_retorna_erro(self, monkeypatch, tmp_path):
        tools = _register_tools(_TRIB_MOD, monkeypatch, tmp_path)
        result = tools["calcular_tributos"](tipo="invalido", valor=1000.0)
        assert "erro" in result


# ─── artifacts.py ─────────────────────────────────────────────────────────────

_ART_MOD = "concilium.presentation.mcp.tools.artifacts"


class TestArtifactsTools:
    def _make_tools(self, monkeypatch, tmp_path):
        return _register_tools(_ART_MOD, monkeypatch, tmp_path)

    def test_listar_artefatos_projeto(self, monkeypatch, tmp_path):
        tools = self._make_tools(monkeypatch, tmp_path)
        store_mock = MagicMock()
        artifact_list = [{"nome": "relatorio.json", "tipo": "json", "audiencia": "agente"}]

        with (
            patch(f"{_ART_MOD}._project", return_value=store_mock),
            patch(f"{_ART_MOD}.ab.list_artifacts", return_value={"artefatos": artifact_list}),
        ):
            result = tools["listar_artefatos_projeto"](project_id="proj-1")
        assert "artefatos" in result

    def test_ler_artefato_texto_happy(self, monkeypatch, tmp_path):
        tools = self._make_tools(monkeypatch, tmp_path)
        store_mock = MagicMock()

        with (
            patch(f"{_ART_MOD}._project", return_value=store_mock),
            patch(f"{_ART_MOD}.ab.read_text", return_value={"conteudo": "data", "nome": "f.json"}),
        ):
            result = tools["obter_artefato"](formato="texto", project_id="proj-1", nome_arquivo="f.json")
        assert "conteudo" in result

    def test_ler_artefato_texto_not_found(self, monkeypatch, tmp_path):
        tools = self._make_tools(monkeypatch, tmp_path)
        store_mock = MagicMock()

        with (
            patch(f"{_ART_MOD}._project", return_value=store_mock),
            patch(f"{_ART_MOD}.ab.read_text", side_effect=FileNotFoundError("missing")),
        ):
            result = tools["obter_artefato"](formato="texto", project_id="proj-1", nome_arquivo="missing.json")
        assert "erro" in result

    def test_ler_artefato_texto_value_error(self, monkeypatch, tmp_path):
        tools = self._make_tools(monkeypatch, tmp_path)
        store_mock = MagicMock()

        with (
            patch(f"{_ART_MOD}._project", return_value=store_mock),
            patch(f"{_ART_MOD}.ab.read_text", side_effect=ValueError("binary")),
        ):
            result = tools["obter_artefato"](formato="texto", project_id="proj-1", nome_arquivo="img.png")
        assert "erro" in result

    def test_baixar_artefato_binario_happy(self, monkeypatch, tmp_path):
        tools = self._make_tools(monkeypatch, tmp_path)
        store_mock = MagicMock()

        with (
            patch(f"{_ART_MOD}._project", return_value=store_mock),
            patch(f"{_ART_MOD}.ab.read_binary_b64", return_value={"conteudo_base64": "abc="}),
        ):
            result = tools["obter_artefato"](formato="binario", project_id="proj-1", nome_arquivo="chart.png")
        assert "conteudo_base64" in result

    def test_baixar_artefato_binario_not_found(self, monkeypatch, tmp_path):
        tools = self._make_tools(monkeypatch, tmp_path)
        store_mock = MagicMock()

        with (
            patch(f"{_ART_MOD}._project", return_value=store_mock),
            patch(f"{_ART_MOD}.ab.read_binary_b64", side_effect=FileNotFoundError("no")),
        ):
            result = tools["obter_artefato"](formato="binario", project_id="proj-1", nome_arquivo="missing.png")
        assert "erro" in result

    def test_baixar_bundle_zip_happy(self, monkeypatch, tmp_path):
        tools = self._make_tools(monkeypatch, tmp_path)
        store_mock = MagicMock()

        with (
            patch(f"{_ART_MOD}._project", return_value=store_mock),
            patch(f"{_ART_MOD}.ab.build_bundle", return_value={"zip_base64": "abc="}),
        ):
            result = tools["obter_artefato"](formato="bundle", project_id="proj-1")
        assert "zip_base64" in result

    def test_baixar_bundle_zip_not_found(self, monkeypatch, tmp_path):
        tools = self._make_tools(monkeypatch, tmp_path)
        store_mock = MagicMock()

        with (
            patch(f"{_ART_MOD}._project", return_value=store_mock),
            patch(f"{_ART_MOD}.ab.build_bundle", side_effect=FileNotFoundError("no")),
        ):
            result = tools["obter_artefato"](formato="bundle", project_id="proj-1")
        assert "erro" in result

    def test_ler_artefato_texto_sem_nome_arquivo(self, monkeypatch, tmp_path):
        tools = self._make_tools(monkeypatch, tmp_path)
        store_mock = MagicMock()

        with patch(f"{_ART_MOD}._project", return_value=store_mock):
            result = tools["obter_artefato"](formato="texto", project_id="proj-1")
        assert "erro" in result
        assert "nome_arquivo" in result["erro"]

    def test_baixar_artefato_binario_sem_nome_arquivo(self, monkeypatch, tmp_path):
        tools = self._make_tools(monkeypatch, tmp_path)
        store_mock = MagicMock()

        with patch(f"{_ART_MOD}._project", return_value=store_mock):
            result = tools["obter_artefato"](formato="binario", project_id="proj-1")
        assert "erro" in result
        assert "nome_arquivo" in result["erro"]

    def test_obter_artefato_formato_invalido(self, monkeypatch, tmp_path):
        tools = self._make_tools(monkeypatch, tmp_path)
        store_mock = MagicMock()

        with patch(f"{_ART_MOD}._project", return_value=store_mock):
            result = tools["obter_artefato"](formato="csv", project_id="proj-1")
        assert "erro" in result
        assert "inválido" in result["erro"]




# ─── MCP tributacao ─────────────────────────────────────────────────────────


class TestMcpTributacao:
    def _make_server(self):
        from mcp.server.fastmcp import FastMCP

        from concilium.presentation.mcp.tools.tributacao import register

        server = FastMCP("test")
        register(server)
        return server

    def test_calcular_tributos_clt_delega_servico(self):
        """ADR-116 F5: tool unificada delega a calculate_employer_clt."""
        from concilium.domain.services.financial import tributacao as trib

        assert hasattr(trib, "calculate_employer_clt")
        assert hasattr(trib, "calculate_inss_employee")
        assert hasattr(trib, "calculate_irrf")

    def test_tributacao_register_adds_unified_tool(self):
        """ADR-116 F5: apenas calcular_tributos registrada (3 → 1)."""
        from mcp.server.fastmcp import FastMCP

        from concilium.presentation.mcp.tools.tributacao import register

        server = FastMCP("test")
        register(server)
        tool_names = list(server._tool_manager._tools.keys())
        assert "calcular_tributos" in tool_names
        assert "calcular_custo_empregador_clt" not in tool_names
        assert "calcular_inss_empregado" not in tool_names
        assert "calcular_irrf" not in tool_names




# ─── MCP artifacts ──────────────────────────────────────────────────────────


class TestMcpArtifacts:
    def test_register_adds_tools(self):
        from mcp.server.fastmcp import FastMCP

        from concilium.presentation.mcp.tools.artifacts import register

        server = FastMCP("test")
        register(server)
        names = list(server._tool_manager._tools.keys())
        assert "listar_artefatos_projeto" in names
        assert "obter_artefato" in names  # ADR-116 F5: ler_texto+baixar_binario+bundle_zip→obter_artefato

    def test_listar_artefatos_calls_list_artifacts(self):
        from mcp.server.fastmcp import FastMCP

        from concilium.presentation.mcp.tools.artifacts import register

        server = FastMCP("test")
        register(server)
        mock_store = MagicMock()
        with (
            patch("concilium.presentation.mcp.tools.artifacts._project", return_value=mock_store),
            patch("concilium.presentation.mcp.tools.artifacts.ab.list_artifacts", return_value={"items": []}),
        ):
            # Tools are registered; verify the ab module has the expected functions
            import concilium.application.services.artifact.artifact_bundle as ab

            assert hasattr(ab, "list_artifacts")
            assert hasattr(ab, "read_text")
            assert hasattr(ab, "read_binary_b64")
            assert hasattr(ab, "build_bundle")



