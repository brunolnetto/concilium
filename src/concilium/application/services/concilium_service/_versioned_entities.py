"""ConciliumService — parte extraída de concilium_service.py (mixin _VersionedEntitiesMixin)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._host_protocol import ConciliumServiceHost

    _Base = ConciliumServiceHost
else:
    _Base = object


class _VersionedEntitiesMixin(_Base):
    """Métodos de versioned_entities de ConciliumService."""

    def list_perfis(self) -> list[dict[str, Any]]:
        return self._dependencies.project_service.list_perfis()

    def list_perfil_versions(self, perfil_id: str) -> list[dict[str, Any]]:
        return self._dependencies.project_service.list_perfil_versions(perfil_id)

    def create_perfil_version(
        self,
        perfil_id: str,
        fields: dict[str, Any],
        motivo: str,
        author: str = "system",
        make_current: bool | None = None,
    ) -> dict[str, Any]:
        return self._dependencies.project_service.create_perfil_version(
            perfil_id,
            fields,
            motivo,
            author,
            make_current=make_current,
        )

    def compare_perfil_versions(self, perfil_id: str, version_a: str, version_b: str) -> dict[str, Any]:
        return self._dependencies.project_service.compare_perfil_versions(perfil_id, version_a, version_b)

    def list_contextos(self) -> list[dict[str, Any]]:
        return self._dependencies.project_service.list_contextos()

    def list_contexto_versions(self, contexto_id: str) -> list[dict[str, Any]]:
        return self._dependencies.project_service.list_contexto_versions(contexto_id)

    def create_contexto_version(
        self,
        contexto_id: str,
        fields: dict[str, Any],
        motivo: str,
        author: str = "system",
        make_current: bool | None = None,
    ) -> dict[str, Any]:
        return self._dependencies.project_service.create_contexto_version(
            contexto_id,
            fields,
            motivo,
            author,
            make_current=make_current,
        )

    def compare_contexto_versions(self, contexto_id: str, version_a: str, version_b: str) -> dict[str, Any]:
        return self._dependencies.project_service.compare_contexto_versions(contexto_id, version_a, version_b)

    def list_temas(self) -> list[dict[str, Any]]:
        return self._dependencies.project_service.list_temas()

    def list_tema_versions(self, tema_id: str) -> list[dict[str, Any]]:
        return self._dependencies.project_service.list_tema_versions(tema_id)

    def create_tema_version(
        self,
        tema_id: str,
        fields: dict[str, Any],
        motivo: str,
        author: str = "system",
        make_current: bool | None = None,
    ) -> dict[str, Any]:
        return self._dependencies.project_service.create_tema_version(
            tema_id,
            fields,
            motivo,
            author,
            make_current=make_current,
        )

    def compare_tema_versions(self, tema_id: str, version_a: str, version_b: str) -> dict[str, Any]:
        return self._dependencies.project_service.compare_tema_versions(tema_id, version_a, version_b)

    def list_jurisdicoes(self) -> list[dict[str, Any]]:
        return self._dependencies.project_service.list_jurisdicoes()

    def list_jurisdicao_versions(self, jurisdicao_id: str) -> list[dict[str, Any]]:
        return self._dependencies.project_service.list_jurisdicao_versions(jurisdicao_id)

    def create_jurisdicao_version(
        self,
        jurisdicao_id: str,
        fields: dict[str, Any],
        motivo: str,
        author: str = "system",
        make_current: bool | None = None,
    ) -> dict[str, Any]:
        return self._dependencies.project_service.create_jurisdicao_version(
            jurisdicao_id,
            fields,
            motivo,
            author,
            make_current=make_current,
        )

    def compare_jurisdicao_versions(self, jurisdicao_id: str, version_a: str, version_b: str) -> dict[str, Any]:
        return self._dependencies.project_service.compare_jurisdicao_versions(jurisdicao_id, version_a, version_b)

