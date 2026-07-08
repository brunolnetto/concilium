"""Camada de apresentação — layout Streamlit (parte extraída de layout.py)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import streamlit as st

if TYPE_CHECKING:
    from concilium.domain.models.analytics.diagnostico_pe import DiagnosticoPERelatorio
    from concilium.domain.models.financial.backtracking_pe import (
        BacktrackingPERelatorio,
    )


def _wizard_opcao_L(diagnostico: DiagnosticoPERelatorio | None, opcoes: list) -> None:
    """Appends the L (BDI margin) option if diagnostico is valid."""
    if diagnostico is None:
        return
    delta = diagnostico.l_medio_requerido - (
        diagnostico.itens_deficit[0].l_aplicado if diagnostico.itens_deficit else 0.09
    )
    gap_pct = 100 if diagnostico.gap_total_rs else 0
    opcoes.append(
        (
            "L",
            "Ajustar a margem no orçamento (BDI)",
            f"Estimativa: fecha {gap_pct}% do gap — preço sobe ~{delta * 100:.1f}pp",
        )
    )


def _wizard_janelas_prioritarias(diagnostico: DiagnosticoPERelatorio | None) -> list[dict]:
    """Extrai as janelas prioritárias do bloco de explicação natureza×período do diagnóstico."""
    bloco_explicacao = getattr(diagnostico, "explicacao_natureza_periodo", {}) if diagnostico else {}
    if not isinstance(bloco_explicacao, dict):
        return []
    raw_janelas = bloco_explicacao.get("janelas_prioritarias")
    if not isinstance(raw_janelas, list):
        return []
    return [j for j in raw_janelas if isinstance(j, dict)]


def _collect_wizard_params_disponiveis(backtracking: BacktrackingPERelatorio | None) -> dict[str, list[str]]:
    """Agrupa, por parâmetro, as descrições dos itens de backtracking com solução de roundtrip válida."""
    params_disponiveis: dict[str, list[str]] = {}
    for bt_item in backtracking.itens if backtracking else ():
        for sol in bt_item.solucoes:
            if sol.roundtrip_valido:
                params_disponiveis.setdefault(sol.parametro, []).append(bt_item.descricao[:40])
    return params_disponiveis


def _wizard_t0_ramp_opcao(janelas_prioritarias: list[dict]) -> tuple[str, str, str]:
    """Monta a opção T0_RAMP do wizard, priorizando a janela climática mais crítica quando disponível."""
    timing_msg = "Estima eliminar custo de época desfavorável sem repasse ao cliente"
    if janelas_prioritarias:
        top = janelas_prioritarias[0]
        janela = top.get("janela_iso")
        natureza = top.get("natureza")
        if janela and natureza:
            timing_msg = f"Prioriza janela {janela} com causa dominante {natureza}"
    return ("T0_RAMP", "Mudar quando as atividades começam (cronograma)", timing_msg)


def _build_wizard_deficit_opcoes(
    diagnostico: DiagnosticoPERelatorio | None, backtracking: BacktrackingPERelatorio | None
) -> list[tuple[str, str, str]]:
    """Builds the wizard option tuples from backtracking data."""
    opcoes: list[tuple[str, str, str]] = []
    janelas_prioritarias = _wizard_janelas_prioritarias(diagnostico)
    params_disponiveis = _collect_wizard_params_disponiveis(backtracking)
    if "L" in params_disponiveis:
        _wizard_opcao_L(diagnostico, opcoes)
    if "T0_RAMP" in params_disponiveis:
        opcoes.append(_wizard_t0_ramp_opcao(janelas_prioritarias))
    if "P" in params_disponiveis:
        opcoes.append(
            ("P", "Melhorar produtividade dos equipamentos", "Requer calibração de CPU ou upgrade de equipamento")
        )
    if "N_MAX" in params_disponiveis:
        opcoes.append(("N_MAX", "Aumentar equipes em paralelo", "Comprime o prazo e reduz overhead fixo"))
    return opcoes


def render_version_wizard(
    base_url: str,
    project: dict,
    actor: str,
    diagnostico: DiagnosticoPERelatorio | None = None,
    backtracking: BacktrackingPERelatorio | None = None,
) -> str | None:
    """Wizard de criação de versão com foco no diagnóstico (ADR-060/061 UI).

    Retorna o foco selecionado ("L" | "P" | "N_MAX" | "T0_RAMP" | "LIVRE" | None).
    """
    project_id = project["project_id"]
    st.subheader("✚ Nova versão — O que você quer tentar?")

    tem_deficit = diagnostico and diagnostico.n_itens_deficit > 0
    opcoes: list[tuple[str, str, str]] = []
    if tem_deficit and backtracking and backtracking.itens:
        opcoes = _build_wizard_deficit_opcoes(diagnostico, backtracking)
    opcoes.append(("LIVRE", "Explorar livremente", "Abre o painel de planejamento sem foco específico"))

    labels = [f"{o[1]}\n  ↳ {o[2]}" for o in opcoes]
    escolha = st.radio("", labels, index=len(labels) - 1, key=f"wizard-{project_id}")
    idx = labels.index(escolha)
    foco = opcoes[idx][0]

    col1, col2 = st.columns([3, 1])
    if col2.button("Criar versão →", type="primary", key=f"wizard-create-{project_id}"):
        return foco
    return None


