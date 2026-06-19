"""Bronze Writer — ADR-112 F1.

Grava batches de sinais OTel em NDJSON append-only no Blob Storage (camada Bronze).
Também expõe BronzeLogHandler para captura direta de logs Python → Bronze.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any

from concilium.domain.repositories.blob_storage_port import BlobStoragePort


class BronzeWriter:
    """Grava batches NDJSON no Bronze. Append-only: cada chamada cria um arquivo novo."""

    _PREFIX = "observability/bronze"

    def __init__(self, storage: BlobStoragePort, signal_type: str):
        self._storage = storage
        self._signal_type = signal_type

    def write_batch(self, records: list[dict[str, Any]], date: str | None = None) -> str:
        """Grava records como NDJSON. Retorna o path gravado.

        O batch_id inclui timestamp para garantir ordenação lexicográfica por tempo,
        necessária para o fast-forward incremental.
        """
        import uuid
        if date is None:
            date = datetime.date.today().isoformat()
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%H%M%S%f")
        batch_id = f"{ts}-{uuid.uuid4().hex[:8]}"
        path = f"{self._PREFIX}/{self._signal_type}/{date}/{batch_id}.ndjson"
        lines = [json.dumps(r, ensure_ascii=False) for r in records]
        content = "\n".join(lines) + "\n"
        self._storage.gravar_blob(path, content.encode("utf-8"))
        return path


class BronzeLogHandler(logging.Handler):
    """Handler Python logging que escreve records no Bronze (ADR-112 F1).

    Acumula records em buffer e faz flush para o BronzeWriter.
    Útil para captura in-process sem depender de OTLP Collector externo.
    """

    def __init__(self, writer: BronzeWriter, buffer_size: int = 50):
        super().__init__()
        self._writer = writer
        self._buffer_size = buffer_size
        self._buffer: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        entry = {
            "ts": self.formatter.formatTime(record, "%Y-%m-%dT%H:%M:%S.%fZ") if self.formatter else "",
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": getattr(record, "otelTraceID", ""),
            "span_id": getattr(record, "otelSpanID", ""),
            "service": "concilium",
        }
        self._buffer.append(entry)
        if len(self._buffer) >= self._buffer_size:
            self.flush()

    def flush(self) -> None:
        if not self._buffer:
            return
        batch = self._buffer[:]
        self._buffer.clear()
        try:
            self._writer.write_batch(batch)
        except Exception:
            pass  # logging handler nunca deve lançar exceção
