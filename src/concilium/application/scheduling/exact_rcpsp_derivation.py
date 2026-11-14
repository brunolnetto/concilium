"""Derive the per-resource ``rcpsp_spec`` of a project from its own data (#206).

The exact path (P15 physical witness, P16 pool ledger) needs, for every
activity, the units of each resource type one front mobilises, and the
physical pool the project owns. Projects used to get this only when a caller
hand-wrote ``rcpsp_spec``; here it is read from what the project already
declares:

- ``required_resources``: the production's standard team — units per front of
  each equipment and labour function (``a_ig^front``, N7);
- ``duration_weeks``: the nominal one-front duration ``ceil(Q / (rho*d*h))``;
- ``resource_pool``: the explicitly configured physical pool (Skill03).

Nothing is inferred: a missing CPU, production, team, rate or pool coverage is
returned as a reason and no spec is produced.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from fractions import Fraction
from typing import Any


def _index(rows: object, *keys: str) -> dict[str, Mapping[str, Any]]:
    index: dict[str, Mapping[str, Any]] = {}
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, Mapping):
                for key in keys:
                    if row.get(key):
                        index[str(row[key])] = row
                        break
    return index


def _team_units(team: object) -> dict[str, int] | None:
    if not isinstance(team, Mapping):
        return None
    units: dict[str, int] = {}
    for field, id_key, count_key in (
        ("equipamentos", "equip_id", "num_unidades"),
        ("funcoes", "funcao_id", "num_pessoas"),
    ):
        for row in team.get(field) or []:
            if not isinstance(row, Mapping) or not row.get(id_key):
                return None
            count = row.get(count_key)
            if isinstance(count, bool) or not isinstance(count, (int, float)) or count <= 0 or count != int(count):
                return None
            units[str(row[id_key])] = units.get(str(row[id_key]), 0) + int(count)
    return units or None


def configured_pool(canonical: Any) -> dict[str, int]:
    """Only explicitly configured physical availability counts as a pool."""
    pool: dict[str, int] = {}
    for item in getattr(canonical, "recurso_pool", None) or []:
        if getattr(item, "proveniencia", None) == "CONFIGURADO":
            pool[item.tipo_id] = pool.get(item.tipo_id, 0) + int(item.quantidade_total)
    return pool


def derive_exact_rcpsp_spec(canonical: Any, catalogo: Mapping[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    """``(spec, reasons)``: the per-resource spec, or ``None`` and why not."""
    reasons: list[str] = []
    projeto = getattr(canonical, "projeto", None)
    regime = getattr(projeto, "regime_trabalho", None)
    if regime is None:
        return None, ["project work regime (days/week, hours/day) is not declared"]
    try:
        hours_per_week = Fraction(str(regime.dias_semana)) * Fraction(str(regime.horas_dia))
    except (AttributeError, ValueError, ZeroDivisionError):
        return None, ["project work regime (days/week, hours/day) is not declared"]
    if hours_per_week <= 0:
        return None, ["project work regime must have positive weekly hours"]

    cpus = _index(catalogo.get("cpus"), "codigo")
    productions = _index(catalogo.get("producoes") or catalogo.get("produtividades"), "id", "codigo")
    pool = configured_pool(canonical)
    if not pool:
        reasons.append("no explicitly configured physical pool (Skill03)")

    activities: list[dict[str, Any]] = []
    used: set[str] = set()
    for item in getattr(canonical, "eap", None) or []:
        item_id = item.item_id
        cpu = cpus.get(str(getattr(item, "cpu_id", "") or ""))
        if cpu is None:
            reasons.append(f"{item_id}: CPU {getattr(item, 'cpu_id', None)!r} is absent from the catalog")
            continue
        production = productions.get(str(cpu.get("producao_id_ref") or ""))
        if production is None:
            reasons.append(f"{item_id}: CPU has no production record")
            continue
        team = _team_units(production.get("composicao_padrao_equipe"))
        if team is None:
            reasons.append(f"{item_id}: production has no valid standard team composition")
            continue
        try:
            rate = Fraction(str(production.get("producao_horaria")))
            quantity = Fraction(str(item.quantitativo))
        except (ValueError, ZeroDivisionError):
            reasons.append(f"{item_id}: production rate or quantity is not a finite number")
            continue
        if rate <= 0 or quantity <= 0:
            reasons.append(f"{item_id}: production rate and quantity must be positive")
            continue
        short = sorted(g for g, units in team.items() if pool.get(g, 0) < units)
        if pool and short:
            reasons.append(f"{item_id}: configured pool does not cover one front of {', '.join(short)}")
        used.update(team)
        activities.append(
            {
                "item_id": item_id,
                "descricao": getattr(item, "descricao", None) or item_id,
                "duration_weeks": max(1, math.ceil(quantity / (rate * hours_per_week))),
                "required_resources": dict(sorted(team.items())),
            }
        )
    if not activities and not reasons:
        reasons.append("project has no EAP items")
    if reasons:
        return None, reasons
    return {
        "activities": activities,
        "resource_pool": {g: pool[g] for g in sorted(used)},
        "precedence": [],
        "derivation": "exact_rcpsp_derivation/1",
    }, []
