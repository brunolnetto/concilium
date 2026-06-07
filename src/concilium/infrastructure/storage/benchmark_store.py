"""Adapter: FileSystemBenchmarkStore — persistência em filesystem."""

import json
from datetime import datetime
from pathlib import Path

from concilium.domain.benchmark.models import (
    BenchmarkExecution,
    BenchmarkMetadata,
)
from concilium.domain.benchmark.repository import BenchmarkRepositoryPort


class FileSystemBenchmarkStore(BenchmarkRepositoryPort):
    """Implementação concrete usando filesystem + JSON."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._metadata_dir = self.root / "metadata"
        self._metadata_dir.mkdir(exist_ok=True)
        self._audit_log = self.root / "audit.jsonl"

    def save_metadata(self, metadata: BenchmarkMetadata) -> None:
        """Salva BenchmarkMetadata como JSON."""
        if metadata.imutavel:
            # Se já foi imutável, não sobrescreve
            existing = self.get_metadata_by_version(metadata.benchmark_id, metadata.versao)
            if existing and existing.imutavel:
                raise PermissionError(f"Benchmark {metadata.benchmark_id} v{metadata.versao} é imutável.")

        filename = f"{metadata.benchmark_id}-v{metadata.versao}.json"
        path = self._metadata_dir / filename
        path.write_text(
            json.dumps(self._to_dict(metadata), indent=2, default=str),
            encoding="utf-8",
        )

    def get_metadata(self, benchmark_id: str) -> BenchmarkMetadata | None:
        """Carrega versão mais recente."""
        versions = list(self._metadata_dir.glob(f"{benchmark_id}-v*.json"))
        if not versions:
            return None
        latest = sorted(versions, key=lambda p: int(p.stem.split("-v")[1]))[-1]
        return self._from_dict(json.loads(latest.read_text()))

    def get_metadata_by_version(self, benchmark_id: str, version: int) -> BenchmarkMetadata | None:
        """Carrega versão específica."""
        path = self._metadata_dir / f"{benchmark_id}-v{version}.json"
        if not path.exists():
            return None
        return self._from_dict(json.loads(path.read_text()))

    def list_all(self) -> list[BenchmarkMetadata]:
        """Versões mais recentes de todos os benchmarks."""
        seen = set()
        result = []
        for path in sorted(self._metadata_dir.glob("*-v*.json"), reverse=True):
            bid = path.stem.split("-v")[0]
            if bid not in seen:
                result.append(self._from_dict(json.loads(path.read_text())))
                seen.add(bid)
        return result

    def log_execution(self, execution: BenchmarkExecution) -> None:
        """Append-only audit log JSONL."""
        with self._audit_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(self._exec_to_dict(execution), default=str) + "\n")

    def get_execution_history(self, benchmark_id: str, limit: int = 50) -> list[BenchmarkExecution]:
        """Últimas N execuções."""
        if not self._audit_log.exists():
            return []
        lines = self._audit_log.read_text().strip().split("\n")
        execs = [self._exec_from_dict(json.loads(line)) for line in lines if line]
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
