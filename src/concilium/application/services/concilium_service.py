from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

from concilium.application.benchmarks.execution.batch import discover_benchmark_slugs
from concilium.application.runtime import Runtime
from concilium.application.services.pipeline_service import PipelineService
from concilium.application.services.project.audit_service import AuditService
from concilium.application.services.project.override_service import OverrideService
from concilium.application.services.project.project_input_builder import ProjectInputBuilder
from concilium.application.services.project.project_repository import ProjectRepository
from concilium.application.services.project.project_service import ProjectService

from ._concilium_service_helpers import (
    _cs_get_enriched_cpus,
    _cs_simulate_mobilizacao_policy,
    _cs_upsert_catalog_cpu,
    _cs_validate_mobilizacao_policies,
    _enrich_cpus_with_producao,
)
from .catalog.catalog_reasonability import build_catalog_reasonability_artifact


@dataclass(frozen=True)
class ConciliumDependencies:
    input_builder: ProjectInputBuilder
    repository: ProjectRepository
    project_service: ProjectService
    override_service: OverrideService
    pipeline_service: PipelineService
    audit_service: AuditService
    benchmarks_root: Path


class ConciliumService:
    def __init__(self, dependencies: ConciliumDependencies) -> None:
        self._dependencies = dependencies
        # Cache: catalog_id → (bundle_mtime_ns, enriched_cpus)
        # Invalidated automatically when the bundle file is replaced (ADR-067 bust).
        self._enriched_cache: dict[str, tuple[int, list[dict[str, Any]]]] = {}

    @property
    def config_root(self) -> Path:
        return self._dependencies.input_builder._config_root  # type: ignore[attr-defined]

    # ── Global master catalog (ADR-066) ──────────────────────────────────────

    # ── Master catalog write (ADR-067) ───────────────────────────────────────

    def upsert_catalog_cpu(
        self,
        catalog_id: str,
        cpu_id: str,
        cpu_data: dict[str, Any],
        actor: str = "system",
        motivo: str = "",
    ) -> dict[str, Any]:
        """Create or replace a CPU in the master catalog (ADR-067)."""
        return _cs_upsert_catalog_cpu(self, catalog_id, cpu_id, cpu_data, actor, motivo)

    def list_catalogs(self) -> list[dict[str, Any]]:
        cats_dir = self.config_root / "catalogos"
        if not cats_dir.exists():
            return []
        return sorted(
            [{"id": d.name} for d in cats_dir.iterdir() if d.is_dir() and not d.name.startswith(".")],
            key=lambda x: x["id"],
        )

    def get_catalog(self, catalog_id: str) -> dict[str, Any]:

        rt = Runtime(self.config_root)
        cat = rt.load_catalogo(catalog_id)
        return {
            "id": catalog_id,
            "n_cpus": len(cat.get("cpus", [])),
            "n_insumos": len(cat.get("insumos", [])),
            "n_producoes": len(cat.get("producoes", [])),
        }

    def _get_enriched_cpus(self, catalog_id: str) -> list[dict[str, Any]]:
        return _cs_get_enriched_cpus(self, catalog_id)

    @staticmethod
    def _enrich_cpus_with_producao(cat: dict) -> list[dict[str, Any]]:
        return _enrich_cpus_with_producao(cat)

    def list_catalog_cpus(self, catalog_id: str, q: str | None = None, limit: int = 50) -> dict[str, Any]:
        cpus = self._get_enriched_cpus(catalog_id)
        if q:
            q_lower = q.lower()
            cpus = [
                c
                for c in cpus
                if q_lower in (c.get("codigo") or "").lower() or q_lower in (c.get("descricao") or "").lower()
            ]
        return {"catalog_id": catalog_id, "items": cpus[:limit], "total": len(cpus)}

    def get_catalog_cpu(self, catalog_id: str, cpu_id: str) -> dict[str, Any] | None:
        for cpu in self._get_enriched_cpus(catalog_id):
            if cpu.get("codigo") == cpu_id:
                return cpu
        return None

    def list_catalog_insumos(self, catalog_id: str, q: str | None = None, limit: int = 50) -> dict[str, Any]:

        rt = Runtime(self.config_root)
        cat = rt.load_catalogo(catalog_id)
        insumos = cat.get("insumos", [])
        if q:
            q_lower = q.lower()
            insumos = [
                i
                for i in insumos
                if q_lower in (i.get("codigo") or "").lower() or q_lower in (i.get("descricao") or "").lower()
            ]
        return {"catalog_id": catalog_id, "items": insumos[:limit], "total": len(insumos)}

    def search_catalog(self, q: str, catalog_id: str | None = None, limit: int = 20) -> dict[str, Any]:
        results: list[dict] = []
        cats = [catalog_id] if catalog_id else [d["id"] for d in self.list_catalogs()]
        q_lower = q.lower()
        for cid in cats:
            try:
                self._search_catalog_in(cid, q_lower, results, limit)
            except Exception as e:
                logger.warning("Falha ao buscar no catálogo %s: %s", cid, e, exc_info=True)
                continue
            if len(results) >= limit:
                break
        return {"q": q, "items": results[:limit], "total": len(results)}

    def audit_catalog_reasonability(self, catalog_id: str) -> dict[str, Any]:

        rt = Runtime(self.config_root)
        cat = rt.load_catalogo(catalog_id)
        cpus = cat.get("cpus") if isinstance(cat.get("cpus"), list) else []
        produtividades = cat.get("produtividades") if isinstance(cat.get("produtividades"), list) else []
        producoes_legado = cat.get("producoes") if isinstance(cat.get("producoes"), list) else []
        producoes = produtividades + producoes_legado
        return build_catalog_reasonability_artifact(catalog_id, cpus, producoes)

    def _search_catalog_in(self, cid: str, q_lower: str, results: list, limit: int) -> None:
        for cpu in self._get_enriched_cpus(cid):
            codigo = (cpu.get("codigo") or "").lower()
            descricao = (cpu.get("descricao") or "").lower()
            if q_lower in codigo or q_lower in descricao:
                results.append({**cpu, "_catalog_id": cid})
            if len(results) >= limit:
                break

    def extend_cpu(self, project_id: str, cpu_id: str, cpu_data: dict, actor: str = "system", motivo: str = "") -> None:
        self._dependencies.override_service.extend_cpu(project_id, cpu_id, cpu_data, actor=actor, motivo=motivo)

    def get_project_catalog_overrides(self, project_id: str) -> dict:
        """Return the current CPU overlay dict for a project (ADR-066)."""
        project = self._dependencies.repository.get_project(project_id)
        overlay = project.read_json("overrides/cpus_overlay.json", {})
        return overlay if isinstance(overlay, dict) else {}

    def resolve_cpu(self, project_id: str, cpu_id: str) -> dict | None:
        candidate = self._dependencies.override_service.resolve_cpu(project_id, cpu_id)

        project = self._dependencies.repository.get_project(project_id)
        master_cpu = None
        for catalog_id in self._candidate_catalog_ids(project):
            try:
                master_cpu = self.get_catalog_cpu(catalog_id, cpu_id)
            except Exception as e:
                logger.error("Falha ao resolver CPU %s no catálogo %s: %s", cpu_id, catalog_id, e, exc_info=True)
                master_cpu = None
            if master_cpu:
                break

        if candidate and master_cpu:
            # Preserve project-level fields while inheriting richer master composition.
            return {**master_cpu, **candidate}
        if candidate:
            enriched_candidate = self._enrich_cpu_from_producao(project, dict(candidate))
            return enriched_candidate
        if master_cpu:
            return master_cpu
        return candidate

    def _candidate_catalog_ids(self, project: Any) -> list[str]:
        """Resolve possible catalog IDs for project CPU enrichment."""
        meta = project.meta if isinstance(project.meta, dict) else {}
        ids: list[str] = []

        base_catalog = str(meta.get("catalogo_base") or "").strip()
        if base_catalog:
            ids.append(base_catalog)

        contexto_catalog = self._resolve_project_catalog_id(project)
        if contexto_catalog:
            ids.append(contexto_catalog)

        contexto_id = str(meta.get("contexto_id") or "").strip()
        if contexto_id:
            ids.append(contexto_id)

        dedup: list[str] = []
        seen: set[str] = set()
        for cid in ids:
            if cid and cid not in seen:
                seen.add(cid)
                dedup.append(cid)
        return dedup

    def _enrich_cpu_from_producao(self, project: Any, cpu: dict[str, Any]) -> dict[str, Any]:
        """Inject producao_horaria/equipe from catalog produtividade when CPU is sparse."""
        if cpu.get("equipe") and cpu.get("producao_horaria") is not None:
            return cpu

        prod_id = str(cpu.get("producao_id_ref") or cpu.get("producao_id") or "").strip()
        if not prod_id:
            return cpu

        for catalog_id in self._candidate_catalog_ids(project):
            prod = self._get_catalog_producao(catalog_id, prod_id)
            if not prod:
                continue
            if cpu.get("producao_horaria") is None and prod.get("valor_horario") is not None:
                cpu["producao_horaria"] = prod.get("valor_horario")
            if not cpu.get("equipe"):
                equipe = prod.get("equipe")
                if not isinstance(equipe, dict):
                    equipe = prod.get("composicao_padrao_equipe")
                if isinstance(equipe, dict):
                    cpu["equipe"] = equipe
            if cpu.get("equipe") and cpu.get("producao_horaria") is not None:
                break

        return cpu

    def _get_catalog_producao(self, catalog_id: str, prod_id: str) -> dict[str, Any] | None:

        rt = Runtime(self.config_root)
        cat = rt.load_catalogo(catalog_id)
        for key in ("produtividades", "producoes"):
            rows = cat.get(key)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if isinstance(row, dict) and str(row.get("id") or "") == prod_id:
                    return row
        return None

    def _resolve_project_catalog_id(self, project: Any) -> str | None:
        """Resolve current catalog id for a project via contexto version metadata."""
        meta = project.meta if isinstance(project.meta, dict) else {}
        contexto_id = str(meta.get("contexto_id") or "").strip()
        if not contexto_id:
            return None

        try:
            versions = self._dependencies.project_service.list_contexto_versions(contexto_id)
        except Exception as e:
            logger.error("Falha ao listar versões do contexto %s: %s", contexto_id, e, exc_info=True)
            versions = []
        if not versions:
            return contexto_id

        contexto_version = str(meta.get("contexto_version") or "").strip()
        selected = None
        if contexto_version:
            selected = next((v for v in versions if str(v.get("version") or "") == contexto_version), None)
        if selected is None:
            selected = versions[-1]

        catalog_id = str((selected or {}).get("catalogo_id") or "").strip()
        return catalog_id or contexto_id

    def list_benchmarks(self) -> list[str]:
        return discover_benchmark_slugs(self._dependencies.benchmarks_root)

    def list_projects(self) -> list[dict[str, Any]]:
        return self._dependencies.project_service.list_projects()

    def create_project(self, req: Any, actor: str = "system") -> dict[str, Any]:
        prepared = self._dependencies.input_builder.prepare(req)
        return self._dependencies.project_service.create_project(
            req,
            prepared.inputs_escopo,
            prepared.skill_inputs,
            prepared.benchmark_slug,
            prepared.benchmark_reference,
            actor=actor,
            contexto_version=prepared.contexto_version,  # ADR-062
            perfil_id=prepared.perfil_id,  # ADR-062
            perfil_version=prepared.perfil_version,  # ADR-062
        )

    def get_project(self, project_id: str) -> dict[str, Any]:
        return self._dependencies.project_service.get_project(project_id)

    def delete_project(self, project_id: str, actor: str = "system") -> dict[str, Any]:
        return self._dependencies.project_service.delete_project(project_id, actor=actor)

    # ── ADR-063: EAP management ───────────────────────────────────────────────

    def get_eap(self, project_id: str) -> dict[str, Any]:
        return self._dependencies.project_service.get_eap(project_id)

    def upsert_eap(self, project_id: str, eap_items: list[dict[str, Any]], actor: str = "system") -> dict[str, Any]:
        return self._dependencies.project_service.upsert_eap(project_id, eap_items, actor=actor)

    def patch_project_config(self, project_id: str, updates: dict[str, Any], actor: str = "system") -> dict[str, Any]:
        return self._dependencies.project_service.patch_project_config(project_id, updates, actor=actor)

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

    # ── ADR-065: Temas ────────────────────────────────────────────────────────

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

    # ── ADR-066: Jurisdiction overlays ───────────────────────────────────────

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

    def run_project(
        self,
        project_id: str,
        *,
        base_version: str | None,
        fork_version: bool,
        procurement_intent: str | None = None,
        skill_inputs_override: dict[str, dict[str, Any]],
        use_saved_overrides: bool,
        use_mobilizacao_policy: bool,
        use_strict_catalog_baseline: bool,
        actor: str = "system",
    ) -> dict[str, Any]:
        return self._dependencies.pipeline_service.run_project(
            project_id,
            base_version=base_version,
            fork_version=fork_version,
            procurement_intent=procurement_intent,
            skill_inputs_override=skill_inputs_override,
            use_saved_overrides=use_saved_overrides,
            use_mobilizacao_policy=use_mobilizacao_policy,
            use_strict_catalog_baseline=use_strict_catalog_baseline,
            actor=actor,
        )

    def start_run_project(
        self,
        project_id: str,
        *,
        base_version: str | None,
        fork_version: bool,
        procurement_intent: str | None = None,
        skill_inputs_override: dict[str, dict[str, Any]],
        use_saved_overrides: bool,
        use_mobilizacao_policy: bool,
        use_strict_catalog_baseline: bool,
        actor: str = "system",
    ) -> dict[str, Any]:
        return self._dependencies.pipeline_service.start_run_project(
            project_id,
            base_version=base_version,
            fork_version=fork_version,
            procurement_intent=procurement_intent,
            skill_inputs_override=skill_inputs_override,
            use_saved_overrides=use_saved_overrides,
            use_mobilizacao_policy=use_mobilizacao_policy,
            use_strict_catalog_baseline=use_strict_catalog_baseline,
            actor=actor,
        )

    def list_runs(self, project_id: str) -> list[dict[str, Any]]:
        return self._dependencies.pipeline_service.list_runs(project_id)

    def get_run(self, project_id: str, run_id: str) -> dict[str, Any]:
        return self._dependencies.pipeline_service.get_run(project_id, run_id)

    def list_versions(self, project_id: str) -> list[str]:
        return self._dependencies.project_service.list_versions(project_id)

    def get_version_history(self, project_id: str) -> dict:
        """ADR-119 D3: metadados de autoria de todas as versões."""
        return self._dependencies.project_service.get_version_history(project_id)

    def delete_version(self, project_id: str, version: str, actor: str = "system") -> dict[str, Any]:
        return self._dependencies.project_service.delete_version(project_id, version, actor=actor)

    def compare_versions(self, project_id: str, left_version: str, right_version: str) -> dict[str, Any]:
        return self._dependencies.project_service.compare_versions(project_id, left_version, right_version)

    def fork_version(self, project_id: str, base_version: str, actor: str = "system") -> dict[str, Any]:
        return self._dependencies.project_service.fork_version(project_id, base_version, actor=actor)

    def resolve_run_base_version(self, project_id: str, run_id: str) -> str:
        run = self.get_run(project_id, run_id)
        version = run.get("version")
        if not version:
            raise ValueError(f"Run '{run_id}' ainda não possui versão resolvida.")
        return str(version)

    def list_audit(self, project_id: str, limit: int = 200) -> list[dict[str, Any]]:
        project = self._dependencies.repository.get_project(project_id)
        return self._dependencies.audit_service.list(project, limit=limit)

    def list_overrides(self, project_id: str) -> dict[str, Any]:
        return self._dependencies.override_service.list_overrides(project_id)

    def upsert_override(
        self, project_id: str, skill_id: str, inputs: dict[str, Any], actor: str = "system"
    ) -> dict[str, Any]:
        return self._dependencies.override_service.upsert_override(project_id, skill_id, inputs, actor=actor)

    def delete_override(self, project_id: str, skill_id: str, actor: str = "system") -> dict[str, Any]:
        return self._dependencies.override_service.delete_override(project_id, skill_id, actor=actor)

    def list_artifacts(self, project_id: str, version: str | None) -> dict[str, Any]:
        return self._dependencies.project_service.list_artifacts(project_id, version)

    def get_artifact_bytes(self, project_id: str, version: str | None, kind: str, filename: str) -> tuple[bytes, str]:
        return self._dependencies.project_service.get_artifact_bytes(project_id, version, kind, filename)

    def get_benchmark_reference(self, project_id: str) -> dict[str, Any]:
        return self._dependencies.project_service.get_benchmark_reference(project_id)

    def get_diagnostico_pe(self, project_id: str) -> dict:
        """ADR-060/061: Retorna diagnóstico de PE e backtracking do último run."""
        canonical = self._dependencies.project_service.get_last_canonical(project_id)
        if canonical is None:
            return {"diagnostico_pe": None, "backtracking_pe": None}
        diag = getattr(canonical, "diagnostico_pe", None)
        back = getattr(canonical, "backtracking_pe", None)
        return {
            "diagnostico_pe": diag.to_dict() if diag else None,
            "backtracking_pe": back.to_dict() if back else None,
        }

    def get_calendario_operacional(self, project_id: str, version: str | None = None) -> dict[str, Any]:
        canonical, resolved_version = self._load_canonical_for_version(project_id, version)
        if canonical is None:
            return {"version": resolved_version, "semanas": []}

        semanas: list[dict[str, Any]] = []
        calendario = list(getattr(canonical, "calendario_operacional", []) or [])
        clima_por_semana: dict[str, float] = {}
        total_por_semana: dict[str, float] = {}
        cron = getattr(canonical, "cronograma", None)
        if cron:
            for sa in cron.scheduled_activities:
                for semana_iso, dist in sa.distribuicao_semanal.items():
                    clima_por_semana.setdefault(
                        semana_iso,
                        float(getattr(dist, "fator_clima", getattr(dist, "eficiencia", 1.0)) or 1.0),
                    )
                    total_por_semana.setdefault(
                        semana_iso,
                        float(getattr(dist, "fator_total", getattr(dist, "eficiencia", 1.0)) or 1.0),
                    )

        for row in calendario:
            data = row.model_dump() if hasattr(row, "model_dump") else dict(row)
            semana = str(data.get("semana_iso", ""))
            semanas.append(
                {
                    **data,
                    "fator_clima": round(clima_por_semana.get(semana, 1.0), 4),
                    "fator_total": round(total_por_semana.get(semana, clima_por_semana.get(semana, 1.0)), 4),
                }
            )

        return {"version": resolved_version, "semanas": semanas}

    def simulate_calendario_operacional(
        self,
        project_id: str,
        payload: dict[str, Any],
        version: str | None = None,
    ) -> dict[str, Any]:
        base = self.get_calendario_operacional(project_id, version)
        overrides = dict((payload or {}).get("fator_calendario_semanal", {}) or {})
        simulado: list[dict[str, Any]] = []
        for row in base.get("semanas", []):
            semana = str(row.get("semana_iso", ""))
            _fc = row.get("fator_clima")
            fator_clima = float(_fc if _fc is not None else 1.0)
            _fk_raw = overrides.get(semana, row.get("fator_calendario"))
            fator_cal = float(_fk_raw if _fk_raw is not None else 1.0)
            simulado.append(
                {
                    **row,
                    "fator_calendario": round(fator_cal, 4),
                    "fator_total": round(fator_clima * fator_cal, 4),
                }
            )
        return {"version": base.get("version"), "simulado": simulado}

    def _load_canonical_for_version(self, project_id: str, version: str | None = None):
        """Loads canonical for a specific version (or current when omitted)."""
        repository = getattr(self._dependencies, "repository", None)
        if repository is not None and hasattr(repository, "get_project"):
            try:
                project = repository.get_project(project_id)
                return project.load_canonical(version), (version or project.current_version())
            except Exception:
                pass

        # Compatibilidade com stubs/fluxos legados sem ProjectRepository completo.
        if version is None:
            project_service = getattr(self._dependencies, "project_service", None)
            if project_service is not None and hasattr(project_service, "get_last_canonical"):
                try:
                    return project_service.get_last_canonical(project_id), version
                except Exception:
                    pass

        return None, version

    def get_cubo_analitico(self, project_id: str, version: str | None = None) -> dict[str, Any]:
        """ADR-058/NEP-024: Retorna o cubo analítico e seus agregados derivados."""
        canonical, resolved_version = self._load_canonical_for_version(project_id, version)
        if canonical is None:
            return {"version": resolved_version, "cubo_analitico": None}
        cubo = getattr(canonical, "cubo_analitico", None)
        if cubo is None:
            from concilium.domain.services.analytics.cubo_analitico_builder import CuboAnaliticoBuilder

            cubo = CuboAnaliticoBuilder().build(canonical)
        return {"version": resolved_version, "cubo_analitico": cubo.to_dict() if cubo else None}

    # ── ADR-086: Cubo de Pool Instancial ──────────────────────────────────────
    @staticmethod
    def get_cubo_pool_projection_contract() -> dict[str, Any]:
        """ADR-086 D6.1: contrato navegável das faces do cubo de pool."""
        from concilium.application.services.analytics.cubo_pool_projection import (
            cubo_pool_projection_contract,
        )

        return cubo_pool_projection_contract()

    def get_cubo_pool_projection(
        self,
        project_id: str,
        *,
        version: str | None = None,
        face: str = "instancia_ciclo_vida",
        granularidade: str = "mes",
        top_n: int = 300,
        atividade_id: str | None = None,
        instancia_id: str | None = None,
    ) -> dict[str, Any]:
        """ADR-086 D6.1: projeção honesta e descritiva da decomposição de pool de recursos."""
        from concilium.application.services.analytics.cubo_pool_projection import (
            resolve_cubo_pool_projection,
        )

        canonical, resolved_version = self._load_canonical_for_version(project_id, version)
        if canonical is None:
            return {
                "version": resolved_version,
                "face": face,
                "rows": [],
                "narrativa": [],
                "filtros_aplicados": {},
                "invariantes_ok": True,
                "invariantes_violacoes": [],
            }
        proj = resolve_cubo_pool_projection(
            canonical,
            face=face,
            granularidade=granularidade,
            top_n=top_n,
            atividade_id=atividade_id,
            instancia_id=instancia_id,
        )
        proj["version"] = resolved_version
        return proj

    @staticmethod
    def get_cubo_projection_contract() -> dict[str, Any]:
        faces: dict[str, dict[str, Any]] = {
            "tempo_natureza": {
                "label": "Tempo x natureza",
                "unit_type": "currency_brl",
                "measure_profiles": ["financial_default"],
                "aggregation_modes": ["sum"],
            },
            "tempo_componente": {
                "label": "Tempo x componente BDI",
                "unit_type": "currency_brl",
                "measure_profiles": ["financial_default"],
                "aggregation_modes": ["sum"],
            },
            "categoria_componente": {
                "label": "Categoria x componente BDI",
                "unit_type": "currency_brl",
                "measure_profiles": ["financial_default"],
                "aggregation_modes": ["sum"],
            },
            "atividade_componente": {
                "label": "Atividade x componente BDI",
                "unit_type": "currency_brl",
                "measure_profiles": ["financial_default"],
                "aggregation_modes": ["sum"],
            },
            "diesel_temporal": {
                "label": "Diesel temporal",
                "unit_type": "volume_liter",
                "measure_profiles": ["financial_default"],
                "aggregation_modes": ["sum"],
            },
            "abc_curva": {
                "label": "Curva ABC",
                "unit_type": "currency_brl",
                "measure_profiles": ["abc_custo_direto"],
                "aggregation_modes": ["pareto"],
            },
            "s_curve_custo": {
                "label": "S-curve de custo",
                "unit_type": "currency_brl",
                "measure_profiles": ["financial_default"],
                "aggregation_modes": ["cumulative"],
            },
            "recursos_ativos_tempo": {
                "label": "Recursos ativos no tempo",
                "unit_type": "count",
                "measure_profiles": ["recursos_ativos"],
                "aggregation_modes": ["sum", "count_distinct"],
            },
        }
        return {
            "faces": faces,
            "granularidades": ["semana", "mes", "bimestre", "trimestre", "semestre", "ano"],
            "measure_profiles": ["financial_default", "abc_custo_direto", "recursos_ativos"],
            "aggregation_modes": ["sum", "count_distinct", "cumulative", "pareto"],
            "abc_defaults": {"threshold_a": 0.80, "threshold_b": 0.95},
        }

    @staticmethod
    def _resolve_cubo_projection_rows(
        cubo: Any,
        face: str,
        granularidade: Literal["semana", "mes", "bimestre", "trimestre", "semestre", "ano"],
        top_n: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]], str]:
        from .analytics.cube_projection_views import resolve_cubo_projection_rows

        return resolve_cubo_projection_rows(cubo, face, granularidade, top_n)

    @staticmethod
    def _bucket_from_week_iso(
        week_iso: str,
        granularidade: Literal["semana", "mes", "bimestre", "trimestre", "semestre", "ano"],
    ) -> str:
        from .analytics.cube_projection_views import bucket_from_week_iso

        return bucket_from_week_iso(week_iso, granularidade)

    def _resolve_abc_curva_rows(
        self,
        canonical: Any,
        top_n: int,
        threshold_a: float,
        threshold_b: float,
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]], str, str, dict[str, Any]]:
        from .analytics.cube_projection_views import resolve_abc_curva_rows

        return resolve_abc_curva_rows(canonical, top_n, threshold_a, threshold_b)

    def _resolve_s_curve_rows(
        self,
        canonical: Any,
        granularidade: Literal["semana", "mes", "bimestre", "trimestre", "semestre", "ano"],
        top_n: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]], str, str, dict[str, Any]]:
        from .analytics.cube_projection_views import resolve_s_curve_rows

        return resolve_s_curve_rows(canonical, granularidade, top_n)

    def _resolve_recursos_ativos_rows(
        self,
        canonical: Any,
        granularidade: Literal["semana", "mes", "bimestre", "trimestre", "semestre", "ano"],
        top_n: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]], str, str, dict[str, Any]]:
        from .analytics.cube_projection_views import resolve_recursos_ativos_rows

        return resolve_recursos_ativos_rows(canonical, granularidade, top_n)

    def get_cubo_analitico_projection(
        self,
        project_id: str,
        *,
        version: str | None = None,
        face: str = "tempo_natureza",
        granularidade: Literal["semana", "mes", "bimestre", "trimestre", "semestre", "ano"] = "mes",
        categoria: str | None = None,
        componente_bdi: str | None = None,
        atividade_id: str | None = None,
        top_n: int = 300,
        measure_profile: str | None = None,
        aggregation_mode: str | None = None,
        abc_threshold_a: float = 0.80,
        abc_threshold_b: float = 0.95,
    ) -> dict[str, Any]:
        """ADR-069: Projeções navegáveis do cubo para UX iterativa de filtros."""
        # Validate parameters early — before loading canonical, so callers get
        # immediate errors on invalid face/granularidade regardless of project state.
        allowed_faces = {
            "tempo_natureza",
            "tempo_componente",
            "categoria_componente",
            "atividade_componente",
            "diesel_temporal",
            "abc_curva",
            "s_curve_custo",
            "recursos_ativos_tempo",
        }
        contract = self.get_cubo_projection_contract()
        face_specs = contract["faces"]
        allowed_granularidade = set(contract["granularidades"])
        allowed_categoria = {"mao_obra", "equipamento", "diesel", "material"}
        allowed_componentes = {
            "custo_direto",
            "overhead_ac",
            "overhead_df",
            "overhead_r",
            "overhead_cr",
            "margem_l",
            "tributo_cofins",
            "tributo_iss",
            "tributo_pis",
            "tributo_cssl",
            "tributo_ir",
        }
        allowed_measure_profile = set(contract["measure_profiles"])
        allowed_aggregation_mode = set(contract["aggregation_modes"])
        if face not in allowed_faces:
            raise ValueError(f"Face de projeção não suportada: {face}")
        if granularidade not in allowed_granularidade:
            raise ValueError(f"Granularidade inválida: {granularidade}")
        if categoria is not None and categoria not in allowed_categoria:
            raise ValueError(f"Categoria inválida: {categoria}")
        if componente_bdi is not None and componente_bdi not in allowed_componentes:
            raise ValueError(f"Componente BDI inválido: {componente_bdi}")
        if not (0.0 < abc_threshold_a < abc_threshold_b < 1.0):
            raise ValueError("Thresholds ABC inválidos: use 0 < a < b < 1")

        face_measure_profiles_list = list(face_specs[face]["measure_profiles"])
        face_aggregation_modes_list = list(face_specs[face]["aggregation_modes"])
        face_measure_profiles = set(face_measure_profiles_list)
        face_aggregation_modes = set(face_aggregation_modes_list)
        resolved_measure_profile = measure_profile or face_measure_profiles_list[0]
        resolved_aggregation_mode = aggregation_mode or face_aggregation_modes_list[0]
        if resolved_measure_profile not in allowed_measure_profile:
            raise ValueError(f"Measure profile inválido: {resolved_measure_profile}")
        if resolved_aggregation_mode not in allowed_aggregation_mode:
            raise ValueError(f"Aggregation mode inválido: {resolved_aggregation_mode}")
        if resolved_measure_profile not in face_measure_profiles:
            raise ValueError(f"Measure profile inválido para a face: {resolved_measure_profile} em {face}")
        if resolved_aggregation_mode not in face_aggregation_modes:
            raise ValueError(f"Aggregation mode inválido para a face: {resolved_aggregation_mode} em {face}")

        canonical, resolved_version = self._load_canonical_for_version(project_id, version)
        if canonical is None:
            return {
                "version": resolved_version,
                "face": face,
                "granularidade": granularidade,
                "rows": [],
                "filtros_aplicados": {},
            }
        cubo = getattr(canonical, "cubo_analitico", None)
        if cubo is None:
            from concilium.domain.services.analytics.cubo_analitico_builder import CuboAnaliticoBuilder

            cubo = CuboAnaliticoBuilder().build(canonical)

        bounded_top_n = max(1, min(int(top_n), 2000))
        cubo_filtrado = cubo.slice(categoria=categoria, atividade_id=atividade_id, componente_bdi=componente_bdi)

        from .analytics.cube_projection_views import build_cube_projection_payload

        projection_payload = build_cube_projection_payload(
            canonical=canonical,
            cubo=cubo_filtrado,
            face=face,
            granularidade=granularidade,
            top_n=bounded_top_n,
            abc_threshold_a=abc_threshold_a,
            abc_threshold_b=abc_threshold_b,
        )
        rows = projection_payload["rows"]
        columns = projection_payload["columns"]
        chart_hint = str(projection_payload["chart_hint"])
        unit_type = str(projection_payload["unit_type"])
        operator_meta = projection_payload["operator_meta"]

        return {
            "version": resolved_version,
            "face": face,
            "granularidade": granularidade,
            "measure_profile": resolved_measure_profile,
            "aggregation_mode": resolved_aggregation_mode,
            "unit_type": unit_type,
            "chart_hint": chart_hint,
            "columns": columns,
            "operator_meta": operator_meta,
            "filtros_aplicados": {
                "categoria": categoria,
                "componente_bdi": componente_bdi,
                "atividade_id": atividade_id,
                "top_n": bounded_top_n,
            },
            "totais": {
                "total_preco_venda": float(cubo_filtrado.total_preco_venda),
                "total_custo_direto": float(cubo_filtrado.total_custo_direto),
                "total_overhead": float(cubo_filtrado.total_overhead),
                "total_margem": float(cubo_filtrado.total_margem),
                "total_tributos": float(cubo_filtrado.total_tributos),
                "total_consumo_diesel_L": float(cubo_filtrado.total_consumo_diesel_L),
            },
            "rows": rows,
        }

    # ADR-054: Workforce Mobilization Policy methods

    def get_mobilizacao_policies(self, project_id: str) -> dict[str, Any]:
        return self._dependencies.override_service.get_mobilizacao_policies(project_id)

    def upsert_mobilizacao_policy(
        self, project_id: str, item_id: str, policy_data: dict[str, Any], actor: str = "system"
    ) -> None:
        self._dependencies.override_service.upsert_mobilizacao_policy(project_id, item_id, policy_data, actor=actor)

    def delete_mobilizacao_policy(self, project_id: str, item_id: str, actor: str = "system") -> None:
        self._dependencies.override_service.delete_mobilizacao_policy(project_id, item_id, actor=actor)

    def simulate_mobilizacao_policy(self, project_id: str, req: dict[str, Any]) -> dict[str, Any]:
        return _cs_simulate_mobilizacao_policy(project_id, req)

    def validate_mobilizacao_policies(self, project_id: str) -> list[dict[str, Any]]:
        return _cs_validate_mobilizacao_policies(self, project_id)

    def get_deliverables_config(self, project_id: str) -> dict[str, Any]:
        return self._dependencies.override_service.get_deliverables_config(project_id)

    def put_deliverables_config(self, project_id: str, config: dict[str, Any], actor: str = "system") -> dict[str, Any]:
        return self._dependencies.override_service.put_deliverables_config(project_id, config, actor=actor)
