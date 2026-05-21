"""CLI Typer para o Concilium — Fase 1A.

Comandos implementados:
    concilium init <nome>                 — cria novo projeto
    concilium snapshot create             — tira snapshot das camadas atuais
    concilium version new <project>       — cria nova versão (copy-on-write)
    concilium run <skill> --version vN    — invoca skill
    concilium status <project>            — mostra estado atual
    concilium validate <project>@vN       — re-executa validações

Convenções:
    - <project> pode ser nome ou UUID. Se há múltiplos com mesmo nome, exige UUID.
    - <project>@vN aceita versão explícita; sem @ usa current_version
    - --as <papel>  para comandos que requerem decisão humana (approve, decision log)
"""

import json
import os
from pathlib import Path

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from concilium.runtime import Runtime, RuntimeError
from concilium.storage.project import ProjectStore

app = typer.Typer(
    name="concilium",
    help="Framework determinístico de planejamento de obras.",
    no_args_is_help=True,
    add_completion=False,
)

snapshot_app = typer.Typer(name="snapshot", help="Operações de snapshot.", no_args_is_help=True)
version_app = typer.Typer(name="version", help="Operações de versionamento.", no_args_is_help=True)
app.add_typer(snapshot_app)
app.add_typer(version_app)

console = Console()

# Diretórios padrão
def _config_root() -> Path:
    return Path(os.environ.get("CONCILIUM_CONFIG", "."))


def _projetos_root() -> Path:
    return Path(os.environ.get("CONCILIUM_PROJETOS", "./projetos"))


def _resolve_project(name_or_id: str) -> ProjectStore:
    """Resolve nome ou UUID para um ProjectStore."""
    base = _projetos_root()
    if not base.exists():
        rprint(f"[red]Diretório de projetos não existe: {base}[/red]")
        raise typer.Exit(1)

    # Tentativa direta por UUID/diretório
    direct = base / name_or_id
    if direct.is_dir() and (direct / "meta.json").exists():
        return ProjectStore(direct)

    # Busca por nome
    matches = []
    for p in base.iterdir():
        if not p.is_dir():
            continue
        meta_path = p / "meta.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text())
        if meta.get("nome") == name_or_id:
            matches.append(p)

    if len(matches) == 0:
        rprint(f"[red]Projeto não encontrado: {name_or_id}[/red]")
        raise typer.Exit(1)
    if len(matches) > 1:
        rprint(f"[red]Múltiplos projetos com nome '{name_or_id}'. Use o UUID:[/red]")
        for m in matches:
            rprint(f"  • {m.name}")
        raise typer.Exit(1)
    return ProjectStore(matches[0])


def _parse_project_version(arg: str) -> tuple[str, str | None]:
    """Aceita 'projeto' ou 'projeto@v3'. Retorna (nome, versao_ou_None)."""
    if "@" in arg:
        nome, ver = arg.split("@", 1)
        return nome, ver
    return arg, None


# ─────────────────────── COMANDOS ───────────────────────


@app.command()
def init(
    nome: str = typer.Argument(..., help="Nome legível do projeto."),
    perfil: str = typer.Option("agis", "--perfil", "-p", help="ID do perfil de construtora."),
    jurisdicao: str = typer.Option("BR", "--jurisdicao", "-j", help="Código da jurisdição."),
) -> None:
    """Cria novo projeto. Gera UUID, popula meta.json, prepara diretórios."""
    config = _config_root()
    rt = Runtime(config)
    # Valida que perfil e jurisdição existem antes de criar
    try:
        rt.load_perfil(perfil)
        rt.load_jurisdicao(jurisdicao)
    except RuntimeError as e:
        rprint(f"[red]{e}[/red]")
        raise typer.Exit(1) from None

    base = _projetos_root()
    base.mkdir(parents=True, exist_ok=True)
    project = ProjectStore.init(base, nome, perfil, jurisdicao)
    rprint(f"[green]✓[/green] Projeto criado: [bold]{nome}[/bold]")
    rprint(f"  ID:        {project.meta['id']}")
    rprint(f"  Perfil:    {perfil}")
    rprint(f"  Jurisdição: {jurisdicao}")
    rprint(f"  Path:      {project.root}")


@snapshot_app.command("create")
def snapshot_create(
    projeto: str = typer.Argument(..., help="Nome ou UUID do projeto."),
) -> None:
    """Tira snapshot das Camadas 0-3 atuais. Reusa por hash quando possível."""
    project = _resolve_project(projeto)
    rt = Runtime(_config_root())
    snaps = rt.create_snapshots(project)
    rprint(f"[green]✓[/green] Snapshots criados:")
    for kind, h in snaps.items():
        rprint(f"  {kind:12s} {h}")


@version_app.command("new")
def version_new(
    projeto: str = typer.Argument(..., help="Nome ou UUID do projeto."),
    base: str | None = typer.Option(None, "--base", help="Versão base para copy-on-write."),
) -> None:
    """Cria nova versão (copy-on-write da current ou da base especificada)."""
    project = _resolve_project(projeto)
    new_v = project.new_version(base=base)
    rprint(f"[green]✓[/green] Versão criada: [bold]{new_v}[/bold]")
    if base:
        rprint(f"  Base: {base}")
    rprint(f"  Path: {project.version_path(new_v)}")


@app.command()
def run(
    skill: str = typer.Argument(..., help="ID da skill (ex.: 01-praticabilidade)."),
    projeto: str = typer.Option(..., "--project", "-p", help="Nome ou UUID do projeto."),
    version: str | None = typer.Option(None, "--version", "-v", help="Versão alvo."),
    inputs_json: str | None = typer.Option(
        None, "--inputs", "-i", help="JSON com inputs da skill, ou path para arquivo .json"
    ),
) -> None:
    """Invoca uma skill. Persiste canônico se sucesso. Sempre registra log."""
    project = _resolve_project(projeto)
    rt = Runtime(_config_root())

    inputs: dict = {}
    if inputs_json:
        if Path(inputs_json).exists():
            inputs = json.loads(Path(inputs_json).read_text())
        else:
            inputs = json.loads(inputs_json)

    try:
        result = rt.run_skill(skill, project, version=version, inputs=inputs)
    except RuntimeError as e:
        rprint(f"[red]Erro de runtime: {e}[/red]")
        raise typer.Exit(1) from None
    except Exception as e:
        rprint(f"[red]Erro inesperado na skill: {e}[/red]")
        raise typer.Exit(2) from None

    if result.has_errors:
        rprint(f"[red]✗[/red] Skill {skill} falhou:")
    else:
        rprint(f"[green]✓[/green] Skill {skill} executada com sucesso.")

    # Mostra validações
    for v in result.validacoes:
        cor = {"OK": "green", "AVISO": "yellow", "ERRO": "red"}[v.status]
        msg = f": {v.mensagem}" if v.mensagem else ""
        rprint(f"  [{cor}]{v.status:5s}[/{cor}] {v.codigo}{msg}")

    if result.has_errors:
        raise typer.Exit(1)


@app.command()
def status(
    projeto: str = typer.Argument(..., help="Nome ou UUID do projeto."),
) -> None:
    """Mostra estado atual do projeto: versão ativa, skills executadas, validações."""
    project = _resolve_project(projeto)
    meta = project.meta

    table = Table(title=f"Projeto: {meta['nome']}", show_header=False)
    table.add_column("Campo", style="cyan")
    table.add_column("Valor")
    table.add_row("ID", meta["id"])
    table.add_row("Perfil", meta["perfil_construtora_id"])
    table.add_row("Jurisdição", meta["jurisdicao_id"])
    table.add_row("Criado em", meta.get("criado_em", "-"))
    table.add_row("Versão atual", meta.get("current_version") or "(nenhuma)")
    table.add_row("Versões existentes", ", ".join(project.list_versions()) or "(nenhuma)")
    console.print(table)

    # Mostra log de invocações da versão atual
    cur = project.current_version()
    if cur:
        log_path = project.version_path(cur) / "invocations.log"
        if log_path.exists() and log_path.stat().st_size > 0:
            console.print(f"\n[bold]Invocações em {cur}:[/bold]")
            for line in log_path.read_text().splitlines():
                entry = json.loads(line)
                cor = "green" if entry["status"] == "OK" else "red"
                console.print(
                    f"  [{cor}]{entry['status']:5s}[/{cor}] "
                    f"{entry['skill']:30s}  {entry['ts']}"
                )


@app.command()
def validate(
    arg: str = typer.Argument(..., help="projeto ou projeto@vN"),
) -> None:
    """Re-executa validações estruturais sobre o canônico (sem rodar skills)."""
    nome, ver = _parse_project_version(arg)
    project = _resolve_project(nome)
    canonical = project.load_canonical(ver)
    if canonical is None:
        rprint(f"[red]Sem canônico para validar[/red]")
        raise typer.Exit(1)

    rprint(f"[green]✓[/green] Canônico carregado e validado contra schema.")
    rprint(f"  Projeto:    {canonical.projeto.nome}")
    rprint(f"  Status:     {canonical.projeto.status}")
    rprint(f"  EAP itens:  {len(canonical.eap)}")
    rprint(f"  Cronograma: {len(canonical.cronograma)} itens")
    rprint(f"  Equipes:    {len(canonical.equipes_diretas)}")
    if canonical.resultado:
        rprint(f"  Margem:     {canonical.resultado.margem_pct*100:.2f}% ({canonical.resultado.status_margem})")
        for v in canonical.resultado.validacoes:
            cor = {"OK": "green", "AVISO": "yellow", "ERRO": "red"}[v.status]
            rprint(f"  [{cor}]{v.status:5s}[/{cor}] {v.codigo}")


if __name__ == "__main__":
    app()
