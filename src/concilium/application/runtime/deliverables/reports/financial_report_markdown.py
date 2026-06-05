"""Renderização principal do relatório financeiro em Markdown."""

from __future__ import annotations

from .report_calibration_sections import render_equilibrium_section, render_insights_section
from .report_markdown_sections import (
    render_compressao_cronograma,
    render_executive_summary,
    render_header,
    render_oportunidades,
    render_planejamento_table,
    render_resultado,
)


def render_financial_report_markdown(relatorio: dict, canonical: object | None = None) -> str:
    """Gera Markdown analítico modular do payload de relatório."""
    meta = relatorio.get("meta", {}) if isinstance(relatorio, dict) else {}
    resumo = relatorio.get("resumo", {}) if isinstance(relatorio, dict) else {}
    resultado = relatorio.get("RESULTADO", {}) if isinstance(relatorio, dict) else {}
    planejamento = relatorio.get("PLANEJAMENTO", []) if isinstance(relatorio, dict) else []
    ponto_equilibrio = relatorio.get("ponto_equilibrio") or relatorio.get("PONTO_EQUILIBRIO") or []
    insights = relatorio.get("ACTIONABLE_INSIGHTS", []) if isinstance(relatorio, dict) else []
    # ADR-078: grafo de oportunidades de compartilhamento (se presente no payload)
    oportunidades = relatorio.get("relatorio_oportunidades") if isinstance(relatorio, dict) else None
    # NEP-038: análise de compressão de cronograma
    compressao = relatorio.get("COMPRESSAO_CRONOGRAMA") if isinstance(relatorio, dict) else None

    lines = []
    lines += render_header(meta, resumo)
    lines += render_executive_summary(resumo, resultado)
    lines += render_resultado(resultado)
    lines += render_planejamento_table(planejamento)
    lines += render_equilibrium_section(ponto_equilibrio, resultado)
    lines += render_oportunidades(oportunidades)
    lines += render_compressao_cronograma(compressao)
    lines += render_insights_section(insights)
    return "\n".join(lines)


__all__ = ["render_financial_report_markdown"]
