"""Unit tests for algorithm_comparison.py (ADR-075).

Covers:
- AlgorithmComparisonEntry dataclass construction and defaults
- AlgorithmComparisonReport.best_by_quality / best_by_makespan selection
- AlgorithmComparisonReport.summary_table formatting
- AlgorithmComparisonReport.to_dict serialisation
- AlgorithmComparisonRunner.compare() with mocked Runtime / ProjectStore /
  BenchmarkInferenceService
- AlgorithmComparisonRunner._extract_entry() in isolation
- DEFAULT_COMPARISON_ALGORITHMS value
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from concilium.application.benchmarks.algorithm_comparison import (
    DEFAULT_COMPARISON_ALGORITHMS,
    AlgorithmComparisonEntry,
    AlgorithmComparisonReport,
    AlgorithmComparisonRunner,
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_entry(
    algorithm: str,
    *,
    makespan: int | None = 10,
    quality: float | None = 0.8,
    feasible: bool = True,
    relaxed: bool = False,
    cost: float | None = None,
    mob: float | None = None,
    error: str | None = None,
    version: str | None = "v1",
) -> AlgorithmComparisonEntry:
    return AlgorithmComparisonEntry(
        algorithm=algorithm,
        version=version,
        makespan_weeks=makespan,
        quality_score=quality,
        is_feasible=feasible,
        was_relaxed=relaxed,
        cost_total=cost,
        mob_cost=mob,
        error=error,
    )


def _make_report(entries: list[AlgorithmComparisonEntry]) -> AlgorithmComparisonReport:
    return AlgorithmComparisonReport(
        project_name="TestProject",
        algorithms_tried=[e.algorithm for e in entries],
        entries=entries,
    )


# ─────────────────────────────────────────────────────────────────────────────
# AlgorithmComparisonEntry — dataclass defaults and construction
# ─────────────────────────────────────────────────────────────────────────────


class TestAlgorithmComparisonEntry:
    def test_minimal_construction(self):
        e = AlgorithmComparisonEntry(algorithm="CP-SAT")
        assert e.algorithm == "CP-SAT"
        assert e.version is None
        assert e.makespan_weeks is None
        assert e.quality_score is None
        assert e.is_feasible is False
        assert e.was_relaxed is False
        assert e.cost_total is None
        assert e.mob_cost is None
        assert e.error is None

    def test_full_construction(self):
        e = AlgorithmComparisonEntry(
            algorithm="LNS",
            version="v2",
            makespan_weeks=12,
            quality_score=0.95,
            is_feasible=True,
            was_relaxed=True,
            cost_total=100_000.0,
            mob_cost=5_000.0,
            error=None,
        )
        assert e.algorithm == "LNS"
        assert e.version == "v2"
        assert e.makespan_weeks == 12
        assert e.quality_score == 0.95
        assert e.is_feasible is True
        assert e.was_relaxed is True
        assert e.cost_total == 100_000.0
        assert e.mob_cost == 5_000.0
        assert e.error is None

    def test_error_entry(self):
        e = AlgorithmComparisonEntry(algorithm="MINSLK", error="RuntimeError: boom")
        assert e.error == "RuntimeError: boom"
        assert e.is_feasible is False


# ─────────────────────────────────────────────────────────────────────────────
# DEFAULT_COMPARISON_ALGORITHMS
# ─────────────────────────────────────────────────────────────────────────────


class TestDefaultAlgorithms:
    def test_default_list(self):
        assert DEFAULT_COMPARISON_ALGORITHMS == ["CP-SAT", "LNS", "MINSLK"]

    def test_is_list_of_strings(self):
        assert all(isinstance(a, str) for a in DEFAULT_COMPARISON_ALGORITHMS)


# ─────────────────────────────────────────────────────────────────────────────
# AlgorithmComparisonReport.best_by_quality
# ─────────────────────────────────────────────────────────────────────────────


class TestBestByQuality:
    def test_returns_highest_quality(self):
        e1 = _make_entry("CP-SAT", quality=0.7, feasible=True)
        e2 = _make_entry("LNS", quality=0.9, feasible=True)
        e3 = _make_entry("MINSLK", quality=0.6, feasible=True)
        report = _make_report([e1, e2, e3])
        assert report.best_by_quality is e2

    def test_skips_infeasible(self):
        e1 = _make_entry("CP-SAT", quality=0.99, feasible=False)
        e2 = _make_entry("LNS", quality=0.7, feasible=True)
        report = _make_report([e1, e2])
        assert report.best_by_quality is e2

    def test_skips_none_quality(self):
        e1 = _make_entry("CP-SAT", quality=None, feasible=True)
        e2 = _make_entry("LNS", quality=0.5, feasible=True)
        report = _make_report([e1, e2])
        assert report.best_by_quality is e2

    def test_returns_none_when_no_feasible(self):
        e1 = _make_entry("CP-SAT", quality=0.9, feasible=False)
        report = _make_report([e1])
        assert report.best_by_quality is None

    def test_returns_none_for_empty_entries(self):
        report = AlgorithmComparisonReport(project_name="P", algorithms_tried=[])
        assert report.best_by_quality is None

    def test_single_feasible_entry(self):
        e = _make_entry("CP-SAT", quality=0.55, feasible=True)
        report = _make_report([e])
        assert report.best_by_quality is e


# ─────────────────────────────────────────────────────────────────────────────
# AlgorithmComparisonReport.best_by_makespan
# ─────────────────────────────────────────────────────────────────────────────


class TestBestByMakespan:
    def test_returns_shortest_makespan(self):
        e1 = _make_entry("CP-SAT", makespan=20, feasible=True)
        e2 = _make_entry("LNS", makespan=8, feasible=True)
        e3 = _make_entry("MINSLK", makespan=15, feasible=True)
        report = _make_report([e1, e2, e3])
        assert report.best_by_makespan is e2

    def test_skips_infeasible(self):
        e1 = _make_entry("CP-SAT", makespan=3, feasible=False)
        e2 = _make_entry("LNS", makespan=12, feasible=True)
        report = _make_report([e1, e2])
        assert report.best_by_makespan is e2

    def test_skips_none_makespan(self):
        e1 = _make_entry("CP-SAT", makespan=None, feasible=True)
        e2 = _make_entry("LNS", makespan=10, feasible=True)
        report = _make_report([e1, e2])
        assert report.best_by_makespan is e2

    def test_returns_none_when_no_feasible(self):
        e1 = _make_entry("CP-SAT", makespan=5, feasible=False)
        report = _make_report([e1])
        assert report.best_by_makespan is None

    def test_returns_none_for_empty_entries(self):
        report = AlgorithmComparisonReport(project_name="P", algorithms_tried=[])
        assert report.best_by_makespan is None


# ─────────────────────────────────────────────────────────────────────────────
# AlgorithmComparisonReport.summary_table
# ─────────────────────────────────────────────────────────────────────────────


class TestSummaryTable:
    def test_header_present(self):
        report = _make_report([_make_entry("CP-SAT")])
        table = report.summary_table()
        assert "Algorithm" in table
        assert "Makespan" in table
        assert "Quality" in table

    def test_separator_present(self):
        report = _make_report([_make_entry("CP-SAT")])
        table = report.summary_table()
        assert "---" in table

    def test_project_name_footer(self):
        report = _make_report([_make_entry("CP-SAT")])
        table = report.summary_table()
        assert "TestProject" in table

    def test_error_row_shows_error(self):
        e = _make_entry("MINSLK", error="timeout after 30s")
        report = _make_report([e])
        table = report.summary_table()
        assert "ERROR:" in table
        assert "timeout after 30s" in table
        # error rows use em-dash placeholders
        assert "—" in table

    def test_error_truncated_at_40_chars(self):
        long_error = "X" * 80
        e = _make_entry("MINSLK", error=long_error)
        report = _make_report([e])
        table = report.summary_table()
        # Only 40 chars of error shown
        assert "X" * 40 in table
        assert "X" * 41 not in table

    def test_best_marker_shown_for_best(self):
        e1 = _make_entry("CP-SAT", quality=0.5, feasible=True)
        e2 = _make_entry("LNS", quality=0.9, feasible=True)
        report = _make_report([e1, e2])
        table = report.summary_table()
        assert "◀ best" in table

    def test_best_marker_only_on_best_entry(self):
        e1 = _make_entry("CP-SAT", quality=0.5, feasible=True)
        e2 = _make_entry("LNS", quality=0.9, feasible=True)
        report = _make_report([e1, e2])
        table = report.summary_table()
        lines = table.split("\n")
        best_lines = [ln for ln in lines if "◀ best" in ln]
        assert len(best_lines) == 1
        assert "LNS" in best_lines[0]

    def test_relaxed_flag_shown(self):
        e = _make_entry("LNS", relaxed=True)
        report = _make_report([e])
        table = report.summary_table()
        assert "relaxed" in table

    def test_makespan_formatted_with_w(self):
        e = _make_entry("CP-SAT", makespan=14)
        report = _make_report([e])
        table = report.summary_table()
        assert "14w" in table

    def test_none_makespan_shows_dash(self):
        e = _make_entry("CP-SAT", makespan=None)
        report = _make_report([e])
        table = report.summary_table()
        assert "—" in table

    def test_quality_formatted_to_4dp(self):
        e = _make_entry("CP-SAT", quality=0.12345)
        report = _make_report([e])
        table = report.summary_table()
        # Python :.4f rounds 0.12345 → 0.1235
        assert "0.1235" in table

    def test_none_quality_shows_dash(self):
        e = _make_entry("CP-SAT", quality=None)
        report = _make_report([e])
        table = report.summary_table()
        assert "—" in table

    def test_cost_formatted_with_currency(self):
        e = _make_entry("CP-SAT", cost=1_000_000.0)
        report = _make_report([e])
        table = report.summary_table()
        assert "R$" in table

    def test_none_cost_shows_dash(self):
        e = _make_entry("CP-SAT", cost=None)
        report = _make_report([e])
        table = report.summary_table()
        assert "—" in table

    def test_mob_formatted_with_currency(self):
        e = _make_entry("LNS", mob=50_000.0)
        report = _make_report([e])
        table = report.summary_table()
        assert "R$" in table

    def test_none_mob_shows_dash(self):
        e = _make_entry("LNS", mob=None)
        report = _make_report([e])
        table = report.summary_table()
        assert "—" in table

    def test_ok_status_for_normal_entry(self):
        e = _make_entry("CP-SAT")
        report = _make_report([e])
        table = report.summary_table()
        assert "OK" in table

    def test_multiple_entries_all_appear(self):
        entries = [
            _make_entry("CP-SAT", quality=0.6),
            _make_entry("LNS", quality=0.8),
            _make_entry("MINSLK", quality=0.7),
        ]
        report = _make_report(entries)
        table = report.summary_table()
        assert "CP-SAT" in table
        assert "LNS" in table
        assert "MINSLK" in table

    def test_returns_string(self):
        report = _make_report([_make_entry("CP-SAT")])
        assert isinstance(report.summary_table(), str)


# ─────────────────────────────────────────────────────────────────────────────
# AlgorithmComparisonReport.to_dict
# ─────────────────────────────────────────────────────────────────────────────


class TestToDict:
    def test_project_name_in_dict(self):
        report = _make_report([_make_entry("CP-SAT")])
        d = report.to_dict()
        assert d["project_name"] == "TestProject"

    def test_algorithms_tried_in_dict(self):
        entries = [_make_entry("CP-SAT"), _make_entry("LNS")]
        report = _make_report(entries)
        d = report.to_dict()
        assert d["algorithms_tried"] == ["CP-SAT", "LNS"]

    def test_best_by_quality_key(self):
        e1 = _make_entry("CP-SAT", quality=0.5)
        e2 = _make_entry("LNS", quality=0.9)
        report = _make_report([e1, e2])
        d = report.to_dict()
        assert d["best_by_quality"] == "LNS"

    def test_best_by_makespan_key(self):
        e1 = _make_entry("CP-SAT", makespan=20)
        e2 = _make_entry("LNS", makespan=8)
        report = _make_report([e1, e2])
        d = report.to_dict()
        assert d["best_by_makespan"] == "LNS"

    def test_best_by_quality_none_when_no_feasible(self):
        e = _make_entry("CP-SAT", feasible=False)
        report = _make_report([e])
        d = report.to_dict()
        assert d["best_by_quality"] is None

    def test_best_by_makespan_none_when_no_feasible(self):
        e = _make_entry("CP-SAT", feasible=False)
        report = _make_report([e])
        d = report.to_dict()
        assert d["best_by_makespan"] is None

    def test_entries_serialised(self):
        e = _make_entry("CP-SAT", makespan=12, quality=0.75, cost=50_000.0, mob=2_000.0)
        report = _make_report([e])
        d = report.to_dict()
        assert len(d["entries"]) == 1
        entry_d = d["entries"][0]
        assert entry_d["algorithm"] == "CP-SAT"
        assert entry_d["makespan_weeks"] == 12
        assert entry_d["quality_score"] == 0.75
        assert entry_d["cost_total"] == 50_000.0
        assert entry_d["mob_cost"] == 2_000.0
        assert entry_d["is_feasible"] is True
        assert entry_d["was_relaxed"] is False

    def test_error_entry_serialised(self):
        e = _make_entry("MINSLK", error="timeout", feasible=False)
        report = _make_report([e])
        d = report.to_dict()
        assert d["entries"][0]["error"] == "timeout"

    def test_json_serialisable(self):
        e = _make_entry("LNS", cost=99_999.99, mob=1_234.0)
        report = _make_report([e])
        # Should not raise
        json_str = json.dumps(report.to_dict())
        loaded = json.loads(json_str)
        assert loaded["project_name"] == "TestProject"

    def test_empty_entries(self):
        report = AlgorithmComparisonReport(project_name="P", algorithms_tried=["CP-SAT"])
        d = report.to_dict()
        assert d["entries"] == []
        assert d["best_by_quality"] is None
        assert d["best_by_makespan"] is None


# ─────────────────────────────────────────────────────────────────────────────
# AlgorithmComparisonRunner._extract_entry — in isolation
# ─────────────────────────────────────────────────────────────────────────────


class TestExtractEntry:
    """Test _extract_entry() as a static method with SimpleNamespace objects."""

    def test_none_canonical_returns_error(self):
        entry = AlgorithmComparisonRunner._extract_entry("CP-SAT", "v1", None)
        assert entry.algorithm == "CP-SAT"
        assert entry.version == "v1"
        assert entry.error == "canonical not found"

    def test_canonical_with_no_attributes(self):
        canonical = SimpleNamespace()
        entry = AlgorithmComparisonRunner._extract_entry("LNS", "v1", canonical)
        assert entry.makespan_weeks is None
        assert entry.quality_score is None
        assert entry.is_feasible is False
        assert entry.was_relaxed is False
        assert entry.cost_total is None
        assert entry.mob_cost is None
        assert entry.error is None

    def test_extracts_scheduling_metrics(self):
        cron = SimpleNamespace(makespan_weeks=15, quality_score=0.88, is_feasible=True, was_relaxed=False)
        canonical = SimpleNamespace(cronograma=cron)
        entry = AlgorithmComparisonRunner._extract_entry("CP-SAT", "v1", canonical)
        assert entry.makespan_weeks == 15
        assert entry.quality_score == 0.88
        assert entry.is_feasible is True
        assert entry.was_relaxed is False

    def test_extracts_relaxed_flag(self):
        cron = SimpleNamespace(makespan_weeks=10, quality_score=0.5, is_feasible=True, was_relaxed=True)
        canonical = SimpleNamespace(cronograma=cron)
        entry = AlgorithmComparisonRunner._extract_entry("LNS", "v2", canonical)
        assert entry.was_relaxed is True

    def test_cronograma_none_skips_scheduling(self):
        canonical = SimpleNamespace(cronograma=None)
        entry = AlgorithmComparisonRunner._extract_entry("MINSLK", "v1", canonical)
        assert entry.makespan_weeks is None
        assert entry.quality_score is None

    def test_extracts_cost_total(self):
        custo = SimpleNamespace(total=250_000.0)
        resultado = SimpleNamespace(custo=custo)
        canonical = SimpleNamespace(resultado=resultado)
        entry = AlgorithmComparisonRunner._extract_entry("CP-SAT", "v1", canonical)
        assert entry.cost_total == 250_000.0

    def test_cost_total_as_integer_gets_converted_to_float(self):
        custo = SimpleNamespace(total=100000)
        resultado = SimpleNamespace(custo=custo)
        canonical = SimpleNamespace(resultado=resultado)
        entry = AlgorithmComparisonRunner._extract_entry("CP-SAT", "v1", canonical)
        assert isinstance(entry.cost_total, float)
        assert entry.cost_total == 100_000.0

    def test_resultado_none_skips_cost(self):
        canonical = SimpleNamespace(resultado=None)
        entry = AlgorithmComparisonRunner._extract_entry("LNS", "v1", canonical)
        assert entry.cost_total is None

    def test_custo_none_skips_cost(self):
        resultado = SimpleNamespace(custo=None)
        canonical = SimpleNamespace(resultado=resultado)
        entry = AlgorithmComparisonRunner._extract_entry("LNS", "v1", canonical)
        assert entry.cost_total is None

    def test_custo_total_none_stays_none(self):
        custo = SimpleNamespace(total=None)
        resultado = SimpleNamespace(custo=custo)
        canonical = SimpleNamespace(resultado=resultado)
        entry = AlgorithmComparisonRunner._extract_entry("CP-SAT", "v1", canonical)
        assert entry.cost_total is None

    def test_extracts_mob_cost_from_contratos(self):
        c1 = SimpleNamespace(custo_mob_desmob_contrato=1_000.0)
        c2 = SimpleNamespace(custo_mob_desmob_contrato=2_500.0)
        canonical = SimpleNamespace(contratos_recurso=[c1, c2])
        entry = AlgorithmComparisonRunner._extract_entry("CP-SAT", "v1", canonical)
        assert entry.mob_cost == 3_500.0

    def test_mob_cost_zero_stays_none(self):
        c1 = SimpleNamespace(custo_mob_desmob_contrato=0.0)
        canonical = SimpleNamespace(contratos_recurso=[c1])
        entry = AlgorithmComparisonRunner._extract_entry("CP-SAT", "v1", canonical)
        assert entry.mob_cost is None

    def test_contratos_empty_list(self):
        canonical = SimpleNamespace(contratos_recurso=[])
        entry = AlgorithmComparisonRunner._extract_entry("CP-SAT", "v1", canonical)
        assert entry.mob_cost is None

    def test_contratos_none(self):
        canonical = SimpleNamespace(contratos_recurso=None)
        entry = AlgorithmComparisonRunner._extract_entry("CP-SAT", "v1", canonical)
        assert entry.mob_cost is None

    def test_full_canonical(self):
        cron = SimpleNamespace(makespan_weeks=12, quality_score=0.9, is_feasible=True, was_relaxed=False)
        custo = SimpleNamespace(total=500_000.0)
        resultado = SimpleNamespace(custo=custo)
        c1 = SimpleNamespace(custo_mob_desmob_contrato=3_000.0)
        canonical = SimpleNamespace(cronograma=cron, resultado=resultado, contratos_recurso=[c1])
        entry = AlgorithmComparisonRunner._extract_entry("CP-SAT", "v3", canonical)
        assert entry.makespan_weeks == 12
        assert entry.quality_score == 0.9
        assert entry.is_feasible is True
        assert entry.cost_total == 500_000.0
        assert entry.mob_cost == 3_000.0
        assert entry.error is None


# ─────────────────────────────────────────────────────────────────────────────
# AlgorithmComparisonRunner.__init__
# ─────────────────────────────────────────────────────────────────────────────


class TestAlgorithmComparisonRunnerInit:
    def test_stores_paths(self):
        runner = AlgorithmComparisonRunner(
            config_root=Path("/tmp/cfg"),
            projects_root=Path("/tmp/projects"),
        )
        assert runner.config_root == Path("/tmp/cfg")
        assert runner.projects_root == Path("/tmp/projects")


# ─────────────────────────────────────────────────────────────────────────────
# AlgorithmComparisonRunner.compare() — with mocked Runtime/ProjectStore/Service
# ─────────────────────────────────────────────────────────────────────────────


def _make_spec(name: str = "TestProject") -> SimpleNamespace:
    return SimpleNamespace(
        nome=name,
        contexto_id="CTX-001",
        referencia_path=None,
        inputs_escopo={"area": 100},
        inputs_01A=None,
        inputs_cronograma=None,
        inputs_indiretos=None,
        extra_inputs={},
    )


def _make_canonical() -> SimpleNamespace:
    cron = SimpleNamespace(makespan_weeks=10, quality_score=0.85, is_feasible=True, was_relaxed=False)
    custo = SimpleNamespace(total=200_000.0)
    resultado = SimpleNamespace(custo=custo)
    c1 = SimpleNamespace(custo_mob_desmob_contrato=5_000.0)
    return SimpleNamespace(cronograma=cron, resultado=resultado, contratos_recurso=[c1])


class TestRunnerCompare:
    """Drive compare() with all external dependencies mocked."""

    def _build_runner(self):
        return AlgorithmComparisonRunner(
            config_root=Path("/tmp/cfg"),
            projects_root=Path("/tmp/projects"),
        )

    def _patch_all(self):
        """Return a context-manager dict that patches Runtime, ProjectStore, and inference."""
        patches = {}

        # Mock Runtime
        mock_runtime_cls = MagicMock()
        mock_runtime = MagicMock()
        mock_runtime_cls.return_value = mock_runtime
        patches["runtime_cls"] = patch("concilium.application.runtime.Runtime", mock_runtime_cls)

        # Mock ProjectStore
        mock_store_cls = MagicMock()
        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store
        mock_store_cls.init.return_value = mock_store
        mock_store.new_version.return_value = "v1"
        mock_store.load_canonical.return_value = _make_canonical()
        patches["store_cls"] = patch("concilium.infrastructure.storage.project.ProjectStore", mock_store_cls)

        return patches, mock_runtime, mock_store, mock_runtime_cls, mock_store_cls

    def test_compare_returns_report_with_entries(self):
        runner = self._build_runner()
        spec = _make_spec()

        with (
            patch.object(runner, "_find_or_create") as mock_foc,
            patch.object(runner, "_load_referencia", return_value=None),
            patch.object(runner, "_derive_inference_pack", return_value={}),
            patch.object(runner, "_prepare_inputs", return_value={}),
            patch("concilium.application.runtime.Runtime") as MockRuntime,
        ):
            mock_store = MagicMock()
            mock_store.new_version.side_effect = ["v1", "v2", "v3"]
            mock_store.load_canonical.return_value = _make_canonical()
            mock_foc.return_value = mock_store

            MockRuntime.return_value = MagicMock()

            report = runner.compare(spec)

        assert report.project_name == "TestProject"
        # Default = 3 algorithms
        assert len(report.entries) == 3
        assert report.algorithms_tried == DEFAULT_COMPARISON_ALGORITHMS

    def test_compare_uses_provided_algorithms(self):
        runner = self._build_runner()
        spec = _make_spec()

        with (
            patch.object(runner, "_find_or_create") as mock_foc,
            patch.object(runner, "_load_referencia", return_value=None),
            patch.object(runner, "_derive_inference_pack", return_value={}),
            patch.object(runner, "_prepare_inputs", return_value={}),
            patch("concilium.application.runtime.Runtime") as MockRuntime,
        ):
            mock_store = MagicMock()
            mock_store.new_version.side_effect = ["v1", "v2"]
            mock_store.load_canonical.return_value = _make_canonical()
            mock_foc.return_value = mock_store
            MockRuntime.return_value = MagicMock()

            report = runner.compare(spec, algorithms=["CP-SAT", "LNS"])

        assert report.algorithms_tried == ["CP-SAT", "LNS"]
        assert len(report.entries) == 2

    def test_algorithm_injected_into_cron_inputs(self):
        runner = self._build_runner()
        spec = _make_spec()
        captured_algorithms = []

        def fake_run_pipeline(store, inputs):
            # Capture the algorithm value at the moment of the call
            cron = inputs.get("04-cronograma", {})
            captured_algorithms.append(cron.get("algorithm"))

        # _prepare_inputs must return a NEW dict on each call so the loop
        # doesn't share mutable state between iterations
        def fresh_inputs(*args, **kwargs):
            return {}

        with (
            patch.object(runner, "_find_or_create") as mock_foc,
            patch.object(runner, "_load_referencia", return_value=None),
            patch.object(runner, "_derive_inference_pack", return_value={}),
            patch.object(runner, "_prepare_inputs", side_effect=fresh_inputs),
            patch("concilium.application.runtime.Runtime") as MockRuntime,
        ):
            mock_store = MagicMock()
            mock_store.new_version.side_effect = ["v1", "v2"]
            mock_store.load_canonical.return_value = _make_canonical()
            mock_foc.return_value = mock_store

            mock_rt = MagicMock()
            mock_rt.run_pipeline.side_effect = fake_run_pipeline
            MockRuntime.return_value = mock_rt

            runner.compare(spec, algorithms=["CP-SAT", "LNS"])

        assert captured_algorithms[0] == "CP-SAT"
        assert captured_algorithms[1] == "LNS"

    def test_exception_stored_as_error_entry(self):
        runner = self._build_runner()
        spec = _make_spec()

        with (
            patch.object(runner, "_find_or_create") as mock_foc,
            patch.object(runner, "_load_referencia", return_value=None),
            patch.object(runner, "_derive_inference_pack", return_value={}),
            patch.object(runner, "_prepare_inputs", return_value={}),
            patch("concilium.application.runtime.Runtime") as MockRuntime,
        ):
            mock_store = MagicMock()
            mock_store.new_version.side_effect = ["v1", "v2", "v3"]
            mock_foc.return_value = mock_store

            mock_rt = MagicMock()
            mock_rt.run_pipeline.side_effect = RuntimeError("pipeline exploded")
            MockRuntime.return_value = mock_rt

            report = runner.compare(spec, algorithms=["CP-SAT"])

        assert len(report.entries) == 1
        assert report.entries[0].error is not None
        assert "RuntimeError" in report.entries[0].error
        assert "pipeline exploded" in report.entries[0].error

    def test_exception_version_preserved_in_error_entry(self):
        runner = self._build_runner()
        spec = _make_spec()

        with (
            patch.object(runner, "_find_or_create") as mock_foc,
            patch.object(runner, "_load_referencia", return_value=None),
            patch.object(runner, "_derive_inference_pack", return_value={}),
            patch.object(runner, "_prepare_inputs", return_value={}),
            patch("concilium.application.runtime.Runtime") as MockRuntime,
        ):
            mock_store = MagicMock()
            mock_store.new_version.return_value = "v42"
            mock_foc.return_value = mock_store

            mock_rt = MagicMock()
            mock_rt.run_pipeline.side_effect = ValueError("bad input")
            MockRuntime.return_value = mock_rt

            report = runner.compare(spec, algorithms=["LNS"])

        assert report.entries[0].version == "v42"

    def test_save_json_writes_valid_json(self):
        runner = self._build_runner()
        spec = _make_spec()

        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = Path(tmpdir) / "subdir" / "report.json"

            with (
                patch.object(runner, "_find_or_create") as mock_foc,
                patch.object(runner, "_load_referencia", return_value=None),
                patch.object(runner, "_derive_inference_pack", return_value={}),
                patch.object(runner, "_prepare_inputs", return_value={}),
                patch("concilium.application.runtime.Runtime") as MockRuntime,
            ):
                mock_store = MagicMock()
                mock_store.new_version.side_effect = ["v1", "v2", "v3"]
                mock_store.load_canonical.return_value = _make_canonical()
                mock_foc.return_value = mock_store
                MockRuntime.return_value = MagicMock()

                runner.compare(spec, algorithms=["CP-SAT"], save_json=save_path)

            assert save_path.exists()
            loaded = json.loads(save_path.read_text(encoding="utf-8"))
            assert loaded["project_name"] == "TestProject"
            assert "entries" in loaded

    def test_save_json_creates_parent_dirs(self):
        runner = self._build_runner()
        spec = _make_spec()

        with tempfile.TemporaryDirectory() as tmpdir:
            # nested path that does not yet exist
            save_path = Path(tmpdir) / "a" / "b" / "c" / "report.json"

            with (
                patch.object(runner, "_find_or_create") as mock_foc,
                patch.object(runner, "_load_referencia", return_value=None),
                patch.object(runner, "_derive_inference_pack", return_value={}),
                patch.object(runner, "_prepare_inputs", return_value={}),
                patch("concilium.application.runtime.Runtime") as MockRuntime,
            ):
                mock_store = MagicMock()
                mock_store.new_version.return_value = "v1"
                mock_store.load_canonical.return_value = _make_canonical()
                mock_foc.return_value = mock_store
                MockRuntime.return_value = MagicMock()

                runner.compare(spec, algorithms=["MINSLK"], save_json=save_path)

            assert save_path.exists()

    def test_compare_without_save_json_returns_report(self):
        runner = self._build_runner()
        spec = _make_spec()

        with (
            patch.object(runner, "_find_or_create") as mock_foc,
            patch.object(runner, "_load_referencia", return_value=None),
            patch.object(runner, "_derive_inference_pack", return_value={}),
            patch.object(runner, "_prepare_inputs", return_value={}),
            patch("concilium.application.runtime.Runtime") as MockRuntime,
        ):
            mock_store = MagicMock()
            mock_store.new_version.return_value = "v1"
            mock_store.load_canonical.return_value = _make_canonical()
            mock_foc.return_value = mock_store
            MockRuntime.return_value = MagicMock()

            report = runner.compare(spec, algorithms=["CP-SAT"], save_json=None)

        assert isinstance(report, AlgorithmComparisonReport)

    def test_compare_entries_have_correct_algorithms(self):
        runner = self._build_runner()
        spec = _make_spec()

        with (
            patch.object(runner, "_find_or_create") as mock_foc,
            patch.object(runner, "_load_referencia", return_value=None),
            patch.object(runner, "_derive_inference_pack", return_value={}),
            patch.object(runner, "_prepare_inputs", return_value={}),
            patch("concilium.application.runtime.Runtime") as MockRuntime,
        ):
            mock_store = MagicMock()
            mock_store.new_version.side_effect = ["v1", "v2"]
            mock_store.load_canonical.return_value = _make_canonical()
            mock_foc.return_value = mock_store
            MockRuntime.return_value = MagicMock()

            report = runner.compare(spec, algorithms=["CP-SAT", "LNS"])

        algo_names = [e.algorithm for e in report.entries]
        assert algo_names == ["CP-SAT", "LNS"]

    def test_all_succeed_no_errors(self):
        runner = self._build_runner()
        spec = _make_spec()

        with (
            patch.object(runner, "_find_or_create") as mock_foc,
            patch.object(runner, "_load_referencia", return_value=None),
            patch.object(runner, "_derive_inference_pack", return_value={}),
            patch.object(runner, "_prepare_inputs", return_value={}),
            patch("concilium.application.runtime.Runtime") as MockRuntime,
        ):
            mock_store = MagicMock()
            mock_store.new_version.side_effect = ["v1", "v2", "v3"]
            mock_store.load_canonical.return_value = _make_canonical()
            mock_foc.return_value = mock_store
            MockRuntime.return_value = MagicMock()

            report = runner.compare(spec)

        for entry in report.entries:
            assert entry.error is None

    def test_mixed_success_and_failure(self):
        runner = self._build_runner()
        spec = _make_spec()
        call_count = [0]

        def side_effect_run(store, inputs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise RuntimeError("second algo failed")

        with (
            patch.object(runner, "_find_or_create") as mock_foc,
            patch.object(runner, "_load_referencia", return_value=None),
            patch.object(runner, "_derive_inference_pack", return_value={}),
            patch.object(runner, "_prepare_inputs", return_value={}),
            patch("concilium.application.runtime.Runtime") as MockRuntime,
        ):
            mock_store = MagicMock()
            mock_store.new_version.side_effect = ["v1", "v2", "v3"]
            mock_store.load_canonical.return_value = _make_canonical()
            mock_foc.return_value = mock_store

            mock_rt = MagicMock()
            mock_rt.run_pipeline.side_effect = side_effect_run
            MockRuntime.return_value = mock_rt

            report = runner.compare(spec)

        errors = [e for e in report.entries if e.error is not None]
        successes = [e for e in report.entries if e.error is None]
        assert len(errors) == 1
        assert len(successes) == 2


# ─────────────────────────────────────────────────────────────────────────────
# AlgorithmComparisonRunner._load_referencia
# ─────────────────────────────────────────────────────────────────────────────


class TestLoadReferencia:
    def test_returns_none_when_no_path(self):
        runner = AlgorithmComparisonRunner(Path("/tmp/cfg"), Path("/tmp/prj"))
        spec = SimpleNamespace(referencia_path=None)
        result = runner._load_referencia(spec)
        assert result is None

    def test_returns_none_when_path_not_exist(self):
        runner = AlgorithmComparisonRunner(Path("/tmp/cfg"), Path("/tmp/prj"))
        spec = SimpleNamespace(referencia_path=Path("/nonexistent/path/ref.json"))
        result = runner._load_referencia(spec)
        assert result is None

    def test_returns_dict_when_path_exists(self):
        runner = AlgorithmComparisonRunner(Path("/tmp/cfg"), Path("/tmp/prj"))
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False, encoding="utf-8") as f:
            json.dump({"key": "value"}, f)
            tmp_path = Path(f.name)
        try:
            spec = SimpleNamespace(referencia_path=tmp_path)
            result = runner._load_referencia(spec)
            assert result == {"key": "value"}
        finally:
            tmp_path.unlink(missing_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# AlgorithmComparisonRunner._derive_inference_pack
# ─────────────────────────────────────────────────────────────────────────────


class TestDeriveInferencePack:
    def test_calls_benchmark_inference_service(self):
        runner = AlgorithmComparisonRunner(Path("/tmp/cfg"), Path("/tmp/prj"))
        mock_pack = {"some": "pack"}
        mock_svc = MagicMock()
        mock_svc.derive.return_value = mock_pack
        mock_mod = MagicMock()
        mock_mod.BenchmarkInferenceService = mock_svc

        with patch("importlib.import_module", return_value=mock_mod):
            result = runner._derive_inference_pack(None)

        mock_svc.derive.assert_called_once_with(None)
        assert result == mock_pack

    def test_passes_ref_data_to_derive(self):
        runner = AlgorithmComparisonRunner(Path("/tmp/cfg"), Path("/tmp/prj"))
        ref_data = {"some": "ref"}
        mock_svc = MagicMock()
        mock_mod = MagicMock()
        mock_mod.BenchmarkInferenceService = mock_svc

        with patch("importlib.import_module", return_value=mock_mod):
            runner._derive_inference_pack(ref_data)

        mock_svc.derive.assert_called_once_with(ref_data)


# ─────────────────────────────────────────────────────────────────────────────
# AlgorithmComparisonRunner._prepare_inputs
# ─────────────────────────────────────────────────────────────────────────────


class TestPrepareInputs:
    def _make_mock_svc(self):
        mock_svc = MagicMock()
        # apply_to_skill_inputs returns its first argument unchanged
        mock_svc.apply_to_skill_inputs.side_effect = lambda inputs, pack: inputs
        mock_mod = MagicMock()
        mock_mod.BenchmarkInferenceService = mock_svc
        return mock_mod, mock_svc

    def test_escopo_inputs_added_to_skill_inputs(self):
        runner = AlgorithmComparisonRunner(Path("/tmp/cfg"), Path("/tmp/prj"))
        spec = SimpleNamespace(
            contexto_id="CTX-1",
            inputs_escopo={"area": 50},
            inputs_01A=None,
            inputs_cronograma=None,
            inputs_indiretos=None,
            extra_inputs={},
        )
        mock_mod, mock_svc = self._make_mock_svc()

        with patch("importlib.import_module", return_value=mock_mod):
            result = runner._prepare_inputs(spec, None, {})

        assert "01-escopo-e-eap" in result
        assert "00-escopo" in result

    def test_contexto_id_injected_when_missing(self):
        runner = AlgorithmComparisonRunner(Path("/tmp/cfg"), Path("/tmp/prj"))
        spec = SimpleNamespace(
            contexto_id="CTX-99",
            inputs_escopo={"area": 10},
            inputs_01A=None,
            inputs_cronograma=None,
            inputs_indiretos=None,
            extra_inputs={},
        )
        mock_mod, mock_svc = self._make_mock_svc()

        with patch("importlib.import_module", return_value=mock_mod):
            result = runner._prepare_inputs(spec, None, {})

        assert result["01-escopo-e-eap"]["contexto_id"] == "CTX-99"

    def test_contexto_id_not_overwritten_if_already_present(self):
        runner = AlgorithmComparisonRunner(Path("/tmp/cfg"), Path("/tmp/prj"))
        spec = SimpleNamespace(
            contexto_id="CTX-99",
            inputs_escopo={"area": 10, "contexto_id": "CTX-OVERRIDE"},
            inputs_01A=None,
            inputs_cronograma=None,
            inputs_indiretos=None,
            extra_inputs={},
        )
        mock_mod, mock_svc = self._make_mock_svc()

        with patch("importlib.import_module", return_value=mock_mod):
            result = runner._prepare_inputs(spec, None, {})

        assert result["01-escopo-e-eap"]["contexto_id"] == "CTX-OVERRIDE"

    def test_inputs_01A_mapped_to_catalogo(self):
        runner = AlgorithmComparisonRunner(Path("/tmp/cfg"), Path("/tmp/prj"))
        spec = SimpleNamespace(
            contexto_id="CTX-1",
            inputs_escopo=None,
            inputs_01A={"cat": "data"},
            inputs_cronograma=None,
            inputs_indiretos=None,
            extra_inputs={},
        )
        mock_mod, mock_svc = self._make_mock_svc()

        with patch("importlib.import_module", return_value=mock_mod):
            result = runner._prepare_inputs(spec, None, {})

        assert result["03-catalogo-de-recursos"] == {"cat": "data"}

    def test_inputs_cronograma_mapped_to_04(self):
        runner = AlgorithmComparisonRunner(Path("/tmp/cfg"), Path("/tmp/prj"))
        spec = SimpleNamespace(
            contexto_id="CTX-1",
            inputs_escopo=None,
            inputs_01A=None,
            inputs_cronograma={"duration_weeks": 4},
            inputs_indiretos=None,
            extra_inputs={},
        )
        mock_mod, mock_svc = self._make_mock_svc()

        with patch("importlib.import_module", return_value=mock_mod):
            result = runner._prepare_inputs(spec, None, {})

        assert result["04-cronograma"] == {"duration_weeks": 4}

    def test_inputs_indiretos_merged_into_resultado(self):
        runner = AlgorithmComparisonRunner(Path("/tmp/cfg"), Path("/tmp/prj"))
        spec = SimpleNamespace(
            contexto_id="CTX-1",
            inputs_escopo=None,
            inputs_01A=None,
            inputs_cronograma=None,
            inputs_indiretos={"taxa": 0.1},
            extra_inputs={},
        )
        mock_mod, mock_svc = self._make_mock_svc()

        with patch("importlib.import_module", return_value=mock_mod):
            result = runner._prepare_inputs(spec, None, {})

        assert "06-resultado-financeiro" in result
        assert result["06-resultado-financeiro"]["taxa"] == 0.1

    def test_extra_inputs_merged(self):
        runner = AlgorithmComparisonRunner(Path("/tmp/cfg"), Path("/tmp/prj"))
        spec = SimpleNamespace(
            contexto_id="CTX-1",
            inputs_escopo=None,
            inputs_01A=None,
            inputs_cronograma=None,
            inputs_indiretos=None,
            extra_inputs={"07-foo": {"bar": 1}},
        )
        mock_mod, mock_svc = self._make_mock_svc()

        with patch("importlib.import_module", return_value=mock_mod):
            result = runner._prepare_inputs(spec, None, {})

        assert "07-foo" in result

    def test_apply_to_skill_inputs_called(self):
        runner = AlgorithmComparisonRunner(Path("/tmp/cfg"), Path("/tmp/prj"))
        spec = SimpleNamespace(
            contexto_id="CTX-1",
            inputs_escopo={"area": 10},
            inputs_01A=None,
            inputs_cronograma=None,
            inputs_indiretos=None,
            extra_inputs={},
        )
        mock_mod, mock_svc = self._make_mock_svc()
        inference_pack = {"some_pack": True}

        with patch("importlib.import_module", return_value=mock_mod):
            runner._prepare_inputs(spec, None, inference_pack)

        mock_svc.apply_to_skill_inputs.assert_called_once()
        call_args = mock_svc.apply_to_skill_inputs.call_args
        assert call_args[0][1] == inference_pack


# ─────────────────────────────────────────────────────────────────────────────
# AlgorithmComparisonRunner._find_or_create
# ─────────────────────────────────────────────────────────────────────────────


class TestFindOrCreate:
    def test_creates_new_when_projects_root_not_exist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            non_existent = Path(tmpdir) / "does_not_exist"
            runner = AlgorithmComparisonRunner(Path("/tmp/cfg"), non_existent)
            spec = SimpleNamespace(nome="MyProject", contexto_id="CTX-1")

            mock_store = MagicMock()
            with patch("concilium.infrastructure.storage.project.ProjectStore") as MockStore:
                MockStore.init.return_value = mock_store
                runner._find_or_create(spec, reset=False)

            MockStore.init.assert_called_once_with(non_existent, "MyProject", "CTX-1")

    def test_returns_existing_store_when_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            projects_root = Path(tmpdir)
            # Create a fake project directory with meta.json
            proj_dir = projects_root / "abc123"
            proj_dir.mkdir()
            (proj_dir / "meta.json").write_text(json.dumps({"nome": "ExistingProject"}), encoding="utf-8")

            runner = AlgorithmComparisonRunner(Path("/tmp/cfg"), projects_root)
            spec = SimpleNamespace(nome="ExistingProject", contexto_id="CTX-1")

            mock_store = MagicMock()
            with patch("concilium.infrastructure.storage.project.ProjectStore") as MockStore:
                MockStore.return_value = mock_store
                result = runner._find_or_create(spec, reset=False)

            MockStore.assert_called_once_with(proj_dir)
            assert result is mock_store

    def test_reset_deletes_and_falls_through_to_create(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            projects_root = Path(tmpdir)
            proj_dir = projects_root / "abc123"
            proj_dir.mkdir()
            (proj_dir / "meta.json").write_text(json.dumps({"nome": "ExistingProject"}), encoding="utf-8")

            runner = AlgorithmComparisonRunner(Path("/tmp/cfg"), projects_root)
            spec = SimpleNamespace(nome="ExistingProject", contexto_id="CTX-1")

            mock_store = MagicMock()
            with patch("concilium.infrastructure.storage.project.ProjectStore") as MockStore:
                MockStore.init.return_value = mock_store
                runner._find_or_create(spec, reset=True)

            # After reset, we call ProjectStore.init (not ProjectStore())
            MockStore.init.assert_called_once()

    def test_skips_non_directory_entries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            projects_root = Path(tmpdir)
            # Create a file (not a directory) in projects_root
            (projects_root / "not_a_dir.txt").write_text("hello", encoding="utf-8")

            runner = AlgorithmComparisonRunner(Path("/tmp/cfg"), projects_root)
            spec = SimpleNamespace(nome="SomeProject", contexto_id="CTX-1")

            mock_store = MagicMock()
            with patch("concilium.infrastructure.storage.project.ProjectStore") as MockStore:
                MockStore.init.return_value = mock_store
                runner._find_or_create(spec, reset=False)

            MockStore.init.assert_called_once()

    def test_continues_loop_past_non_matching_name(self):
        """A project dir whose meta.json 'nome' doesn't match spec.nome must
        not short-circuit the search — the loop keeps going to the next dir
        (covers the false branch of the name-match check)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            projects_root = Path(tmpdir)
            other_dir = projects_root / "other"
            other_dir.mkdir()
            (other_dir / "meta.json").write_text(json.dumps({"nome": "OtherProject"}), encoding="utf-8")

            runner = AlgorithmComparisonRunner(Path("/tmp/cfg"), projects_root)
            spec = SimpleNamespace(nome="NewProject", contexto_id="CTX-1")

            mock_store = MagicMock()
            with patch("concilium.infrastructure.storage.project.ProjectStore") as MockStore:
                MockStore.init.return_value = mock_store
                result = runner._find_or_create(spec, reset=False)

            MockStore.init.assert_called_once()
            assert result is mock_store


# ─────────────────────────────────────────────────────────────────────────────
# _print_entry (module-level helper)
# ─────────────────────────────────────────────────────────────────────────────


class TestPrintEntry:
    def test_prints_error_for_failed_entry(self, capsys):
        from concilium.application.benchmarks.algorithm_comparison import _print_entry

        e = AlgorithmComparisonEntry(algorithm="CP-SAT", error="some failure")
        _print_entry(e)
        captured = capsys.readouterr()
        assert "[FAIL]" in captured.out
        assert "some failure" in captured.out

    def test_prints_ok_for_successful_entry(self, capsys):
        from concilium.application.benchmarks.algorithm_comparison import _print_entry

        e = AlgorithmComparisonEntry(algorithm="LNS", makespan_weeks=10, quality_score=0.85, is_feasible=True)
        _print_entry(e)
        captured = capsys.readouterr()
        assert "[OK]" in captured.out
        assert "LNS" in captured.out

    def test_prints_relaxed_flag(self, capsys):
        from concilium.application.benchmarks.algorithm_comparison import _print_entry

        e = AlgorithmComparisonEntry(
            algorithm="MINSLK",
            makespan_weeks=12,
            quality_score=0.7,
            was_relaxed=True,
        )
        _print_entry(e)
        captured = capsys.readouterr()
        assert "relaxed" in captured.out

    def test_prints_cost_when_present(self, capsys):
        from concilium.application.benchmarks.algorithm_comparison import _print_entry

        e = AlgorithmComparisonEntry(
            algorithm="CP-SAT",
            makespan_weeks=8,
            quality_score=0.9,
            cost_total=300_000.0,
        )
        _print_entry(e)
        captured = capsys.readouterr()
        assert "cost=" in captured.out

    def test_prints_mob_when_present(self, capsys):
        from concilium.application.benchmarks.algorithm_comparison import _print_entry

        e = AlgorithmComparisonEntry(
            algorithm="LNS",
            makespan_weeks=10,
            quality_score=0.8,
            mob_cost=5_000.0,
        )
        _print_entry(e)
        captured = capsys.readouterr()
        assert "mob=" in captured.out
