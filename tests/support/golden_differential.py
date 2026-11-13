"""Phase-by-phase differential of a finished pipeline run against independent oracles (#24).

Each phase is recomputed from the run's own inputs with code that does not
import the production module that produced it:

* PHYSICAL — F(m) by the P22-B max-flow oracle on the production's capacity
  elements; per week q_ij = min(residual, H * F(m_ij) * climate * calendar *
  shift); Σ_j q_ij = Q_i within the documented scope tolerance;
* POOL — P16 contractual K per contract: closed form when no mobilisation
  cost is declared (never bridging is optimal: presence = demand, K = tariff *
  Σ demand), the exhaustive P22-C pool oracle inside its bounds, else
  UNVERIFIED;
* CONSUMPTION — P18 V per activity = Σ_j q_ij * coef * price (consumption
  oracle form) and the N6 declaration;
* CATALOG — C^cat by the catalog-envelope oracle;
* PRICE — P = Σ_category cost * (1 + β), profit, margin and BDI = P / C^cat - 1;
* CERTIFICATE — the P23 record (decision, status, fingerprints) is reported,
  never re-decided here (P23 is the only GO contract).

The report keeps pipeline order; ``first_divergence`` is the earliest DIVERGE.
Expected values are never rewritten to match the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from tests.reference_formalism.catalog_envelope_reference import evaluate_catalog_envelope
from tests.reference_formalism.economic_reference import _pool as exhaustive_pool
from tests.reference_formalism.physical_reference import _max_flow

ABS_SCOPE_TOLERANCE = Fraction(1, 1_000_000)
REL_SCOPE_TOLERANCE = Fraction(1, 1_000_000_000)
PHASES = ("PHYSICAL", "POOL", "CONSUMPTION", "CATALOG", "PRICE", "CERTIFICATE")


def q(value: object) -> Fraction:
    return Fraction(str(value))


@dataclass(frozen=True)
class Check:
    phase: str
    check: str
    status: str  # MATCH | DIVERGE | UNVERIFIED
    pipeline: str
    oracle: str
    provenance: str


def _cmp(
    phase: str, check: str, pipeline: Fraction, oracle: Fraction, provenance: str, tolerance: Fraction = Fraction(0)
) -> Check:
    status = "MATCH" if abs(pipeline - oracle) <= tolerance else "DIVERGE"
    return Check(phase, check, status, str(pipeline), str(oracle), provenance)


def _elements_graph(production: dict) -> dict | None:
    """Capacity elements in series, each replicated per front -> P22-B graph.

    None when the production declares no capacity element (not translatable).
    """
    graph = production.get("grafo_sinergia") or {}
    elements = [c for c in graph.get("capacidades") or [] if c.get("capacidade_horaria")]
    if not elements:
        return None
    nodes = ["s", *[f"n{i}" for i in range(1, len(elements))], "t"]
    edges = [
        {"from": nodes[i], "to": nodes[i + 1], "capacity": str(e["capacidade_horaria"]), "scaling": "per_front"}
        for i, e in enumerate(elements)
    ]
    return {"nodes": nodes, "source": "s", "sink": "t", "edges": edges}


def physical_checks(canonical: Any, catalog: dict) -> list[Check]:
    checks: list[Check] = []
    cpus = {c["codigo"]: c for c in catalog["cpus"]}
    productions = {p["id"]: p for p in catalog["producoes"]}
    regime = canonical.projeto.regime_trabalho
    hours = Fraction(regime.horas_dia) * Fraction(regime.dias_semana)
    eap = {item.item_id: item for item in canonical.eap}
    for activity in canonical.cronograma.scheduled_activities:
        item = eap[activity.activity_id]
        production = productions[cpus[item.cpu_id]["producao_id_ref"]]
        graph = _elements_graph(production)
        scope = q(item.quantitativo)
        residual = scope
        total = Fraction(0)
        for week, cell in sorted(activity.distribuicao_semanal.items()):
            label = f"{activity.activity_id}/{week}"
            m = int(cell.num_equipes)
            if graph is None:
                checks.append(
                    Check(
                        "PHYSICAL",
                        f"{label} F(m)",
                        "UNVERIFIED",
                        str(cell.produtividade_fisica_horaria),
                        "-",
                        "production graph has no capacity elements",
                    )
                )
                continue
            rate = _max_flow(graph, m) if m > 0 else Fraction(0)
            checks.append(
                _cmp(
                    "PHYSICAL",
                    f"{label} F(m={m})",
                    q(cell.produtividade_fisica_horaria),
                    rate,
                    "P22-B max-flow on production capacity elements",
                    tolerance=Fraction(1, 10**9) * max(rate, 1),
                )
            )
            capacity = hours * rate * q(cell.fator_clima) * q(cell.fator_calendario) * q(cell.fator_jornada)
            expected_q = min(residual, capacity)
            delivered = q(cell.qtd_executada)
            checks.append(
                _cmp(
                    "PHYSICAL",
                    f"{label} q=min(residual,B)",
                    delivered,
                    expected_q,
                    "CAPACIDADE_E_RECURSOS closing law",
                    tolerance=ABS_SCOPE_TOLERANCE,
                )
            )
            residual -= delivered
            total += delivered
        tolerance = min(ABS_SCOPE_TOLERANCE, scope * REL_SCOPE_TOLERANCE)
        checks.append(
            _cmp(
                "PHYSICAL",
                f"{activity.activity_id} sum q = Q",
                total,
                scope,
                "V1 scope closure (documented tolerance)",
                tolerance=max(tolerance, ABS_SCOPE_TOLERANCE),
            )
        )
    return checks


def resource_demand_checks(canonical: Any, catalog: dict) -> list[Check]:
    """d_gj = sum_i m_ij a_ig^front (CAPACIDADE_E_RECURSOS) against the P16 demand.

    Catches fictitious capacity: fronts that the contracted resources cannot staff.
    """
    cpus = {c["codigo"]: c for c in catalog["cpus"]}
    productions = {p["id"]: p for p in catalog["producoes"]}
    eap = {item.item_id: item for item in canonical.eap}
    expected: dict[tuple[str, str], int] = {}
    for activity in canonical.cronograma.scheduled_activities:
        team = productions[cpus[eap[activity.activity_id].cpu_id]["producao_id_ref"]]["composicao_padrao_equipe"]
        per_front = {r["equip_id"]: r["num_unidades"] for r in team.get("equipamentos", [])}
        per_front |= {r["funcao_id"]: r["num_pessoas"] for r in team.get("funcoes", [])}
        for week, cell in activity.distribuicao_semanal.items():
            for resource, units in per_front.items():
                key = (resource, week)
                expected[key] = expected.get(key, 0) + int(cell.num_equipes) * units
    observed: dict[tuple[str, str], int] = {}
    for contract in canonical.contratos_recurso:
        witness = contract.p16_global_assignment or {}
        for week, demand in zip(witness.get("calendar_weeks", []), witness.get("demand", []), strict=True):
            observed[(contract.tipo_id, week)] = observed.get((contract.tipo_id, week), 0) + int(demand)
    checks = []
    for key in sorted(set(expected) | set(observed)):
        if expected.get(key, 0) or observed.get(key, 0):
            checks.append(
                _cmp(
                    "POOL",
                    f"{key[0]}/{key[1]} demand = m * a^front",
                    Fraction(observed.get(key, 0)),
                    Fraction(expected.get(key, 0)),
                    "CAPACIDADE_E_RECURSOS d_gj = sum_i m_ij a_ig^front",
                )
            )
    return checks


def pool_checks(canonical: Any) -> list[Check]:
    checks: list[Check] = []
    for contract in canonical.contratos_recurso:
        witness = contract.p16_global_assignment or {}
        demand = [int(d) for d in witness.get("demand", [])]
        tariff = witness.get("tariff", {})
        active, idle = q(tariff.get("active_week", "0")), q(tariff.get("idle_week", "0"))
        movement = q(tariff.get("mobilize", "0")) + q(tariff.get("demobilize", "0"))
        costs = witness.get("costs", {})
        label = contract.tipo_id
        if movement == 0 and idle > 0:
            checks.append(
                _cmp(
                    "POOL",
                    f"{label} K active",
                    q(costs["active"]),
                    active * sum(demand),
                    "closed form: no movement cost -> never bridge",
                )
            )
            checks.append(
                _cmp(
                    "POOL",
                    f"{label} standby+mobility",
                    q(costs["standby"]) + q(costs["mobility"]),
                    Fraction(0),
                    "closed form: presence = demand",
                )
            )
            continue
        nonzero = [j for j, d in enumerate(demand) if d]
        window = demand[nonzero[0] : nonzero[-1] + 1] if nonzero else []
        instances = int(contract.quantidade_contratada)
        if not window or instances > 3 or len(window) > 6:
            checks.append(
                Check(
                    "POOL",
                    f"{label} K",
                    "UNVERIFIED",
                    str(q(costs.get("pool_total", 0))),
                    "-",
                    "outside exhaustive oracle bounds (<= 3 instances, <= 6 weeks)",
                )
            )
            continue
        regime = "FULL_RATE_STANDBY" if idle == active else "DISCOUNTED_STANDBY"
        record = exhaustive_pool(
            tuple(window),
            {
                "instances": instances,
                "active": str(active),
                "idle": str(idle),
                "movement": str(movement),
                "max_idle_gap": int(tariff.get("max_idle_gap_effective", tariff.get("max_idle_gap_declared", 0))),
                "regime": regime,
                "off_hire_weeks": [],
            },
        )
        oracle_total = record["active_cost"] + record["idle_cost"] + record["movement_cost"]
        checks.append(_cmp("POOL", f"{label} K total", q(costs["pool_total"]), oracle_total, "P22-C exhaustive pool"))
    return checks


def consumption_checks(canonical: Any, catalog: dict) -> list[Check]:
    checks: list[Check] = []
    preview = canonical.p18_consumption_preview or {}
    observed: dict[str, Fraction] = {}
    for row in preview.get("evidence", []):
        observed[row["activity_id"]] = observed.get(row["activity_id"], Fraction(0)) + q(row["exact_cost"])
    declared = set(preview.get("declared_no_consumables", []))
    cpus = {c["codigo"]: c for c in catalog["cpus"]}
    prices = {i["codigo"]: q(i["preco_unitario"]) for i in catalog["insumos"]}
    eap = {item.item_id: item for item in canonical.eap}
    for activity in canonical.cronograma.scheduled_activities:
        aid = activity.activity_id
        delivered = sum((q(c.qtd_executada) for c in activity.distribuicao_semanal.values()), Fraction(0))
        rows = [
            r
            for r in cpus[eap[aid].cpu_id].get("composicao_itens", [])
            if r.get("categoria_custo") in ("MATERIAL", "DIESEL", "COMBUSTIVEL")
        ]
        oracle = (
            Fraction(0)
            if aid in declared
            else delivered * sum((q(r["coeficiente"]) * prices[r["insumo_id"]] for r in rows), Fraction(0))
        )
        checks.append(
            _cmp(
                "CONSUMPTION",
                f"{aid} V",
                observed.get(aid, Fraction(0)),
                oracle,
                "consumption oracle: sum_j q_ij * coef * price (N6)",
            )
        )
    return checks


def catalog_checks(canonical: Any, catalog: dict) -> list[Check]:
    cpus = {c["codigo"]: c for c in catalog["cpus"]}
    productions = {p["id"]: p for p in catalog["producoes"]}
    insumos = {i["codigo"]: i for i in catalog["insumos"]}
    activities = []
    for item in canonical.eap:
        cpu = cpus[item.cpu_id]
        production = productions[cpu["producao_id_ref"]]
        team = production["composicao_padrao_equipe"]
        contractual = [
            {
                "id": r["equip_id"],
                "cat": "EQ",
                "price": str(q(insumos[r["equip_id"]]["preco_unitario"])),
                "price_unit": insumos[r["equip_id"]]["unidade"],
                "n": r["num_unidades"],
            }
            for r in team.get("equipamentos", [])
        ]
        contractual += [
            {
                "id": r["funcao_id"],
                "cat": "MO",
                "price": str(q(insumos[r["funcao_id"]]["preco_unitario"])),
                "price_unit": insumos[r["funcao_id"]]["unidade"],
                "n": r["num_pessoas"],
            }
            for r in team.get("funcoes", [])
        ]
        consumables = [
            {
                "id": r["insumo_id"],
                "coef": str(q(r["coeficiente"])),
                "price": str(q(insumos[r["insumo_id"]]["preco_unitario"])),
                "unit": "",
            }
            for r in cpu.get("composicao_itens", [])
        ]
        activities.append(
            {
                "id": item.item_id,
                "Q": str(q(item.quantitativo)),
                "rho": str(q(production["producao_horaria"])),
                "unit": cpu["unidade"],
                "contractual": contractual,
                "consumables": consumables,
            }
        )
    regime = canonical.projeto.regime_trabalho
    oracle = q(
        evaluate_catalog_envelope(
            {
                "inputs": {
                    "regime": {"d": regime.dias_semana, "h": regime.horas_dia},
                    "s_mes": "1461/336",
                    "activities": activities,
                }
            }
        )["total"]
    )
    pipeline = q(canonical.resultado.pricing_diagnostics["catalog_benchmark"])
    return [_cmp("CATALOG", "C^cat", pipeline, oracle, "catalog-envelope oracle")]


def price_checks(canonical: Any) -> list[Check]:
    diagnostics = canonical.resultado.pricing_diagnostics
    gates = canonical.resultado.pricing_gates
    reconciliation = canonical.resultado.p20_financial_reconciliation
    by_category: dict[str, Fraction] = {}
    for row in reconciliation["weekly_category_balances"]:
        by_category[row["category"]] = by_category.get(row["category"], Fraction(0)) + q(row["amount"])
    total = sum(by_category.values(), Fraction(0))
    price = sum(
        (amount * (1 + q(diagnostics[f"bdi_rate_{cat.lower()}"])) for cat, amount in by_category.items()), Fraction(0)
    )
    profit = price - total
    c_cat = q(diagnostics["catalog_benchmark"])
    return [
        _cmp("PRICE", "C_tot", q(diagnostics["total_cost"]), total, "P20 category totals"),
        _cmp("PRICE", "P", q(diagnostics["operational_price"]), price, "sum_cat C_cat (1 + beta_cat)"),
        _cmp("PRICE", "profit", q(diagnostics["profit_amount"]), profit, "P - C_tot"),
        _cmp("PRICE", "margin", q(diagnostics["realized_margin"]), profit / price, "(P - C_tot) / P"),
        _cmp("PRICE", "BDI over C^cat", q(gates["regulatory_bdi_rate"]), price / c_cat - 1, "P / C^cat - 1 (N2)"),
    ]


def certificate_checks(certificate: dict) -> list[Check]:
    fingerprints = f"evaluation={certificate.get('evaluation_sha256')} record={certificate.get('record_sha256')}"
    return [
        Check(
            "CERTIFICATE",
            "P23 decision",
            "MATCH" if certificate.get("status") == "CURRENT" else "DIVERGE",
            f"{certificate.get('status')}/{certificate.get('effective_decision')}",
            "CURRENT (read-time)",
            fingerprints,
        )
    ]


def differential_report(canonical: Any, catalog: dict, certificate: dict) -> dict[str, Any]:
    checks = [
        *physical_checks(canonical, catalog),
        *resource_demand_checks(canonical, catalog),
        *pool_checks(canonical),
        *consumption_checks(canonical, catalog),
        *catalog_checks(canonical, catalog),
        *price_checks(canonical),
        *certificate_checks(certificate),
    ]
    first = next((c for c in checks if c.status == "DIVERGE"), None)
    return {
        "checks": checks,
        "first_divergence": first,
        "unverified": [c for c in checks if c.status == "UNVERIFIED"],
        "summary": {phase: sorted({c.status for c in checks if c.phase == phase}) for phase in PHASES},
    }
