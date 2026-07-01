"""BlobMigrator — migração entre backends de storage (ADR-047 extensão).

Copia blobs de um BlobStoragePort (source) para outro (target) de forma
idempotente, com suporte a dry-run, prefix filter, overwrite control,
progress callback e uploads paralelos via ThreadPoolExecutor.

Uso:
    from concilium.infrastructure.adapters.blob_storage.migrator import BlobMigrator

    result = BlobMigrator(workers=8).migrate(source, target, prefix="projetos/")
    print(f"Migrados: {result.copied}/{result.total_blobs}")
"""

from __future__ import annotations

import dataclasses
import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from concilium.domain.repositories.blob_storage_port import BlobStoragePort

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class MigrationResult:
    """Resultado de uma operação de migração."""

    total_blobs: int = 0
    copied: int = 0
    skipped: int = 0
    failed: int = 0
    dry_run: bool = False

    @property
    def success(self) -> bool:
        return self.failed == 0


class BlobMigrator:
    """Migra blobs entre dois BlobStoragePort de forma idempotente.

    Args:
        log_interval: loga progresso a cada N blobs (default: 50)
        workers:      número de threads paralelas de upload (default: 1 — sequencial)
    """

    def __init__(self, log_interval: int = 50, workers: int = 1) -> None:
        self._log_interval = log_interval
        self._workers = max(1, workers)

    def migrate(
        self,
        source: BlobStoragePort,
        target: BlobStoragePort,
        prefix: str = "",
        dry_run: bool = False,
        overwrite: bool = True,
        on_progress: Callable[[str, int, int], None] | None = None,
    ) -> MigrationResult:
        """Copia todos os blobs de source para target.

        Args:
            source:      Storage de origem.
            target:      Storage de destino.
            prefix:      Filtro de prefixo — só migra blobs que começam com este valor.
            dry_run:     Se True, lista blobs sem copiar (simulação).
            overwrite:   Se False, pula blobs que já existem no target.
            on_progress: Callback(path, n_processado, total) chamado a cada blob.

        Returns:
            MigrationResult com estatísticas da operação.
        """
        blobs = sorted(source.listar_blobs(prefix))
        total = len(blobs)
        result = MigrationResult(total_blobs=total, dry_run=dry_run)

        logger.info(
            "Migração iniciada: %d blobs (prefix='%s', dry_run=%s, overwrite=%s, workers=%d)",
            total,
            prefix or "*",
            dry_run,
            overwrite,
            self._workers,
        )

        if dry_run:
            for n, blob_path in enumerate(blobs, start=1):
                if on_progress:
                    on_progress(blob_path, n, total)
                if n % self._log_interval == 0 or n == total:
                    logger.info("  %d/%d blobs processados", n, total)
        elif self._workers == 1:
            self._migrate_sequential(blobs, source, target, overwrite, on_progress, result)
        else:
            self._migrate_parallel(blobs, source, target, overwrite, on_progress, result, total)

        logger.info(
            "Migração concluída: copiados=%d, pulados=%d, falhas=%d (dry_run=%s)",
            result.copied,
            result.skipped,
            result.failed,
            dry_run,
        )
        return result

    def _migrate_sequential(
        self,
        blobs: list[str],
        source: BlobStoragePort,
        target: BlobStoragePort,
        overwrite: bool,
        on_progress: Callable[[str, int, int], None] | None,
        result: MigrationResult,
    ) -> None:
        total = len(blobs)
        for n, blob_path in enumerate(blobs, start=1):
            self._copy_one(blob_path, source, target, overwrite, result)
            if on_progress:
                on_progress(blob_path, n, total)
            if n % self._log_interval == 0 or n == total:
                logger.info("  %d/%d blobs processados", n, total)

    def _migrate_parallel(
        self,
        blobs: list[str],
        source: BlobStoragePort,
        target: BlobStoragePort,
        overwrite: bool,
        on_progress: Callable[[str, int, int], None] | None,
        result: MigrationResult,
        total: int,
    ) -> None:
        counter_lock = threading.Lock()
        done = [0]

        def _task(blob_path: str) -> str:
            self._copy_one(blob_path, source, target, overwrite, result, counter_lock)
            with counter_lock:
                done[0] += 1
                n = done[0]
            if on_progress:
                on_progress(blob_path, n, total)
            if n % self._log_interval == 0 or n == total:
                logger.info("  %d/%d blobs processados", n, total)
            return blob_path

        with ThreadPoolExecutor(max_workers=self._workers) as pool:
            futures = {pool.submit(_task, p): p for p in blobs}
            for fut in as_completed(futures):
                exc = fut.exception()
                if exc:
                    logger.error("Falha inesperada no worker: %s", exc, exc_info=exc)

    def _copy_one(
        self,
        blob_path: str,
        source: BlobStoragePort,
        target: BlobStoragePort,
        overwrite: bool,
        result: MigrationResult,
        lock: threading.Lock | None = None,
    ) -> None:
        try:
            if not overwrite and target.blob_existe(blob_path):
                self._inc(result, "skipped", lock)
            else:
                content = source.ler_blob(blob_path)
                target.gravar_blob(blob_path, content)
                self._inc(result, "copied", lock)
        except Exception as exc:
            self._inc(result, "failed", lock)
            logger.error("Falha ao migrar '%s': %s", blob_path, exc, exc_info=True)

    @staticmethod
    def _inc(result: MigrationResult, field: str, lock: threading.Lock | None) -> None:
        if lock:
            with lock:
                setattr(result, field, getattr(result, field) + 1)
        else:
            setattr(result, field, getattr(result, field) + 1)
