"""Repositório de ToolInvocation baseado em BlobStoragePort (ADR-118 F7).

Persiste invocações em NDJSON append-only, compatível com todos os backends
configurados via CONCILIUM__STORE_BACKEND (filesystem, sharepoint, s3, azure, gdrive).

Padrão idêntico ao log_execution do FileSystemBenchmarkStore:
  1. ler_blob(audit_blob) — lê conteúdo existente (FileNotFoundError → b"")
  2. concatena nova linha JSON
  3. gravar_blob(audit_blob, conteúdo_completo)

Lock de instância garante serialização em ambiente multi-thread.
"""

from __future__ import annotations

import json
import threading
from typing import TYPE_CHECKING

from concilium.application.tool_invocations.models import ToolInvocation
from concilium.application.tool_invocations.repository import ToolInvocationRepository

if TYPE_CHECKING:
    from concilium.domain.repositories.blob_storage_port import BlobStoragePort

_AUDIT_PREFIX = ".tool_invocations"
_AUDIT_FILE = "audit.jsonl"


class BlobToolInvocationRepository(ToolInvocationRepository):
    """Audit log NDJSON persistido via BlobStoragePort.

    Caminho padrão no storage: .tool_invocations/audit.jsonl
    Configurável via parâmetro `prefix`.

    Limitações (mesmas do BenchmarkStore):
    - Append via read+rewrite: O(n) por gravação
    - Multi-process: sem coordenação entre processos distintos
    - Rotação de arquivo: não implementada (futuro ADR)
    """

    def __init__(
        self,
        storage: BlobStoragePort,
        prefix: str = _AUDIT_PREFIX,
    ) -> None:
        self._storage = storage
        self._blob = f"{prefix.strip('/')}/{_AUDIT_FILE}"
        self._lock = threading.Lock()

    # ── ToolInvocationRepository ──────────────────────────────────────────────

    def append(self, invocation: ToolInvocation) -> None:
        """Grava linha NDJSON no audit log (thread-safe, best-effort)."""
        line = json.dumps(invocation.to_dict(), default=str) + "\n"
        with self._lock:
            existing = self._read_raw()
            self._storage.gravar_blob(self._blob, existing + line.encode("utf-8"))

    def list_recent(self, limit: int = 100) -> list[ToolInvocation]:
        """Últimas `limit` invocações, mais recente primeiro."""
        records = self._read_all()
        return list(reversed(records[-limit:]))

    def list_by_tool(self, tool_name: str, limit: int = 100) -> list[ToolInvocation]:
        """Últimas `limit` invocações de uma tool específica."""
        records = [r for r in self._read_all() if r.tool_name == tool_name]
        return list(reversed(records[-limit:]))

    def list_by_user(self, user_id: str, limit: int = 100) -> list[ToolInvocation]:
        """Últimas `limit` invocações de um usuário específico."""
        records = [r for r in self._read_all() if r.user_id == user_id]
        return list(reversed(records[-limit:]))

    def count(self) -> int:
        """Total de registros no arquivo."""
        return len(self._read_all())

    # ── Helpers internos ──────────────────────────────────────────────────────

    def _read_raw(self) -> bytes:
        try:
            return self._storage.ler_blob(self._blob)
        except FileNotFoundError:
            return b""

    def _read_all(self) -> list[ToolInvocation]:
        raw = self._read_raw()
        if not raw:
            return []
        records: list[ToolInvocation] = []
        for line in raw.decode("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(ToolInvocation.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError):
                continue
        return records
