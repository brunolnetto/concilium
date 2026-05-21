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
    from concilium.application.services.project_repository import ProjectHandle

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
        individual = cat_base / subdir / f"{item_id}.json"
        if individual.exists():
            try:
                return json.loads(individual.read_text(encoding="utf-8"))
            except Exception:
                pass

        # Aggregate file
        agg = cat_base / f"{subdir}.json"
        if agg.exists():
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
        jur_overlay = self._load_jurisdiction_overlay(jurisdicao_id or "")
        jur_cpus = jur_overlay.get("cpus", {})
        jur_insumos = jur_overlay.get("insumos", {})

        # CPUs: apply jurisdiction then project
        resolved_cpus: list[dict] = []
        cpu_ids_processed: set[str] = set()
        for cpu in resolved.get("cpus", []):
            cid = cpu.get("codigo", "")
            if not cid:
                continue
            source: OverlaySource = "master"
            item = dict(cpu)
            if cid in jur_cpus:
                item = _deep_merge(item, jur_cpus[cid])
                source = "jurisdiction"
            if cid in proj_cpu_overlay:
                item = _deep_merge(item, proj_cpu_overlay[cid])
                source = "project"
            resolved_cpus.append(item)
            cpu_ids_processed.add(cid)
            trace.record(cid, source)

        # Project-only CPUs (not in master)
        for cid, cpu_data in proj_cpu_overlay.items():
            if cid not in cpu_ids_processed:
                resolved_cpus.append(cpu_data)
                trace.record(cid, "project")

        resolved["cpus"] = resolved_cpus

        # Insumos
        resolved_insumos: list[dict] = []
        insumo_ids_processed: set[str] = set()
        for ins in resolved.get("insumos", []):
            iid = ins.get("id") or ins.get("codigo", "")
            if not iid:
                continue
            source = "master"
            item = dict(ins)
            if iid in jur_insumos:
                item = _deep_merge(item, jur_insumos[iid])
                source = "jurisdiction"
            if iid in proj_insumo_overlay:
                item = _deep_merge(item, proj_insumo_overlay[iid])
                source = "project"
            resolved_insumos.append(item)
            insumo_ids_processed.add(iid)
            trace.record(iid, source)
        for iid, ins_data in proj_insumo_overlay.items():
            if iid not in insumo_ids_processed:
                resolved_insumos.append(ins_data)
                trace.record(iid, "project")
        resolved["insumos"] = resolved_insumos

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


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Merge: overlay vence em campos escalares; dicts são mesclados recursivamente."""
    result = dict(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and k in result and isinstance(result[k], dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result
