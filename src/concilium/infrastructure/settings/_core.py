"""Settings (parte extraída de settings.py) — grupo _core."""

from __future__ import annotations

import os
from pathlib import Path


def _env_fingerprint() -> tuple[tuple[str, str], ...]:
    """Fingerprint determinístico das env vars relevantes para settings."""
    tracked: list[tuple[str, str]] = []
    for key, value in os.environ.items():
        if key.startswith("CONCILIUM__") or key in {
            "OTEL_SDK_DISABLED",
            "OTEL_SERVICE_NAME",
            "OTEL_EXPORTER_OTLP_ENDPOINT",
        }:
            tracked.append((key, value))
    tracked.sort(key=lambda item: item[0])
    return tuple(tracked)


_last_env_fingerprint: tuple[tuple[str, str], ...] | None = None


def _reset_env_fingerprint() -> None:
    global _last_env_fingerprint
    _last_env_fingerprint = None


def _refresh_if_env_changed() -> None:
    """Invalida cache de settings quando env vars mudam no mesmo processo."""
    # Import tardio: evita import circular com _lifecycle (que importa
    # get_X/_reset_X de todos os grupos de settings).
    from ._lifecycle import _reset_all

    global _last_env_fingerprint
    current = _env_fingerprint()
    if _last_env_fingerprint != current:
        _reset_all()
        _last_env_fingerprint = current


def _str(name: str, default: str = "") -> str:
    """Lê variável de ambiente como string com fallback."""
    return (os.environ.get(name) or default).strip() or default


def _int(name: str, default: int = 0) -> int:
    """Lê variável de ambiente como inteiro com fallback."""
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw.strip())
    except (ValueError, TypeError):
        return default


def _flag(name: str, default: bool = False) -> bool:
    """Lê variável de ambiente como booleano. Falsy: '0', 'false', 'no', 'off', ''."""
    val = (os.environ.get(name) or "").strip().lower()
    if not val:
        return default
    return val not in ("0", "false", "no", "off")


def _path(name: str, default: Path | None = None) -> Path | None:
    """Lê variável de ambiente como Path expandido. None se ausente."""
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    return Path(raw).expanduser().resolve()


