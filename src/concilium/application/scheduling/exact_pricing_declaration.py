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

**Project declaration (N9.1).** Tax incidence and profit are project-specific
(ADR-023 §D6–D7): a project may declare, in exact strings, the profit ``l`` and
the applicability/rate of individual taxes of a row. The declaration is merged
over the profile's row **field by field** — a declared field replaces the
profile's, every other field stays the profile's — and the layers, the category
markup and the floors are then derived from the merged rows exactly as in N9.
Overhead (``ac``, ``r``, ``cr``, ``df``) and ``natureza`` are company-level and
cannot be overridden per project. The origin of every layer field (``profile``
or ``project``) is recorded in the declaration.

Nothing is defaulted: a missing or inexact field returns the reason and no
declaration, so the price is not evaluated.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from fractions import Fraction
from typing import Any

from concilium.application.scheduling.catalog_cost_envelope import derive_catalog_cost_envelope
from concilium.application.scheduling.markup_layers import PROVENANCE_SCHEMA, LayerRates

P21_INPUT_SCHEMA = "concilium.p21.pricing-evidence.v1"
PROFILE_SCHEMA = "concilium.perfil.precificacao-exata.v1"
FORMULA = "TCU_ACORDAO_2622_2013"
CATEGORY_ROWS = {"MO": "mao_obra", "EQ": "servicos", "MAT": "material", "COMB": "diesel", "IND": "indireto"}
_OVERHEAD = ("ac", "r", "cr", "df", "l")
_TAXES = ("cofins", "iss", "pis", "cssl", "ir")
NATURES = ("servico", "fornecimento")
PROJECT_SCHEMA = "concilium.projeto.bdi-exato.v1"
_PROJECT_ROW_FIELDS = ("l", "tributos")


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


def _project_tax_rate(entry: object, label: str) -> str:
    """Effective rate string of ``{"aplicavel": bool, "aliquota": exact}``: a tax
    that is not applicable is zero and must not carry a rate."""
    if not isinstance(entry, Mapping) or type(entry.get("aplicavel")) is not bool:
        raise PricingDeclarationError(f"{label} must declare aplicavel as an explicit boolean")
    unknown = set(entry) - {"aplicavel", "aliquota"}
    if unknown:
        raise PricingDeclarationError(f"{label} declares unknown fields {sorted(map(str, unknown))}")
    if not entry["aplicavel"]:
        if "aliquota" in entry:
            raise PricingDeclarationError(f"{label} is not applicable and must not declare aliquota")
        return "0"
    if "aliquota" not in entry:
        raise PricingDeclarationError(f"{label} is applicable and must declare aliquota")
    _rate(entry["aliquota"], f"{label}.aliquota")
    return str(entry["aliquota"])


def merge_project_rows(
    rows: Mapping[str, object], project: object
) -> tuple[dict[str, object], dict[str, set[str]], dict[str, str] | None]:
    """N9.1: profile rows with the project's declared fields replaced, field by field.

    Returns ``(merged rows, {row: fields that came from the project}, project
    reference)``. ``project`` is ``None`` (no project declaration: the rows are
    the profile's) or ``{"schema", "fonte", "linhas": {row: {"l": exact,
    "tributos": {tax: {"aplicavel": bool, "aliquota": exact}}}}}``.
    """
    merged: dict[str, object] = dict(rows)
    overridden: dict[str, set[str]] = {row: set() for row in CATEGORY_ROWS.values()}
    if project is None:
        return merged, overridden, None
    label = "project BDI declaration"
    if not isinstance(project, Mapping) or set(project) != {"schema", "fonte", "linhas"}:
        raise PricingDeclarationError(f"{label} must declare exactly schema, fonte and linhas")
    if project["schema"] != PROJECT_SCHEMA:
        raise PricingDeclarationError(f"{label} must declare schema {PROJECT_SCHEMA}")
    if not isinstance(project["fonte"], str) or not project["fonte"].strip():
        raise PricingDeclarationError(f"{label} must declare its fonte")
    lines = project["linhas"]
    if not isinstance(lines, Mapping) or not lines:
        raise PricingDeclarationError(f"{label}.linhas must override at least one row")
    for row_name, override in lines.items():
        row_label = f"{label}.linhas.{row_name}"
        if row_name not in overridden:
            raise PricingDeclarationError(
                f"{row_label}: unknown row; rows are {', '.join(CATEGORY_ROWS.values())}"
            )
        base = rows.get(row_name)
        if not isinstance(base, Mapping):
            raise PricingDeclarationError(f"{row_label}: the profile declares no such row to override")
        if not isinstance(override, Mapping) or not override:
            raise PricingDeclarationError(f"{row_label} must override at least one field")
        unknown = sorted(str(name) for name in set(override) - set(_PROJECT_ROW_FIELDS))
        if unknown:
            raise PricingDeclarationError(
                f"{row_label} declares {unknown}; a project overrides only l and tributos "
                "(overhead and natureza are declared by the profile)"
            )
        row = dict(base)
        if "l" in override:
            if "l" not in base:
                raise PricingDeclarationError(f"{row_label}.l: the profile row has no such field")
            _rate(override["l"], f"{row_label}.l")
            row["l"] = override["l"]
            overridden[row_name].add("l")
        if "tributos" in override:
            taxes = override["tributos"]
            if not isinstance(taxes, Mapping) or not taxes:
                raise PricingDeclarationError(f"{row_label}.tributos must override at least one tax")
            for tax, entry in taxes.items():
                if tax not in _TAXES or tax not in base:
                    raise PricingDeclarationError(
                        f"{row_label}.tributos.{tax}: the profile row has no such tax; taxes are {', '.join(_TAXES)}"
                    )
                row[tax] = _project_tax_rate(entry, f"{row_label}.tributos.{tax}")
                overridden[row_name].add(tax)
        merged[row_name] = row
    reference = {
        "schema": PROJECT_SCHEMA,
        "source": project["fonte"],
        "fingerprint": project_declaration_fingerprint(project),
    }
    return merged, overridden, reference


def project_declaration_fingerprint(project: object) -> str:
    """SHA-256 of the declaration's canonical JSON (sorted keys, no whitespace)."""
    return hashlib.sha256(
        json.dumps(project, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def validate_project_declaration(project: object, rows: Mapping[str, object] | None = None) -> None:
    """Raise unless ``project`` is a valid exact declaration (N9.1).

    With the profile's ``tabela_bdi.linhas`` the check is the one the price
    runs: merge, then derive every row's layers. Without them it is structural
    and exact — known rows and taxes, exact strings, declared taxes below 100%
    — and the merge against the profile still happens when the price is built.
    """
    if project is None:
        raise PricingDeclarationError("project BDI declaration is required")
    if rows is None:
        blank = {**dict.fromkeys((*_OVERHEAD, *_TAXES), "0"), "natureza": NATURES[0]}
        rows = {row: dict(blank) for row in CATEGORY_ROWS.values()}
    merged, _overridden, _reference = merge_project_rows(rows, project)
    for row in CATEGORY_ROWS.values():
        profile_row_layers(merged.get(row), f"tabela_bdi.{row} merged with the project BDI declaration")


def _field_origins(overridden: set[str]) -> dict[str, object]:
    """Origin of each layer field of one category, in the shape of ``LayerRates.as_json``."""
    return {
        "ac": "profile",
        "rsg": "profile",
        "df": "profile",
        "l": "project" if "l" in overridden else "profile",
        "taxes": {tax: "project" if tax in overridden else "profile" for tax in _TAXES},
    }


def profile_pricing_terms(perfil: object, tipo_obra: str, project_bdi: object = None) -> dict[str, Any]:
    """Category markups, minimum margin, regulatory floor and inventory scope.

    ``project_bdi`` is the project's exact declaration (N9.1), merged over the
    profile rows before the layers are derived.
    """
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
    # The profile must be complete on its own: the project replaces fields, it does not fill gaps.
    for row in CATEGORY_ROWS.values():
        profile_row_layers(rows.get(row), f"tabela_bdi.{row}")
    merged, overridden, project_reference = merge_project_rows(rows, project_bdi)
    layers = {
        category: profile_row_layers(
            merged[row], f"tabela_bdi.{row}" + (" merged with the project BDI declaration" if overridden[row] else "")
        )
        for category, row in CATEGORY_ROWS.items()
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
        "project_reference": project_reference,
        "layer_origins": {category: _field_origins(overridden[row]) for category, row in CATEGORY_ROWS.items()},
        "minimum_profit_margin": _rate(str(band["min"]), "faixa_margem_aceitavel.min"),
        "regulatory_source": f"{floor['fonte']} — {'; '.join(references)}",
        "inventory_status": scope["status"],
        "inventory_source": scope["fonte"],
    }


def build_p21_declaration(
    perfil: object, canonical: Any, catalogo: Mapping[str, object], project_bdi: object = None
) -> tuple[dict[str, Any] | None, list[str]]:
    """``(declaration, reasons)``: the ``p21_pricing_evidence`` JSON, or why not.

    ``project_bdi`` (N9.1) is the project's exact tax/profit declaration; when
    given it must be valid, otherwise there is no declaration at all.
    """
    projeto = getattr(canonical, "projeto", None)
    tipo_obra = getattr(projeto, "tipo_obra", None)
    if not isinstance(tipo_obra, str) or not tipo_obra:
        return None, ["project work type (tipo_obra) is not declared"]
    try:
        terms = profile_pricing_terms(perfil, tipo_obra, project_bdi)
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
        "markup_layers_provenance": {
            "schema": PROVENANCE_SCHEMA,
            "profile": {"reference_id": f"perfil:{profile_id}:tabela_bdi", "source": terms["table_source"]},
            "project": terms["project_reference"],
            "fields": terms["layer_origins"],
        },
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
