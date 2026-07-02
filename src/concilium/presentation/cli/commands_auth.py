"""concilium auth — gestão de usuários e dispositivos.

Comandos de administrador para o sistema de autenticação. Cada usuário recebe um
client_code reutilizável no cadastro (add-user) — o mesmo código ativa quantos
dispositivos ele precisar no Claude Desktop, sem exigir um cadastro por TI a cada
dispositivo novo.

Uso típico:
  # Criar usuário (gera client_code reutilizável)
  concilium auth add-user --id bruno --role operator

  # Regenerar o client_code do usuário (ex: vazamento do código original)
  concilium auth regenerate-code --user bruno

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
        "operator", "--role", "-r", help="Role RBAC: operator | engineer | admin | auditor | catalog-manager"
    ),
    notes: str = typer.Option("", "--notes", help="Observações opcionais."),
    email: str | None = typer.Option(None, "--email", "-e", help="Email do usuário para notificações (ADR-123)."),
) -> None:
    """Registra um novo usuário/cliente no auth store.

    Roles disponíveis:
      operator       — leitura + criar projetos + executar pipeline + dados financeiros
      engineer       — operator + aprovar versões + escrever catálogo
      admin          — acesso completo incluindo gestão de usuários
      auditor        — leitura + dados financeiros (sem executar)
      catalog-manager — especialista em catálogo (sem acesso a projetos de clientes)

    Sempre gera um client_code reutilizável de bootstrap — o mesmo código serve
    para ativar quantos dispositivos o usuário precisar (Claude Desktop em casa,
    no trabalho, etc.), sem depender do admin/TI para cadastrar cada um.

    Se --email for fornecido, o claude_desktop_config.json pronto é enviado por
    email automaticamente (ADR-123 F2).
    """
    import json as _json

    from concilium.infrastructure.auth.auth_store import get_auth_store
    from concilium.infrastructure.services.notification_service import get_notification_service

    store = get_auth_store()
    generated = secret is None
    if generated:
        secret = secrets.token_urlsafe(32)
    client_code = "RCODE-" + secrets.token_hex(16).upper()

    try:
        record = store.add_client(client_id, secret, [role], notes, email=email or "", client_code=client_code)
    except ValueError as e:
        rprint(f"[red]Erro:[/red] {e}")
        raise typer.Exit(1) from e

    rprint(f"[green]✓ Usuário '{record.client_id}' criado.[/green]")
    rprint(f"  Role    : {', '.join(record.roles)}")
    if generated:
        rprint("\n[yellow]Secret gerado (guarde agora — não será exibido de novo):[/yellow]")
        rprint(f"  [bold]{secret}[/bold]")
    rprint("\n[yellow]Client code gerado (guarde agora — não será exibido de novo):[/yellow]")
    rprint(f"  [bold]{client_code}[/bold]")

    config_block = {
        "mcpServers": {
            "concilium": {
                "command": "concilium-mcp-proxy",
                "env": {
                    "CONCILIUM_CLIENT_CODE": client_code,
                    "CONCILIUM_SERVER_URL": "https://mcp.mendesloboconstrucao.com.br",
                },
            }
        }
    }
    config_json = _json.dumps(config_block, indent=2, ensure_ascii=False)

    if email:
        get_notification_service().notify_user_created(
            client_id=client_id,
            role=role,
            email=email,
            config_json=config_json,
        )
        rprint(f"\n[green]✓ Email de boas-vindas enviado para {email}[/green]")
    else:
        rprint("\n[bold]Cole em claude_desktop_config.json:[/bold]")
        rprint("[dim]macOS: ~/Library/Application Support/Claude/claude_desktop_config.json[/dim]")
        rprint("[dim]Win:   %APPDATA%\\Claude\\claude_desktop_config.json[/dim]\n")
        typer.echo(config_json)


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


@app.command("regenerate-code")
def regenerate_code(
    user: str = typer.Option(..., "--user", "-u", help="client_id do usuário."),
    show_config: bool = typer.Option(
        True, "--config/--no-config", help="Exibir bloco JSON para claude_desktop_config."
    ),
) -> None:
    """Gera um novo client_code para o usuário (invalida o anterior).

    O client_code é reutilizável em quantos dispositivos o usuário precisar —
    não é necessário gerar um código por dispositivo. Use este comando apenas
    se o usuário perdeu o código original ou se ele vazou e precisa ser trocado.
    """
    import json as _json

    from concilium.infrastructure.auth.auth_store import get_auth_store

    store = get_auth_store()
    client_code = store.regenerate_client_code(user)
    if client_code is None:
        rprint(f"[red]Erro:[/red] usuário '{user}' não encontrado.")
        raise typer.Exit(1)

    rprint(f"\n[green]✓ Client code regenerado para '{user}'[/green]")
    rprint(f"  Código  : [bold]{client_code}[/bold]")
    rprint("  [dim]Reutilizável em quantos dispositivos o usuário precisar.[/dim]")

    if show_config:
        config_block = {
            "mcpServers": {
                "concilium": {
                    "command": "concilium-mcp-proxy",
                    "env": {
                        "CONCILIUM_CLIENT_CODE": client_code,
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
