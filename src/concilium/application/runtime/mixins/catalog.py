"""Mixin de catálogo: carrega, valida e sintetiza catálogos, CPUs, produções e insumos."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from ..deliverables.helpers.insumos import dedup_insumos, ingest_insumos, load_insumos_subdir
from ..exceptions import RuntimeDomainError


class CatalogMixin:
    """Mixin com métodos de resolução e carregamento de catálogos."""

    config_root: Path
    _config_cache: dict[str, Any]
    # ADR-100 Phase 4: CatalogSession cache — reutiliza sessão DuckDB entre skills do mesmo run
    _catalog_session_cache: dict[str, Any]

    def _get_or_create_catalog_session(self, catalogo: dict[str, Any], cache_key: str) -> Any:
        """ADR-100 Phase 4: retorna CatalogSession cacheada ou cria nova.

        A sessão é reutilizada entre todas as skills do mesmo pipeline run,
        evitando recriar as junction tables a cada skill execution.
        """
        try:
            from concilium.infrastructure.catalog.query_engine import CatalogSession, is_available

            if not is_available():
                return None
            if not hasattr(self, "_catalog_session_cache"):
                self._catalog_session_cache = {}
            if cache_key not in self._catalog_session_cache:
                self._catalog_session_cache[cache_key] = CatalogSession.from_resolved(catalogo)
            return self._catalog_session_cache[cache_key]
        except Exception:
            return None

    def load_catalogo(self, catalogo_id: str) -> dict[str, Any]:
        key = f"catalogo:{catalogo_id}"
        if key not in self._config_cache:
            self._config_cache[key] = self._load_catalogo_from_disk(catalogo_id)
        return copy.deepcopy(self._config_cache[key])

    def _resolve_project_catalog_base(self, catalogo_id: str, project: Any) -> tuple[dict[str, Any], str]:
        benchmark_reference = project.read_json("benchmark_reference.json", {})
        if isinstance(benchmark_reference, dict):
            project_catalog = benchmark_reference.get("catalog")
            if isinstance(project_catalog, dict) and project_catalog:
                return copy.deepcopy(project_catalog), "project_reference"
        return self.load_catalogo(catalogo_id), "master"

    def _load_resolved_catalogo(
        self,
        catalogo_id: str,
        jurisdicao_id: str | None,
        project: Any,
        version: str | None = None,
    ) -> dict[str, Any]:
        """ADR-066/NEP-028: load project baseline catalog then apply jurisdiction + project overlays."""
        from concilium.application.services.catalog_resolver import CatalogResolver

        master, _source = self._resolve_project_catalog_base(catalogo_id, project)
        resolver = CatalogResolver(self.config_root)
        resolved, _trace = resolver.apply_overlays(master, project, jurisdicao_id)
        return resolved

    def _load_resolved_catalog_with_provenance(
        self,
        catalogo_id: str,
        jurisdicao_id: str | None,
        project: Any,
        version: str | None = None,
        strict_baseline: bool = False,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        import hashlib
        import json as _json

        from concilium.application.services.catalog_resolver import CatalogResolver

        benchmark_reference = project.read_json("benchmark_reference.json", {})
        project_catalog = benchmark_reference.get("catalog") if isinstance(benchmark_reference, dict) else None
        if strict_baseline and not (isinstance(project_catalog, dict) and project_catalog):
            raise RuntimeDomainError("Baseline de catalogo do projeto nao encontrado para modo estrito.")

        base_catalog, base_source = self._resolve_project_catalog_base(catalogo_id, project)
        resolver = CatalogResolver(self.config_root)
        resolved, trace = resolver.apply_overlays(base_catalog, project, jurisdicao_id)
        base_hash = hashlib.sha256(
            _json.dumps(base_catalog, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
        ).hexdigest()
        provenance = {
            "catalogo_base_origem": base_source,
            "catalogo_base_hash": base_hash,
            "catalogo_base_id": catalogo_id,
            "jurisdicao_id": jurisdicao_id,
            "version": version,
            "strict_baseline": strict_baseline,
            "resolution_trace": trace.to_dict(),
        }
        return resolved, provenance

    def _catalog_bundle_valid(self, cat_dir: Path, bundle_path: Path) -> bool:
        if not bundle_path.exists():
            return False
        try:
            bundle_mtime = bundle_path.stat().st_mtime
            for json_file in cat_dir.rglob("*.json"):
                if json_file.name == ".catalog_bundle.json":
                    continue
                if json_file.stat().st_mtime > bundle_mtime:
                    return False
            return True
        except Exception:
            return False

    @staticmethod
    def _load_cpus_from_cpu_dir(cpu_dir: Path) -> list:
        cpus: list = []
        if not (cpu_dir.exists() and cpu_dir.is_dir()):
            return cpus
        for f in cpu_dir.glob("*.json"):
            try:
                cpu_data = json.loads(f.read_text(encoding="utf-8"))
                if isinstance(cpu_data, list):
                    cpus.extend(cpu_data)
                elif isinstance(cpu_data, dict) and "cpus" in cpu_data:
                    cpus.extend(cpu_data["cpus"])
                else:
                    cpus.append(cpu_data)
            except Exception:
                continue
        return cpus

    @staticmethod
    def _load_cpus_from_json(cpus_file: Path) -> list:
        try:
            cpu_data = json.loads(cpus_file.read_text(encoding="utf-8"))
            if isinstance(cpu_data, list):
                return cpu_data
            if isinstance(cpu_data, dict) and "cpus" in cpu_data:
                return cpu_data["cpus"]
            return []
        except Exception:
            return []

    @staticmethod
    def _load_producoes_from_cat_dirs(cat_dir: Path) -> list:
        producoes: list = []
        for dname in ["producoes", "produtividades"]:
            p_dir = cat_dir / dname
            if p_dir.exists() and p_dir.is_dir():
                for f in p_dir.glob("*.json"):
                    try:
                        p_data = json.loads(f.read_text(encoding="utf-8"))
                        if isinstance(p_data, list):
                            producoes.extend(p_data)
                        elif isinstance(p_data, dict):
                            producoes.append(p_data)
                    except Exception:
                        continue
        return producoes

    @staticmethod
    def _synthesize_missing_producoes(cpus: list, seen_prod_ids: set) -> list:
        result: list = []
        for cpu in cpus:
            prod_id_ref = cpu.get("producao_id_ref")
            producao_horaria = cpu.get("producao_horaria")
            if prod_id_ref and producao_horaria and prod_id_ref not in seen_prod_ids:
                result.append(
                    {
                        "id": prod_id_ref,
                        "valor_horario": float(producao_horaria),
                        "composicao_padrao_equipe": cpu.get("composicao_padrao_equipe"),
                    }
                )
                seen_prod_ids.add(prod_id_ref)
        return result

    @staticmethod
    def _merge_global_producoes(producoes: list, global_prods: list) -> list:
        seen_ids = {p["id"] for p in producoes if "id" in p}
        for gp in global_prods:
            if gp.get("id") not in seen_ids:
                producoes.append(gp)
        return producoes

    def _load_and_synthesize_producoes(self, cpus: list[dict[str, Any]], cat_dir: Path) -> list[dict[str, Any]]:
        producoes = self._load_producoes_from_cat_dirs(cat_dir)
        seen_prod_ids = {p.get("id") for p in producoes if "id" in p}
        synth = self._synthesize_missing_producoes(cpus, seen_prod_ids)
        producoes.extend(synth)
        global_prods = self._load_producoes_from_cpus(cpus, cat_dir)
        return self._merge_global_producoes(producoes, global_prods)

    def _load_catalogo_from_disk(self, catalogo_id: str) -> dict[str, Any]:
        cat_dir = self.config_root / "catalogos" / catalogo_id
        if not cat_dir.exists():
            raise RuntimeDomainError(f"Catálogo '{catalogo_id}' não encontrado em {cat_dir}")

        bundle_path = cat_dir / ".catalog_bundle.json"
        if self._catalog_bundle_valid(cat_dir, bundle_path):
            try:
                return json.loads(bundle_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        catalogo: dict[str, Any] = {"cpus": [], "insumos": [], "templates": {}, "produtividades": []}

        catalogo["cpus"] = self._load_cpus_from_cpu_dir(cat_dir / "cpus")
        if not catalogo["cpus"]:
            cpus_file = cat_dir / "cpus.json"
            if cpus_file.exists():
                catalogo["cpus"] = self._load_cpus_from_json(cpus_file)

        catalogo["insumos"] = self._load_insumos(cat_dir)

        templates_path = cat_dir / "templates.json"
        if templates_path.exists():
            data = json.loads(templates_path.read_text(encoding="utf-8"))
            catalogo["templates"] = data.get("templates", data) if isinstance(data, dict) else {}

        catalogo["producoes"] = self._load_and_synthesize_producoes(catalogo["cpus"], cat_dir)

        try:
            bundle_path.write_text(json.dumps(catalogo, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

        return catalogo

    def _load_producoes_from_cpus(
        self, cpus: list[dict[str, Any]], cat_dir: Path | None = None
    ) -> list[dict[str, Any]]:
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        search_dirs = [self.config_root / "producoes"]
        if cat_dir:
            search_dirs.append(cat_dir / "producoes")
            search_dirs.append(cat_dir / "produtividades")
        for cpu in cpus:
            prod_id = cpu.get("producao_id_ref") or cpu.get("producao_id")
            if not prod_id or prod_id in seen:
                continue
            for p_dir in search_dirs:
                if not p_dir.exists():
                    continue
                path = p_dir / f"{prod_id}.json"
                if path.exists():
                    try:
                        result.append(json.loads(path.read_text(encoding="utf-8")))
                        seen.add(prod_id)
                        break
                    except Exception:
                        continue
        return result

    def _load_insumos(self, cat_dir: Path) -> list[dict[str, Any]]:
        dir_insumos = cat_dir / "insumos"
        if not dir_insumos.exists() or not dir_insumos.is_dir():
            return []
        insumos: list[dict[str, Any]] = []
        for f in dir_insumos.glob("*.json"):
            try:
                ingest_insumos(json.loads(f.read_text(encoding="utf-8")), insumos)
            except Exception:
                pass
        for sub in dir_insumos.iterdir():
            if sub.is_dir():
                load_insumos_subdir(sub, insumos)
        return dedup_insumos(insumos)
