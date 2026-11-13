"""Independent C^cat goldens (FORMALISMO_LONGO Parts II–III, §XIV.8 BDI basis)."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from tests.reference_formalism.catalog_envelope_reference import (
    CatalogEnvelopeContractError,
    evaluate_catalog_envelope,
)

PATH = Path(__file__).parent / "vectors" / "catalog_envelope_v1.json"


def goldens() -> list[dict]:
    doc = json.loads(PATH.read_text(encoding="utf-8"))
    assert doc["protocol"] == "formalism-catalog-envelope/1"
    assert doc["formalism"]["baseline_blob"] == "f83d37c03b3dbcebc0cbb446cc6d4333fa05cdd5"
    return doc["vectors"]


@pytest.mark.parametrize("case", goldens(), ids=lambda c: c["case_id"])
def test_catalog_envelope_goldens_are_exact(case: dict) -> None:
    assert evaluate_catalog_envelope(deepcopy(case)) == case["expected"]


def test_corrupted_catalog_envelope_golden_is_detected() -> None:
    case = deepcopy(goldens()[0])
    case["expected"]["total"] = "667"
    assert evaluate_catalog_envelope(deepcopy(case)) != case["expected"]


def test_non_normative_month_length_is_rejected() -> None:
    case = deepcopy(goldens()[0])
    case["inputs"]["s_mes"] = "52/12"
    with pytest.raises(CatalogEnvelopeContractError, match="1461/336"):
        evaluate_catalog_envelope(case)


def test_unknown_contractual_price_unit_is_rejected() -> None:
    case = deepcopy(goldens()[0])
    case["inputs"]["activities"][0]["contractual"][0]["price_unit"] = "dia"
    with pytest.raises(CatalogEnvelopeContractError, match="mes or h"):
        evaluate_catalog_envelope(case)
