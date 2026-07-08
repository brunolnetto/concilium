"""ConciliumService — parte extraída de concilium_service.py (mixin _ProjectCrudMixin)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from concilium.application.benchmarks.execution.batch import discover_benchmark_slugs

if TYPE_CHECKING:
    from ._host_protocol import ConciliumServiceHost

    _Base = ConciliumServiceHost
else:
    _Base = object


class _ProjectCrudMixin(_Base):
    """Métodos de project_crud de ConciliumService."""

    def list_benchmarks(self) -> list[str]:
        return discover_benchmark_slugs(self._dependencies.benchmarks_root)

    def list_projects(self) -> list[dict[str, Any]]:
        return self._dependencies.project_service.list_projects()

    def create_project(self, req: Any, actor: str = "system") -> dict[str, Any]:
        prepared = self._dependencies.input_builder.prepare(req)
        return self._dependencies.project_service.create_project(
            req,
            prepared.inputs_escopo,
            prepared.skill_inputs,
            prepared.benchmark_slug,
            prepared.benchmark_reference,
            actor=actor,
            contexto_version=prepared.contexto_version,  # ADR-062
            perfil_id=prepared.perfil_id,  # ADR-062
            perfil_version=prepared.perfil_version,  # ADR-062
        )

    def get_project(self, project_id: str) -> dict[str, Any]:
        return self._dependencies.project_service.get_project(project_id)

    def delete_project(self, project_id: str, actor: str = "system") -> dict[str, Any]:
        return self._dependencies.project_service.delete_project(project_id, actor=actor)

    def get_eap(self, project_id: str) -> dict[str, Any]:
        return self._dependencies.project_service.get_eap(project_id)

    def upsert_eap(self, project_id: str, eap_items: list[dict[str, Any]], actor: str = "system") -> dict[str, Any]:
        return self._dependencies.project_service.upsert_eap(project_id, eap_items, actor=actor)

    def patch_project_config(self, project_id: str, updates: dict[str, Any], actor: str = "system") -> dict[str, Any]:
        return self._dependencies.project_service.patch_project_config(project_id, updates, actor=actor)

