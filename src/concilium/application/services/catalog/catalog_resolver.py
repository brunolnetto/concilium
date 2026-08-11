"""ADR-066: CatalogResolver — resolução em três camadas.

Precedência: Master catalog → JurisdictionOverlay → ProjectOverlay
O resultado é determinístico e auditado via CatalogResolutionTrace.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from concilium.application.services.project.project_repository import ProjectHandle

OverlaySource = Literal["master", "jurisdiction", "project"]
ItemType = Literal["cpu", "insumo", "producao"]


@dataclass
class CatalogResolutionTrace:
    """Registra de qual camada cada item veio."""

    items: dict[str, OverlaySource] = field(default_factory=dict)

    def record(self, item_id: str, source: OverlaySource) -> None:
        self.items[item_id] = source

    def to_dict(self) -> dict[str, str]:
        return dict(self.items)


class CatalogResolver:
    """Serviço de resolução de catálogo em três camadas (ADR-066).

    Instanciar por request/run — não manter estado entre execuções.
    """

    def __init__(self, config_root: Path) -> None:
        self._config_root = Path(config_root)
        self._overlay_cache: dict[str, dict] = {}

    # ── Leitura de overlays ───────────────────────────────────────────────────

    def _load_project_cpu_overlay(self, project: ProjectHandle) -> dict[str, Any]:
        """Carrega overlay de CPUs do projeto (ADR-066)."""
        key = f"proj_cpu:{project.meta.get('id', '')}"
        if key in self._overlay_cache:
            return self._overlay_cache[key]

        try:
            raw = project.read_json("overrides/cpus_overlay.json", {})
            result = raw if isinstance(raw, dict) else {}
        except Exception:
            result = {}
        self._overlay_cache[key] = result
        return result

    def _load_project_insumo_overlay(self, project: ProjectHandle) -> dict[str, Any]:
        key = f"proj_insumo:{project.meta.get('id', '')}"
        if key in self._overlay_cache:
            return self._overlay_cache[key]
        try:
            raw = project.read_json("overrides/insumos_overlay.json", {})
            result = raw if isinstance(raw, dict) else {}
        except Exception:
            result = {}
        self._overlay_cache[key] = result
        return result

    def _load_project_producao_overlay(self, project: ProjectHandle) -> dict[str, Any]:
        """Carrega overlay de produções do projeto — calibra custo_hora_total_referencia por projeto."""
        key = f"proj_producao:{project.meta.get('id', '')}"
        if key in self._overlay_cache:
            return self._overlay_cache[key]
        try:
            raw = project.read_json("overrides/producoes_overlay.json", {})
            result = raw if isinstance(raw, dict) else {}
        except Exception:
            result = {}
        self._overlay_cache[key] = result
        return result

    def _load_jurisdiction_overlay(self, jurisdicao_id: str) -> dict[str, Any]:
        """Carrega overlay de jurisdição (ADR-066 §F6)."""
        key = f"jur:{jurisdicao_id}"
        if key in self._overlay_cache:
            return self._overlay_cache[key]

        path = self._config_root / "jurisdicoes" / jurisdicao_id / "overlay.json"
        if not path.exists():
            self._overlay_cache[key] = {}
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            result = data if isinstance(data, dict) else {}
        except Exception:
            result = {}
        self._overlay_cache[key] = result
        return result

    # ── Resolução individual ──────────────────────────────────────────────────

    def resolve_cpu(
        self,
        cpu_id: str,
        catalogo_id: str,
        project: ProjectHandle,
        jurisdicao_id: str | None = None,
    ) -> tuple[dict[str, Any] | None, OverlaySource]:
        """Resolve uma CPU com precedência: project > jurisdiction > master.

        Returns:
            (item_dict | None, source)
        """
        # 1. Project overlay (maior prioridade)
        proj_overlay = self._load_project_cpu_overlay(project)
        if cpu_id in proj_overlay:
            return proj_overlay[cpu_id], "project"

        # 2. Jurisdiction overlay
        if jurisdicao_id:
            jur_overlay = self._load_jurisdiction_overlay(jurisdicao_id)
            jur_cpus = jur_overlay.get("cpus", {})
            if cpu_id in jur_cpus:
                return jur_cpus[cpu_id], "jurisdiction"

        # 3. Master catalog
        master = self._resolve_from_master(cpu_id, catalogo_id, "cpu", project)
        if master is not None:
            return master, "master"
        return None, "master"

    def resolve_insumo(
        self,
        insumo_id: str,
        catalogo_id: str,
        project: ProjectHandle,
        jurisdicao_id: str | None = None,
    ) -> tuple[dict[str, Any] | None, OverlaySource]:
        # 1. Project overlay
        proj_overlay = self._load_project_insumo_overlay(project)
        if insumo_id in proj_overlay:
            return proj_overlay[insumo_id], "project"

        # 2. Jurisdiction overlay
        if jurisdicao_id:
            jur_overlay = self._load_jurisdiction_overlay(jurisdicao_id)
            jur_insumos = jur_overlay.get("insumos", {})
            if insumo_id in jur_insumos:
                return jur_insumos[insumo_id], "jurisdiction"

        # 3. Master
        master = self._resolve_from_master(insumo_id, catalogo_id, "insumo", project)
        if master is not None:
            return master, "master"
        return None, "master"

    def _resolve_from_master(
        self,
        item_id: str,
        catalogo_id: str,
        item_type: str,
        project: ProjectHandle,
    ) -> dict[str, Any] | None:
        """Resolve item do master catalog — individual file → aggregate → project snapshot."""
        concilium_root = Path(project.root).parents[1]
        cat_base = concilium_root / "config" / "catalogos" / catalogo_id
        subdir = "cpus" if item_type == "cpu" else "insumos"
        result = _rfm_try_individual(cat_base, subdir, item_id)
        if result is not None:
            return result
        return _rfm_try_aggregate(cat_base, subdir, item_id)

    # ── Resolução do catálogo completo para um run ────────────────────────────

    def apply_overlays(
        self,
        master_catalog: dict[str, Any],
        project: ProjectHandle,
        jurisdicao_id: str | None = None,
    ) -> tuple[dict[str, Any], CatalogResolutionTrace]:
        """Aplica jurisdiction + project overlays sobre o catálogo master carregado.

        Retorna (catálogo resolvido, trace de origem por item).
        """
        import copy

        trace = CatalogResolutionTrace()
        resolved = copy.deepcopy(master_catalog)

        proj_cpu_overlay = self._load_project_cpu_overlay(project)
        proj_insumo_overlay = self._load_project_insumo_overlay(project)
        proj_producao_overlay = self._load_project_producao_overlay(project)
        jur_overlay = self._load_jurisdiction_overlay(jurisdicao_id or "")
        jur_cpus = jur_overlay.get("cpus", {})
        jur_insumos = jur_overlay.get("insumos", {})
        jur_producoes = jur_overlay.get("producoes", {})

        resolved["cpus"] = _resolve_catalog_items(resolved.get("cpus", []), "codigo", jur_cpus, proj_cpu_overlay, trace)
        resolved["insumos"] = _resolve_catalog_items(
            resolved.get("insumos", []), None, jur_insumos, proj_insumo_overlay, trace
        )
        # Producoes: override de custo_hora_total_referencia por projeto (NEP-029)
        for key_field in ("producoes", "produtividades"):
            if resolved.get(key_field):
                resolved[key_field] = _resolve_catalog_items(
                    resolved[key_field], "id", jur_producoes, proj_producao_overlay, trace
                )
        return resolved, trace

    def build_resolved_catalog(
        self,
        master_catalog: dict[str, Any],
        project: ProjectHandle,
        jurisdicao_id: str | None,
        eap_cpu_ids: set[str] | None = None,
    ) -> tuple[dict[str, Any], CatalogResolutionTrace]:
        """Resolve e filtra o catálogo para apenas os itens usados por este run.

        eap_cpu_ids: conjunto de cpu_ids referenciados pela EAP do projeto.
                     None → inclui todos (full catalog, sem filtro).
        """
        resolved, trace = self.apply_overlays(master_catalog, project, jurisdicao_id)

        if eap_cpu_ids is not None:
            resolved["cpus"] = [c for c in resolved.get("cpus", []) if c.get("codigo") in eap_cpu_ids]

        return resolved, trace


def _rfm_try_individual(cat_base, subdir: str, item_id: str):
    individual = cat_base / subdir / f"{item_id}.json"
    if individual.exists():
        try:
            return json.loads(individual.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def _rfm_try_aggregate(cat_base, subdir: str, item_id: str):
    agg = cat_base / f"{subdir}.json"
    if not agg.exists():
        return None
    try:
        data = json.loads(agg.read_text(encoding="utf-8"))
        items = data.get(subdir, data) if isinstance(data, dict) else data
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict) and it.get("codigo") == item_id:
                    return it
    except Exception:
        pass
    return None


def _resolve_catalog_items(
    items: list,
    id_key: str | None,
    jur_overlay: dict,
    proj_overlay: dict,
    trace: CatalogResolutionTrace,
) -> list:
    resolved_items = []
    ids_processed: set = set()
    for it in items:
        iid = it.get(id_key, "") if id_key else (it.get("id") or it.get("codigo", ""))
        if not iid:
            continue
        source = "master"
        item = dict(it)
        if iid in jur_overlay:
            item = _deep_merge(item, jur_overlay[iid])
            source = "jurisdiction"
        if iid in proj_overlay:
            item = _deep_merge(item, proj_overlay[iid])
            source = "project"
        resolved_items.append(item)
        ids_processed.add(iid)
        trace.record(iid, source)
    for iid, data in proj_overlay.items():
        # isinstance(..., dict): overlay de projeto malformado (ex.: uma sugestão/placeholder
        # de texto gravada onde deveria ir o dict completo do item) não pode injetar uma
        # string solta na lista de itens resolvidos — isso propagava AttributeError mais
        # a jusante (skill-05: ('str' object has no attribute 'get')) num ponto bem mais
        # difícil de diagnosticar do que aqui, na origem da resolução.
        if iid not in ids_processed and isinstance(data, dict):
            resolved_items.append(data)
            trace.record(iid, "project")
    return resolved_items


def _deep_merge(base: dict, overlay: Any) -> dict:
    """Merge: overlay vence em campos escalares; dicts são mesclados recursivamente.

    `overlay` não-dict (dado malformado — ver `_resolve_catalog_items`) é ignorado:
    mantém `base` intacto em vez de propagar AttributeError em `overlay.items()`.
    """
    if not isinstance(overlay, dict):
        return dict(base)
    result = dict(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and k in result and isinstance(result[k], dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result
