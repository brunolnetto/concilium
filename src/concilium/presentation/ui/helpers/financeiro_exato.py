"""Lógica (sem Streamlit) das telas que mostram o financeiro exato (#206, W3-A).

As telas leem somente a visão exata única
(`concilium.application.scheduling.exact_financial_view`) gravada no resumo da
execução em `summary["financeiro_exato"]`: camadas de markup (custo, overhead,
lucro, tributos), preço e estados dos gates. Não há semáforo de margem nem
números legados; quando o financeiro exato não foi avaliado a tela diz
"não avaliado" com os motivos e como resolver.

Os valores exibidos são aproximações de exibição dos racionais exatos; o texto
exato fica disponível nas tabelas de detalhe.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from concilium.application.scheduling.exact_financial_view import (
    AVALIADO,
    CATEGORIES,
    certificate_decision,
    format_money,
    format_percent,
    reason_lines,
    view_from_summary,
)

NAO_AVALIADO_TEXTO = "não avaliado"
APROXIMACAO_TEXTO = "Valores aproximados para exibição; os racionais exatos estão na tabela de detalhe."

_DELTA_LABELS = {
    "custo_total": ("Custo total", "money"),
    "custo_direto": ("Custo direto", "money"),
    "custo_indireto": ("Custo indireto", "money"),
    "preco": ("Preço", "money"),
    "camada_overhead": ("Camada de overhead", "money"),
    "camada_lucro": ("Camada de lucro", "money"),
    "camada_tributos": ("Camada de tributos", "money"),
    "participacao_lucro_no_preco": ("Participação do lucro no preço", "percent"),
    "bdi_sobre_catalogo": ("BDI sobre catálogo", "percent"),
}


def _map(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _brl(value: Any) -> str:
    text = format_money(value)
    return text if text == "—" else f"R$ {text}"


def summary_view(summary: Any) -> dict[str, Any]:
    """A visão exata de um resumo de execução (não avaliada quando o resumo é anterior a ela)."""
    return view_from_summary(summary)


def is_evaluated(view: Mapping[str, Any]) -> bool:
    return view.get("status") == AVALIADO


def not_evaluated_lines(view: Mapping[str, Any]) -> list[str]:
    """Motivos (com o que falta e como resolver) de um financeiro não avaliado."""
    return reason_lines(view) or ["Motivo não registrado."]


def layer_cards(view: Mapping[str, Any]) -> list[dict[str, str]]:
    """Cartões das camadas de markup: custo, overhead, lucro, tributos e preço."""
    if not is_evaluated(view):
        return []
    layers = _map(view.get("layers"))
    return [
        {"label": "Custo total", "value": _brl(layers.get("cost"))},
        {"label": "Overhead", "value": _brl(layers.get("overhead"))},
        {"label": "Lucro", "value": _brl(layers.get("profit"))},
        {"label": "Tributos", "value": _brl(layers.get("taxes"))},
        {"label": "Preço", "value": _brl(view.get("price"))},
    ]


def gate_rows(view: Mapping[str, Any], certificate: Any = None) -> list[dict[str, str]]:
    """Estados dos gates de preço e, quando fornecido, do certificado P23 da execução."""
    rows: list[dict[str, str]] = []
    if is_evaluated(view):
        gates = _map(view.get("gates"))
        reasons = "; ".join(str(r) for r in gates.get("reasons") or []) or "-"
        rows.extend([
            {
                "gate": "Piso regulatório de BDI",
                "status": str(gates.get("regulatory_status") or "-"),
                "detalhe": (
                    f"BDI sobre a base regulatória {format_percent(view.get('regulatory_bdi_rate'))}; "
                    f"piso ponderado {format_percent(view.get('regulatory_bdi_floor'))}"
                ),
            },
            {
                "gate": "Camada de lucro",
                "status": str(gates.get("profitability_status") or "-"),
                "detalhe": (
                    f"participação do lucro no preço {format_percent(view.get('profit_layer_share'))}; "
                    f"mínimo {format_percent(view.get('minimum_profit_margin'))}"
                ),
            },
            {"gate": "Gates de preço (P21)", "status": str(gates.get("status") or "-"), "detalhe": reasons},
        ])
        below = view.get("categories_below_floor")
        if below:
            rows.append({
                "gate": "Piso de BDI por categoria",
                "status": "ABAIXO",
                "detalhe": "categorias abaixo do piso: " + ", ".join(str(c) for c in below),
            })
    cert = _map(certificate)
    if cert:
        rows.append({
            "gate": "Certificado P23",
            "status": certificate_decision(cert),
            "detalhe": f"situação {cert.get('status') or 'NOT_EVALUATED'}"
            + ("; " + "; ".join(str(r) for r in cert.get("reasons") or []) if cert.get("reasons") else ""),
        })
        for gate in cert.get("gates") or []:
            if isinstance(gate, Mapping):
                rows.append({
                    "gate": f"P23 {gate.get('gate_id', '-')}",
                    "status": str(gate.get("status") or "-"),
                    "detalhe": str(gate.get("reason") or "-"),
                })
    return rows


def category_rows(view: Mapping[str, Any]) -> list[dict[str, str]]:
    """Camadas por categoria, com o racional exato e a aproximação de exibição do preço."""
    if not is_evaluated(view):
        return []
    by_category = _map(view.get("by_category"))
    rates = _map(view.get("bdi_rate_by_category"))
    floors = _map(view.get("bdi_floor_by_category"))
    rows = []
    for category in CATEGORIES:
        row = _map(by_category.get(category))
        rows.append({
            "categoria": category,
            "custo": _brl(row.get("cost")),
            "overhead": _brl(row.get("overhead")),
            "lucro": _brl(row.get("profit")),
            "tributos": _brl(row.get("taxes")),
            "preço": _brl(row.get("price")),
            "BDI": format_percent(rates.get(category)),
            "piso BDI": format_percent(floors.get(category)),
            "preço (exato)": str(row.get("price") or "-"),
        })
    return rows


def exact_rows(view: Mapping[str, Any]) -> list[dict[str, str]]:
    """Totais como racionais exatos (a fonte dos valores exibidos)."""
    if not is_evaluated(view):
        return []
    cost, layers, site = _map(view.get("cost")), _map(view.get("layers")), _map(view.get("site_indirects"))
    pairs = [
        ("Custo total", cost.get("total")),
        ("Custo direto", cost.get("direct")),
        ("Custo indireto", cost.get("indirect")),
        ("Camada de overhead", layers.get("overhead")),
        ("Camada de lucro", layers.get("profit")),
        ("Camada de tributos", layers.get("taxes")),
        ("Preço", view.get("price")),
        ("Participação do lucro no preço", view.get("profit_layer_share")),
        ("Referência de catálogo", view.get("catalog_benchmark")),
        ("BDI sobre catálogo", view.get("bdi_on_catalog")),
        ("Piso ponderado de BDI", view.get("regulatory_bdi_floor")),
        (f"Indiretos de canteiro ({site.get('scope_status') or '-'})", site.get("cost")),
    ]
    return [{"grandeza": label, "valor exato": str(value) if value is not None else "-"} for label, value in pairs]


def run_row_cells(summary: Any) -> dict[str, str]:
    """Células financeiras de uma linha da tabela de execuções."""
    view = summary_view(summary)
    if not is_evaluated(view):
        return {"Custo": NAO_AVALIADO_TEXTO, "Preço": NAO_AVALIADO_TEXTO, "Gates de preço": NAO_AVALIADO_TEXTO}
    return {
        "Custo": _brl(_map(view.get("cost")).get("total")),
        "Preço": _brl(view.get("price")),
        "Gates de preço": str(_map(view.get("gates")).get("status") or "-"),
    }


def delta_rows(deltas: Any) -> list[dict[str, str]]:
    """Linhas dos deltas exatos entre duas versões (direita − esquerda)."""
    exact = _map(_map(deltas).get("financeiro_exato"))
    values = _map(exact.get("deltas"))
    rows = []
    for key, (label, kind) in _DELTA_LABELS.items():
        value = values.get(key)
        if value is None:
            shown = NAO_AVALIADO_TEXTO
        elif kind == "money":
            shown = _brl(value)
        else:
            shown = format_percent(value).replace("%", " p.p.")
        rows.append({"indicador": label, "delta": shown, "delta (exato)": str(value) if value is not None else "-"})
    return rows


def delta_not_evaluated_lines(deltas: Any) -> list[str]:
    """Motivos, por lado, de uma comparação financeira não avaliada."""
    exact = _map(_map(deltas).get("financeiro_exato"))
    if exact.get("status") == AVALIADO:
        return []
    if not exact:
        return ["Comparação sem financeiro exato: motivo não registrado."]
    sides = {"left": "versão esquerda", "right": "versão direita"}
    lines = []
    for reason in exact.get("reasons") or []:
        if not isinstance(reason, Mapping):
            continue
        text = reason_lines({"reasons": [reason]})
        lines.append(f"{sides.get(str(reason.get('side')), 'versão')}: {text[0] if text else 'motivo não registrado.'}")
    return lines or ["Motivo não registrado."]
