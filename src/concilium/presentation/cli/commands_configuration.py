"""CLI commands for temas and jurisdicoes configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

app_temas = typer.Typer(name="temas", help="Temas visuais disponíveis.", no_args_is_help=True)
app_jurisdicao = typer.Typer(name="jurisdicao", help="Jurisdições disponíveis.", no_args_is_help=True)
app_calendarios = typer.Typer(
    name="calendarios", help="Calendário operacional (feriados/pontos facultativos, ADR-068).", no_args_is_help=True
)


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


@app_calendarios.command("sync")
def calendarios_sync(
    source: Annotated[
        str,
        typer.Argument(
            help="Caminho do holiday_history.json (local, ou blob path quando --backend for informado)."
        ),
    ],
    backend: Annotated[
        str,
        typer.Option(
            "--backend",
            "-b",
            help="Backend de blob storage (ex.: sharepoint) para baixar `source` remotamente. "
            "Se omitido, `source` é lido como arquivo local.",
        ),
    ] = "",
) -> None:
    """Sincroniza config/calendarios/ (ADR-068) a partir do histórico de feriados.

    Fonte: `holiday_history.json`, exportado por
    `lab/feriados_api/src/exporters/holiday_history.py` (SCD2 por dia). Filtra
    automaticamente para registros vigentes (valid_to nulo) e níveis
    NACIONAL/ESTADUAL — MUNICIPAL é ignorado (cobertura só de capitais).

    Eventos de ponto_facultativo saem com fator_operacao=None: observá-lo ou
    não (binário — parada integral vs dia normal, sem meio-termo) NÃO é
    decidido aqui — é escolha de configuração de projeto, resolvida em
    runtime por skill 04 via `inputs["observar_pontos_facultativos"]`.
    """
    import json

    from concilium.application.services.catalog.calendario_sync import sync_calendarios_config

    if backend:
        from concilium.presentation.cli.commands_blob import _make_storage

        storage = _make_storage(backend)
        content = storage.ler_blob(source)
    else:
        content = Path(source).read_bytes()

    rows = json.loads(content)
    resultado = sync_calendarios_config(rows, _config_root())
    for path, n_eventos in sorted(resultado.items()):
        rprint(f"[bold green]✓[/bold green] {path}: {n_eventos} eventos")
