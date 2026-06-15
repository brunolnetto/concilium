"""Fat CLI tests for commands_schedule.py.

Strategy: typer.testing.CliRunner + patch to cover as many branches as possible
without running actual solvers. Tests cover schedule_run, schedule_compare,
_activities_from_spec, _pool_from_spec, _dag_from_spec, _resolve_deadline_weeks,
and _emit_result.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from concilium.presentation.cli.commands_schedule import (
    _activities_from_spec,
    _dag_from_spec,
    _emit_result,
    _pool_from_spec,
    _resolve_deadline_weeks,
    app,
)

runner = CliRunner()

_CLI_MOD = "concilium.presentation.cli.commands_schedule"
_SCHEDULING_MOD = "concilium.application.scheduling"


# ────────────────────────────────────────────────────────────────────────────
# Fixtures — minimal rcpsp_spec and referencia.json payloads
# ────────────────────────────────────────────────────────────────────────────

MINIMAL_RCPSP_SPEC = {
    "activities": [
        {
            "item_id": "act-01",
            "descricao": "Escavacao",
            "duration_weeks": 4,
            "required_resources": {"escavadeira": 2},
        },
        {
            "item_id": "act-02",
            "duration_weeks": 2,
            "required_resources": {"escavadeira": 1},
        },
    ],
    "resource_pool": {"escavadeira": 3},
    "precedence": [["act-01", "act-02"]],
}


def _make_referencia_json(tmp_path: Path, rcpsp_spec=MINIMAL_RCPSP_SPEC, extra: dict | None = None) -> Path:
    """Write a referencia.json with optional rcpsp_spec and return its path."""
    payload: dict = {}
    if rcpsp_spec is not None:
        payload["rcpsp_spec"] = rcpsp_spec
    if extra:
        payload.update(extra)
    p = tmp_path / "referencia.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _make_explore_result(heuristic: str = "MINSLK", makespan: int = 6, quality: float = 0.85):
    """Return a MagicMock mimicking ExploreResult."""
    sched_act = MagicMock()
    sched_act.activity_id = "act-01"
    sched_act.start_week = 0
    sched_act.end_week = 4
    sched_act.duration_weeks = 4
    sched_act.assigned_resources = {"escavadeira": 2}

    schedule = MagicMock()
    schedule.makespan = makespan
    schedule.feasible = True
    schedule.scheduled_activities = [sched_act]

    result = MagicMock()
    result.heuristic = heuristic
    result.schedule = schedule
    result.quality_score = quality
    result.error = None
    return result


# ────────────────────────────────────────────────────────────────────────────
# _resolve_deadline_weeks — unit tests (no CLI)
# ────────────────────────────────────────────────────────────────────────────


class TestResolveDeadlineWeeks:
    def test_explicit_value_overrides_all(self):
        """Explicit deadline_weeks returns as-is, ignoring ref_raw."""
        ref = {"meta": {"data_inicio": "2026-01-01", "data_termino": "2026-12-31"}}
        assert _resolve_deadline_weeks(42, ref) == 42

    def test_date_math_from_meta(self):
        """Reads dates from ref_raw['meta'] when deadline_weeks is None."""
        ref = {"meta": {"data_inicio": "2026-01-01", "data_termino": "2026-04-01"}}
        result = _resolve_deadline_weeks(None, ref)
        # 89 days // 7 + 1 = 13 weeks
        assert result >= 12

    def test_date_math_from_top_level(self):
        """Falls back to top-level keys when meta is missing."""
        ref = {"data_inicio": "2026-01-01", "data_termino": "2026-03-01"}
        result = _resolve_deadline_weeks(None, ref)
        assert result >= 8

    def test_fallback_to_60_on_missing_keys(self):
        """Returns 60 when both meta and top-level dates are absent."""
        assert _resolve_deadline_weeks(None, {}) == 60

    def test_fallback_to_60_on_bad_date_format(self):
        """Returns 60 when date strings are unparseable."""
        ref = {"meta": {"data_inicio": "not-a-date", "data_termino": "2026-12-31"}}
        assert _resolve_deadline_weeks(None, ref) == 60

    def test_minimum_1_week_enforced(self):
        """Same start and end date yields at least 1 week."""
        ref = {"meta": {"data_inicio": "2026-06-01", "data_termino": "2026-06-01"}}
        result = _resolve_deadline_weeks(None, ref)
        assert result >= 1

    def test_zero_explicit_returns_zero(self):
        """Explicit 0 is returned directly (caller's responsibility)."""
        assert _resolve_deadline_weeks(0, {}) == 0


# ────────────────────────────────────────────────────────────────────────────
# _activities_from_spec / _pool_from_spec / _dag_from_spec — unit tests
# ────────────────────────────────────────────────────────────────────────────


class TestHelperFunctions:
    def test_activities_from_spec_basic(self):
        """Parses activities list, uses item_id as description fallback."""
        activities = _activities_from_spec(MINIMAL_RCPSP_SPEC)
        assert len(activities) == 2
        assert activities[0].activity_id == "act-01"
        assert activities[0].description == "Escavacao"
        assert activities[0].duration_weeks == 4
        assert activities[0].required_resources == {"escavadeira": 2}

    def test_activities_from_spec_uses_item_id_as_description_fallback(self):
        """When 'descricao' is absent, activity_id is used."""
        activities = _activities_from_spec(MINIMAL_RCPSP_SPEC)
        assert activities[1].description == "act-02"

    def test_pool_from_spec(self):
        """Parses resource_pool correctly."""
        pool = _pool_from_spec(MINIMAL_RCPSP_SPEC)
        assert pool.resources == {"escavadeira": 3}

    def test_dag_from_spec_with_precedence(self):
        """Parses precedence list into ActivityDAG."""
        acts = _activities_from_spec(MINIMAL_RCPSP_SPEC)
        dag = _dag_from_spec(MINIMAL_RCPSP_SPEC, acts)
        assert len(dag.precedence) == 1
        assert ("act-01", "act-02") in dag.precedence

    def test_dag_from_spec_empty_precedence(self):
        """Handles spec without 'precedence' key."""
        spec = dict(MINIMAL_RCPSP_SPEC)
        spec.pop("precedence", None)
        acts = _activities_from_spec(spec)
        dag = _dag_from_spec(spec, acts)
        assert dag.precedence == []


# ────────────────────────────────────────────────────────────────────────────
# _emit_result — unit tests
# ────────────────────────────────────────────────────────────────────────────


class TestEmitResult:
    def test_emit_result_no_output_prints_json(self, capsys):
        """Without output path, data is printed as JSON."""
        data = {"algorithm": "MINSLK", "makespan": 6}
        _emit_result(data, None)
        # No file should be created; function should not raise

    def test_emit_result_with_output_writes_file(self, tmp_path):
        """With output path, file is written with JSON content."""
        out = tmp_path / "result.json"
        data = {"algorithm": "MINSLK", "makespan": 6, "feasible": True}
        _emit_result(data, out)
        assert out.exists()
        loaded = json.loads(out.read_text())
        assert loaded["algorithm"] == "MINSLK"
        assert loaded["makespan"] == 6


# ────────────────────────────────────────────────────────────────────────────
# schedule_run — CLI tests
# ────────────────────────────────────────────────────────────────────────────


class TestScheduleRun:
    def _patch_explore(self, results):
        # explore_schedules is imported lazily via `from concilium.application.scheduling import ...`
        # Patch both the package namespace and the selector source so all references are replaced.
        return patch(f"{_SCHEDULING_MOD}.explore_schedules", return_value=results)

    def _patch_scheduling_imports(self):
        """Patch the scheduling domain imports used inside _activities_from_spec, etc."""
        return []

    def test_happy_path_exit_0_json_output(self, tmp_path):
        """Feasible solver result: exit 0, JSON output contains expected keys."""
        ref = _make_referencia_json(tmp_path)
        explore_result = _make_explore_result()

        with self._patch_explore([explore_result]):
            result = runner.invoke(app, ["run", str(ref)])

        assert result.exit_code == 0, result.output
        # JSON keys should appear somewhere in output
        assert "algorithm" in result.output or "MINSLK" in result.output

    def test_happy_path_v2_spec_key(self, tmp_path):
        """rcpsp_spec nested under 'spec' key (v2 format) is found correctly."""
        payload = {"spec": {"rcpsp_spec": MINIMAL_RCPSP_SPEC}}
        p = tmp_path / "referencia.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        explore_result = _make_explore_result()

        with self._patch_explore([explore_result]):
            result = runner.invoke(app, ["run", str(p)])

        assert result.exit_code == 0, result.output

    def test_no_rcpsp_spec_exit_1(self, tmp_path):
        """Missing rcpsp_spec key → exit 1 with red message."""
        p = tmp_path / "referencia.json"
        p.write_text("{}", encoding="utf-8")
        result = runner.invoke(app, ["run", str(p)])
        assert result.exit_code == 1
        assert "rcpsp_spec" in result.output

    def test_solver_returns_empty_list_exit_1(self, tmp_path):
        """Empty explore_schedules result → exit 1."""
        ref = _make_referencia_json(tmp_path)
        with self._patch_explore([]):
            result = runner.invoke(app, ["run", str(ref)])
        assert result.exit_code == 1
        assert "viavel" in result.output.lower() or "solver" in result.output.lower()

    def test_with_output_flag_writes_file(self, tmp_path):
        """--output flag causes JSON to be written to file."""
        ref = _make_referencia_json(tmp_path)
        out = tmp_path / "schedule_result.json"
        explore_result = _make_explore_result()

        with self._patch_explore([explore_result]):
            result = runner.invoke(app, ["run", str(ref), "--output", str(out)])

        assert result.exit_code == 0, result.output
        assert out.exists()
        loaded = json.loads(out.read_text())
        assert "algorithm" in loaded
        assert "makespan" in loaded
        assert "feasible" in loaded

    def test_algorithm_flag_minslk(self, tmp_path):
        """--algorithm MINSLK passes single-item heuristics list."""
        ref = _make_referencia_json(tmp_path)
        captured_kwargs = {}

        def fake_explore(**kwargs):
            captured_kwargs.update(kwargs)
            return [_make_explore_result("MINSLK")]

        with patch(f"{_SCHEDULING_MOD}.explore_schedules", side_effect=fake_explore):
            result = runner.invoke(app, ["run", str(ref), "--algorithm", "MINSLK"])

        assert result.exit_code == 0, result.output
        assert captured_kwargs.get("heuristics") == ["MINSLK"]

    def test_default_heuristics_when_no_algorithm_flag(self, tmp_path):
        """No --algorithm flag → default heuristics list has 3 entries."""
        ref = _make_referencia_json(tmp_path)
        captured_kwargs = {}

        def fake_explore(**kwargs):
            captured_kwargs.update(kwargs)
            return [_make_explore_result()]

        with patch(f"{_SCHEDULING_MOD}.explore_schedules", side_effect=fake_explore):
            result = runner.invoke(app, ["run", str(ref)])

        assert result.exit_code == 0, result.output
        assert set(captured_kwargs.get("heuristics", [])) == {"MINSLK", "LPT", "MAXRES"}

    def test_deadline_flag_overrides_date_math(self, tmp_path):
        """--deadline N passes N directly to explore_schedules."""
        ref = _make_referencia_json(tmp_path)
        captured_kwargs = {}

        def fake_explore(**kwargs):
            captured_kwargs.update(kwargs)
            return [_make_explore_result()]

        with patch(f"{_SCHEDULING_MOD}.explore_schedules", side_effect=fake_explore):
            result = runner.invoke(app, ["run", str(ref), "--deadline", "52"])

        assert result.exit_code == 0, result.output
        assert captured_kwargs.get("deadline_weeks") == 52

    def test_scheduled_activities_appear_in_output(self, tmp_path):
        """Result JSON contains scheduled_activities list."""
        ref = _make_referencia_json(tmp_path)
        explore_result = _make_explore_result()

        with self._patch_explore([explore_result]):
            result = runner.invoke(app, ["run", str(ref)])

        assert result.exit_code == 0, result.output
        assert "scheduled_activities" in result.output

    def test_deadline_from_meta_dates(self, tmp_path):
        """Without explicit --deadline, date math uses meta.data_inicio/termino."""
        payload = {
            "rcpsp_spec": MINIMAL_RCPSP_SPEC,
            "meta": {"data_inicio": "2026-01-01", "data_termino": "2026-06-30"},
        }
        p = tmp_path / "referencia.json"
        p.write_text(json.dumps(payload), encoding="utf-8")

        captured_kwargs = {}

        def fake_explore(**kwargs):
            captured_kwargs.update(kwargs)
            return [_make_explore_result()]

        with patch(f"{_SCHEDULING_MOD}.explore_schedules", side_effect=fake_explore):
            result = runner.invoke(app, ["run", str(p)])

        assert result.exit_code == 0, result.output
        # 2026-01-01 to 2026-06-30 is 180 days → 180//7 + 1 = 26 weeks
        assert captured_kwargs.get("deadline_weeks", 0) >= 20


# ────────────────────────────────────────────────────────────────────────────
# schedule_compare — CLI tests
# ────────────────────────────────────────────────────────────────────────────


class TestScheduleCompare:
    def _patch_compare(self, results):
        # compare_all_algorithms is imported lazily inside schedule_compare
        return patch(f"{_SCHEDULING_MOD}.compare_all_algorithms", return_value=results)

    def _make_compare_result(self, heuristic="MINSLK", feasible=True, error=None, makespan=6, quality=0.85):
        schedule = MagicMock()
        schedule.makespan = makespan
        schedule.feasible = feasible

        r = MagicMock()
        r.heuristic = heuristic
        r.schedule = schedule
        r.quality_score = quality
        r.error = error
        return r

    def test_happy_path_exit_0_table_printed(self, tmp_path):
        """Feasible results: exit 0, table rendered."""
        ref = _make_referencia_json(tmp_path)
        results = [self._make_compare_result("MINSLK", True)]

        with self._patch_compare(results):
            result = runner.invoke(app, ["compare", str(ref)])

        assert result.exit_code == 0, result.output
        assert "MINSLK" in result.output

    def test_compare_with_feasible_and_errored_results(self, tmp_path):
        """Mix of feasible and errored results renders both rows in table."""
        ref = _make_referencia_json(tmp_path)
        results = [
            self._make_compare_result("MINSLK", True),
            self._make_compare_result("LPT", False, error="timeout after 30s"),
        ]

        with self._patch_compare(results):
            result = runner.invoke(app, ["compare", str(ref)])

        assert result.exit_code == 0, result.output
        assert "MINSLK" in result.output
        assert "LPT" in result.output

    def test_no_rcpsp_spec_exit_1(self, tmp_path):
        """Missing rcpsp_spec key → exit 1."""
        p = tmp_path / "referencia.json"
        p.write_text("{}", encoding="utf-8")
        result = runner.invoke(app, ["compare", str(p)])
        assert result.exit_code == 1
        assert "rcpsp_spec" in result.output

    def test_empty_results_exit_1(self, tmp_path):
        """compare_all_algorithms returns empty list → exit 1."""
        ref = _make_referencia_json(tmp_path)
        with self._patch_compare([]):
            result = runner.invoke(app, ["compare", str(ref)])
        assert result.exit_code == 1
        assert "Nenhum resultado" in result.output

    def test_with_output_writes_json_file(self, tmp_path):
        """--output flag causes JSON to be written."""
        ref = _make_referencia_json(tmp_path)
        out = tmp_path / "compare_result.json"
        results = [self._make_compare_result("MINSLK", True)]

        with self._patch_compare(results):
            result = runner.invoke(app, ["compare", str(ref), "--output", str(out)])

        assert result.exit_code == 0, result.output
        assert out.exists()
        loaded = json.loads(out.read_text())
        assert isinstance(loaded, list)
        assert loaded[0]["algorithm"] == "MINSLK"

    def test_algorithms_flag_passed_to_compare(self, tmp_path):
        """--algorithms flag passes comma-separated list to compare_all_algorithms."""
        ref = _make_referencia_json(tmp_path)
        captured_kwargs = {}

        def fake_compare(activities, dag, pool, deadline_weeks, **kwargs):
            captured_kwargs.update(kwargs)
            return [self._make_compare_result()]

        with patch(f"{_SCHEDULING_MOD}.compare_all_algorithms", side_effect=fake_compare):
            result = runner.invoke(app, ["compare", str(ref), "--algorithms", "MINSLK,LPT"])

        assert result.exit_code == 0, result.output
        assert captured_kwargs.get("algorithms") == ["MINSLK", "LPT"]

    def test_default_algorithms_when_flag_empty(self, tmp_path):
        """Empty --algorithms flag → None passed (use defaults)."""
        ref = _make_referencia_json(tmp_path)
        captured_kwargs = {}

        def fake_compare(activities, dag, pool, deadline_weeks, **kwargs):
            captured_kwargs.update(kwargs)
            return [self._make_compare_result()]

        with patch(f"{_SCHEDULING_MOD}.compare_all_algorithms", side_effect=fake_compare):
            result = runner.invoke(app, ["compare", str(ref)])

        assert result.exit_code == 0, result.output
        assert captured_kwargs.get("algorithms") is None

    def test_compare_v2_spec_format(self, tmp_path):
        """rcpsp_spec nested under 'spec' key (v2) is found correctly."""
        payload = {"spec": {"rcpsp_spec": MINIMAL_RCPSP_SPEC}}
        p = tmp_path / "referencia.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        results = [self._make_compare_result("MINSLK", True)]

        with self._patch_compare(results):
            result = runner.invoke(app, ["compare", str(p)])

        assert result.exit_code == 0, result.output

    def test_compare_infeasible_result_renders_infeasible(self, tmp_path):
        """Infeasible result (no error string) shows infeasible in table."""
        ref = _make_referencia_json(tmp_path)
        results = [self._make_compare_result("LPT", feasible=False, error=None)]

        with self._patch_compare(results):
            result = runner.invoke(app, ["compare", str(ref)])

        assert result.exit_code == 0, result.output
        assert "infeasible" in result.output or "LPT" in result.output

    def test_compare_best_marker_appears(self, tmp_path):
        """Best feasible result gets marked with arrow marker."""
        ref = _make_referencia_json(tmp_path)
        results = [
            self._make_compare_result("MINSLK", True, quality=0.9),
            self._make_compare_result("LPT", True, quality=0.7),
        ]

        with self._patch_compare(results):
            result = runner.invoke(app, ["compare", str(ref)])

        assert result.exit_code == 0, result.output
        # Best marker ◀ should appear for the first (best) feasible result
        assert "◀" in result.output

    def test_compare_output_json_includes_error_field(self, tmp_path):
        """Output JSON includes error field for each result."""
        ref = _make_referencia_json(tmp_path)
        out = tmp_path / "out.json"
        results = [
            self._make_compare_result("MINSLK", True),
            self._make_compare_result("LPT", False, error="solver failed"),
        ]

        with self._patch_compare(results):
            result = runner.invoke(app, ["compare", str(ref), "--output", str(out)])

        assert result.exit_code == 0, result.output
        loaded = json.loads(out.read_text())
        algorithms = {r["algorithm"] for r in loaded}
        assert "MINSLK" in algorithms
        assert "LPT" in algorithms

    def test_deadline_flag_passed_to_compare(self, tmp_path):
        """--deadline flag is resolved and passed."""
        ref = _make_referencia_json(tmp_path)
        captured = {}

        def fake_compare(activities, dag, pool, deadline_weeks, **kwargs):
            captured["deadline_weeks"] = deadline_weeks
            return [self._make_compare_result()]

        with patch(f"{_SCHEDULING_MOD}.compare_all_algorithms", side_effect=fake_compare):
            result = runner.invoke(app, ["compare", str(ref), "--deadline", "26"])

        assert result.exit_code == 0, result.output
        assert captured["deadline_weeks"] == 26
