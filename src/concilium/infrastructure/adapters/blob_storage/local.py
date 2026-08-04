"""Implementação local (Filesystem) do BlobStoragePort (ADR-033 §D1)."""

from pathlib import Path
from typing import Any

from concilium.domain.repositories.blob_storage_port import BlobStoragePort


class LocalBlobStorage(BlobStoragePort):
    """Implementação de storage usando o Filesystem local.

    Usado primordialmente para testes, desenvolvimento, e como cache local
    quando operando com blobs em nuvem no futuro.
    """

    def __init__(self, root_dir: Path | str):
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, path: str) -> Path:
        """Resolve o caminho absoluto impedindo path traversal fora do root."""
        # Remove barras iniciais para evitar que sejam tratados como caminhos absolutos no root do disco
        safe_path = str(path).lstrip("/")
        resolved = (self.root_dir / safe_path).resolve()
        if not str(resolved).startswith(str(self.root_dir.resolve())):
            raise ValueError(f"Acesso negado: o path '{path}' aponta para fora do diretório raiz do storage.")
        return resolved

    def ler_blob(self, path: str) -> bytes:
        p = self._resolve_path(path)
        if not p.exists():
            raise FileNotFoundError(f"Blob não encontrado: {path}")
        if not p.is_file():
            raise IsADirectoryError(f"Caminho aponta para um diretório, não um blob: {path}")
        return p.read_bytes()

    def gravar_blob(self, path: str, content: bytes) -> None:
        p = self._resolve_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)

    def listar_blobs(self, prefix: str) -> list[str]:
        # Para o LocalBlobStorage, prefixo pode ser interpretado como um subdiretório
        # ou como o início de um nome de arquivo. Simplificamos tratando como uma busca recursiva
        # se apontar para um diretório, ou filtragem de prefixo na pasta pai.
        safe_prefix = str(prefix).lstrip("/")
        base_path = self.root_dir / safe_prefix

        if base_path.is_dir():
            # Retorna todos os arquivos dentro do diretório, de forma recursiva
            return [str(f.relative_to(self.root_dir)).replace("\\", "/") for f in base_path.rglob("*") if f.is_file()]

        # Se não for diretório, procuramos no diretório pai por arquivos que iniciem com o prefixo
        parent_dir = base_path.parent
        if not parent_dir.exists():
            return []

        file_prefix = base_path.name
        return [
            str(f.relative_to(self.root_dir)).replace("\\", "/")
            for f in parent_dir.rglob("*")
            if f.is_file() and f.name.startswith(file_prefix)
        ]

    def blob_existe(self, path: str) -> bool:
        try:
            p = self._resolve_path(path)
            return p.exists() and p.is_file()
        except ValueError:
            return False

    def health_check(self) -> dict[str, Any]:
        return {
            "status": "ok" if self.root_dir.exists() else "error",
            "backend": "filesystem",
            "root": str(self.root_dir),
        }

    def deletar_blob(self, path: str) -> None:
        """Remove o arquivo do disco. Sem-op se já não existir (base permite omitir)."""
        p = self._resolve_path(path)
        if p.exists():
            p.unlink()

    def aprovar_versao(self, path: str) -> None:
        """Torna o blob somente-leitura (chmod 444) — equivalente local ao checkin SharePoint."""
        import stat as _stat

        p = self._resolve_path(path)
        if p.exists():
            p.chmod(p.stat().st_mode & ~(_stat.S_IWUSR | _stat.S_IWGRP | _stat.S_IWOTH))
