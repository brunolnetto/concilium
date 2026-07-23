"""Coverage sweep — files with few missing lines (1-30 lines missing)."""

from __future__ import annotations

import pytest

# ─── domain/units.py ─────────────────────────────────────────────────────────


class TestDomainUnits:
    def test_normalize_canonical(self):
        from concilium.domain.units import normalize_unidade

        assert normalize_unidade("m³") == "m³"
        assert normalize_unidade("m²") == "m²"
        assert normalize_unidade("h") == "h"

    def test_normalize_alias(self):
        from concilium.domain.units import normalize_unidade

        assert normalize_unidade("M²") == "m²"
        assert normalize_unidade("M3") == "m³"
        assert normalize_unidade("UNID") == "unid"
        assert normalize_unidade("und") == "unid"

    def test_normalize_unknown_raises(self):
        from concilium.domain.units import normalize_unidade

        with pytest.raises(ValueError, match="desconhecida"):
            normalize_unidade("foobar")

    def test_alias_mes_variants(self):
        from concilium.domain.units import normalize_unidade

        assert normalize_unidade("MES") == "mes"
        assert normalize_unidade("mês") == "mes"

    def test_all_canonicas_pass_through(self):
        from concilium.domain.units import UNIDADES_CANONICAS, normalize_unidade

        for u in UNIDADES_CANONICAS:
            assert normalize_unidade(u) == u



