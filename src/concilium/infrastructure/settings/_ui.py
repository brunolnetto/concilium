"""Settings (parte extraída de settings.py) — grupo _ui."""

from __future__ import annotations

from dataclasses import dataclass

from ._api import ApiSettings, get_api
from ._core import _int, _refresh_if_env_changed, _str


@dataclass(frozen=True)
class UiSettings:
    """Configuração da UI Streamlit."""

    host: str
    """CONCILIUM__UI_HOST — bind host (default: 127.0.0.1)."""

    port: int
    """CONCILIUM__UI_PORT — bind port (default: 8501)."""

    api_base_url_override: str
    """CONCILIUM__UI_API_BASE_URL — URL da API vista pela UI (sobrescreve CONCILIUM__API_BASE_URL)."""

    entrypoint: str
    """CONCILIUM__UI_ENTRYPOINT — caminho para script Streamlit customizado."""

    def resolved_api_base_url(self, api: ApiSettings | None = None) -> str:
        """Resolve a URL da API com precedência: UI_override > API_BASE_URL > host:port."""
        if self.api_base_url_override:
            return self.api_base_url_override.rstrip("/")
        if api and api.base_url:
            return api.base_url.rstrip("/")
        _api = api or get_api()
        return f"http://{_api.host}:{_api.port}"

    @classmethod
    def from_env(cls) -> UiSettings:
        return cls(
            host=_str("CONCILIUM__UI_HOST", "127.0.0.1"),
            port=_int("CONCILIUM__UI_PORT", 8501),
            api_base_url_override=_str("CONCILIUM__UI_API_BASE_URL", ""),
            entrypoint=_str("CONCILIUM__UI_ENTRYPOINT", ""),
        )


_ui: UiSettings | None = None


def get_ui() -> UiSettings:
    _refresh_if_env_changed()
    global _ui
    if _ui is None:
        _ui = UiSettings.from_env()
    return _ui




def _reset_ui() -> None:
    global _ui
    _ui = None
