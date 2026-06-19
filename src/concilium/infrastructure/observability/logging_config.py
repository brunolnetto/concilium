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
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# _JsonFormatter: JSON-lines com campos OTel obrigatórios (ADR-111 D4)
# ─────────────────────────────────────────────────────────────────────────────

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
    """Retorna (user_id, request_id) do contexto de request atual, ou ('', '') se ausente."""
    try:
        from concilium.infrastructure.middleware.auth_context import (
            current_request_id,
            current_user_id,
        )
        return current_user_id.get(), current_request_id.get()
    except Exception:
        return "", ""


class _JsonFormatter(logging.Formatter):
    """Emite JSON-lines com campos obrigatórios: ts, severity, logger, message, trace_id, span_id, service."""

    def format(self, record: logging.LogRecord) -> str:
        trace_id, span_id = _get_trace_context()
        user_id, request_id = _get_auth_context()
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%fZ"),
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
        return json.dumps(payload, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
# configure_logging()
# ─────────────────────────────────────────────────────────────────────────────

_NOISY_LOGGERS = ("httpx", "httpcore", "urllib3", "azure", "opentelemetry.sdk")


def configure_logging(level: str = "INFO", json_format: bool = True) -> None:
    """Configura o sistema de logging do Concilium (ADR-111 D3).

    Args:
        level:       Nível do root logger (INFO, WARNING, DEBUG, ERROR).
        json_format: True → JSON estruturado (produção/MCP/API).
                     False → formato humano (dev, CLI, CI).

    Idempotente: chamar duas vezes não duplica handlers.
    """
    root = logging.getLogger()
    root.setLevel(level)

    # Sempre remove handlers _JsonFormatter existentes antes de reconfigurar
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

    # Silenciar bibliotecas ruidosas (ADR-111 D3)
    for noisy in _NOISY_LOGGERS:
        logging.getLogger(noisy).setLevel(logging.WARNING)
