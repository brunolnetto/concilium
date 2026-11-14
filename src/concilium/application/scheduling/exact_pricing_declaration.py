"""Exact pricing declaration of a project from its profile (N9, #206).

P21 prices the exact P20 ledger with declared inputs only. For a project that
does not hand-write ``p21_pricing_evidence`` they come from the construction
profile's ``precificacao_exata`` block — the project-level default declaration:

- ``tabela_bdi``: BDI components per row; each category markup is the TCU
  formula (Acórdão 2622/2013-Plenário) in exact rationals,
  ``(1 + (AC + R + S + G)) (1 + DF) (1 + L) / (1 - T) - 1``, with MO from
  ``mao_obra``, EQ from ``servicos`` (equipment working inside a service takes
  the service BDI; reduced BDI is only for mere supply, Súmula TCU 253), MAT
  from ``material``, COMB from ``diesel`` and IND from ``indireto``;
- ``piso_bdi_regulatorio``: the BDI floor for the project's work type, with
  its source;
- ``escopo_estoque``: the declared inventory scope;
- the minimum profit margin is the profile's ``faixa_margem_aceitavel.min``.

The catalog benchmark and the regulatory basis amount are the derived catalog
envelope C^cat. Nothing is defaulted: a missing or inexact field returns the
reason and no declaration, so the price is not evaluated.
"""

from __future__ import annotations

from collections.abc import Mapping
from fractions import Fraction
from typing import Any

from concilium.application.scheduling.catalog_cost_envelope import derive_catalog_cost_envelope

P21_INPUT_SCHEMA = "concilium.p21.pricing-evidence.v1"
PROFILE_SCHEMA = "concilium.perfil.precificacao-exata.v1"
FORMULA = "TCU_ACORDAO_2622_2013"
CATEGORY_ROWS = {"MO": "mao_obra", "EQ": "servicos", "MAT": "material", "COMB": "diesel", "IND": "indireto"}
_OVERHEAD = ("ac", "r", "cr", "df", "l")
_TAXES = ("cofins", "iss", "pis", "cssl", "ir")


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


def tcu_bdi_rate(row: object, label: str = "BDI row") -> Fraction:
    """``(1 + (AC + R + S + G)) (1 + DF) (1 + L) / (1 - T) - 1`` in exact rationals.

    ``r`` carries risk/insurance/guarantee and ``cr`` the risk contingency
    (together R + S + G); ``T`` is the sum of the taxes on the sale price.
    """
    if not isinstance(row, Mapping):
        raise PricingDeclarationError(f"{label} must be a mapping of BDI components")
    unknown = set(row) - set(_OVERHEAD) - set(_TAXES)
    missing = [name for name in (*_OVERHEAD, *_TAXES) if name not in row]
    if unknown or missing:
        raise PricingDeclarationError(
            f"{label} must declare exactly {', '.join((*_OVERHEAD, *_TAXES))}"
            + (f"; missing {missing}" if missing else "")
            + (f"; unknown {sorted(unknown)}" if unknown else "")
        )
    parts = {name: _rate(row[name], f"{label}.{name}") for name in (*_OVERHEAD, *_TAXES)}
    taxes = sum((parts[name] for name in _TAXES), Fraction(0))
    if taxes >= 1:
        raise PricingDeclarationError(f"{label}: taxes on the sale price must be below 100%")
    numerator = (1 + parts["ac"] + parts["r"] + parts["cr"]) * (1 + parts["df"]) * (1 + parts["l"])
    return numerator / (1 - taxes) - 1


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
    bdi = {category: tcu_bdi_rate(rows.get(row), f"tabela_bdi.{row}") for category, row in CATEGORY_ROWS.items()}

    floor = block.get("piso_bdi_regulatorio")
    if not isinstance(floor, Mapping) or not isinstance(floor.get("fonte"), str) or not floor["fonte"].strip():
        raise PricingDeclarationError("precificacao_exata.piso_bdi_regulatorio with its fonte is required")
    by_type = floor.get("por_tipo_obra")
    if not isinstance(by_type, Mapping) or tipo_obra not in by_type:
        raise PricingDeclarationError(f"no regulatory BDI floor declared for work type {tipo_obra!r}")
    entry = by_type[tipo_obra]
    if not isinstance(entry, Mapping) or not isinstance(entry.get("referencia"), str):
        raise PricingDeclarationError(f"regulatory BDI floor for {tipo_obra!r} must declare taxa and referencia")

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
        "bdi_by_category": bdi,
        "table_source": table["fonte"],
        "minimum_profit_margin": _rate(str(band["min"]), "faixa_margem_aceitavel.min"),
        "regulatory_floor": _rate(entry.get("taxa"), f"piso_bdi_regulatorio.{tipo_obra}.taxa"),
        "regulatory_source": f"{floor['fonte']} — {entry['referencia']}",
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
            "minimum_rate": str(terms["regulatory_floor"]),
            "source": terms["regulatory_source"],
            "reference_id": f"perfil:{profile_id}:piso_bdi:{tipo_obra}",
        },
        "minimum_profit_margin": str(terms["minimum_profit_margin"]),
    }, []
