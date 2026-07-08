"""ConciliumService — parte extraída de concilium_service.py (mixin _RunVersionMixin)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._host_protocol import ConciliumServiceHost

    _Base = ConciliumServiceHost
else:
    _Base = object


class _RunVersionMixin(_Base):
    """Métodos de run_version de ConciliumService."""

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
        return self._dependencies.pipeline_service.run_project(
            project_id,
            base_version=base_version,
            fork_version=fork_version,
            procurement_intent=procurement_intent,
            skill_inputs_override=skill_inputs_override,
            use_saved_overrides=use_saved_overrides,
            use_mobilizacao_policy=use_mobilizacao_policy,
            use_strict_catalog_baseline=use_strict_catalog_baseline,
            actor=actor,
        )

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
        return self._dependencies.pipeline_service.start_run_project(
            project_id,
            base_version=base_version,
            fork_version=fork_version,
            procurement_intent=procurement_intent,
            skill_inputs_override=skill_inputs_override,
            use_saved_overrides=use_saved_overrides,
            use_mobilizacao_policy=use_mobilizacao_policy,
            use_strict_catalog_baseline=use_strict_catalog_baseline,
            actor=actor,
        )

    def list_runs(self, project_id: str) -> list[dict[str, Any]]:
        return self._dependencies.pipeline_service.list_runs(project_id)

    def get_run(self, project_id: str, run_id: str) -> dict[str, Any]:
        return self._dependencies.pipeline_service.get_run(project_id, run_id)

    def list_versions(self, project_id: str) -> list[str]:
        return self._dependencies.project_service.list_versions(project_id)

    def get_version_history(self, project_id: str) -> dict:
        """ADR-119 D3: metadados de autoria de todas as versões."""
        return self._dependencies.project_service.get_version_history(project_id)

    def delete_version(self, project_id: str, version: str, actor: str = "system") -> dict[str, Any]:
        return self._dependencies.project_service.delete_version(project_id, version, actor=actor)

    def compare_versions(self, project_id: str, left_version: str, right_version: str) -> dict[str, Any]:
        return self._dependencies.project_service.compare_versions(project_id, left_version, right_version)

    def fork_version(self, project_id: str, base_version: str, actor: str = "system") -> dict[str, Any]:
        return self._dependencies.project_service.fork_version(project_id, base_version, actor=actor)

    def resolve_run_base_version(self, project_id: str, run_id: str) -> str:
        run = self.get_run(project_id, run_id)
        version = run.get("version")
        if not version:
            raise ValueError(f"Run '{run_id}' ainda não possui versão resolvida.")
        return str(version)

    def list_audit(self, project_id: str, limit: int = 200) -> list[dict[str, Any]]:
        project = self._dependencies.repository.get_project(project_id)
        return self._dependencies.audit_service.list(project, limit=limit)

    def list_overrides(self, project_id: str) -> dict[str, Any]:
        return self._dependencies.override_service.list_overrides(project_id)

    def upsert_override(
        self, project_id: str, skill_id: str, inputs: dict[str, Any], actor: str = "system"
    ) -> dict[str, Any]:
        return self._dependencies.override_service.upsert_override(project_id, skill_id, inputs, actor=actor)

    def delete_override(self, project_id: str, skill_id: str, actor: str = "system") -> dict[str, Any]:
        return self._dependencies.override_service.delete_override(project_id, skill_id, actor=actor)

