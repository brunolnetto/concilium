"""ProjectService — parte extraída de project_service.py (mixin _CrudMixin)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

from .._project_service_helpers import _ps_create_project, _ps_delete_project, _ps_delete_version
from ._shared import _debug_storage_info, _ps_build_list_item, _resolve_project_type

if TYPE_CHECKING:
    from ._host_protocol import ProjectServiceHost

    _Base = ProjectServiceHost
else:
    _Base = object


class _CrudMixin(_Base):
    """Métodos de crud de ProjectService."""

    def list_projects(self) -> list[dict[str, Any]]:
        projects = self._repository.list_projects()
        if not projects:
            return []
        # Backends remotos (SharePoint/S3/Azure) pagam 1 round-trip por meta.json +
        # 1 listagem (recursiva) por projeto para 'versions' — sequencial isso escala
        # O(N) em latência de rede. Paraleliza para manter o tempo de resposta ~constante.
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

