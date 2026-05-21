"""ADR-062: CLI commands for context and profile versioning.

Commands:
  concilium context versions <id>              List versions of a context
  concilium context new-version <id>           Create a new version of a context
  concilium context compare <id> <vA> <vB>     Compare two context versions

  concilium perfil versions <id>               List versions of a profile
  concilium perfil new-version <id>            Create a new version of a profile
  concilium perfil compare <id> <vA> <vB>      Compare two profile versions
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich import print as rprint
from rich.table import Table

from concilium.application.services.contexto_version_service import (
    ContextoVersionService,
    PerfilVersionService,
)

# ── Sub-apps ──────────────────────────────────────────────────────────────────

app_context = typer.Typer(name="context", help="Gerenciamento de versões de contextos (ADR-062).")
app_perfil = typer.Typer(name="perfil", help="Gerenciamento de versões de perfis (ADR-062).")


def _config_root() -> Path:
    """Resolve config/ relative to this file's installation."""
    for candidate in [
        Path(__file__).parents[4] / "config",
        Path(__file__).parents[5] / "config",
    ]:
        if candidate.exists():
            return candidate
    raise typer.BadParameter("Diretório config/ não encontrado.")


# ══════════════════════════════════════════════════════════════════════════════
# CONTEXT commands
# ══════════════════════════════════════════════════════════════════════════════


@app_context.command("list")
def context_list() -> None:
    """Lista todos os contextos disponíveis e suas versões."""
    svc = ContextoVersionService(_config_root())
    contexts = svc.list_contexts()
    if not contexts:
        rprint("[yellow]Nenhum contexto encontrado.[/yellow]")
        raise typer.Exit()

    table = Table(title="Contextos disponíveis", show_header=True, header_style="bold blue")
    table.add_column("ID")
    table.add_column("Nome")
    table.add_column("Versão ativa")
    table.add_column("Total versões")
    for c in contexts:
        table.add_row(
            c.get("id", "—"),
            c.get("nome", "—"),
            c.get("current_version", "v1"),
            str(len(c.get("versions") or [])),
        )
    rprint(table)


@app_context.command("versions")
def context_versions(
    contexto_id: str = typer.Argument(..., help="ID do contexto"),
) -> None:
    """Lista o histórico de versões de um contexto."""
    svc = ContextoVersionService(_config_root())
    versions = svc.list_versions(contexto_id)
    current = svc.current_version(contexto_id)
    if not versions:
        rprint(f"[yellow]Nenhuma versão encontrada para '{contexto_id}'.[/yellow]")
        raise typer.Exit()

    table = Table(title=f"Versões — {contexto_id}", show_header=True, header_style="bold")
    table.add_column("Versão")
    table.add_column("Ativa")
    table.add_column("Criado em")
    table.add_column("Por")
    table.add_column("Motivo")
    for v in versions:
        table.add_row(
            v.get("version", "—"),
            "✅" if v.get("version") == current else "",
            str(v.get("created_at") or "—")[:19].replace("T", " "),
            v.get("created_by") or "—",
            v.get("motivo") or "—",
        )
    rprint(table)


@app_context.command("new-version")
def context_new_version(
    contexto_id: str = typer.Argument(..., help="ID do contexto"),
    motivo: str = typer.Option(..., "--motivo", "-m", help="Motivo da nova versão (obrigatório)."),
    catalogo_id: str | None = typer.Option(None, help="Novo catalogo_id."),
    jurisdicao_id: str | None = typer.Option(None, help="Novo jurisdicao_id."),
    perfil_id: str | None = typer.Option(None, help="Novo perfil_id."),
    no_current: bool = typer.Option(False, "--no-current", help="Não tornar esta a versão ativa."),
    author: str = typer.Option("cli", "--author", "-a", help="Autor da versão."),
) -> None:
    """Cria uma nova versão de um contexto."""
    svc = ContextoVersionService(_config_root())
    fields: dict = {}
    if catalogo_id:
        fields["catalogo_id"] = catalogo_id
    if jurisdicao_id:
        fields["jurisdicao_id"] = jurisdicao_id
    if perfil_id:
        fields["perfil_id"] = perfil_id
    result = svc.create_version(contexto_id, fields, motivo, author, make_current=not no_current)
    rprint(f"[green]Versão [bold]{result['version']}[/bold] criada para '{contexto_id}'.[/green]")
    if not no_current:
        rprint(f"  → Versão ativa atualizada para [bold]{result['version']}[/bold].")


@app_context.command("compare")
def context_compare(
    contexto_id: str = typer.Argument(..., help="ID do contexto"),
    version_a: str = typer.Argument(..., help="Versão A (base)."),
    version_b: str = typer.Argument(..., help="Versão B (nova)."),
) -> None:
    """Compara duas versões de um contexto."""
    svc = ContextoVersionService(_config_root())
    diff = svc.compare(contexto_id, version_a, version_b)
    changed = diff.get("changed") or {}
    if not changed:
        rprint(f"[green]As versões {version_a} e {version_b} são idênticas.[/green]")
        return

    rprint(f"[bold]{len(changed)} campo(s) alterado(s)[/bold] entre {version_a} → {version_b}:")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Campo")
    table.add_column(f"De ({version_a})")
    table.add_column(f"Para ({version_b})")
    for field, delta in changed.items():
        table.add_row(field, str(delta.get("de") or "—"), str(delta.get("para") or "—"))
    rprint(table)
    unchanged = diff.get("unchanged") or []
    if unchanged:
        rprint(f"[dim]Inalterados: {', '.join(str(u) for u in unchanged)}[/dim]")


# ══════════════════════════════════════════════════════════════════════════════
# PERFIL commands (same pattern)
# ══════════════════════════════════════════════════════════════════════════════


@app_perfil.command("list")
def perfil_list() -> None:
    """Lista todos os perfis disponíveis e suas versões."""
    svc = PerfilVersionService(_config_root())
    perfis = svc.list_perfis()
    if not perfis:
        rprint("[yellow]Nenhum perfil encontrado.[/yellow]")
        raise typer.Exit()

    table = Table(title="Perfis disponíveis", show_header=True, header_style="bold blue")
    table.add_column("ID")
    table.add_column("Nome")
    table.add_column("Versão ativa")
    table.add_column("Total versões")
    for p in perfis:
        table.add_row(
            p.get("id", "—"),
            p.get("nome", "—"),
            p.get("current_version", "v1"),
            str(len(p.get("versions") or [])),
        )
    rprint(table)


@app_perfil.command("versions")
def perfil_versions(
    perfil_id: str = typer.Argument(..., help="ID do perfil"),
) -> None:
    """Lista o histórico de versões de um perfil."""
    svc = PerfilVersionService(_config_root())
    versions = svc.list_versions(perfil_id)
    current = svc.current_version(perfil_id)
    if not versions:
        rprint(f"[yellow]Nenhuma versão encontrada para '{perfil_id}'.[/yellow]")
        raise typer.Exit()

    table = Table(title=f"Versões — {perfil_id}", show_header=True, header_style="bold")
    table.add_column("Versão")
    table.add_column("Ativa")
    table.add_column("Criado em")
    table.add_column("Por")
    table.add_column("Motivo")
    for v in versions:
        table.add_row(
            v.get("version", "—"),
            "✅" if v.get("version") == current else "",
            str(v.get("created_at") or "—")[:19].replace("T", " "),
            v.get("created_by") or "—",
            v.get("motivo") or "—",
        )
    rprint(table)


@app_perfil.command("new-version")
def perfil_new_version(
    perfil_id: str = typer.Argument(..., help="ID do perfil"),
    motivo: str = typer.Option(..., "--motivo", "-m", help="Motivo da nova versão (obrigatório)."),
    jurisdicao_id: str | None = typer.Option(None, help="Nova jurisdicao_id."),
    no_current: bool = typer.Option(False, "--no-current", help="Não tornar esta a versão ativa."),
    author: str = typer.Option("cli", "--author", "-a", help="Autor da versão."),
) -> None:
    """Cria uma nova versão de um perfil."""
    svc = PerfilVersionService(_config_root())
    fields: dict = {}
    if jurisdicao_id:
        fields["jurisdicao_id"] = jurisdicao_id
    result = svc.create_version(perfil_id, fields, motivo, author, make_current=not no_current)
    rprint(f"[green]Versão [bold]{result['version']}[/bold] criada para '{perfil_id}'.[/green]")
    if not no_current:
        rprint(f"  → Versão ativa atualizada para [bold]{result['version']}[/bold].")


@app_perfil.command("compare")
def perfil_compare(
    perfil_id: str = typer.Argument(..., help="ID do perfil"),
    version_a: str = typer.Argument(..., help="Versão A (base)."),
    version_b: str = typer.Argument(..., help="Versão B (nova)."),
) -> None:
    """Compara duas versões de um perfil."""
    svc = PerfilVersionService(_config_root())
    diff = svc.compare(perfil_id, version_a, version_b)
    changed = diff.get("changed") or {}
    if not changed:
        rprint(f"[green]As versões {version_a} e {version_b} são idênticas.[/green]")
        return

    rprint(f"[bold]{len(changed)} campo(s) alterado(s)[/bold] entre {version_a} → {version_b}:")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Campo")
    table.add_column(f"De ({version_a})")
    table.add_column(f"Para ({version_b})")
    for field, delta in changed.items():
        table.add_row(field, str(delta.get("de") or "—"), str(delta.get("para") or "—"))
    rprint(table)
