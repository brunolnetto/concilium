from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from typing import Any

from concilium.domain.services.project_rules import (
    calculate_deltas,
    resolve_compare_version,
)

from ._project_service_helpers import (
    _enrich_payload_bdi,
    _enrich_payload_catalog,
    _enrich_payload_encargos,
    _ps_create_project,
    _ps_delete_version,
    _ps_upsert_eap,
)
from .audit_service import AuditService
from .project_files import DEFAULT_PROJECT_FILES, ProjectFiles
from .project_repository import ProjectRepository
from .service_support import build_summary


logger = logging.getLogger(__name__)


class ProjectService:
    def __init__(
        self, repository: ProjectRepository, audit_service: AuditService, files: ProjectFiles = DEFAULT_PROJECT_FILES
    ):
        self._repository = repository
        self._audit_service = audit_service
        self._files = files

    def list_projects(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for project in self._repository.list_projects():
            meta = project.meta
            tipo = meta.get("tipo_projeto", "hot_project")
            items.append(
                {
                    "project_id": meta.get("id", ""),
                    "nome": meta.get("nome", ""),
                    "contexto_id": meta.get("contexto_id", ""),
                    "tipo_projeto": tipo,
                    "status_eap": meta.get("status_eap", "ATIVO"),
                    "current_version": meta.get("current_version"),
                    "versions": project.list_versions(),
                    "benchmark_slug": meta.get("benchmark_slug"),
                }
            )
        return items

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
        tipo = meta.get("tipo_projeto", "hot_project")
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
        }

    # ── ADR-063: EAP management for "project" type ───────────────────────────

    def get_eap(self, project_id: str) -> dict[str, Any]:
        project = self._repository.get_project(project_id)
        eap = project.read_json(self._files.eap_items, [])
        return {
            "project_id": project_id,
            "status_eap": project.meta.get("status_eap", "RASCUNHO"),
            "items": eap,
            "count": len(eap),
        }

    def upsert_eap(self, project_id: str, eap_items: list[dict[str, Any]], actor: str = "system") -> dict[str, Any]:
        return _ps_upsert_eap(self, project_id, eap_items, actor)

    def list_versions(self, project_id: str) -> list[str]:
        return self._repository.get_project(project_id).list_versions()

    def delete_version(self, project_id: str, version: str, actor: str = "system") -> dict[str, Any]:
        return _ps_delete_version(self, project_id, version, actor)

    def fork_version(self, project_id: str, base_version: str, actor: str = "system") -> dict[str, Any]:
        project = self._repository.get_project(project_id)
        versions = project.list_versions()
        if base_version not in versions:
            raise FileNotFoundError(f"Versao '{base_version}' nao encontrada.")

        new_version = project.new_version(base=base_version)
        payload = {
            "project_id": project_id,
            "base_version": base_version,
            "forked_version": new_version,
            "current_version": project.current_version(),
            "versions": project.list_versions(),
        }
        self._audit_service.log(
            project, action="fork_version", actor=actor, payload={"base_version": base_version}, result=payload
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

        return {
            "left_version": left_version,
            "right_version": right_version,
            "resolved_left_version": resolved_left,
            "resolved_right_version": resolved_right,
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
        self, contexto_id: str, fields: dict[str, Any], motivo: str, author: str = "system"
    ) -> dict[str, Any]:
        """Create a new version of a context (ADR-062)."""
        svc = self._get_contexto_svc()
        if not svc:
            raise RuntimeError("Serviço de contextos não disponível.")
        return svc.create_version(contexto_id, fields, motivo, author)

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
        self, perfil_id: str, fields: dict[str, Any], motivo: str, author: str = "system"
    ) -> dict[str, Any]:
        svc = self._get_perfil_svc()
        if not svc:
            raise RuntimeError("Serviço de perfis não disponível.")
        return svc.create_version(perfil_id, fields, motivo, author)

    def compare_perfil_versions(self, perfil_id: str, version_a: str, version_b: str) -> dict[str, Any]:
        svc = self._get_perfil_svc()
        if not svc:
            return {"error": "Serviço de perfis não disponível."}
        return svc.compare(perfil_id, version_a, version_b)

    def _get_perfil_svc(self):
        try:
            from pathlib import Path

            from concilium.application.services.contexto_version_service import PerfilVersionService

            for candidate in [
                Path(__file__).parents[4] / "config",
                Path(__file__).parents[5] / "config",
            ]:
                if candidate.exists():
                    return PerfilVersionService(candidate)
        except Exception:
            pass
        return None

    # ── ADR-065: Temas ────────────────────────────────────────────────────────

    def list_temas(self) -> list[dict[str, Any]]:
        svc = self._get_tema_svc()
        return svc.list_temas() if svc else []

    def list_tema_versions(self, tema_id: str) -> list[dict[str, Any]]:
        svc = self._get_tema_svc()
        return svc.list_versions(tema_id) if svc else []

    def create_tema_version(
        self, tema_id: str, fields: dict[str, Any], motivo: str, author: str = "system"
    ) -> dict[str, Any]:
        svc = self._get_tema_svc()
        if not svc:
            raise RuntimeError("Serviço de temas não disponível.")
        return svc.create_version(tema_id, fields, motivo, author)

    def compare_tema_versions(self, tema_id: str, version_a: str, version_b: str) -> dict[str, Any]:
        svc = self._get_tema_svc()
        if not svc:
            return {"error": "Serviço de temas não disponível."}
        return svc.compare(tema_id, version_a, version_b)

    # ── ADR-066: Jurisdiction overlays ───────────────────────────────────────

    def list_jurisdicoes(self) -> list[dict[str, Any]]:
        svc = self._get_jurisdiction_svc()
        return svc.list_jurisdicoes() if svc else []

    def list_jurisdicao_versions(self, jurisdicao_id: str) -> list[dict[str, Any]]:
        svc = self._get_jurisdiction_svc()
        return svc.list_versions(jurisdicao_id) if svc else []

    def create_jurisdicao_version(
        self, jurisdicao_id: str, fields: dict[str, Any], motivo: str, author: str = "system"
    ) -> dict[str, Any]:
        svc = self._get_jurisdiction_svc()
        if not svc:
            raise RuntimeError("Serviço de jurisdições não disponível.")
        return svc.create_version(jurisdicao_id, fields, motivo, author)

    def compare_jurisdicao_versions(self, jurisdicao_id: str, version_a: str, version_b: str) -> dict[str, Any]:
        svc = self._get_jurisdiction_svc()
        if not svc:
            return {"error": "Serviço de jurisdições não disponível."}
        return svc.compare(jurisdicao_id, version_a, version_b)

    def _get_jurisdiction_svc(self):
        try:
            from pathlib import Path

            from concilium.application.services.contexto_version_service import JurisdictionVersionService

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

            from concilium.application.services.contexto_version_service import TemaVersionService

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

            from concilium.application.services.contexto_version_service import ContextoVersionService

            for candidate in [
                Path(__file__).parents[4] / "config",
                Path(__file__).parents[5] / "config",
            ]:
                if candidate.exists():
                    return ContextoVersionService(candidate)
        except Exception:
            pass
        return None

    @staticmethod
    def _normalize_eap_item(item: dict[str, Any], ordem_padrao: int) -> dict[str, Any] | None:
        item_id = item.get("item_id")
        cpu_id = item.get("cpu_id")
        if not item_id or not cpu_id:
            return None
        return {
            "item_id": str(item_id),
            "ordem": int(item.get("ordem") or ordem_padrao),
            "cpu_id": str(cpu_id),
            "descricao": str(item.get("descricao") or item_id),
            "unidade": str(item.get("unidade") or "un"),
            "quantitativo": float(item.get("quantitativo") or 0.0),
        }

    @staticmethod
    def _resolve_eap_source(payload: dict[str, Any]) -> str | None:
        cpus_block = payload.get("cpus")
        if isinstance(cpus_block, dict) and isinstance(cpus_block.get("itens_eap"), list):
            return "canonical.cpus.itens_eap"
        if isinstance(payload.get("eap"), list):
            return "legacy.eap_root"
        skill_inputs = payload.get("skill_inputs")
        if isinstance(skill_inputs, dict):
            escopo = skill_inputs.get("01-escopo-e-eap")
            if isinstance(escopo, dict):
                if isinstance(escopo.get("eap"), list):
                    return "legacy.skill_inputs.01-escopo-e-eap.eap"
                nested = escopo.get("inputs_escopo")
                if isinstance(nested, dict) and isinstance(nested.get("eap"), list):
                    return "legacy.skill_inputs.01-escopo-e-eap.inputs_escopo.eap"
        return None

    def _validate_benchmark_reference_contract(self, payload: dict[str, Any]) -> None:
        """Enforce canonical benchmark reference contract for EAP.

        Sprint 3 (NEP-026): legacy EAP paths are no longer accepted.
        """
        source = self._resolve_eap_source(payload)
        if source is None:
            cpus_block = payload.get("cpus") if isinstance(payload.get("cpus"), dict) else {}
            cpus_block.setdefault("itens_eap", [])
            payload["cpus"] = cpus_block
            return

        if source != "canonical.cpus.itens_eap":
            logger.error(
                "VAL-CONTRACT-EAP-LEGACY-BLOQUEADO: source=%s action=reject_legacy_payload",
                source,
            )
            raise ValueError(
                "VAL-CONTRACT-EAP-LEGACY-BLOQUEADO: use somente 'cpus.itens_eap' no benchmark_reference."
            )

        cpus_block = payload.get("cpus") if isinstance(payload.get("cpus"), dict) else {}
        raw_items = [row for row in cpus_block.get("itens_eap", []) if isinstance(row, dict)]
        canonical_items: list[dict[str, Any]] = []
        seen_item_ids: set[str] = set()
        for idx, row in enumerate(raw_items, start=1):
            normalized = self._normalize_eap_item(row, ordem_padrao=idx)
            if normalized is None:
                continue
            item_id = normalized["item_id"]
            if item_id in seen_item_ids:
                continue
            seen_item_ids.add(item_id)
            canonical_items.append(normalized)
        cpus_block["itens_eap"] = canonical_items
        payload["cpus"] = cpus_block

    def get_benchmark_reference(self, project_id: str) -> dict[str, Any]:
        project = self._repository.get_project(project_id)
        ref_file = self._files.benchmark_reference
        payload = project.read_json(ref_file, {})
        if not isinstance(payload, dict):
            raise ValueError("Referencia de benchmark invalida.")
        if not payload.get("catalog"):
            _enrich_payload_catalog(payload, project)
        _enrich_payload_encargos(payload, project)
        _enrich_payload_bdi(payload)
        self._validate_benchmark_reference_contract(payload)
        return payload
