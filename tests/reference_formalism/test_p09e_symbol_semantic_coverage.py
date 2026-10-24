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

# Independently reviewed expected atom sets from the 21 normative contracts.
# This witness is intentionally NOT imported from the provenance JSON:
# deleting an individual symbol from the registry must falsify the gate.
REQUIRED_NORMATIVE_TERMS = {
    "FL-001": frozenset(["\\mathcal{A}","A_i","n_{\\text{ativ}}"]),
    "FL-002": frozenset(["A_i","Q_i","E_i","W_i","B_i"]),
    "FL-003": frozenset(["c_r","V_r^{\\text{mensal}}","s_{\\text{mes}}","d_i","h_i","\\kappa_r","p_{g(r)}","\\text{cat}(r)"]),
    "FL-004": frozenset(["F_i(m)","s_i","t_i","\\mathcal G_i^D","m"]),
    "FL-005": frozenset(["W_i","m_i^0","\\mu_i^+","m_i^1","\\mu_i^-","m_i^{\\max}"]),
    "FL-006": frozenset(["m_i(\\tau)","\\tau","N_i","m_i^0","\\mu_i^+","m_i^{\\max}","m_i^1","\\mu_i^-"]),
    "FL-007": frozenset(["\\mu_i^+","\\mu_i^-","m_i^0","m_i^1","m_i^{\\max}","m_i(\\tau)","\\tau","N_i"]),
    "FL-008": frozenset(["m_{ij}","m_i(","j_i^0","j","N_i"]),
    "FL-009": frozenset(["B_i","\\mathcal{A}","A_i","\\theta_i"]),
    "FL-010": frozenset(["\\Phi_b(j)","Q_b","q_{b,j'}","j_b^0","j"]),
    "FL-011": frozenset(["s_{\\text{mes}}"]),
    "FL-012": frozenset(["d_i","h_i"]),
    "FL-013": frozenset(["\\beta^{EQ}","\\beta^{MO}","\\beta^{MAT}","\\beta^{COMB}","\\beta^{IND}"]),
    "FL-021": frozenset(["q_{i,j_i^1}","Q_i","q_{ij}","j_i^0","j_i^1"]),
    "FL-022": frozenset(["\\varphi_i","q_{i,j_i^1}","F_i(","m_i(","N_i","h_i","d_i","\\varepsilon_{i,j_i^1}^{exog}"]),
    "FL-023": frozenset(["q_{ij}","Q_i","j_i^0","j_i^1"]),
    "FL-024": frozenset(["\\mathcal{A}_j","A_i","\\mathcal{A}","j_i^0","j","N_i"]),
    "FL-075": frozenset(["\\mathcal{L}","ADM","TOP","LAB","QSMS","MOB^{\\text{site}}"]),
    "FL-076": frozenset(["\\text{driver}(l)","l","\\texttt{perm}","\\texttt{onetime}"]),
    "FL-077": frozenset(["l","\\text{driver}(l)","\\Gamma_l^{k,\\text{mensal}}","k","c_l^{\\text{mob}}","c_l^{\\text{demob}}","\\Gamma_l^{VM,\\text{mensal}}"]),
    "FL-078": frozenset(["\\gamma_l^{k,\\text{sem}}","\\Gamma_l^{k,\\text{mensal}}","s_{\\text{mes}}","m_l(j)","j","n"]),
}



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
    assert set(normative) == set(REQUIRED_NORMATIVE_TERMS)
    assert conditioned.isdisjoint(traced)
    assert len(conditioned) == 72
    for id_, equation in traced.items():
        expression = normative[id_]["expression"]
        assert evidence[id_]["expression"] == expression
        assert evidence[id_]["proof_status"] == "DIMENSIONAL_UNDER_TYPED_PRECONDITIONS"
        assert equation["terms"], id_
        assert {t["latex"] for t in equation["terms"]} == REQUIRED_NORMATIVE_TERMS[id_], id_
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


def test_missing_single_symbol_fails_even_if_equation_counts_are_unchanged() -> None:
    # Regress reviewer falsifier: deleting h_i from FL-022 left total
    # counts >110 and still passed older global-count-only checks.
    cloned = json.loads(json.dumps(COVERAGE))
    row = next(e for e in cloned["equations"] if e["id"] == "FL-022")
    row["terms"] = [t for t in row["terms"] if t["latex"] != "h_i"]
    assert len(row["terms"]) >= 1
    with pytest.raises(AssertionError):
        validate_normative_coverage(INVENTORY, PROOFS, cloned)


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
