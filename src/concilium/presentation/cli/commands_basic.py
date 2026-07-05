"""Commands: init, status, validate."""

import typer
from rich import print as rprint
from rich.table import Table

from concilium.presentation.cli.shared import (
    config_root,
    parse_project_version,
    project_repository,
    projetos_root,
    resolve_project,
)

app = typer.Typer(name="root", help="Comandos bÃ¡sicos.", no_args_is_help=True)


@app.command("list")
def list_projects() -> None:
    """Lista todos os projetos existentes."""
    from concilium.infrastructure.storage.project import ProjectStore

    root = projetos_root()
    if not root.exists():
        rprint("[yellow]Nenhum projeto encontrado.[/yellow]")
        return

    projetos = [p for p in sorted(root.iterdir()) if p.is_dir()]
    if not projetos:
        rprint("[yellow]Nenhum projeto encontrado.[/yellow]")
        return

    t = Table(show_header=True, header_style="bold")
    t.add_column("ID", style="cyan")
    t.add_column("Nome")
    t.add_column("Contexto")
    t.add_column("Versão")
    for p in projetos:
        try:
            store = ProjectStore(p)
            meta = store.meta
            t.add_row(p.name, meta.get("nome", "?"), meta.get("contexto_id", "?"), meta.get("current_version") or "-")
        except Exception as e:
            t.add_row(p.name, "[red]?[/red]", "[red]?[/red]", f"[red]{e}[/red]")
    rprint(t)


@app.command()
def init(
    nome: str = typer.Argument(..., help="Nome legÃ­vel do projeto."),
    contexto: str = typer.Option(
        "samples",
        "--contexto",
        "-c",
        help="ID do contexto de obra (config/contextos/{id}.json).",
    ),
) -> None:
    """Cria novo projeto. Gera UUID, popula meta.json, prepara diretÃ³rios."""
    from concilium.application.runtime import Runtime

    config = config_root()
    rt = Runtime(config)
    try:
        rt.load_contexto(contexto)
    except RuntimeError as e:
        rprint(f"[red]{e}[/red]")
        raise typer.Exit(1) from None

    repo = project_repository()
    project = repo.create_project(nome, contexto)
    rprint(f"[green][OK][/green] Projeto criado: [bold]{nome}[/bold]")
    rprint(f"  ID:       {project.meta['id']}")
    rprint(f"  Contexto: {contexto}")
    rprint(f"  Path:     {project.root}")


@app.command()
def _print_skills_table(console) -> None:
    from rich.table import Table

    from concilium.application.skills.registry import SkillRegistry

    registry = SkillRegistry()
    table = Table(title="Catálogo de Skills")
    table.add_column("ID", style="cyan")
    table.add_column("Descrição")
    for sid, meta in registry.get_all_skills().items():
        table.add_row(sid, meta.descricao)
    console.print(table)


def status(
    projeto: str = typer.Argument(..., help="Nome ou UUID do projeto."),
    skills: bool = typer.Option(False, "--skills", help="Lista catálogo de skills disponíveis."),
    version: bool = typer.Option(False, "--version", help="Mostra versão do framework e infra."),
) -> None:
    """Mostra estado atual do projeto: versão ativa, skills executadas, integridade."""
    import json

    from rich.console import Console
    from rich.table import Table

    console = Console()

    if version:
        rprint("[bold cyan]Concilium Framework[/bold cyan]")
        rprint("  Versão:   0.6.2-beta")
        rprint(f"  Config:   {config_root()}")
        return

    if skills:
        _print_skills_table(console)
        return

    project = resolve_project(projeto)
    meta = project.meta

    table = Table(title=f"Projeto: {meta['nome']}", show_header=False)
    table.add_column("Campo", style="cyan")
    table.add_column("Valor")
    table.add_row("ID", meta["id"])
    table.add_row("Contexto", meta["contexto_id"])
    table.add_row("Criado em", meta.get("criado_em", "-"))
    table.add_row("Versão atual", meta.get("current_version") or "(nenhuma)")
    table.add_row("Versões", ", ".join(project.list_versions()) or "(nenhuma)")
    console.print(table)

    cur = project.current_version()
    if cur:
        log_path = project.version_path(cur) / "invocations.log"
        if log_path.exists() and log_path.stat().st_size > 0:
            console.print(f"\n[bold]Invocação de Skills em {cur}:[/bold]")
            for line in log_path.read_text(encoding="utf-8").splitlines():
                entry = json.loads(line)
                cor = "green" if entry["status"] == "OK" else "red"
                console.print(f"  [{cor}]{entry['status']:5s}[/{cor}] {entry['skill']:30s}  {entry['ts']}")


@app.command()
def _audit_val_color(status: str) -> str:
    return {"OK": "green", "AVISO": "yellow", "ERRO": "red"}.get(status, "red")


def _audit_print_conflitos(conflitos_pico) -> None:
    from rich import print as rprint

    if conflitos_pico:
        rprint(f"\n[bold yellow]⚠ {len(conflitos_pico)} Conflitos de Recurso Detectados:[/bold yellow]")
        for c in conflitos_pico[:3]:
            rprint(f"  - {c.recurso_id}: Excesso de {c.quantidade_excedente} na semana {c.semana}")
        if len(conflitos_pico) > 3:
            rprint(f"    (... e mais {len(conflitos_pico) - 3} outros)")
    else:
        rprint("\n[green]✔ Sem conflitos de recurso detectados.[/green]")


def audit(
    arg: str = typer.Argument(..., help="projeto ou projeto@vN"),
) -> None:
    """Diagnóstico 360º de Engenharia: Validação, Gargalos e Financeiro."""
    nome, ver = parse_project_version(arg)
    project = resolve_project(nome)
    canonical = project.load_canonical(ver)

    if canonical is None:
        rprint("[red]Sem dados canônicos para auditoria. Execute 'run' primeiro.[/red]")
        raise typer.Exit(1)

    rprint(f"\n[bold cyan]Auditoria de Engenharia: {project.meta['nome']} ({ver})[/bold cyan]")

    # 1. Integridade
    status_int = canonical.pipeline_integridade or "DESCONHECIDO"
    cor_int = "green" if status_int == "COMPLETO" else "yellow"
    rprint(f"  Integridade: [{cor_int}]{status_int}[/{cor_int}]")

    # 2. Financeiro
    if canonical.resultado:
        res = canonical.resultado
        rprint(f"  Margem:      [bold]{res.margem_pct * 100:.2f}%[/bold] ({res.status_margem})")
        rprint(f"  Custo Total: R$ {res.custo.total:,.2f}")

    # 3. Gargalos (Recursos)
    _audit_print_conflitos(canonical.conflitos_pico)

    # 4. Validações de Skill
    if canonical.resultado and canonical.resultado.validacoes:
        rprint("\n[bold]Validações de Skill:[/bold]")
        for v in canonical.resultado.validacoes:
            cor = _audit_val_color(v.status)
            rprint(f"  [{cor}]{v.status:5s}[/{cor}] {v.codigo}")
