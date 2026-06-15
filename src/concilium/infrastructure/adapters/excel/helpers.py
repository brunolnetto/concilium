from __future__ import annotations
from datetime import date
from typing import Any
from concilium.domain.models.canonical import CanonicalModel
from .styles import MESES_PT


def _fmt_mes(ym: tuple[int, int]) -> str:
    return f"{MESES_PT[ym[1]]}/{str(ym[0])[-2:]}"


def _week_to_month(week_str: str) -> tuple[int, int]:
    """'2026-W23' -> (2026, 6) — mês da segunda-feira dessa semana ISO."""
    year_str, w_str = week_str.split("-W")
    monday = date.fromisocalendar(int(year_str), int(w_str), 1)
    return monday.year, monday.month


def _project_months(canonical: CanonicalModel) -> list[tuple[int, int]]:
    """Lista ordenada de (ano, mês) cobrindo todo o projeto."""
    months: set[tuple[int, int]] = set()
    if canonical.cronograma:
        for act in canonical.cronograma.scheduled_activities:
            for week_key in act.distribuicao_semanal:
                months.add(_week_to_month(week_key))
    if not months and canonical.projeto:
        p = canonical.projeto
        if p.data_inicio and p.data_termino:
            d = p.data_inicio
            while d <= p.data_termino:
                months.add((d.year, d.month))
                # Avança para o próximo mês
                if d.month == 12:
                    d = date(d.year + 1, 1, 1)
                else:
                    d = date(d.year, d.month + 1, 1)
    return sorted(months)


def _find_eap_item(eap_list, item_id: str):
    """Linear search for an EAP item by id. Returns None if not found."""
    for e in eap_list:
        if e.item_id == item_id:
            return e
    return None


def coerce_to_cell_value(value: Any) -> Any:
    """Converte valor Python para tipo compatível com célula Excel."""
    if value is None:
        return None
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, dict)):
        if isinstance(value, dict) and len(value) == 1:
            return list(value.values())[0]
        if isinstance(value, list) and len(value) == 1:
            return coerce_to_cell_value(value[0])
        s = str(value)
        if len(s) > 100:
            s = s[:97] + "..."
        return s
    return str(value)
