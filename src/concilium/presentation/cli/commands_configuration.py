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
    """Lista os temas visuais disponíveis com paleta de cores."""
    import json

    from rich.text import Text

    root = _config_root() / "temas"
    table = Table(title="Temas disponíveis", show_header=True, header_style="bold")
    table.add_column("Tema", style="cyan")
    table.add_column("Empresa")
    table.add_column("Perfil")
    table.add_column("Cabeçalho")
    table.add_column("Destaque")
    table.add_column("Fonte corpo")

    def _swatch(hex_color: str, label: str) -> Text:
        t = Text()
        t.append("██ ", style=f"#{hex_color}")
        t.append(f"#{hex_color} {label}")
        return t

    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        try:
            tema = json.loads((d / "tema.json").read_text(encoding="utf-8"))
        except Exception:
            table.add_row(d.name, "?", "?", "?", "?", "?")
            continue
        cores = tema.get("cores", {})
        table.add_row(
            tema.get("id", d.name),
            tema.get("empresa", "-"),
            tema.get("perfil_exibicao", "-"),
            _swatch(cores.get("cabecalho_fundo", "888888"), cores.get("cabecalho_texto", "")),
            _swatch(cores.get("destaque", "888888"), ""),
            tema.get("fontes", {}).get("corpo", "-"),
        )
    Console().print(table)


@app_jurisdicao.command("list")
def jurisdicao_list() -> None:
    """Lista as jurisdições disponíveis com alíquotas tributárias agregadas."""
    import json

    root = _config_root() / "jurisdicoes"
    table = Table(title="Jurisdições disponíveis", show_header=True, header_style="bold")
    table.add_column("Código", style="cyan")
    table.add_column("Nome")
    table.add_column("Parent")
    table.add_column("ISS", justify="right")
    table.add_column("PIS", justify="right")
    table.add_column("COFINS", justify="right")
    table.add_column("CPRB", justify="right")
    table.add_column("Total trib.", justify="right", style="bold")

    for f in sorted(root.rglob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        aliq = d.get("motor_tributario_bdi", {}).get("aliquotas", {})
        total = sum(aliq.values()) if aliq else None
        table.add_row(
            d.get("codigo", f.stem),
            d.get("nome", "-"),
            d.get("parent_id", "-"),
            f"{aliq.get('ISS', 0) * 100:.2f}%" if aliq else "-",
            f"{aliq.get('PIS', 0) * 100:.2f}%" if aliq else "-",
            f"{aliq.get('COFINS', 0) * 100:.2f}%" if aliq else "-",
            f"{aliq.get('CPRB', 0) * 100:.2f}%" if aliq else "-",
            f"{total * 100:.2f}%" if total is not None else "-",
        )
    Console().print(table)
