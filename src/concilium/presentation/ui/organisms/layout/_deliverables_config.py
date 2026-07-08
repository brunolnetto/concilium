"""Camada de apresentação — layout Streamlit (parte extraída de layout.py)."""

from __future__ import annotations

import streamlit as st

from ...infra.api import api_call


def render_deliverables_config(base_url: str, project_id: str, actor: str) -> None:
    """Configurable output generation panel — artefatos reais de saída."""
    st.caption("Configure quais **outputs** serão gerados no próximo run.")

    try:
        config = api_call(
            method="GET",
            path=f"/api/projects/{project_id}/deliverables-config",
            base_url=base_url,
            actor=actor,
        )
        outputs: dict = config.get("outputs", {})
    except Exception:
        outputs = {}

    def _get(key: str, default: bool = True) -> bool:
        return bool(outputs.get(key, default))

    edited: dict[str, bool] = {}

    # ── Fundamentais (sempre ativos, não desativáveis) ────────────────────
    st.markdown("**📌 Fundamentais** — sempre incluídos na entrega")
    f1, f2, f3 = st.columns(3)
    edited["resultado_xlsx"] = True
    f1.checkbox(
        "📊 resultado.xlsx",
        value=True,
        disabled=True,
        key=f"deliv-{project_id}-xlsx-fixed",
        help="Planilha principal com RESULTADO, BDI, FLUXO.CAIXA",
    )
    edited["relatorio_md"] = True
    f2.checkbox(
        "📝 relatorio.md",
        value=True,
        disabled=True,
        key=f"deliv-{project_id}-rmd-fixed",
        help="Relatório executivo em Markdown",
    )
    edited["memorial_bdi_pdf"] = True
    f3.checkbox(
        "📄 memorial_bdi.pdf",
        value=True,
        disabled=True,
        key=f"deliv-{project_id}-mbdpdf-fixed",
        help="Memorial de cálculo BDI para entrega",
    )

    st.divider()

    # ── Complementares (toggleáveis) ──────────────────────────────────────
    st.markdown("**🔬 Analíticos complementares** — opcionais")
    c1, c2, c3 = st.columns(3)
    edited["aba_memorial_bdi"] = c1.checkbox(
        "MEMORIAL.BDI",
        value=_get("aba_memorial_bdi", True),
        key=f"deliv-{project_id}-aba-bdi",
        help="Aba de auditoria de cálculo BDI no Excel",
    )
    edited["aba_curva_abc"] = c2.checkbox(
        "CURVA.ABC.ATIVIDADES",
        value=_get("aba_curva_abc", True),
        key=f"deliv-{project_id}-aba-abc",
        help="Pareto por atividade (curva ABC atual)",
    )
    edited["aba_curva_abc_composicao"] = c3.checkbox(
        "CURVA.ABC.COMPOSIÇÃO",
        value=_get("aba_curva_abc_composicao", False),
        key=f"deliv-{project_id}-aba-abc-comp",
        help="Pareto por componente de custo (MO, EQ, MAT, DIESEL) — nova aba",
    )
    c4, c5, c6 = st.columns(3)
    edited["aba_s_curve"] = c4.checkbox(
        "S-CURVE",
        value=_get("aba_s_curve", True),
        key=f"deliv-{project_id}-aba-sc",
        help="Curva de desembolso acumulado",
    )
    edited["aba_campanha_frota"] = c5.checkbox(
        "CAMPANHA.FROTA",
        value=_get("aba_campanha_frota", True),
        key=f"deliv-{project_id}-aba-frota",
        help="Permanência de equipamentos",
    )
    edited["relatorio_pdf"] = c6.checkbox(
        "relatorio.pdf",
        value=_get("relatorio_pdf", True),
        key=f"deliv-{project_id}-rpdf",
        help="PDF nativo financeiro (ReportLab)",
    )

    if st.button(
        "Salvar configuração de saídas", key=f"save-deliv-{project_id}", use_container_width=True, type="primary"
    ):
        try:
            api_call(
                method="PUT",
                path=f"/api/projects/{project_id}/deliverables-config",
                base_url=base_url,
                payload={"outputs": edited},
                actor=actor,
            )
            st.success("Salvo.")
        except Exception as exc:
            st.error(f"Erro ao salvar: {exc}")


