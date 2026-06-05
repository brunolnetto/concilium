"""Port: BenchmarkRepository (Hexagonal Architecture)."""
from abc import ABC, abstractmethod

from concilium.domain.benchmark.models import (
    BenchmarkMetadata,
    BenchmarkExecution,
)


class BenchmarkRepositoryPort(ABC):
    """Define contrato para armazenamento de benchmarks."""

    @abstractmethod
    def save_metadata(self, metadata: BenchmarkMetadata) -> None:
        """Salva ou atualiza BenchmarkMetadata."""
        pass

    @abstractmethod
    def get_metadata(self, benchmark_id: str) -> BenchmarkMetadata | None:
        """Carrega versão atual de benchmark."""
        pass

    @abstractmethod
    def get_metadata_by_version(
        self, benchmark_id: str, version: int
    ) -> BenchmarkMetadata | None:
        """Carrega versão específica de benchmark."""
        pass

    @abstractmethod
    def list_all(self) -> list[BenchmarkMetadata]:
        """Lista todos os benchmarks (versão atual)."""
        pass

    @abstractmethod
    def log_execution(self, execution: BenchmarkExecution) -> None:
        """Registra execução em audit log append-only."""
        pass

    @abstractmethod
    def get_execution_history(
        self, benchmark_id: str, limit: int = 50
    ) -> list[BenchmarkExecution]:
        """Histórico de execuções (últimas N)."""
        pass

    @abstractmethod
    def create_new_version(
        self, benchmark_id: str, patch: dict
    ) -> BenchmarkMetadata:
        """Editar benchmark gera nova versão."""
        pass

    @abstractmethod
    def update_metadata(self, benchmark_id: str, patch: dict) -> None:
        """Atualiza metadados (validando imutabilidade)."""
        pass
