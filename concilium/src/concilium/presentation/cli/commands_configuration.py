"""CLI commands for temas and jurisdicoes configuration."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app_temas = typer.Typer(name="temas", help="Temas visuais disponíveis.", no_args_is_help=True)
app_jurisdicao = typer.Typer(name="jurisdicao", help="Jurisdições disponíveis.", no_args_is_help=True)


def _config_root() -> Path:
    from concilium.presentation.cli.shared import config_root

    return config_root()


@app_temas.command("list")
def temas_list() -> None:
    """Lista os temas visuais disponíveis."""
    root = _config_root() / "temas"
    temas = sorted(d.name for d in root.iterdir() if d.is_dir())
    table = Table("Tema", title="Temas disponíveis")
    for t in temas:
        table.add_row(t)
    Console().print(table)


@app_jurisdicao.command("list")
def jurisdicao_list() -> None:
    """Lista as jurisdições disponíveis."""
    root = _config_root() / "jurisdicoes"
    files = sorted(f.stem for f in root.rglob("*.json"))
    table = Table("Jurisdição", title="Jurisdições disponíveis")
    for f in files:
        table.add_row(f)
    Console().print(table)
