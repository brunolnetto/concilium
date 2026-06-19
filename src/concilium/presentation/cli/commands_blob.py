"""CLI para operações de blob storage — migração entre backends.

Comandos:
    concilium blob migrate   — copia blobs de source para target
    concilium blob status    — lista blobs e estatísticas do backend atual
"""

from __future__ import annotations

from typing import Annotated

import typer
from rich import print as rprint

blob_app = typer.Typer(
    name="blob",
    help="Operações de blob storage: migração entre backends (ADR-047).",
    no_args_is_help=True,
)


def _make_source_storage():
    """Instancia storage de origem (lê env vars de source)."""
    from concilium.infrastructure.storage.store_factory import build_blob_storage
    return build_blob_storage()


def _make_target_storage():
    """Instancia storage de destino (lê env vars de target).

    Em produção, trocar as env vars antes de chamar este comando:
        CONCILIUM__STORE_BACKEND=azure_blob
        CONCILIUM__AZURE_ACCOUNT=...
        CONCILIUM__AZURE_CONTAINER=...
    """
    from concilium.infrastructure.storage.store_factory import build_blob_storage
    return build_blob_storage()


@blob_app.command("migrate")
def migrate(
    prefix: Annotated[str, typer.Option(help="Prefixo de blobs a migrar. Vazio = todos.")] = "",
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Lista blobs sem copiar.")] = False,
    no_overwrite: Annotated[bool, typer.Option("--no-overwrite", help="Pula blobs já existentes no target.")] = False,
    log_interval: Annotated[int, typer.Option(help="Log de progresso a cada N blobs.")] = 50,
) -> None:
    """Migra blobs do storage de origem para o storage de destino.

    Usa as variáveis de ambiente CONCILIUM__STORE_BACKEND_SOURCE e
    CONCILIUM__STORE_BACKEND_TARGET (ou o backend padrão para ambos).

    Exemplo:
        # Migrar projetos/ de filesystem para Azure Blob:
        CONCILIUM__STORE_BACKEND=azure_blob \\
        CONCILIUM__AZURE_ACCOUNT=minha-conta \\
        CONCILIUM__AZURE_CONTAINER=prod \\
        concilium blob migrate --prefix projetos/
    """
    from concilium.infrastructure.adapters.blob_storage.migrator import BlobMigrator

    source = _make_source_storage()
    target = _make_target_storage()

    if dry_run:
        rprint("[bold yellow]▶ Modo dry-run — nenhum blob será copiado[/bold yellow]")

    rprint(f"[bold cyan]▶ Iniciando migração (prefix='{prefix or '*'}')[/bold cyan]")

    progress_log: list[str] = []

    def on_progress(path: str, n: int, total: int) -> None:
        if n % 10 == 0 or n == total:
            rprint(f"  [dim]{n}/{total}[/dim] {path}")

    result = BlobMigrator(log_interval=log_interval).migrate(
        source=source,
        target=target,
        prefix=prefix,
        dry_run=dry_run,
        overwrite=not no_overwrite,
        on_progress=on_progress,
    )

    color = "green" if result.success else "red"
    rprint(
        f"\n[bold {color}]{'DRY-RUN ' if dry_run else ''}Migração concluída[/bold {color}]"
    )
    rprint(f"  Total blobs:  {result.total_blobs}")
    if not dry_run:
        rprint(f"  Copiados:     [green]{result.copied}[/green]")
        rprint(f"  Pulados:      [yellow]{result.skipped}[/yellow]")
        rprint(f"  Falhas:       [{'red' if result.failed else 'dim'}]{result.failed}[/{'red' if result.failed else 'dim'}]")

    if result.failed > 0:
        raise typer.Exit(1)


@blob_app.command("status")
def status(
    prefix: Annotated[str, typer.Option(help="Prefixo a listar. Vazio = todos.")] = "",
) -> None:
    """Lista blobs e estatísticas do backend configurado."""
    storage = _make_source_storage()
    blobs = storage.listar_blobs(prefix)
    rprint(f"[bold]Backend:[/bold] {type(storage).__name__}")
    rprint(f"[bold]Prefix:[/bold] '{prefix or '*'}'")
    rprint(f"[bold]Total blobs:[/bold] {len(blobs)}")
    if blobs:
        rprint("\n[dim]Primeiros 20:[/dim]")
        for b in sorted(blobs)[:20]:
            rprint(f"  {b}")
        if len(blobs) > 20:
            rprint(f"  [dim]... e mais {len(blobs) - 20} blobs[/dim]")
