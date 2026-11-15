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

    # N9.1 (#206): the project's exact BDI declaration — the only project BDI the exact price reads.

    def _project_bdi_profile(self, project: Any) -> tuple[str | None, dict[str, Any] | None, str | None]:
        from concilium.application.runtime import Runtime
        from concilium.application.scheduling.project_bdi_exact_status import load_project_profile

        return load_project_profile(Runtime(self.config_root), project.meta)

    def get_project_bdi_exato(self, project_id: str) -> dict[str, Any]:
        """Status of the saved exact declaration and the effective layers per category."""
        from concilium.application.scheduling.project_bdi_exact_status import exact_project_bdi_status

        project = self._dependencies.repository.get_project(project_id)
        perfil_id, perfil, motivo = self._project_bdi_profile(project)
        return exact_project_bdi_status(project, perfil, perfil_id=perfil_id, perfil_motivo=motivo)

    def save_project_bdi_exato(
        self,
        project_id: str,
        declaracao: dict[str, Any],
        *,
        confirmado_por: str,
        motivo_revisao: str | None,
        actor: str = "system",
    ) -> dict[str, Any]:
        """Validate (merged over the profile rows when known) and save a new version.

        Raises ``ProjectBdiExactError`` with the reason; nothing is written then.
        """
        from concilium.application.scheduling.project_bdi_exact_status import (
            exact_project_bdi_status,
            profile_rows_for_validation,
        )
        from concilium.application.scheduling.project_bdi_exact_store import save_exact_project_bdi

        project = self._dependencies.repository.get_project(project_id)
        perfil_id, perfil, motivo = self._project_bdi_profile(project)
        salvo = save_exact_project_bdi(
            project,
            project_id,
            declaracao,
            confirmado_por=confirmado_por,
            motivo_revisao=motivo_revisao,
            profile_rows=profile_rows_for_validation(perfil),
        )
        self._dependencies.audit_service.log(
            project,
            action="save_project_bdi_exato",
            actor=actor,
            payload={"confirmado_por": confirmado_por, "motivo_revisao": motivo_revisao},
            result={"versao": salvo["versao"], "content_hash": salvo["content_hash"]},
        )
        return {
            "salvo": {key: salvo[key] for key in ("versao", "content_hash", "confirmado_em", "diff") if key in salvo},
            "status": exact_project_bdi_status(project, perfil, perfil_id=perfil_id, perfil_motivo=motivo),
        }

