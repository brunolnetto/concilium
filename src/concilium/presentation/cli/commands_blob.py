"""CLI para operações de blob storage — migração entre backends.

Comandos:
    concilium ops blob migrate   — copia blobs de source para target
    concilium ops blob status    — lista blobs e estatísticas do backend atual
    concilium ops blob put       — envia um arquivo local para o blob storage
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from rich import print as rprint

if TYPE_CHECKING:
    from concilium.domain.repositories.blob_storage_port import BlobStoragePort

blob_app = typer.Typer(
    name="blob",
    help="Operações de blob storage: migração entre backends (ADR-047).",
    no_args_is_help=True,
)

_BACKEND_HELP = "Backend: filesystem | azure_blob | sharepoint | s3 | gdrive. Padrão: CONCILIUM__STORE_BACKEND."


def _make_storage(backend: str, root: str = "", *, system: bool = False) -> BlobStoragePort:
    """Instancia um BlobStoragePort a partir do tipo de backend explícito.

    Se *backend* for vazio, cai no comportamento padrão (CONCILIUM__STORE_BACKEND).
    Credenciais são sempre lidas das env vars padrão do lado correspondente
    (CONCILIUM__SP_*, CONCILIUM__AZURE_*, CONCILIUM__S3_* …).

    system=True usa o Drive de sistema (auth/distribuição) em vez do Drive de
    projetos — só tem efeito com backend vazio (padrão) ou "sharepoint".
    """
    from concilium.infrastructure.storage.store_factory import (
        _BACKEND_ALIASES,
        build_blob_storage,
        build_system_blob_storage,
    )

    if not backend:
        if system:
            return build_system_blob_storage(root_override=Path(root) if root else None)
        return build_blob_storage(root_override=Path(root) if root else None)

    canonical = _BACKEND_ALIASES.get(backend.strip().lower(), backend.strip().lower())

    if canonical == "filesystem":
        from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage

        return LocalBlobStorage(root_dir=Path(root) if root else Path("."))
    if canonical == "sharepoint":
        from concilium.infrastructure.adapters.blob_storage.sharepoint import SharePointBlobStorage

        return SharePointBlobStorage.from_env(system=system)
    if canonical in ("azure", "azure_blob"):
        from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

        return AzureBlobStorage.from_env()
    if canonical == "s3":
        from concilium.infrastructure.adapters.blob_storage.s3 import S3BlobStorage

        return S3BlobStorage.from_env()
    if canonical == "gdrive":
        from concilium.infrastructure.adapters.blob_storage.gdrive import GoogleDriveBlobStorage

        return GoogleDriveBlobStorage.from_env()
    raise typer.BadParameter(
        f"Backend desconhecido: '{backend}'. Valores válidos: filesystem, azure_blob, sharepoint, s3, gdrive.",
        param_hint="--source-backend / --target-backend",
    )


@blob_app.command("migrate")
def migrate(
    source_backend: Annotated[str, typer.Option("--source-backend", "-s", help=_BACKEND_HELP)] = "",
    source_root: Annotated[str, typer.Option("--source-root", help="Diretório raiz (apenas backend filesystem).")] = "",
    target_backend: Annotated[str, typer.Option("--target-backend", "-t", help=_BACKEND_HELP)] = "",
    target_root: Annotated[str, typer.Option("--target-root", help="Diretório raiz (apenas backend filesystem).")] = "",
    prefix: Annotated[str, typer.Option(help="Prefixo de blobs a migrar. Vazio = todos.")] = "",
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Lista blobs sem copiar.")] = False,
    no_overwrite: Annotated[bool, typer.Option("--no-overwrite", help="Pula blobs já existentes no target.")] = False,
    log_interval: Annotated[int, typer.Option(help="Log de progresso a cada N blobs.")] = 50,
    workers: Annotated[int, typer.Option("--workers", "-w", help="Threads paralelas de upload (default: 1).")] = 1,
) -> None:
    """Migra blobs entre dois backends de storage.

    Cada lado (source/target) é configurado independentemente via --source-backend
    e --target-backend. Credenciais vêm das variáveis de ambiente locais do
    respectivo backend — o comando pode ser executado de qualquer máquina, fora
    do container de hospedagem.

    Exemplos:

        # Filesystem local → SharePoint (credenciais SP setadas localmente):
        concilium ops blob migrate \\
            --source-backend filesystem --source-root ./backup \\
            --target-backend sharepoint

        # SharePoint → Azure Blob:
        concilium ops blob migrate \\
            --source-backend sharepoint \\
            --target-backend azure_blob

        # Dry-run de um prefixo específico:
        concilium ops blob migrate \\
            --source-backend filesystem --source-root ./data \\
            --target-backend sharepoint \\
            --prefix projetos/ --dry-run
    """
    from concilium.infrastructure.adapters.blob_storage.migrator import BlobMigrator

    source = _make_storage(source_backend, source_root)
    target = _make_storage(target_backend, target_root)

    if dry_run:
        rprint("[bold yellow]▶ Modo dry-run — nenhum blob será copiado[/bold yellow]")

    rprint(f"[bold cyan]▶ Iniciando migração (prefix='{prefix or '*'}')[/bold cyan]")

    def on_progress(path: str, n: int, total: int) -> None:
        if n % 10 == 0 or n == total:
            rprint(f"  [dim]{n}/{total}[/dim] {path}")

    result = BlobMigrator(log_interval=log_interval, workers=workers).migrate(
        source=source,
        target=target,
        prefix=prefix,
        dry_run=dry_run,
        overwrite=not no_overwrite,
        on_progress=on_progress,
    )

    color = "green" if result.success else "red"
    rprint(f"\n[bold {color}]{'DRY-RUN ' if dry_run else ''}Migração concluída[/bold {color}]")
    rprint(f"  Total blobs:  {result.total_blobs}")
    if not dry_run:
        rprint(f"  Copiados:     [green]{result.copied}[/green]")
        rprint(f"  Pulados:      [yellow]{result.skipped}[/yellow]")
        rprint(
            f"  Falhas:       [{'red' if result.failed else 'dim'}]{result.failed}"
            f"[/{'red' if result.failed else 'dim'}]"
        )

    if result.failed > 0:
        raise typer.Exit(1)


@blob_app.command("put")
def put(
    local_path: Annotated[Path, typer.Argument(help="Arquivo local a enviar.")],
    blob_path: Annotated[str, typer.Argument(help="Caminho/chave de destino no blob storage.")],
    backend: Annotated[str, typer.Option("--backend", "-b", help=_BACKEND_HELP)] = "",
    root: Annotated[str, typer.Option("--root", help="Diretório raiz (apenas backend filesystem).")] = "",
    system: Annotated[
        bool,
        typer.Option("--system", help="Usa o Drive de sistema (auth/distribuição) em vez do Drive de projetos."),
    ] = False,
) -> None:
    """Envia um arquivo local para o blob storage (ex.: publicar o proxy .exe)."""
    storage = _make_storage(backend, root, system=system)
    storage.gravar_blob(blob_path, local_path.read_bytes())
    rprint(f"[bold green]✓[/bold green] {local_path} → {blob_path}")


@blob_app.command("status")
def status(
    backend: Annotated[str, typer.Option("--backend", "-b", help=_BACKEND_HELP)] = "",
    root: Annotated[str, typer.Option("--root", help="Diretório raiz (apenas backend filesystem).")] = "",
    prefix: Annotated[str, typer.Option(help="Prefixo a listar. Vazio = todos.")] = "",
) -> None:
    """Lista blobs e estatísticas de um backend de storage."""
    storage = _make_storage(backend, root)
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
