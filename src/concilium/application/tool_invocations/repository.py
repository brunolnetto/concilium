"""Repository para ToolInvocation (ADR-118).

Interface Port + implementação InMemory com buffer circular.
Padrão idêntico ao JobRepository (ADR-103) para consistência.

Variável de ambiente:
  CONCILIUM__TOOL_INVOCATIONS_MAX_SIZE  — tamanho máximo do buffer circular
                                          (padrão: 10000; 0 = ilimitado)
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from collections import deque
from os import getenv

from concilium.application.tool_invocations.models import ToolInvocation


class ToolInvocationRepository(ABC):
    """Interface de auditoria de invocações (Port pattern)."""

    @abstractmethod
    def append(self, invocation: ToolInvocation) -> None:
        """Registra uma invocação concluída."""
        ...

    @abstractmethod
    def list_recent(self, limit: int = 100) -> list[ToolInvocation]:
        """Retorna as últimas `limit` invocações (mais recente primeiro)."""
        ...

    @abstractmethod
    def list_by_tool(self, tool_name: str, limit: int = 100) -> list[ToolInvocation]:
        """Retorna as últimas `limit` invocações de uma tool específica."""
        ...

    @abstractmethod
    def list_by_user(self, user_id: str, limit: int = 100) -> list[ToolInvocation]:
        """Retorna as últimas `limit` invocações de um usuário específico."""
        ...

    @abstractmethod
    def list_by_device(self, device_id: str, limit: int = 100) -> list[ToolInvocation]:
        """Retorna as últimas `limit` invocações de um dispositivo específico (ADR-138)."""
        ...

    @abstractmethod
    def count(self) -> int:
        """Total de registros no buffer."""
        ...


class InMemoryToolInvocationRepository(ToolInvocationRepository):
    """Buffer circular thread-safe em memória.

    max_size = 0  → ilimitado (usar apenas em testes/dev)
    max_size > 0  → buffer circular (oldest dropped when full)
    """

    def __init__(self, max_size: int = 10_000) -> None:
        self._buffer: deque[ToolInvocation] = deque(maxlen=max_size if max_size > 0 else None)
        self._lock = threading.Lock()

    def append(self, invocation: ToolInvocation) -> None:
        with self._lock:
            self._buffer.append(invocation)

    def list_recent(self, limit: int = 100) -> list[ToolInvocation]:
        with self._lock:
            items = list(self._buffer)
        return list(reversed(items[-limit:]))

    def list_by_tool(self, tool_name: str, limit: int = 100) -> list[ToolInvocation]:
        with self._lock:
            items = [i for i in self._buffer if i.tool_name == tool_name]
        return list(reversed(items[-limit:]))

    def list_by_user(self, user_id: str, limit: int = 100) -> list[ToolInvocation]:
        with self._lock:
            items = [i for i in self._buffer if i.user_id == user_id]
        return list(reversed(items[-limit:]))

    def list_by_device(self, device_id: str, limit: int = 100) -> list[ToolInvocation]:
        with self._lock:
            items = [i for i in self._buffer if i.device_id == device_id]
        return list(reversed(items[-limit:]))

    def count(self) -> int:
        with self._lock:
            return len(self._buffer)

    def clear(self) -> None:
        """Limpa o buffer (apenas para testes)."""
        with self._lock:
            self._buffer.clear()


# ── Singleton ─────────────────────────────────────────────────────────────────

_repository: ToolInvocationRepository | None = None
_repository_lock = threading.Lock()


def _max_size() -> int:
    raw = getenv("CONCILIUM__TOOL_INVOCATIONS_MAX_SIZE", "10000") or "10000"
    try:
        return max(0, int(raw))
    except ValueError:
        return 10_000


def get_tool_invocation_repository() -> ToolInvocationRepository:
    """Retorna repositório singleton.

    Pode ser sobrescrito em testes via reset_tool_invocation_repository().
    """
    global _repository
    if _repository is None:
        with _repository_lock:
            if _repository is None:
                _repository = InMemoryToolInvocationRepository(max_size=_max_size())
    assert _repository is not None  # double-checked locking sempre atribui antes daqui
    return _repository


def reset_tool_invocation_repository(repo: ToolInvocationRepository | None = None) -> None:
    """Reseta ou substitui repositório. Apenas para testes."""
    global _repository
    with _repository_lock:
        _repository = repo
