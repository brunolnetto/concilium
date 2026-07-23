"""Tests for ping() + novidades wiring (ADR-144 D2) — presentation/mcp/tools/system.py.

TDD: escritos antes da implementação. `ping()` delega para
`check_and_report_novidades(client_id)` (application/services/system_novelties.py,
já testado isoladamente em test_system_novelties.py) — aqui só confere a
integração: quando há novidade, ela aparece na resposta de `ping()`; quando
não há (ou sem identidade), o campo fica ausente.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from mcp.server.fastmcp import FastMCP

_SYSTEM_MOD = "concilium.presentation.mcp.tools.system"


def _register_tools(monkeypatch, tmp_path: Path) -> dict:
    import importlib

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CONCILIUM__CONFIG_ROOT", str(config_dir))
    monkeypatch.setenv("CONCILIUM__PROJECTS_ROOT", str(tmp_path / "projetos"))

    mod = importlib.import_module(_SYSTEM_MOD)
    importlib.reload(mod)
    server = FastMCP("test")
    mod.register(server)

    tools: dict = {}
    for t in server._tool_manager.list_tools():
        fn = getattr(t, "fn", None) or getattr(t, "func", None)
        tools[t.name] = fn
    return tools


class TestPingNovidades:
    def test_novidades_absent_when_nothing_to_report(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        with (
            patch(f"{_SYSTEM_MOD}.get_current_user_id", return_value="c1"),
            patch(f"{_SYSTEM_MOD}.check_and_report_novidades", return_value=None),
        ):
            result = tools["ping"]()
        assert "novidades" not in result

    def test_novidades_present_when_something_to_report(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        novidades = {
            "deploy": {"resumo": "ADR-144", "promoted_at": "2026-07-20T14:32:00+00:00"},
            "skill_desatualizado": False,
        }
        with (
            patch(f"{_SYSTEM_MOD}.get_current_user_id", return_value="c1"),
            patch(f"{_SYSTEM_MOD}.check_and_report_novidades", return_value=novidades),
        ):
            result = tools["ping"]()
        assert result["novidades"] == novidades

    def test_no_identity_never_calls_novidades_check(self, monkeypatch, tmp_path):
        """Sem client_id resolvível, nem vale a pena chamar — não há cursor a comparar."""
        tools = _register_tools(monkeypatch, tmp_path)
        with (
            patch(f"{_SYSTEM_MOD}.get_current_user_id", return_value=None),
            patch(f"{_SYSTEM_MOD}.check_and_report_novidades") as mock_check,
        ):
            result = tools["ping"]()
        mock_check.assert_not_called()
        assert "novidades" not in result
