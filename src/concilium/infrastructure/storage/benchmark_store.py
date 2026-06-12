"""Adapter: FileSystemBenchmarkStore — persistência via BlobStoragePort."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from concilium.domain.benchmark.models import (
    BenchmarkExecution,
    BenchmarkMetadata,
)
from concilium.domain.benchmark.repository import BenchmarkRepositoryPort
from concilium.domain.repositories.blob_storage_port import BlobStoragePort


class FileSystemBenchmarkStore(BenchmarkRepositoryPort):
    """Implementação do BenchmarkRepositoryPort via BlobStoragePort.

    Compatível com qualquer backend configurado (filesystem, SharePoint, S3, etc.).
    """

    def __init__(
        self,
        storage: "BlobStoragePort | None" = None,
        prefix: str = ".nep039",
        *,
        root: "Path | None" = None,
    ) -> None:
        """
        Args:
            storage: Backend de armazenamento (BlobStoragePort).
            prefix:  Prefixo/diretório raiz para todos os blobs deste store.
            root:    [LEGADO] Path do diretório raiz (wraps LocalBlobStorage).
                     Use ``from_path()`` ou passe ``storage`` explicitamente.
        """
        if root is not None:
            # Backward-compat: FileSystemBenchmarkStore(root=some_path)
            # ``root`` is the store's own directory (e.g. .nep039/).
            # Create a LocalBlobStorage rooted at that dir with an empty prefix,
            # so metadata lives at <root>/metadata/ and audit at <root>/audit.jsonl.
            from concilium.infrastructure.adapters.local_blob_storage import LocalBlobStorage

            _storage = LocalBlobStorage(root_dir=root)
            self._storage = _storage
            self._prefix = ""  # empty: blobs are relative to root directly
            self._metadata_prefix = "metadata"
            self._audit_blob = "audit.jsonl"
            # For legacy compat, expose .root and derived paths
            self.root = root
            self._metadata_dir = root / "metadata"
            self._audit_log = root / "audit.jsonl"
            return

        if storage is None:
            raise TypeError("Forneça 'storage' (BlobStoragePort) ou 'root' (Path legado).")
        self._storage = storage
        self._prefix = prefix.strip("/")
        self._metadata_prefix = f"{self._prefix}/metadata"
        self._audit_blob = f"{self._prefix}/audit.jsonl"

    # ── Backward-compat classmethod ──────────────────────────────────────────

    @classmethod
    def from_path(cls, root: Path) -> "FileSystemBenchmarkStore":
        """Cria store usando LocalBlobStorage apontando para *root*.

        *root* é o diretório raiz do store (ex: ``.nep039/``).
        Os blobs são armazenados em ``root/metadata/`` e ``root/audit.jsonl``.
        """
        from concilium.infrastructure.adapters.local_blob_storage import LocalBlobStorage

        storage = LocalBlobStorage(root_dir=root)
        # Empty prefix: blobs live directly under root (metadata/, audit.jsonl)
        return cls(storage=storage, prefix="")

    # ── BenchmarkRepositoryPort implementation ───────────────────────────────

    def save_metadata(self, metadata: BenchmarkMetadata) -> None:
        """Salva BenchmarkMetadata como JSON."""
        if metadata.imutavel:
            # Se já foi imutável, não sobrescreve
            existing = self.get_metadata_by_version(metadata.benchmark_id, metadata.versao)
            if existing and existing.imutavel:
                raise PermissionError(f"Benchmark {metadata.benchmark_id} v{metadata.versao} é imutável.")

        filename = f"{metadata.benchmark_id}-v{metadata.versao}.json"
        blob_path = f"{self._metadata_prefix}/{filename}"
        content = json.dumps(self._to_dict(metadata), indent=2, default=str)
        self._storage.gravar_blob(blob_path, content.encode("utf-8"))

    def get_metadata(self, benchmark_id: str) -> BenchmarkMetadata | None:
        """Carrega versão mais recente."""
        all_blobs = self._storage.listar_blobs(self._metadata_prefix)
        prefix_strip = self._metadata_prefix + "/"
        matching = [
            b for b in all_blobs
            if b.removeprefix(prefix_strip).startswith(f"{benchmark_id}-v")
            and b.endswith(".json")
        ]
        if not matching:
            return None

        def _version_key(blob_path: str) -> int:
            name = blob_path.removeprefix(prefix_strip)
            # name like "benchmark_id-v3.json"
            try:
                return int(name.split("-v")[1].removesuffix(".json"))
            except (IndexError, ValueError):
                return 0

        latest = sorted(matching, key=_version_key)[-1]
        data = self._storage.ler_blob(latest)
        return self._from_dict(json.loads(data.decode("utf-8")))

    def get_metadata_by_version(self, benchmark_id: str, version: int) -> BenchmarkMetadata | None:
        """Carrega versão específica."""
        blob_path = f"{self._metadata_prefix}/{benchmark_id}-v{version}.json"
        if not self._storage.blob_existe(blob_path):
            return None
        data = self._storage.ler_blob(blob_path)
        return self._from_dict(json.loads(data.decode("utf-8")))

    def list_all(self) -> list[BenchmarkMetadata]:
        """Versões mais recentes de todos os benchmarks."""
        all_blobs = self._storage.listar_blobs(self._metadata_prefix)
        prefix_strip = self._metadata_prefix + "/"
        seen: dict[str, tuple[int, str]] = {}  # benchmark_id → (version, blob_path)

        for blob_path in all_blobs:
            name = blob_path.removeprefix(prefix_strip)
            if not name.endswith(".json") or "-v" not in name:
                continue
            try:
                parts = name.removesuffix(".json").split("-v")
                bid = parts[0]
                ver = int(parts[1])
            except (IndexError, ValueError):
                continue
            if bid not in seen or ver > seen[bid][0]:
                seen[bid] = (ver, blob_path)

        result = []
        for _bid, (_ver, blob_path) in sorted(seen.items()):
            try:
                data = self._storage.ler_blob(blob_path)
                result.append(self._from_dict(json.loads(data.decode("utf-8"))))
            except (FileNotFoundError, json.JSONDecodeError):
                continue
        return result

    def log_execution(self, execution: BenchmarkExecution) -> None:
        """Append-only audit log JSONL (read + append + rewrite)."""
        line = json.dumps(self._exec_to_dict(execution), default=str) + "\n"
        existing = b""
        try:
            existing = self._storage.ler_blob(self._audit_blob)
        except FileNotFoundError:
            pass
        self._storage.gravar_blob(self._audit_blob, existing + line.encode("utf-8"))

    def get_execution_history(self, benchmark_id: str, limit: int = 50) -> list[BenchmarkExecution]:
        """Últimas N execuções."""
        try:
            data = self._storage.ler_blob(self._audit_blob)
        except FileNotFoundError:
            return []
        lines = data.decode("utf-8").strip().split("\n")
        execs = [self._exec_from_dict(json.loads(line)) for line in lines if line.strip()]
        filtered = [e for e in execs if e.benchmark_id == benchmark_id]
        return filtered[-limit:]

    def create_new_version(self, benchmark_id: str, patch: dict) -> BenchmarkMetadata:
        """Editar gera v+1."""
        current = self.get_metadata(benchmark_id)
        if not current:
            raise ValueError(f"Benchmark {benchmark_id} não existe.")

        # Nova versão
        new_meta = BenchmarkMetadata(
            benchmark_id=current.benchmark_id,
            nome=patch.get("nome", current.nome),
            origem=patch.get("origem", current.origem),
            tags=patch.get("tags", current.tags),
            criado_em=current.criado_em,
            versao=current.versao + 1,
            imutavel=False,  # Nova versão começa mutável
        )
        self.save_metadata(new_meta)
        return new_meta

    def update_metadata(self, benchmark_id: str, patch: dict) -> None:
        """Atualiza metadados (validando imutabilidade)."""
        current = self.get_metadata(benchmark_id)
        if not current:
            raise ValueError(f"Benchmark {benchmark_id} não existe.")

        if current.imutavel:
            raise PermissionError(f"Benchmark {benchmark_id} é imutável. Use create_new_version() para editar.")

        # Atualiza in-place se mutável
        updated = BenchmarkMetadata(
            benchmark_id=current.benchmark_id,
            nome=patch.get("nome", current.nome),
            origem=patch.get("origem", current.origem),
            tags=patch.get("tags", current.tags),
            criado_em=current.criado_em,
            versao=current.versao,
            imutavel=current.imutavel,
        )
        self.save_metadata(updated)

    # ── Serialisation helpers ────────────────────────────────────────────────

    @staticmethod
    def _to_dict(m: BenchmarkMetadata) -> dict:
        return {
            "benchmark_id": m.benchmark_id,
            "nome": m.nome,
            "origem": m.origem,
            "tags": m.tags,
            "criado_em": m.criado_em.isoformat(),
            "versao": m.versao,
            "imutavel": m.imutavel,
        }

    @staticmethod
    def _from_dict(d: dict) -> BenchmarkMetadata:
        return BenchmarkMetadata(
            benchmark_id=d["benchmark_id"],
            nome=d["nome"],
            origem=d["origem"],
            tags=d["tags"],
            criado_em=datetime.fromisoformat(d["criado_em"]),
            versao=d["versao"],
            imutavel=d["imutavel"],
        )

    @staticmethod
    def _exec_to_dict(e: BenchmarkExecution) -> dict:
        return {
            "execution_id": e.execution_id,
            "benchmark_id": e.benchmark_id,
            "versao": e.versao,
            "projeto_id": e.projeto_id,
            "status": e.status,
            "executado_em": e.executado_em.isoformat(),
            "discrepancia_sumario": e.discrepancia_sumario,
        }

    @staticmethod
    def _exec_from_dict(d: dict) -> BenchmarkExecution:
        return BenchmarkExecution(
            execution_id=d["execution_id"],
            benchmark_id=d["benchmark_id"],
            versao=d["versao"],
            projeto_id=d["projeto_id"],
            status=d["status"],
            executado_em=datetime.fromisoformat(d["executado_em"]),
            discrepancia_sumario=d.get("discrepancia_sumario"),
        )
