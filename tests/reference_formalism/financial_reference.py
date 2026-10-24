"""P22-C: pure rational independent finance/stock/contractual assignment oracle.

Never imports concilium production code. This reference intentionally uses
small bounded exhaustive assignments and explicit physical acquisition events.
"""
from __future__ import annotations

from fractions import Fraction as F
from itertools import combinations, product
from typing import Any

from tests.reference_formalism.protocol import (
    ReferenceContractError,
    _finite_decimal,
    decimal_input,
)

VERSION = "formalism-financial/1"
CATEGORIES = frozenset({"EQ", "MO", "MAT", "COMB", "IND"})


def _keys(d: Any, keys: set[str], name: str) -> dict:
    if not isinstance(d, dict) or set(d) != keys:
        raise ReferenceContractError(f"{name}: missing or unknown fields")
    return d


def _amount(value: Any, name: str, *, positive: bool = False) -> F:
    v = decimal_input(value, name)
    if v < 0 or (positive and v == 0):
        raise ReferenceContractError(f"{name}: invalid nonpositive amount")
    return v


def _weeks(value: Any, name: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise ReferenceContractError(f"{name}: invalid integer week or count")
    return value


def _pool(demand: list[int], inputs: dict, *, horizon: int) -> tuple[F, F, int]:
    """Enumerate labeled weekly assignment AND chain keep/split for <=3 instances."""
    tariff = _keys(inputs, {"active", "idle", "movement", "max_idle_gap", "instances",
                            "category", "source"}, "contract")
    if tariff["category"] not in {"EQ", "MO"} or not isinstance(tariff["source"], str) or not tariff["source"].strip():
        raise ReferenceContractError("contract: category or provenance missing")
    count = _weeks(tariff["instances"], "instances", maximum=3)
    gap_max = _weeks(tariff["max_idle_gap"], "max_idle_gap", maximum=horizon)
    active = _amount(tariff["active"], "active")
    idle = _amount(tariff["idle"], "idle")
    movement = _amount(tariff["movement"], "movement")
    if any(n > count for n in demand):
        raise ReferenceContractError("physical demand exceeds contract instances")
    if not demand or not any(demand):
        return F(0), F(0), 0
    best: tuple[F, int, F, F] | None = None
    week_options = [list(combinations(range(count), d)) for d in demand]
    for assigned in product(*week_options):
        active_cost = F(sum(demand)) * active
        alternatives: list[list[tuple[F, int, F]]] = []
        for instance in range(count):
            occupied = [j for j, owners in enumerate(assigned) if instance in owners]
            if not occupied:
                alternatives.append([(F(0), 0, F(0))])
                continue
            gaps = [b - a - 1 for a, b in zip(occupied, occupied[1:])]
            options = []
            for flags in product((False, True), repeat=len(gaps)):
                if any(keep and gap > gap_max for gap, keep in zip(gaps, flags)):
                    continue
                idle_weeks = sum(gap for gap, keep in zip(gaps, flags) if keep)
                chain_count = 1 + sum(not keep for keep in flags)
                options.append((F(idle_weeks)*idle + chain_count*movement,
                                chain_count, F(idle_weeks)*idle))
            alternatives.append(options)
        for choices in product(*alternatives):
            movement_count = sum(c[1] for c in choices)
            id_cost = sum((c[0] for c in choices), F(0))
            standby_cost = sum((c[2] for c in choices), F(0))
            candidate = (active_cost + id_cost, movement_count, standby_cost,
                         F(movement_count)*movement)
            if best is None or candidate[:2] < best[:2]:
                best = candidate
    if best is None:
        raise ReferenceContractError("no physically feasible pool")
    total, _, standby, movements = best
    return total - movements, movements, sum(demand)


def evaluate_financial(vector: dict[str, Any]) -> dict[str, str]:
    _keys(vector, {"protocol", "case_id", "inputs", "expected"}, "vector")
    if vector["protocol"] != VERSION:
        raise ReferenceContractError("unsupported finance protocol")
    p = _keys(vector["inputs"], {
        "demand", "contract", "goods", "stock", "bdi", "selling_price",
    }, "finance inputs")
    demand = p["demand"]
    if not isinstance(demand, list) or not 1 <= len(demand) <= 6:
        raise ReferenceContractError("demand horizon outside bounded oracle")
    demand = [_weeks(x, "demand", maximum=3) for x in demand]
    contract_k, movement, _ = _pool(demand, p["contract"], horizon=len(demand))
    bdi = _keys(p["bdi"], CATEGORIES, "bdi")
    markup = {cat: _amount(rate, f"bdi.{cat}") for cat, rate in bdi.items()}
    contractual_cat = p["contract"]["category"]
    seen: set[str] = set()
    v = F(0)
    v_marked = F(0)
    purchases_by_good: dict[str, F] = {}
    for row in p["goods"]:
        _keys(row, {"event_id", "good", "quantity", "price", "category",
                     "unit", "rate_source", "price_source"}, "physical purchase")
        for name in ("event_id", "good", "unit", "rate_source", "price_source"):
            if not isinstance(row[name], str) or not row[name].strip():
                raise ReferenceContractError(f"{name} physical provenance absent")
        if row["event_id"] in seen:
            raise ReferenceContractError("duplicate physical event ownership")
        seen.add(row["event_id"])
        if row["category"] not in {"MAT", "COMB"}:
            raise ReferenceContractError("physical purchase must be MAT or COMB")
        qty = _amount(row["quantity"], "physical quantity")
        price = _amount(row["price"], "price per physical unit")
        cost = qty * price
        v += cost
        v_marked += cost*(1+markup[row["category"]])
        purchases_by_good[row["good"]] = purchases_by_good.get(row["good"], F(0)) + qty
    holding = F(0)
    ordering = F(0)
    for row in p["stock"]:
        _keys(row, {"good", "initial", "demand", "receipts", "hold_per_week",
                    "order_events", "order_fee"}, "stock")
        if row["good"] not in purchases_by_good:
            raise ReferenceContractError("stock good lacks physical acquisition source")
        if len(row["demand"]) != len(demand) or len(row["receipts"]) != len(demand):
            raise ReferenceContractError("stock weekly horizon mismatch")
        remaining = _amount(row["initial"], "initial inventory")
        consumed = F(0)
        received = F(0)
        price_holding = _amount(row["hold_per_week"], "holding rate")
        for d, receipt in zip(row["demand"], row["receipts"]):
            qty = _amount(d, "weekly physical demand")
            arrival = _amount(receipt, "weekly receipt")
            remaining += arrival - qty
            if remaining < 0:
                raise ReferenceContractError("negative inventory: shortage")
            holding += remaining * price_holding
            consumed += qty
            received += arrival
        if consumed != purchases_by_good[row["good"]]:
            raise ReferenceContractError("stock / physical purchase quantity mismatch")
        if remaining != _amount(row["initial"], "initial inventory") + received - consumed:
            raise ReferenceContractError("stock conservation mismatch")
        order_count = _weeks(row["order_events"], "order_events", maximum=len(demand))
        ordering += order_count * _amount(row["order_fee"], "order fee")
    indirect = movement + holding + ordering
    total = contract_k + v + indirect
    price = _amount(p["selling_price"], "selling price", positive=True)
    outputs = {
        "contractual_k": contract_k,
        "consumable_v": v,
        "movement_ind": movement,
        "inventory_holding_ind": holding,
        "ordering_ind": ordering,
        "indirect_total": indirect,
        "cost_total": total,
        "marked_price": contract_k*(1+markup[contractual_cat])
            + v_marked + indirect*(1+markup["IND"]),
        "realized_margin": (price-total)/price,
    }
    return {key: _finite_decimal(val, key) for key, val in outputs.items()}


def verify_financial(vector: dict[str, Any]) -> dict[str, str]:
    observed = evaluate_financial(vector)
    expected = vector["expected"]
    if not isinstance(expected, dict) or set(expected) != set(observed):
        raise ReferenceContractError("financial expected keys mismatch")
    for key in observed:
        if decimal_input(observed[key], key) != decimal_input(expected[key], key):
            raise ReferenceContractError(f"financial golden mismatch: {key}")
    return observed


def compare_financial_output(
    vector: dict[str, Any], observed: dict[str, Any],
) -> dict[str, str]:
    """Compare an external (e.g. production) projection against pure reference.

    Callers explicitly supply the external output; this module does not
    import the system being tested. There is no fixture mirroring or
    automatic acceptance of omitted/mutated projection fields.
    """
    reference = evaluate_financial(vector)
    _keys(observed, set(reference), "external financial projection")
    for key, expected in reference.items():
        if decimal_input(observed[key], key) != decimal_input(expected, key):
            raise ReferenceContractError(
                f"financial production mismatch: {key} "
                f"expected={expected} observed={observed[key]}"
            )
    return reference
