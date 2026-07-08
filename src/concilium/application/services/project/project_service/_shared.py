"""ProjectService — funções auxiliares compartilhadas (parte extraída de project_service.py)."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_REF_YYYY_MM_RE = re.compile(r"^\d{4}-\d{2}$")


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


def _ps_build_list_item(project: Any) -> dict[str, Any]:
    """Monta o item de list_projects() para um único ProjectHandle (1 unidade de trabalho paralela)."""
    meta = project.meta
    return {
        "project_id": meta.get("id", ""),
        "nome": meta.get("nome", ""),
        "contexto_id": meta.get("contexto_id", ""),
        "tipo_projeto": _resolve_project_type(meta),
        "status_eap": meta.get("status_eap", "ATIVO"),
        "current_version": meta.get("current_version"),
        "versions": project.list_versions(),
        "benchmark_slug": meta.get("benchmark_slug"),
    }


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


def _as_dict_rows(src: Any) -> list[dict[str, Any]] | None:
    """Retorna as linhas dict de `src` se for uma lista, senão None."""
    if isinstance(src, list):
        return [row for row in src if isinstance(row, dict)]
    return None


def _extract_historical_eap_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract historical EAP rows from known payload locations."""
    rows = _as_dict_rows(payload.get("eap"))
    if rows is not None:
        return rows

    skill_inputs = payload.get("skill_inputs")
    if not isinstance(skill_inputs, dict):
        return []
    escopo = skill_inputs.get("01-escopo-e-eap")
    if not isinstance(escopo, dict):
        return []

    rows = _as_dict_rows(escopo.get("eap"))
    if rows is not None:
        return rows

    nested = escopo.get("inputs_escopo")
    if isinstance(nested, dict):
        rows = _as_dict_rows(nested.get("eap"))
        if rows is not None:
            return rows

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


def _cpu_has_equipe_composicao(cpu: Any) -> bool:
    """Verifica se um CPU tem composição de equipe (funções ou equipamentos)."""
    if not isinstance(cpu, dict):
        return False
    equipe = cpu.get("equipe")
    if not isinstance(equipe, dict):
        return False
    return bool((equipe.get("funcoes") or []) or (equipe.get("equipamentos") or []))


def _catalog_is_deficit(catalog: Any) -> bool:
    """Heuristic: catalog is deficit when CPUs exist but none carries team composition."""
    if not isinstance(catalog, dict):
        return True
    cpus = catalog.get("cpus")
    if not isinstance(cpus, list) or not cpus:
        return True
    return not any(_cpu_has_equipe_composicao(cpu) for cpu in cpus)


def _latest_version_with_eap(project: Any) -> tuple[list[dict[str, Any]], str | None]:
    """Return canonical EAP rows from the newest version that contains EAP."""
    versions = list(project.list_versions() or [])
    for version in reversed(versions):
        try:
            canonical = project.load_canonical(version)
        except Exception as e:
            logger.warning("Falha ao carregar canonical da versão %s: %s", version, e, exc_info=True)
            canonical = None
        if canonical is None:
            continue
        rows = _canonical_eap_to_rows(canonical)
        if rows:
            return rows, version
    return [], None


