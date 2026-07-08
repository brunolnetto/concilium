"""Camada de apresentação — layout Streamlit (parte extraída de layout.py)."""

from __future__ import annotations

import streamlit as st

from ...infra.api import (
    api_call,
    fetch_artifact_bytes,
)


def _render_md_with_mermaid(text: str) -> None:
    """Render Markdown com suporte a diagramas Mermaid via componente HTML."""
    import re

    import streamlit.components.v1 as components

    # Pin to a stable Mermaid 11.x that has xychart support without 10.9.6 bugs
    MERMAID_JS = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"

    # Separa blocos mermaid do resto do markdown
    pattern = re.compile(r"```mermaid\n(.*?)```", re.DOTALL)
    parts = pattern.split(text)

    for i, part in enumerate(parts):
        if i % 2 == 0:
            # Texto/markdown normal
            if part.strip():
                st.markdown(part)
        else:
            # Bloco mermaid — renderiza via HTML
            diagram = part.strip()
            html = f"""
<div id="mermaid-{i}" class="mermaid" style="background:white">{diagram}</div>
<script>
  (function() {{
    function render() {{
      if (typeof mermaid !== 'undefined') {{
        mermaid.initialize({{startOnLoad: false, theme: 'default', securityLevel: 'loose'}});
        mermaid.run({{nodes: [document.getElementById('mermaid-{i}')]}});
      }}
    }}
    if (typeof mermaid === 'undefined') {{
      var s = document.createElement('script');
      s.src = '{MERMAID_JS}';
      s.onload = render;
      document.head.appendChild(s);
    }} else {{
      render();
    }}
  }})();
</script>
"""
            components.html(html, height=350, scrolling=True)


def _find_md_artifact(outputs: list) -> str | None:
    """Returns the best Markdown artifact name from outputs list."""
    md_candidates = [name for name in outputs if str(name).lower().endswith(".md")]
    preferred = next((name for name in md_candidates if str(name).lower() == "relatorio.md"), None)
    return preferred or (md_candidates[0] if md_candidates else None)


def render_markdown_report_preview(base_url: str, project_id: str, version: str | None, actor: str) -> None:
    """Render Markdown report preview."""
    st.subheader("Pré-visualização do relatório (Markdown)")
    st.caption(
        "⚠️ Gráficos e visualizações analíticas (Curva ABC, S-Curve, Cubo BDI, Campanha de Frota) "
        "estão disponíveis nas abas dedicadas do Excel (`resultado_planejamento.xlsx`). "
        "O relatório Markdown contém texto, tabelas e métricas financeiras."
    )
    try:
        artifacts = api_call(
            method="GET",
            path=f"/api/projects/{project_id}/artifacts",
            base_url=base_url,
            params={"version": version} if version else None,
            actor=actor,
        )
    except Exception as exc:
        st.info(f"Não foi possível carregar lista de artefatos para prévia: {exc}")
        return

    outputs = list(artifacts.get("outputs") or [])
    md_file = _find_md_artifact(outputs)
    if not md_file:
        st.info("Nenhum arquivo Markdown encontrado nos outputs desta versão.")
        return

    try:
        payload = fetch_artifact_bytes(base_url, project_id, "outputs", md_file, version, actor)
        text = payload.decode("utf-8", errors="replace")
        st.caption(f"Arquivo exibido: {md_file}")
        _render_md_with_mermaid(text)
        with st.expander("Ver fonte do Markdown", expanded=False):
            st.code(text, language="markdown")
    except Exception as exc:
        st.warning(f"Falha ao renderizar prévia de {md_file}: {exc}")


