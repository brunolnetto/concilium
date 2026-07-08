"""ProjectService — parte extraída de project_service.py (mixin _VersionsArtifactsMixin)."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import TYPE_CHECKING, Any

from concilium.domain.services.project_rules import (
    calculate_deltas,
    resolve_compare_version,
)

from ...service_support import build_summary

if TYPE_CHECKING:
    from ._host_protocol import ProjectServiceHost

    _Base = ProjectServiceHost
else:
    _Base = object


class _VersionsArtifactsMixin(_Base):
    """Métodos de versions_artifacts de ProjectService."""

    def fork_version(self, project_id: str, base_version: str, actor: str = "system") -> dict[str, Any]:
        project = self._repository.get_project(project_id)
        versions = project.list_versions()
        if base_version not in versions:
            raise FileNotFoundError(f"Versao '{base_version}' nao encontrada.")

        # ADR-119 D3: captura identidade do ator via contextvars (ADR-118)
        from concilium.infrastructure.auth.permission_guard import (
            _current_roles,
            get_current_user_id,
        )

        user_id = get_current_user_id() or actor
        roles = list(_current_roles.get())
        role_criador = roles[0] if roles else None
        # herda intent da versão de origem
        base_meta = project.get_version_meta(base_version)
        inherited_intent = base_meta.get("procurement_intent")

        new_version = project.new_version(
            base=base_version,
            criado_por=user_id,
            role_criador=role_criador,
            procurement_intent=inherited_intent,
            forked_from=base_version,
        )
        payload = {
            "project_id": project_id,
            "base_version": base_version,
            "forked_version": new_version,
            "current_version": project.current_version(),
            "versions": project.list_versions(),
            "criado_por": user_id,
            "role_criador": role_criador,
        }
        # ADR-119 D5: VersionAction no audit trail
        from ..audit_service import VersionAction

        va = VersionAction(
            action="fork",
            version_afetada=new_version,
            actor_id=user_id,
            actor_role=role_criador,
            intent=inherited_intent,
            detalhes={"forked_from": base_version},
        )
        self._audit_service.log(
            project,
            action="fork_version",
            actor=actor,
            payload={"base_version": base_version},
            result=payload,
            version_action=va,
        )
        return payload

    def compare_versions(self, project_id: str, left_version: str, right_version: str) -> dict[str, Any]:
        project = self._repository.get_project(project_id)
        resolved_left = resolve_compare_version(project, left_version)
        resolved_right = resolve_compare_version(project, right_version)
        left = project.load_canonical(resolved_left)
        right = project.load_canonical(resolved_right)
        if left is None or right is None:
            raise ValueError("Versoes informadas sem canônico disponível.")

        left_summary = build_summary(left)
        right_summary = build_summary(right)
        deltas = calculate_deltas(left_summary, right_summary)

        # ADR-119 D4: enriquecer com metadados de autoria das versões comparadas
        version_history = project.meta.get("version_history") or {}
        left_meta = version_history.get(resolved_left) or {}
        right_meta = version_history.get(resolved_right) or {}

        return {
            "left_version": left_version,
            "right_version": right_version,
            "resolved_left_version": resolved_left,
            "resolved_right_version": resolved_right,
            "left_autoria": {
                "criado_por": left_meta.get("criado_por"),
                "role_criador": left_meta.get("role_criador"),
                "procurement_intent": left_meta.get("procurement_intent"),
                "criado_em": left_meta.get("criado_em"),
            },
            "right_autoria": {
                "criado_por": right_meta.get("criado_por"),
                "role_criador": right_meta.get("role_criador"),
                "procurement_intent": right_meta.get("procurement_intent"),
                "criado_em": right_meta.get("criado_em"),
            },
            "left": left_summary,
            "right": right_summary,
            "deltas": deltas,
        }

    def list_artifacts(self, project_id: str, version: str | None) -> dict[str, Any]:
        project = self._repository.get_project(project_id)
        resolved_version = version or project.current_version()
        if resolved_version is None:
            return {"version": None, "outputs": [], "intermediate": [], "typed_artifacts": []}

        outputs = project.list_output_files(resolved_version)
        intermediate = project.list_file_names(f"{resolved_version}/intermediate")
        typed_artifacts = project.list_file_names(f"{resolved_version}/artifacts")
        return {
            "version": resolved_version,
            "outputs": outputs,
            "intermediate": intermediate,
            "typed_artifacts": typed_artifacts,
        }

    def get_artifact_bytes(self, project_id: str, version: str | None, kind: str, filename: str) -> tuple[bytes, str]:
        project = self._repository.get_project(project_id)
        resolved_version = version or project.current_version()
        if resolved_version is None:
            raise FileNotFoundError("Projeto nao possui versao ativa.")

        safe_filename = Path(filename).name
        if safe_filename != filename:
            raise ValueError("Nome de arquivo invalido.")

        if kind == "outputs":
            payload = project.load_output_file(resolved_version, safe_filename)
        elif kind == "intermediate":
            payload = project.read_bytes(f"{resolved_version}/intermediate/{safe_filename}")
        elif kind in ("artifacts", "typed_artifacts"):
            payload = project.read_bytes(f"{resolved_version}/artifacts/{safe_filename}")
        else:
            raise ValueError("kind deve ser 'outputs', 'intermediate' ou 'typed_artifacts'.")

        if payload is None:
            raise FileNotFoundError(f"Artefato '{safe_filename}' nao encontrado na versao '{resolved_version}'.")

        media_type = mimetypes.guess_type(safe_filename)[0] or "application/octet-stream"
        return payload, media_type

    def get_last_canonical(self, project_id: str):
        """ADR-060/061: retorna CanonicalModel da versão atual, ou None."""
        try:
            project = self._repository.get_project(project_id)
            return project.load_canonical()
        except Exception:
            return None

    def patch_project_config(self, project_id: str, updates: dict[str, Any], actor: str = "system") -> dict[str, Any]:
        project = self._repository.get_project(project_id)
        allowed = {"contexto_id", "nome"}
        meta = dict(project.meta)
        changed = []
        for k in allowed:
            if k in updates and updates[k] != meta.get(k):
                meta[k] = updates[k]
                changed.append(k)
        if changed:
            project.write_json("meta.json", meta)
        return {"project_id": project_id, "updated": changed, "meta": meta}

