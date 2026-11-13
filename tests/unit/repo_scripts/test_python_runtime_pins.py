"""Guard: every pinned Python runtime matches ``.python-version``.

Renovate PR #3 moved CI, Docker and ``.python-version`` to 3.15 while
``ortools`` ships no cp315 wheels, so install failed everywhere. Without
working CI the drift went unnoticed. This test keeps a single declared
runtime and makes any partial bump fail locally and in CI.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]

# Matrix entries in formalism-reference-cross-version are intentionally
# different versions and use ``${{ matrix.python }}``, so they are not matched.
PINNED_FILES = (
    ".github/workflows/ci.yml",
    ".github/workflows/build-proxy.yml",
    "Dockerfile",
    "cd/development/Dockerfile.dev",
)
PATTERNS = (
    re.compile(r'python-version:\s*"(\d+\.\d+)"'),
    re.compile(r"FROM\s+python:(\d+\.\d+)[-\s]"),
)


def _declared_runtime() -> str:
    return (ROOT / ".python-version").read_text(encoding="utf-8").strip()


def _pins(relative: str) -> list[str]:
    text = (ROOT / relative).read_text(encoding="utf-8")
    return [m.group(1) for pattern in PATTERNS for m in pattern.finditer(text)]


def test_declared_runtime_is_major_minor() -> None:
    assert re.fullmatch(r"3\.\d+", _declared_runtime())


@pytest.mark.parametrize("relative", PINNED_FILES)
def test_pins_match_declared_runtime(relative: str) -> None:
    pins = _pins(relative)
    assert pins, f"{relative}: no Python pin found; update PATTERNS or PINNED_FILES"
    declared = _declared_runtime()
    assert set(pins) == {declared}, f"{relative}: pins {pins} != .python-version {declared}"


TY_PIN = re.compile(r"ty==(\d+\.\d+\.\d+)")


def test_ci_ty_pin_matches_pyproject_dev_pins() -> None:
    """CI hardcoded ty 0.0.56 while pyproject pinned 0.0.95; CI then
    reported errors the declared checker does not. One version only."""
    declared = set(TY_PIN.findall((ROOT / "pyproject.toml").read_text(encoding="utf-8")))
    declared |= set(
        TY_PIN.findall((ROOT / "tools/mcp-proxy/pyproject.toml").read_text(encoding="utf-8"))
    )
    assert len(declared) == 1, f"pyproject ty pins disagree: {sorted(declared)}"
    ci = TY_PIN.findall((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    assert ci, "ci.yml no longer pins ty; update this guard"
    assert set(ci) == declared, f"ci.yml ty pins {ci} != pyproject {sorted(declared)}"


def test_pyproject_floor_admits_declared_runtime() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    floor = re.search(r'requires-python\s*=\s*">=(\d+)\.(\d+)"', text)
    assert floor is not None
    major, minor = map(int, _declared_runtime().split("."))
    assert (major, minor) >= (int(floor.group(1)), int(floor.group(2)))
