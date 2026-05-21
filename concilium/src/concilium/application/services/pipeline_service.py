from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime
from threading import RLock
from typing import Any
from uuid import uuid4

from concilium.application.pipeline_strategy import get_pipeline_strategy

from .audit_service import AuditService
from .project_files import DEFAULT_PROJECT_FILES, ProjectFiles
from .project_repository import ProjectHandle, ProjectRepository
from .service_support import build_summary, deep_merge


class PipelineService:
    def __init__(
        self,
        repository: ProjectRepository,
        audit_service: AuditService,
        runtime_factory,
        files: ProjectFiles = DEFAULT_PROJECT_FILES,
    ):
        self._repository = repository
        self._audit_service = audit_service
        self._runtime_factory = runtime_factory
        self._files = files
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="concilium-prototype")
        self._lock = RLock()
        self._futures: dict[str, Future[None]] = {}

    def run_project(
        self,
        project_id: str,
        *,
        base_version: str | None,
        fork_version: bool,
        skill_inputs_override: dict[str, dict[str, Any]],
        use_saved_overrides: bool,
        actor: str = "system",
    ) -> dict[str, Any]:
        project = self._repository.get_project(project_id)
        run_id = self._create_run(
            project,
            base_version=base_version,
            fork_version=fork_version,
            skill_inputs_override=skill_inputs_override,
            use_saved_overrides=use_saved_overrides,
            actor=actor,
            mode="sync",
        )
        self._execute_run(project, run_id)
        payload = self.get_run(project_id, run_id)
        self._audit_service.log(
            project,
            action="run_project_sync",
            actor=actor,
            payload={
                "run_id": run_id,
                "base_version": base_version,
                "fork_version": fork_version,
                "use_saved_overrides": use_saved_overrides,
            },
            result={"status": payload.get("status"), "version": payload.get("version")},
        )
        return payload

    def start_run_project(
        self,
        project_id: str,
        *,
        base_version: str | None,
        fork_version: bool,
        skill_inputs_override: dict[str, dict[str, Any]],
        use_saved_overrides: bool,
        actor: str = "system",
    ) -> dict[str, Any]:
        project = self._repository.get_project(project_id)
        run_id = self._create_run(
            project,
            base_version=base_version,
            fork_version=fork_version,
            skill_inputs_override=skill_inputs_override,
            use_saved_overrides=use_saved_overrides,
            actor=actor,
            mode="async",
        )
        future = self._executor.submit(self._execute_run, project, run_id)
        with self._lock:
            self._futures[run_id] = future

        payload = {
            "project_id": project_id,
            "run_id": run_id,
            "status": "PENDING",
        }
        self._audit_service.log(
            project,
            action="start_run_project",
            actor=actor,
            payload={
                "run_id": run_id,
                "base_version": base_version,
                "fork_version": fork_version,
                "use_saved_overrides": use_saved_overrides,
            },
            result=payload,
        )
        return payload

    def list_runs(self, project_id: str) -> list[dict[str, Any]]:
        project = self._repository.get_project(project_id)
        runs = project.read_json(self._files.runs, [])
        if not isinstance(runs, list):
            return []
        return sorted(runs, key=lambda item: item.get("requested_at", ""), reverse=True)

    def get_run(self, project_id: str, run_id: str) -> dict[str, Any]:
        project = self._repository.get_project(project_id)
        runs = project.read_json(self._files.runs, [])
        if not isinstance(runs, list):
            raise FileNotFoundError(f"Run '{run_id}' nao encontrado.")

        run = next((item for item in runs if item.get("run_id") == run_id), None)
        if run is None:
            raise FileNotFoundError(f"Run '{run_id}' nao encontrado.")

        progress = self._read_run_progress(project, run)
        return {
            "project_id": project_id,
            "run_id": run_id,
            "status": run.get("status"),
            "requested_at": run.get("requested_at"),
            "started_at": run.get("started_at"),
            "finished_at": run.get("finished_at"),
            "base_version": run.get("base_version"),
            "version": run.get("version"),
            "fork_version": run.get("fork_version", False),
            "skills_log": run.get("skills_log", []),
            "skills_progress": progress,
            "summary": run.get("summary", {}),
            "output_files": run.get("output_files", []),
            "error": run.get("error"),
        }

    def _create_run(
        self,
        project: ProjectHandle,
        *,
        base_version: str | None,
        fork_version: bool,
        skill_inputs_override: dict[str, dict[str, Any]],
        use_saved_overrides: bool,
        actor: str,
        mode: str,
    ) -> str:
        run_id = f"run_{uuid4().hex[:12]}"
        run = {  # type: ignore[var-annotated]
            "run_id": run_id,
            "project_id": project.meta.get("id"),
            "requested_at": self._now_iso(),
            "started_at": None,
            "finished_at": None,
            "status": "PENDING",
            "mode": mode,
            "actor": actor,
            "base_version": base_version,
            "version": None,
            "fork_version": fork_version,
            "use_saved_overrides": use_saved_overrides,
            "skill_inputs_override": skill_inputs_override,
            "skills_log": [],
            "summary": {},
            "output_files": [],
            "error": None,
        }
        with self._lock:
            runs = project.read_json(self._files.runs, [])
            if not isinstance(runs, list):
                runs = []
            runs.append(run)
            project.write_json(self._files.runs, runs)
        return run_id

    def _execute_run(self, project: ProjectHandle, run_id: str) -> None:
        run = self._find_run(project, run_id)
        if run is None:
            return

        self._update_run(
            project,
            run_id,
            {
                "status": "RUNNING",
                "started_at": self._now_iso(),
            },
        )
        try:
            if project.current_version() is None:
                project.new_version()

            base_version = run.get("base_version")
            if run.get("fork_version"):
                project.new_version(base=base_version or project.current_version())

            version = project.current_version()
            if version is None:
                raise RuntimeError("Falha ao resolver versao para execucao.")

            line_offset = len(project.read_lines(f"{version}/invocations.log"))
            self._update_run(project, run_id, {"version": version, "invocation_line_offset": line_offset})

            skill_inputs = project.read_json(self._files.skill_inputs, {})
            if run.get("use_saved_overrides"):
                saved_overrides = project.read_json(self._files.overrides, {})
                skill_inputs = deep_merge(skill_inputs, saved_overrides)

            skill_inputs_override = run.get("skill_inputs_override") or {}
            skill_inputs = deep_merge(skill_inputs, skill_inputs_override)

            # ADR-054 §9.1: inject saved mobilization policies into Skill 04 inputs.
            # use_mobilizacao_policy=False lets planners revert to explicit allocation.
            # Explicit skill_inputs_override["04-cronograma"]["mobilizacao_policies"] always wins.
            use_wmp = run.get("use_mobilizacao_policy", True)
            if use_wmp and run.get("use_saved_overrides", True):
                policies = project.read_json(self._files.mobilizacao_policies, {})
                if policies:
                    skill04 = skill_inputs.setdefault("04-cronograma", {})
                    if "mobilizacao_policies" not in skill04:
                        skill04["mobilizacao_policies"] = policies

            # ADR-063 §D6: validate preconditions per project type
            strategy = get_pipeline_strategy(project)
            strategy.validate_preconditions(project)

            runtime = self._runtime_factory()
            skills_log = runtime.run_pipeline(project, skill_inputs, invocation_context={"run_id": run_id})
            canonical = project.load_canonical(version)
            has_errors = any(item.get("status") in ("ERRO", "EXCEPTION") for item in skills_log)

            # ADR-066 §F4: persist compact resolved catalog for run immutability
            self._persist_resolved_catalog(project, version, run_id, runtime)

            self._update_run(
                project,
                run_id,
                {
                    "status": "ERRO" if has_errors else "OK",
                    "finished_at": self._now_iso(),
                    "skills_log": skills_log,
                    "summary": build_summary(canonical),
                    "output_files": project.list_output_files(version),
                    "error": None,
                },
            )
        except Exception as exc:
            self._update_run(
                project,
                run_id,
                {
                    "status": "EXCEPTION",
                    "finished_at": self._now_iso(),
                    "error": str(exc),
                },
            )
        finally:
            with self._lock:
                self._futures.pop(run_id, None)

    def _read_run_progress(self, project: ProjectHandle, run: dict[str, Any]) -> list[dict[str, Any]]:
        version = run.get("version")
        if not version:
            return []

        start_line = int(run.get("invocation_line_offset") or 0)
        rows = project.read_lines(f"{version}/invocations.log")
        progress: list[dict[str, Any]] = []
        for line in rows[start_line:]:
            try:
                item = self._load_json_from_line(line)
            except Exception:
                continue
            if item.get("run_id") != run.get("run_id"):
                continue
            progress.append(
                {
                    "skill": item.get("skill"),
                    "status": item.get("status"),
                    "duration_ms": item.get("duration_ms"),
                    "error_kind": item.get("error_kind"),
                    "avisos": item.get("avisos") or [],
                }
            )
        return progress

    def _find_run(self, project: ProjectHandle, run_id: str) -> dict[str, Any] | None:
        runs = project.read_json(self._files.runs, [])
        if not isinstance(runs, list):
            return None
        for run in runs:
            if run.get("run_id") == run_id:
                return run
        return None

    def _update_run(self, project: ProjectHandle, run_id: str, patch: dict[str, Any]) -> None:
        with self._lock:
            runs = project.read_json(self._files.runs, [])
            if not isinstance(runs, list):
                runs = []
            for index, run in enumerate(runs):
                if run.get("run_id") != run_id:
                    continue
                updated = dict(run)
                updated.update(patch)
                runs[index] = updated
                project.write_json(self._files.runs, runs)
                return

    def _persist_resolved_catalog(
        self,
        project: ProjectHandle,
        version: str,
        run_id: str,
        runtime: Any,
    ) -> None:
        """ADR-066 §F4: persist compact resolved catalog for run immutability."""
        try:
            import json as _json

            from concilium.application.services.catalog_resolver import CatalogResolver

            contexto = runtime.load_contexto(project.meta["contexto_id"])
            master = runtime.load_catalogo(contexto.catalogo_id)
            resolver = CatalogResolver(runtime.config_root)

            # Filter to only CPU IDs used in the canonical (EAP items)
            canonical = project.load_canonical(version)
            eap_cpu_ids: set[str] | None = None
            if canonical and canonical.eap:
                eap_cpu_ids = {item.cpu_id for item in canonical.eap if item.cpu_id}

            resolved, trace = resolver.build_resolved_catalog(master, project, contexto.jurisdicao_id, eap_cpu_ids)

            payload = {
                "run_id": run_id,
                "version": version,
                "catalogo_id": contexto.catalogo_id,
                "jurisdicao_id": contexto.jurisdicao_id,
                "resolved_at": self._now_iso(),
                "resolution_trace": trace.to_dict(),
                "items": {
                    "cpus": resolved.get("cpus", []),
                    "insumos": resolved.get("insumos", []),
                    "producoes": resolved.get("producoes", []),
                },
            }

            out_path = project.root / version / "resolved_catalog.json"
            out_path.write_text(
                _json.dumps(payload, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        except Exception:
            pass  # best-effort: run must not fail because of resolved_catalog persistence

    @staticmethod
    def _load_json_from_line(line: str) -> dict[str, Any]:
        import json

        return json.loads(line)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()
