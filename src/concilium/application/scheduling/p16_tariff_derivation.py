"""Exact P16 tariffs for every project: catalog rate + declared contract terms (N8, #206).

The active weekly rate of a contractual resource is derived from the catalog
with the same hourly rate the catalog envelope uses (FORMALISMO_LONGO §XIV.2):
``c_r * d * h`` — a monthly price divided by ``s_mes``, an hourly price times
the weekly hours — kept as an exact rational, never rounded.

What the catalog does not carry is never inferred (P13-A): the standby regime,
mobilisation/demobilisation and the maximum idle gap come from the project's
contract-terms declaration — one project-level default plus per-resource-type
overrides. A resource without complete declared terms is ``UNKNOWN_CONTRACT``:
no tariff is produced and nothing downstream may be evaluated for it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from fractions import Fraction

from concilium.application.scheduling.catalog_cost_envelope import hourly_contractual_rate

REGIMES = ("FULL_RATE_STANDBY", "DISCOUNTED_STANDBY")
_CATEGORY = {"EQUIPAMENTO": "EQ", "MAO_OBRA": "MO"}
_TERM_FIELDS = ("regime", "mobilize", "demobilize", "max_idle_gap", "source")
_OPTIONAL_FIELDS = ("idle_week", "active_week", "gap_max_viavel")


class UnknownContractError(ValueError):
    """The resource has no complete declared contract terms or catalog rate."""


def _money(value: object, label: str) -> Fraction:
    if not isinstance(value, str) or not value.strip():
        raise UnknownContractError(f"{label} must be an exact rational string")
    try:
        amount = Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise UnknownContractError(f"{label} must be an exact rational string") from exc
    if amount < 0:
        raise UnknownContractError(f"{label} must be nonnegative")
    return amount


def resolve_contract_terms(declarations: object, tipo_id: str) -> dict[str, object]:
    """Project default merged with the resource-type override, field by field."""
    if not isinstance(declarations, Mapping):
        raise UnknownContractError(f"{tipo_id}: no contract terms declared for the project")
    default = declarations.get("default") or {}
    overrides = declarations.get("overrides") or {}
    if not isinstance(default, Mapping) or not isinstance(overrides, Mapping):
        raise UnknownContractError(f"{tipo_id}: contract terms must be mappings")
    override = overrides.get(tipo_id) or {}
    if not isinstance(override, Mapping):
        raise UnknownContractError(f"{tipo_id}: contract-terms override must be a mapping")
    unknown = (set(default) | set(override)) - set(_TERM_FIELDS) - set(_OPTIONAL_FIELDS)
    if unknown:
        raise UnknownContractError(f"{tipo_id}: unknown contract-term fields {sorted(unknown)}")
    terms = {**default, **override}
    missing = [field for field in _TERM_FIELDS if field not in terms]
    if missing:
        raise UnknownContractError(f"{tipo_id}: contract terms not declared: {', '.join(missing)}")
    if terms["regime"] not in REGIMES:
        raise UnknownContractError(f"{tipo_id}: unsupported or undeclared standby regime {terms['regime']!r}")
    gap = terms["max_idle_gap"]
    if type(gap) is not int or gap < 0:
        raise UnknownContractError(f"{tipo_id}: max_idle_gap must be a nonnegative integer")
    if not isinstance(terms["source"], str) or not terms["source"].strip():
        raise UnknownContractError(f"{tipo_id}: contract-terms source is required")
    return terms


def derive_p16_tariff(
    tipo_id: str,
    insumo: Mapping[str, object] | None,
    *,
    dias_semana: int,
    horas_dia: Fraction | int,
    declarations: object,
    currency: str,
    catalog_reference: str,
) -> dict[str, object]:
    """One ``p16_exact_tariffs`` entry, or UnknownContractError."""
    terms = resolve_contract_terms(declarations, tipo_id)
    if insumo is None:
        raise UnknownContractError(f"{tipo_id}: resource is absent from the catalog")
    category = _CATEGORY.get(str(insumo.get("tipo")))
    if category is None:
        raise UnknownContractError(f"{tipo_id}: catalog type {insumo.get('tipo')!r} is not a contractual EQ/MO type")
    hours_per_week = Fraction(dias_semana) * Fraction(horas_dia)
    if hours_per_week <= 0:
        raise UnknownContractError(f"{tipo_id}: weekly hours must be positive")

    if "active_week" in terms:
        active = _money(terms["active_week"], f"{tipo_id}: declared active_week")
        rate_source = "declared active tariff"
    else:
        try:
            active = hourly_contractual_rate(insumo, hours_per_week, tipo_id) * hours_per_week
        except ValueError as exc:
            raise UnknownContractError(str(exc)) from exc
        rate_source = (
            f"catalog {insumo.get('unidade')} price {insumo.get('preco_unitario')} -> c_r*d*h "
            f"({dias_semana} d x {horas_dia} h, FORMALISMO_LONGO XIV.2)"
        )

    if terms["regime"] == "FULL_RATE_STANDBY":
        if "idle_week" in terms and _money(terms["idle_week"], f"{tipo_id}: idle_week") != active:
            raise UnknownContractError(f"{tipo_id}: FULL_RATE_STANDBY requires idle tariff equal to the active tariff")
        idle = active
    else:
        if "idle_week" not in terms:
            raise UnknownContractError(f"{tipo_id}: DISCOUNTED_STANDBY requires a declared idle_week tariff")
        idle = _money(terms["idle_week"], f"{tipo_id}: idle_week")
        if idle >= active:
            raise UnknownContractError(f"{tipo_id}: DISCOUNTED_STANDBY requires idle tariff below the active tariff")

    gap = terms["max_idle_gap"]
    feasible_gap = terms.get("gap_max_viavel", gap)
    if type(feasible_gap) is not int or feasible_gap < 0:
        raise UnknownContractError(f"{tipo_id}: gap_max_viavel must be a nonnegative integer")
    return {
        "source_id": f"{catalog_reference} {tipo_id}: {rate_source}; {terms['regime']}; terms: {terms['source']}",
        "currency": currency,
        "category": category,
        "regime": terms["regime"],
        "active_week": str(active),
        "idle_week": str(idle),
        "mobilize": str(_money(terms["mobilize"], f"{tipo_id}: mobilize")),
        "demobilize": str(_money(terms["demobilize"], f"{tipo_id}: demobilize")),
        "max_idle_gap": gap,
        "gap_max_viavel": feasible_gap,
    }


def derive_p16_tariffs(
    resource_types: Iterable[str],
    catalogo: Mapping[str, object],
    *,
    dias_semana: int,
    horas_dia: Fraction | int,
    declarations: object,
    currency: str,
    catalog_reference: str,
) -> tuple[dict[str, dict[str, object]], dict[str, str]]:
    """``(tariffs, unknown)``: exact tariffs per resource type and, for the rest,
    why the contract is unknown. Callers must treat any ``unknown`` entry as
    NOT_EVALUATED for every quantity that needs that resource's cost."""
    rows = catalogo.get("insumos")
    index = (
        {str(row.get("codigo")): row for row in rows if isinstance(row, Mapping)} if isinstance(rows, list) else {}
    )
    tariffs: dict[str, dict[str, object]] = {}
    unknown: dict[str, str] = {}
    for tipo_id in sorted(set(resource_types)):
        try:
            tariffs[tipo_id] = derive_p16_tariff(
                tipo_id,
                index.get(tipo_id),
                dias_semana=dias_semana,
                horas_dia=horas_dia,
                declarations=declarations,
                currency=currency,
                catalog_reference=catalog_reference,
            )
        except UnknownContractError as exc:
            unknown[tipo_id] = str(exc)
    return tariffs, unknown
