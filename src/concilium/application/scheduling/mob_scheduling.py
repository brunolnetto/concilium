"""MOB (Mobilização/Desmobilização) Scheduling — ADR-105

Inferência automática de janelas de mobilização baseado em:
- Datas de projeto (meta.data_inicio, meta.data_termino)
- Datas de EAP (primeira/última atividade via topological sort de predecessores)

Outputs:
- mob_windows: Datas de início e fim de cada fase (mobilizacao, operacao, desmobilizacao)
- mob_costs: Distribuição de custos conforme driver (projeto vs mensal)
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any


def _iso_week_key(d: date) -> str:
    """Retorna chave ISO 'AAAA-Www' para uma data."""
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _parse_date(date_str: str | date) -> date:
    """Converte string ISO (YYYY-MM-DD) ou date object para date."""
    if isinstance(date_str, date):
        return date_str
    if isinstance(date_str, str):
        return date.fromisoformat(date_str)
    raise TypeError(f"Expected date or str, got {type(date_str)}")


def _topological_sort_eap(eap_items: list[dict]) -> list[dict]:
    """Retorna EAP items em ordem topológica (respeitando predecessores).

    Simples DFS sem ciclos — assume predecessores válidos.
    """
    # Build adjacency
    graph = {item["item_id"]: item for item in eap_items}
    deps = {item["item_id"]: {p["item_id"] for p in item.get("predecessores", [])} for item in eap_items}

    visited = set()
    order = []

    def visit(item_id: str):
        if item_id in visited:
            return
        visited.add(item_id)
        for dep_id in deps.get(item_id, set()):
            if dep_id in graph:
                visit(dep_id)
        order.append(graph[item_id])

    for item_id in graph:
        visit(item_id)

    return order


def infer_mob_windows(
    meta: dict[str, Any],
    spec_eap: list[dict[str, Any]],
    safety_margin_days: int = 7,
) -> dict[str, dict[str, date]]:
    """Calcula janelas de mobilização automáticamente.

    Args:
        meta: Dicionário com data_inicio e data_termino
        spec_eap: Lista de items de EAP com predecessores
        safety_margin_days: Dias de margem antes da primeira e após última atividade EAP

    Returns:
        {
            "mobilizacao": {"inicio": date, "fim": date},
            "operacao": {"inicio": date, "fim": date},
            "desmobilizacao": {"inicio": date, "fim": date}
        }
    """
    project_start = _parse_date(meta["data_inicio"])
    project_end = _parse_date(meta["data_termino"])

    # Calcular datas de EAP
    # Simplificado: assume que primeiro item começa no project_start,
    # e duram conforme precedências (aqui apenas assumindo ordem)
    sorted_eap = _topological_sort_eap(spec_eap)

    if not sorted_eap:
        # Sem EAP, usar project dates
        first_eap_date = project_start
        last_eap_date = project_end
    else:
        # Primeira atividade começa projeto_start
        # Última termina projeto_end (simplificado)
        first_eap_date = project_start
        last_eap_date = project_end

    # Janelas com margem
    mob_start = project_start
    mob_end = first_eap_date - timedelta(days=safety_margin_days)
    if mob_end < mob_start:
        mob_end = first_eap_date  # Sem margem se espaço insuficiente

    op_start = project_start
    op_end = last_eap_date + timedelta(days=safety_margin_days)
    if op_end > project_end:
        op_end = project_end

    demob_start = last_eap_date
    demob_end = project_end

    return {
        "mobilizacao": {"inicio": mob_start, "fim": mob_end},
        "operacao": {"inicio": op_start, "fim": op_end},
        "desmobilizacao": {"inicio": demob_start, "fim": demob_end},
    }


def calcular_custo_indireto_mob(
    indiretos: list[dict[str, Any]],
    mob_windows: dict[str, dict[str, date]],
) -> dict[str, Any]:
    """Distribui custos de MOB segundo driver (projeto vs mensal).

    Args:
        indiretos: Lista de dicts com tipo, fase, driver, custo_fixo_*
        mob_windows: Output de infer_mob_windows()

    Returns:
        {
            "mob": {
                "mobilizacao": {"custo_total": float, "semana_inicio": str},
                "operacao": {"custo_mensal": float, "duracao_meses": float, "total": float},
                "desmobilizacao": {"custo_total": float, "semana_inicio": str}
            },
            "custo_mob_total": float
        }
    """
    mob: dict[str, dict[str, Any]] = {}
    resultado: dict[str, Any] = {"mob": mob, "custo_mob_total": 0.0}

    for indireto in indiretos:
        if indireto.get("tipo") != "MOB":
            continue

        fase = indireto.get("fase")  # "mobilizacao", "operacao", "desmobilizacao"
        if fase not in mob_windows:
            continue

        driver = indireto.get("driver")
        window = mob_windows[fase]

        if driver == "projeto":
            # Custo incorre na primeira semana da fase
            custo_total = indireto.get("custo_fixo_total", 0.0)
            mob[fase] = {
                "custo_total": custo_total,
                "semana_inicio": _iso_week_key(window["inicio"]),
            }
            resultado["custo_mob_total"] += custo_total

        elif driver == "mensal":
            # Distribuir ao longo da janela
            custo_mensal = indireto.get("custo_fixo_mensal", 0.0)
            duracao_dias = (window["fim"] - window["inicio"]).days + 1
            duracao_meses = duracao_dias / 30.5  # Média mensal
            total = custo_mensal * duracao_meses

            mob[fase] = {
                "custo_mensal": custo_mensal,
                "duracao_meses": duracao_meses,
                "duracao_dias": duracao_dias,
                "total": total,
            }
            resultado["custo_mob_total"] += total

    return resultado


def get_mob_summary(mob_costs: dict[str, Any]) -> dict[str, float]:
    """Extrai resumo de custos MOB por fase."""
    summary = {}
    for fase, dados in mob_costs.get("mob", {}).items():
        if "custo_total" in dados:
            summary[fase] = dados["custo_total"]
        elif "total" in dados:
            summary[fase] = dados["total"]
    return summary
