"""Coverage boost test for fuel.py __main__ block."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

# ═══════════════════════════════════════════════════════════════════════════════
# fuel.py — lines 181-189 (__main__ block)
# ═══════════════════════════════════════════════════════════════════════════════


class TestFuelMainBlock:
    """Cover the if __name__ == '__main__' block in fuel.py (lines 181-189)."""

    @staticmethod
    def _make_api_response() -> dict:
        return {
            "data_coleta": "2024-01-15 00:00:00",
            "fonte": "ANP",
            "moeda": "BRL",
            "precos": {
                "gasolina": {
                    "GO": "5.50",
                    "SP": "6.64",
                    "RJ": "6.20",
                },
                "diesel": {
                    "GO": "6.25",
                    "SP": "6.80",
                    "RJ": "6.55",
                },
                "diesel_s10": {
                    "GO": "6.35",
                    "SP": "6.90",
                    "RJ": "6.65",
                },
                "etanol": {
                    "GO": "3.75",
                    "SP": "4.10",
                    "RJ": "4.50",
                },
            },
            "error": None,
        }

    @patch("requests.get")
    def test_fuel_main_block_execution(self, mock_get):
        """Running fuel module as __main__ executes the usage examples (lines 181-189)."""
        import runpy

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = self._make_api_response()
        mock_get.return_value = mock_response

        _mod = "concilium.infrastructure.clients.fuel"
        _saved = sys.modules.pop(_mod, None)
        try:
            # This runs the __main__ block, covering lines 181-189
            runpy.run_module(_mod, run_name="__main__", alter_sys=False)
        finally:
            if _saved is not None:
                sys.modules[_mod] = _saved
