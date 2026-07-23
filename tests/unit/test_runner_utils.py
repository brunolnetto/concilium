"""Coverage batch 17 — artifact_store, flat_version_store, runner_utils small gaps."""

from __future__ import annotations

# runner_utils.py line 71->70: equip without 'custo_mensal' → if check False → continue
# ---------------------------------------------------------------------------


class TestApplyCustoDeltaEquipNoCustoMensal:
    def test_equipment_without_custo_mensal_skipped(self):
        """Line 71->70 branch: equip has no 'custo_mensal' key → if 'custo_mensal' in equip: False."""
        from concilium.application.scenarios.runner_utils import apply_custo_delta

        inputs = {
            "composicao_customizada": {
                "ITEM-01": {
                    "funcoes": [],
                    "equipamentos": [
                        {"equip_id": "EQ-01"},  # no custo_mensal → skipped
                        {"equip_id": "EQ-02", "custo_mensal": 8000.0},  # has it → updated
                    ],
                }
            }
        }
        result = apply_custo_delta(inputs, delta=1.1)

        equips = result["composicao_customizada"]["ITEM-01"]["equipamentos"]
        # EQ-01 has no custo_mensal → unchanged
        assert "custo_mensal" not in equips[0]
        # EQ-02 has custo_mensal → updated by delta
        assert equips[1]["custo_mensal"] == round(8000.0 * 1.1, 2)

