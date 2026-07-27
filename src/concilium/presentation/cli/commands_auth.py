"""concilium auth — gestão de usuários e dispositivos.

Comandos de administrador para o sistema de autenticação. Cada usuário recebe um
client_code reutilizável no cadastro (add-user) — o mesmo código ativa quantos
dispositivos ele precisar no Claude Desktop, sem exigir um cadastro por TI a cada
dispositivo novo.

Uso típico (nested sob "ops" — ver ops_app.add_typer(auth_app) em presentation/main.py):
  # Criar usuário (gera client_code reutilizável)
  concilium ops auth add-user --id bruno --role operator

  # Atualizar role/email/notes de um usuário existente
  concilium ops auth update-user --id bruno --role admin

  # Criar/atualizar em lote a partir de um CSV (colunas: action,id,role,email,notes,secret)
  concilium ops auth batch --file usuarios.csv --dry-run
  concilium ops auth batch --file usuarios.csv

  # Regenerar o client_code do usuário (ex: vazamento do código original)
  concilium ops auth regenerate-code --user bruno

  # Migrar em lote usuários cadastrados antes do client_code existir
  concilium ops auth migrate-legacy-codes

  # Listar dispositivos ativos
  concilium ops auth list-devices

  # Listar sessões MCP recentes de um dispositivo
  concilium ops auth list-sessions --device macbook-bruno

  # Revogar acesso de um dispositivo
  concilium ops auth revoke-device --device macbook-bruno

  # Remover usuário (soft-delete — client_id continua resolvível em owner_id/audit trails)
  concilium ops auth remove-user --id bruno

  # Remover E apagar PII (direito de ser esquecido, LGPD Art. 18)
  concilium ops auth remove-user --id bruno --forget
  concilium ops auth forget-user --id bruno  # para um usuário já removido antes
"""

from __future__ import annotations

import csv
import secrets
from typing import TYPE_CHECKING, NamedTuple

import typer
from rich import print as rprint
from rich.table import Table

if TYPE_CHECKING:
    from concilium.infrastructure.auth.auth_store import ClientRecord

app = typer.Typer(
    name="auth",
    help="Gestão de usuários, dispositivos e tokens JWT.",
    no_args_is_help=True,
)

_MCP_SERVER_URL = "https://mcp.mendesloboconstrucao.com.br"

_WINDOWS_INSTALL_PATH = r"C:\Concilium\concilium-mcp-proxy.exe"
_UNIX_INSTALL_PATH = "$HOME/.concilium/bin/concilium-mcp-proxy"

# Publicados pela workflow build-proxy.yml (PyInstaller, um build nativo por SO) —
# não há PyPI/wheel publicado para instalação via pip em máquinas de usuário final.
_PROXY_EXE_BLOB_PATHS = {
    "windows": "distribuicao/concilium-mcp-proxy.exe",
    "linux": "distribuicao/concilium-mcp-proxy-linux",
    "macos": "distribuicao/concilium-mcp-proxy-macos",
}


def _get_proxy_exe_download_urls(ttl_segundos: int = 7 * 24 * 3600) -> dict[str, str | None]:
    """Gera links de download temporário dos executáveis do proxy (um por SO).

    scope="organization": o destinatário (funcionário com conta no tenant
    MendesLobo) só precisa estar logado no M365 para abrir o link — não expõe o
    arquivo publicamente. Diferente de scope="anonymous" (default do backend),
    que depende de compartilhamento externo estar habilitado no site do
    SharePoint — confirmado em produção que está desabilitado (ADR-135 §D3.1).
    "organization" funciona hoje sem nenhuma mudança de configuração do site.

    Retorna {"windows": url, "linux": url, "macos": url} — cada valor é None se o
    backend não suportar URL assinada (ex.: filesystem local em dev), tratado pelo
    chamador (cai no texto de fallback assumindo instalação via pip).
    """
    from concilium.infrastructure.storage.store_factory import build_system_blob_storage

    storage = build_system_blob_storage()
    return {
        platform: storage.gerar_url_temporaria(blob_path, ttl_segundos=ttl_segundos, scope="organization")
        for platform, blob_path in _PROXY_EXE_BLOB_PATHS.items()
    }


def _warn_if_no_download_urls(proxy_download_urls: dict[str, str | None]) -> None:
    """Avisa o admin no terminal quando nenhum link de download pôde ser gerado.

    O executável do proxy só chega ao usuário pelo link assinado (não há mais
    fallback de anexo — ver `notifications._distribution_attachments`); se os
    3 SOs vierem None (backend sem suporte, ou Graph createLink falhando —
    já aconteceu em produção, ADR-135), o email de boas-vindas ainda é enviado
    com sucesso, mas sem nenhuma instrução de onde obter o executável. Sem
    este aviso, isso passa desapercebido (o comando só reporta "✓ enviado").
    """
    if not any(proxy_download_urls.values()):
        rprint(
            "\n[yellow]⚠ Nenhum link de download do executável do proxy foi gerado "
            "(backend de storage sem suporte a URL assinada, ou falha ao gerar — veja os "
            "logs do servidor). O email de boas-vindas será enviado sem o link de download; "
            "entregue o executável ao usuário por outro meio.[/yellow]"
        )


def _build_mcp_config_block(client_code: str, platform: str) -> dict:
    """Monta o bloco claude_desktop_config.json — "command" varia por plataforma.

    Windows e Unix apontam para o executável standalone (PyInstaller) num caminho
    fixo local — o usuário baixa o binário (link enviado por email) e salva nesse
    caminho. Isso evita depender do pacote Python/PATH estar instalado na máquina do
    usuário final, já que não há PyPI/wheel publicado para `concilium`.

    No Unix, "command" não expande "$HOME" sozinho (não passa por um shell) — por
    isso usamos "sh -c" para forçar a expansão, análogo ao "cmd /c" usado no Windows
    para outros fins (aqui não é sobre PATH, é sobre variável de ambiente).
    """
    entry: dict = {}
    if platform == "windows":
        entry["command"] = _WINDOWS_INSTALL_PATH
    else:
        entry["command"] = "sh"
        entry["args"] = ["-c", _UNIX_INSTALL_PATH]
    entry["env"] = {
        "CONCILIUM_CLIENT_CODE": client_code,
        "CONCILIUM_SERVER_URL": _MCP_SERVER_URL,
    }
    return {"mcpServers": {"concilium": entry}}


def _build_mcp_config_jsons(client_code: str) -> tuple[str, str]:
    """Retorna (config_json_unix, config_json_windows) — o admin nunca escolhe

    plataforma na hora do cadastro (não sabe o SO do dispositivo final com
    certeza), então sempre geramos os dois e deixamos o usuário decidir qual usar.
    """
    import json as _json

    unix_json = _json.dumps(_build_mcp_config_block(client_code, "unix"), indent=2, ensure_ascii=False)
    windows_json = _json.dumps(_build_mcp_config_block(client_code, "windows"), indent=2, ensure_ascii=False)
    return unix_json, windows_json


def _print_both_configs(config_json_unix: str, config_json_windows: str) -> None:
    rprint("\n[bold]macOS/Linux:[/bold]")
    typer.echo(config_json_unix)
    rprint("\n[bold]Windows:[/bold]")
    typer.echo(config_json_windows)


# ── Usuários ──────────────────────────────────────────────────────────────────


def _do_add_user(
    client_id: str, secret: str, role: str | list[str], notes: str, email: str
) -> tuple[ClientRecord, str]:
    """Cria 1 usuário. Retorna (record, client_code). Raises ValueError se já existir.

    Núcleo compartilhado por add-user (singular) e batch — mantém a geração de
    client_code e a chamada ao store num único lugar. `role` aceita uma string
    (uso do batch, 1 role por linha de CSV) ou uma lista (add-user, --role repetível).
    """
    from concilium.infrastructure.auth.auth_store import get_auth_store

    store = get_auth_store()
    roles = [role] if isinstance(role, str) else list(role)
    client_code = "RCODE-" + secrets.token_hex(16).upper()
    record = store.add_client(client_id, secret, roles, notes, email=email or "", client_code=client_code)
    return record, client_code


def _do_update_user(client_id: str, role: str | None, email: str | None, notes: str | None) -> ClientRecord:
    """Atualiza 1 usuário. Raises ValueError se não existir ou role for inválido.

    Núcleo compartilhado por update-user (singular) e batch.
    """
    from concilium.infrastructure.auth.auth_store import get_auth_store

    store = get_auth_store()
    return store.update_client(client_id, roles=[role] if role is not None else None, email=email, notes=notes)


def _describe_update_user_changes(
    existing: ClientRecord, role: str | None, email: str | None, notes: str | None
) -> dict[str, str]:
    """Resume em texto o que muda em `existing` — usado só para o email de aviso."""
    changes: dict[str, str] = {}
    if role is not None and [role] != existing.roles:
        changes["role"] = f"{'/'.join(existing.roles)} → {role}"
    if email is not None and email != existing.email:
        changes["email"] = "atualizado"
    if notes is not None and notes != existing.notes:
        changes["notes"] = "atualizado"
    return changes


def _print_update_user_result(record: ClientRecord) -> None:
    rprint(f"[green]✓ Usuário '{record.client_id}' atualizado.[/green]")
    rprint(f"  Role    : {', '.join(record.roles)}")
    if record.email:
        rprint(f"  Email   : {record.email}")
    if record.notes:
        rprint(f"  Notas   : {record.notes}")


def _resolve_update_user_target(
    client_id: str, role: str | None, email: str | None, notes: str | None
) -> ClientRecord:
    """Valida os argumentos de update-user e resolve o registro existente.

    Raises typer.Exit(1) se nenhum campo foi informado ou o usuário não existe.
    """
    from concilium.infrastructure.auth.auth_store import get_auth_store

    if role is None and email is None and notes is None:
        rprint("[red]Erro:[/red] informe ao menos --role, --email ou --notes.")
        raise typer.Exit(1)

    store = get_auth_store()
    existing = store.get_client(client_id)
    if existing is None:
        rprint(f"[red]Erro:[/red] usuário '{client_id}' não encontrado. Use add-user para criar.")
        raise typer.Exit(1)
    if not existing.active:
        rprint(f"[yellow]Aviso:[/yellow] '{client_id}' está inativo/removido — atualizando mesmo assim.")
    return existing


@app.command("add-user")
def add_user(
    client_id: str = typer.Option(..., "--id", "-i", help="ID do cliente/usuário."),
    secret: str | None = typer.Option(None, "--secret", "-s", help="Secret. Gerado automaticamente se omitido."),
    role: list[str] = typer.Option(
        ["operator"],
        "--role",
        "-r",
        help="Role RBAC: operator | engineer | admin | auditor | catalog-manager (repita --role para múltiplas)",
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

    Um usuário pode ter mais de uma role — repita --role (ex.: --role engineer
    --role catalog-manager).

    Sempre gera um client_code reutilizável de bootstrap — o mesmo código serve
    para ativar quantos dispositivos o usuário precisar (Claude Desktop em casa,
    no trabalho, etc.), sem depender do admin/TI para cadastrar cada um.

    Se --email for fornecido, o claude_desktop_config.json pronto é enviado por
    email automaticamente (ADR-123 F2).
    """
    from concilium.application.services.notifications import notify_user_created

    generated = secret is None
    if secret is None:
        secret = secrets.token_urlsafe(32)

    try:
        record, client_code = _do_add_user(client_id, secret, role, notes, email or "")
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

    config_json_unix, config_json_windows = _build_mcp_config_jsons(client_code)

    if email:
        proxy_download_urls = _get_proxy_exe_download_urls()
        _warn_if_no_download_urls(proxy_download_urls)
        sent = notify_user_created(
            client_id=client_id,
            role=", ".join(role),
            email=email,
            config_json_unix=config_json_unix,
            config_json_windows=config_json_windows,
            proxy_download_urls=proxy_download_urls,
        )
        if sent:
            rprint(f"\n[green]✓ Email de boas-vindas enviado para {email}[/green]")
        else:
            rprint(
                f"\n[red]✗ Falha ao enviar o email de boas-vindas para {email}[/red] "
                "[yellow](veja os logs do servidor para o motivo) — entregue o client_code manualmente:[/yellow]"
            )
            _print_both_configs(config_json_unix, config_json_windows)
    else:
        rprint("\n[bold]Cole em claude_desktop_config.json (use o bloco do seu sistema):[/bold]")
        rprint("[dim]macOS: ~/Library/Application Support/Claude/claude_desktop_config.json[/dim]")
        rprint("[dim]Win:   %APPDATA%\\Claude\\claude_desktop_config.json[/dim]")
        _print_both_configs(config_json_unix, config_json_windows)


@app.command("update-user")
def update_user(
    client_id: str = typer.Option(..., "--id", "-i", help="ID do cliente/usuário a atualizar."),
    role: str | None = typer.Option(
        None, "--role", "-r", help="Nova role: operator | engineer | admin | auditor | catalog-manager"
    ),
    email: str | None = typer.Option(None, "--email", "-e", help="Novo email."),
    notes: str | None = typer.Option(None, "--notes", help="Novas observações."),
) -> None:
    """Atualiza role/email/notes de um usuário existente (para criar, use add-user)."""
    from concilium.application.services.notifications import notify_user_edited

    existing = _resolve_update_user_target(client_id, role, email, notes)
    changes = _describe_update_user_changes(existing, role, email, notes)

    try:
        record = _do_update_user(client_id, role, email, notes)
    except ValueError as e:
        rprint(f"[red]Erro:[/red] {e}")
        raise typer.Exit(1) from e

    _print_update_user_result(record)

    if changes and record.email:
        if not notify_user_edited(client_id, record.email, changes):
            rprint(f"[red]✗ Falha ao enviar email de aviso para {record.email}[/red]")


class _BatchRow(NamedTuple):
    """Uma linha do CSV de `batch`, já normalizada (strip/lower nos campos textuais)."""

    action: str
    client_id: str
    role_cell: str  # "" = nao informado (relevante so pra update)
    email_cell: str
    notes_cell: str
    secret_cell: str
    role_for_add: str  # add sempre tem role (default operator, como add-user)
    role_to_validate: str


def _parse_batch_row(row: dict[str, str]) -> _BatchRow:
    action = (row.get("action") or "").strip().lower()
    client_id = (row.get("id") or "").strip()
    role_cell = (row.get("role") or "").strip()
    email_cell = (row.get("email") or "").strip()
    notes_cell = (row.get("notes") or "").strip()
    secret_cell = (row.get("secret") or "").strip()
    role_for_add = role_cell or "operator"
    role_to_validate = role_for_add if action == "add" else role_cell
    return _BatchRow(action, client_id, role_cell, email_cell, notes_cell, secret_cell, role_for_add, role_to_validate)


def _batch_role_invalid(role_to_validate: str, valid_roles: frozenset[str]) -> bool:
    return bool(role_to_validate) and role_to_validate not in valid_roles


def _batch_update_missing_fields(parsed: _BatchRow) -> bool:
    if parsed.action != "update":
        return False
    return not (parsed.role_cell or parsed.email_cell or parsed.notes_cell)


def _validate_batch_row(parsed: _BatchRow, valid_roles: frozenset[str]) -> tuple[str, str, str] | None:
    """Retorna (action_display, client_id_display, detalhe) se a linha for inválida, senão None."""
    if parsed.action not in ("add", "update"):
        return parsed.action or "(vazio)", parsed.client_id or "(vazio)", "action inválida"
    if not parsed.client_id:
        return parsed.action, "(vazio)", "id obrigatório"
    if _batch_role_invalid(parsed.role_to_validate, valid_roles):
        return parsed.action, parsed.client_id, f"role inválida: {parsed.role_to_validate}"
    if _batch_update_missing_fields(parsed):
        return parsed.action, parsed.client_id, "nenhum campo pra atualizar"
    return None


def _dry_run_batch_row(store, parsed: _BatchRow) -> tuple[bool, str, str]:
    """Retorna (ok, status_markup, detalhe) sem gravar nada no store."""
    exists = store.get_client(parsed.client_id) is not None
    if parsed.action == "add":
        detalhe = "já existe (falharia)" if exists else f"criaria com role={parsed.role_for_add}"
        status = "[red]✗[/red]" if exists else "[green]✓[/green]"
    else:
        detalhe = f"atualizaria role={parsed.role_cell or '—'}" if exists else "não existe (falharia)"
        status = "[green]✓[/green]" if exists else "[red]✗[/red]"
    ok = (parsed.action == "add" and not exists) or (parsed.action == "update" and exists)
    return ok, status, detalhe


def _apply_batch_row(parsed: _BatchRow) -> str:
    """Executa o add/update de fato. Retorna o texto de detalhe. Raises ValueError se falhar."""
    if parsed.action == "add":
        used_secret = parsed.secret_cell or secrets.token_urlsafe(32)
        _record, client_code = _do_add_user(
            parsed.client_id, used_secret, parsed.role_for_add, parsed.notes_cell, parsed.email_cell
        )
        detalhe = f"code={client_code}"
        if not parsed.secret_cell:
            detalhe += f", secret gerado={used_secret}"
        return detalhe
    _do_update_user(parsed.client_id, parsed.role_cell or None, parsed.email_cell or None, parsed.notes_cell or None)
    return "atualizado"


def _read_batch_csv(file: str) -> list[dict[str, str]]:
    """Lê o CSV de `batch`. Raises typer.Exit(1) se o arquivo não puder ser aberto."""
    try:
        with open(file, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except OSError as e:
        rprint(f"[red]Erro:[/red] não foi possível ler '{file}': {e}")
        raise typer.Exit(1) from e


@app.command("batch")
def batch(
    file: str = typer.Option(..., "--file", "-f", help="CSV com colunas: action,id,role,email,notes,secret."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Valida e mostra o que seria feito, sem escrever nada."),
) -> None:
    """Cria/atualiza usuários em lote a partir de um CSV.

    Colunas: action (add|update), id, role, email, notes, secret (opcional, só
    para action=add — gerado automaticamente se vazio).

    Cada linha é processada de forma independente — um erro numa linha não
    aborta as demais. Ao final, uma tabela resume o resultado por linha e o
    comando sai com código 1 se alguma linha falhou.
    """
    from concilium.infrastructure.auth.permission_guard import VALID_ROLES

    rows = _read_batch_csv(file)

    from concilium.infrastructure.auth.auth_store import get_auth_store

    store = get_auth_store()
    table = Table(title="Batch — usuários" + (" (dry-run)" if dry_run else ""), show_header=True)
    table.add_column("Linha", justify="right")
    table.add_column("Ação")
    table.add_column("ID", style="cyan")
    table.add_column("Status")
    table.add_column("Detalhe", style="dim")

    n_ok = 0
    n_failed = 0
    for i, row in enumerate(rows, start=2):  # linha 1 = header
        parsed = _parse_batch_row(row)

        invalid = _validate_batch_row(parsed, VALID_ROLES)
        if invalid is not None:
            action_display, client_id_display, detalhe = invalid
            table.add_row(str(i), action_display, client_id_display, "[red]✗[/red]", detalhe)
            n_failed += 1
            continue

        if dry_run:
            ok_row, status, detalhe = _dry_run_batch_row(store, parsed)
            n_ok += 1 if ok_row else 0
            n_failed += 0 if ok_row else 1
            table.add_row(str(i), parsed.action, parsed.client_id, status, detalhe)
            continue

        try:
            detalhe = _apply_batch_row(parsed)
        except ValueError as e:
            table.add_row(str(i), parsed.action, parsed.client_id, "[red]✗[/red]", str(e))
            n_failed += 1
            continue

        table.add_row(str(i), parsed.action, parsed.client_id, "[green]✓[/green]", detalhe)
        n_ok += 1

    rprint(table)
    rprint(f"\n{n_ok} ok, {n_failed} falharam.")
    if n_failed:
        raise typer.Exit(1)


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


def _check_owned_projects(client_id: str, reassign_to: str | None, force: bool, force_yes: bool) -> None:
    """ADR-126 D7/F7: bloqueia remove-user se o client é dono de projetos.

    - Sem projetos possuídos: no-op, comportamento idêntico ao anterior ao ADR-126.
    - Com projetos e sem --reassign-to/--force: bloqueia, listando os projetos.
    - --reassign-to <owner_id>: transfere ownership (forçado, D4.1) para cada
      projeto e só então permite a remoção.
    - --force: permite a remoção mesmo assim, deixando owner_id órfão — exige
      confirmação explícita adicional (--force-yes ou prompt interativo).
    """
    if reassign_to is not None and reassign_to == client_id:
        rprint(
            f"[red]✗ --reassign-to não pode ser o mesmo client sendo removido ('{client_id}'). "
            "Isso deixaria owner_id inalterado e os projetos órfãos após a remoção — "
            "equivalente a --force, mas silenciosamente. Use --force explicitamente se essa "
            "é a intenção, ou informe um owner_id diferente.[/red]"
        )
        raise typer.Exit(code=1)

    from concilium.application.services.project._ownership_helpers import (
        find_projects_by_owner,
        transfer_ownership_forced,
    )
    from concilium.application.services.project.audit_service import AuditService
    from concilium.presentation.cli.shared import project_repository

    repo = project_repository()
    owned = find_projects_by_owner(repo, client_id)
    if not owned:
        return

    project_ids = ", ".join(p.meta.get("id", "?") for p in owned)

    if reassign_to:
        audit = AuditService()
        for project in owned:
            transfer_ownership_forced(project, reassign_to, actor=f"cli:remove-user:{client_id}", audit=audit)
        rprint(f"[green]✓ {len(owned)} projeto(s) transferido(s) para '{reassign_to}': {project_ids}.[/green]")
        return

    if force:
        if not force_yes:
            typer.confirm(
                f"'{client_id}' é owner de {len(owned)} projeto(s) ({project_ids}). "
                "Remover mesmo assim deixará owner_id órfão. Confirma?",
                abort=True,
            )
        rprint(
            f"[yellow]⚠ Removendo '{client_id}' com projetos órfãos (owner_id não reatribuído): {project_ids}.[/yellow]"
        )
        return

    rprint(f"[red]✗ '{client_id}' é owner de {len(owned)} projeto(s): {project_ids}.[/red]")
    rprint(
        "  Use --reassign-to <owner_id> para transferir antes de remover, ou --force para remover mesmo assim\n"
        "  (projetos ficarão com owner_id órfão até reatribuição manual)."
    )
    raise typer.Exit(1)


def _revoke_all_devices(store, client_id: str) -> int:
    """Revoga todos os dispositivos do client. revoke_device() espera device_id, não

    client_id — chamar com client_id revogaria por coincidência qualquer dispositivo
    de QUALQUER usuário cujo device_id colida com este client_id. Retorna a
    quantidade de dispositivos revogados.
    """
    devices = store.list_devices(client_id=client_id)
    for d in devices:
        store.revoke_device(d.device_id)
    return len(devices)


def _forget_pii(store, client_id: str) -> None:
    """Direito de ser esquecido: redige PII do ClientRecord, anonimiza o audit log

    de invocações MCP, E varre audit trails de projeto/catálogo trocando
    `client_id` por um alias opaco e estável (gerado uma vez aqui — não é
    persistido em lugar nenhum do sistema, para não recriar o vínculo que
    acabamos de apagar). `client_id` do ClientRecord em si é preservado (é a
    chave primária do registro, já inativo e sem PII) — o que muda é toda
    REFERÊNCIA a ele em owner_id/criado_por/actor/aprovado_por.

    O alias é impresso uma única vez no terminal — se precisar correlacionar
    entradas anonimizadas a este esquecimento no futuro (ex.: investigação),
    guarde-o fora do sistema (ex.: ticket de compliance) no momento em que
    este comando roda.
    """
    import secrets

    from concilium.application.services.project._pii_sweep import sweep_all_projects, sweep_catalog_version_files
    from concilium.infrastructure.settings import get_storage
    from concilium.infrastructure.storage.store_factory import get_tool_invocation_store
    from concilium.presentation.cli.shared import project_repository

    store.forget_client(client_id)
    # get_tool_invocation_repository() (singleton em memória de processo) não serve aqui:
    # a CLI roda num processo separado do servidor MCP, que é quem chama
    # reset_tool_invocation_repository(get_tool_invocation_store()) no startup (server.py).
    # Sem ir direto ao store_factory, a CLI apagaria de um buffer InMemory vazio e
    # nunca tocaria os dados reais persistidos pelo servidor.
    n_invocations = get_tool_invocation_store().delete_by_user(client_id)

    alias = f"forgotten-{secrets.token_hex(8)}"
    project_stats = sweep_all_projects(project_repository(), client_id, alias)
    n_catalog_files = sweep_catalog_version_files(get_storage().config_root, client_id, alias)

    rprint(
        f"[green]✓ PII de '{client_id}' apagada (email, notas, credenciais) e "
        f"{n_invocations} registro(s) de invocação MCP anonimizado(s).[/green]"
    )
    rprint(
        f"[green]✓ Audit trails anonimizados (alias '{alias}'): "
        f"{project_stats['audit_log_entries']} entrada(s) de audit_log em "
        f"{project_stats['projects_affected']}/{project_stats['projects_scanned']} projeto(s), "
        f"{project_stats['meta_fields']} campo(s) de meta.json, "
        f"{n_catalog_files} arquivo(s) de versão de catálogo.[/green]"
    )
    rprint(
        "[dim]Guarde o alias acima fora do sistema se precisar correlacionar "
        "estas entradas a este esquecimento no futuro — não fica registrado em nenhum lugar.[/dim]"
    )


def _confirm_remove_user(client_id: str, forget: bool, yes: bool) -> None:
    confirm_msg = f"Remover usuário '{client_id}' e revogar todos os seus dispositivos?"
    if forget:
        confirm_msg = (
            f"Remover usuário '{client_id}', revogar todos os seus dispositivos E apagar "
            "permanentemente sua PII (email, notas, credenciais, histórico de invocações)? "
            "Esta ação NÃO PODE ser desfeita."
        )
    if not yes:
        typer.confirm(confirm_msg, abort=True)


def _notify_remove_user_result(client_id: str, existing: ClientRecord | None) -> None:
    from concilium.application.services.notifications import notify_user_removed

    if existing and existing.email:
        if not notify_user_removed(client_id, existing.email):
            rprint(f"[red]✗ Falha ao enviar email de confirmação para {existing.email}[/red]")
    else:
        rprint("[dim]Usuário sem email cadastrado — nenhuma notificação enviada.[/dim]")


@app.command("remove-user")
def remove_user(
    client_id: str = typer.Option(..., "--id", "-i", help="ID do cliente a remover."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirmar sem prompt."),
    forget: bool = typer.Option(
        False,
        "--forget",
        help="Direito de ser esquecido (LGPD Art. 18): além de desativar, apaga PII "
        "(email, notas, credenciais) e anonimiza o audit log de invocações MCP. "
        "Irreversível — para um usuário já removido antes, use 'forget-user'.",
    ),
    reassign_to: str | None = typer.Option(
        None,
        "--reassign-to",
        help="ADR-126 D7: transfere ownership dos projetos possuídos para este owner_id antes de remover.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="ADR-126 D7: remove mesmo sendo owner de projetos (ficam órfãos). Exige confirmação extra.",
    ),
    force_yes: bool = typer.Option(
        False, "--force-yes", help="Confirma automaticamente o --force (sem prompt), para uso não-interativo."
    ),
) -> None:
    """Desativa um usuário no auth store (soft-delete) e revoga todos os seus dispositivos.

    ADR-126 D7/F7: se o usuário é owner de projetos, a remoção é bloqueada por
    padrão — use --reassign-to para transferir ownership antes, ou --force para
    remover mesmo assim (deixa owner_id órfão).

    O usuário permanece no store (inativo) — client_id continua resolvível para
    quem já o referencia (ownership, audit trails). Use --forget para também
    apagar a PII (direito de ser esquecido, LGPD Art. 18).
    """
    from concilium.infrastructure.auth.auth_store import get_auth_store

    _check_owned_projects(client_id, reassign_to, force, force_yes)
    _confirm_remove_user(client_id, forget, yes)

    store = get_auth_store()
    # Captura o email antes da remoção/esquecimento — --forget apaga o campo email do registro.
    existing = next((r for r in store.list_clients() if r.client_id == client_id), None)

    _revoke_all_devices(store, client_id)

    removed = store.remove_client(client_id)
    if not removed:
        rprint(f"[yellow]Usuário '{client_id}' não encontrado (ou já inativo) no store local.[/yellow]")
        if forget:
            rprint("[dim]Para apagar a PII de um usuário já removido, use 'forget-user'.[/dim]")
        return

    rprint(f"[green]✓ Usuário '{client_id}' removido. Dispositivos revogados.[/green]")
    _notify_remove_user_result(client_id, existing)

    if forget:
        _forget_pii(store, client_id)


@app.command("forget-user")
def forget_user(
    client_id: str = typer.Option(..., "--id", "-i", help="ID do cliente a esquecer."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirmar sem prompt."),
) -> None:
    """Direito de ser esquecido (LGPD Art. 18) para um usuário já removido (ou ainda ativo).

    Complementar a 'remove-user --forget': existe separado para o caso comum de o
    pedido de esquecimento chegar depois da desativação (ex.: usuário já foi
    removido semanas atrás, jurídico só agora formalizou o pedido de exclusão de
    dados) — não é preciso reprocessar reassign-to/força de ownership de novo, só
    apagar a PII que ainda resta. Se o usuário ainda estiver ativo, desativa e
    revoga dispositivos como parte da mesma operação, antes de apagar a PII.

    NÃO apaga client_id nem referências a ele em owner_id/audit trails de projeto e
    catálogo — essas permanecem como identificador pseudonimizado (LGPD Art. 16).
    """
    from concilium.infrastructure.auth.auth_store import get_auth_store

    store = get_auth_store()
    existing = next((r for r in store.list_clients() if r.client_id == client_id), None)
    if existing is None:
        rprint(f"[red]Erro:[/red] usuário '{client_id}' não encontrado.")
        raise typer.Exit(1)

    if not yes:
        typer.confirm(
            f"Apagar permanentemente a PII de '{client_id}' (email, notas, credenciais, "
            "histórico de invocações)? Esta ação NÃO PODE ser desfeita.",
            abort=True,
        )

    if existing.active:
        _revoke_all_devices(store, client_id)
        store.remove_client(client_id)

    _forget_pii(store, client_id)


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
    from concilium.application.services.notifications import notify_user_edited
    from concilium.infrastructure.auth.auth_store import get_auth_store

    store = get_auth_store()
    client_code = store.regenerate_client_code(user)
    if client_code is None:
        rprint(f"[red]Erro:[/red] usuário '{user}' não encontrado.")
        raise typer.Exit(1)

    existing = next((r for r in store.list_clients() if r.client_id == user), None)
    if existing and existing.email:
        if not notify_user_edited(user, existing.email, {"client_code": "regenerado"}):
            rprint(f"[red]✗ Falha ao enviar email de aviso para {existing.email}[/red]")

    if show_config:
        config_json_unix, config_json_windows = _build_mcp_config_jsons(client_code)

        rprint("\n[bold]Envie ao usuário — colar em claude_desktop_config.json (use o bloco do seu sistema):[/bold]")
        rprint("[dim]macOS: ~/Library/Application Support/Claude/claude_desktop_config.json[/dim]")
        rprint("[dim]Win:   %APPDATA%\\Claude\\claude_desktop_config.json[/dim]")
        _print_both_configs(config_json_unix, config_json_windows)
    else:
        typer.echo(client_code)


@app.command("migrate-legacy-codes")
def migrate_legacy_codes() -> None:
    """Gera client_code para todo usuário ativo que não tem um (migração em lote).

    Usuários cadastrados antes do bootstrap por client_code (ADR-099) nunca
    conseguem ativar um dispositivo novo — activate_device_code() sempre rejeita,
    pois não há hash pra comparar. Rode este comando UMA VEZ após atualizar o
    servidor para corrigir todos de uma vez, em vez de esperar cada usuário
    reportar o problema e rodar 'regenerate-code' individualmente.

    Usuários com email cadastrado recebem os dois configs (macOS/Linux e Windows)
    por email automaticamente (ADR-123) — o próprio usuário escolhe o certo.
    Usuários sem email ficam listados no terminal (também os dois formatos) para
    envio manual.
    """
    from concilium.application.services.notifications import notify_client_code_migrated
    from concilium.infrastructure.auth.auth_store import get_auth_store

    store = get_auth_store()
    migrated = store.migrate_legacy_client_codes()

    if not migrated:
        rprint("[green]Nenhum usuário pendente — todos já têm client_code.[/green]")
        return

    rprint(f"[green]✓ {len(migrated)} usuário(s) migrado(s):[/green]\n")

    proxy_download_urls = _get_proxy_exe_download_urls()
    _warn_if_no_download_urls(proxy_download_urls)
    manual: list[tuple[str, str]] = []
    for client_id, client_code, email in migrated:
        config_json_unix, config_json_windows = _build_mcp_config_jsons(client_code)
        if email:
            sent = notify_client_code_migrated(
                client_id,
                email,
                config_json_unix,
                config_json_windows,
                proxy_download_urls,
            )
            if sent:
                rprint(f"  [cyan]{client_id}[/cyan] — email enviado para {email}")
            else:
                manual.append((client_id, client_code))
                rprint(f"  [red]{client_id}[/red] — falha ao enviar email para {email}, entregar manualmente")
        else:
            manual.append((client_id, client_code))
            rprint(f"  [yellow]{client_id}[/yellow] — sem email cadastrado, entregar manualmente")

    if manual:
        rprint("\n[bold]Entrega manual (sem email cadastrado ou falha no envio):[/bold]")
        for client_id, client_code in manual:
            config_json_unix, config_json_windows = _build_mcp_config_jsons(client_code)
            rprint(f"\n  [cyan]{client_id}[/cyan]:")
            _print_both_configs(config_json_unix, config_json_windows)


@app.command("list-devices")
def list_devices(
    user: str | None = typer.Option(None, "--user", "-u", help="Filtrar por client_id."),
) -> None:
    """Lista dispositivos ativos (refresh tokens não revogados e não expirados).

    A coluna "Roles" reflete o snapshot gravado na ativação do dispositivo —
    pode ficar desatualizada em relação ao role atual do usuário até o próximo
    refresh automático do proxy (que sempre resolve a partir do ClientRecord
    atual, ver POST /auth/token/refresh).
    """
    from concilium.infrastructure.auth.auth_store import get_auth_store

    devices = get_auth_store().list_devices(client_id=user)
    if not devices:
        rprint("[dim]Nenhum dispositivo ativo.[/dim]")
        return

    table = Table(title="Dispositivos ativos", show_header=True)
    table.add_column("Device ID", style="cyan")
    table.add_column("Usuário")
    table.add_column("Roles")
    table.add_column("Emitido em")
    table.add_column("Expira em")
    table.add_column("Último uso")

    for d in devices:
        table.add_row(
            d.device_id,
            d.client_id,
            ", ".join(d.roles),
            d.issued_at[:10],
            d.expires_at[:10],
            d.last_used_at[:10] if d.last_used_at else "—",
        )

    rprint(table)


@app.command("list-sessions")
def list_sessions(
    device: str = typer.Option(..., "--device", "-d", help="Device ID."),
) -> None:
    """Lista sessões MCP recentes de um dispositivo (ADR-138).

    Uma sessão é uma conexão streamable-http/SSE — derivada do audit log de
    invocações de tool (não é um registro à parte). Requer que o audit log
    ainda contenha as invocações da sessão (ver limites do backend de audit).
    """
    from concilium.application.tool_invocations.sessions import sessions_for_device

    sessions = sessions_for_device(device)
    if not sessions:
        rprint("[dim]Nenhuma sessão encontrada para este dispositivo.[/dim]")
        return

    table = Table(title=f"Sessões MCP — {device}", show_header=True)
    table.add_column("Session ID", style="cyan")
    table.add_column("Usuário")
    table.add_column("Iniciada em")
    table.add_column("Última atividade")
    table.add_column("Chamadas", justify="right")

    for s in sessions:
        table.add_row(
            s.session_id,
            s.user_id or "—",
            s.started_at[:19],
            s.last_activity_at[:19],
            str(s.call_count),
        )

    rprint(table)


@app.command("revoke-device")
def revoke_device(
    device: str = typer.Option(..., "--device", "-d", help="Device ID a revogar."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirmar sem prompt."),
) -> None:
    """Revoga todos os refresh tokens de um dispositivo."""
    from concilium.application.services.notifications import notify_device_revoked_admin
    from concilium.infrastructure.auth.auth_store import get_auth_store

    if not yes:
        typer.confirm(f"Revogar acesso do dispositivo '{device}'?", abort=True)

    store = get_auth_store()
    # Captura o client_id do dispositivo antes de revogar, com o MESMO critério
    # de revoke_device() (not revoked, ignora expiração) — list_devices() filtra
    # também por expiração e podia "perder" o dono de um token expirado-mas-não-
    # revogado que revoke_device() ainda revoga normalmente.
    owner_client_id = store.find_device_client_id(device)

    count = store.revoke_device(device)
    if count:
        rprint(f"[green]✓ {count} token(s) revogado(s) para '{device}'.[/green]")
        if owner_client_id:
            client = next((r for r in store.list_clients() if r.client_id == owner_client_id), None)
            if client and client.email:
                notify_device_revoked_admin(client.client_id, device, client.email)
    else:
        rprint(f"[yellow]Nenhum token ativo encontrado para '{device}'.[/yellow]")
