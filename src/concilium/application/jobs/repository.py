"""Repository pattern para persistência de jobs.

ADR-103: Jobs na Camada de Aplicação

Interface de persistência (Port pattern) que permite trocar implementação
sem afetar a camada de aplicação.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from typing import Any


class JobRepository(ABC):
    """Interface de persistência para jobs (Port pattern)."""

    @abstractmethod
    def save(self, job_id: str, job_data: dict[str, Any]) -> None:
        """Salva ou atualiza um job.

        Args:
            job_id: ID do job
            job_data: Dados do job
        """
        ...

    @abstractmethod
    def get(self, job_id: str) -> dict[str, Any] | None:
        """Recupera um job por ID.

        Args:
            job_id: ID do job

        Returns:
            Dados do job ou None se não encontrado
        """
        ...

    @abstractmethod
    def list_all(self) -> list[dict[str, Any]]:
        """Lista todos os jobs.

        Returns:
            Lista com dados de todos os jobs
        """
        ...

    @abstractmethod
    def delete(self, job_id: str) -> bool:
        """Remove um job.

        Args:
            job_id: ID do job

        Returns:
            True se job foi removido, False se não existia
        """
        ...

    @abstractmethod
    def delete_many(self, job_ids: list[str]) -> int:
        """Remove múltiplos jobs.

        Args:
            job_ids: Lista de IDs de jobs

        Returns:
            Número de jobs removidos
        """
        ...

    @abstractmethod
    def count(self) -> int:
        """Conta total de jobs.

        Returns:
            Número total de jobs
        """
        ...


class InMemoryJobRepository(JobRepository):
    """Implementação em memória (thread-safe).

    Adequado para:
    - Desenvolvimento local
    - Testes
    - Ambientes com poucos jobs (<1000)

    Limitações:
    - Jobs perdidos ao reiniciar servidor
    - Memória cresce indefinidamente sem GC
    - Não funciona em múltiplos processos/servidores
    """

    def __init__(self):
        """Inicializa repositório vazio."""
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def save(self, job_id: str, job_data: dict[str, Any]) -> None:
        """Salva ou atualiza um job."""
        with self._lock:
            self._jobs[job_id] = job_data

    def get(self, job_id: str) -> dict[str, Any] | None:
        """Recupera um job por ID."""
        with self._lock:
            return self._jobs.get(job_id)

    def list_all(self) -> list[dict[str, Any]]:
        """Lista todos os jobs."""
        with self._lock:
            return list(self._jobs.values())

    def delete(self, job_id: str) -> bool:
        """Remove um job."""
        with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
                return True
            return False

    def delete_many(self, job_ids: list[str]) -> int:
        """Remove múltiplos jobs."""
        with self._lock:
            removed = 0
            for job_id in job_ids:
                if job_id in self._jobs:
                    del self._jobs[job_id]
                    removed += 1
            return removed

    def count(self) -> int:
        """Conta total de jobs."""
        with self._lock:
            return len(self._jobs)


# Singleton global (usado por get_job_repository())
_repository: JobRepository | None = None
_repository_lock = threading.Lock()


def get_job_repository() -> JobRepository:
    """Retorna repositório singleton.

    Returns:
        Instância de JobRepository
    """
    global _repository

    if _repository is None:
        with _repository_lock:
            if _repository is None:
                # TODO: Ler de configuração qual implementação usar
                # Por enquanto, sempre InMemory
                _repository = InMemoryJobRepository()

    return _repository


def reset_repository() -> None:
    """Reseta repositório (apenas para testes).

    WARNING: Esta função NÃO é thread-safe e deve ser usada apenas em testes.
    """
    global _repository
    with _repository_lock:
        _repository = None
