"""Tests for four 0%-coverage benchmark modules.

Covers:
  1. src/concilium/application/benchmarks/_chart_colors.py
  2. src/concilium/application/benchmarks/cronograma_parser.py
  3. src/concilium/application/benchmarks/reconciliacao_planejamento.py
  4. src/concilium/application/benchmarks/analise_llm_reconciliacao.py
"""

from __future__ import annotations

# 1. _chart_colors
# ---------------------------------------------------------------------------


class TestChartColors:
    def test_cores_is_dict_with_at_least_10_keys(self):
        from concilium.application.benchmarks.charts._chart_colors import _CORES

        assert isinstance(_CORES, dict)
        assert len(_CORES) >= 10

    def test_cores_values_are_hex_strings(self):
        from concilium.application.benchmarks.charts._chart_colors import _CORES

        for key, value in _CORES.items():
            assert isinstance(value, str), f"Expected str for key {key!r}, got {type(value)}"
            assert value.startswith("#"), f"Value for {key!r} should start with '#': {value!r}"

    def test_bg_is_string_starting_with_hash(self):
        from concilium.application.benchmarks.charts._chart_colors import BG

        assert isinstance(BG, str)
        assert BG.startswith("#")


# ---------------------------------------------------------------------------

