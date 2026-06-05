"""Snapshots imutáveis das Camadas 0-3 identificados por hash de conteúdo."""

import hashlib
import json
from pathlib import Path
from typing import Any


class SnapshotStore:
    """Armazena snapshots como arquivos JSON identificados por hash SHA-256.

    Snapshot nunca é editado após criação. Deduplicação automática:
    mesmo conteúdo gera mesmo hash e reusa o arquivo existente.
    """

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def compute_hash(content: dict | list) -> str:
        """Hash determinístico do conteúdo. Sort keys garante reprodutibilidade."""
        serialized = json.dumps(content, sort_keys=True, default=str).encode()
        return hashlib.sha256(serialized).hexdigest()

    def store(self, kind: str, content: dict | list) -> str:
        """Persiste snapshot, retorna o hash. Reusa arquivo existente se hash coincide."""
        h = self.compute_hash(content)
        path = self.root / f"{kind}-{h[:7]}.json"
        if not path.exists():
            path.write_text(json.dumps(content, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
        return h[:7]  # short hash para legibilidade nos paths

    def load(self, kind: str, short_hash: str) -> Any:
        """Carrega snapshot pelo hash curto."""
        path = self.root / f"{kind}-{short_hash}.json"
        if not path.exists():
            raise FileNotFoundError(f"Snapshot não encontrado: {path}")
        return json.loads(path.read_text(encoding="utf-8"))
