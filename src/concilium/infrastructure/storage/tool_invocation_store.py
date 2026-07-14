"""Repositório de ToolInvocation baseado em BlobStoragePort (ADR-118 F7, rotação ADR-138).

Persiste invocações em NDJSON append-only, compatível com todos os backends
configurados via CONCILIUM__STORE_BACKEND (filesystem, sharepoint, s3, azure, gdrive).

Padrão idêntico ao log_execution do FileSystemBenchmarkStore:
  1. ler_blob(audit_blob) — lê conteúdo existente (FileNotFoundError → b"")
  2. concatena nova linha JSON
  3. gravar_blob(audit_blob, conteúdo_completo)

Rotação (idade OU tamanho, o que vier primeiro): antes de cada append, se o
arquivo ativo já excede CONCILIUM__TOOL_INVOCATIONS_ROTATE_MAX_SIZE_MB (default
1024 — "1 GB") OU o registro mais antigo nele é mais velho que
CONCILIUM__TOOL_INVOCATIONS_ROTATE_MAX_AGE_DAYS (default 30 — "1 mês"), o
conteúdo atual é arquivado em audit-<timestamp>.jsonl e o arquivo ativo
recomeça vazio. Isso mantém append/leitura O(arquivo ativo), não O(histórico
total) — trade-off deliberado: dados arquivados continuam no storage, mas
list_recent/list_by_tool/list_by_user/list_by_device só enxergam o arquivo
ativo pós-rotação (consultar o arquivado exige ler o blob diretamente).

Lock de instância garante serialização em ambiente multi-thread.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from concilium.application.tool_invocations.models import ToolInvocation
from concilium.application.tool_invocations.repository import ToolInvocationRepository

if TYPE_CHECKING:
    from concilium.domain.repositories.blob_storage_port import BlobStoragePort

_AUDIT_PREFIX = ".tool_invocations"
_AUDIT_FILE = "audit.jsonl"

_DEFAULT_ROTATE_MAX_AGE_DAYS = 30.0  # "1 mês"
_DEFAULT_ROTATE_MAX_SIZE_MB = 1024.0  # "1 GB"


def _rotate_max_age_seconds() -> float:
    raw = os.getenv("CONCILIUM__TOOL_INVOCATIONS_ROTATE_MAX_AGE_DAYS", "")
    try:
        days = float(raw) if raw else _DEFAULT_ROTATE_MAX_AGE_DAYS
    except ValueError:
        days = _DEFAULT_ROTATE_MAX_AGE_DAYS
    return days * 86400


def _rotate_max_size_bytes() -> float:
    raw = os.getenv("CONCILIUM__TOOL_INVOCATIONS_ROTATE_MAX_SIZE_MB", "")
    try:
        mb = float(raw) if raw else _DEFAULT_ROTATE_MAX_SIZE_MB
    except ValueError:
        mb = _DEFAULT_ROTATE_MAX_SIZE_MB
    return mb * 1024 * 1024


class BlobToolInvocationRepository(ToolInvocationRepository):
    """Audit log NDJSON persistido via BlobStoragePort.

    Caminho padrão no storage: .tool_invocations/audit.jsonl
    Configurável via parâmetro `prefix`.

    Limitações (mesmas do BenchmarkStore):
    - Append via read+rewrite: O(n) do arquivo ATIVO por gravação (rotação
      mantém esse n limitado — ver módulo)
    - Multi-process: sem coordenação entre processos distintos
    """

    def __init__(
        self,
        storage: BlobStoragePort,
        prefix: str = _AUDIT_PREFIX,
    ) -> None:
        self._storage = storage
        self._prefix = prefix.strip("/")
        self._blob = f"{self._prefix}/{_AUDIT_FILE}"
        self._lock = threading.Lock()

    # ── ToolInvocationRepository ──────────────────────────────────────────────

    def append(self, invocation: ToolInvocation) -> None:
        """Grava linha NDJSON no audit log (thread-safe, best-effort).

        Rotaciona primeiro (ver _should_rotate) se o arquivo ativo já excede
        os limites configurados de idade OU tamanho.
        """
        line = json.dumps(invocation.to_dict(), default=str) + "\n"
        with self._lock:
            existing = self._read_raw()
            if self._should_rotate(existing):
                self._rotate(existing)
                existing = b""
            self._storage.gravar_blob(self._blob, existing + line.encode("utf-8"))

    def _should_rotate(self, raw: bytes) -> bool:
        if not raw:
            return False
        if len(raw) >= _rotate_max_size_bytes():
            return True
        oldest_started_at = self._oldest_started_at(raw)
        if oldest_started_at is None:
            return False
        age_seconds = (datetime.now(UTC) - oldest_started_at).total_seconds()
        return age_seconds >= _rotate_max_age_seconds()

    @staticmethod
    def _oldest_started_at(raw: bytes) -> datetime | None:
        """Parseia started_at da primeira linha válida. None se ilegível."""
        for line in raw.decode("utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                started_at = datetime.fromisoformat(record["started_at"])
            except (json.JSONDecodeError, KeyError, ValueError):
                return None
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=UTC)
            return started_at
        return None

    def _rotate(self, raw: bytes) -> None:
        """Arquiva o conteúdo atual em um blob separado com timestamp."""
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        archive_blob = f"{self._prefix}/audit-{ts}.jsonl"
        self._storage.gravar_blob(archive_blob, raw)

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

    def list_by_device(self, device_id: str, limit: int = 100) -> list[ToolInvocation]:
        """Últimas `limit` invocações de um dispositivo específico (ADR-138)."""
        records = [r for r in self._read_all() if r.device_id == device_id]
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
