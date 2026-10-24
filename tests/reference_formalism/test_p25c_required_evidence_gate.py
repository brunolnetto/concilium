"""Pure stdlib negative fixtures for mandatory economic PR gate."""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/formalism_contract_change_gate.py"
spec = importlib.util.spec_from_file_location("formalism_contract_change_gate", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

PRODUCTION = "src/concilium/application/scheduling/economic_regime_contracts.py"
LONG = "docs/product/5-specifications/formulario_longo/FORMALISMO_LONGO.md"
GOLDEN = "tests/reference_formalism/vectors/economic_reconciliation_v1.json"
INVENTORY = "docs/product/5-specifications/formulario_longo/EQUATION_INVENTORY_P09C.json"


def test_negative_economic_mutation_cannot_pass_without_evidence() -> None:
    assert module.assess_paths({PRODUCTION})[0] is False
    assert module.assess_paths({PRODUCTION, LONG})[0] is False
    assert module.assess_paths({PRODUCTION, GOLDEN})[0] is False
    assert module.assess_paths({PRODUCTION, INVENTORY, GOLDEN})[0] is False


def test_economic_change_requires_both_normative_and_golden() -> None:
    valid, reason = module.assess_paths({PRODUCTION, LONG, GOLDEN})
    assert valid, reason


def test_economics_core_model_and_deletion_are_protected() -> None:
    assert module.is_economic("src/concilium/domain/models/canonical/_pool_recursos.py")
    assert module.is_economic("src/concilium/domain/models/canonical/_estoque_consumiveis.py")
    assert not module.assess_paths({PRODUCTION, LONG,
        "tests/reference_formalism/vectors/physical_calendar_v1.json"})[0]


def test_non_economic_refactor_does_not_require_false_evidence() -> None:
    assert module.assess_paths({"src/concilium/api/router.py"})[0]


def test_empty_or_unresolved_diff_fails_closed() -> None:
    assert module.assess_paths(set())[0] is False


def test_known_physical_contracts_trigger_protection() -> None:
    for file in module.ECONOMIC_PATHS:
        assert module.is_economic(file), file


def test_existing_finance_sources_are_economic_without_any_fixtures() -> None:
    protected = (
        "src/concilium/application/scheduling/realized_financial_metrics.py",
        "src/concilium/application/scheduling/financial_cost_reconciliation.py",
        "src/concilium/application/scheduling/skill06_realized_consumer.py",
        "src/concilium/application/skills/manifests/06-resultado-financeiro/_precificacao/pricing.py",
    )
    for source in protected:
        assert module.is_economic(source), source
        assert not module.assess_paths({source})[0], source


def test_git_rename_with_economic_mutation_preserves_source_path(
    tmp_path: Path, monkeypatch,
) -> None:
    """A high-similarity rename must not evade the requirement for witnesses."""
    repo = tmp_path / "git"
    repo.mkdir()

    def git(*args: str) -> str:
        return subprocess.check_output(
            ["git", *args], cwd=repo, text=True,
        ).strip()

    git("init", "-q", "-b", "main")
    git("config", "user.name", "P25-C Fixture")
    git("config", "user.email", "ci-fixture@example.invalid")
    original = repo / PRODUCTION
    original.parent.mkdir(parents=True)
    original.write_text(
        "# Stable economic contract witness\n" * 80 + "price = 100\n",
        encoding="utf-8",
    )
    git("add", "-A")
    git("commit", "-q", "-m", "baseline")
    base = git("rev-parse", "HEAD")
    moved = repo / "src/legacy/unprotected.py"
    moved.parent.mkdir(parents=True)
    original.rename(moved)
    moved.write_text(moved.read_text(encoding="utf-8").replace(
        "price = 100", "price = 200",
    ), encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "rename and double price")
    head = git("rev-parse", "HEAD")
    monkeypatch.chdir(repo)
    changed = module.git_changed(base, head)
    assert PRODUCTION in changed, changed
    assert "src/legacy/unprotected.py" in changed, changed
    assert not module.assess_paths(changed)[0]


def test_divergent_force_push_does_not_hide_economic_reversion(
    tmp_path: Path, monkeypatch,
) -> None:
    """A prior main tip and a divergent replacement have no shared direct diff."""
    repo = tmp_path / "divergent"
    repo.mkdir()

    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()

    git("init", "-q", "-b", "main")
    git("config", "user.name", "P25-C Fixture")
    git("config", "user.email", "ci-fixture@example.invalid")
    economic = repo / PRODUCTION
    economic.parent.mkdir(parents=True)
    economic.write_text("cost = 100\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "common root")
    common = git("rev-parse", "HEAD")

    economic.write_text("cost = 200\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "old main tip changes economic cost")
    before = git("rev-parse", "HEAD")

    git("switch", "--detach", "-q", common)
    (repo / "README.md").write_text("replacement tip\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "divergent force push")
    after = git("rev-parse", "HEAD")

    monkeypatch.chdir(repo)
    # Wrong PR-style comparison hides the reverted change.
    assert PRODUCTION not in module.git_changed(before, after, mode="pr")
    # Push must compare the two endpoints and expose the financial reversion.
    detected = module.git_changed(before, after, mode="push")
    assert PRODUCTION in detected, detected
    assert not module.assess_paths(detected)[0]
