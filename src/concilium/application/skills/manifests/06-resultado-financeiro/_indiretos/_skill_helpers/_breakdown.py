"""Skill 06 (_indiretos) — Indiretos (ADR-009, ADR-023 §D4).

Breakdown semanal de permanência e MOB.
"""

from __future__ import annotations

from concilium.domain.constants import SEMANAS_POR_MES as _SEMANAS_POR_MES  # ADR-056 §T3
from concilium.domain.models.canonical import (
    IndirectoCategoria,
    IndiretoSemanal,
)


def _breakdown_permanencia_override(
    categoria: IndirectoCategoria,
    n_semanas: int,
    custo_total_override: float,
    mo_mensal: float,
    eq_mensal: float,
    mensal_total: float,
) -> list[IndiretoSemanal]:
    """Distribui custo_total_override pelas semanas preservando a proporção dos componentes."""
    result: list[IndiretoSemanal] = []
    # Preserva a proporção entre componentes e garante soma semanal == custo total utilizado na categoria.
    frac_mo = mo_mensal / mensal_total
    frac_eq = eq_mensal / mensal_total

    custo_sem_base = round(float(custo_total_override) / n_semanas, 2)
    acumulado = 0.0
    for w in range(n_semanas):
        if w < (n_semanas - 1):
            custo_sem = custo_sem_base
        else:
            custo_sem = round(float(custo_total_override) - acumulado, 2)
        acumulado += custo_sem

        mo_sem = round(custo_sem * frac_mo, 2)
        eq_sem = round(custo_sem * frac_eq, 2)
        vb_sem = round(custo_sem - mo_sem - eq_sem, 2)

        result.append(
            IndiretoSemanal(
                semana=w,
                categoria=categoria.categoria,
                custo_mao_de_obra=mo_sem,
                custo_equipamentos=eq_sem,
                custo_verbas=vb_sem,
                custo_semanal=round(custo_sem, 2),
                ativa=True,
            )
        )
    return result


def _breakdown_permanencia_default(
    categoria: IndirectoCategoria,
    n_semanas: int,
    mo_mensal: float,
    eq_mensal: float,
    vb_mensal: float,
) -> list[IndiretoSemanal]:
    result: list[IndiretoSemanal] = []
    mo_sem = mo_mensal / _SEMANAS_POR_MES
    eq_sem = eq_mensal / _SEMANAS_POR_MES
    vb_sem = vb_mensal / _SEMANAS_POR_MES
    custo_sem = mo_sem + eq_sem + vb_sem
    for w in range(n_semanas):
        result.append(
            IndiretoSemanal(
                semana=w,
                categoria=categoria.categoria,
                custo_mao_de_obra=round(mo_sem, 2),
                custo_equipamentos=round(eq_sem, 2),
                custo_verbas=round(vb_sem, 2),
                custo_semanal=round(custo_sem, 2),
                ativa=True,
            )
        )
    return result


def _breakdown_mob(categoria: IndirectoCategoria, n_semanas: int) -> list[IndiretoSemanal]:
    # MOB: split entre semana 0 e semana final
    result: list[IndiretoSemanal] = []
    metade = round(categoria.custo_fixo_total / 2, 2)
    for w in range(n_semanas):
        ativa = w == 0 or w == (n_semanas - 1)
        custo_w = metade if ativa else 0.0
        result.append(
            IndiretoSemanal(
                semana=w,
                categoria=categoria.categoria,
                custo_mao_de_obra=0.0,
                custo_equipamentos=0.0,
                custo_verbas=round(custo_w, 2) if ativa else 0.0,
                custo_semanal=round(custo_w, 2),
                ativa=ativa,
            )
        )
    return result


def _build_semanal_breakdown(
    categoria: IndirectoCategoria,
    n_semanas: int,
    custo_total_override: float | None = None,
) -> list[IndiretoSemanal]:
    """Gera breakdown semanal para uma categoria (ADR-009 §D2)."""
    if categoria.driver == "permanencia":
        mo_mensal = categoria.mao_de_obra.custo_fixo_mensal if categoria.mao_de_obra else 0.0
        eq_mensal = categoria.equipamentos.custo_fixo_mensal if categoria.equipamentos else 0.0
        vb_mensal = categoria.verbas.custo_fixo_mensal if categoria.verbas else 0.0
        mensal_total = mo_mensal + eq_mensal + vb_mensal

        if custo_total_override is not None and n_semanas > 0 and mensal_total > 0:
            return _breakdown_permanencia_override(
                categoria, n_semanas, float(custo_total_override), mo_mensal, eq_mensal, mensal_total
            )

        return _breakdown_permanencia_default(categoria, n_semanas, mo_mensal, eq_mensal, vb_mensal)

    return _breakdown_mob(categoria, n_semanas)


