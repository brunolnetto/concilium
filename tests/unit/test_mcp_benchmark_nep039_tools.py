"""Tests for MCP tools registered in benchmark_nep039.py (NEP-039).

Strategy: call `register(server)` with a mock FastMCP instance whose `.tool`
side-effect captures decorated callables. Each inner function is then invoked
directly so no MCP transport is needed. consultar_benchmark reads from the
filesystem (benchmarks/data/) — tests mock _config_root via its source module
concilium.presentation.mcp._context.
"""

from unittest.mock import MagicMock, patch

import pytest

from concilium.presentation.mcp.tools.benchmark_nep039 import register

_CTX_CONFIG_ROOT = "concilium.presentation.mcp._context._config_root"
_CTX_WRAP = "concilium.presentation.mcp._context._wrap_response"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_server_and_tools():
    """Build a mock FastMCP server and return a dict of captured tool functions."""
    tools: dict = {}
    server = MagicMock()

    def _tool_decorator(description=None, **_kw):
        def _capture(fn):
            tools[fn.__name__] = fn
            return fn

        return _capture

    server.tool.side_effect = _tool_decorator
    register(server)
    return server, tools


@pytest.fixture
def tools():
    _, t = _make_server_and_tools()
    return t


# ---------------------------------------------------------------------------
# register()
# ---------------------------------------------------------------------------


class TestRegister:
    def test_only_consultar_benchmark_registered(self):
        """register() must register exactly one tool: consultar_benchmark."""
        _, tools = _make_server_and_tools()
        assert set(tools.keys()) == {"consultar_benchmark"}

    def test_server_tool_called_one_time(self):
        server, _ = _make_server_and_tools()
        assert server.tool.call_count == 1


# ---------------------------------------------------------------------------
# consultar_benchmark — list mode (benchmark_id=None)
# ---------------------------------------------------------------------------


class TestConsultarBenchmarkListMode:
    def test_empty_data_dir_returns_zero(self, tmp_path, tools):
        """When data_dir does not exist, returns total=0."""
        with patch(_CTX_CONFIG_ROOT, return_value=tmp_path / "config"):
            result = tools["consultar_benchmark"]()

        assert result["total"] == 0
        assert result["benchmarks"] == []

    def test_lists_benchmark_dirs(self, tmp_path, tools):
        """Benchmark dirs with referencia.json are listed."""
        config = tmp_path / "config"
        data_dir = tmp_path / "benchmarks" / "data"
        slug_dir = data_dir / "agis-q1"
        slug_dir.mkdir(parents=True)
        import json

        (slug_dir / "referencia.json").write_text(
            json.dumps(
                {
                    "projeto": {"nome": "AGIS Q1", "tipo_obra": "viaduto"},
                    "meta": {"gerado_em": "2025-01-15"},
                    "eap": [],
                }
            ),
            encoding="utf-8",
        )

        with patch(_CTX_CONFIG_ROOT, return_value=config):
            result = tools["consultar_benchmark"]()

        assert result["total"] == 1
        entry = result["benchmarks"][0]
        assert entry["benchmark_id"] == "agis-q1"
        assert entry["nome"] == "AGIS Q1"
        assert entry["tipo_obra"] == "viaduto"

    def test_dir_without_referencia_json_uses_slug_as_name(self, tmp_path, tools):
        config = tmp_path / "config"
        data_dir = tmp_path / "benchmarks" / "data"
        (data_dir / "plain-slug").mkdir(parents=True)

        with patch(_CTX_CONFIG_ROOT, return_value=config):
            result = tools["consultar_benchmark"]()

        assert result["total"] == 1
        assert result["benchmarks"][0]["benchmark_id"] == "plain-slug"

    def test_non_directory_entries_ignored(self, tmp_path, tools):
        config = tmp_path / "config"
        data_dir = tmp_path / "benchmarks" / "data"
        data_dir.mkdir(parents=True)
        (data_dir / "some-file.txt").write_text("noise")
        (data_dir / "real-slug").mkdir()

        with patch(_CTX_CONFIG_ROOT, return_value=config):
            result = tools["consultar_benchmark"]()

        assert result["total"] == 1
        assert result["benchmarks"][0]["benchmark_id"] == "real-slug"


# ---------------------------------------------------------------------------
# consultar_benchmark — detail mode (benchmark_id provided)
# ---------------------------------------------------------------------------


class TestConsultarBenchmarkDetailMode:
    def test_not_found_returns_erro(self, tmp_path, tools):
        config = tmp_path / "config"
        data_dir = tmp_path / "benchmarks" / "data"
        data_dir.mkdir(parents=True)

        with patch(_CTX_CONFIG_ROOT, return_value=config):
            result = tools["consultar_benchmark"](benchmark_id="ghost")

        assert "erro" in result
        assert result["status"] == "NAO_ENCONTRADO"
        assert "ghost" in result["erro"]

    def test_found_without_referencia_returns_none_referencia(self, tmp_path, tools):
        config = tmp_path / "config"
        data_dir = tmp_path / "benchmarks" / "data"
        (data_dir / "empty-slug").mkdir(parents=True)

        with patch(_CTX_CONFIG_ROOT, return_value=config):
            result = tools["consultar_benchmark"](benchmark_id="empty-slug")

        assert result["benchmark_id"] == "empty-slug"
        assert result["referencia"] is None

    def test_found_with_referencia_returns_detail(self, tmp_path, tools):
        import json

        config = tmp_path / "config"
        data_dir = tmp_path / "benchmarks" / "data"
        slug_dir = data_dir / "agis-q1"
        slug_dir.mkdir(parents=True)
        ref = {
            "projeto": {"nome": "AGIS Q1"},
            "eap": [{"id": "1"}, {"id": "2"}, {"id": "3"}],
            "meta": {"gerado_em": "2025-01-15"},
        }
        (slug_dir / "referencia.json").write_text(json.dumps(ref), encoding="utf-8")

        with patch(_CTX_CONFIG_ROOT, return_value=config):
            result = tools["consultar_benchmark"](benchmark_id="agis-q1")

        assert result["benchmark_id"] == "agis-q1"
        assert result["eap_n_itens"] == 3
        assert result["projeto"]["nome"] == "AGIS Q1"
        assert result["meta"]["gerado_em"] == "2025-01-15"

    def test_corrupted_referencia_returns_erro(self, tmp_path, tools):
        config = tmp_path / "config"
        data_dir = tmp_path / "benchmarks" / "data"
        slug_dir = data_dir / "bad-slug"
        slug_dir.mkdir(parents=True)
        (slug_dir / "referencia.json").write_text("NOT JSON", encoding="utf-8")

        with patch(_CTX_CONFIG_ROOT, return_value=config):
            result = tools["consultar_benchmark"](benchmark_id="bad-slug")

        assert "erro" in result
