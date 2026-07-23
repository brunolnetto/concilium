"""Coverage sweep 8 — cube_projection_views, side_effects, escopo_store, etapa_diffs."""

from __future__ import annotations

import pytest

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



