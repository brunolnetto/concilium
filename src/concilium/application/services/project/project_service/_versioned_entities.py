"""ProjectService — parte extraída de project_service.py (mixin _VersionedEntitiesMixin)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._host_protocol import ProjectServiceHost

    _Base = ProjectServiceHost
else:
    _Base = object


class _VersionedEntitiesMixin(_Base):
    """Métodos de versioned_entities de ProjectService."""

    def list_contextos(self) -> list[dict[str, Any]]:
        """List available contexts with version history (ADR-062)."""
        svc = self._get_contexto_svc()
        if svc:
            return svc.list_contexts()
        return []

    def list_contexto_versions(self, contexto_id: str) -> list[dict[str, Any]]:
        """List versions of a specific context (ADR-062)."""
        svc = self._get_contexto_svc()
        if svc:
            return svc.list_versions(contexto_id)
        return []

    def create_contexto_version(
        self,
        contexto_id: str,
        fields: dict[str, Any],
        motivo: str,
        author: str = "system",
        make_current: bool | None = None,
    ) -> dict[str, Any]:
        """Create a new version of a context (ADR-062)."""
        svc = self._get_contexto_svc()
        if not svc:
            raise RuntimeError("Serviço de contextos não disponível.")
        self._validate_contexto_fields(fields)
        return svc.create_version(contexto_id, fields, motivo, author, make_current=(make_current is not False))

    def compare_contexto_versions(self, contexto_id: str, version_a: str, version_b: str) -> dict[str, Any]:
        """Compare two versions of a context (ADR-062)."""
        svc = self._get_contexto_svc()
        if not svc:
            return {"error": "Serviço de contextos não disponível."}
        return svc.compare(contexto_id, version_a, version_b)

    def list_perfis(self) -> list[dict[str, Any]]:
        """List available profiles with version history (ADR-062)."""
        svc = self._get_perfil_svc()
        if svc:
            return svc.list_entities()
        return []

    def list_perfil_versions(self, perfil_id: str) -> list[dict[str, Any]]:
        svc = self._get_perfil_svc()
        return svc.list_versions(perfil_id) if svc else []

    def create_perfil_version(
        self,
        perfil_id: str,
        fields: dict[str, Any],
        motivo: str,
        author: str = "system",
        make_current: bool | None = None,
    ) -> dict[str, Any]:
        svc = self._get_perfil_svc()
        if not svc:
            raise RuntimeError("Serviço de perfis não disponível.")
        self._validate_perfil_fields(fields)
        return svc.create_version(perfil_id, fields, motivo, author, make_current=(make_current is not False))

    def compare_perfil_versions(self, perfil_id: str, version_a: str, version_b: str) -> dict[str, Any]:
        svc = self._get_perfil_svc()
        if not svc:
            return {"error": "Serviço de perfis não disponível."}
        return svc.compare(perfil_id, version_a, version_b)

    def _get_perfil_svc(self):
        try:
            from pathlib import Path

            from concilium.application.services.catalog.contexto_version_service import PerfilVersionService

            for candidate in [
                Path(__file__).parents[4] / "config",
                Path(__file__).parents[5] / "config",
            ]:
                if candidate.exists():
                    return PerfilVersionService(candidate)
        except Exception:
            pass
        return None

    def list_temas(self) -> list[dict[str, Any]]:
        svc = self._get_tema_svc()
        return svc.list_temas() if svc else []

    def list_tema_versions(self, tema_id: str) -> list[dict[str, Any]]:
        svc = self._get_tema_svc()
        return svc.list_versions(tema_id) if svc else []

    def create_tema_version(
        self,
        tema_id: str,
        fields: dict[str, Any],
        motivo: str,
        author: str = "system",
        make_current: bool | None = None,
    ) -> dict[str, Any]:
        svc = self._get_tema_svc()
        if not svc:
            raise RuntimeError("Serviço de temas não disponível.")
        self._validate_tema_fields(svc, tema_id, fields)
        return svc.create_version(tema_id, fields, motivo, author, make_current=(make_current is not False))

    def compare_tema_versions(self, tema_id: str, version_a: str, version_b: str) -> dict[str, Any]:
        svc = self._get_tema_svc()
        if not svc:
            return {"error": "Serviço de temas não disponível."}
        return svc.compare(tema_id, version_a, version_b)

    def list_jurisdicoes(self) -> list[dict[str, Any]]:
        svc = self._get_jurisdiction_svc()
        return svc.list_jurisdicoes() if svc else []

    def list_jurisdicao_versions(self, jurisdicao_id: str) -> list[dict[str, Any]]:
        svc = self._get_jurisdiction_svc()
        return svc.list_versions(jurisdicao_id) if svc else []

    def create_jurisdicao_version(
        self,
        jurisdicao_id: str,
        fields: dict[str, Any],
        motivo: str,
        author: str = "system",
        make_current: bool | None = None,
    ) -> dict[str, Any]:
        svc = self._get_jurisdiction_svc()
        if not svc:
            raise RuntimeError("Serviço de jurisdições não disponível.")
        self._validate_jurisdicao_fields(fields)
        return svc.create_version(jurisdicao_id, fields, motivo, author, make_current=(make_current is not False))

    def compare_jurisdicao_versions(self, jurisdicao_id: str, version_a: str, version_b: str) -> dict[str, Any]:
        svc = self._get_jurisdiction_svc()
        if not svc:
            return {"error": "Serviço de jurisdições não disponível."}
        return svc.compare(jurisdicao_id, version_a, version_b)

    def _get_jurisdiction_svc(self):
        try:
            from pathlib import Path

            from concilium.application.services.catalog.contexto_version_service import JurisdictionVersionService

            for candidate in [
                Path(__file__).parents[4] / "config",
                Path(__file__).parents[5] / "config",
            ]:
                if candidate.exists():
                    return JurisdictionVersionService(candidate)
        except Exception:
            pass
        return None

    def _get_tema_svc(self):
        try:
            from pathlib import Path

            from concilium.application.services.catalog.contexto_version_service import TemaVersionService

            for candidate in [
                Path(__file__).parents[4] / "config",
                Path(__file__).parents[5] / "config",
            ]:
                if candidate.exists():
                    return TemaVersionService(candidate)
        except Exception:
            pass
        return None

    def _get_contexto_svc(self):
        """Returns ContextoVersionService if config_root is locatable."""
        try:
            from pathlib import Path

            from concilium.application.services.catalog.contexto_version_service import ContextoVersionService

            for candidate in [
                Path(__file__).parents[4] / "config",
                Path(__file__).parents[5] / "config",
            ]:
                if candidate.exists():
                    return ContextoVersionService(candidate)
        except Exception:
            pass
        return None

