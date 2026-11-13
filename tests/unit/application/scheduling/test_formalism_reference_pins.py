"""Certificates pin the normative spec and the independent oracles by git blob.

If any pinned file changes without updating the pin, every certificate would
keep claiming the old formalism/oracle identity. This guard recomputes each
blob and fails on drift (a small, concrete slice of #26).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from concilium.application.scheduling import formalism_certification_service as service

ROOT = Path(__file__).resolve().parents[4]
PATHS = {
    "long": "docs/product/5-specifications/formulario_longo/FORMALISMO_LONGO.md",
    "resumido": "docs/product/5-specifications/formulario_longo/FORMALISMO_RESUMIDO.md",
    "physical-reference": "tests/reference_formalism/physical_reference.py",
    "economic-reference": "tests/reference_formalism/economic_reference.py",
    "physical-vector": "tests/reference_formalism/vectors/physical_calendar_v1.json",
    "economic-vector": "tests/reference_formalism/vectors/economic_reconciliation_v1.json",
    "calendar-oracle": "tests/reference_formalism/calendar_rcpsp_oracle.py",
    "catalog-envelope-oracle": "tests/reference_formalism/catalog_envelope_reference.py",
    "catalog-envelope-vector": "tests/reference_formalism/vectors/catalog_envelope_v1.json",
    "activity-cost-oracle": "tests/reference_formalism/activity_cost_reference.py",
    "activity-cost-vector": "tests/reference_formalism/vectors/activity_cost_reconciliation_v1.json",
    "consumption-declaration-oracle": "tests/reference_formalism/consumption_declaration_reference.py",
    "consumption-declaration-vector": "tests/reference_formalism/vectors/consumption_declaration_v1.json",
}


def _pins() -> dict[str, str]:
    raw = f"{service._FORMALISM_REFERENCE};{service._ORACLE_REFERENCE}"
    return dict(entry.split(":", 1) for entry in raw.split(";"))


def _git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def test_every_pin_has_a_known_file() -> None:
    assert set(_pins()) == set(PATHS)


@pytest.mark.parametrize("label", sorted(PATHS))
def test_pinned_blob_matches_the_file(label: str) -> None:
    assert _git_blob(ROOT / PATHS[label]) == _pins()[label], (
        f"{PATHS[label]} changed: update the pin in formalism_certification_service (and re-review the formalism)"
    )
