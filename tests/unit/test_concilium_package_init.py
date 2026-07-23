"""Coverage sweep — files with few missing lines (1-30 lines missing)."""

from __future__ import annotations

import pytest

# ─── concilium/__init__.py ───────────────────────────────────────────────────


def test_package_getattr_raises():
    import concilium

    with pytest.raises(AttributeError, match="no attribute"):
        _ = concilium.nonexistent_attribute



