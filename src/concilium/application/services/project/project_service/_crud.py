"""ProjectService — parte extraída de project_service.py (mixin _CrudMixin)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

from .._ownership_helpers import (
    accept_ownership_transfer,
    create_ownership_transfer_pending,
    find_projects_by_owner,
    get_project_owner,
    reject_ownership_transfer,
    transfer_ownership_forced,
)
from .._project_service_helpers import _ps_create_project, _ps_delete_project, _ps_delete_version
from ._shared import _debug_storage_info, _ps_build_list_item, _resolve_project_type

if TYPE_CHECKING:
    from ._host_protocol import ProjectServiceHost

    _Base = ProjectServiceHost
else:
    _Base = object


class _CrudMixin(_Base):
    """Métodos de crud de ProjectService."""

    def list_projects(self, owner_id: str | None = None) -> list[dict[str, Any]]:
        """ADR-126 D5: `owner_id` filtra por dono (usado por `?mine=true`)."""
        projects = self._repository.list_projects()
        if owner_id is not None:
            projects = [p for p in projects if p.meta.get("owner_id") == owner_id]
        if not projects:
            return []
        # Backends remotos (SharePoint/S3/Azure) pagam 1 round-trip por meta.json +
        # 1 listagem (recursiva) por projeto para 'versions' — sequencial isso escala
        # O(N) em latência de rede. Paraleliza para manter o tempo de resposta ~constante.
        # Filtra por owner_id ANTES de construir os itens (evita list_versions()
        # desnecessário em projetos que serão descartados pelo filtro).
        with ThreadPoolExecutor(max_workers=min(16, len(projects))) as executor:
            return list(executor.map(_ps_build_list_item, projects))

    def create_project(
        self,
        req: Any,
        inputs_escopo: dict[str, Any],
        skill_inputs: dict[str, dict[str, Any]],
        benchmark_slug: str | None,
        benchmark_reference: dict[str, Any] | None,
        actor: str = "system",
        contexto_version: str | None = None,
        perfil_id: str | None = None,
        perfil_version: str | None = None,
    ) -> dict[str, Any]:
        return _ps_create_project(
            self,
            req,
            inputs_escopo,
            skill_inputs,
            benchmark_slug,
            benchmark_reference,
            actor,
            contexto_version,
            perfil_id,
            perfil_version,
        )

    def get_project(self, project_id: str) -> dict[str, Any]:
        project = self._repository.get_project(project_id)
        meta = project.meta
        versions = project.list_versions()
        tipo = _resolve_project_type(meta)
        return {
            "project_id": meta.get("id", project_id),
            "nome": meta.get("nome", ""),
            "contexto_id": meta.get("contexto_id", ""),
            "tipo_projeto": tipo,
            "status_eap": meta.get("status_eap", "ATIVO"),
            "current_version": project.current_version(),
            "versions": versions,
            "benchmark_slug": meta.get("benchmark_slug"),
            "benchmark_reference_file": self._files.benchmark_reference
            if project.exists(self._files.benchmark_reference)
            else None,
            # ADR-126 D1/D2: owner_id (responsável pelo projeto) é distinto de
            # criado_por/role_criador por versão (ADR-119, exposto via version_history).
            "owner_id": meta.get("owner_id"),
            "owner_assigned_at": meta.get("owner_assigned_at"),
            "_debug": _debug_storage_info(project),
        }

    def list_versions(self, project_id: str) -> list[str]:
        return self._repository.get_project(project_id).list_versions()

    def get_version_history(self, project_id: str) -> dict:
        """ADR-119 D3: retorna metadados de autoria de todas as versões do projeto."""
        project = self._repository.get_project(project_id)
        return project.meta.get("version_history") or {}

    def delete_version(self, project_id: str, version: str, actor: str = "system") -> dict[str, Any]:
        return _ps_delete_version(self, project_id, version, actor)

    def delete_project(self, project_id: str, actor: str = "system") -> dict[str, Any]:
        return _ps_delete_project(self, project_id, actor)

    def get_project_owner(self, project_id: str) -> str | None:
        """ADR-126 D3: usado pelas rotas para checar autorização combinada (role + ownership)."""
        return get_project_owner(self._repository.get_project(project_id))

    def find_projects_by_owner(self, owner_id: str) -> list[Any]:
        """ADR-126 D7/F7: usado por `remove-user` (CLI) para bloquear/realocar antes de remover um client."""
        return find_projects_by_owner(self._repository, owner_id)

    def transfer_ownership_forced(self, project_id: str, owner_novo: str, actor: str) -> dict[str, Any]:
        """ADR-126 D4.1: admin troca owner_id imediatamente, sem aceite."""
        return transfer_ownership_forced(
            self._repository.get_project(project_id), owner_novo, actor=actor, audit=self._audit_service
        )

    def create_ownership_transfer_pending(self, project_id: str, owner_proposto: str, actor: str) -> dict[str, Any]:
        """ADR-126 D4.2: dono atual cria convite pendente (owner_id só muda após accept)."""
        pending = create_ownership_transfer_pending(
            self._repository.get_project(project_id), owner_proposto, actor=actor, audit=self._audit_service
        )
        return pending.to_dict()

    def accept_ownership_transfer(self, project_id: str, token: str, actor: str) -> dict[str, Any]:
        """ADR-126 F3: destinatário aceita — owner_id passa a ser owner_proposto."""
        return accept_ownership_transfer(
            self._repository.get_project(project_id), token, actor=actor, audit=self._audit_service
        )

    def reject_ownership_transfer(self, project_id: str, token: str, actor: str) -> dict[str, Any]:
        """ADR-126 F3: destinatário rejeita — owner_id permanece inalterado."""
        return reject_ownership_transfer(
            self._repository.get_project(project_id), token, actor=actor, audit=self._audit_service
        )

