"""Coverage batch 22 — cubo_pool, _plausibility_checks small gaps."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# cubo_pool.py line 57->59: sequential key with unrecognized granularidade
# ---------------------------------------------------------------------------


class TestAgruparSemanaIso:
    def test_sequential_key_unknown_granularidade_returns_as_is(self):
        """Line 57->59: s='S001', granularidade='quinzena' (unknown) → none of the
        if conditions match inside sequential block → falls through to return s."""
        from concilium.domain.models.analytics.cubo_pool import bucket_periodo

        result = bucket_periodo("S001", granularidade="quinzena")
        assert result == "S001"  # returned unchanged

    def test_sequential_key_mes_covered(self):
        """Confirm mes path works (regression guard)."""
        from concilium.domain.models.analytics.cubo_pool import bucket_periodo

        result = bucket_periodo("S005", granularidade="mes")
        assert result == "M02"  # (5-1)//4 + 1 = 2

    def test_sequential_key_trimestre_covered(self):
        """Confirm trimestre path works."""
        from concilium.domain.models.analytics.cubo_pool import bucket_periodo

        result = bucket_periodo("S014", granularidade="trimestre")
        assert result == "T2"  # (14-1)//13 + 1 = 2

    def test_sequential_key_ano_covered(self):
        """Confirm ano path works (line 57 True branch)."""
        from concilium.domain.models.analytics.cubo_pool import bucket_periodo

        result = bucket_periodo("S053", granularidade="ano")
        assert result == "A2"  # (53-1)//52 + 1 = 2


# ---------------------------------------------------------------------------
# _plausibility_checks.py line 210: p <= 0 → continue in _pc_eq_diesel
# ---------------------------------------------------------------------------


class TestPcEqDieselZeroPotencia:
    def test_continues_when_potencia_cv_is_zero(self):
        """Line 210: p=0 → p <= 0 → continue (skipped, no anomalia added)."""
        from concilium.application.catalog._plausibility_checks import _pc_eq_diesel

        equipamentos = [
            {
                "codigo": "EQ-TRATOR-01",
                "atributos_especificos": {
                    "consumo_litros_hora": 5.0,
                    "potencia_cv": 0.0,  # p=0 → continue
                },
            }
        ]
        result = _pc_eq_diesel(equipamentos)
        assert result == []  # no anomalia, skipped

    def test_continues_when_potencia_cv_is_negative(self):
        """Line 210: p < 0 → p <= 0 → continue."""
        from concilium.application.catalog._plausibility_checks import _pc_eq_diesel

        equipamentos = [
            {
                "codigo": "EQ-INVALID",
                "atributos_especificos": {
                    "consumo_litros_hora": 5.0,
                    "potencia_cv": -10.0,  # negative → continue
                },
            }
        ]
        result = _pc_eq_diesel(equipamentos)
        assert result == []
