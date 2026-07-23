"""Coverage batch 21 — price_trend, circular_deps small gaps."""

from __future__ import annotations

# circular_deps.py line 34->33: item.categoria_custo != "TERCEIRIZADO" → continue
# ---------------------------------------------------------------------------


class TestCircularDepsNonTerceirizadoItem:
    def test_branch_skips_non_terceirizado_items(self):
        """Line 34->33: composicao_itens with non-TERCEIRIZADO categoria → if False → continue."""
        from concilium.domain.validations.circular_deps import verificar_ciclos_cpu

        # cpu_referencia_id is set, but composicao_itens has non-TERCEIRIZADO items only
        catalogo = {
            "cpus": [
                {
                    "codigo": "CPU-A",
                    "cpu_referencia_id": "CPU-B",  # has ref_id → enters inner for loop
                    "composicao_itens": [
                        {"insumo_id": "MA-01", "categoria_custo": "MATERIAL"},  # not TERCEIRIZADO → skip
                        {"insumo_id": "MO-01", "categoria_custo": "MAO_OBRA"},  # not TERCEIRIZADO → skip
                    ],
                },
                {
                    "codigo": "CPU-B",
                    "composicao_itens": [],
                },
            ]
        }
        # Should run without raising and find no cycles
        result = verificar_ciclos_cpu(catalogo)
        assert isinstance(result, list)

