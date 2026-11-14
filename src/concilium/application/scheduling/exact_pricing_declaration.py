"""Exact pricing declaration of a project from its profile (N9, #206).

P21 prices the exact P20 ledger with declared inputs only. For a project that
does not hand-write ``p21_pricing_evidence`` they come from the construction
profile's ``precificacao_exata`` block — the project-level default declaration.

The declaration is made of **markup layers**, not of a flat rate: each row of
``tabela_bdi`` declares its overhead (AC, R+S+G, DF), its profit (L) and its
taxes on the sale price, plus its ``natureza`` (``servico`` or
``fornecimento``). The category markup is the layers' consequence by the TCU
formula (Acórdão 2622/2013-Plenário); MO comes from ``mao_obra``, EQ from
``servicos`` (equipment working inside a service takes the service layers;
there is no rental/maintenance blend), MAT from ``material``, COMB from
``diesel`` and IND from ``indireto``.

- The BDI floor is declared per nature and applies **per category**; the
  aggregate floor of the V2 gate is their average weighted by the catalog
  composition (contractual K at the MO/EQ floor, consumable V at the MAT/COMB
  floor).
- The minimum margin (``faixa_margem_aceitavel.min``) is a criterion on the
  profit layer's share of the sale price.
- ``escopo_estoque`` declares the inventory scope.

Nothing is defaulted: a missing or inexact field returns the reason and no
declaration, so the price is not evaluated.
"""

from __future__ import annotations

from collections.abc import Mapping
from fractions import Fraction
from typing import Any

from concilium.application.scheduling.catalog_cost_envelope import derive_catalog_cost_envelope
from concilium.application.scheduling.markup_layers import LayerRates

P21_INPUT_SCHEMA = "concilium.p21.pricing-evidence.v1"
PROFILE_SCHEMA = "concilium.perfil.precificacao-exata.v1"
FORMULA = "TCU_ACORDAO_2622_2013"
CATEGORY_ROWS = {"MO": "mao_obra", "EQ": "servicos", "MAT": "material", "COMB": "diesel", "IND": "indireto"}
_OVERHEAD = ("ac", "r", "cr", "df", "l")
_TAXES = ("cofins", "iss", "pis", "cssl", "ir")
NATURES = ("servico", "fornecimento")


class PricingDeclarationError(ValueError):
    """The profile does not declare complete exact pricing terms."""


def _rate(value: object, label: str) -> Fraction:
    if not isinstance(value, str) or not value.strip():
        raise PricingDeclarationError(f"{label} must be an exact decimal or rational string")
    try:
        rate = Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise PricingDeclarationError(f"{label} must be an exact decimal or rational string") from exc
    if rate < 0:
        raise PricingDeclarationError(f"{label} must be nonnegative")
    return rate


def profile_row_layers(row: object, label: str = "BDI row") -> LayerRates:
    """Layer rates of one profile row. ``r`` (risk/insurance/guarantee) and ``cr``
    (risk contingency) together are R + S + G; every tax is kept by name."""
    if not isinstance(row, Mapping):
        raise PricingDeclarationError(f"{label} must be a mapping of BDI components")
    fields = (*_OVERHEAD, *_TAXES, "natureza")
    unknown = set(row) - set(fields)
    missing = [name for name in fields if name not in row]
    if unknown or missing:
        raise PricingDeclarationError(
            f"{label} must declare exactly {', '.join(fields)}"
            + (f"; missing {missing}" if missing else "")
            + (f"; unknown {sorted(unknown)}" if unknown else "")
        )
    if row["natureza"] not in NATURES:
        raise PricingDeclarationError(f"{label}.natureza must be one of {', '.join(NATURES)}")
    parts = {name: _rate(row[name], f"{label}.{name}") for name in (*_OVERHEAD, *_TAXES)}
    try:
        return LayerRates(
            ac=parts["ac"],
            rsg=parts["r"] + parts["cr"],
            df=parts["df"],
            profit=parts["l"],
            taxes=tuple((name, parts[name]) for name in _TAXES),
        )
    except ValueError as exc:
        raise PricingDeclarationError(f"{label}: {exc}") from exc


def tcu_bdi_rate(row: object, label: str = "BDI row") -> Fraction:
    """``(1 + (AC + R + S + G)) (1 + DF) (1 + L) / (1 - T) - 1`` in exact rationals."""
    return profile_row_layers(row, label).beta


def profile_pricing_terms(perfil: object, tipo_obra: str) -> dict[str, Any]:
    """Category markups, minimum margin, regulatory floor and inventory scope."""
    if not isinstance(perfil, Mapping) or not isinstance(perfil.get("precificacao_exata"), Mapping):
        raise PricingDeclarationError("profile declares no precificacao_exata block")
    block = perfil["precificacao_exata"]
    if block.get("schema") != PROFILE_SCHEMA or block.get("formula_bdi") != FORMULA:
        raise PricingDeclarationError(f"precificacao_exata must declare schema {PROFILE_SCHEMA} and formula {FORMULA}")

    table = block.get("tabela_bdi")
    if not isinstance(table, Mapping) or not isinstance(table.get("fonte"), str) or not table["fonte"].strip():
        raise PricingDeclarationError("precificacao_exata.tabela_bdi with its fonte is required")
    rows = table.get("linhas")
    if not isinstance(rows, Mapping):
        raise PricingDeclarationError("precificacao_exata.tabela_bdi.linhas is required")
    layers = {
        category: profile_row_layers(rows.get(row), f"tabela_bdi.{row}") for category, row in CATEGORY_ROWS.items()
    }
    natures = {category: rows[row]["natureza"] for category, row in CATEGORY_ROWS.items()}

    floor = block.get("piso_bdi_regulatorio")
    if not isinstance(floor, Mapping) or not isinstance(floor.get("fonte"), str) or not floor["fonte"].strip():
        raise PricingDeclarationError("precificacao_exata.piso_bdi_regulatorio with its fonte is required")
    service = floor.get("servico")
    by_type = service.get("por_tipo_obra") if isinstance(service, Mapping) else None
    if not isinstance(by_type, Mapping) or tipo_obra not in by_type:
        raise PricingDeclarationError(f"no regulatory BDI floor declared for work type {tipo_obra!r}")
    floors_by_nature: dict[str, Fraction] = {}
    references: list[str] = []
    for nature, entry in (("servico", by_type[tipo_obra]), ("fornecimento", floor.get("fornecimento"))):
        if not isinstance(entry, Mapping) or not isinstance(entry.get("referencia"), str):
            raise PricingDeclarationError(f"regulatory BDI floor for {nature!r} must declare taxa and referencia")
        floors_by_nature[nature] = _rate(entry.get("taxa"), f"piso_bdi_regulatorio.{nature}.taxa")
        references.append(f"{nature}: {entry['referencia']}")
    floors = {category: floors_by_nature[natures[category]] for category in CATEGORY_ROWS}

    scope = block.get("escopo_estoque")
    if (
        not isinstance(scope, Mapping)
        or scope.get("status") not in ("NO_INVENTORY", "COMPLETE")
        or not isinstance(scope.get("fonte"), str)
        or not scope["fonte"].strip()
    ):
        raise PricingDeclarationError("precificacao_exata.escopo_estoque must declare status and fonte")

    band = perfil.get("faixa_margem_aceitavel")
    if not isinstance(band, Mapping) or isinstance(band.get("min"), bool) or band.get("min") is None:
        raise PricingDeclarationError("profile declares no faixa_margem_aceitavel.min")
    return {
        "layers": layers,
        "bdi_by_category": {category: rates.beta for category, rates in layers.items()},
        "bdi_floor_by_category": floors,
        "table_source": table["fonte"],
        "minimum_profit_margin": _rate(str(band["min"]), "faixa_margem_aceitavel.min"),
        "regulatory_source": f"{floor['fonte']} — {'; '.join(references)}",
        "inventory_status": scope["status"],
        "inventory_source": scope["fonte"],
    }


def build_p21_declaration(
    perfil: object, canonical: Any, catalogo: Mapping[str, object]
) -> tuple[dict[str, Any] | None, list[str]]:
    """``(declaration, reasons)``: the ``p21_pricing_evidence`` JSON, or why not."""
    projeto = getattr(canonical, "projeto", None)
    tipo_obra = getattr(projeto, "tipo_obra", None)
    if not isinstance(tipo_obra, str) or not tipo_obra:
        return None, ["project work type (tipo_obra) is not declared"]
    try:
        terms = profile_pricing_terms(perfil, tipo_obra)
    except PricingDeclarationError as exc:
        return None, [str(exc)]
    currency = catalogo.get("currency")
    if not isinstance(currency, str) or not currency:
        return None, ["resolved catalog declares no currency"]
    try:
        envelope = derive_catalog_cost_envelope(canonical, catalogo)
    except (ValueError, TypeError, KeyError, ZeroDivisionError) as exc:
        return None, [f"catalog envelope C^cat is not derivable: {exc}"]
    floors = terms["bdi_floor_by_category"]
    if floors["MO"] != floors["EQ"] or floors["MAT"] != floors["COMB"]:
        return None, [
            "aggregate BDI floor needs one floor for the contractual block (MO, EQ) and one for the "
            "consumable block (MAT, COMB): the catalog envelope does not split them further"
        ]
    contractual = sum((a.contractual for a in envelope.activities), Fraction(0))
    consumable = sum((a.consumable for a in envelope.activities), Fraction(0))
    if envelope.total <= 0:
        return None, ["catalog envelope C^cat must be positive"]
    # Aggregate floor of the V2 gate: per-category floors weighted by the catalog composition.
    aggregate_floor = (contractual * floors["MO"] + consumable * floors["MAT"]) / envelope.total
    basis = envelope.fingerprint()
    profile_id = str(perfil.get("id")) if isinstance(perfil, Mapping) else "perfil"
    amount = str(envelope.total)
    return {
        "schema": P21_INPUT_SCHEMA,
        "inventory_scope": {
            "status": terms["inventory_status"],
            "source": terms["inventory_source"],
            "reference_id": f"perfil:{profile_id}:escopo_estoque",
            "fingerprint": f"perfil:{profile_id}:{terms['inventory_status']}",
        },
        "bdi_by_category": {category: str(rate) for category, rate in terms["bdi_by_category"].items()},
        "markup_layers": {category: rates.as_json() for category, rates in terms["layers"].items()},
        "bdi_floor_by_category": {category: str(rate) for category, rate in floors.items()},
        "catalog": {
            "amount": amount,
            "currency": currency,
            "source": "derived C^cat from resolved project catalog (catalog_cost_envelope)",
            "reference_id": f"catalog-envelope:{basis[:16]}",
            "basis_fingerprint": basis,
        },
        "operational_basis_fingerprint": basis,
        "regulatory_basis": {
            "amount": amount,
            "currency": currency,
            "basis_fingerprint": basis,
            "minimum_rate": str(aggregate_floor),
            "source": (
                f"{terms['regulatory_source']} — agregado ponderado pela composição de catálogo "
                f"(K {contractual} ao piso de MO/EQ, V {consumable} ao piso de MAT/COMB)"
            ),
            "reference_id": f"perfil:{profile_id}:piso_bdi:{tipo_obra}",
        },
        "minimum_profit_margin": str(terms["minimum_profit_margin"]),
    }, []
