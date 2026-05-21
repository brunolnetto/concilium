"""Configuration and constants for Streamlit UI."""

from __future__ import annotations

# API Configuration
DEFAULT_BASE_URL = "http://api:8000"
DEFAULT_ACTOR = "ui-demo"
DEFAULT_PAGE_SIZE = 50
REQUEST_TIMEOUT = 120

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
NAVIGATION_OPTIONS = ["Dashboard", "Configuração", "Catálogo", "Projetos"]
DEFAULT_NAV = "Dashboard"

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
