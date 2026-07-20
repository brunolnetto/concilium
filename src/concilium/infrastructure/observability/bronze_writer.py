"""Bronze Writer — ADR-112 F1.

Grava batches de sinais OTel em NDJSON append-only no Blob Storage (camada Bronze).
Também expõe BronzeLogHandler para captura direta de logs Python → Bronze.
"""

from __future__ import annotations

import datetime
import json
import logging
import threading
from collections.abc import Callable
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
        ts = datetime.datetime.now(datetime.UTC).strftime("%H%M%S%f")
        batch_id = f"{ts}-{uuid.uuid4().hex[:8]}"
        path = f"{self._PREFIX}/{self._signal_type}/{date}/{batch_id}.ndjson"
        lines = [json.dumps(r, ensure_ascii=False) for r in records]
        content = "\n".join(lines) + "\n"
        self._storage.gravar_blob(path, content.encode("utf-8"))
        return path


class _PeriodicFlusher:
    """Thread daemon que chama uma função de flush a cada `interval_s` segundos.

    Complementa o flush por tamanho de buffer: sem isso, um processo de baixo
    volume de log (ou uma réplica que recicla por scale-to-zero antes de
    acumular `buffer_size` registros) nunca esvazia o buffer — os registros
    ficam presos em memória e são perdidos quando o processo termina.
    """

    def __init__(self, flush_fn: Callable[[], None], interval_s: float) -> None:
        self._flush_fn = flush_fn
        self._interval_s = interval_s
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="bronze-periodic-flush")
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop_event.wait(self._interval_s):
            try:
                self._flush_fn()
            except Exception:
                pass

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None


class BronzeLogHandler(logging.Handler):
    """Handler Python logging que escreve records no Bronze (ADR-112 F1).

    Acumula records em buffer e faz flush para o BronzeWriter — por tamanho
    (emit) e por tempo (flush periódico opcional, ver `start_periodic_flush`).
    Útil para captura in-process sem depender de OTLP Collector externo.
    """

    def __init__(self, writer: BronzeWriter, buffer_size: int = 50, flush_interval_s: float = 30.0):
        super().__init__()
        self._writer = writer
        self._buffer_size = buffer_size
        self._buffer: list[dict[str, Any]] = []
        self._buffer_lock = threading.Lock()
        self._flusher = _PeriodicFlusher(self.flush, flush_interval_s) if flush_interval_s > 0 else None

    def start_periodic_flush(self) -> None:
        """Inicia o flush em background. Chamado explicitamente pelo composition
        root (configure_logging), nunca em __init__ — mantém testes que só
        instanciam o handler livres de threads implícitas."""
        if self._flusher is not None:
            self._flusher.start()

    def emit(self, record: logging.LogRecord) -> None:
        from concilium.infrastructure.observability.logging_config import _format_ts_utc, _get_auth_context

        user_id, request_id = _get_auth_context()
        entry = {
            "ts": _format_ts_utc(record) if self.formatter else "",
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": getattr(record, "otelTraceID", ""),
            "span_id": getattr(record, "otelSpanID", ""),
            "service": "concilium",
            "user_id": user_id,
            "request_id": request_id,
        }
        with self._buffer_lock:
            self._buffer.append(entry)
            should_flush = len(self._buffer) >= self._buffer_size
        if should_flush:
            self.flush()

    def flush(self) -> None:
        # Lock protege contra emit()/flush periódico concorrentes (threads distintas).
        with self._buffer_lock:
            if not self._buffer:
                return
            batch = self._buffer[:]
            self._buffer.clear()
        try:
            self._writer.write_batch(batch)
        except Exception:
            pass  # logging handler nunca deve lançar exceção

    def close(self) -> None:
        """Para o flush periódico e drena o buffer restante (shutdown-drain).

        Chamado automaticamente por `logging.shutdown()` (atexit registrado
        pelo módulo `logging` na importação) em encerramento normal do
        processo, além de explicitamente por `configure_logging` ao substituir
        um handler antigo.
        """
        if self._flusher is not None:
            self._flusher.stop()
        self.flush()
        super().close()
