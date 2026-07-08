"""Settings (parte extraída de settings.py) — grupo _api."""

from __future__ import annotations

from dataclasses import dataclass

from ._core import _flag, _int, _refresh_if_env_changed, _str


@dataclass(frozen=True)
class ApiSettings:
    """Configuração do servidor FastAPI REST (porta 8000)."""

    host: str
    """CONCILIUM__API_HOST — bind host (default: 127.0.0.1)."""

    port: int
    """CONCILIUM__API_PORT — bind port (default: 8000)."""

    reload: bool
    """CONCILIUM__API_RELOAD — hot-reload uvicorn (default: False)."""

    base_url: str
    """CONCILIUM__API_BASE_URL — URL canônica da API para consumidores (UI, scripts)."""

    @classmethod
    def from_env(cls) -> ApiSettings:
        return cls(
            host=_str("CONCILIUM__API_HOST", "127.0.0.1"),
            port=_int("CONCILIUM__API_PORT", 8000),
            reload=_flag("CONCILIUM__API_RELOAD"),
            base_url=_str("CONCILIUM__API_BASE_URL", ""),
        )


_api: ApiSettings | None = None


def get_api() -> ApiSettings:
    _refresh_if_env_changed()
    global _api
    if _api is None:
        _api = ApiSettings.from_env()
    return _api


def _reset_api() -> None:
    global _api
    _api = None


