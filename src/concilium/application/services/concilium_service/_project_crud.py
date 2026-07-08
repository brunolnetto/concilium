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

    def list_projects(self, owner_id: str | None = None) -> list[dict[str, Any]]:
        """ADR-126 D5: `owner_id` filtra por dono (usado por `?mine=true`)."""
        return self._dependencies.project_service.list_projects(owner_id=owner_id)

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

    def get_project_owner(self, project_id: str) -> str | None:
        """ADR-126 D3: usado pelas rotas para checar autorização combinada (role + ownership)."""
        return self._dependencies.project_service.get_project_owner(project_id)

    def find_projects_by_owner(self, owner_id: str) -> list[Any]:
        """ADR-126 D7/F7: usado por `remove-user` (CLI)."""
        return self._dependencies.project_service.find_projects_by_owner(owner_id)

    def transfer_ownership_forced(self, project_id: str, owner_novo: str, actor: str) -> dict[str, Any]:
        """ADR-126 D4.1: admin troca owner_id imediatamente, sem aceite."""
        return self._dependencies.project_service.transfer_ownership_forced(project_id, owner_novo, actor)

    def create_ownership_transfer_pending(self, project_id: str, owner_proposto: str, actor: str) -> dict[str, Any]:
        """ADR-126 D4.2: dono atual cria convite pendente (owner_id só muda após accept)."""
        return self._dependencies.project_service.create_ownership_transfer_pending(project_id, owner_proposto, actor)

    def accept_ownership_transfer(self, project_id: str, token: str, actor: str) -> dict[str, Any]:
        """ADR-126 F3: destinatário aceita — owner_id passa a ser owner_proposto."""
        return self._dependencies.project_service.accept_ownership_transfer(project_id, token, actor)

    def reject_ownership_transfer(self, project_id: str, token: str, actor: str) -> dict[str, Any]:
        """ADR-126 F3: destinatário rejeita — owner_id permanece inalterado."""
        return self._dependencies.project_service.reject_ownership_transfer(project_id, token, actor)

