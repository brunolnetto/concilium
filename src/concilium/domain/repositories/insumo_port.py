"""ADR-029 D5 — Port interface: RepositorioInsumoPort.

Define o contrato (ABC) que qualquer implementação concreta de repositório
de insumos deve satisfazer. Implementações concretas vivem em
concilium.infrastructure.repositories.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from concilium.domain.models.catalog.catalogo import Insumo


class RepositorioInsumoPort(ABC):
    """Port (interface) para acesso ao catálogo de insumos."""

    @abstractmethod
    def buscar(self, codigo: str) -> Insumo | None:
        """Retorna o Insumo pelo código ou None se não encontrado."""

    @abstractmethod
    def listar(self, tipo: str | None = None) -> list[Insumo]:
        """Lista todos os insumos, opcionalmente filtrados por tipo."""

    @abstractmethod
    def funcao_existe(self, funcao_id: str) -> bool:
        """Verifica existência de uma função (MAO_OBRA) no catálogo."""

    @abstractmethod
    def equipamento_existe(self, equip_id: str) -> bool:
        """Verifica existência de um equipamento no catálogo."""

    @abstractmethod
    def obter_insumo(self, codigo: str) -> dict | None:
        """Retorna insumo como dict (compatibilidade com skill layer)."""
