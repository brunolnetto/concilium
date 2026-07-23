"""Coverage batch 5 — visualization normalization, diesel fallback, and other small gaps."""

from __future__ import annotations

# pool_custo_estado.py lines 31, 40-42: normalize key fallbacks
# ---------------------------------------------------------------------------


class TestPoolCustoEstadoNormalizeKeys:
    def _comp(self, raw):
        from concilium.application.runtime.deliverables.visualizations.cube.pool_custo_estado import (
            _normalize_component_key,
        )

        return _normalize_component_key(raw)

    def _state(self, raw):
        from concilium.application.runtime.deliverables.visualizations.cube.pool_custo_estado import (
            _normalize_state_key,
        )

        return _normalize_state_key(raw)

    def test_unknown_component_returns_raw(self):
        """Line 31: no match → return txt as-is."""
        assert self._comp("unknown_comp") == "unknown_comp"

    def test_normalize_off_state(self):
        """Lines 40-41: 'off' → 'off'."""
        assert self._state("off") == "off"

    def test_normalize_desmobilizado_state(self):
        """Lines 40-41: 'desmobilizado' → 'off'."""
        assert self._state("desmobilizado") == "off"

    def test_unknown_state_returns_raw(self):
        """Line 42: no state match → return txt as-is."""
        assert self._state("unknown_state") == "unknown_state"


# ---------------------------------------------------------------------------

