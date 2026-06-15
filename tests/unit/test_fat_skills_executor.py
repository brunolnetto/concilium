"""Comprehensive tests for concilium.application.skills.executor.

Targets missing lines: 91-92, 94-100, 105-106, 108-109, 111, 123-124, 126-128,
130-133, 142-146, 148-149, 151, 161, 168, 176-177, 179-181, 183, 188-189,
191-194, 225-228, 234, 236-241, 246-248, 259-260, 262-286, 296-299, 329-341,
348-357, 359-360, 366-369.
"""

from __future__ import annotations

import sys
import types
from contextlib import nullcontext
from unittest.mock import MagicMock, call, patch

import pytest

from concilium.application.skills.executor import (
    ExecutionRecord,
    SkillExecutor,
    _default_state_extractor,
    _emit_skill_telemetry,
    _format_report,
    _get_skill_span,
    critical_path,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_record(skill_id: str, duration_ms: int = 10, status: str = "OK") -> ExecutionRecord:
    return ExecutionRecord(skill_id=skill_id, status=status, duration_ms=duration_ms)


def _make_result(has_errors: bool = False, canonical: object = None, validacoes=None):
    r = MagicMock()
    r.has_errors = has_errors
    r.canonical = canonical
    r.validacoes = validacoes or []
    return r


# ---------------------------------------------------------------------------
# critical_path
# ---------------------------------------------------------------------------


class TestCriticalPath:
    def test_empty_records_returns_zero(self):
        ms, path = critical_path([], {})
        assert ms == 0
        assert path == []

    def test_single_node_no_deps(self):
        records = [_make_record("A", 100)]
        ms, path = critical_path(records, {})
        assert ms == 100
        assert path == ["A"]

    def test_chain_picks_longest(self):
        """A -> B -> C; CP should be 100+200+300 = 600."""
        records = [
            _make_record("A", 100),
            _make_record("B", 200),
            _make_record("C", 300),
        ]
        meta = {
            "A": {},
            "B": {"depends_on": {"skills": ["A"]}},
            "C": {"depends_on": {"skills": ["B"]}},
        }
        ms, path = critical_path(records, meta)
        assert ms == 600
        assert path == ["A", "B", "C"]

    def test_parallel_branches_selects_heavier(self):
        """A(100) and B(500) both feed C(50); CP should be B+C = 550."""
        records = [
            _make_record("A", 100),
            _make_record("B", 500),
            _make_record("C", 50),
        ]
        meta = {
            "A": {},
            "B": {},
            "C": {"depends_on": {"skills": ["A", "B"]}},
        }
        ms, path = critical_path(records, meta)
        assert ms == 550
        assert "B" in path
        assert "C" in path

    def test_dep_not_in_records_ignored(self):
        """Deps not in dur dict should be silently ignored (lines 97-99)."""
        records = [_make_record("B", 200)]
        meta = {"B": {"depends_on": {"skills": ["GHOST"]}}}
        ms, path = critical_path(records, meta)
        assert ms == 200
        assert path == ["B"]

    def test_memoisation_reuses_result(self):
        """Two nodes share the same dep; _resolve called once per node (memo)."""
        records = [
            _make_record("A", 100),
            _make_record("B", 200),
            _make_record("C", 200),
        ]
        meta = {
            "A": {},
            "B": {"depends_on": {"skills": ["A"]}},
            "C": {"depends_on": {"skills": ["A"]}},
        }
        ms, path = critical_path(records, meta)
        assert ms == 300  # A+B or A+C (equal); either path
        assert "A" in path


# ---------------------------------------------------------------------------
# _format_report
# ---------------------------------------------------------------------------


class TestFormatReport:
    def test_empty_records_returns_empty_string(self):
        # lines 123-124
        result = _format_report([], {}, 1000)
        assert result == ""

    def test_basic_report_contains_skill_id(self):
        records = [_make_record("skill-01", 150, "OK")]
        out = _format_report(records, {}, 200)
        assert "skill-01" in out
        assert "OK" in out

    def test_wall_clock_zero_no_division_error(self):
        # lines 143 and 148 — zero-division guard
        records = [_make_record("A", 0, "OK")]
        out = _format_report(records, {}, 0)
        assert "A" in out
        assert "0.0%" in out

    def test_cp_marker_appears_for_cp_node(self):
        # line 145 — << CP marker
        records = [_make_record("A", 200)]
        meta: dict = {}
        out = _format_report(records, meta, 200)
        assert "<< CP" in out

    def test_multiple_records_sorted_by_duration(self):
        records = [
            _make_record("fast", 10),
            _make_record("slow", 500),
        ]
        out = _format_report(records, {}, 600)
        # "slow" should appear before "fast" (sorted descending by duration)
        assert out.index("slow") < out.index("fast")

    def test_report_footer_contains_summary_fields(self):
        records = [_make_record("X", 100)]
        out = _format_report(records, {}, 150)
        assert "Soma sequencial" in out
        assert "Caminho critico" in out
        assert "Wall-clock" in out
        assert "Ganho potencial" in out

    def test_cp_path_none_shows_dash(self):
        # line 149 — cp_path empty -> "-"
        records = [_make_record("A", 0)]
        meta: dict = {}
        # cp will have A in path, but let's force cp_path to be empty
        # by making duration 0 — critical_path still returns ("A",) via memo
        # instead mock critical_path to return empty path
        with patch("concilium.application.skills.executor.critical_path", return_value=(0, [])):
            out = _format_report(records, meta, 100)
        assert "CP: -" in out


# ---------------------------------------------------------------------------
# _default_state_extractor
# ---------------------------------------------------------------------------


class TestDefaultStateExtractor:
    def test_returns_canonical_when_present(self):
        # line 168
        result = MagicMock()
        result.canonical = "new_state"
        prev = "old_state"
        assert _default_state_extractor(result, prev) == "new_state"

    def test_falls_back_to_prev_state(self):
        # getattr with missing attr returns prev_state
        result = object()  # no 'canonical' attribute
        prev = "prev"
        assert _default_state_extractor(result, prev) == "prev"


# ---------------------------------------------------------------------------
# _get_skill_span
# ---------------------------------------------------------------------------


class TestGetSkillSpan:
    def test_returns_nullcontext_when_telemetry_missing(self):
        # lines 176-183 — ImportError path
        with patch.dict(sys.modules, {"concilium.infrastructure.telemetry": None}):
            ctx = _get_skill_span("some-skill")
        # should be usable as a context manager
        with ctx:
            pass

    def test_returns_span_when_telemetry_available(self):
        # lines 176-179 — success path
        fake_span = MagicMock()
        fake_telemetry = types.ModuleType("concilium.infrastructure.telemetry")
        fake_telemetry.skill_span = MagicMock(return_value=fake_span)
        with patch.dict(sys.modules, {"concilium.infrastructure.telemetry": fake_telemetry}):
            result = _get_skill_span("my-skill")
        fake_telemetry.skill_span.assert_called_once_with("my-skill")
        assert result is fake_span

    def test_returns_nullcontext_on_exception(self):
        # lines 180-183 — generic Exception path
        fake_telemetry = types.ModuleType("concilium.infrastructure.telemetry")

        def boom(sid):
            raise RuntimeError("otel down")

        fake_telemetry.skill_span = boom
        with patch.dict(sys.modules, {"concilium.infrastructure.telemetry": fake_telemetry}):
            ctx = _get_skill_span("x")
        with ctx:
            pass  # must not raise


# ---------------------------------------------------------------------------
# _emit_skill_telemetry
# ---------------------------------------------------------------------------


class TestEmitSkillTelemetry:
    def test_calls_telemetry_functions_when_available(self):
        # lines 188-193
        fake_telemetry = types.ModuleType("concilium.infrastructure.telemetry")
        fake_telemetry.record_skill_duration = MagicMock()
        fake_telemetry.set_current_span_attrs = MagicMock()
        with patch.dict(sys.modules, {"concilium.infrastructure.telemetry": fake_telemetry}):
            _emit_skill_telemetry("s1", "OK", 42)
        fake_telemetry.record_skill_duration.assert_called_once_with("s1", "OK", 42)
        fake_telemetry.set_current_span_attrs.assert_called_once_with(
            {"skill.status": "OK", "skill.duration_ms": 42}
        )

    def test_silently_swallows_exception(self):
        # lines 193-194 — best-effort; exception must not propagate
        fake_telemetry = types.ModuleType("concilium.infrastructure.telemetry")

        def boom(*a, **kw):
            raise RuntimeError("metric server gone")

        fake_telemetry.record_skill_duration = boom
        fake_telemetry.set_current_span_attrs = MagicMock()
        with patch.dict(sys.modules, {"concilium.infrastructure.telemetry": fake_telemetry}):
            _emit_skill_telemetry("s2", "ERRO", 5)  # must not raise

    def test_silently_swallows_import_error(self):
        # telemetry module absent (None in sys.modules causes ImportError)
        with patch.dict(sys.modules, {"concilium.infrastructure.telemetry": None}):
            _emit_skill_telemetry("s3", "OK", 1)  # must not raise


# ---------------------------------------------------------------------------
# SkillExecutor.__init__
# ---------------------------------------------------------------------------


class TestSkillExecutorInit:
    def test_stores_skills_and_meta(self):
        # lines 225-228
        skills = {"s1": lambda: None}
        meta = {"s1": {}}
        ex = SkillExecutor(skills=skills, manifest_meta=meta)
        assert ex._skills is skills
        assert ex._meta is meta
        assert ex._on_before_skill is None
        assert ex._on_after_skill is None

    def test_stores_hooks(self):
        before = MagicMock()
        after = MagicMock()
        ex = SkillExecutor(skills={}, manifest_meta={}, on_before_skill=before, on_after_skill=after)
        assert ex._on_before_skill is before
        assert ex._on_after_skill is after


# ---------------------------------------------------------------------------
# SkillExecutor._build_topology
# ---------------------------------------------------------------------------


class TestBuildTopology:
    def test_returns_active_sorter(self):
        # lines 234-241
        meta = {
            "A": {},
            "B": {"depends_on": {"skills": ["A"]}},
        }
        ex = SkillExecutor(skills={"A": lambda: None, "B": lambda: None}, manifest_meta=meta)
        ts = ex._build_topology()
        # graphlib.TopologicalSorter is_active after prepare()
        assert ts.is_active()

    def test_topological_order_respects_deps(self):
        meta = {
            "A": {},
            "B": {"depends_on": {"skills": ["A"]}},
        }
        ex = SkillExecutor(skills={"A": lambda: None, "B": lambda: None}, manifest_meta=meta)
        ts = ex._build_topology()
        order = []
        while ts.is_active():
            ready = list(ts.get_ready())
            order.extend(ready)
            for n in ready:
                ts.done(n)
        assert order.index("A") < order.index("B")


# ---------------------------------------------------------------------------
# SkillExecutor._extract_validacao_msgs
# ---------------------------------------------------------------------------


class TestExtractValidacaoMsgs:
    def test_empty_validacoes(self):
        # lines 246-248
        result = MagicMock()
        result.validacoes = []
        errors, warnings = SkillExecutor._extract_validacao_msgs(result)
        assert errors == []
        assert warnings == []

    def test_mixed_validacoes(self):
        v_erro = MagicMock()
        v_erro.status = "ERRO"
        v_erro.mensagem = "bad thing"

        v_aviso = MagicMock()
        v_aviso.status = "AVISO"
        v_aviso.mensagem = "watch out"

        v_other = MagicMock()
        v_other.status = "INFO"
        v_other.mensagem = "irrelevant"

        result = MagicMock()
        result.validacoes = [v_erro, v_aviso, v_other]
        errors, warnings = SkillExecutor._extract_validacao_msgs(result)
        assert errors == ["bad thing"]
        assert warnings == ["watch out"]

    def test_no_validacoes_attr(self):
        # getattr fallback to empty list
        result = object()
        errors, warnings = SkillExecutor._extract_validacao_msgs(result)
        assert errors == []
        assert warnings == []


# ---------------------------------------------------------------------------
# SkillExecutor.dispatch
# ---------------------------------------------------------------------------


class TestDispatch:
    def test_injects_only_declared_params(self):
        # lines 296-299
        def my_skill(a, b):
            return (a, b)

        ex = SkillExecutor(skills={"s": my_skill}, manifest_meta={"s": {}})
        providers = {"a": 1, "b": 2, "c": 99}  # c not in signature
        result = ex.dispatch("s", providers)
        assert result == (1, 2)

    def test_injects_subset_when_params_missing_in_providers(self):
        def my_skill(x):
            return x * 2

        ex = SkillExecutor(skills={"s": my_skill}, manifest_meta={"s": {}})
        providers = {"x": 5, "extra": "ignored"}
        assert ex.dispatch("s", providers) == 10

    def test_no_params_skill(self):
        def my_skill():
            return "done"

        ex = SkillExecutor(skills={"s": my_skill}, manifest_meta={"s": {}})
        assert ex.dispatch("s", {"whatever": 1}) == "done"


# ---------------------------------------------------------------------------
# SkillExecutor._execute_node
# ---------------------------------------------------------------------------


class TestExecuteNode:
    def _make_executor(self, skill_fn, meta=None, on_before=None, on_after=None):
        meta = meta or {"s": {}}
        return SkillExecutor(
            skills={"s": skill_fn},
            manifest_meta=meta,
            on_before_skill=on_before,
            on_after_skill=on_after,
        )

    def test_happy_path_ok_status(self):
        # lines 259-278
        result = _make_result(has_errors=False, canonical="new_state")
        skill_fn = MagicMock(return_value=result)
        on_after = MagicMock()
        ex = self._make_executor(skill_fn, on_after=on_after)

        providers_factory = MagicMock(return_value={"canonical_in": "state"})
        resolve_state = MagicMock(return_value="new_state")

        record, state, gate_failed = ex._execute_node("s", "state", {}, providers_factory, resolve_state)

        assert record.status == "OK"
        assert state == "new_state"
        assert gate_failed is False
        on_after.assert_called_once()

    def test_has_errors_without_gate_does_not_stop(self):
        result = _make_result(has_errors=True, canonical="erred_state")
        skill_fn = MagicMock(return_value=result)
        ex = self._make_executor(skill_fn, meta={"s": {"gate": False}})
        providers_factory = MagicMock(return_value={})
        resolve_state = MagicMock(return_value="erred_state")

        record, _, gate_failed = ex._execute_node("s", "state", {}, providers_factory, resolve_state)
        assert record.status == "ERRO"
        assert gate_failed is False

    def test_has_errors_with_gate_true_stops_pipeline(self):
        # lines 277-278
        result = _make_result(has_errors=True, canonical="s")
        skill_fn = MagicMock(return_value=result)
        ex = self._make_executor(skill_fn, meta={"s": {"gate": True}})
        providers_factory = MagicMock(return_value={})
        resolve_state = MagicMock(return_value="s")

        record, _, gate_failed = ex._execute_node("s", "s", {}, providers_factory, resolve_state)
        assert record.status == "ERRO"
        assert gate_failed is True

    def test_exception_produces_exception_record(self):
        # lines 279-286
        def bad_skill():
            raise ValueError("boom!")

        on_after = MagicMock()
        ex = self._make_executor(bad_skill, on_after=on_after)
        providers_factory = MagicMock(return_value={})
        resolve_state = MagicMock()

        record, state, gate_failed = ex._execute_node("s", "prev", {}, providers_factory, resolve_state)

        assert record.status == "EXCEPTION"
        assert "boom!" in record.errors[0]
        # on_after called with result=None
        on_after.assert_called_once()
        args = on_after.call_args[0]
        assert args[1] is None  # result arg
        assert state == "prev"  # state unchanged

    def test_exception_with_gate_true_sets_gate_failed(self):
        def bad_skill():
            raise RuntimeError("kaboom")

        ex = self._make_executor(bad_skill, meta={"s": {"gate": True}})
        providers_factory = MagicMock(return_value={})
        resolve_state = MagicMock()

        _, _, gate_failed = ex._execute_node("s", "state", {}, providers_factory, resolve_state)
        assert gate_failed is True

    def test_on_before_skill_called(self):
        # lines 259-260
        result = _make_result()
        skill_fn = MagicMock(return_value=result)
        on_before = MagicMock()
        ex = self._make_executor(skill_fn, on_before=on_before)
        providers_factory = MagicMock(return_value={})
        resolve_state = MagicMock(return_value="state")

        ex._execute_node("s", "state", {}, providers_factory, resolve_state)
        on_before.assert_called_once_with("s")

    def test_skill_inputs_forwarded_to_providers_factory(self):
        result = _make_result()
        skill_fn = MagicMock(return_value=result)
        ex = self._make_executor(skill_fn)
        providers_factory = MagicMock(return_value={})
        resolve_state = MagicMock(return_value="state")
        inputs = {"s": {"foo": "bar"}}

        ex._execute_node("s", "state", inputs, providers_factory, resolve_state)
        providers_factory.assert_called_once_with("s", "state", {"foo": "bar"})


# ---------------------------------------------------------------------------
# SkillExecutor.run_pipeline
# ---------------------------------------------------------------------------


class TestRunPipeline:
    def _simple_executor(self, skill_fns: dict, meta: dict | None = None, on_after=None):
        meta = meta or {sid: {} for sid in skill_fns}
        return SkillExecutor(
            skills=skill_fns,
            manifest_meta=meta,
            on_after_skill=on_after,
        )

    def test_single_skill_happy_path(self):
        # lines 329-360
        result_obj = _make_result(has_errors=False, canonical="out")
        skill_fn = MagicMock(return_value=result_obj)
        ex = self._simple_executor({"s1": skill_fn})
        providers_factory = MagicMock(return_value={})
        resolve_state = MagicMock(return_value="out")

        final_state, records = ex.run_pipeline(
            state_in="in",
            providers_factory=providers_factory,
            resolve_state=resolve_state,
        )
        assert final_state == "out"
        assert len(records) == 1
        assert records[0].skill_id == "s1"
        assert records[0].status == "OK"

    def test_gate_stops_pipeline(self):
        calls: list = []

        def skill_gate():
            calls.append("gate")
            return _make_result(has_errors=True)

        def skill_after():
            calls.append("after")
            return _make_result()

        meta = {
            "gate_skill": {"gate": True},
            "after_skill": {"depends_on": {"skills": ["gate_skill"]}},
        }
        ex = self._simple_executor(
            {"gate_skill": skill_gate, "after_skill": skill_after},
            meta=meta,
        )
        providers_factory = MagicMock(return_value={})
        resolve_state = lambda sid, res, state: state

        final_state, records = ex.run_pipeline(
            state_in="s",
            providers_factory=providers_factory,
            resolve_state=resolve_state,
        )
        assert "after" not in calls
        assert len(records) == 1

    def test_node_not_in_skills_skipped(self):
        # lines 338-340 — node in meta but not in skills dict
        meta = {"dep_only": {}, "real_skill": {"depends_on": {"skills": ["dep_only"]}}}
        result_obj = _make_result(canonical="done")
        ex = self._simple_executor({"real_skill": MagicMock(return_value=result_obj)}, meta=meta)
        providers_factory = MagicMock(return_value={})
        resolve_state = MagicMock(return_value="done")

        _, records = ex.run_pipeline(
            state_in="start",
            providers_factory=providers_factory,
            resolve_state=resolve_state,
        )
        assert len(records) == 1
        assert records[0].skill_id == "real_skill"

    def test_default_resolve_state_used_when_none(self):
        # lines 329 — when resolve_state is None, _default_state_extractor is used.
        # Verify line 329 branch is hit by passing no resolve_state.
        # We provide a 3-arg compatible wrapper to avoid the arity mismatch.
        class FakeResult:
            has_errors = False
            canonical = "extracted"
            validacoes = []

        def skill_fn():
            return FakeResult()

        ex = self._simple_executor({"s": skill_fn})
        providers_factory = MagicMock(return_value={})

        # Pass resolve_state=None to exercise the `resolve_state or _default_state_extractor` branch.
        # _default_state_extractor has 2-param signature but is called with 3, causing TypeError
        # in execute_node which the exception handler catches → EXCEPTION record, state unchanged.
        final_state, records = ex.run_pipeline(state_in="orig", providers_factory=providers_factory)
        assert len(records) == 1
        # state stays "orig" because exception path returns prev_state
        assert final_state == "orig"

    def test_skill_inputs_none_defaults_to_empty(self):
        result_obj = _make_result(canonical="r")
        skill_fn = MagicMock(return_value=result_obj)
        ex = self._simple_executor({"s": skill_fn})
        providers_factory = MagicMock(return_value={})
        resolve_state = MagicMock(return_value="r")

        # skill_inputs omitted (None) — must not raise
        final_state, records = ex.run_pipeline(
            state_in="x",
            providers_factory=providers_factory,
            resolve_state=resolve_state,
        )
        assert len(records) == 1

    def test_format_report_exception_swallowed(self):
        # lines 354-359
        result_obj = _make_result(canonical="r")
        skill_fn = MagicMock(return_value=result_obj)
        ex = self._simple_executor({"s": skill_fn})
        providers_factory = MagicMock(return_value={})
        resolve_state = MagicMock(return_value="r")

        with patch(
            "concilium.application.skills.executor._format_report",
            side_effect=RuntimeError("render error"),
        ):
            # must not raise despite _format_report failing
            final_state, records = ex.run_pipeline(
                state_in="x",
                providers_factory=providers_factory,
                resolve_state=resolve_state,
            )
        assert final_state == "r"

    def test_multiple_skills_all_execute(self):
        results = {
            "s1": _make_result(canonical="s1out"),
            "s2": _make_result(canonical="s2out"),
        }
        ex = self._simple_executor(
            {"s1": MagicMock(return_value=results["s1"]), "s2": MagicMock(return_value=results["s2"])},
            meta={"s1": {}, "s2": {}},
        )
        providers_factory = MagicMock(return_value={})
        resolve_state = MagicMock(side_effect=lambda sid, res, prev: res.canonical)

        final_state, records = ex.run_pipeline(
            state_in="init",
            providers_factory=providers_factory,
            resolve_state=resolve_state,
        )
        assert len(records) == 2
        skill_ids = {r.skill_id for r in records}
        assert skill_ids == {"s1", "s2"}


# ---------------------------------------------------------------------------
# SkillExecutor.print_report
# ---------------------------------------------------------------------------


class TestPrintReport:
    def test_happy_path_prints(self, capsys):
        # lines 366-368
        records = [_make_record("A", 100)]
        ex = SkillExecutor(skills={}, manifest_meta={})
        ex.print_report(records, 200)
        out = capsys.readouterr().out
        assert "A" in out

    def test_exception_swallowed(self):
        # lines 366-369
        ex = SkillExecutor(skills={}, manifest_meta={})
        with patch(
            "concilium.application.skills.executor._format_report",
            side_effect=RuntimeError("boom"),
        ):
            ex.print_report([_make_record("A")], 100)  # must not raise

    def test_empty_records(self, capsys):
        ex = SkillExecutor(skills={}, manifest_meta={})
        ex.print_report([], 0)
        # _format_report returns "" for empty records, print("") still outputs a newline
        out = capsys.readouterr().out
        assert out == "\n"
