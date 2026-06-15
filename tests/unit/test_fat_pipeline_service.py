"""Fat coverage tests for PipelineService.

Goal: exercise as many lines as possible by mocking dependencies at the
boundary so that the real service method logic runs.

Each test covers one complete execution path (happy path or specific error path).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from concilium.application.services.project.audit_service import AuditService
from concilium.application.services.pipeline_service import PipelineService
from concilium.application.services.project.project_files import DEFAULT_PROJECT_FILES, ProjectFiles


# ─── helpers ──────────────────────────────────────────────────────────────────


def _make_project_mock(tmp_path: Path | None = None, meta: dict | None = None) -> MagicMock:
    """Build a project MagicMock with sensible defaults."""
    p = MagicMock()
    p.meta = meta or {"id": "proj-test", "contexto_id": "ctx-1"}
    p.root = (tmp_path / "project") if tmp_path else Path("/fake/project")
    p.read_json.return_value = []
    p.read_lines.return_value = []
    p.current_version.return_value = "v1"
    p.new_version.return_value = "v2"
    p.list_output_files.return_value = []
    p.load_canonical.return_value = MagicMock(eap=None)
    return p


def _make_svc(project: MagicMock | None = None, tmp_path: Path | None = None):
    """Return (PipelineService, project_mock, audit_mock, runtime_mock)."""
    if project is None:
        project = _make_project_mock(tmp_path=tmp_path)

    repo = MagicMock()
    repo.get_project.return_value = project

    audit = MagicMock(spec=AuditService)

    runtime = MagicMock()
    runtime.run_pipeline.return_value = []
    runtime_factory = MagicMock(return_value=runtime)

    svc = PipelineService(
        repository=repo,
        audit_service=audit,
        runtime_factory=runtime_factory,
    )
    return svc, project, audit, runtime


# ─── TestRunProject ───────────────────────────────────────────────────────────


class TestRunProject:
    """Covers lines 45-46, 57-59, 73: sync happy path."""

    def test_happy_path_returns_run_dict(self, tmp_path):
        svc, project, audit, runtime = _make_svc(tmp_path=tmp_path)
        # runs.json returns an empty list initially (creates the run), then after
        # _create_run has written it, we need _find_run and get_run to work.
        # We'll control read_json to return the run we expect after creation.
        run_id_holder = {}

        original_write = MagicMock()

        def capture_write(path, data):
            if path == DEFAULT_PROJECT_FILES.runs:
                original_write(path, data)
                # Store the run_id so we can return it later
                if data:
                    run_id_holder["run_id"] = data[-1]["run_id"]

        project.write_json.side_effect = capture_write

        read_call_count = [0]

        def dynamic_read(path, default=None):
            if path == DEFAULT_PROJECT_FILES.runs:
                read_call_count[0] += 1
                run_id = run_id_holder.get("run_id")
                if run_id is None:
                    return []
                return [
                    {
                        "run_id": run_id,
                        "project_id": "proj-test",
                        "status": "OK",
                        "requested_at": "2024-01-01T00:00:00+00:00",
                        "started_at": "2024-01-01T00:00:01+00:00",
                        "finished_at": "2024-01-01T00:00:02+00:00",
                        "base_version": None,
                        "version": "v1",
                        "fork_version": False,
                        "use_mobilizacao_policy": True,
                        "use_strict_catalog_baseline": False,
                        "catalogo_base_origem": "master",
                        "catalogo_base_hash": None,
                        "skill_inputs_override": {},
                        "skills_log": [],
                        "invocation_line_offset": 0,
                        "summary": {},
                        "output_files": [],
                        "error": None,
                    }
                ]
            if path == DEFAULT_PROJECT_FILES.skill_inputs:
                return {}
            return default if default is not None else {}

        project.read_json.side_effect = dynamic_read
        project.read_lines.return_value = []

        # Ensure version dir exists for resolved_catalog write
        version_dir = tmp_path / "project" / "v1"
        version_dir.mkdir(parents=True, exist_ok=True)

        with patch("concilium.application.pipeline_strategy.get_pipeline_strategy") as mock_strategy:
            strategy = MagicMock()
            strategy.skill_sequence.return_value = []
            mock_strategy.return_value = strategy

            with patch("concilium.application.services.service_support.build_summary", return_value={}):
                result = svc.run_project(
                    "proj-test",
                    base_version=None,
                    fork_version=False,
                    skill_inputs_override={},
                    use_saved_overrides=False,
                    use_mobilizacao_policy=False,
                    use_strict_catalog_baseline=False,
                    actor="test-user",
                )

        assert "run_id" in result
        assert result["status"] == "OK"
        # audit.log called once
        audit.log.assert_called_once()
        call_kwargs = audit.log.call_args
        assert call_kwargs[1]["action"] == "run_project_sync"
        assert call_kwargs[1]["actor"] == "test-user"

    def test_run_project_calls_execute_and_get_run(self, tmp_path):
        """Lines 57-58: _execute_run and get_run are both invoked."""
        svc, project, audit, runtime = _make_svc(tmp_path=tmp_path)

        execute_called = []
        get_run_called = []

        original_execute = svc._execute_run
        original_get_run = svc.get_run

        # We'll patch at instance level
        def fake_execute(proj, run_id):
            execute_called.append(run_id)

        def fake_get_run(project_id, run_id):
            get_run_called.append(run_id)
            return {"status": "OK", "version": "v1", "run_id": run_id}

        svc._execute_run = fake_execute
        svc.get_run = fake_get_run

        project.read_json.return_value = []

        result = svc.run_project(
            "proj-test",
            base_version=None,
            fork_version=False,
            skill_inputs_override={},
            use_saved_overrides=False,
            use_mobilizacao_policy=False,
            use_strict_catalog_baseline=False,
        )

        assert len(execute_called) == 1
        assert len(get_run_called) == 1
        assert result["status"] == "OK"


# ─── TestStartRunProject ──────────────────────────────────────────────────────


class TestStartRunProject:
    """Covers lines 87-88, 99-108, 122: async path."""

    def test_returns_pending_status(self):
        svc, project, audit, runtime = _make_svc()
        project.read_json.return_value = []

        result = svc.start_run_project(
            "proj-test",
            base_version=None,
            fork_version=False,
            skill_inputs_override={},
            use_saved_overrides=False,
            use_mobilizacao_policy=False,
            use_strict_catalog_baseline=False,
            actor="async-user",
        )

        assert result["status"] == "PENDING"
        assert result["project_id"] == "proj-test"
        assert "run_id" in result

    def test_future_is_stored_in_futures_dict(self):
        svc, project, audit, runtime = _make_svc()
        project.read_json.return_value = []

        result = svc.start_run_project(
            "proj-test",
            base_version=None,
            fork_version=False,
            skill_inputs_override={},
            use_saved_overrides=False,
            use_mobilizacao_policy=False,
            use_strict_catalog_baseline=False,
        )

        run_id = result["run_id"]
        assert run_id in svc._futures

    def test_audit_called_with_start_run_action(self):
        svc, project, audit, runtime = _make_svc()
        project.read_json.return_value = []

        result = svc.start_run_project(
            "proj-test",
            base_version="v1",
            fork_version=True,
            skill_inputs_override={"k": "v"},
            use_saved_overrides=True,
            use_mobilizacao_policy=True,
            use_strict_catalog_baseline=True,
            actor="actor-1",
        )

        audit.log.assert_called_once()
        call_kwargs = audit.log.call_args[1]
        assert call_kwargs["action"] == "start_run_project"
        assert call_kwargs["actor"] == "actor-1"
        assert call_kwargs["result"]["status"] == "PENDING"


# ─── TestListRuns ─────────────────────────────────────────────────────────────


class TestListRuns:
    """Covers lines 125-129: list_runs."""

    def test_returns_sorted_by_requested_at(self):
        svc, project, audit, runtime = _make_svc()
        runs = [
            {"run_id": "r1", "requested_at": "2024-01-01T00:00:00"},
            {"run_id": "r3", "requested_at": "2024-01-03T00:00:00"},
            {"run_id": "r2", "requested_at": "2024-01-02T00:00:00"},
        ]
        project.read_json.return_value = runs

        result = svc.list_runs("proj-test")

        assert [r["run_id"] for r in result] == ["r3", "r2", "r1"]

    def test_non_list_returns_empty(self):
        svc, project, audit, runtime = _make_svc()
        project.read_json.return_value = {"not": "a list"}

        result = svc.list_runs("proj-test")

        assert result == []

    def test_empty_list_returns_empty(self):
        svc, project, audit, runtime = _make_svc()
        project.read_json.return_value = []

        result = svc.list_runs("proj-test")

        assert result == []


# ─── TestGetRun ──────────────────────────────────────────────────────────────


class TestGetRun:
    """Covers lines 132-139, 141-142: get_run."""

    def test_non_list_raises_file_not_found(self):
        svc, project, audit, runtime = _make_svc()
        project.read_json.return_value = "not a list"

        with pytest.raises(FileNotFoundError, match="nao encontrado"):
            svc.get_run("proj-test", "r1")

    def test_run_id_missing_raises_file_not_found(self):
        svc, project, audit, runtime = _make_svc()
        project.read_json.return_value = [{"run_id": "r999"}]

        with pytest.raises(FileNotFoundError, match="nao encontrado"):
            svc.get_run("proj-test", "r-missing")

    def test_happy_path_calls_read_run_progress(self):
        svc, project, audit, runtime = _make_svc()
        run_data = {
            "run_id": "r1",
            "status": "OK",
            "requested_at": "2024-01-01T00:00:00",
            "started_at": None,
            "finished_at": None,
            "base_version": None,
            "version": "v1",
            "fork_version": False,
            "use_mobilizacao_policy": True,
            "use_strict_catalog_baseline": False,
            "catalogo_base_origem": None,
            "catalogo_base_hash": None,
            "skills_log": [],
            "invocation_line_offset": 0,
            "summary": {},
            "output_files": [],
            "error": None,
        }
        project.read_json.return_value = [run_data]
        project.read_lines.return_value = []

        progress_called = []
        original_rp = svc._read_run_progress

        def fake_progress(proj, run):
            progress_called.append(run["run_id"])
            return []

        svc._read_run_progress = fake_progress

        result = svc.get_run("proj-test", "r1")

        assert result["run_id"] == "r1"
        assert result["status"] == "OK"
        assert len(progress_called) == 1

    def test_get_run_returns_all_expected_fields(self):
        svc, project, audit, runtime = _make_svc()
        run_data = {
            "run_id": "r42",
            "status": "EXCEPTION",
            "requested_at": "2024-01-01T00:00:00",
            "started_at": "2024-01-01T00:00:01",
            "finished_at": "2024-01-01T00:00:05",
            "base_version": "v1",
            "version": "v2",
            "fork_version": True,
            "use_mobilizacao_policy": False,
            "use_strict_catalog_baseline": True,
            "catalogo_base_origem": "master",
            "catalogo_base_hash": "abc123",
            "skills_log": [{"skill": "01", "status": "OK"}],
            "invocation_line_offset": 0,
            "summary": {"preco_venda_total": 1000.0},
            "output_files": ["report.xlsx"],
            "error": "some error",
        }
        project.read_json.return_value = [run_data]
        project.read_lines.return_value = []

        result = svc.get_run("proj-test", "r42")

        assert result["project_id"] == "proj-test"
        assert result["run_id"] == "r42"
        assert result["status"] == "EXCEPTION"
        assert result["version"] == "v2"
        assert result["fork_version"] is True
        assert result["use_strict_catalog_baseline"] is True
        assert result["catalogo_base_hash"] == "abc123"
        assert result["error"] == "some error"


# ─── TestExecuteRun ───────────────────────────────────────────────────────────


class TestExecuteRun:
    """Covers lines 225-307: _execute_run various paths."""

    def _setup_runs(self, project, run_data: dict):
        """Configure project.read_json to return a run list with run_data."""
        runs_store = [dict(run_data)]
        write_store = {"data": list(runs_store)}

        def read_json(path, default=None):
            if path == DEFAULT_PROJECT_FILES.runs:
                return list(write_store["data"])
            if path == DEFAULT_PROJECT_FILES.skill_inputs:
                return {}
            if path == "benchmark_reference.json":
                return {}
            return default if default is not None else {}

        def write_json(path, data):
            if path == DEFAULT_PROJECT_FILES.runs:
                write_store["data"] = list(data)

        project.read_json.side_effect = read_json
        project.write_json.side_effect = write_json
        return write_store

    def test_find_run_none_returns_early(self):
        svc, project, audit, runtime = _make_svc()
        # _find_run returns None because runs list doesn't contain the run_id
        project.read_json.return_value = []

        # Should return without error
        svc._execute_run(project, "nonexistent-run-id")
        # write_json should not be called (no status update)
        project.write_json.assert_not_called()

    def test_current_version_none_triggers_new_version(self, tmp_path):
        svc, project, audit, runtime = _make_svc(tmp_path=tmp_path)
        run_id = "run_abc123"
        run_data = {
            "run_id": run_id,
            "status": "PENDING",
            "base_version": None,
            "fork_version": False,
            "use_saved_overrides": False,
            "use_mobilizacao_policy": False,
            "use_strict_catalog_baseline": False,
            "skill_inputs_override": {},
            "invocation_line_offset": 0,
        }
        self._setup_runs(project, run_data)

        # current_version returns None first time, then "v1" after new_version()
        call_count = [0]

        def current_version_side():
            call_count[0] += 1
            if call_count[0] <= 1:
                return None
            return "v1"

        project.current_version.side_effect = current_version_side
        project.new_version.return_value = "v1"
        project.read_lines.return_value = []

        # Create version dir
        version_dir = tmp_path / "project" / "v1"
        version_dir.mkdir(parents=True, exist_ok=True)

        with patch("concilium.application.pipeline_strategy.get_pipeline_strategy") as mock_strategy:
            strategy = MagicMock()
            strategy.skill_sequence.return_value = []
            mock_strategy.return_value = strategy
            with patch("concilium.application.services.service_support.build_summary", return_value={}):
                svc._execute_run(project, run_id)

        project.new_version.assert_called()

    def test_fork_version_true_triggers_new_version_with_base(self, tmp_path):
        svc, project, audit, runtime = _make_svc(tmp_path=tmp_path)
        run_id = "run_fork01"
        run_data = {
            "run_id": run_id,
            "status": "PENDING",
            "base_version": "v1",
            "fork_version": True,
            "use_saved_overrides": False,
            "use_mobilizacao_policy": False,
            "use_strict_catalog_baseline": False,
            "skill_inputs_override": {},
            "invocation_line_offset": 0,
        }
        self._setup_runs(project, run_data)

        project.current_version.return_value = "v2"
        project.new_version.return_value = "v2"
        project.read_lines.return_value = []

        version_dir = tmp_path / "project" / "v2"
        version_dir.mkdir(parents=True, exist_ok=True)

        with patch("concilium.application.pipeline_strategy.get_pipeline_strategy") as mock_strategy:
            strategy = MagicMock()
            strategy.skill_sequence.return_value = []
            mock_strategy.return_value = strategy
            with patch("concilium.application.services.service_support.build_summary", return_value={}):
                svc._execute_run(project, run_id)

        # new_version should be called with base="v1"
        project.new_version.assert_called_with(base="v1")

    def test_version_none_after_fork_raises_runtime_error(self, tmp_path):
        svc, project, audit, runtime = _make_svc(tmp_path=tmp_path)
        run_id = "run_noversion"
        run_data = {
            "run_id": run_id,
            "status": "PENDING",
            "base_version": None,
            "fork_version": False,
            "use_saved_overrides": False,
            "use_mobilizacao_policy": False,
            "use_strict_catalog_baseline": False,
            "skill_inputs_override": {},
            "invocation_line_offset": 0,
        }
        self._setup_runs(project, run_data)

        # current_version always returns None → RuntimeError
        project.current_version.return_value = None
        project.new_version.return_value = None

        svc._execute_run(project, run_id)

        # Should have set status=EXCEPTION
        write_calls = [c for c in project.write_json.call_args_list if c[0][0] == DEFAULT_PROJECT_FILES.runs]
        # Find last write with EXCEPTION status
        last_runs = write_calls[-1][0][1]
        last_run = next(r for r in last_runs if r["run_id"] == run_id)
        assert last_run["status"] == "EXCEPTION"

    def test_strict_catalog_baseline_no_benchmark_ref_raises(self, tmp_path):
        svc, project, audit, runtime = _make_svc(tmp_path=tmp_path)
        run_id = "run_strict01"
        run_data = {
            "run_id": run_id,
            "status": "PENDING",
            "base_version": None,
            "fork_version": False,
            "use_saved_overrides": False,
            "use_mobilizacao_policy": False,
            "use_strict_catalog_baseline": True,
            "skill_inputs_override": {},
            "invocation_line_offset": 0,
        }

        def read_json(path, default=None):
            if path == DEFAULT_PROJECT_FILES.runs:
                return [dict(run_data)]
            if path == "benchmark_reference.json":
                return {}  # empty → no catalog
            if path == DEFAULT_PROJECT_FILES.skill_inputs:
                return {}
            return default if default is not None else {}

        def write_json(path, data):
            pass

        project.read_json.side_effect = read_json
        project.write_json.side_effect = write_json
        project.current_version.return_value = "v1"
        project.read_lines.return_value = []

        svc._execute_run(project, run_id)

        # Should have stored the error in EXCEPTION status
        writes = [c for c in project.write_json.call_args_list if c[0][0] == DEFAULT_PROJECT_FILES.runs]
        last_runs = writes[-1][0][1]
        last_run = next(r for r in last_runs if r["run_id"] == run_id)
        assert last_run["status"] == "EXCEPTION"
        assert "catalogo" in last_run["error"].lower() or "baseline" in last_run["error"].lower()

    def test_happy_path_no_errors_sets_status_ok(self, tmp_path):
        svc, project, audit, runtime = _make_svc(tmp_path=tmp_path)
        run_id = "run_happy01"
        run_data = {
            "run_id": run_id,
            "status": "PENDING",
            "base_version": None,
            "fork_version": False,
            "use_saved_overrides": False,
            "use_mobilizacao_policy": False,
            "use_strict_catalog_baseline": False,
            "skill_inputs_override": {},
            "invocation_line_offset": 0,
        }
        write_store = self._setup_runs(project, run_data)

        project.current_version.return_value = "v1"
        project.read_lines.return_value = []
        runtime.run_pipeline.return_value = [{"skill": "01", "status": "OK"}]

        version_dir = tmp_path / "project" / "v1"
        version_dir.mkdir(parents=True, exist_ok=True)

        with patch("concilium.application.pipeline_strategy.get_pipeline_strategy") as mock_strategy:
            strategy = MagicMock()
            strategy.skill_sequence.return_value = ["01"]
            mock_strategy.return_value = strategy
            with patch("concilium.application.services.service_support.build_summary", return_value={"total": 1}):
                svc._execute_run(project, run_id)

        last_run = next(r for r in write_store["data"] if r["run_id"] == run_id)
        assert last_run["status"] == "OK"

    def test_skills_log_with_error_sets_status_erro(self, tmp_path):
        svc, project, audit, runtime = _make_svc(tmp_path=tmp_path)
        run_id = "run_err01"
        run_data = {
            "run_id": run_id,
            "status": "PENDING",
            "base_version": None,
            "fork_version": False,
            "use_saved_overrides": False,
            "use_mobilizacao_policy": False,
            "use_strict_catalog_baseline": False,
            "skill_inputs_override": {},
            "invocation_line_offset": 0,
        }
        write_store = self._setup_runs(project, run_data)

        project.current_version.return_value = "v1"
        project.read_lines.return_value = []
        runtime.run_pipeline.return_value = [{"skill": "01", "status": "ERRO"}]

        version_dir = tmp_path / "project" / "v1"
        version_dir.mkdir(parents=True, exist_ok=True)

        with patch("concilium.application.pipeline_strategy.get_pipeline_strategy") as mock_strategy:
            strategy = MagicMock()
            strategy.skill_sequence.return_value = ["01"]
            mock_strategy.return_value = strategy
            with patch("concilium.application.services.service_support.build_summary", return_value={}):
                svc._execute_run(project, run_id)

        last_run = next(r for r in write_store["data"] if r["run_id"] == run_id)
        assert last_run["status"] == "ERRO"

    def test_exception_in_pipeline_sets_status_exception(self, tmp_path):
        svc, project, audit, runtime = _make_svc(tmp_path=tmp_path)
        run_id = "run_exc01"
        run_data = {
            "run_id": run_id,
            "status": "PENDING",
            "base_version": None,
            "fork_version": False,
            "use_saved_overrides": False,
            "use_mobilizacao_policy": False,
            "use_strict_catalog_baseline": False,
            "skill_inputs_override": {},
            "invocation_line_offset": 0,
        }
        write_store = self._setup_runs(project, run_data)

        project.current_version.return_value = "v1"
        project.read_lines.return_value = []
        runtime.run_pipeline.side_effect = RuntimeError("pipeline exploded")

        version_dir = tmp_path / "project" / "v1"
        version_dir.mkdir(parents=True, exist_ok=True)

        with patch("concilium.application.pipeline_strategy.get_pipeline_strategy") as mock_strategy:
            strategy = MagicMock()
            strategy.skill_sequence.return_value = ["01"]
            mock_strategy.return_value = strategy
            svc._execute_run(project, run_id)

        last_run = next(r for r in write_store["data"] if r["run_id"] == run_id)
        assert last_run["status"] == "EXCEPTION"
        assert "pipeline exploded" in last_run["error"]

    def test_finally_pops_future(self, tmp_path):
        svc, project, audit, runtime = _make_svc(tmp_path=tmp_path)
        run_id = "run_future01"
        run_data = {
            "run_id": run_id,
            "status": "PENDING",
            "base_version": None,
            "fork_version": False,
            "use_saved_overrides": False,
            "use_mobilizacao_policy": False,
            "use_strict_catalog_baseline": False,
            "skill_inputs_override": {},
            "invocation_line_offset": 0,
        }
        self._setup_runs(project, run_data)

        project.current_version.return_value = "v1"
        project.read_lines.return_value = []

        version_dir = tmp_path / "project" / "v1"
        version_dir.mkdir(parents=True, exist_ok=True)

        # Pre-populate futures dict
        fake_future = MagicMock()
        svc._futures[run_id] = fake_future

        with patch("concilium.application.pipeline_strategy.get_pipeline_strategy") as mock_strategy:
            strategy = MagicMock()
            strategy.skill_sequence.return_value = []
            mock_strategy.return_value = strategy
            with patch("concilium.application.services.service_support.build_summary", return_value={}):
                svc._execute_run(project, run_id)

        assert run_id not in svc._futures


# ─── TestPrepareSkillInputs ───────────────────────────────────────────────────


class TestPrepareSkillInputs:
    """Covers lines 209-222: _prepare_skill_inputs."""

    def test_use_saved_overrides_true_deep_merges(self):
        svc, project, audit, runtime = _make_svc()

        skill_inputs_base = {"01-escopo": {"area": 100}}
        saved_overrides = {"01-escopo": {"area": 200, "extra": True}}

        def read_json(path, default=None):
            if path == DEFAULT_PROJECT_FILES.skill_inputs:
                return dict(skill_inputs_base)
            if path == DEFAULT_PROJECT_FILES.overrides:
                return dict(saved_overrides)
            if path == DEFAULT_PROJECT_FILES.mobilizacao_policies:
                return {}
            return default if default is not None else {}

        project.read_json.side_effect = read_json

        run = {
            "use_saved_overrides": True,
            "skill_inputs_override": {},
            "use_mobilizacao_policy": False,
        }

        result = svc._prepare_skill_inputs(project, run)

        assert result["01-escopo"]["area"] == 200
        assert result["01-escopo"]["extra"] is True

    def test_use_mobilizacao_policy_true_injects_when_absent(self):
        svc, project, audit, runtime = _make_svc()

        policies = {"item-1": {"policy": "x"}}

        def read_json(path, default=None):
            if path == DEFAULT_PROJECT_FILES.skill_inputs:
                return {}
            if path == DEFAULT_PROJECT_FILES.mobilizacao_policies:
                return policies
            return default if default is not None else {}

        project.read_json.side_effect = read_json

        run = {
            "use_saved_overrides": True,  # required for mobilizacao branch
            "skill_inputs_override": {},
            "use_mobilizacao_policy": True,
        }

        result = svc._prepare_skill_inputs(project, run)

        assert result["04-cronograma"]["mobilizacao_policies"] == policies

    def test_mobilizacao_policies_already_present_not_overwritten(self):
        svc, project, audit, runtime = _make_svc()

        existing_policies = {"item-existing": {"policy": "y"}}
        new_policies = {"item-new": {"policy": "z"}}

        def read_json(path, default=None):
            if path == DEFAULT_PROJECT_FILES.skill_inputs:
                return {"04-cronograma": {"mobilizacao_policies": existing_policies}}
            if path == DEFAULT_PROJECT_FILES.mobilizacao_policies:
                return new_policies
            return default if default is not None else {}

        project.read_json.side_effect = read_json

        run = {
            "use_saved_overrides": True,
            "skill_inputs_override": {},
            "use_mobilizacao_policy": True,
        }

        result = svc._prepare_skill_inputs(project, run)

        # Should not be overwritten
        assert result["04-cronograma"]["mobilizacao_policies"] == existing_policies

    def test_skill_inputs_override_merged_last(self):
        svc, project, audit, runtime = _make_svc()

        def read_json(path, default=None):
            if path == DEFAULT_PROJECT_FILES.skill_inputs:
                return {"01-escopo": {"area": 100}}
            return default if default is not None else {}

        project.read_json.side_effect = read_json

        run = {
            "use_saved_overrides": False,
            "skill_inputs_override": {"01-escopo": {"area": 999}},
            "use_mobilizacao_policy": False,
        }

        result = svc._prepare_skill_inputs(project, run)

        assert result["01-escopo"]["area"] == 999

    def test_empty_policies_dict_does_not_inject(self):
        svc, project, audit, runtime = _make_svc()

        def read_json(path, default=None):
            if path == DEFAULT_PROJECT_FILES.skill_inputs:
                return {}
            if path == DEFAULT_PROJECT_FILES.mobilizacao_policies:
                return {}  # empty → don't inject
            return default if default is not None else {}

        project.read_json.side_effect = read_json

        run = {
            "use_saved_overrides": True,
            "skill_inputs_override": {},
            "use_mobilizacao_policy": True,
        }

        result = svc._prepare_skill_inputs(project, run)

        assert "04-cronograma" not in result


# ─── TestReadRunProgress ──────────────────────────────────────────────────────


class TestReadRunProgress:
    """Covers lines 310-333: _read_run_progress."""

    def test_no_version_returns_empty(self):
        svc, project, audit, runtime = _make_svc()
        run = {"version": None, "run_id": "r1", "invocation_line_offset": 0}

        result = svc._read_run_progress(project, run)

        assert result == []

    def test_start_line_offset_skips_earlier_lines(self):
        svc, project, audit, runtime = _make_svc()
        lines = [
            json.dumps({"run_id": "r1", "skill": "01", "status": "OK", "duration_ms": 100}),
            json.dumps({"run_id": "r1", "skill": "02", "status": "OK", "duration_ms": 200}),
        ]
        project.read_lines.return_value = lines

        run = {"version": "v1", "run_id": "r1", "invocation_line_offset": 1}

        result = svc._read_run_progress(project, run)

        assert len(result) == 1
        assert result[0]["skill"] == "02"

    def test_invalid_json_line_skipped(self):
        svc, project, audit, runtime = _make_svc()
        lines = [
            "not valid json",
            json.dumps({"run_id": "r1", "skill": "02", "status": "OK", "duration_ms": 50}),
        ]
        project.read_lines.return_value = lines

        run = {"version": "v1", "run_id": "r1", "invocation_line_offset": 0}

        result = svc._read_run_progress(project, run)

        assert len(result) == 1
        assert result[0]["skill"] == "02"

    def test_run_id_mismatch_filtered_out(self):
        svc, project, audit, runtime = _make_svc()
        lines = [
            json.dumps({"run_id": "r999", "skill": "01", "status": "OK", "duration_ms": 10}),
            json.dumps({"run_id": "r1", "skill": "02", "status": "OK", "duration_ms": 20}),
        ]
        project.read_lines.return_value = lines

        run = {"version": "v1", "run_id": "r1", "invocation_line_offset": 0}

        result = svc._read_run_progress(project, run)

        assert len(result) == 1
        assert result[0]["skill"] == "02"

    def test_valid_matching_line_appended(self):
        svc, project, audit, runtime = _make_svc()
        lines = [
            json.dumps({
                "run_id": "r1",
                "skill": "05-bdi",
                "status": "OK",
                "duration_ms": 300,
                "error_kind": None,
                "avisos": ["aviso 1"],
            }),
        ]
        project.read_lines.return_value = lines

        run = {"version": "v1", "run_id": "r1", "invocation_line_offset": 0}

        result = svc._read_run_progress(project, run)

        assert len(result) == 1
        assert result[0]["skill"] == "05-bdi"
        assert result[0]["status"] == "OK"
        assert result[0]["duration_ms"] == 300
        assert result[0]["avisos"] == ["aviso 1"]


# ─── TestPersistResolvedCatalog ───────────────────────────────────────────────


class TestPersistResolvedCatalog:
    """Covers lines 371-449: _persist_resolved_catalog."""

    def _make_project_with_root(self, tmp_path: Path) -> MagicMock:
        project = _make_project_mock(tmp_path=tmp_path)
        version_dir = tmp_path / "project" / "v1"
        version_dir.mkdir(parents=True, exist_ok=True)
        return project

    def test_happy_path_writes_resolved_catalog_file(self, tmp_path):
        svc, project, audit, runtime = _make_svc(tmp_path=tmp_path)
        project = self._make_project_with_root(tmp_path)

        run_id = "run_persist01"
        run_data = [{"run_id": run_id, "use_strict_catalog_baseline": False}]

        def read_json(path, default=None):
            if path == DEFAULT_PROJECT_FILES.runs:
                return run_data
            if path == "benchmark_reference.json":
                return {}
            return default if default is not None else {}

        project.read_json.side_effect = read_json
        project.write_json.return_value = None

        # Runtime returns catalog data
        contexto = MagicMock()
        contexto.catalogo_id = "cat-1"
        contexto.jurisdicao_id = "jur-1"
        runtime.load_contexto.return_value = contexto

        resolved = {"cpus": [{"codigo": "CPU-A"}], "insumos": [], "producoes": []}
        provenance = {
            "catalogo_base_origem": "project_reference",
            "catalogo_base_hash": "hash123",
            "resolution_trace": {},
        }
        runtime._load_resolved_catalog_with_provenance.return_value = (resolved, provenance)

        canonical = MagicMock()
        canonical.eap = None
        project.load_canonical.return_value = canonical

        svc._persist_resolved_catalog(project, "v1", run_id, runtime)

        out_path = tmp_path / "project" / "v1" / "resolved_catalog.json"
        assert out_path.exists()
        data = json.loads(out_path.read_text("utf-8"))
        assert data["run_id"] == run_id
        assert data["version"] == "v1"
        assert data["catalogo_id"] == "cat-1"

    def test_eap_cpu_ids_filter_applied(self, tmp_path):
        svc, project, audit, runtime = _make_svc(tmp_path=tmp_path)
        project = self._make_project_with_root(tmp_path)

        run_id = "run_eap01"
        run_data = [{"run_id": run_id, "use_strict_catalog_baseline": False}]

        def read_json(path, default=None):
            if path == DEFAULT_PROJECT_FILES.runs:
                return run_data
            if path == "benchmark_reference.json":
                return {}
            return default if default is not None else {}

        project.read_json.side_effect = read_json
        project.write_json.return_value = None

        contexto = MagicMock()
        contexto.catalogo_id = "cat-1"
        contexto.jurisdicao_id = "jur-1"
        runtime.load_contexto.return_value = contexto

        # EAP with specific cpu_ids
        eap_item1 = MagicMock()
        eap_item1.cpu_id = "CPU-A"
        eap_item2 = MagicMock()
        eap_item2.cpu_id = "CPU-B"
        canonical = MagicMock()
        canonical.eap = [eap_item1, eap_item2]
        project.load_canonical.return_value = canonical

        resolved = {
            "cpus": [
                {"codigo": "CPU-A"},
                {"codigo": "CPU-C"},  # Not in EAP, should be filtered
            ],
            "insumos": [],
            "producoes": [],
        }
        provenance = {
            "catalogo_base_origem": "master",
            "catalogo_base_hash": None,
            "resolution_trace": {},
        }
        runtime._load_resolved_catalog_with_provenance.return_value = (resolved, provenance)

        svc._persist_resolved_catalog(project, "v1", run_id, runtime)

        out_path = tmp_path / "project" / "v1" / "resolved_catalog.json"
        data = json.loads(out_path.read_text("utf-8"))
        assert len(data["items"]["cpus"]) == 1
        assert data["items"]["cpus"][0]["codigo"] == "CPU-A"

    def test_runtime_exception_falls_back_to_project_catalog(self, tmp_path):
        svc, project, audit, runtime = _make_svc(tmp_path=tmp_path)
        project = self._make_project_with_root(tmp_path)

        run_id = "run_fallback01"
        project_catalog = {"cpus": [{"codigo": "CPU-LOCAL"}], "insumos": [], "producoes": []}
        run_data = [{"run_id": run_id, "use_strict_catalog_baseline": False}]

        def read_json(path, default=None):
            if path == DEFAULT_PROJECT_FILES.runs:
                return run_data
            if path == "benchmark_reference.json":
                return {"catalog": project_catalog}
            return default if default is not None else {}

        project.read_json.side_effect = read_json
        project.write_json.return_value = None

        # Runtime raises, triggering fallback
        runtime.load_contexto.side_effect = RuntimeError("runtime not available")

        svc._persist_resolved_catalog(project, "v1", run_id, runtime)

        out_path = tmp_path / "project" / "v1" / "resolved_catalog.json"
        assert out_path.exists()
        data = json.loads(out_path.read_text("utf-8"))
        assert data["catalogo_base_origem"] == "project_reference"
        assert data["items"]["cpus"] == [{"codigo": "CPU-LOCAL"}]

    def test_outer_exception_swallowed_silently(self, tmp_path):
        svc, project, audit, runtime = _make_svc(tmp_path=tmp_path)
        project = self._make_project_with_root(tmp_path)

        # Make project.root raise to force outer exception path
        project.root = MagicMock()
        project.root.__truediv__ = MagicMock(side_effect=Exception("disk error"))

        project.read_json.side_effect = Exception("can't read json")

        # Should not raise
        svc._persist_resolved_catalog(project, "v1", "run-x", runtime)

    def test_update_run_called_with_origin_and_hash(self, tmp_path):
        svc, project, audit, runtime = _make_svc(tmp_path=tmp_path)
        project = self._make_project_with_root(tmp_path)

        run_id = "run_update01"
        run_data = [{"run_id": run_id, "use_strict_catalog_baseline": False}]

        def read_json(path, default=None):
            if path == DEFAULT_PROJECT_FILES.runs:
                return list(run_data)
            if path == "benchmark_reference.json":
                return {}
            return default if default is not None else {}

        project.read_json.side_effect = read_json
        project.write_json.return_value = None

        contexto = MagicMock()
        contexto.catalogo_id = "cat-1"
        contexto.jurisdicao_id = "jur-1"
        runtime.load_contexto.return_value = contexto

        resolved = {"cpus": [], "insumos": [], "producoes": []}
        provenance = {
            "catalogo_base_origem": "master",
            "catalogo_base_hash": "abc",
            "resolution_trace": {},
        }
        runtime._load_resolved_catalog_with_provenance.return_value = (resolved, provenance)
        canonical = MagicMock()
        canonical.eap = None
        project.load_canonical.return_value = canonical

        update_calls = []
        original_update = svc._update_run

        def track_update(proj, rid, patch_data):
            update_calls.append(dict(patch_data))
            return original_update(proj, rid, patch_data)

        svc._update_run = track_update

        svc._persist_resolved_catalog(project, "v1", run_id, runtime)

        # Last update call should include catalogo_base_origem and catalogo_base_hash
        last_update = update_calls[-1]
        assert "catalogo_base_origem" in last_update
        assert "catalogo_base_hash" in last_update


# ─── TestStaticMethods ────────────────────────────────────────────────────────


class TestStaticMethods:
    """Covers lines 452-459: _load_json_from_line and _now_iso."""

    def test_load_json_from_line_parses_valid_json(self):
        line = '{"run_id": "r1", "skill": "01", "status": "OK"}'
        result = PipelineService._load_json_from_line(line)
        assert result == {"run_id": "r1", "skill": "01", "status": "OK"}

    def test_load_json_from_line_raises_on_invalid_json(self):
        with pytest.raises(json.JSONDecodeError):
            PipelineService._load_json_from_line("not json at all")

    def test_now_iso_returns_utc_iso_string(self):
        result = PipelineService._now_iso()
        assert isinstance(result, str)
        # UTC offset should be present (+00:00)
        assert "+00:00" in result or "Z" in result

    def test_now_iso_has_date_structure(self):
        result = PipelineService._now_iso()
        # Should be parseable
        from datetime import datetime
        dt = datetime.fromisoformat(result)
        assert dt.year >= 2024


# ─── TestCreateRun ────────────────────────────────────────────────────────────


class TestCreateRun:
    """Covers lines 176-206: _create_run."""

    def test_creates_run_with_all_fields(self):
        svc, project, audit, runtime = _make_svc()
        write_store = {"data": None}

        def read_json(path, default=None):
            if path == DEFAULT_PROJECT_FILES.runs:
                return []
            return default if default is not None else {}

        def write_json(path, data):
            if path == DEFAULT_PROJECT_FILES.runs:
                write_store["data"] = data

        project.read_json.side_effect = read_json
        project.write_json.side_effect = write_json

        run_id = svc._create_run(
            project,
            base_version="v1",
            fork_version=True,
            skill_inputs_override={"k": "v"},
            use_saved_overrides=True,
            use_mobilizacao_policy=False,
            use_strict_catalog_baseline=True,
            actor="test-actor",
            mode="sync",
        )

        assert run_id.startswith("run_")
        assert write_store["data"] is not None
        run = write_store["data"][0]
        assert run["run_id"] == run_id
        assert run["status"] == "PENDING"
        assert run["mode"] == "sync"
        assert run["actor"] == "test-actor"
        assert run["base_version"] == "v1"
        assert run["fork_version"] is True
        assert run["use_strict_catalog_baseline"] is True

    def test_non_list_runs_replaced_with_empty(self):
        svc, project, audit, runtime = _make_svc()
        write_store = {"data": None}

        def read_json(path, default=None):
            if path == DEFAULT_PROJECT_FILES.runs:
                return "corrupted"  # not a list
            return default if default is not None else {}

        def write_json(path, data):
            if path == DEFAULT_PROJECT_FILES.runs:
                write_store["data"] = data

        project.read_json.side_effect = read_json
        project.write_json.side_effect = write_json

        run_id = svc._create_run(
            project,
            base_version=None,
            fork_version=False,
            skill_inputs_override={},
            use_saved_overrides=False,
            use_mobilizacao_policy=False,
            use_strict_catalog_baseline=False,
            actor="sys",
            mode="async",
        )

        # Should have created a new list with just the new run
        assert len(write_store["data"]) == 1
        assert write_store["data"][0]["run_id"] == run_id


# ─── TestFindRun ─────────────────────────────────────────────────────────────


class TestFindRun:
    """Covers lines 336-342: _find_run."""

    def test_returns_run_when_found(self):
        svc, project, audit, runtime = _make_svc()
        run_data = {"run_id": "r42", "status": "OK"}
        project.read_json.return_value = [run_data, {"run_id": "r99", "status": "PENDING"}]

        result = svc._find_run(project, "r42")

        assert result["run_id"] == "r42"

    def test_returns_none_when_not_found(self):
        svc, project, audit, runtime = _make_svc()
        project.read_json.return_value = [{"run_id": "r999"}]

        result = svc._find_run(project, "r-missing")

        assert result is None

    def test_returns_none_when_not_list(self):
        svc, project, audit, runtime = _make_svc()
        project.read_json.return_value = {"not": "a list"}

        result = svc._find_run(project, "any-id")

        assert result is None


# ─── TestUpdateRun ────────────────────────────────────────────────────────────


class TestUpdateRun:
    """Covers lines 345-356: _update_run."""

    def test_updates_matching_run(self):
        svc, project, audit, runtime = _make_svc()
        run_data = [
            {"run_id": "r1", "status": "PENDING"},
            {"run_id": "r2", "status": "OK"},
        ]
        write_store = {"data": list(run_data)}

        def read_json(path, default=None):
            if path == DEFAULT_PROJECT_FILES.runs:
                return list(write_store["data"])
            return default if default is not None else {}

        def write_json(path, data):
            if path == DEFAULT_PROJECT_FILES.runs:
                write_store["data"] = list(data)

        project.read_json.side_effect = read_json
        project.write_json.side_effect = write_json

        svc._update_run(project, "r1", {"status": "RUNNING", "started_at": "2024-01-01"})

        updated = next(r for r in write_store["data"] if r["run_id"] == "r1")
        assert updated["status"] == "RUNNING"
        assert updated["started_at"] == "2024-01-01"
        # r2 unchanged
        r2 = next(r for r in write_store["data"] if r["run_id"] == "r2")
        assert r2["status"] == "OK"

    def test_non_list_runs_is_reset(self):
        svc, project, audit, runtime = _make_svc()

        def read_json(path, default=None):
            if path == DEFAULT_PROJECT_FILES.runs:
                return "broken"
            return default if default is not None else {}

        project.read_json.side_effect = read_json

        # Should not raise, just noop since run_id won't be found
        svc._update_run(project, "r1", {"status": "RUNNING"})
