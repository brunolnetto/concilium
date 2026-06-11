"""concilium auth — gestão de usuários e dispositivos.

Comandos de administrador para o sistema de autenticação por device code.

Uso típico:
  # Criar usuário
  concilium auth add-user --id bruno --scope mcp:read --scope pipeline:run

  # Gerar device code para o usuário configurar o Claude Desktop
  concilium auth new-device --user bruno --device "macbook-bruno"

  # Listar dispositivos ativos
  concilium auth list-devices

  # Revogar acesso de um dispositivo
  concilium auth revoke-device --device macbook-bruno
"""

from __future__ import annotations

import secrets

import typer
from rich import print as rprint
from rich.table import Table

app = typer.Typer(
    name="auth",
    help="Gestão de usuários, dispositivos e tokens JWT.",
    no_args_is_help=True,
)


# ── Usuários ──────────────────────────────────────────────────────────────────


@app.command("add-user")
def add_user(
    client_id: str = typer.Option(..., "--id", "-i", help="ID do cliente/usuário."),
    secret: str | None = typer.Option(None, "--secret", "-s", help="Secret. Gerado automaticamente se omitido."),
    role: str = typer.Option(
        "operator", "--role", "-r", help="Role RBAC: viewer | operator | engineer | admin | service-ci | auditor"
    ),
    notes: str = typer.Option("", "--notes", help="Observações opcionais."),
) -> None:
    """Registra um novo usuário/cliente no auth store.

    Roles disponíveis:
      viewer     — leitura de projetos e artefatos
      operator   — viewer + criar projetos + executar pipeline + dados financeiros
      engineer   — operator + aprovar versões + escrever catálogo
      admin      — acesso completo incluindo gestão de usuários
      service-ci — criar + executar pipeline (sem dados financeiros, sem aprovar)
      auditor    — leitura + dados financeiros (sem executar)
    """
    from concilium.infrastructure.auth.auth_store import get_auth_store

    store = get_auth_store()
    generated = secret is None
    if generated:
        secret = secrets.token_urlsafe(32)

    try:
        record = store.add_client(client_id, secret, [role], notes)
    except ValueError as e:
        rprint(f"[red]Erro:[/red] {e}")
        raise typer.Exit(1)

    rprint(f"[green]✓ Usuário '{record.client_id}' criado.[/green]")
    rprint(f"  Role    : {', '.join(record.roles)}")
    if generated:
        rprint("\n[yellow]Secret gerado (guarde agora — não será exibido de novo):[/yellow]")
        rprint(f"  [bold]{secret}[/bold]")


@app.command("list-users")
def list_users() -> None:
    """Lista todos os usuários registrados no auth store."""
    from concilium.infrastructure.auth.auth_store import get_auth_store

    records = get_auth_store().list_clients()
    if not records:
        rprint("[dim]Nenhum usuário registrado no store local.[/dim]")
        rprint("[dim]Usuários em CONCILIUM__AUTH_CLIENTS não são listados aqui.[/dim]")
        return

    table = Table(title="Usuários", show_header=True)
    table.add_column("ID", style="cyan")
    table.add_column("Role(s)")
    table.add_column("Ativo")
    table.add_column("Criado em")
    table.add_column("Notas", style="dim")

    for r in records:
        table.add_row(
            r.client_id,
            ", ".join(r.roles),
            "✓" if r.active else "✗",
            r.created_at[:10],
            r.notes,
        )

    rprint(table)


@app.command("remove-user")
def remove_user(
    client_id: str = typer.Option(..., "--id", "-i", help="ID do cliente a remover."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirmar sem prompt."),
) -> None:
    """Remove um usuário do auth store (e revoga todos os seus dispositivos)."""
    from concilium.infrastructure.auth.auth_store import get_auth_store

    if not yes:
        typer.confirm(f"Remover usuário '{client_id}' e revogar todos os seus dispositivos?", abort=True)

    store = get_auth_store()
    revoked = store.revoke_device(client_id)  # revoga por client_id via list_devices
    # Revoke all devices for this client
    devices = store.list_devices(client_id=client_id)
    for d in devices:
        store.revoke_device(d.device_id)

    removed = store.remove_client(client_id)
    if not removed:
        rprint(f"[yellow]Usuário '{client_id}' não encontrado no store local.[/yellow]")
    else:
        rprint(f"[green]✓ Usuário '{client_id}' removido. Dispositivos revogados.[/green]")


# ── Dispositivos ──────────────────────────────────────────────────────────────


@app.command("new-device")
def new_device(
    user: str = typer.Option(..., "--user", "-u", help="client_id do usuário."),
    device: str = typer.Option(..., "--device", "-d", help="Nome do dispositivo (ex: macbook-bruno)."),
    scopes: list[str] | None = typer.Option(None, "--scope", help="Escopos. Default: herda do usuário."),
    expires: str = typer.Option("1h", "--expires", "-e", help="Expiração do código (ex: 1h, 30m)."),
    show_config: bool = typer.Option(
        True, "--config/--no-config", help="Exibir bloco JSON para claude_desktop_config."
    ),
) -> None:
    """Gera um device code de uso único para o usuário configurar o Claude Desktop."""
    import json as _json

    from concilium.infrastructure.auth.auth_store import get_auth_store

    store = get_auth_store()
    record = store.create_device_code(
        client_id=user,
        device_id=device,
        device_name=device,
        scopes=scopes,
    )

    rprint(f"\n[green]✓ Device code gerado para '{user}' / '{device}'[/green]")
    rprint(f"  Código  : [bold]{record.code}[/bold]")
    rprint(f"  Expira  : {record.expires_at[:19].replace('T', ' ')} UTC")
    rprint(f"  Roles   : {', '.join(record.roles)}")
    rprint("  [dim]Uso único — inválido após primeiro uso ou após expirar.[/dim]")

    if show_config:
        from concilium.infrastructure.settings import get_storage

        storage = get_storage()

        config_block = {
            "mcpServers": {
                "concilium": {
                    "command": "concilium-mcp-proxy",
                    "env": {
                        "CONCILIUM_DEVICE_CODE": record.code,
                        "CONCILIUM_DEVICE_ID": device,
                        "CONCILIUM_SERVER_URL": "https://mcp.mendesloboconstrucao.com.br",
                    },
                }
            }
        }

        rprint("\n[bold]Envie ao usuário — colar em claude_desktop_config.json:[/bold]")
        rprint("[dim]macOS: ~/Library/Application Support/Claude/claude_desktop_config.json[/dim]")
        rprint("[dim]Win:   %APPDATA%\\Claude\\claude_desktop_config.json[/dim]\n")
        typer.echo(_json.dumps(config_block, indent=2, ensure_ascii=False))


@app.command("list-devices")
def list_devices(
    user: str | None = typer.Option(None, "--user", "-u", help="Filtrar por client_id."),
) -> None:
    """Lista dispositivos ativos (refresh tokens não revogados e não expirados)."""
    from concilium.infrastructure.auth.auth_store import get_auth_store

    devices = get_auth_store().list_devices(client_id=user)
    if not devices:
        rprint("[dim]Nenhum dispositivo ativo.[/dim]")
        return

    table = Table(title="Dispositivos ativos", show_header=True)
    table.add_column("Device ID", style="cyan")
    table.add_column("Usuário")
    table.add_column("Escopos")
    table.add_column("Emitido em")
    table.add_column("Expira em")
    table.add_column("Último uso")

    for d in devices:
        table.add_row(
            d.device_id,
            d.client_id,
            ", ".join(d.scopes),
            d.issued_at[:10],
            d.expires_at[:10],
            d.last_used_at[:10] if d.last_used_at else "—",
        )

    rprint(table)


@app.command("revoke-device")
def revoke_device(
    device: str = typer.Option(..., "--device", "-d", help="Device ID a revogar."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirmar sem prompt."),
) -> None:
    """Revoga todos os refresh tokens de um dispositivo."""
    from concilium.infrastructure.auth.auth_store import get_auth_store

    if not yes:
        typer.confirm(f"Revogar acesso do dispositivo '{device}'?", abort=True)

    count = get_auth_store().revoke_device(device)
    if count:
        rprint(f"[green]✓ {count} token(s) revogado(s) para '{device}'.[/green]")
    else:
        rprint(f"[yellow]Nenhum token ativo encontrado para '{device}'.[/yellow]")
