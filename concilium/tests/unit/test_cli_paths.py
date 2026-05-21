from pathlib import Path

from concilium.presentation.cli import shared as cli_shared
from concilium.presentation.main import app


def test_cli_package_expoe_app() -> None:
    assert app is not None


def test_tools_root_resolve_para_diretorio_tools() -> None:
    root = cli_shared._tools_root()
    assert isinstance(root, Path)
    assert (root / "pyproject.toml").exists()


def test_config_root_usa_env_override(monkeypatch) -> None:
    monkeypatch.setenv("CONCILIUM_CONFIG_ROOT", "/tmp/config-root")
    assert cli_shared._config_root() == Path("/tmp/config-root")


def test_config_root_default_deriva_do_tools(monkeypatch) -> None:
    monkeypatch.delenv("CONCILIUM_CONFIG_ROOT", raising=False)
    assert cli_shared._config_root() == cli_shared._tools_root() / "config"


def test_projetos_root_usa_env_override(monkeypatch) -> None:
    monkeypatch.setenv("CONCILIUM_PROJECTS_ROOT", "/tmp/projetos-root")
    assert cli_shared._projetos_root() == Path("/tmp/projetos-root")


def test_projetos_root_default_deriva_do_tools(monkeypatch) -> None:
    monkeypatch.delenv("CONCILIUM_PROJECTS_ROOT", raising=False)
    assert cli_shared._projetos_root() == cli_shared._tools_root() / "projetos"
