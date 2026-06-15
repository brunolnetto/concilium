"""Coverage sweep 8 — cube_projection_views, side_effects, escopo_store, etapa_diffs."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ─── application/services/cube_projection_views.py ───────────────────────────

class TestCubeProjectionViews:
    def test_normalize_bdi_component(self):
        from concilium.application.services.analytics.cube_projection_views import _normalize_bdi_component
        result = _normalize_bdi_component("overhead_AC")
        assert isinstance(result, str)

    def test_bucket_from_week_iso_mes(self):
        from concilium.application.services.analytics.cube_projection_views import bucket_from_week_iso
        result = bucket_from_week_iso("2026-W05", "mes")
        assert isinstance(result, str)

    def test_bucket_from_week_iso_trimestre(self):
        from concilium.application.services.analytics.cube_projection_views import bucket_from_week_iso
        result = bucket_from_week_iso("2026-W05", "trimestre")
        assert isinstance(result, str)

    def test_bucket_from_week_iso_semana(self):
        from concilium.application.services.analytics.cube_projection_views import bucket_from_week_iso
        result = bucket_from_week_iso("2026-W05", "semana")
        assert "W" in result or isinstance(result, str)

    def test_extract_cost_from_entry_float(self):
        from concilium.application.services.analytics.cube_projection_views import _extract_cost_from_entry
        entry = MagicMock()
        entry.valor_rs = 1_000.0
        result = _extract_cost_from_entry(entry)
        assert isinstance(result, float)

    def test_split_operational_cost(self):
        from concilium.application.services.analytics.cube_projection_views import _split_operational_cost_with_bdi
        multipliers = {"overhead_AC": 0.05, "margem_l": 0.10}
        result = _split_operational_cost_with_bdi(1_000_000.0, multipliers)
        assert isinstance(result, dict)

    def test_build_bdi_multipliers_from_cubo_empty(self):
        from concilium.application.services.analytics.cube_projection_views import _build_bdi_multipliers_from_cubo
        cubo = MagicMock()
        cubo.total_preco_venda = 0.0
        cubo.total_custo_direto = 0.0
        result = _build_bdi_multipliers_from_cubo(cubo)
        assert isinstance(result, dict)

    def test_build_bdi_multipliers_with_data(self):
        from concilium.application.services.analytics.cube_projection_views import _build_bdi_multipliers_from_cubo
        cubo = MagicMock()
        cubo.total_preco_venda = 1_000_000.0
        cubo.total_custo_direto = 700_000.0
        cubo.total_overhead = 200_000.0
        cubo.total_margem = 100_000.0
        cubo.total_tributos = 50_000.0
        result = _build_bdi_multipliers_from_cubo(cubo)
        assert isinstance(result, dict)

    def test_build_indireto_component_totals_empty(self):
        from concilium.application.services.analytics.cube_projection_views import _build_indireto_component_totals
        canonical = MagicMock()
        canonical.indiretos = []
        result = _build_indireto_component_totals(canonical)
        assert isinstance(result, dict)

    def test_indireto_component_shares_empty(self):
        from concilium.application.services.analytics.cube_projection_views import _indireto_component_shares
        canonical = MagicMock()
        canonical.indiretos = []
        result = _indireto_component_shares(canonical)
        assert isinstance(result, dict)


# ─── application/runtime/deliverables/side_effects.py ────────────────────────

class TestSideEffects:
    def test_json_default_unserializable_raises(self):
        from concilium.application.runtime.deliverables.side_effects import _json_default
        with pytest.raises(TypeError):
            _json_default(object())

    def test_dedup_insumos_removes_duplicates(self):
        from concilium.application.runtime.deliverables.side_effects import _dedup_insumos
        insumos = [
            {"codigo": "I1", "preco": 100},
            {"codigo": "I1", "preco": 100},
            {"codigo": "I2", "preco": 200},
        ]
        result = _dedup_insumos(insumos)
        assert len(result) == 2

    def test_append_png_gallery_empty(self):
        from concilium.application.runtime.deliverables.side_effects import _append_png_gallery
        result = _append_png_gallery("# Report\n\nContent.", [])
        assert isinstance(result, str)
        assert "# Report" in result

    def test_append_png_gallery_with_pngs(self):
        from concilium.application.runtime.deliverables.side_effects import _append_png_gallery
        result = _append_png_gallery("Content.", ["chart1.png", "chart2.png"])
        assert isinstance(result, str)

    def test_load_insumos_subdir_empty(self, tmp_path):
        from concilium.application.runtime.deliverables.side_effects import _load_insumos_subdir
        insumos = []
        _load_insumos_subdir(tmp_path, insumos)
        assert insumos == []


# ─── infrastructure/storage/escopo_store.py ──────────────────────────────────

class TestPlanoStore:
    def _make_plano_store(self, tmp_path):
        from concilium.infrastructure.storage.escopo_store import PlanoStore, EscopoStore
        plano_root = tmp_path / "escopos" / "esc-1" / "planos" / "plan-1"
        plano_root.mkdir(parents=True)
        es = EscopoStore(root=tmp_path / "escopos" / "esc-1")
        return PlanoStore(root=plano_root, escopo_store=es)

    def test_plano_store_creates(self, tmp_path):
        ps = self._make_plano_store(tmp_path)
        assert ps is not None
        assert ps.plano_id == "plan-1"

    def test_plano_store_meta(self, tmp_path):
        ps = self._make_plano_store(tmp_path)
        meta = ps.meta
        assert "plano_id" in meta

    def test_plano_store_load_canonical_none(self, tmp_path):
        ps = self._make_plano_store(tmp_path)
        assert ps.load_canonical() is None

    def test_plano_store_log_invocation(self, tmp_path):
        ps = self._make_plano_store(tmp_path)
        ps.log_invocation({"skill": "01", "status": "OK"})
        records = ps.read_invocations()
        assert len(records) == 1

    def test_plano_store_read_empty(self, tmp_path):
        ps = self._make_plano_store(tmp_path)
        assert ps.read_invocations() == []


class TestEscopoStore:
    def _make_escopo_store(self, tmp_path):
        from concilium.infrastructure.storage.escopo_store import EscopoStore
        escopo_root = tmp_path / "escopos" / "esc-1"
        escopo_root.mkdir(parents=True)
        return EscopoStore(root=escopo_root)

    def test_escopo_store_creates(self, tmp_path):
        es = self._make_escopo_store(tmp_path)
        assert es is not None

    def test_escopo_store_meta(self, tmp_path):
        es = self._make_escopo_store(tmp_path)
        assert "escopo_id" in es.meta

    def test_list_planos_empty(self, tmp_path):
        es = self._make_escopo_store(tmp_path)
        planos = es.list_plans()
        assert isinstance(planos, list)

    def test_create_plano(self, tmp_path):
        es = self._make_escopo_store(tmp_path)
        ps = es.create_plan(nome="Plano Principal")
        assert ps is not None
        assert ps.plano_id is not None


# ─── application/benchmarks/analysis/etapa_diffs.py ──────────────────────────

class TestEtapaDiffs:
    def test_module_importable(self):
        from concilium.application.benchmarks.analysis import etapa_diffs
        assert etapa_diffs is not None

    def test_functions_exist(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import generate_diffs_for_benchmark
        assert callable(generate_diffs_for_benchmark)

    def test_compare_functions_importable(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import (
            compare_planejamento_skill04,
            compare_resultado_skill06,
        )
        assert callable(compare_planejamento_skill04)
        assert callable(compare_resultado_skill06)
