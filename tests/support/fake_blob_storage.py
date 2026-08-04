"""Double compartilhado de BlobStoragePort para testes — sem filesystem/cloud.

Promovido do `MemoryBlobStorage` que vivia inline em
`tests/unit/infrastructure/storage/test_storage_project_repo2.py` para uso
compartilhado por qualquer teste que precise de um BlobStoragePort em memória
(escopo/plano, snapshots, migração entre backends, etc.).
"""

from __future__ import annotations

from concilium.domain.repositories.blob_storage_port import BlobStoragePort


class FakeBlobStorage(BlobStoragePort):
    """In-memory dict-backed double implementando BlobStoragePort."""

    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}
        self._approved: set[str] = set()

    def ler_blob(self, path: str) -> bytes:
        if path not in self._data:
            raise FileNotFoundError(f"Blob not found: {path}")
        return self._data[path]

    def gravar_blob(self, path: str, content: bytes) -> None:
        self._data[path] = content

    def listar_blobs(self, prefix: str) -> list[str]:
        return [k for k in self._data if k.startswith(prefix)]

    def blob_existe(self, path: str) -> bool:
        return path in self._data

    def deletar_blob(self, path: str) -> None:
        if path not in self._data:
            raise FileNotFoundError(f"Blob not found: {path}")
        del self._data[path]
        self._approved.discard(path)

    def aprovar_versao(self, path: str) -> None:
        self._approved.add(path)

    def is_approved(self, path: str) -> bool:
        """Helper só de teste (fora de BlobStoragePort) para asserir `aprovar_versao`."""
        return path in self._approved
