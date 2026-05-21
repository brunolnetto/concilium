from __future__ import annotations

from typing import Any

from .audit_service import AuditService
from .project_files import DEFAULT_DELIVERABLES, DEFAULT_PROJECT_FILES, ProjectFiles
from .project_repository import ProjectRepository
from .service_support import deep_merge


class OverrideService:
    def __init__(
        self, repository: ProjectRepository, audit_service: AuditService, files: ProjectFiles = DEFAULT_PROJECT_FILES
    ):
        self._repository = repository
        self._audit_service = audit_service
        self._files = files

    def extend_cpu(self, project_id: str, cpu_id: str, cpu_data: dict, actor: str = "system", motivo: str = "") -> None:
        project = self._repository.get_project(project_id)
        project.extend_cpu(cpu_id, cpu_data, actor=actor, motivo=motivo)
        self._audit_service.log(
            project,
            action="extend_cpu",
            actor=actor,
            payload={"cpu_id": cpu_id, "motivo": motivo},
            result={"status": "ok"},
        )

    def resolve_cpu(self, project_id: str, cpu_id: str) -> dict | None:
        return self._repository.get_project(project_id).resolve_cpu(cpu_id)

    def list_overrides(self, project_id: str) -> dict[str, Any]:
        project = self._repository.get_project(project_id)
        return project.read_json(self._files.overrides, {})

    def upsert_override(
        self, project_id: str, skill_id: str, inputs: dict[str, Any], actor: str = "system"
    ) -> dict[str, Any]:
        project = self._repository.get_project(project_id)
        overrides = project.read_json(self._files.overrides, {})
        overrides.setdefault(skill_id, {})
        overrides[skill_id] = deep_merge(overrides[skill_id], inputs)
        project.write_json(self._files.overrides, overrides)
        self._audit_service.log(
            project,
            action="upsert_override",
            actor=actor,
            payload={"skill_id": skill_id, "inputs": inputs},
            result={"skills": list(overrides.keys())},
        )
        return overrides

    def delete_override(self, project_id: str, skill_id: str, actor: str = "system") -> dict[str, Any]:
        project = self._repository.get_project(project_id)
        overrides = project.read_json(self._files.overrides, {})
        overrides.pop(skill_id, None)
        project.write_json(self._files.overrides, overrides)
        self._audit_service.log(
            project,
            action="delete_override",
            actor=actor,
            payload={"skill_id": skill_id},
            result={"skills": list(overrides.keys())},
        )
        return overrides

    # ADR-054: Workforce Mobilization Policy persistence

    def get_mobilizacao_policies(self, project_id: str) -> dict[str, Any]:
        project = self._repository.get_project(project_id)
        return project.read_json(self._files.mobilizacao_policies, {})

    def upsert_mobilizacao_policy(
        self,
        project_id: str,
        item_id: str,
        policy_data: dict[str, Any],
        actor: str = "system",
    ) -> None:
        project = self._repository.get_project(project_id)
        policies = project.read_json(self._files.mobilizacao_policies, {})
        policies[item_id] = policy_data
        project.write_json(self._files.mobilizacao_policies, policies)
        self._audit_service.log(
            project,
            action="upsert_mobilizacao_policy",
            actor=actor,
            payload={"item_id": item_id, "policy": policy_data},
            result={"items": list(policies.keys())},
        )

    def delete_mobilizacao_policy(
        self,
        project_id: str,
        item_id: str,
        actor: str = "system",
    ) -> None:
        project = self._repository.get_project(project_id)
        policies = project.read_json(self._files.mobilizacao_policies, {})
        policies.pop(item_id, None)
        project.write_json(self._files.mobilizacao_policies, policies)
        self._audit_service.log(
            project,
            action="delete_mobilizacao_policy",
            actor=actor,
            payload={"item_id": item_id},
            result={"items": list(policies.keys())},
        )

    # ADR-054: Deliverables configuration

    def get_deliverables_config(self, project_id: str) -> dict:
        project = self._repository.get_project(project_id)
        stored = project.read_json(self._files.deliverables_config, {})
        if not stored:
            return dict(DEFAULT_DELIVERABLES)
        return stored

    def put_deliverables_config(self, project_id: str, config: dict, actor: str = "system") -> dict:
        project = self._repository.get_project(project_id)
        project.write_json(self._files.deliverables_config, config)
        self._audit_service.log(
            project,
            action="put_deliverables_config",
            actor=actor,
            payload=config,
            result={"status": "ok"},
        )
        return config
