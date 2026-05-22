from __future__ import annotations

import os


def resolve_api_bind() -> tuple[str, int]:
    """Resolve host/port de bind da API com fallback seguro."""
    host = (os.environ.get("CONCILIUM_API_HOST") or "127.0.0.1").strip() or "127.0.0.1"
    raw_port = os.environ.get("CONCILIUM_API_PORT")
    try:
        port = int(raw_port) if raw_port is not None else 8000
    except (TypeError, ValueError):
        port = 8000
    return host, port
