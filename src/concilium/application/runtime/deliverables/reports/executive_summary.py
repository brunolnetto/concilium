"""ADR-093 D5 — Resumo executivo de 1 página para decisores.

Documento curto, separado do relatório técnico, contendo o essencial para uma
decisão: status de aprovação, preço operacional e margem, atividades mais
críticas e os levers de ponto de equilíbrio com maior potencial de melhoria.

Best-effort: cada seção degrada graciosamente quando o dado não está disponível,
de modo que o resumo é sempre gerável a partir do payload de relatório + canônico.
"""

from __future__ import annotations

from typing import Any

from .report_markdown_sections import _brl, _pct


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _top_criticas(canonical: Any, n: int = 3) -> list[dict[str, Any]]:
    """Top-N atividades mais críticas (menor rank_lexicografico)."""
    report = _get(canonical, "cost_criticality_report")
    atividades = _get(report, "atividades", []) or []
    norm: list[dict[str, Any]] = []
    for a in atividades:
        norm.append(
            {
                "atividade_id": _get(a, "atividade_id", "?"),
                "classe": _get(a, "classe", "?"),
                "rank": _get(a, "rank_lexicografico", 9999) or 9999,
                "interpretacao": _get(a, "interpretacao", "") or "",
            }
        )
    norm.sort(key=lambda x: x["rank"])
    return norm[:n]


def _top_levers(canonical: Any, n: int = 3) -> list[dict[str, Any]]:
    """Levers de ponto de equilíbrio viáveis, ordenados por delta_margin desc."""
    pes = _get(canonical, "ponto_equilibrio", []) or []
    levers: list[dict[str, Any]] = []
    for pe in pes:
        item_id = _get(pe, "item_id", "?")
        for lv in _get(pe, "levers_equilibrio", []) or []:
            if not _get(lv, "viavel", False):
                continue
            levers.append(
                {
                    "item_id": item_id,
                    "id": _get(lv, "id", "?"),
                    "descricao": _get(lv, "descricao", "") or "",
                    "delta_margin": float(_get(lv, "delta_margin", 0.0) or 0.0),
                }
            )
    levers.sort(key=lambda x: x["delta_margin"], reverse=True)
    return levers[:n]


def render_resumo_executivo(relatorio: dict[str, Any], canonical: Any | None = None) -> str:
    """Gera o ``resumo_executivo.md`` (1 página) a partir do relatório + canônico."""
    meta = relatorio.get("meta", {}) if isinstance(relatorio, dict) else {}
    resumo = relatorio.get("resumo", {}) if isinstance(relatorio, dict) else {}
    resultado = relatorio.get("RESULTADO", {}) if isinstance(relatorio, dict) else {}

    nome = resumo.get("projeto") or meta.get("projeto") or "Projeto"
    status = resumo.get("status") or "—"
    periodo = resumo.get("periodo") or ""

    preco = float(resultado.get("preco_venda_total") or 0)
    custo_total = float(resultado.get("custo_total") or 0)
    resultado_bruto = float(resultado.get("resultado_bruto") or 0)
    margem_pct = float(resultado.get("margem_pct") or 0)
    status_margem = str(resultado.get("status_margem") or "—")

    semaforo = {"VERDE": "🟢", "AMARELO": "🟡", "VERMELHO": "🔴"}.get(status_margem, "⚪")

    lines: list[str] = [
        f"# Sumário Executivo — {nome}",
        "",
        f"**Status do plano:** {status}" + (f" · **Período:** {periodo}" if periodo else ""),
        "",
        "## Dimensionamento Financeiro",
        "",
        "| Indicador | Valor |",
        "|-----------|------:|",
        f"| Preço de venda | {_brl(preco)} |",
        f"| Custo total | {_brl(custo_total)} |",
        f"| Resultado bruto | {_brl(resultado_bruto)} |",
        f"| Margem | {_pct(margem_pct)} {semaforo} ({status_margem}) |",
        "",
    ]

    criticas = _top_criticas(canonical, 3)
    if criticas:
        lines += ["## Atividades Críticas do Cronograma", ""]
        for c in criticas:
            interp = c["interpretacao"][:90]
            lines.append(f"- **{c['atividade_id']}** (classe {c['classe']}) — {interp}")
        lines.append("")

    levers = _top_levers(canonical, 3)
    if levers:
        lines += [
            "## Alavancas de Viabilidade (Ponto de Equilíbrio)",
            "",
            "| Item | Alavanca | Ganho potencial de margem |",
            "|------|----------|--------------------------:|",
        ]
        for lv in levers:
            desc = (lv["descricao"] or lv["id"])[:60]
            lines.append(f"| {lv['item_id']} | {desc} | {_brl(lv['delta_margin'])} |")
        lines.append("")

    lines += ["---", "", "_Documento gerado automaticamente para decisores (ADR-093)._"]
    return "\n".join(lines)


__all__ = ["render_resumo_executivo"]
