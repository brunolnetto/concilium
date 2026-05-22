from __future__ import annotations

from pathlib import Path

from concilium.presentation.ui import launcher


def test_build_streamlit_command_uses_env_bind(monkeypatch) -> None:
    monkeypatch.setenv("CONCILIUM_UI_HOST", "0.0.0.0")
    monkeypatch.setenv("CONCILIUM_UI_PORT", "8600")

    cmd = launcher.build_streamlit_command(Path("src/concilium/presentation/ui/prototype_streamlit.py"))

    assert cmd[0] == "streamlit"
    assert cmd[1] == "run"
    assert cmd[2].replace("\\", "/").endswith("src/concilium/presentation/ui/prototype_streamlit.py")
    assert "--server.address" in cmd
    assert "0.0.0.0" in cmd
    assert "--server.port" in cmd
    assert "8600" in cmd


def test_resolve_ui_entrypoint_uses_override(monkeypatch) -> None:
    monkeypatch.setenv("CONCILIUM_UI_ENTRYPOINT", "/tmp/custom_ui.py")

    assert launcher.resolve_ui_entrypoint() == Path("/tmp/custom_ui.py")


def test_resolve_ui_entrypoint_defaults(monkeypatch) -> None:
    monkeypatch.delenv("CONCILIUM_UI_ENTRYPOINT", raising=False)

    assert launcher.resolve_ui_entrypoint().name == "prototype_streamlit.py"
