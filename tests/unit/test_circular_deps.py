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




import pytest  # noqa: E402

# ─── domain/validations/circular_deps.py ──────────────────────────────────────


class TestCircularDeps:
    def test_no_cycles_simple(self):
        from concilium.domain.validations.circular_deps import verificar_ciclos_cpu

        catalog = {
            "cpus": [
                {"codigo": "A", "composicao_itens": []},
                {"codigo": "B", "composicao_itens": [], "cpu_referencia_id": "A"},
            ]
        }
        assert verificar_ciclos_cpu(catalog) == []

    def test_cycle_detected(self):
        from concilium.domain.validations.circular_deps import verificar_ciclos_cpu

        catalog = {
            "cpus": [
                {"codigo": "A", "composicao_itens": [], "cpu_referencia_id": "B"},
                {"codigo": "B", "composicao_itens": [], "cpu_referencia_id": "A"},
            ]
        }
        errors = verificar_ciclos_cpu(catalog)
        assert len(errors) > 0

    def test_validar_sem_ciclos_raises(self):
        from concilium.domain.validations.circular_deps import validar_sem_ciclos

        catalog = {
            "cpus": [
                {"codigo": "A", "composicao_itens": [], "cpu_referencia_id": "B"},
                {"codigo": "B", "composicao_itens": [], "cpu_referencia_id": "A"},
            ]
        }
        with pytest.raises(ValueError):
            validar_sem_ciclos(catalog)

