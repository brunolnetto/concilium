"""P11-C: active (not merely referenced) normative contract in three renderings."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "docs/product/5-specifications/formulario_longo"


def test_active_contract_replaces_nominal_alias_in_all_three_formats() -> None:
    files = [
        "FORMALISMO_LONGO.md",
        "FORMALISMO_RESUMIDO.md",
        "formulario_longo.tex",
    ]
    for name in files:
        text = (DIR / name).read_text(encoding="utf-8")
        assert "P11-C" in text, name
        assert r"\varepsilon_{ij}^{real}" in text, name
        assert r"\zeta" in text and r"\pi" in text, name
        assert "normativ" in text.lower(), name
        assert "standby" in text or "standby" in (
            DIR / "P11A_EFICIENCIA_REAL_IDENTIDADES.md"
        ).read_text(encoding="utf-8"), name
        assert "K" in text and "BDI" in text, name


def test_short_and_long_per_week_cost_ratios_use_realized_reference() -> None:
    for name in ("FORMALISMO_LONGO.md", "FORMALISMO_RESUMIDO.md"):
        content = (DIR / name).read_text(encoding="utf-8")
        assert r"\zeta" in content and r"\pi" in content
        assert r"\sum_jq_{ij}" in content
        assert r"\sum_jR_{ij}" in content
        assert r"\kappa" in content
        assert "revogad" in content or "suspensas" in content


def test_p11c_keeps_reference_equation_inventory_stable() -> None:
    import json

    inventory = json.loads(
        (DIR / "EQUATION_INVENTORY_P09C.json").read_text(encoding="utf-8")
    )
    assert len(inventory["rows"]) == 93
    assert sum(
        row["status"] == "NORMATIVE_CANDIDATE"
        for row in inventory["rows"]
    ) == 21
    # P11-C does not retroactively promote 72 P09-C conditionals to GO.
    assert sum(
        row["status"] == "CONDITIONAL_OR_UNCERTIFIED"
        for row in inventory["rows"]
    ) == 72
