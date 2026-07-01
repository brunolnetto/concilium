"""Coverage batch 30 — pu_calculator, escopo_store, catalog_resolver small gaps."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# pu_calculator.py line 300:
# _check_pu_divergencia with bd.pu_calculado is None (valor_horario=0) → return
# ---------------------------------------------------------------------------


class TestCheckPuDivergenciaNull:
    def test_pu_calculado_none_returns_early(self):
        """Line 300: bd.pu_calculado is None (valor_horario=0) → early return."""
        from concilium.application.catalog.pu_calculator import BreakdownPU, _check_pu_divergencia

        bd = BreakdownPU(producao_id="P-01", valor_horario=0.0)  # pu_calculado → None
        pu_divergentes: list = []
        _check_pu_divergencia(
            bd, prod={"_cu_planilha_referencia": "100.0"}, tolerancia_pct=5.0, pu_divergentes=pu_divergentes
        )
        assert pu_divergentes == []


# ---------------------------------------------------------------------------
# pu_calculator.py lines 317-318:
# _check_pu_divergencia with non-numeric cpu_hint → ValueError → pass
# ---------------------------------------------------------------------------


class TestCheckPuDivergenciaInvalidHint:
    def test_non_numeric_cpu_hint_is_caught(self):
        """Lines 317-318: float('N/A') → ValueError → except → pass."""
        from concilium.application.catalog.pu_calculator import BreakdownPU, _check_pu_divergencia

        bd = BreakdownPU(producao_id="P-01", valor_horario=10.0, custo_mo_h=5.0)
        pu_divergentes: list = []
        _check_pu_divergencia(
            bd,
            prod={"_cu_planilha_referencia": "N/A"},  # not a float
            tolerancia_pct=5.0,
            pu_divergentes=pu_divergentes,
        )
        # Exception was caught, divergentes unchanged
        assert pu_divergentes == []

    def test_cpu_hint_none_returns_early_before_float(self):
        """Lines 302-303: cpu_hint is None → return early (no conversion attempted)."""
        from concilium.application.catalog.pu_calculator import BreakdownPU, _check_pu_divergencia

        bd = BreakdownPU(producao_id="P-01", valor_horario=10.0, custo_mo_h=5.0)
        pu_divergentes: list = []
        _check_pu_divergencia(bd, prod={}, tolerancia_pct=5.0, pu_divergentes=pu_divergentes)
        assert pu_divergentes == []


# ---------------------------------------------------------------------------
# escopo_store.py lines 154-155:
# PlanoStore.read_invocations with malformed JSON line → JSONDecodeError → pass
# ---------------------------------------------------------------------------


class TestPlanoStoreReadInvocationsInvalidJson:
    def test_malformed_json_line_is_skipped(self, tmp_path):
        """Lines 154-155: invalid JSON line in invocations.log → JSONDecodeError → pass."""
        from concilium.infrastructure.storage.escopo_store import PlanoStore

        plan_dir = tmp_path / "plan-001"
        plan_dir.mkdir()
        log_file = plan_dir / PlanoStore.INVOCATIONS_LOG
        # Write one valid and one invalid JSON line
        log_file.write_text('{"skill_id": "01"}\nNOT-VALID-JSON\n', encoding="utf-8")

        store = PlanoStore(root=plan_dir)
        result = store.read_invocations()
        # Only the valid line is returned; invalid is skipped
        assert len(result) == 1
        assert result[0]["skill_id"] == "01"


# ---------------------------------------------------------------------------
# catalog_resolver.py line 271:
# _resolve_catalog_items with item having empty/missing id → continue
# ---------------------------------------------------------------------------


class TestResolveCatalogItemsEmptyId:
    def test_item_with_no_id_or_codigo_is_skipped(self):
        """Line 271: item with no id/codigo → iid='' → not iid → continue."""
        from concilium.application.services.catalog.catalog_resolver import (
            CatalogResolutionTrace,
            _resolve_catalog_items,
        )

        items = [
            {},  # no id, no codigo → iid='' → skipped
            {"id": "CPU-01", "val": 1},  # valid id → included
        ]
        trace = CatalogResolutionTrace()
        result = _resolve_catalog_items(items, id_key=None, jur_overlay={}, proj_overlay={}, trace=trace)

        assert len(result) == 1
        assert result[0]["id"] == "CPU-01"

    def test_item_with_empty_id_key_is_skipped(self):
        """Line 271: item.get(id_key, '') == '' → skipped."""
        from concilium.application.services.catalog.catalog_resolver import (
            CatalogResolutionTrace,
            _resolve_catalog_items,
        )

        items = [
            {"codigo": "", "descricao": "orphan"},  # codigo='' → skipped
            {"codigo": "INS-01", "descricao": "valid"},
        ]
        trace = CatalogResolutionTrace()
        result = _resolve_catalog_items(items, id_key="codigo", jur_overlay={}, proj_overlay={}, trace=trace)

        assert len(result) == 1
        assert result[0]["codigo"] == "INS-01"
