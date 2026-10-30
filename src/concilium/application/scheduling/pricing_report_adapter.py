"""P21-C: serialize the same exact pricing evidence across all report surfaces.

The adapter intentionally requires an explicit P20 reconciliation context. It
never reconstructs a financial ledger from rounded legacy display fields.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal, cast

from concilium.domain.models.canonical import CanonicalModel, Resultado, ValidacaoItem

from .contractual_cost_ledger import ExclusiveCostLedger
from .financial_cost_reconciliation import (
    ExactFinancialReconciliation,
    reconcile_financial_sources,
)
from .operational_pricing_diagnostics import (
    CatalogPriceBenchmark,
    project_operational_pricing,
)
from .physical_consumption_journal import PhysicalConsumptionJournalResult
from .physical_stock_holding import (
    HoldingJournal,
    HoldingTariff,
    post_exact_weekly_holding,
)
from .physical_stock_ledger import StockArrival, StockGood, project_exact_weekly_stock
from .physical_stock_provisioning import (
    ExternalStockProvisioningJournal,
    ExternalStockPurchase,
    book_external_stock_provisioning,
)
from .pricing_gates import RegulatoryBdiBasis, evaluate_pricing_gates
from .skill04_consumption_preview import (
    book_skill04_planned_consumption_preview,
    build_activity_goods_from_catalog,
)
from .skill06_p18c_consumption_preview import (
    _validate_catalog_currency,
    build_skill05_exact_pool_ledger,
)


@dataclass(frozen=True)
class InventoryEvidenceScope:
    """Provenance-bearing declaration that inventory/holding coverage is complete."""

    status: Literal["NO_INVENTORY", "COMPLETE"]
    source: str
    reference_id: str
    fingerprint: str

    def __post_init__(self) -> None:
        if self.status not in ("NO_INVENTORY", "COMPLETE"):
            raise ValueError("inventory evidence scope must be NO_INVENTORY or COMPLETE")
        if any(not isinstance(value, str) or not value.strip() for value in (
            self.source, self.reference_id, self.fingerprint,
        )):
            raise ValueError("inventory evidence scope requires source, reference and fingerprint")



_P21_INPUT_SCHEMA = "concilium.p21.pricing-evidence.v1"
_P21_CATEGORIES = frozenset({"MO", "EQ", "MAT", "COMB", "IND"})


def _json_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(
        isinstance(key, str) for key in value
    ):
        raise ValueError(f"{label} must be a JSON object with string keys")
    return cast(Mapping[str, object], value)


def _json_list(value: object, label: str) -> list:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a JSON array")
    return value


def _json_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")
    return value.strip()


def _json_fraction(value: object, label: str) -> Fraction:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be an exact rational string")
    try:
        return Fraction(value.strip())
    except (ValueError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError(f"{label} must be an exact rational string") from exc


def _json_integer(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _parse_stock_goods(raw: object) -> dict[str, StockGood]:
    goods: dict[str, StockGood] = {}
    for index, value in enumerate(_json_list(raw, "inventory.goods")):
        row = _json_mapping(value, f"inventory.goods[{index}]")
        if set(row) - {"good_id", "unit", "initial_quantity", "capacity", "lead_time_weeks"}:
            raise ValueError("stock good contains unsupported fields")
        good_id = _json_text(row.get("good_id"), "stock good_id")
        if good_id in goods:
            raise ValueError(f"duplicate stock good identity: {good_id}")
        capacity_raw = row.get("capacity")
        capacity = (
            None if capacity_raw is None
            else _json_fraction(capacity_raw, f"{good_id}.capacity")
        )
        goods[good_id] = StockGood(
            good_id=good_id,
            unit=_json_text(row.get("unit"), f"{good_id}.unit"),
            initial_quantity=_json_fraction(
                row.get("initial_quantity"), f"{good_id}.initial_quantity",
            ),
            capacity=capacity,
            lead_time_weeks=_json_integer(
                row.get("lead_time_weeks"), f"{good_id}.lead_time_weeks",
            ),
        )
    if not goods:
        raise ValueError("inventory.goods must declare at least one physical good")
    return goods


def _parse_internal_arrivals(raw: object) -> tuple[StockArrival, ...]:
    arrivals: list[StockArrival] = []
    for index, value in enumerate(_json_list(raw, "inventory.internal_arrivals")):
        row = _json_mapping(value, f"inventory.internal_arrivals[{index}]")
        if set(row) - {"source_id", "good_id", "arrival_week", "quantity", "unit", "source", "ordered_week"}:
            raise ValueError("internal arrival contains unsupported fields")
        source = _json_text(row.get("source"), "internal arrival source")
        if source != "INTERNAL_GENERATION":
            raise ValueError(
                "inventory.internal_arrivals accepts only INTERNAL_GENERATION; "
                "external receipts require a paired priced purchase"
            )
        if row.get("ordered_week") is not None:
            raise ValueError("internal generation cannot declare an order week")
        arrivals.append(StockArrival(
            source_id=_json_text(row.get("source_id"), "arrival source_id"),
            good_id=_json_text(row.get("good_id"), "arrival good_id"),
            arrival_week=_json_text(row.get("arrival_week"), "arrival_week"),
            quantity=_json_fraction(row.get("quantity"), "arrival quantity"),
            unit=_json_text(row.get("unit"), "arrival unit"),
            source="INTERNAL_GENERATION",
        ))
    return tuple(arrivals)


def _parse_external_purchases(raw: object) -> tuple[ExternalStockPurchase, ...]:
    purchases: list[ExternalStockPurchase] = []
    for index, value in enumerate(_json_list(raw, "inventory.purchases")):
        row = _json_mapping(value, f"inventory.purchases[{index}]")
        if set(row) - {
            "source_id", "good_id", "ordered_week", "arrival_week", "quantity",
            "physical_unit", "unit_price", "price_unit", "price_source",
            "price_reference_date", "currency", "category",
        }:
            raise ValueError("external purchase contains unsupported fields")
        category = _json_text(row.get("category"), "purchase category")
        if category not in ("MAT", "COMB"):
            raise ValueError("external purchase category must be MAT or COMB")
        purchases.append(ExternalStockPurchase(
            source_id=_json_text(row.get("source_id"), "purchase source_id"),
            good_id=_json_text(row.get("good_id"), "purchase good_id"),
            ordered_week=_json_text(row.get("ordered_week"), "purchase ordered_week"),
            arrival_week=_json_text(row.get("arrival_week"), "purchase arrival_week"),
            quantity=_json_fraction(row.get("quantity"), "purchase quantity"),
            physical_unit=_json_text(row.get("physical_unit"), "purchase physical_unit"),
            unit_price=_json_fraction(row.get("unit_price"), "purchase unit_price"),
            price_unit=_json_text(row.get("price_unit"), "purchase price_unit"),
            price_source=_json_text(row.get("price_source"), "purchase price_source"),
            price_reference_date=_json_text(
                row.get("price_reference_date"), "purchase price_reference_date",
            ),
            currency=_json_text(row.get("currency"), "purchase currency"),
            category=cast(Literal["MAT", "COMB"], category),
        ))
    return tuple(purchases)


def _parse_holding_tariffs(raw: object) -> dict[str, HoldingTariff]:
    tariffs: dict[str, HoldingTariff] = {}
    for index, value in enumerate(_json_list(raw, "inventory.holding_tariffs")):
        row = _json_mapping(value, f"inventory.holding_tariffs[{index}]")
        if set(row) - {"good_id", "amount_per_unit_week", "physical_unit", "basis"}:
            raise ValueError("holding tariff contains unsupported fields")
        good_id = _json_text(row.get("good_id"), "holding good_id")
        if good_id in tariffs:
            raise ValueError(f"duplicate holding tariff for {good_id}")
        basis = _json_text(row.get("basis"), "holding basis")
        if basis != "END_OF_WEEK":
            raise ValueError("holding basis must be explicitly END_OF_WEEK")
        tariffs[good_id] = HoldingTariff(
            good_id=good_id,
            amount_per_unit_week=_json_fraction(
                row.get("amount_per_unit_week"), "holding amount_per_unit_week",
            ),
            physical_unit=_json_text(row.get("physical_unit"), "holding physical_unit"),
            basis="END_OF_WEEK",
        )
    return tariffs


def _build_p19_journals(
    raw_inventory: object,
    *,
    consumption: PhysicalConsumptionJournalResult,
    catalog_metadata: Mapping[str, object],
) -> tuple[HoldingJournal | None, ExternalStockProvisioningJournal | None]:
    inventory = _json_mapping(raw_inventory, "p21_pricing_evidence.inventory")
    allowed = {
        "calendar_weeks", "goods", "internal_arrivals",
        "purchases", "holding_tariffs",
    }
    unknown = set(inventory) - allowed
    if unknown:
        raise ValueError(f"unsupported inventory fields: {', '.join(sorted(unknown))}")

    calendar_weeks = tuple(
        _json_text(week, "inventory calendar week")
        for week in _json_list(inventory.get("calendar_weeks"), "inventory.calendar_weeks")
    )
    if not calendar_weeks:
        raise ValueError("inventory.calendar_weeks must not be empty")
    goods = _parse_stock_goods(inventory.get("goods"))
    internal_arrivals = _parse_internal_arrivals(
        inventory.get("internal_arrivals", []),
    )
    purchases = _parse_external_purchases(inventory.get("purchases", []))
    tariffs = _parse_holding_tariffs(inventory.get("holding_tariffs", []))
    provisioning: ExternalStockProvisioningJournal | None = None
    if purchases:
        provisioning = book_external_stock_provisioning(
            consumption,
            goods,
            calendar_weeks,
            purchases,
            catalog_metadata=catalog_metadata,
            other_arrivals=internal_arrivals,
        )
        stock = provisioning.stock
        holding_base = provisioning.ledger
    else:
        stock = project_exact_weekly_stock(
            goods,
            calendar_weeks,
            consumption.evidence,
            internal_arrivals,
        )
        if not stock.feasible:
            raise ValueError("COMPLETE inventory evidence leaves an unresolved physical stockout")
        holding_base = consumption.journal

    holding: HoldingJournal | None = None
    if tariffs:
        holding = post_exact_weekly_holding(
            holding_base,
            stock,
            goods,
            tariffs,
        )
    return holding, provisioning


def build_pricing_report_evidence_context(
    canonical: CanonicalModel,
    catalogo: Mapping[str, object],
    declaration: object,
) -> dict[str, object]:
    """Build typed P17/P18/P19/P20/P21 evidence from a versioned JSON contract.

    The transport boundary accepts declarative JSON only. Authoritative ledgers
    and journals are rebuilt from canonical P16/P18 witnesses and explicit P19
    physical declarations; callers cannot submit serialized ledger objects,
    arbitrary catalog metadata, or prebuilt reconciliation instances.
    """
    raw = _json_mapping(declaration, "p21_pricing_evidence")
    allowed = {
        "schema", "inventory_scope", "bdi_by_category", "catalog",
        "operational_basis_fingerprint", "regulatory_basis",
        "minimum_profit_margin", "inventory",
    }
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError(f"unsupported P21 evidence fields: {', '.join(sorted(unknown))}")
    if raw.get("schema") != _P21_INPUT_SCHEMA:
        raise ValueError(f"p21_pricing_evidence.schema must be {_P21_INPUT_SCHEMA}")

    scope_raw = _json_mapping(raw.get("inventory_scope"), "inventory_scope")
    scope_allowed = {"status", "source", "reference_id", "fingerprint"}
    if set(scope_raw) - scope_allowed:
        raise ValueError("inventory_scope contains unsupported fields")
    scope_status_raw = _json_text(scope_raw.get("status"), "inventory_scope.status")
    if scope_status_raw == "NO_INVENTORY":
        scope_status: Literal["NO_INVENTORY", "COMPLETE"] = "NO_INVENTORY"
    elif scope_status_raw == "COMPLETE":
        scope_status = "COMPLETE"
    else:
        raise ValueError("inventory_scope.status must be NO_INVENTORY or COMPLETE")
    inventory_scope = InventoryEvidenceScope(
        status=scope_status,
        source=_json_text(scope_raw.get("source"), "inventory_scope.source"),
        reference_id=_json_text(
            scope_raw.get("reference_id"), "inventory_scope.reference_id",
        ),
        fingerprint=_json_text(
            scope_raw.get("fingerprint"), "inventory_scope.fingerprint",
        ),
    )

    if not isinstance(catalogo, Mapping):
        raise ValueError("resolved catalog is required for P21 pricing evidence")
    _validate_catalog_currency(canonical, catalogo)
    catalog_metadata: dict[str, object] = {
        "currency": catalogo["currency"],
        "currency_source": catalogo["currency_source"],
    }
    currency = _json_text(catalog_metadata["currency"], "resolved catalog currency")

    rates_raw = _json_mapping(raw.get("bdi_by_category"), "bdi_by_category")
    if set(rates_raw) != _P21_CATEGORIES:
        raise ValueError("bdi_by_category must declare exactly MO, EQ, MAT, COMB and IND")
    bdi_by_category = {
        category: _json_fraction(rates_raw[category], f"BDI {category}")
        for category in sorted(_P21_CATEGORIES)
    }
    if any(rate < 0 for rate in bdi_by_category.values()):
        raise ValueError("BDI category rates must be nonnegative")

    catalog_raw = _json_mapping(raw.get("catalog"), "catalog benchmark")
    if set(catalog_raw) - {
        "amount", "currency", "source", "reference_id", "basis_fingerprint",
    }:
        raise ValueError("catalog benchmark contains unsupported fields")
    benchmark_currency = _json_text(catalog_raw.get("currency"), "catalog benchmark currency")
    if benchmark_currency != currency:
        raise ValueError("catalog benchmark currency differs from resolved catalog metadata")
    catalog = CatalogPriceBenchmark(
        amount=_json_fraction(catalog_raw.get("amount"), "catalog benchmark amount"),
        currency=benchmark_currency,
        source=_json_text(catalog_raw.get("source"), "catalog benchmark source"),
        reference_id=_json_text(
            catalog_raw.get("reference_id"), "catalog benchmark reference_id",
        ),
        basis_fingerprint=_json_text(
            catalog_raw.get("basis_fingerprint"), "catalog benchmark basis_fingerprint",
        ),
    )
    operational_basis_fingerprint = _json_text(
        raw.get("operational_basis_fingerprint"),
        "operational_basis_fingerprint",
    )

    regulatory_raw = raw.get("regulatory_basis")
    regulatory_basis: RegulatoryBdiBasis | None = None
    if regulatory_raw is not None:
        regulatory = _json_mapping(regulatory_raw, "regulatory_basis")
        if set(regulatory) - {
            "amount", "currency", "basis_fingerprint", "minimum_rate",
            "source", "reference_id",
        }:
            raise ValueError("regulatory_basis contains unsupported fields")
        regulatory_basis = RegulatoryBdiBasis(
            amount=_json_fraction(regulatory.get("amount"), "regulatory amount"),
            currency=_json_text(regulatory.get("currency"), "regulatory currency"),
            basis_fingerprint=_json_text(
                regulatory.get("basis_fingerprint"), "regulatory basis_fingerprint",
            ),
            minimum_rate=_json_fraction(
                regulatory.get("minimum_rate"), "regulatory minimum_rate",
            ),
            source=_json_text(regulatory.get("source"), "regulatory source"),
            reference_id=_json_text(
                regulatory.get("reference_id"), "regulatory reference_id",
            ),
        )

    minimum_raw = raw.get("minimum_profit_margin")
    minimum_profit_margin = (
        None if minimum_raw is None
        else _json_fraction(minimum_raw, "minimum_profit_margin")
    )
    if minimum_profit_margin is not None and minimum_profit_margin < 0:
        raise ValueError("minimum_profit_margin must be nonnegative")

    pool_ledger = build_skill05_exact_pool_ledger(canonical)
    activity_goods = build_activity_goods_from_catalog(canonical, catalogo)
    p18 = book_skill04_planned_consumption_preview(
        canonical,
        pool_ledger,
        activity_goods,
    )
    if inventory_scope.status == "NO_INVENTORY":
        if raw.get("inventory") is not None:
            raise ValueError("NO_INVENTORY scope cannot contain inventory declarations")
        reconciliation = reconcile_financial_sources(
            pool_ledger,
            p18.consumption,
        )
    else:
        if raw.get("inventory") is None:
            raise ValueError("COMPLETE inventory scope requires explicit P19 inventory declarations")
        holding, provisioning = _build_p19_journals(
            raw["inventory"],
            consumption=p18.consumption,
            catalog_metadata=catalog_metadata,
        )
        reconciliation = reconcile_financial_sources(
            pool_ledger,
            p18.consumption,
            holding,
            provisioning,
        )

    return {
        "inventory_scope": inventory_scope,
        "reconciliation": reconciliation,
        "bdi_by_category": bdi_by_category,
        "catalog": catalog,
        "catalog_metadata": catalog_metadata,
        "operational_basis_fingerprint": operational_basis_fingerprint,
        "regulatory_basis": regulatory_basis,
        "minimum_profit_margin": minimum_profit_margin,
    }



def _unknown(result: Resultado, validations: list, intent: str, reason: str) -> None:
    status = "AVISO" if intent == "PREVIEW" else "ERRO"
    result.pricing_diagnostics = {"status": "UNKNOWN", "reason": reason}
    result.pricing_gates = {
        "status": "UNKNOWN",
        "regulatory_status": "UNKNOWN",
        "profitability_status": "UNKNOWN",
        "reason": reason,
    }
    result.pricing_authority = "P21_C_PRICING_GATES_UNKNOWN_NOT_PROJECT_GO"
    validations.append(
        ValidacaoItem(
            codigo="VAL-P21-PRICE-EVIDENCE",
            status=status,
            mensagem=(
                "Preço não certificado: " if intent != "PREVIEW" else
                "Diagnóstico de preço indisponível: "
            ) + reason,
        )
    )


def apply_pricing_report_evidence(
    result: Resultado,
    inputs: Mapping[str, object],
    validations: list,
) -> None:
    """Attach exact P21 diagnostics and gates to the canonical Skill 06 result.

    All transports serialize this canonical result, so REST, MCP, UI, RFI and
    RFP see the same status. A missing P20 ledger is UNKNOWN, never PASS.
    """
    intent = str(inputs.get("certification_intent", "PREVIEW")).upper()
    context = inputs.get("p21_pricing_evidence", inputs.get("p20_financial_sources"))
    if not isinstance(context, Mapping):
        _unknown(
            result, validations, intent,
            "missing p21_pricing_evidence with authoritative P20 ledger and explicit bases",
        )
        return
    # Mapping's runtime check proves shape only; narrow its generic parameters
    # before reading string-keyed evidence fields.
    if not all(isinstance(key, str) for key in context):
        _unknown(result, validations, intent, "pricing evidence keys must be strings")
        return
    context = cast(Mapping[str, object], context)
    source_build_error = context.get("source_build_error")
    if isinstance(source_build_error, str):
        _unknown(result, validations, intent, source_build_error)
        return
    inventory_scope = context.get("inventory_scope")
    if not isinstance(inventory_scope, InventoryEvidenceScope):
        _unknown(
            result, validations, intent,
            "typed, provenance-bearing P19 inventory scope is required before pricing",
        )
        return
    if inventory_scope.status == "NO_INVENTORY" and (
        context.get("holding_journal") is not None
        or context.get("stock_provisioning_journal") is not None
    ):
        _unknown(
            result, validations, intent,
            "NO_INVENTORY scope conflicts with supplied P19 journals",
        )
        return
    if inventory_scope.status == "COMPLETE" and (
        not isinstance(context.get("reconciliation"), ExactFinancialReconciliation)
        and context.get("holding_journal") is None
        and context.get("stock_provisioning_journal") is None
    ):
        _unknown(
            result, validations, intent,
            "COMPLETE inventory scope requires an explicit holding or provisioning journal",
        )
        return

    reconciliation = context.get("reconciliation")
    if not isinstance(reconciliation, ExactFinancialReconciliation):
        pool_ledger = context.get("pool_ledger")
        consumption_journal = context.get("consumption_journal")
        holding_journal = context.get("holding_journal")
        stock_provisioning_journal = context.get("stock_provisioning_journal")
        if pool_ledger is not None and consumption_journal is not None:
            if (
                not isinstance(pool_ledger, ExclusiveCostLedger)
                or not isinstance(consumption_journal, PhysicalConsumptionJournalResult)
                or (holding_journal is not None and not isinstance(holding_journal, HoldingJournal))
                or (
                    stock_provisioning_journal is not None
                    and not isinstance(stock_provisioning_journal, ExternalStockProvisioningJournal)
                )
            ):
                _unknown(
                    result,
                    validations,
                    intent,
                    "P20/P19 reconciliation requires typed P17 ledger and P18/P19 journals",
                )
                return
            try:
                reconciliation = reconcile_financial_sources(
                    pool_ledger,
                    consumption_journal,
                    holding_journal,
                    stock_provisioning_journal,
                )
            except (TypeError, ValueError) as exc:
                _unknown(result, validations, intent, str(exc))
                return
    bdi_by_category_raw = context.get("bdi_by_category")
    catalog = context.get("catalog")
    catalog_metadata_raw = context.get("catalog_metadata")
    operational_basis_fingerprint = context.get("operational_basis_fingerprint")
    regulatory_basis = context.get("regulatory_basis")
    minimum_profit_margin = context.get("minimum_profit_margin")
    if (
        not isinstance(reconciliation, ExactFinancialReconciliation)
        or not isinstance(bdi_by_category_raw, Mapping)
        or not all(
            isinstance(category, str) and isinstance(rate, Fraction)
            for category, rate in bdi_by_category_raw.items()
        )
        or not isinstance(catalog, CatalogPriceBenchmark)
        or not isinstance(catalog_metadata_raw, Mapping)
        or not all(isinstance(key, str) for key in catalog_metadata_raw)
        or not isinstance(operational_basis_fingerprint, str)
        or (regulatory_basis is not None and not isinstance(regulatory_basis, RegulatoryBdiBasis))
        or (
            minimum_profit_margin is not None
            and (type(minimum_profit_margin) is not Fraction or minimum_profit_margin < 0)
        )
    ):
        _unknown(
            result, validations, intent,
            "pricing evidence has missing or invalid exact ledger, catalog, currency, or regulatory inputs",
        )
        return
    bdi_by_category = cast(Mapping[str, Fraction], bdi_by_category_raw)
    catalog_metadata = cast(Mapping[str, object], catalog_metadata_raw)

    try:
        diagnostics = project_operational_pricing(
            reconciliation,
            bdi_by_category=bdi_by_category,
            catalog=catalog,
            catalog_metadata=catalog_metadata,
            operational_basis_fingerprint=operational_basis_fingerprint,
        )
        gates = evaluate_pricing_gates(
            diagnostics,
            regulatory_basis=regulatory_basis,
            catalog_metadata=catalog_metadata,
            minimum_profit_margin=minimum_profit_margin,
        )
    except (TypeError, ValueError) as exc:
        _unknown(result, validations, intent, str(exc))
        return

    result.pricing_diagnostics = {
        "operational_price": str(diagnostics.operational_price),
        "catalog_benchmark": str(diagnostics.catalog_benchmark),
        "direct_cost": str(diagnostics.direct_cost),
        "indirect_cost": str(diagnostics.indirect_cost),
        "total_cost": str(diagnostics.total_cost),
        "profit_amount": str(diagnostics.profit_amount),
        "implied_bdi_on_catalog": (
            str(diagnostics.implied_bdi_on_catalog)
            if diagnostics.implied_bdi_on_catalog is not None else None
        ),
        "cost_ratio_vs_catalog": (
            str(diagnostics.cost_ratio_vs_catalog)
            if diagnostics.cost_ratio_vs_catalog is not None else None
        ),
        "realized_margin": (
            str(diagnostics.realized_margin)
            if diagnostics.realized_margin is not None else None
        ),
        "equivalent_markup": (
            str(diagnostics.equivalent_markup)
            if diagnostics.equivalent_markup is not None else None
        ),
        "catalog_comparison": diagnostics.catalog_comparison,
        "comparison_reason": diagnostics.comparison_reason,
        "currency": diagnostics.operational_currency,
        "currency_source": diagnostics.currency_source,
        "currency_metadata_fingerprint": diagnostics.currency_metadata_fingerprint,
    }
    result.pricing_gates = {
        "status": gates.status,
        "regulatory_status": gates.regulatory_status,
        "profitability_status": gates.profitability_status,
        "regulatory_bdi_rate": str(gates.regulatory_bdi_rate) if gates.regulatory_bdi_rate is not None else None,
        "regulatory_bdi_floor": str(gates.regulatory_bdi_floor) if gates.regulatory_bdi_floor is not None else None,
        "profit_amount": str(gates.profit_amount),
        "realized_margin": str(gates.realized_margin) if gates.realized_margin is not None else None,
        "minimum_profit_margin": str(gates.minimum_profit_margin) if gates.minimum_profit_margin is not None else None,
        "regulatory_basis_reference": gates.regulatory_basis_reference,
        "reasons": "; ".join(gates.reasons),
    }
    result.pricing_authority = gates.authority
    if gates.status != "PASS":
        status = "AVISO" if intent == "PREVIEW" else "ERRO"
        validations.append(
            ValidacaoItem(
                codigo="VAL-P21-PRICE-GATES",
                status=status,
                mensagem=(
                    f"Pricing gates {gates.status}: " + "; ".join(gates.reasons)
                ),
            )
        )
