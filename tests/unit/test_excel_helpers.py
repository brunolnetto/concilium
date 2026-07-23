"""Coverage batch 18 — helpers, confidence, catalog_confronto small gaps."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

# helpers.py line 48: _find_eap_item returns None when not found
# helpers.py line 31->40: _project_months branch when data_inicio is None
# ---------------------------------------------------------------------------


class TestFindEapItemReturnsNone:
    def test_returns_none_when_not_found(self):
        """Line 48: loop exhausted without match → return None."""
        from concilium.infrastructure.adapters.excel.helpers import _find_eap_item

        item = SimpleNamespace(item_id="ITEM-01")
        result = _find_eap_item([item], "NONEXISTENT-ID")
        assert result is None

    def test_returns_none_from_empty_list(self):
        """Line 48: empty list → for loop body never executes → return None."""
        from concilium.infrastructure.adapters.excel.helpers import _find_eap_item

        assert _find_eap_item([], "ANY-ID") is None


class TestProjectMonthsNullDataInicio:
    def test_returns_empty_when_data_inicio_is_none(self):
        """Line 31->40: projeto exists but data_inicio is None → if False → return []."""
        from concilium.infrastructure.adapters.excel.helpers import _project_months

        canonical = SimpleNamespace(
            cronograma=None,
            projeto=SimpleNamespace(data_inicio=None, data_termino=date(2026, 12, 31)),
        )
        result = _project_months(canonical)
        assert result == []

    def test_returns_empty_when_data_termino_is_none(self):
        """Line 31->40: projeto has data_termino=None → if check False → return []."""
        from concilium.infrastructure.adapters.excel.helpers import _project_months

        canonical = SimpleNamespace(
            cronograma=None,
            projeto=SimpleNamespace(data_inicio=date(2026, 1, 1), data_termino=None),
        )
        result = _project_months(canonical)
        assert result == []


# ---------------------------------------------------------------------------

