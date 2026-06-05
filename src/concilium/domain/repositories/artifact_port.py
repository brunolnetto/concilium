"""ADR-029 D5 — Port interface: ArtifactStorePort.

Define o contrato (ABC) que qualquer implementação concreta de artifact store
deve satisfazer. Implementações concretas vivem em
concilium.infrastructure.repositories (ou infrastructure.storage).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


class ArtifactStorePort(ABC):
    """Port (interface) para persistência e recuperação de artefatos."""

    @abstractmethod
    def save(self, artifact_id: str, data: Any, metadata: dict | None = None) -> None:
        """Persiste um artefato identificado por artifact_id."""

    @abstractmethod
    def load(self, artifact_id: str) -> Any:
        """Recupera um artefato pelo seu identificador.

        Raises:
            KeyError: se o artifact_id não for encontrado.
        """

    @abstractmethod
    def exists(self, artifact_id: str) -> bool:
        """Verifica se um artefato com o artifact_id existe."""

    @abstractmethod
    def delete(self, artifact_id: str) -> None:
        """Remove um artefato persistido."""
