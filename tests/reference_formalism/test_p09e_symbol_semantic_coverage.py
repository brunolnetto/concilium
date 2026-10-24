"""P09-E: complete provenance / semantic-location gates for normative candidates.

These checks do not certify conditional financial identities; those belong to
issues #11/#13/#16–#21. The gate fails closed on missing symbol links.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "docs/product/5-specifications/formulario_longo"


def load(name: str) -> dict:
    return json.loads((DIR / name).read_text(encoding="utf-8"))


INVENTORY = load("EQUATION_INVENTORY_P09C.json")
PROOFS = load("NORMATIVE_DIMENSION_PROOFS_P09D.json")
COVERAGE = load("NORMATIVE_SYMBOL_COVERAGE_P09E.json")


def validate_normative_coverage(
    inventory: dict,
    proofs: dict,
    coverage: dict,
) -> None:
    assert coverage["schema"] == "concilium.formalism.normative_symbol_coverage.v1"
    normative = {
        row["id"]: row
        for row in inventory["rows"]
        if row["status"] == "NORMATIVE_CANDIDATE"
    }
    conditioned = {
        row["id"]
        for row in inventory["rows"]
        if row["status"] == "CONDITIONAL_OR_UNCERTIFIED"
    }
    evidence = {row["id"]: row for row in proofs["proofs"]}
    traced = {row["id"]: row for row in coverage["equations"]}
    assert len(normative) == len(evidence) == len(traced) == 21
    assert len(coverage["equations"]) == len(traced)
    assert set(normative) == set(evidence) == set(traced)
    assert conditioned.isdisjoint(traced)
    assert len(conditioned) == 72
    for id_, equation in traced.items():
        expression = normative[id_]["expression"]
        assert evidence[id_]["expression"] == expression
        assert evidence[id_]["proof_status"] == "DIMENSIONAL_UNDER_TYPED_PRECONDITIONS"
        assert equation["terms"], id_
        keys: set[str] = set()
        for term in equation["terms"]:
            assert set(("latex", "unit", "source", "output")) <= set(term)
            assert all(
                isinstance(term[field], str) and term[field].strip()
                for field in ("latex", "unit", "source", "output")
            )
            assert term["latex"] in expression, (id_, term["latex"])
            assert term["latex"] not in keys, (id_, term["latex"])
            keys.add(term["latex"])
        assert set(equation["representations"]) == {"resumido", "tex"}
        for format_ in ("resumido", "tex"):
            assert equation["representations"][format_]["semantic_anchor"]


def test_symbol_provenance_for_all_21_normative_equations() -> None:
    validate_normative_coverage(INVENTORY, PROOFS, COVERAGE)
    assert sum(len(e["terms"]) for e in COVERAGE["equations"]) >= 110
    assert len({t["latex"] for e in COVERAGE["equations"] for t in e["terms"]}) >= 65


def test_missing_normative_provenance_causes_failure() -> None:
    modified = {**COVERAGE, "equations": COVERAGE["equations"][1:]}
    with pytest.raises(AssertionError):
        validate_normative_coverage(INVENTORY, PROOFS, modified)


def test_conditional_identity_cannot_be_promoted_to_normative() -> None:
    modified = {
        **COVERAGE,
        "equations": [
            *COVERAGE["equations"],
            {"id": "FL-037", "terms": [], "representations": {}},
        ],
    }
    with pytest.raises(AssertionError):
        validate_normative_coverage(INVENTORY, PROOFS, modified)


@pytest.mark.parametrize(
    "equation",
    COVERAGE["equations"],
    ids=lambda e: e["id"],
)
def test_each_semantic_reference_exists_in_short_and_tex(equation: dict) -> None:
    documents = {
        "resumido": (DIR / "FORMALISMO_RESUMIDO.md").read_text(encoding="utf-8"),
        "tex": (DIR / "formulario_longo.tex").read_text(encoding="utf-8"),
    }
    for fmt, content in documents.items():
        anchor = equation["representations"][fmt]["semantic_anchor"]
        assert anchor in content, (equation["id"], fmt, anchor)


def test_critical_aliases_carry_consistent_units_and_lineage() -> None:
    indexed = defaultdict(list)
    for equation in COVERAGE["equations"]:
        for term in equation["terms"]:
            indexed[term["latex"]].append(term)
    # Repeated symbols may have different human descriptions of origin, but
    # the same physical dimensional type. No monetary proxy into unit_g.
    for token, expected in (
        ("Q_i", "activity-unit quantity"),
        ("F_i(m)", "activity-units/operating hour"),
        ("\\kappa_r", "good-units/operating hour"),
        ("p_{g(r)}", "BRL/good-unit"),
        ("s_{\\text{mes}}", "weeks/month"),
        ("\\mu_i^+", "fronts/weekly transition"),
        ("\\mu_i^-", "fronts/weekly transition"),
    ):
        assert indexed[token], token
        assert all(t["unit"] == expected for t in indexed[token]), token
    assert "money" not in indexed["\\kappa_r"][0]["unit"]
    assert "good-unit" in indexed["p_{g(r)}"][0]["unit"]


def test_critical_meaning_is_preserved_across_representations() -> None:
    long = (DIR / "FORMALISMO_LONGO.md").read_text(encoding="utf-8")
    short = (DIR / "FORMALISMO_RESUMIDO.md").read_text(encoding="utf-8")
    tex = (DIR / "formulario_longo.tex").read_text(encoding="utf-8")
    conventions = (DIR / "CONVENCOES_NORMATIVAS.md").read_text(encoding="utf-8")
    # Three independently important normative claims must be true in all
    # renderings. Merely finding a symbol elsewhere cannot satisfy these.
    for name, text in (("LONGO", long), ("RESUMIDO", short), ("TEX", tex)):
        assert "m_i^0=m_i^1=m_i^{max}" in text or "m_i^0=m_i^1=m_i^{\\max}" in text, name
        assert "μ" in text or "\\mu" in text, name
        assert "P09-D" in text, name
        assert "UNVERIFIED" in text, name
    assert "Δw_j = 1 semana" in conventions
    assert "gap=0" in conventions
    assert "UNKNOWN" in conventions
    assert "NOT_EVALUATED" in conventions
    # Typed relationship: an amount summed over cells has unit Q, not Q/week;
    # partial final production does not discount fixed weekly K.
    assert "φ_i" in conventions
    assert "R$/h" in long
    assert "\\varphi_i" in tex
