"""Registro da última promoção de deploy (ADR-144 D1).

Mesmo padrão de `infrastructure/observability/checkpoint_store.py` — leitura/
escrita de um blob JSON via `BlobStoragePort`. Só guarda a última promoção
(`deploy/latest.json`, sobrescrito a cada deploy), não um histórico completo:
`ping()` (D2/D3) só precisa comparar contra a mais recente para decidir se há
novidade a reportar ao `client_id` que chamou.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass

from concilium.domain.repositories.blob_storage_port import BlobStoragePort


@dataclass
class DeployLogEntry:
    image_tag: str
    api_revision: str
    mcp_revision: str
    promoted_at: str  # ISO-8601
    resumo: str


class DeployLogStore:
    """Leitura/escrita da última promoção de deploy no BlobStorage de sistema."""

    _PATH = "deploy/latest.json"

    def __init__(self, storage: BlobStoragePort) -> None:
        self._storage = storage

    def load_latest(self) -> DeployLogEntry | None:
        try:
            raw = self._storage.ler_blob(self._PATH)
            if not raw.strip():
                return None  # blob vazio (ex.: apagado) — mesmo tratamento do CheckpointStore
            data = json.loads(raw.decode("utf-8"))
            return DeployLogEntry(**data)
        except FileNotFoundError:
            return None

    def save_latest(self, entry: DeployLogEntry) -> None:
        content = json.dumps(dataclasses.asdict(entry), ensure_ascii=False, indent=2)
        self._storage.gravar_blob(self._PATH, content.encode("utf-8"))
