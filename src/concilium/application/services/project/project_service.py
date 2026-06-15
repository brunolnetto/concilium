from __future__ import annotations

import logging
import mimetypes
import re
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
    _ps_delete_project,
    _ps_delete_version,
    _ps_upsert_eap,
)
from .audit_service import AuditService
from .project_files import DEFAULT_PROJECT_FILES, ProjectFiles
from .project_repository import ProjectRepository
from ..service_support import build_summary

logger = logging.getLogger(__name__)


def _debug_storage_info(project: Any) -> dict[str, Any]:
    """Expose non-sensitive storage diagnostics for runtime troubleshooting."""
    try:
        root = str(project.root)
    except Exception:
        root = ""
    try:
        projects_root = str(project.root.parent)
    except Exception:
        projects_root = ""
    return {
        "storage_root": root,
        "projects_root": projects_root,
    }


def _resolve_project_type(meta: dict[str, Any]) -> str:
    """Resolve project type with historical payload compatibility.

    Older projects may lack `tipo_projeto`. In that case, infer by benchmark_slug.
    """
    raw = str(meta.get("tipo_projeto") or "").strip().lower()
    if raw in {"hot_project", "project"}:
        return raw
    return "hot_project" if meta.get("benchmark_slug") else "project"


def _canonical_eap_to_rows(canonical: Any) -> list[dict[str, Any]]:
    """Convert canonical.eap entries into plain dict rows."""
    rows: list[dict[str, Any]] = []
    eap_items = getattr(canonical, "eap", None) or []
    for item in eap_items:
        if isinstance(item, dict):
            rows.append(dict(item))
            continue
        if hasattr(item, "model_dump"):
            rows.append(item.model_dump())
            continue
        if hasattr(item, "dict"):
            rows.append(item.dict())
            continue
        if hasattr(item, "to_dict"):
            rows.append(item.to_dict())
    return rows


def _is_valid_canonical_eap(payload: dict[str, Any]) -> bool:
    cpus_block = payload.get("cpus")
    if not isinstance(cpus_block, dict):
        return False
    items = cpus_block.get("itens_eap")
    return isinstance(items, list) and len(items) > 0


_REF_YYYY_MM_RE = re.compile(r"^\d{4}-\d{2}$")


def _extract_historical_eap_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract historical EAP rows from known payload locations."""
    src = payload.get("eap")
    if isinstance(src, list):
        return [row for row in src if isinstance(row, dict)]
    skill_inputs = payload.get("skill_inputs")
    if isinstance(skill_inputs, dict):
        escopo = skill_inputs.get("01-escopo-e-eap")
        if isinstance(escopo, dict):
            src = escopo.get("eap")
            if isinstance(src, list):
                return [row for row in src if isinstance(row, dict)]
            nested = escopo.get("inputs_escopo")
            if isinstance(nested, dict):
                src = nested.get("eap")
                if isinstance(src, list):
                    return [row for row in src if isinstance(row, dict)]
    return []


def _extract_canonical_eap_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract canonical EAP rows from cpus.itens_eap when present."""
    cpus_block = payload.get("cpus")
    if not isinstance(cpus_block, dict):
        return []
    rows = cpus_block.get("itens_eap")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _catalog_is_deficit(catalog: Any) -> bool:
    """Heuristic: catalog is deficit when CPUs exist but none carries team composition."""
    if not isinstance(catalog, dict):
        return True
    cpus = catalog.get("cpus")
    if not isinstance(cpus, list) or not cpus:
        return True
    for cpu in cpus:
        if not isinstance(cpu, dict):
            continue
        equipe = cpu.get("equipe")
        if isinstance(equipe, dict) and ((equipe.get("funcoes") or []) or (equipe.get("equipamentos") or [])):
            return False
    return True


def _latest_version_with_eap(project: Any) -> tuple[list[dict[str, Any]], str | None]:
    """Return canonical EAP rows from the newest version that contains EAP."""
    versions = list(project.list_versions() or [])
    for version in reversed(versions):
        try:
            canonical = project.load_canonical(version)
        except Exception:
            canonical = None
        if canonical is None:
            continue
        rows = _canonical_eap_to_rows(canonical)
        if rows:
            return rows, version
    return [], None


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
            tipo = _resolve_project_type(meta)
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

    # ── ADR-063: EAP management for "project" type ───────────────────────────

    def get_eap(self, project_id: str) -> dict[str, Any]:
        project = self._repository.get_project(project_id)
        eap = project.read_json(self._files.eap_items, [])
        eap_source = "project.eap_items"
        if not isinstance(eap, list):
            eap = []

        if not eap:
            ref_payload = project.read_json(self._files.benchmark_reference, {})
            if isinstance(ref_payload, dict):
                source = self._resolve_eap_source(ref_payload)
                if source == "canonical.cpus.itens_eap":
                    raw_rows = _extract_canonical_eap_rows(ref_payload)
                else:
                    raw_rows = _extract_historical_eap_rows(ref_payload)
                normalized_rows: list[dict[str, Any]] = []
                seen_item_ids: set[str] = set()
                for idx, row in enumerate(raw_rows, start=1):
                    normalized = self._normalize_eap_item(row, ordem_padrao=idx)
                    if normalized is None:
                        continue
                    item_id = normalized["item_id"]
                    if item_id in seen_item_ids:
                        continue
                    seen_item_ids.add(item_id)
                    normalized_rows.append(normalized)
                if normalized_rows:
                    eap = normalized_rows
                    eap_source = f"benchmark_reference:{source or 'historical'}"

        if not eap:
            canonical = project.load_canonical()
            if canonical is not None:
                eap = _canonical_eap_to_rows(canonical)
                if eap:
                    eap_source = "canonical.eap"

        if not eap:
            historical_rows, historical_version = _latest_version_with_eap(project)
            if historical_rows:
                eap = historical_rows
                eap_source = f"historical_canonical.eap:{historical_version or 'unknown'}"

        tipo = _resolve_project_type(project.meta)
        default_status = "ATIVO" if tipo == "hot_project" else "RASCUNHO"
        return {
            "project_id": project_id,
            "status_eap": project.meta.get("status_eap", default_status),
            "items": eap,
            "count": len(eap),
            "_debug": {
                **_debug_storage_info(project),
                "eap_source": eap_source,
            },
        }

    def upsert_eap(self, project_id: str, eap_items: list[dict[str, Any]], actor: str = "system") -> dict[str, Any]:
        return _ps_upsert_eap(self, project_id, eap_items, actor)

    def list_versions(self, project_id: str) -> list[str]:
        return self._repository.get_project(project_id).list_versions()

    def delete_version(self, project_id: str, version: str, actor: str = "system") -> dict[str, Any]:
        return _ps_delete_version(self, project_id, version, actor)

    def delete_project(self, project_id: str, actor: str = "system") -> dict[str, Any]:
        return _ps_delete_project(self, project_id, actor)

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

    # ── ADR-065: Temas ────────────────────────────────────────────────────────

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

    # ── ADR-066: Jurisdiction overlays ───────────────────────────────────────

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

    def _resolve_config_root(self) -> Path | None:
        for candidate in [
            Path(__file__).parents[4] / "config",
            Path(__file__).parents[5] / "config",
        ]:
            if candidate.exists():
                return candidate
        return None

    def _validate_range_field(
        self,
        fields: dict[str, Any],
        key: str,
        *,
        lower: float,
        upper: float,
    ) -> None:
        value = fields.get(key)
        if not isinstance(value, dict):
            return
        if "min" not in value or "max" not in value:
            raise ValueError(f"{key}: campos 'min' e 'max' são obrigatórios")
        try:
            vmin = float(value.get("min"))
            vmax = float(value.get("max"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key}: valores inválidos para min/max") from exc
        if vmin > vmax:
            raise ValueError(f"{key}: min deve ser <= max")
        if vmin < lower or vmax > upper:
            raise ValueError(f"{key}: valores fora do intervalo permitido [{lower}, {upper}]")

    def _validate_perfil_fields(self, fields: dict[str, Any]) -> None:
        self._validate_range_field(fields, "faixa_margem_alvo", lower=0.0, upper=1.0)
        self._validate_range_field(fields, "faixa_margem_aceitavel", lower=0.0, upper=1.0)
        self._validate_range_field(fields, "razao_indireto_direto_alvo", lower=0.0, upper=2.0)

    def _validate_contexto_fields(self, fields: dict[str, Any]) -> None:
        perfil_id = fields.get("perfil_id")
        if perfil_id is not None and perfil_id not in {p.get("id") for p in self.list_perfis()}:
            raise ValueError(f"perfil_id inválido: '{perfil_id}'")

        jurisdicao_id = fields.get("jurisdicao_id")
        if jurisdicao_id is not None and jurisdicao_id not in {j.get("id") for j in self.list_jurisdicoes()}:
            raise ValueError(f"jurisdicao_id inválido: '{jurisdicao_id}'")

        tema_id = fields.get("tema_id")
        if tema_id is not None and tema_id not in {t.get("id") for t in self.list_temas()}:
            raise ValueError(f"tema_id inválido: '{tema_id}'")

        catalogo_id = fields.get("catalogo_id")
        if catalogo_id is not None:
            cfg = self._resolve_config_root()
            if cfg is None or not (cfg / "catalogos" / str(catalogo_id)).exists():
                raise ValueError(f"catalogo_id inválido: '{catalogo_id}'")

    def _validate_tema_fields(self, svc: Any, tema_id: str, fields: dict[str, Any]) -> None:
        from concilium.domain.models.catalog.tema import TemaVisual

        base = svc.resolve(tema_id) or {"id": tema_id}
        merged = {**base, **fields}
        if "id" not in merged:
            merged["id"] = tema_id
        try:
            TemaVisual.model_validate(merged)
        except Exception as exc:
            raise ValueError(f"Tema inválido: {exc}") from exc

    def _validate_jurisdicao_fields(self, fields: dict[str, Any]) -> None:
        provedores = fields.get("provedores_referencia")
        if isinstance(provedores, list):
            for idx, prov in enumerate(provedores):
                if not isinstance(prov, dict):
                    raise ValueError(f"provedores_referencia[{idx}] deve ser objeto")
                ref = str(prov.get("data_referencia") or "").strip()
                if ref and not _REF_YYYY_MM_RE.match(ref):
                    raise ValueError(
                        f"provedores_referencia[{idx}].data_referencia inválida: '{ref}' (esperado AAAA-MM)"
                    )

    @staticmethod
    def _normalize_eap_item(item: dict[str, Any], ordem_padrao: int) -> dict[str, Any] | None:
        def _pick(*keys: str) -> Any:
            for key in keys:
                value = item.get(key)
                if value is None:
                    continue
                if isinstance(value, str) and not value.strip():
                    continue
                return value
            return None

        item_id = _pick("item_id", "activity_id", "eap_item_id", "id", "codigo")
        cpu_id = _pick("cpu_id", "cpu", "cpu_codigo", "codigo_cpu")
        if not item_id or not cpu_id:
            return None

        ordem_raw = _pick("ordem", "order", "seq")
        try:
            ordem = int(ordem_raw) if ordem_raw is not None else ordem_padrao
        except (TypeError, ValueError):
            ordem = ordem_padrao

        quantitativo_raw = _pick("quantitativo", "quantidade", "qtd", "volume")
        try:
            quantitativo = float(quantitativo_raw) if quantitativo_raw is not None else 0.0
        except (TypeError, ValueError):
            quantitativo = 0.0

        normalized = dict(item)
        normalized.update(
            {
                "item_id": str(item_id),
                "ordem": ordem,
                "cpu_id": str(cpu_id),
                "descricao": str(_pick("descricao", "nome", "atividade_descricao") or item_id),
                "unidade": str(_pick("unidade", "un", "und") or "un"),
                "quantitativo": quantitativo,
            }
        )
        return normalized

    @staticmethod
    def _resolve_eap_source(payload: dict[str, Any]) -> str | None:
        cpus_block = payload.get("cpus")
        if isinstance(cpus_block, dict) and isinstance(cpus_block.get("itens_eap"), list):
            return "canonical.cpus.itens_eap"
        if isinstance(payload.get("eap"), list):
            return "historical.eap_root"
        skill_inputs = payload.get("skill_inputs")
        if isinstance(skill_inputs, dict):
            escopo = skill_inputs.get("01-escopo-e-eap")
            if isinstance(escopo, dict):
                if isinstance(escopo.get("eap"), list):
                    return "historical.skill_inputs.01-escopo-e-eap.eap"
                nested = escopo.get("inputs_escopo")
                if isinstance(nested, dict) and isinstance(nested.get("eap"), list):
                    return "historical.skill_inputs.01-escopo-e-eap.inputs_escopo.eap"
        return None

    def _validate_benchmark_reference_contract(self, payload: dict[str, Any]) -> None:
        """Enforce canonical benchmark reference contract for EAP.

        Sprint 3 (NEP-026): historical EAP paths are no longer accepted.
        """
        source = self._resolve_eap_source(payload)
        if source is None:
            cpus_block = payload.get("cpus") if isinstance(payload.get("cpus"), dict) else {}
            cpus_block.setdefault("itens_eap", [])
            payload["cpus"] = cpus_block
            return

        if source != "canonical.cpus.itens_eap":
            logger.error(
                "VAL-CONTRACT-EAP-HISTORICO-BLOQUEADO: source=%s action=reject_historical_payload",
                source,
            )
            raise ValueError(
                "VAL-CONTRACT-EAP-HISTORICO-BLOQUEADO: use somente 'cpus.itens_eap' no benchmark_reference."
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
        benchmark_source = "benchmark_reference.json"
        if not isinstance(payload, dict):
            raise ValueError("Referencia de benchmark invalida.")

        # Backward compatibility: hydrate missing sections from project runtime state.
        if not isinstance(payload.get("skill_inputs"), dict):
            skill_inputs = project.read_json(self._files.skill_inputs, {})
            if isinstance(skill_inputs, dict):
                payload["skill_inputs"] = skill_inputs

        if not _is_valid_canonical_eap(payload):
            eap_items = project.read_json(self._files.eap_items, [])
            if isinstance(eap_items, list) and eap_items:
                canonical_items: list[dict[str, Any]] = []
                seen_item_ids: set[str] = set()
                for idx, row in enumerate(eap_items, start=1):
                    if not isinstance(row, dict):
                        continue
                    normalized = self._normalize_eap_item(row, ordem_padrao=idx)
                    if normalized is None:
                        continue
                    item_id = normalized["item_id"]
                    if item_id in seen_item_ids:
                        continue
                    seen_item_ids.add(item_id)
                    canonical_items.append(normalized)
                if canonical_items:
                    cpus_block = payload.get("cpus") if isinstance(payload.get("cpus"), dict) else {}
                    cpus_block["itens_eap"] = canonical_items
                    payload["cpus"] = cpus_block
                    benchmark_source = "eap_items->cpus.itens_eap"

        source = self._resolve_eap_source(payload)
        if source and source != "canonical.cpus.itens_eap":
            historical_rows = _extract_historical_eap_rows(payload)
            canonical_items: list[dict[str, Any]] = []
            seen_item_ids: set[str] = set()
            for idx, row in enumerate(historical_rows, start=1):
                normalized = self._normalize_eap_item(row, ordem_padrao=idx)
                if normalized is None:
                    continue
                item_id = normalized["item_id"]
                if item_id in seen_item_ids:
                    continue
                seen_item_ids.add(item_id)
                canonical_items.append(normalized)
            if canonical_items:
                cpus_block = payload.get("cpus") if isinstance(payload.get("cpus"), dict) else {}
                cpus_block["itens_eap"] = canonical_items
                payload["cpus"] = cpus_block
                benchmark_source = f"{source}->cpus.itens_eap"

        if not _is_valid_canonical_eap(payload):
            canonical = project.load_canonical()
            if canonical is not None:
                eap_rows = _canonical_eap_to_rows(canonical)
                if eap_rows:
                    cpus_block = payload.get("cpus") if isinstance(payload.get("cpus"), dict) else {}
                    cpus_block["itens_eap"] = eap_rows
                    payload["cpus"] = cpus_block
                    benchmark_source = "canonical.eap->cpus.itens_eap"

        if not _is_valid_canonical_eap(payload):
            historical_rows, historical_version = _latest_version_with_eap(project)
            if historical_rows:
                cpus_block = payload.get("cpus") if isinstance(payload.get("cpus"), dict) else {}
                cpus_block["itens_eap"] = historical_rows
                payload["cpus"] = cpus_block
                benchmark_source = f"historical_canonical.eap:{historical_version or 'unknown'}->cpus.itens_eap"

        if _catalog_is_deficit(payload.get("catalog")):
            _enrich_payload_catalog(payload, project)
        _enrich_payload_encargos(payload, project)
        _enrich_payload_bdi(payload)
        self._validate_benchmark_reference_contract(payload)
        payload["_debug"] = {
            **_debug_storage_info(project),
            "eap_source": self._resolve_eap_source(payload) or "none",
            "benchmark_reference_source": benchmark_source,
        }
        return payload
