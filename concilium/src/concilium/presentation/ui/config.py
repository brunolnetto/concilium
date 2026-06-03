"""Configuration and constants for Streamlit UI."""

from __future__ import annotations

import os


def _env_str(name: str, default: str) -> str:
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip()
    return value or default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def resolve_api_bind_host() -> str:
    """Host canônico da API para ambientes desacoplados."""
    return _env_str("CONCILIUM__API_HOST", "api")


def resolve_api_bind_port() -> int:
    """Porta canônica da API para ambientes desacoplados."""
    return _env_int("CONCILIUM__API_PORT", 8000)


def resolve_api_base_url() -> str:
    """Resolve URL base da API consumida pela UI com precedência explícita.

    Ordem de precedência:
    1. CONCILIUM__UI_API_BASE_URL (override da UI)
    2. CONCILIUM__API_BASE_URL (valor canônico compartilhado)
    3. CONCILIUM__API_HOST + CONCILIUM__API_PORT
    """
    ui_override = os.environ.get("CONCILIUM__UI_API_BASE_URL", "").strip()
    if ui_override:
        return ui_override.rstrip("/")

    api_base = os.environ.get("CONCILIUM__API_BASE_URL", "").strip()
    if api_base:
        return api_base.rstrip("/")

    host = resolve_api_bind_host()
    port = resolve_api_bind_port()
    return f"http://{host}:{port}"


def resolve_ui_bind_host() -> str:
    """Host sugerido para bind da UI (Streamlit)."""
    return _env_str("CONCILIUM__UI_HOST", "127.0.0.1")


def resolve_ui_bind_port() -> int:
    """Porta sugerida para bind da UI (Streamlit)."""
    return _env_int("CONCILIUM__UI_PORT", 8501)


# API Configuration
DEFAULT_BASE_URL = resolve_api_base_url()
DEFAULT_ACTOR = "ui-demo"
DEFAULT_PAGE_SIZE = 50
REQUEST_TIMEOUT = 120

# Suggested bind values for Streamlit launcher scripts
UI_BIND_HOST = resolve_ui_bind_host()
UI_BIND_PORT = resolve_ui_bind_port()

# UI Configuration — alinhado com .streamlit/config.toml (paleta MendesLobo)
PAGE_CONFIG = {
    "page_title": "Concilium | MendesLobo",
    "page_icon": "🏗️",
    "layout": "wide",
    "initial_sidebar_state": "expanded",
}

# Paleta corporativa MendesLobo (espelha _C em excel_adapter.py)
ML_NAVY = "#1A3A5C"
ML_NAVY_MD = "#2B6CB0"
ML_NAVY_LT = "#EBF2FA"
ML_ORANGE = "#C05C18"
ML_ORANGE_LT = "#F5E6D8"

# Navigation
NAVIGATION_OPTIONS = ["Configuração", "Catálogo", "Projetos", "Novo QQP"]
DEFAULT_NAV = "Projetos"

# Project Kinds
PROJECT_KIND_HOT = "hot_project"
PROJECT_KIND_NORMAL = "project"

# BDI Keys
BDI_KEYS = ["mao_obra", "equipamentos", "material", "diesel", "indireto"]

# UI Limits
MAX_AUDIT_LIMIT = 1000
DEFAULT_AUDIT_LIMIT = 200
MIN_AUDIT_LIMIT = 10

# Emojis/Icons
ICON_OVERVIEW = "📊"
ICON_CONTROL = "🛠️"
ICON_COMPARE = "🔀"
ICON_ARTIFACTS = "📦"
ICON_AUDIT = "📝"
ICON_SUCCESS = "✨"
ICON_ERROR = "❌"
ICON_INFO = "ℹ️"
ICON_WARNING = "⚠️"
