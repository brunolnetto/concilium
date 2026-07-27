"""CLI para operações de blob storage — migração entre backends.

Comandos:
    concilium ops blob migrate       — copia blobs de source para target
    concilium ops blob status        — lista blobs e estatísticas do backend atual
    concilium ops blob put           — envia um arquivo local para o blob storage
    concilium ops blob put-versioned — publica versionado (vN + ponteiro "latest")
    concilium ops blob delete        — remove um blob/pasta (recursivo, irreversível na prática)
"""

from __future__ import annotations

import re
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


def _make_storage_default_backend(root: str, *, system: bool) -> BlobStoragePort:
    """Backend vazio: cai no comportamento padrão (CONCILIUM__STORE_BACKEND)."""
    from concilium.infrastructure.storage.store_factory import build_blob_storage, build_system_blob_storage

    if system:
        return build_system_blob_storage(root_override=Path(root) if root else None)
    return build_blob_storage(root_override=Path(root) if root else None)


def _make_storage_filesystem(root: str) -> BlobStoragePort:
    from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage

    return LocalBlobStorage(root_dir=Path(root) if root else Path("."))


def _make_storage_sharepoint(*, system: bool) -> BlobStoragePort:
    from concilium.infrastructure.adapters.blob_storage.sharepoint import SharePointBlobStorage

    return SharePointBlobStorage.from_env(system=system)


def _make_storage_azure() -> BlobStoragePort:
    from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

    return AzureBlobStorage.from_env()


def _make_storage_s3() -> BlobStoragePort:
    from concilium.infrastructure.adapters.blob_storage.s3 import S3BlobStorage

    return S3BlobStorage.from_env()


def _make_storage_gdrive() -> BlobStoragePort:
    from concilium.infrastructure.adapters.blob_storage.gdrive import GoogleDriveBlobStorage

    return GoogleDriveBlobStorage.from_env()


def _make_storage(backend: str, root: str = "", *, system: bool = False) -> BlobStoragePort:
    """Instancia um BlobStoragePort a partir do tipo de backend explícito.

    Se *backend* for vazio, cai no comportamento padrão (CONCILIUM__STORE_BACKEND).
    Credenciais são sempre lidas das env vars padrão do lado correspondente
    (CONCILIUM__SP_*, CONCILIUM__AZURE_*, CONCILIUM__S3_* …).

    system=True usa o Drive de sistema (auth/distribuição) em vez do Drive de
    projetos — só tem efeito com backend vazio (padrão) ou "sharepoint".
    """
    from concilium.infrastructure.storage.store_factory import _BACKEND_ALIASES

    if not backend:
        return _make_storage_default_backend(root, system=system)

    canonical = _BACKEND_ALIASES.get(backend.strip().lower(), backend.strip().lower())
    if canonical == "azure_blob":
        canonical = "azure"

    factories = {
        "filesystem": lambda: _make_storage_filesystem(root),
        "sharepoint": lambda: _make_storage_sharepoint(system=system),
        "azure": _make_storage_azure,
        "s3": _make_storage_s3,
        "gdrive": _make_storage_gdrive,
    }
    factory = factories.get(canonical)
    if factory is None:
        raise typer.BadParameter(
            f"Backend desconhecido: '{backend}'. Valores válidos: filesystem, azure_blob, sharepoint, s3, gdrive.",
            param_hint="--source-backend / --target-backend",
        )
    return factory()


@blob_app.command("migrate")
def migrate(
    source_backend: Annotated[str, typer.Option("--source-backend", "-s", help=_BACKEND_HELP)] = "",
    source_root: Annotated[str, typer.Option("--source-root", help="Diretório raiz (apenas backend filesystem).")] = "",
    source_system: Annotated[
        bool, typer.Option("--source-system", help="Lado source usa o Drive de sistema (auth/distribuição).")
    ] = False,
    target_backend: Annotated[str, typer.Option("--target-backend", "-t", help=_BACKEND_HELP)] = "",
    target_root: Annotated[str, typer.Option("--target-root", help="Diretório raiz (apenas backend filesystem).")] = "",
    target_system: Annotated[
        bool, typer.Option("--target-system", help="Lado target usa o Drive de sistema (auth/distribuição).")
    ] = False,
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

        # Drive de projetos → Drive de sistema, mesmo backend (ADR-135 D3):
        concilium ops blob migrate \\
            --source-backend sharepoint \\
            --target-backend sharepoint --target-system \\
            --prefix auth/
    """
    from concilium.infrastructure.adapters.blob_storage.migrator import BlobMigrator

    source = _make_storage(source_backend, source_root, system=source_system)
    target = _make_storage(target_backend, target_root, system=target_system)

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


@blob_app.command("put-versioned")
def put_versioned(
    local_path: Annotated[Path, typer.Argument(help="Arquivo local a enviar.")],
    prefix: Annotated[
        str, typer.Argument(help="Pasta de destino no blob storage (ex.: distribuicao/concilium-mcp-proxy).")
    ],
    latest_name: Annotated[
        str, typer.Option("--latest-name", help="Nome do ponteiro estável sobrescrito a cada publish.")
    ] = "latest",
    backend: Annotated[str, typer.Option("--backend", "-b", help=_BACKEND_HELP)] = "",
    root: Annotated[str, typer.Option("--root", help="Diretório raiz (apenas backend filesystem).")] = "",
    system: Annotated[
        bool,
        typer.Option("--system", help="Usa o Drive de sistema (auth/distribuição) em vez do Drive de projetos."),
    ] = False,
) -> None:
    """Publica um artefato versionado (ex.: o .mcpb do proxy — ADR-161 F3).

    Grava dois blobs: `<prefix>/vN<ext>` (imutável, N sequencial — mesma convenção
    vN de `ConfigVersionService`/ADR-062, adaptada aqui para blob storage) e
    `<prefix>/<latest_name><ext>` (ponteiro estável, sobrescrito a cada publish —
    é este path que deve ser usado para gerar o link fixo de download).

    N é calculado a partir dos blobs `vN<ext>` já existentes no prefixo — nunca
    sobrescreve uma versão anterior.
    """
    storage = _make_storage(backend, root, system=system)
    ext = local_path.suffix
    clean_prefix = prefix.rstrip("/")
    existing = storage.listar_blobs(f"{clean_prefix}/")
    version_re = re.compile(rf"^{re.escape(clean_prefix)}/v(\d+){re.escape(ext)}$")
    versions = [int(m.group(1)) for b in existing if (m := version_re.match(b))]
    next_version = max(versions, default=0) + 1

    content = local_path.read_bytes()
    versioned_path = f"{clean_prefix}/v{next_version}{ext}"
    latest_path = f"{clean_prefix}/{latest_name}{ext}"

    storage.gravar_blob(versioned_path, content)
    storage.gravar_blob(latest_path, content)
    rprint(f"[bold green]✓[/bold green] {local_path} → {versioned_path} (versão {next_version})")
    rprint(f"[bold green]✓[/bold green] {local_path} → {latest_path} (ponteiro estável)")


@blob_app.command("delete")
def delete(
    path: Annotated[str, typer.Argument(help="Caminho/prefixo (pasta) a remover, recursivo.")],
    backend: Annotated[str, typer.Option("--backend", "-b", help=_BACKEND_HELP)] = "",
    root: Annotated[str, typer.Option("--root", help="Diretório raiz (apenas backend filesystem).")] = "",
    system: Annotated[
        bool, typer.Option("--system", help="Usa o Drive de sistema em vez do Drive de projetos.")
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Confirmar sem prompt interativo.")] = False,
) -> None:
    """Remove um blob ou pasta (recursivo) do blob storage.

    Irreversível na prática: no backend SharePoint cai na lixeira do site
    (retenção padrão ~93 dias), mas não trate isso como plano de recuperação.
    """
    storage = _make_storage(backend, root, system=system)
    if not yes:
        typer.confirm(f"Remover '{path}' permanentemente do storage?", abort=True)
    try:
        storage.deletar_blob(path)
    except FileNotFoundError as e:
        rprint(f"[red]Erro:[/red] {e}")
        raise typer.Exit(1) from e
    rprint(f"[bold green]✓[/bold green] Removido: {path}")


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
