"""Skill 10 — Adapter de Saída (gera JSON + Excel .xlsm) — cash flow mensal (distribuição uniforme)."""

from datetime import date

from concilium.domain.models.canonical import CanonicalModel

from ._planejamento import _MESES_PT  # ty: ignore[unresolved-import]


def _cash_flow_rows(canonical_in: CanonicalModel, project_months: list[tuple[int, int]]) -> list[dict]:
    if not project_months:
        return []
    receita_total = float(canonical_in.resultado.venda.total_com_bdi) if canonical_in.resultado else 0.0
    despesa_total = float(canonical_in.resultado.custo.total) if canonical_in.resultado else 0.0
    n = max(1, len(project_months))
    rec_m = receita_total / n
    des_m = despesa_total / n
    acc = 0.0
    rows: list[dict] = []
    for ym in project_months:
        saldo = rec_m - des_m
        acc += saldo
        rows.append(
            {
                "mes": ym,
                "mes_label": _fmt_mes(ym),
                "receita": round(rec_m, 2),
                "despesa": round(des_m, 2),
                "saldo": round(saldo, 2),
                "exposicao": round(acc, 2),
            }
        )
    return rows


def _week_to_month(week_key: str) -> tuple[int, int]:
    year_str, week_str = week_key.split("-W")
    monday = date.fromisocalendar(int(year_str), int(week_str), 1)
    return monday.year, monday.month


def _fmt_mes(ym: tuple[int, int]) -> str:
    return f"{_MESES_PT[ym[1]]}/{str(ym[0])[-2:]}"


def _next_month(ym: tuple[int, int]) -> tuple[int, int]:
    year, month = ym
    return (year + 1, 1) if month == 12 else (year, month + 1)


