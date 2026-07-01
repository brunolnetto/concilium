"""Coverage batch 23 — resource_pool_validator, template_interpreter,
consolidation, engine_refs, campaign_store small gaps."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# resource_pool_validator.py line 69->57:
# elif classe == "concorrente_compartilhavel" is False → back to for loop
# ---------------------------------------------------------------------------


class TestRpvAccumulateDemandsUnknownClass:
    def test_unknown_class_skips_all_elif_branches(self):
        """Line 69->57: insumo classe='other' → none of the three elif match → continue."""
        from concilium.infrastructure.catalog.resource_pool_validator import (
            _rpv_accumulate_demands,
        )

        insumos = {
            "EQ-CUSTOM": {
                "classe_compartilhamento": {"classe": "not_a_known_class"},
            }
        }
        alocacoes = {"act-1": {"EQ-CUSTOM": 2.0}}
        atividades_ativas = ["act-1"]

        demand_a, demand_b, demand_c = _rpv_accumulate_demands(atividades_ativas, alocacoes, insumos)
        # Unknown class → none of A/B/C accumulated
        assert dict(demand_a) == {}
        assert dict(demand_b) == {}
        assert dict(demand_c) == {}


# ---------------------------------------------------------------------------
# template_interpreter.py line 82->85: linhas is not a list or is empty → skip
# template_interpreter.py line 87->90: template_linhas empty → return None
# ---------------------------------------------------------------------------


def _make_template_interpreter(spec: dict):
    """Write spec to a temp file and return TemplateInterpreter instance."""
    from concilium.infrastructure.adapters.template_interpreter import TemplateInterpreter

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(spec, f)
        tmp = Path(f.name)

    return TemplateInterpreter(template_path=tmp)


class TestTemplateInterpreterGetSectionLineRange:
    def test_returns_none_when_linhas_is_empty_list(self):
        """Line 82->85: 'linhas': [] → len == 0 → if False → check template_linhas."""
        ti = _make_template_interpreter({"abas": {}})
        # "linhas" key present but empty list → first if fails → falls to template_linhas check
        # "template_linhas" absent → returns None
        result = ti.get_section_line_range({"linhas": []})
        assert result is None

    def test_returns_none_when_linhas_is_string(self):
        """Line 82->85: 'linhas': 'not-a-list' → isinstance False → skip."""
        ti = _make_template_interpreter({"abas": {}})
        result = ti.get_section_line_range({"linhas": "not-a-list"})
        assert result is None

    def test_returns_none_when_template_linhas_is_empty(self):
        """Line 87->90: 'template_linhas': [] → len==0 → if False → return None."""
        ti = _make_template_interpreter({"abas": {}})
        result = ti.get_section_line_range({"template_linhas": []})
        assert result is None

    def test_returns_range_when_linhas_has_items(self):
        """Normal path: 'linhas': [3, 1, 2] → return (1, 3)."""
        ti = _make_template_interpreter({"abas": {}})
        result = ti.get_section_line_range({"linhas": [3, 1, 2]})
        assert result == (1, 3)

    def test_returns_range_when_template_linhas_has_items(self):
        """Normal path for template_linhas: return (min, max)."""
        ti = _make_template_interpreter({"abas": {}})
        result = ti.get_section_line_range({"template_linhas": [10, 20, 15]})
        assert result == (10, 20)


# ---------------------------------------------------------------------------
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
# campaign_store.py line 207->212: new_run with non-LocalBlobStorage skips mkdir
# ---------------------------------------------------------------------------


class TestNewRunWithMockStorage:
    def test_new_run_skips_mkdir_for_non_local_backend(self):
        """Line 207->212: MagicMock is not LocalBlobStorage → if False → returns run_name."""
        from concilium.infrastructure.storage.campaign_store import CampaignRunStore

        mock_storage = MagicMock()
        mock_storage.listar_blobs.return_value = []
        store = CampaignRunStore(storage=mock_storage, prefix="PROJ-01/campaigns")

        run_name = store.new_run()

        # Should return a run name string without touching the filesystem
        assert run_name.startswith("run-")
        # gravar_blob called for sentinel + current pointer (mkdir NOT called on storage)
        assert mock_storage.gravar_blob.call_count == 2
