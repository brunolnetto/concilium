"""Checkpoint store para o pipeline de observabilidade — ADR-112 F2.

Persiste o estado de processamento Bronze → Silver por tipo de sinal,
permitindo fast-forward incremental ao retomar após interrupção.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass

from concilium.domain.repositories.blob_storage_port import BlobStoragePort


@dataclass
class Checkpoint:
    signal_type: str
    last_processed_path: str | None
    last_processed_ts: str | None
    records_processed: int


class CheckpointStore:
    """Leitura/escrita de checkpoints JSON no BlobStorage."""

    _PREFIX = "observability/checkpoints"

    def __init__(self, storage: BlobStoragePort):
        self._storage = storage

    def _path(self, signal_type: str) -> str:
        return f"{self._PREFIX}/{signal_type}.json"

    def load(self, signal_type: str) -> Checkpoint | None:
        try:
            raw = self._storage.ler_blob(self._path(signal_type))
            if not raw.strip():
                return None  # arquivo vazio = checkpoint deletado
            data = json.loads(raw.decode("utf-8"))
            return Checkpoint(**data)
        except FileNotFoundError:
            return None

    def save(self, checkpoint: Checkpoint) -> None:
        content = json.dumps(dataclasses.asdict(checkpoint), ensure_ascii=False, indent=2)
        self._storage.gravar_blob(self._path(checkpoint.signal_type), content.encode("utf-8"))

    def delete(self, signal_type: str) -> None:
        try:
            # BlobStoragePort não tem delete; sobrescreve com marcador de deleção
            # e load() trata empty como None
            self._storage.gravar_blob(self._path(signal_type), b"")
        except Exception:
            pass

    def load_all(self) -> list[Checkpoint]:
        paths = self._storage.listar_blobs(self._PREFIX)
        checkpoints = []
        for p in paths:
            try:
                raw = self._storage.ler_blob(p)
                if not raw.strip():
                    continue
                data = json.loads(raw.decode("utf-8"))
                checkpoints.append(Checkpoint(**data))
            except Exception:
                pass
        return checkpoints
