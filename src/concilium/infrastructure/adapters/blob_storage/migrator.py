"""BlobMigrator — migração entre backends de storage (ADR-047 extensão).

Copia blobs de um BlobStoragePort (source) para outro (target) de forma
idempotente, com suporte a dry-run, prefix filter, overwrite control
e progress callback.

Uso:
    from concilium.infrastructure.adapters.blob_storage.migrator import BlobMigrator

    result = BlobMigrator().migrate(source, target, prefix="projetos/")
    print(f"Migrados: {result.copied}/{result.total_blobs}")
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable

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
    """

    def __init__(self, log_interval: int = 50) -> None:
        self._log_interval = log_interval

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
            "Migração iniciada: %d blobs (prefix='%s', dry_run=%s, overwrite=%s)",
            total,
            prefix or "*",
            dry_run,
            overwrite,
        )

        for n, blob_path in enumerate(blobs, start=1):
            try:
                if not dry_run:
                    if not overwrite and target.blob_existe(blob_path):
                        result.skipped += 1
                    else:
                        content = source.ler_blob(blob_path)
                        target.gravar_blob(blob_path, content)
                        result.copied += 1
                # dry_run: não copia, apenas conta

                if on_progress:
                    on_progress(blob_path, n, total)

                if n % self._log_interval == 0 or n == total:
                    logger.info("  %d/%d blobs processados", n, total)

            except Exception as exc:
                result.failed += 1
                logger.error("Falha ao migrar '%s': %s", blob_path, exc, exc_info=True)

        logger.info(
            "Migração concluída: copiados=%d, pulados=%d, falhas=%d (dry_run=%s)",
            result.copied,
            result.skipped,
            result.failed,
            dry_run,
        )
        return result
