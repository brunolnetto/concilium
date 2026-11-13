"""Exact catalog envelope C^cat derived from the resolved catalog.

FORMALISMO_LONGO Parts II–III and §XIII/§XIV.8::

    c_r     = V_r^mensal / (s_mes · d · h)     EQ/MO priced per month
    c_r     = price per hour                   EQ/MO priced per hour
    γ_i^K   = Σ_r c_r n_r                      production team of one front
    C_i^cat = Q_i γ_i^K / ρ_i + Q_i Σ_g κ_g^out p_g
    C^cat   = Σ_i C_i^cat                      the BDI basis: BDI = P / C^cat − 1

Sources are fixed and never inferred: the contractual part comes only from the
production record's ``composicao_padrao_equipe`` (ρ_i = its ``producao_horaria``),
the consumable part only from the CPU's MATERIAL/DIESEL/COMBUSTIVEL rows with a
per-delivered-unit coefficient. Anything else (unknown price unit, missing
price, a CPU that also lists EQ/MO rows, mismatched units) raises ValueError so
the pricing evidence fails closed instead of producing a free-form basis.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from math import isfinite

from concilium.domain.models.canonical import CanonicalModel
from concilium.domain.units import normalize_unidade

S_MES = Fraction(1461, 336)  # FORMALISMO_LONGO Part II, weeks per month
_CONTRACTUAL_TYPES = {"EQUIPAMENTO": "EQ", "MAO_OBRA": "MO"}
_CONSUMABLE_ROWS = frozenset({"MATERIAL", "DIESEL", "COMBUSTIVEL"})
_CONTRACTUAL_ROWS = frozenset({"EQUIPAMENTO", "MAO_OBRA"})


@dataclass(frozen=True)
class ActivityCatalogCost:
    activity_id: str
    contractual: Fraction
    consumable: Fraction

    @property
    def total(self) -> Fraction:
        return self.contractual + self.consumable


@dataclass(frozen=True)
class CatalogCostEnvelope:
    activities: tuple[ActivityCatalogCost, ...]

    @property
    def total(self) -> Fraction:
        return sum((a.total for a in self.activities), Fraction(0))

    def fingerprint(self) -> str:
        payload = {
            "schema": "concilium.catalog-envelope.v1",
            "activities": [
                {"id": a.activity_id, "K": str(a.contractual), "V": str(a.consumable)} for a in self.activities
            ],
            "total": str(self.total),
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


def _exact(value: object, label: str) -> Fraction:
    if type(value) is int or type(value) is float:
        try:
            finite = isfinite(value)
        except OverflowError:
            finite = False
        if finite:
            return Fraction(str(value))
    if type(value) is str:
        try:
            return Fraction(value)
        except (ValueError, ZeroDivisionError):
            pass
    raise ValueError(f"{label} must be a finite exact number")


def _index(rows: object, key: str, label: str) -> dict[str, Mapping[str, object]]:
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise ValueError(f"catalog {label} must be a sequence")
    index: dict[str, Mapping[str, object]] = {}
    for row in rows:
        if isinstance(row, Mapping) and isinstance(row.get(key), str) and row[key]:
            if row[key] in index:
                raise ValueError(f"catalog {label} identity {row[key]!r} is duplicated")
            index[str(row[key])] = row
    return index


def _hourly_contractual_rate(insumo: Mapping[str, object], hours_per_week: Fraction, label: str) -> Fraction:
    price = _exact(insumo.get("preco_unitario"), f"{label} price")
    unit = insumo.get("unidade")
    if unit in ("mes", "mês"):
        return price / (S_MES * hours_per_week)
    if unit == "h":
        return price
    raise ValueError(f"{label}: contractual price unit must be 'mes' or 'h', got {unit!r}")


def _team_rows(team: Mapping[str, object], field: str, count: str) -> list[tuple[str, int]]:
    rows = team.get(field) or []
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise ValueError(f"production team {field} must be a sequence")
    out: list[tuple[str, int]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError(f"production team {field} row must be a mapping")
        ident = row.get("equip_id" if field == "equipamentos" else "funcao_id")
        n = row.get(count)
        if not isinstance(ident, str) or not ident or type(n) is not int or n <= 0:
            raise ValueError(f"production team {field} row needs an id and a positive integer {count}")
        out.append((ident, n))
    return out


def derive_catalog_cost_envelope(canonical: CanonicalModel, catalogo: Mapping[str, object]) -> CatalogCostEnvelope:
    regime = canonical.projeto.regime_trabalho if canonical.projeto is not None else None
    if regime is None:
        raise ValueError("C^cat requires the project work regime (d, h)")
    hours_per_week = Fraction(regime.dias_semana) * Fraction(regime.horas_dia)
    cpus = _index(catalogo.get("cpus"), "codigo", "CPUs")
    productions = _index(catalogo.get("producoes"), "id", "producoes")
    insumos = _index(catalogo.get("insumos"), "codigo", "insumos")
    if not canonical.eap:
        raise ValueError("C^cat requires a nonempty EAP")

    activities: list[ActivityCatalogCost] = []
    for item in canonical.eap:
        label = item.item_id
        cpu = cpus.get(item.cpu_id)
        if cpu is None:
            raise ValueError(f"{label}: CPU {item.cpu_id!r} is not in the resolved catalog")
        production = productions.get(str(cpu.get("producao_id_ref") or ""))
        if production is None:
            raise ValueError(f"{label}: CPU has no resolvable production record for rho_i")
        unit = normalize_unidade(str(cpu.get("unidade") or ""))
        if normalize_unidade(str(production.get("unidade") or "")) != unit:
            raise ValueError(f"{label}: production unit differs from CPU unit")
        if item.unidade and normalize_unidade(item.unidade) != unit:
            raise ValueError(f"{label}: EAP unit differs from CPU unit")
        rho = _exact(production.get("producao_horaria"), f"{label} rho")
        quantity = _exact(item.quantitativo, f"{label} Q")
        if rho <= 0 or quantity <= 0:
            raise ValueError(f"{label}: Q and rho must be positive")

        team = production.get("composicao_padrao_equipe")
        if not isinstance(team, Mapping):
            raise ValueError(f"{label}: production team (composicao_padrao_equipe) is required")
        gamma_k = Fraction(0)
        for field, count in (("equipamentos", "num_unidades"), ("funcoes", "num_pessoas")):
            for ident, n in _team_rows(team, field, count):
                insumo = insumos.get(ident)
                if insumo is None or insumo.get("tipo") not in _CONTRACTUAL_TYPES:
                    raise ValueError(f"{label}/{ident}: contractual resource must be an EQUIPAMENTO/MAO_OBRA insumo")
                gamma_k += _hourly_contractual_rate(insumo, hours_per_week, f"{label}/{ident}") * n

        consumable_per_unit = Fraction(0)
        composition = cpu.get("composicao_itens")
        if not isinstance(composition, Sequence) or isinstance(composition, (str, bytes)):
            raise ValueError(f"{label}: CPU composicao_itens is required")
        for row in composition:
            if not isinstance(row, Mapping):
                raise ValueError(f"{label}: malformed CPU composition row")
            category = row.get("categoria_custo")
            if category in _CONTRACTUAL_ROWS:
                raise ValueError(
                    f"{label}: CPU lists {category} rows; contractual cost comes only from the production team"
                )
            if category not in _CONSUMABLE_ROWS:
                raise ValueError(f"{label}: unsupported CPU composition category {category!r}")
            good = insumos.get(str(row.get("insumo_id") or ""))
            if good is None:
                raise ValueError(f"{label}: consumable {row.get('insumo_id')!r} is not in the catalog")
            coefficient = _exact(row.get("coeficiente"), f"{label} coefficient")
            consumable_per_unit += coefficient * _exact(good.get("preco_unitario"), f"{label} consumable price")

        activities.append(
            ActivityCatalogCost(
                activity_id=label,
                contractual=quantity * gamma_k / rho,
                consumable=quantity * consumable_per_unit,
            )
        )
    return CatalogCostEnvelope(tuple(activities))
