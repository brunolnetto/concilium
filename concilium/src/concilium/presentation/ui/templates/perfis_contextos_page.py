"""Página de gestão de Perfis e Contextos — ADR-062.

Perfis e Contextos compartilham a mesma lógica de versionamento
(ConfigVersionService). Esta página expõe o histórico, comparação e
criação de novas versões para ambas as entidades.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

from ._perfis_helpers_a import (
    _render_entity_section,
)
from ._perfis_helpers_b import (
    _render_perfil_detail,
    _render_temas_section,
)
from ._perfis_helpers_c import (
    _render_jurisdicoes_section,
)

try:
    from ..config import DEFAULT_ACTOR, DEFAULT_BASE_URL
    from ..molecules.common import render_page_heading
except ImportError:
    src_root = Path(__file__).resolve().parents[4]
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    from concilium.presentation.ui.config import DEFAULT_ACTOR, DEFAULT_BASE_URL
    from concilium.presentation.ui.molecules.common import render_page_heading


# ═══════════════════════════════════════════════════════════════════════════
# Página principal
# ═══════════════════════════════════════════════════════════════════════════


def render_configuracao_page() -> None:
    render_page_heading(
        "Configuração",
        "Gerencie perfis financeiros, contextos, temas visuais e overlays de jurisdição.",
    )

    base_url = DEFAULT_BASE_URL
    actor = DEFAULT_ACTOR

    tabs = st.tabs(["⚖️ Jurisdições", "📋 Perfis", "🌐 Contextos", "🎨 Temas"])

    with tabs[0]:
        _render_jurisdicoes_section(base_url=base_url, actor=actor)

    with tabs[1]:
        _render_entity_section(
            base_url=base_url,
            actor=actor,
            list_path="/api/perfis",
            versions_path_tpl="/api/perfis/{id}/versions",
            compare_path="/api/perfis/compare",
            entity_label="Perfil",
            key_prefix="perf",
            extra_renderer=_render_perfil_detail,
        )

    with tabs[2]:
        _render_entity_section(
            base_url=base_url,
            actor=actor,
            list_path="/api/contextos",
            versions_path_tpl="/api/contextos/{id}/versions",
            compare_path="/api/contextos/compare",
            entity_label="Contexto",
            key_prefix="ctx",
        )

    with tabs[3]:
        _render_temas_section(base_url=base_url, actor=actor)

    st.divider()


# ═══════════════════════════════════════════════════════════════════════════
# Secção genérica de entidade versionada (usada por Perfis E Contextos)
# ═══════════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════════
# Helpers de versão compartilhados
# ═══════════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════════
# Componente reutilizável: card de entidade (substitui JSON bruto)
# ═══════════════════════════════════════════════════════════════════════════

_AUDIT_KEYS = {"version", "created_at", "created_by", "motivo", "$comment"}
_SKIP_DISPLAY = {"_make_current"}
# ═══════════════════════════════════════════════════════════════════════════
# Renderer extra específico para Perfis
# ═══════════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════════
# Seção de Temas Visuais (ADR-065)
# ═══════════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════════
# Secao de Jurisdicoes (ADR-066)
# ═══════════════════════════════════════════════════════════════════════════
