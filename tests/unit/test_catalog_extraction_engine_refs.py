"""Tests for: backtracking_pe models, jwt_config, cpu_mapper."""

from __future__ import annotations

import json

import pytest

# ─── infrastructure/catalog/extraction/engine_refs.py ─────────────────────────


class TestEngineRefs:
    def test_safe_float_with_non_numeric_returns_zero(self):
        """Lines 20-23: _safe_float with non-numeric input returns 0.0."""
        from concilium.infrastructure.catalog.extraction.engine_refs import _safe_float

        assert _safe_float("not_a_number") == 0.0
        assert _safe_float(None) == 0.0

    def test_safe_float_with_valid_number(self):
        from concilium.infrastructure.catalog.extraction.engine_refs import _safe_float

        assert _safe_float("3.14") == pytest.approx(3.14)

    def test_check_project_dir_invalid_json_returns_best(self, tmp_path):
        """Lines 52-53: _check_project_dir with invalid JSON meta returns best."""

        from concilium.infrastructure.catalog.extraction.engine_refs import _check_project_dir

        d = tmp_path / "proj1"
        d.mkdir()
        (d / "meta.json").write_text("NOT JSON", encoding="utf-8")

        sentinel = ("2026-01-01", tmp_path / "other")
        result = _check_project_dir(d, "ANY", sentinel)
        assert result is sentinel

    def test_check_project_dir_older_candidate_returns_best(self, tmp_path):
        """Line 60: existing best is newer → returns best unchanged."""

        from concilium.infrastructure.catalog.extraction.engine_refs import _check_project_dir

        d = tmp_path / "proj_old"
        d.mkdir()
        (d / "meta.json").write_text(
            json.dumps({"nome": "Test Project", "criado_em": "2025-01-01"}),
            encoding="utf-8",
        )
        best = ("2026-06-01", tmp_path / "newer_proj")
        result = _check_project_dir(d, "TEST PROJECT", best)
        assert result is best





import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

# engine_refs.py line 114->112: cat is falsy → skip → back to for loop
# ---------------------------------------------------------------------------


class TestExtractEngineIterationReferencesNoCat:
    def test_indireto_with_no_categoria_is_skipped(self):
        """Line 114->112: cat = ind.get('categoria') is None → if cat: False → continue."""
        from concilium.infrastructure.catalog.extraction.engine_refs import (
            extract_engine_iteration_references,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            # Minimal canonical with one indireto that has no 'categoria'
            canonical = {
                "equipes_diretas": [],
                "planejamento": [],
                "indiretos": [{"valor": 100.0}],  # no 'categoria' key
                "resultado": {},
            }

            # Minimal project dir so _find_latest_project_by_name can match
            proj_dir = root / "projetos" / "PROJ-ENGINE"
            (proj_dir / "v1").mkdir(parents=True)
            meta = {"nome": "ENGINE-PROJ"}
            (proj_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
            (proj_dir / "v1" / "canonical.json").write_text(json.dumps(canonical), encoding="utf-8")

            # Benchmark report
            out_dir = root / "benchmarks" / "extracted_references"
            out_dir.mkdir(parents=True)
            report_path = root / "benchmark_engine.json"
            report_path.write_text(
                json.dumps({"slug": "ENGINE", "projeto": "ENGINE-PROJ"}),
                encoding="utf-8",
            )

            result = extract_engine_iteration_references(report_path=report_path, root=root, out_dir=out_dir)

        # indiretos stays as initialised (no cat was populated)
        assert result["slug"] == "ENGINE"
        # The indireto with no categoria was skipped → "indiretos" only has preset cats
        for cat in ("ADM", "TOP", "LAB", "QSMS", "MOB"):
            assert cat in result["indiretos"]
            assert result["indiretos"][cat] == {}


# ---------------------------------------------------------------------------

