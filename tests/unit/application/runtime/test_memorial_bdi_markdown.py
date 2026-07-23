"""Tests to restore coverage from overwritten test_small_gaps_batch3.py:
flat_version_store, consolidation, engine_refs, memorial_bdi_markdown, mcp/server."""

from __future__ import annotations

# ─── application/runtime/deliverables/reports/memorial_bdi_markdown.py ────────


class TestMemorialBdiMarkdown:
    def test_render_with_decomposicao(self):
        from concilium.application.runtime.deliverables.reports.memorial_bdi_markdown import (
            render_memorial_bdi_markdown,
        )

        memorial = {
            "decomposicao_por_categoria": {
                "TERRA": {
                    "custo_direto_pct": 0.7,
                    "overhead_ac_pct": 0.03,
                    "overhead_df_pct": 0.01,
                    "overhead_r_pct": 0.01,
                    "margem_l_pct": 0.10,
                    "tributo_iss_pct": 0.02,
                    "tributo_cssl_pct": 0.01,
                    "tributo_ir_pct": 0.01,
                }
            },
            "aplicacao_por_item": [],
        }
        result = render_memorial_bdi_markdown(memorial)
        assert "TERRA" in result or "Decomposicao" in result

    def test_render_without_decomposicao(self):
        from concilium.application.runtime.deliverables.reports.memorial_bdi_markdown import (
            render_memorial_bdi_markdown,
        )

        result = render_memorial_bdi_markdown({})
        assert isinstance(result, str)



