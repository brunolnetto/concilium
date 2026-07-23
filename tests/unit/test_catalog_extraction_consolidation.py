"""Coverage batch 23 — resource_pool_validator, template_interpreter,
consolidation, engine_refs, campaign_store small gaps."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

# consolidation.py line 41->31: meta.nome != project_name → continue in for loop
# ---------------------------------------------------------------------------


class TestFindProjectDirNoMatch:
    def test_returns_none_when_meta_nome_does_not_match(self):
        """Line 41->31: meta.nome='OTHER' ≠ project_name → continue → loop ends → None."""
        from concilium.infrastructure.catalog.extraction.consolidation import (
            consolidate_reference,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Create benchmark referencia.json pointing to a project name
            bench_slug = "BENCH-TEST"
            bench_dir = root / "benchmarks" / "data" / bench_slug
            bench_dir.mkdir(parents=True)
            (bench_dir / "referencia.json").write_text(
                json.dumps({"projeto": "TARGET-PROJECT", "custo_total": 1_000_000}),
                encoding="utf-8",
            )
            # Create projetos dir with a directory whose meta.nome doesn't match
            proj_dir = root / "projetos" / "PROJ-A"
            proj_dir.mkdir(parents=True)
            (proj_dir / "meta.json").write_text(json.dumps({"nome": "DIFFERENT-PROJECT"}), encoding="utf-8")

            # _find_project_dir loops, nome != TARGET-PROJECT → continues → returns None
            # consolidate_reference returns ref unchanged (no enrichment)
            result = consolidate_reference(slug=bench_slug, root=root)

        # Returns the original referencia.json content (no _fonte key)
        assert result.get("projeto") == "TARGET-PROJECT"
        assert "_fonte" not in result


# ---------------------------------------------------------------------------





# ─── infrastructure/catalog/extraction/consolidation.py ───────────────────────


class TestConsolidation:
    def test_consolidate_reference_no_project_returns_ref(self, tmp_path):
        from concilium.infrastructure.catalog.extraction.consolidation import consolidate_reference

        bench_dir = tmp_path / "benchmarks" / "data" / "AGIS"
        bench_dir.mkdir(parents=True)
        (bench_dir / "referencia.json").write_text('{"slug": "AGIS", "projeto": "Proj Test"}')
        (tmp_path / "projetos").mkdir()
        result = consolidate_reference("AGIS", root=tmp_path)
        assert result["slug"] == "AGIS"

    def test_find_project_dir_not_found(self, tmp_path):
        from concilium.infrastructure.catalog.extraction.consolidation import _find_project_dir

        bench_dir = tmp_path / "benchmarks" / "data" / "AGIS"
        bench_dir.mkdir(parents=True)
        (bench_dir / "referencia.json").write_text('{"projeto": "Nonexistent"}')
        (tmp_path / "projetos").mkdir()
        result = _find_project_dir("AGIS", tmp_path)
        assert result is None

    def test_find_project_dir_no_project_name(self, tmp_path):
        from concilium.infrastructure.catalog.extraction.consolidation import _find_project_dir

        bench_dir = tmp_path / "benchmarks" / "data" / "AGIS"
        bench_dir.mkdir(parents=True)
        (bench_dir / "referencia.json").write_text("{}")
        result = _find_project_dir("AGIS", tmp_path)
        assert result is None



