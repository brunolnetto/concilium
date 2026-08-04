"""Commands: adapter run."""

import typer
from rich import print as rprint

from concilium.presentation.cli.shared import config_root, parse_project_version, resolve_project

app = typer.Typer(name="adapter", help="Adaptadores de saÃ­da.", no_args_is_help=True)


@app.command("run")
def adapter_run(
    arg: str = typer.Argument(..., help="projeto ou projeto@vN"),
) -> None:
    """Gera artefato de saÃ­da via skill 09-relatorio-e-artefatos. Salva em outputs/relatorio.json."""
    nome, ver = parse_project_version(arg)
    project = resolve_project(nome)
    from concilium.application.runtime import Runtime, RuntimeError

    rt = Runtime(config_root())

    v = ver or project.current_version()
    if v is None:
        rprint("[red]Nenhuma versÃ£o ativa.[/red]")
        raise typer.Exit(1)

    try:
        result = rt.run_skill("09-relatorio-e-artefatos", project, version=v, inputs={})
    except RuntimeError as e:
        rprint(f"[red]Erro de runtime: {e}[/red]")
        raise typer.Exit(1) from None

    if result.has_errors:
        rprint("[red]âœ—[/red] Adapter falhou:")
        for val in result.validacoes:
            cor = {"OK": "green", "AVISO": "yellow", "ERRO": "red"}[val.status]
            rprint(f"  [{cor}]{val.status:5s}[/{cor}] {val.codigo}: {val.mensagem or ''}")
        raise typer.Exit(1)

    rprint(f"[green]âœ“[/green] RelatÃ³rio gerado: {v}/outputs/relatorio.json")
