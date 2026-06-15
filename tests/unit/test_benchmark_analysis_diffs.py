"""Tests for src/concilium/application/benchmarks/analysis/diffs.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from concilium.application.benchmarks.analysis.diffs import (
    _ce_compare_item,
    _compare_equipes,
    _find_benchmark_report,
    _gdfs_load_canonical,
    generate_diffs_for_slug,
)


# ---------------------------------------------------------------------------
# _ce_compare_item
# ---------------------------------------------------------------------------


class TestCeCompareItem:
    def test_equal_items_no_diffs(self):
        can = {"funcoes": ["a", "b"], "equipamentos": ["x"], "custo_total": 100.0}
        ref = {"funcoes": ["a", "b"], "equipamentos": ["x"], "custo_total": 100.0}
        result = _ce_compare_item("EQ-001", can, ref)
        assert result == []

    def test_funcoes_count_diff(self):
        can = {"funcoes": ["a", "b", "c"], "equipamentos": [], "custo_total": 0.0}
        ref = {"funcoes": ["a"], "equipamentos": [], "custo_total": 0.0}
        result = _ce_compare_item("EQ-002", can, ref)
        assert len(result) == 1
        diff = result[0]
        assert diff["campo"] == "funcoes_count"
        assert diff["canonical"] == 3
        assert diff["referencia"] == 1
        assert diff["delta"] == 2
        assert diff["item_id"] == "EQ-002"

    def test_equipamentos_count_diff(self):
        can = {"funcoes": [], "equipamentos": ["x", "y"], "custo_total": 0.0}
        ref = {"funcoes": [], "equipamentos": [], "custo_total": 0.0}
        result = _ce_compare_item("EQ-003", can, ref)
        assert len(result) == 1
        diff = result[0]
        assert diff["campo"] == "equipamentos_count"
        assert diff["canonical"] == 2
        assert diff["referencia"] == 0
        assert diff["delta"] == 2

    def test_custo_total_diff(self):
        can = {"funcoes": [], "equipamentos": [], "custo_total": 500.0}
        ref = {"funcoes": [], "equipamentos": [], "custo_total": 300.0}
        result = _ce_compare_item("EQ-004", can, ref)
        assert len(result) == 1
        diff = result[0]
        assert diff["campo"] == "custo_total"
        assert diff["canonical"] == 500.0
        assert diff["referencia"] == 300.0
        assert diff["delta"] == 200.0

    def test_custo_total_within_tolerance_no_diff(self):
        can = {"funcoes": [], "equipamentos": [], "custo_total": 100.0}
        ref = {"funcoes": [], "equipamentos": [], "custo_total": 100.005}
        result = _ce_compare_item("EQ-005", can, ref)
        assert result == []

    def test_ref_uses_custos_total_fallback(self):
        """ref_eq with custos.total key should be read from there."""
        can = {"funcoes": [], "equipamentos": [], "custo_total": 200.0}
        ref = {"funcoes": [], "equipamentos": [], "custos": {"total": 100.0}}
        result = _ce_compare_item("EQ-006", can, ref)
        assert len(result) == 1
        assert result[0]["campo"] == "custo_total"
        assert result[0]["referencia"] == 100.0

    def test_ref_custos_none_falls_back_to_custo_total(self):
        """ref_eq with custos=None should fall back to custo_total."""
        can = {"funcoes": [], "equipamentos": [], "custo_total": 50.0}
        ref = {"funcoes": [], "equipamentos": [], "custos": None, "custo_total": 50.0}
        result = _ce_compare_item("EQ-007", can, ref)
        assert result == []

    def test_multiple_diffs_at_once(self):
        can = {"funcoes": ["a", "b"], "equipamentos": ["x"], "custo_total": 999.0}
        ref = {"funcoes": [], "equipamentos": [], "custo_total": 0.0}
        result = _ce_compare_item("EQ-008", can, ref)
        campos = {d["campo"] for d in result}
        assert "funcoes_count" in campos
        assert "equipamentos_count" in campos
        assert "custo_total" in campos

    def test_missing_keys_default_to_empty(self):
        can = {}
        ref = {}
        result = _ce_compare_item("EQ-009", can, ref)
        assert result == []


# ---------------------------------------------------------------------------
# _compare_equipes
# ---------------------------------------------------------------------------


class TestCompareEquipes:
    def test_matching_items_no_diff(self):
        can = [{"item_id": "E1", "funcoes": ["a"], "equipamentos": [], "custo_total": 10.0}]
        ref = [{"item_id": "E1", "funcoes": ["a"], "equipamentos": [], "custo_total": 10.0}]
        result = _compare_equipes(can, ref)
        assert result == []

    def test_canonical_item_missing_from_ref_is_skipped(self):
        can = [{"item_id": "E1", "funcoes": ["a"], "equipamentos": [], "custo_total": 0.0}]
        ref = []  # no matching item
        result = _compare_equipes(can, ref)
        assert result == []

    def test_ref_item_not_in_canonical_ignored(self):
        can = []
        ref = [{"item_id": "E1", "funcoes": [], "equipamentos": [], "custo_total": 0.0}]
        result = _compare_equipes(can, ref)
        assert result == []

    def test_items_without_item_id_skipped(self):
        can = [{"funcoes": [], "equipamentos": [], "custo_total": 0.0}]  # no item_id
        ref = [{"funcoes": [], "equipamentos": [], "custo_total": 0.0}]
        result = _compare_equipes(can, ref)
        assert result == []

    def test_matching_item_with_diff(self):
        can = [{"item_id": "E1", "funcoes": ["a", "b"], "equipamentos": [], "custo_total": 0.0}]
        ref = [{"item_id": "E1", "funcoes": [], "equipamentos": [], "custo_total": 0.0}]
        result = _compare_equipes(can, ref)
        assert len(result) == 1
        assert result[0]["campo"] == "funcoes_count"

    def test_multiple_items_mixed(self):
        can = [
            {"item_id": "E1", "funcoes": ["a"], "equipamentos": [], "custo_total": 0.0},
            {"item_id": "E2", "funcoes": [], "equipamentos": ["x", "y"], "custo_total": 0.0},
        ]
        ref = [
            {"item_id": "E1", "funcoes": ["a"], "equipamentos": [], "custo_total": 0.0},
            {"item_id": "E2", "funcoes": [], "equipamentos": [], "custo_total": 0.0},
        ]
        result = _compare_equipes(can, ref)
        assert len(result) == 1
        assert result[0]["item_id"] == "E2"


# ---------------------------------------------------------------------------
# _find_benchmark_report
# ---------------------------------------------------------------------------


class TestFindBenchmarkReport:
    def test_returns_organized_path_when_exists(self, tmp_path):
        slug = "MYSLUG"
        organized = tmp_path / "benchmarks" / "data" / slug.upper() / "artifacts" / "outputs"
        organized.mkdir(parents=True)
        report = organized / "benchmark_report.json"
        report.write_text("{}")
        result = _find_benchmark_report(slug, tmp_path)
        assert result == report

    def test_falls_back_to_root_benchmark_json(self, tmp_path):
        slug = "myslug"
        fallback = tmp_path / f"benchmark_{slug.lower()}.json"
        fallback.write_text("{}")
        result = _find_benchmark_report(slug, tmp_path)
        assert result == fallback

    def test_returns_none_when_neither_exists(self, tmp_path):
        result = _find_benchmark_report("noslug", tmp_path)
        assert result is None

    def test_organized_path_takes_priority_over_fallback(self, tmp_path):
        slug = "prio"
        organized = tmp_path / "benchmarks" / "data" / slug.upper() / "artifacts" / "outputs"
        organized.mkdir(parents=True)
        report = organized / "benchmark_report.json"
        report.write_text('{"source": "organized"}')
        fallback = tmp_path / f"benchmark_{slug.lower()}.json"
        fallback.write_text('{"source": "fallback"}')
        result = _find_benchmark_report(slug, tmp_path)
        assert result == report

    def test_slug_case_insensitive_for_organized(self, tmp_path):
        slug = "testslug"
        organized = tmp_path / "benchmarks" / "data" / slug.upper() / "artifacts" / "outputs"
        organized.mkdir(parents=True)
        report = organized / "benchmark_report.json"
        report.write_text("{}")
        result = _find_benchmark_report(slug.lower(), tmp_path)
        assert result == report


# ---------------------------------------------------------------------------
# _gdfs_load_canonical
# ---------------------------------------------------------------------------


class TestGdfsLoadCanonical:
    def _make_projeto(self, projetos_dir: Path, folder: str, nome: str, canonical: dict | None = None) -> Path:
        d = projetos_dir / folder
        d.mkdir(parents=True, exist_ok=True)
        meta = d / "meta.json"
        meta.write_text(json.dumps({"nome": nome}))
        if canonical is not None:
            v1 = d / "v1"
            v1.mkdir(exist_ok=True)
            (v1 / "canonical.json").write_text(json.dumps(canonical))
        return d

    def test_returns_canonical_when_nome_matches(self, tmp_path):
        projetos = tmp_path / "projetos"
        projetos.mkdir()
        data = {"equipes_diretas": [{"item_id": "E1"}]}
        self._make_projeto(projetos, "proj-a", "Projeto A", canonical=data)
        result = _gdfs_load_canonical("Projeto A", tmp_path)
        assert result == data

    def test_returns_empty_when_nome_does_not_match(self, tmp_path):
        projetos = tmp_path / "projetos"
        projetos.mkdir()
        self._make_projeto(projetos, "proj-a", "Projeto A", canonical={"equipes_diretas": []})
        result = _gdfs_load_canonical("Outro Projeto", tmp_path)
        assert result == {}

    def test_returns_empty_when_canonical_absent(self, tmp_path):
        projetos = tmp_path / "projetos"
        projetos.mkdir()
        # create projeto without canonical
        self._make_projeto(projetos, "proj-b", "Projeto B", canonical=None)
        result = _gdfs_load_canonical("Projeto B", tmp_path)
        assert result == {}

    def test_skips_non_directory_entries(self, tmp_path):
        projetos = tmp_path / "projetos"
        projetos.mkdir()
        # create a file (not a dir) inside projetos
        (projetos / "somefile.json").write_text("{}")
        data = {"equipes_diretas": []}
        self._make_projeto(projetos, "proj-c", "Projeto C", canonical=data)
        result = _gdfs_load_canonical("Projeto C", tmp_path)
        assert result == data

    def test_skips_dir_without_meta_json(self, tmp_path):
        projetos = tmp_path / "projetos"
        projetos.mkdir()
        # directory with no meta.json
        (projetos / "no-meta").mkdir()
        data = {"equipes_diretas": []}
        self._make_projeto(projetos, "proj-d", "Projeto D", canonical=data)
        result = _gdfs_load_canonical("Projeto D", tmp_path)
        assert result == data

    def test_handles_malformed_meta_json_gracefully(self, tmp_path):
        projetos = tmp_path / "projetos"
        projetos.mkdir()
        bad_dir = projetos / "bad-meta"
        bad_dir.mkdir()
        (bad_dir / "meta.json").write_text("NOT VALID JSON {{{")
        data = {"equipes_diretas": []}
        self._make_projeto(projetos, "proj-e", "Projeto E", canonical=data)
        result = _gdfs_load_canonical("Projeto E", tmp_path)
        assert result == data

    def test_returns_empty_when_projetos_empty(self, tmp_path):
        projetos = tmp_path / "projetos"
        projetos.mkdir()
        result = _gdfs_load_canonical("Any Project", tmp_path)
        assert result == {}


# ---------------------------------------------------------------------------
# generate_diffs_for_slug
# ---------------------------------------------------------------------------


def _setup_full_fixture(root: Path, slug: str, bench_data: dict, extracted_data: dict, canonical_data: dict | None = None):
    """Helper to wire all necessary files for generate_diffs_for_slug."""
    # extracted_references
    ext_dir = root / "benchmarks" / "extracted_references"
    ext_dir.mkdir(parents=True)
    ext_file = ext_dir / f"iteracao_referencias_{slug.lower()}.json"
    ext_file.write_text(json.dumps(extracted_data))

    # benchmark_report (organized path)
    report_dir = root / "benchmarks" / "data" / slug.upper() / "artifacts" / "outputs"
    report_dir.mkdir(parents=True)
    report_file = report_dir / "benchmark_report.json"
    report_file.write_text(json.dumps(bench_data))

    # canonical
    if canonical_data is not None:
        projetos = root / "projetos"
        projetos.mkdir(parents=True, exist_ok=True)
        proj_dir = projetos / "proj-test"
        proj_dir.mkdir(exist_ok=True)
        projeto_nome = bench_data.get("projeto", slug)
        (proj_dir / "meta.json").write_text(json.dumps({"nome": projeto_nome}))
        v1 = proj_dir / "v1"
        v1.mkdir(exist_ok=True)
        (v1 / "canonical.json").write_text(json.dumps(canonical_data))


class TestGenerateDiffsForSlug:
    def test_returns_none_when_extracted_references_missing(self, tmp_path):
        result = generate_diffs_for_slug("MISSING", root=tmp_path)
        assert result is None

    def test_returns_none_when_benchmark_report_missing(self, tmp_path):
        slug = "noreport"
        ext_dir = tmp_path / "benchmarks" / "extracted_references"
        ext_dir.mkdir(parents=True)
        (ext_dir / f"iteracao_referencias_{slug}.json").write_text(json.dumps({"equipes": {"equipes": []}}))
        # no benchmark report file
        result = generate_diffs_for_slug(slug, root=tmp_path)
        assert result is None

    def test_happy_path_no_diffs(self, tmp_path):
        slug = "happy"
        canonical_data = {
            "equipes_diretas": [
                {"item_id": "E1", "funcoes": ["a"], "equipamentos": [], "custo_total": 100.0}
            ]
        }
        bench_data = {"projeto": "Projeto Happy"}
        extracted_data = {
            "equipes": {
                "equipes": [
                    {"item_id": "E1", "funcoes": ["a"], "equipamentos": [], "custo_total": 100.0}
                ]
            }
        }
        _setup_full_fixture(tmp_path, slug, bench_data, extracted_data, canonical_data)
        result = generate_diffs_for_slug(slug, root=tmp_path)
        assert result is not None
        assert result["slug"] == slug
        assert result["equipes"]["total"] == 0
        assert result["equipes"]["discrepancias"] == []

    def test_happy_path_with_diffs(self, tmp_path):
        slug = "withdiffs"
        canonical_data = {
            "equipes_diretas": [
                {"item_id": "E1", "funcoes": ["a", "b", "c"], "equipamentos": [], "custo_total": 999.0}
            ]
        }
        bench_data = {"projeto": "Projeto WithDiffs"}
        extracted_data = {
            "equipes": {
                "equipes": [
                    {"item_id": "E1", "funcoes": [], "equipamentos": [], "custo_total": 0.0}
                ]
            }
        }
        _setup_full_fixture(tmp_path, slug, bench_data, extracted_data, canonical_data)
        result = generate_diffs_for_slug(slug, root=tmp_path)
        assert result is not None
        assert result["slug"] == slug
        assert result["equipes"]["total"] > 0
        campos = {d["campo"] for d in result["equipes"]["discrepancias"]}
        assert "funcoes_count" in campos
        assert "custo_total" in campos

    def test_happy_path_bench_uses_slug_as_projeto_when_missing(self, tmp_path):
        slug = "fallbkproj"
        canonical_data = {"equipes_diretas": []}
        bench_data = {}  # no "projeto" key
        extracted_data = {"equipes": {"equipes": []}}
        _setup_full_fixture(tmp_path, slug, bench_data, extracted_data, canonical_data=None)
        # We need projetos dir even if empty
        (tmp_path / "projetos").mkdir(parents=True, exist_ok=True)
        result = generate_diffs_for_slug(slug, root=tmp_path)
        assert result is not None
        assert result["slug"] == slug

    def test_canonical_empty_gives_zero_diffs(self, tmp_path):
        slug = "emptycan"
        bench_data = {"projeto": "Proj Empty"}
        extracted_data = {
            "equipes": {
                "equipes": [
                    {"item_id": "E1", "funcoes": ["a"], "equipamentos": [], "custo_total": 50.0}
                ]
            }
        }
        _setup_full_fixture(tmp_path, slug, bench_data, extracted_data, canonical_data=None)
        (tmp_path / "projetos").mkdir(parents=True, exist_ok=True)
        result = generate_diffs_for_slug(slug, root=tmp_path)
        assert result is not None
        assert result["equipes"]["total"] == 0

    def test_result_structure_keys(self, tmp_path):
        slug = "structcheck"
        canonical_data = {"equipes_diretas": []}
        bench_data = {"projeto": "Proj Struct"}
        extracted_data = {"equipes": {"equipes": []}}
        _setup_full_fixture(tmp_path, slug, bench_data, extracted_data, canonical_data)
        result = generate_diffs_for_slug(slug, root=tmp_path)
        assert "slug" in result
        assert "equipes" in result
        assert "total" in result["equipes"]
        assert "discrepancias" in result["equipes"]
