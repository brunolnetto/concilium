from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime
from threading import RLock
from typing import Any
from uuid import uuid4

from concilium.application.pipeline_strategy import get_pipeline_strategy
from concilium.application.skills.phase_classifier import get_pipeline_profile_for_intent, normalize_procurement_intent

from .project.audit_service import AuditService
from .project.project_files import DEFAULT_PROJECT_FILES, ProjectFiles
from .project.project_repository import ProjectHandle, ProjectRepository
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
        procurement_intent: str | None = None,
        skill_inputs_override: dict[str, dict[str, Any]],
        use_saved_overrides: bool,
        use_mobilizacao_policy: bool,
        use_strict_catalog_baseline: bool,
        actor: str = "system",
    ) -> dict[str, Any]:
        project = self._repository.get_project(project_id)
        run_id = self._create_run(
            project,
            base_version=base_version,
            fork_version=fork_version,
            procurement_intent=procurement_intent,
            skill_inputs_override=skill_inputs_override,
            use_saved_overrides=use_saved_overrides,
            use_mobilizacao_policy=use_mobilizacao_policy,
            use_strict_catalog_baseline=use_strict_catalog_baseline,
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
                "procurement_intent": normalize_procurement_intent(procurement_intent).value,
                "use_saved_overrides": use_saved_overrides,
                "use_mobilizacao_policy": use_mobilizacao_policy,
                "use_strict_catalog_baseline": use_strict_catalog_baseline,
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
        procurement_intent: str | None = None,
        skill_inputs_override: dict[str, dict[str, Any]],
        use_saved_overrides: bool,
        use_mobilizacao_policy: bool,
        use_strict_catalog_baseline: bool,
        actor: str = "system",
    ) -> dict[str, Any]:
        project = self._repository.get_project(project_id)
        run_id = self._create_run(
            project,
            base_version=base_version,
            fork_version=fork_version,
            procurement_intent=procurement_intent,
            skill_inputs_override=skill_inputs_override,
            use_saved_overrides=use_saved_overrides,
            use_mobilizacao_policy=use_mobilizacao_policy,
            use_strict_catalog_baseline=use_strict_catalog_baseline,
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
                "procurement_intent": normalize_procurement_intent(procurement_intent).value,
                "use_saved_overrides": use_saved_overrides,
                "use_mobilizacao_policy": use_mobilizacao_policy,
                "use_strict_catalog_baseline": use_strict_catalog_baseline,
            },
            result=payload,
        )
        return payload

    def list_runs(self, project_id: str) -> list[dict[str, Any]]:
        project = self._repository.get_project(project_id)
        raw_runs = project.read_json(self._files.runs, [])
        if not isinstance(raw_runs, list):
            return []
        runs: list[dict[str, Any]] = [r for r in raw_runs if isinstance(r, dict)]
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
            "procurement_intent": run.get("procurement_intent", "rfi"),
            "requested_at": run.get("requested_at"),
            "started_at": run.get("started_at"),
            "finished_at": run.get("finished_at"),
            "base_version": run.get("base_version"),
            "version": run.get("version"),
            "fork_version": run.get("fork_version", False),
            "use_mobilizacao_policy": run.get("use_mobilizacao_policy", True),
            "use_strict_catalog_baseline": run.get("use_strict_catalog_baseline", False),
            "catalogo_base_origem": run.get("catalogo_base_origem"),
            "catalogo_base_hash": run.get("catalogo_base_hash"),
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
        procurement_intent: str | None = None,
        skill_inputs_override: dict[str, dict[str, Any]],
        use_saved_overrides: bool,
        use_mobilizacao_policy: bool,
        use_strict_catalog_baseline: bool,
        actor: str,
        mode: str,
    ) -> str:
        run_id = f"run_{uuid4().hex[:12]}"
        intent = normalize_procurement_intent(procurement_intent)
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
            "procurement_intent": intent.value,
            "use_saved_overrides": use_saved_overrides,
            "use_mobilizacao_policy": use_mobilizacao_policy,
            "use_strict_catalog_baseline": use_strict_catalog_baseline,
            "catalogo_base_origem": None,
            "catalogo_base_hash": None,
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

    def _prepare_skill_inputs(self, project, run: dict) -> dict:
        skill_inputs = project.read_json(self._files.skill_inputs, {})
        if run.get("use_saved_overrides"):
            saved_overrides = project.read_json(self._files.overrides, {})
            skill_inputs = deep_merge(skill_inputs, saved_overrides)
        skill_inputs_override = run.get("skill_inputs_override") or {}
        skill_inputs = deep_merge(skill_inputs, skill_inputs_override)
        use_wmp = bool(run.get("use_mobilizacao_policy", True))
        if use_wmp and run.get("use_saved_overrides", True):
            policies = project.read_json(self._files.mobilizacao_policies, {})
            if policies:
                skill04 = skill_inputs.setdefault("04-cronograma", {})
                if "mobilizacao_policies" not in skill04:
                    skill04["mobilizacao_policies"] = policies
        return skill_inputs

    @staticmethod
    def _resolve_actor_context(run: dict[str, Any]) -> tuple[str, str | None, Any]:
        """Captura identidade do ator via contextvars (ADR-118) para a execução do run."""
        # ADR-119 D3: captura identidade do ator via contextvars (ADR-118)
        from concilium.infrastructure.auth.permission_guard import (
            _current_roles,
            get_current_user_id,
        )

        actor_user_id = get_current_user_id() or run.get("actor") or "system"
        actor_roles = list(_current_roles.get())
        actor_role = actor_roles[0] if actor_roles else None
        intent = run.get("procurement_intent")
        return actor_user_id, actor_role, intent

    def _ensure_run_version(
        self,
        project: ProjectHandle,
        run: dict[str, Any],
        actor_user_id: str,
        actor_role: str | None,
        intent: Any,
    ) -> str:
        """Garante que o projeto tenha uma versão corrente (criando/forkando se necessário)."""
        if project.current_version() is None:
            project.new_version(
                criado_por=actor_user_id,
                role_criador=actor_role,
                procurement_intent=intent,
            )

        base_version = run.get("base_version")
        if run.get("fork_version"):
            project.new_version(
                base=base_version or project.current_version(),
                criado_por=actor_user_id,
                role_criador=actor_role,
                procurement_intent=intent,
                forked_from=base_version or project.current_version(),
            )

        version = project.current_version()
        if version is None:
            raise RuntimeError("Falha ao resolver versao para execucao.")
        return version

    @staticmethod
    def _resolve_catalog_baseline_origin(project: ProjectHandle, run: dict[str, Any]) -> str:
        """Resolve a origem do baseline de catálogo, validando o modo estrito quando aplicável.

        Deve ocorrer antes do pipeline para que falhas de strict_baseline reprovem o run,
        não o passo de persistência pós-run (que engoliria o erro silenciosamente).
        """
        use_strict_catalog_baseline = bool(run.get("use_strict_catalog_baseline", False))
        benchmark_ref = project.read_json("benchmark_reference.json", {})
        project_catalog = benchmark_ref.get("catalog") if isinstance(benchmark_ref, dict) else None
        has_project_catalog = isinstance(project_catalog, dict) and bool(project_catalog)
        if use_strict_catalog_baseline and not has_project_catalog:
            raise RuntimeError("Baseline de catalogo do projeto nao encontrado")
        return "project_reference" if has_project_catalog else "master"

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
            _actor_user_id, _actor_role, _intent = self._resolve_actor_context(run)
            version = self._ensure_run_version(project, run, _actor_user_id, _actor_role, _intent)

            line_offset = len(project.read_lines(f"{version}/invocations.log"))
            self._update_run(project, run_id, {"version": version, "invocation_line_offset": line_offset})

            catalogo_base_origem = self._resolve_catalog_baseline_origin(project, run)
            self._update_run(project, run_id, {"catalogo_base_origem": catalogo_base_origem})

            skill_inputs = self._prepare_skill_inputs(project, run)

            # ADR-063 §D6: validate preconditions per project type
            strategy = get_pipeline_strategy(project)
            strategy.validate_preconditions(project)

            # Linguagem RFX nativa no core: caminho (skills) definido por intent.
            profile = get_pipeline_profile_for_intent(run.get("procurement_intent", "rfi"))

            runtime = self._runtime_factory()
            skills_log = runtime.run_pipeline(
                project,
                skill_inputs,
                invocation_context={"run_id": run_id},
                skill_sequence=profile.skill_sequence or strategy.skill_sequence(),
            )
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
                    "path_name": profile.path_name,
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

    def _resolve_catalog_via_runtime(
        self,
        project: ProjectHandle,
        version: str,
        run_id: str,
        run: dict[str, Any],
        runtime: Any,
    ) -> dict[str, Any]:
        """Resolve o catálogo compacto via runtime (caminho de produção)."""
        contexto = runtime.load_contexto(project.meta["contexto_id"])
        use_strict_catalog_baseline = bool(run.get("use_strict_catalog_baseline", False))
        canonical = project.load_canonical(version)
        eap_cpu_ids: set[str] | None = None
        if canonical and canonical.eap:
            eap_cpu_ids = {item.cpu_id for item in canonical.eap if item.cpu_id}

        resolved, provenance = runtime._load_resolved_catalog_with_provenance(
            contexto.catalogo_id,
            contexto.jurisdicao_id,
            project,
            version,
            strict_baseline=use_strict_catalog_baseline,
        )
        if eap_cpu_ids is not None:
            resolved["cpus"] = [c for c in resolved.get("cpus", []) if c.get("codigo") in eap_cpu_ids]

        return {
            "run_id": run_id,
            "version": version,
            "catalogo_id": contexto.catalogo_id,
            "jurisdicao_id": contexto.jurisdicao_id,
            "resolved_at": self._now_iso(),
            "catalogo_base_origem": provenance.get("catalogo_base_origem"),
            "catalogo_base_hash": provenance.get("catalogo_base_hash"),
            "use_strict_catalog_baseline": use_strict_catalog_baseline,
            "resolution_trace": provenance.get("resolution_trace", {}),
            "items": {
                "cpus": resolved.get("cpus", []),
                "insumos": resolved.get("insumos", []),
                "producoes": resolved.get("producoes", []),
            },
        }

    def _resolve_catalog_fallback(
        self,
        version: str,
        run_id: str,
        project_catalog: Any,
        catalogo_base_origem_local: str,
    ) -> dict[str, Any]:
        """Fallback: usa o catálogo local do projeto (ex.: ambientes de teste sem runtime)."""
        catalog = (
            project_catalog
            if isinstance(project_catalog, dict) and project_catalog
            else {"cpus": [], "insumos": [], "producoes": []}
        )
        return {
            "run_id": run_id,
            "version": version,
            "resolved_at": self._now_iso(),
            "catalogo_base_origem": catalogo_base_origem_local,
            "catalogo_base_hash": None,
            "items": {
                "cpus": catalog.get("cpus", []),
                "insumos": catalog.get("insumos", []),
                "producoes": catalog.get("producoes", []),
            },
        }

    def _persist_resolved_catalog(
        self,
        project: ProjectHandle,
        version: str,
        run_id: str,
        runtime: Any,
    ) -> None:
        """ADR-066 §F4: persist compact resolved catalog for run immutability.

        Tries to resolve via runtime first; falls back to project-local
        benchmark_reference.catalog so the file is always written even in
        test environments where the runtime does not implement catalog methods.
        """
        try:
            run = self._find_run(project, run_id) or {}

            # Determine project catalog baseline from local file (no runtime needed)
            benchmark_ref = project.read_json("benchmark_reference.json", {})
            _project_catalog = benchmark_ref.get("catalog") if isinstance(benchmark_ref, dict) else None
            _has_project_catalog = isinstance(_project_catalog, dict) and bool(_project_catalog)
            catalogo_base_origem_local = "project_reference" if _has_project_catalog else "master"

            try:
                payload = self._resolve_catalog_via_runtime(project, version, run_id, run, runtime)
            except Exception:
                # Fallback: use project-local catalog (e.g. test environments without
                # runtime catalog support, or contexts where contexto is unavailable)
                payload = self._resolve_catalog_fallback(version, run_id, _project_catalog, catalogo_base_origem_local)

            project.write_json(f"{version}/resolved_catalog.json", payload)
            self._update_run(
                project,
                run_id,
                {
                    "catalogo_base_origem": payload.get("catalogo_base_origem"),
                    "catalogo_base_hash": payload.get("catalogo_base_hash"),
                },
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
