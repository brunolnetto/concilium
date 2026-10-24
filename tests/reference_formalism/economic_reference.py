"""P22-C independent bounded economic oracle: fungible pool, measured goods, stock, BDI.

Exactly enumerates fungible physical-instance assignments and keep/split decisions
for tiny horizons, intentionally NOT importing P16/P17/P18 or using their output.
Costs are rational and exact. This is a reference witness, never PROJECT_GO.
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

VERSION = "formalism-economic/1"
MARKUPS = frozenset({"EQ", "MO", "MAT", "COMB", "IND"})
UNITS = {"L": ("volume", F(1)), "mL": ("volume", F(1, 1000)),
         "kg": ("mass", F(1)), "g": ("mass", F(1, 1000)),
         "m3": ("volume3", F(1))}


def _keys(value: Any, keys: set[str], context: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise ReferenceContractError(f"{context}: missing/unknown contract keys")
    return value


def _int(value: Any, label: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ReferenceContractError(f"{label}: integer >= {minimum} required")
    return value


def _money(value: Any, label: str, minimum: F = F(0)) -> F:
    number = decimal_input(value, label)
    if number < minimum:
        raise ReferenceContractError(f"{label}: invalid nonnegative value")
    return number


def _series(values: Any, weeks: int, label: str) -> tuple[F, ...]:
    if not isinstance(values, list) or len(values) != weeks:
        raise ReferenceContractError(f"{label}: expected {weeks} week-cells")
    return tuple(_money(x, label) for x in values)


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReferenceContractError(f"{label}: explicit nonempty provenance required")
    return value


def _pool(demand: tuple[int, ...], contract: dict) -> dict:
    limit = _int(contract["instances"], "instances", 1)
    cap = _int(contract["max_idle_gap"], "max_idle_gap")
    if not (limit <= 3 and len(demand) <= 6):
        raise ReferenceContractError("bounded pool enumeration exceeded")
    if max(demand) > limit:
        raise ReferenceContractError("contracted instance capacity below physical demand")
    active = _money(contract["active"], "contract.active")
    idle = _money(contract["idle"], "contract.idle")
    movement = _money(contract["movement"], "contract.movement")
    regime = contract["regime"]
    if regime not in ("FULL_RATE_STANDBY", "DISCOUNTED_STANDBY", "EXPLICIT_OFF_HIRE"):
        raise ReferenceContractError("unknown commercial regime")
    if regime == "FULL_RATE_STANDBY" and active != idle:
        raise ReferenceContractError("FULL_RATE_STANDBY requires equal tariffs")
    if regime == "DISCOUNTED_STANDBY" and not idle < active:
        raise ReferenceContractError("DISCOUNTED_STANDBY requires idle < active")
    if regime == "EXPLICIT_OFF_HIRE" and idle > active:
        raise ReferenceContractError("off-hire active/idle tariff mismatch")
    absent = contract["off_hire_weeks"]
    if not isinstance(absent, list) or any(
        type(j) is not int or j < 0 or j >= len(demand) for j in absent
    ) or len(set(absent)) != len(absent):
        raise ReferenceContractError("invalid declared off-hire weeks")
    if regime != "EXPLICIT_OFF_HIRE" and absent:
        raise ReferenceContractError("off-hire declarations require typed regime")
    if regime == "EXPLICIT_OFF_HIRE" and not absent:
        raise ReferenceContractError("off-hire weeks must be explicitly declared")
    if any(demand[j] for j in absent):
        raise ReferenceContractError("off-hire cannot mask physical demand")

    # Enumerate exact active-label assignments for the given weekly physical
    # demand, then all possible paid standby bridges for EACH real instance.
    schedules = (
        tuple(combinations(range(limit), d)) for d in demand
    )
    best: tuple[tuple, dict] | None = None
    for weekly_labels in product(*schedules):
        presence = [0] * len(demand)
        chains = 0
        standby_count = 0
        feasible = True
        for instance in range(limit):
            active_weeks = [j for j, labels in enumerate(weekly_labels)
                            if instance in labels]
            if not active_weeks:
                continue
            gaps = [(a + 1, b) for a, b in zip(active_weeks, active_weeks[1:], strict=False)]
            variants = []
            for flags in product((False, True), repeat=len(gaps)):
                occupied = set(active_weeks)
                for (start, end), keep in zip(gaps, flags, strict=True):
                    if keep and (
                        end - start > cap
                        or any(j in absent for j in range(start, end))
                    ):
                        break
                    if keep:
                        occupied.update(range(start, end))
                else:
                    chain_count = 1 + flags.count(False)
                    idle_count = len(occupied) - len(active_weeks)
                    cost = active * len(active_weeks) + idle * idle_count + movement * chain_count
                    variants.append((cost, chain_count, tuple(sorted(occupied))))
            if not variants:
                feasible = False
                break
            _, n_chains, occupied = min(variants)
            chains += n_chains
            standby_count += len(occupied) - len(active_weeks)
            for j in occupied:
                presence[j] += 1
        if not feasible or any(presence[j] for j in absent):
            continue
        if any(p < d for p, d in zip(presence, demand, strict=True)):
            raise ReferenceContractError("internal pool cover violation")
        k_active = active * sum(demand)
        k_idle = idle * standby_count
        k_movement = movement * chains
        rank = (k_active + k_idle + k_movement, chains,
                tuple(presence), tuple(weekly_labels))
        record = {
            "demand": list(demand),
            "presence": presence,
            "standby": [p - d for p, d in zip(presence, demand, strict=True)],
            "chains": chains,
            "active_cost": k_active,
            "idle_cost": k_idle,
            "movement_cost": k_movement,
            "assignment": [list(labels) for labels in weekly_labels],
        }
        if best is None or rank < best[0]:
            best = (rank, record)
    if best is None:
        raise ReferenceContractError("INFEASIBLE physical contract assignment")
    return best[1]


def evaluate_economic(vector: dict[str, Any]) -> dict[str, Any]:
    _keys(vector, {"protocol", "case_id", "inputs", "expected"}, "vector")
    if vector["protocol"] != VERSION or not isinstance(vector["case_id"], str):
        raise ReferenceContractError("unsupported economic reference protocol")
    src = _keys(vector["inputs"], {
        "demand", "contract", "goods", "indirect_weekly", "bdi", "sale_price",
    }, "economic inputs")
    physical = src["demand"]
    if not isinstance(physical, list) or not (1 <= len(physical) <= 6):
        raise ReferenceContractError("bounded physical demand missing")
    demand = tuple(_int(d, "weekly physical demand") for d in physical)
    weeks = len(demand)
    contract = _keys(src["contract"], {
        "instances", "active", "idle", "movement", "max_idle_gap",
        "regime", "category", "source", "currency", "off_hire_weeks",
    }, "contract")
    _text(contract["source"], "contract source")
    if contract["currency"] != "BRL" or contract["category"] not in ("EQ", "MO"):
        raise ReferenceContractError("unsupported currency or K category")
    pool = _pool(demand, contract)
    bdi = _keys(src["bdi"], set(MARKUPS), "category BDI")
    markup = {k: _money(v, f"BDI.{k}") for k, v in bdi.items()}
    indirect_base = _series(src["indirect_weekly"], weeks, "indirect_weekly")
    sale = _money(src["sale_price"], "sale_price", F(1, 10**100))
    goods = src["goods"]
    if not isinstance(goods, list) or len(goods) > 6:
        raise ReferenceContractError("goods must be a bounded list")
    goods_result = {}
    categorized = {key: F(0) for key in MARKUPS}
    categorized[contract["category"]] = pool["active_cost"] + pool["idle_cost"]
    categorized["IND"] = pool["movement_cost"] + sum(indirect_base)
    event_ids: list[str] = []
    for j, n in enumerate(demand):
        if n:
            event_ids.append(f"pool:active:{j}")
        if pool["standby"][j]:
            event_ids.append(f"pool:idle:{j}")
        if indirect_base[j]:
            event_ids.append(f"project:indirect:{j}")
    event_ids.extend(f"pool:movement:{i}" for i in range(pool["chains"]))
    for raw_good in goods:
        g = _keys(raw_good, {
            "id", "category", "unit", "order_unit", "driver_unit", "mode", "rate",
            "driver_weekly", "idle_weekly", "loss_weekly", "price",
            "rate_source", "price_source", "extra_source",
            "initial_stock", "orders_weekly", "lead_weeks", "holding_rate", "order_fee",
        }, "good")
        name = _text(g["id"], "good id")
        if name in goods_result or name.find(":") >= 0:
            raise ReferenceContractError("good identities must be unique and safe")
        category = g["category"]
        if category not in ("MAT", "COMB"):
            raise ReferenceContractError("good cannot post K or IND acquisition")
        unit, order_unit = g["unit"], g["order_unit"]
        if unit not in UNITS or order_unit not in UNITS or UNITS[unit][0] != UNITS[order_unit][0]:
            raise ReferenceContractError("physical dimension mismatch")
        multiplier = UNITS[order_unit][1] / UNITS[unit][1]
        mode = g["mode"]
        if mode not in ("OUTPUT_PROPORTIONAL", "OUTPUT_WITH_MEASURED_LOSS",
                        "HOURLY_WITH_MEASURED_IDLE"):
            raise ReferenceContractError("invalid physical consumption mode")
        if g["driver_unit"] != ("h" if mode == "HOURLY_WITH_MEASURED_IDLE" else "m3"):
            raise ReferenceContractError("physical rate driver dimension mismatch")
        _text(g["rate_source"], "physical rate source")
        _text(g["price_source"], "physical price source")
        rate = _money(g["rate"], "physical rate")
        price = _money(g["price"], "physical price")
        drivers = _series(g["driver_weekly"], weeks, "physical driver")
        idle = _series(g["idle_weekly"], weeks, "measured idle")
        loss = _series(g["loss_weekly"], weeks, "measured loss")
        if mode == "OUTPUT_PROPORTIONAL" and (
            any(idle) or any(loss) or g["extra_source"] is not None
        ):
            raise ReferenceContractError("output baseline cannot include implicit extras")
        if mode == "OUTPUT_WITH_MEASURED_LOSS" and any(idle):
            raise ReferenceContractError("loss mode must not hide measured idle")
        if mode != "OUTPUT_PROPORTIONAL":
            _text(g["extra_source"], "measured loss/idle source")
        consumed = tuple(rate * d + a + b for d, a, b in
                         zip(drivers, idle, loss, strict=True))
        ordered = _series(g["orders_weekly"], weeks, "physical purchase orders")
        orders = tuple(q * multiplier for q in ordered)
        lead = _int(g["lead_weeks"], "delivery lead weeks")
        if lead >= weeks:
            raise ReferenceContractError("lead exceeds reference horizon")
        initial = _money(g["initial_stock"], "initial stock")
        if initial != 0:
            raise ReferenceContractError("initial inventory valuation not supplied; fail closed")
        holding = _money(g["holding_rate"], "holding tariff")
        order_fee = _money(g["order_fee"], "fixed purchase order cost")
        stock = initial
        holding_cost = F(0)
        for j in range(weeks):
            if j >= lead:
                stock += orders[j - lead]
            stock -= consumed[j]
            if stock < 0:
                raise ReferenceContractError("physical inventory stockout")
            holding_cost += holding * stock
            if stock:
                event_ids.append(f"good:{name}:holding:{j}")
            if consumed[j]:
                event_ids.append(f"good:{name}:acquisition:{j}")
            if ordered[j]:
                event_ids.append(f"good:{name}:order:{j}")
        if stock != 0 or sum(orders) != sum(consumed):
            raise ReferenceContractError("unreconciled purchase/consumption inventory")
        order_cost = sum(q > 0 for q in ordered) * order_fee
        direct = price * sum(consumed)
        categorized[category] += direct
        categorized["IND"] += holding_cost + order_cost
        goods_result[name] = {
            "consumed": [_finite_decimal(v, "consumption") for v in consumed],
            "quantity": _finite_decimal(sum(consumed), "quantity"),
            "acquisition": _finite_decimal(direct, "acquisition"),
            "holding": _finite_decimal(holding_cost, "holding"),
            "ordering": _finite_decimal(order_cost, "ordering"),
            "closing_stock": _finite_decimal(stock, "stock"),
        }
    if len(event_ids) != len(set(event_ids)):
        raise ReferenceContractError("duplicate event ownership")
    K = categorized["EQ"] + categorized["MO"]
    V = categorized["MAT"] + categorized["COMB"]
    IND = categorized["IND"]
    total = K + V + IND
    quote = sum(value * (1 + markup[key]) for key, value in categorized.items())
    output_pool = {k: (_finite_decimal(v, k) if isinstance(v, F) else v)
                   for k, v in pool.items()}
    return {
        "pool": output_pool,
        "goods": goods_result,
        "totals": {
            "K": _finite_decimal(K, "K"),
            "V": _finite_decimal(V, "V"),
            "IND": _finite_decimal(IND, "IND"),
            "direct": _finite_decimal(K + V, "direct"),
            "indirect": _finite_decimal(IND, "indirect"),
            "total": _finite_decimal(total, "total"),
            "quote_with_BDI": _finite_decimal(quote, "BDI quote"),
            "sale_price": _finite_decimal(sale, "sale"),
            "margin": _finite_decimal((sale - total) / sale, "margin"),
            "margin_positive": sale > total,
        },
        "categories": {key: _finite_decimal(value, key) for key, value in sorted(categorized.items())},
        "posting_ids": sorted(event_ids),
    }


def verify_economic(vector: dict[str, Any]) -> dict[str, Any]:
    actual = evaluate_economic(vector)
    if actual != vector.get("expected"):
        raise ReferenceContractError(f"{vector.get('case_id')}: economic golden mismatch")
    return actual
