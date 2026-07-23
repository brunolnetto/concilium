"""Coverage batch 12 — small 1-2 miss targets across many files."""

from __future__ import annotations

from types import SimpleNamespace

# executive_summary.py line 20: _get returns getattr when obj is not a dict
# ---------------------------------------------------------------------------


class TestExecutiveSummaryGetHelper:
    def test_get_uses_getattr_for_non_dict_obj(self):
        """Line 20: obj is not a dict → return getattr(obj, key, default)."""
        from concilium.application.runtime.deliverables.reports.executive_summary import _get

        obj = SimpleNamespace(custo_total=99_000.0)
        assert _get(obj, "custo_total") == 99_000.0
        assert _get(obj, "nonexistent_key", "fallback") == "fallback"


# ---------------------------------------------------------------------------




# executive_summary.py line 20:
# _get(dict, key) → isinstance(obj, dict) True → return obj.get(key, default)
# ---------------------------------------------------------------------------


class TestExecutiveSummaryGetDict:
    def test_get_with_dict_returns_value(self):
        """Line 20: obj is dict → return obj.get(key, default)."""
        from concilium.application.runtime.deliverables.reports.executive_summary import _get

        result = _get({"foo": "bar"}, "foo", "default")
        assert result == "bar"

    def test_get_with_dict_missing_key_returns_default(self):
        """Line 20: obj is dict, key missing → return default."""
        from concilium.application.runtime.deliverables.reports.executive_summary import _get

        result = _get({"other": 1}, "foo", "fallback")
        assert result == "fallback"


# ---------------------------------------------------------------------------

