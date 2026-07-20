"""Configuração centralizada de logging — ADR-111.

Uso:
    from concilium.infrastructure.observability.logging_config import configure_logging

    configure_logging()                        # INFO, JSON (produção)
    configure_logging(json_format=False)       # INFO, formato humano (dev)
    configure_logging("WARNING", json_format=False)  # CI/testes
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# _JsonFormatter: JSON-lines com campos OTel obrigatórios (ADR-111 D4)
# ─────────────────────────────────────────────────────────────────────────────


def _format_ts_utc(record: logging.LogRecord) -> str:
    """Timestamp ISO-8601 UTC com microssegundos reais.

    Formatter.formatTime() delega para time.strftime() sobre um time.struct_time,
    que NÃO suporta '%f' (extensão exclusiva de datetime.strftime) — o literal
    "%f" era gravado sem substituição em todo log de Bronze/Silver, quebrando o
    parsing ISO-8601 e degradando o fallback de event_id (ts+logger+message) em
    _make_event_id, já que "%f" não diferencia records no mesmo segundo.
    datetime.fromtimestamp(..., tz=UTC) também torna o UTC explícito — antes
    dependia implicitamente do timezone do container (Formatter.converter usa
    time.localtime por padrão) para o sufixo "Z" ser correto.
    """
    return datetime.fromtimestamp(record.created, tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _get_trace_context() -> tuple[str, str]:
    """Retorna (trace_id, span_id) do span OTel ativo, ou ('', '') se ausente."""
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx and ctx.is_valid:
            return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")
    except Exception:
        pass
    return "", ""


def _get_auth_context() -> tuple[str, str]:
    """Retorna (user_id, request_id) do contexto de request atual, ou ('', '') se ausente.

    Dois mecanismos de auth-context coexistem e não se conhecem: AuthContextMiddleware
    (API, contextvars em auth_context.py) e McpAuthMiddleware (MCP, contextvars
    separadas em permission_guard.py, ADR-118) — praticamente todo o tráfego real
    de tools é via MCP, então sem esse fallback user_id fica sempre vazio.
    """
    user_id, request_id = "", ""
    try:
        from concilium.infrastructure.middleware.auth_context import (
            current_request_id,
            current_user_id,
        )

        user_id, request_id = current_user_id.get(), current_request_id.get()
    except Exception:
        pass

    if not user_id:
        try:
            from concilium.infrastructure.auth.permission_guard import get_current_user_id

            user_id = get_current_user_id() or ""
        except Exception:
            pass

    return user_id, request_id


class _JsonFormatter(logging.Formatter):
    """Emite JSON-lines com campos obrigatórios: ts, severity, logger, message, trace_id, span_id, service."""

    def format(self, record: logging.LogRecord) -> str:
        trace_id, span_id = _get_trace_context()
        user_id, request_id = _get_auth_context()
        payload: dict[str, Any] = {
            "ts": _format_ts_utc(record),
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": trace_id,
            "span_id": span_id,
            "service": "concilium",
            "user_id": user_id,
            "request_id": request_id,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # ADR-121 D2: fallback_type (ADR-110) promovido quando presente no record extra
        fallback_type = record.__dict__.get("fallback_type")
        if fallback_type is not None:
            payload["fallback_type"] = str(fallback_type)
        return json.dumps(payload, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
# configure_logging()
# ─────────────────────────────────────────────────────────────────────────────

_NOISY_LOGGERS = ("httpx", "httpcore", "urllib3", "azure", "opentelemetry.sdk")


def configure_logging(
    level: str = "INFO",
    json_format: bool = True,
    bronze_storage: Any | None = None,
) -> None:
    """Configura o sistema de logging do Concilium (ADR-111 D3, ADR-121 D3).

    Args:
        level:          Nível do root logger (INFO, WARNING, DEBUG, ERROR).
        json_format:    True → JSON estruturado (produção/MCP/API).
                        False → formato humano (dev, CLI, CI).
        bronze_storage: BlobStoragePort opcional. Quando fornecido, conecta
                        BronzeLogHandler ao root logger para alimentar o
                        pipeline Medallion Bronze em tempo real.

    Idempotente: chamar duas vezes não duplica handlers.
    """
    from concilium.infrastructure.observability.bronze_writer import BronzeLogHandler, BronzeWriter

    root = logging.getLogger()
    root.setLevel(level)

    # Remove handlers _JsonFormatter existentes antes de reconfigurar
    for h in root.handlers[:]:
        if isinstance(h, logging.StreamHandler) and isinstance(h.formatter, _JsonFormatter):
            root.removeHandler(h)

    if json_format:
        handler = logging.StreamHandler()
        handler.setFormatter(_JsonFormatter())
        root.addHandler(handler)
    else:
        # Formato humano — adiciona handler básico apenas se root ainda não tem handlers
        if not root.handlers:
            logging.basicConfig(
                level=level,
                format="%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
                datefmt="%H:%M:%S",
            )
        else:
            root.setLevel(level)

    # ADR-121 D3: BronzeLogHandler — alimenta Medallion Bronze com logs ao vivo
    # Remove instâncias prévias antes de adicionar para garantir idempotência —
    # close() para a thread de flush periódico da instância antiga antes de descartá-la.
    for h in root.handlers[:]:
        if isinstance(h, BronzeLogHandler):
            h.close()
            root.removeHandler(h)
    if bronze_storage is not None:
        writer = BronzeWriter(bronze_storage, "logs")
        bronze_handler = BronzeLogHandler(writer, buffer_size=50)
        bronze_handler.setFormatter(_JsonFormatter())
        bronze_handler.start_periodic_flush()
        root.addHandler(bronze_handler)

    # Silenciar bibliotecas ruidosas (ADR-111 D3)
    for noisy in _NOISY_LOGGERS:
        logging.getLogger(noisy).setLevel(logging.WARNING)
