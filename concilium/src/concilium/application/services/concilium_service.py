from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

from concilium.application.benchmarks.batch import discover_benchmark_slugs
from concilium.application.services.audit_service import AuditService
from concilium.application.services.override_service import OverrideService
from concilium.application.services.pipeline_service import PipelineService
from concilium.application.services.project_input_builder import ProjectInputBuilder
from concilium.application.services.project_repository import ProjectRepository
from concilium.application.services.project_service import ProjectService

from ._concilium_service_helpers import (
    _cs_get_enriched_cpus,
    _cs_simulate_mobilizacao_policy,
    _cs_upsert_catalog_cpu,
    _cs_validate_mobilizacao_policies,
    _enrich_cpus_with_producao,
)
from .catalog_reasonability import build_catalog_reasonability_artifact


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
        from concilium.application.runtime import Runtime

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
        from concilium.application.runtime import Runtime

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
            except Exception:
                continue
            if len(results) >= limit:
                break
        return {"q": q, "items": results[:limit], "total": len(results)}

    def audit_catalog_reasonability(self, catalog_id: str) -> dict[str, Any]:
        from concilium.application.runtime import Runtime

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
        return self._dependencies.override_service.resolve_cpu(project_id, cpu_id)

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
        self, perfil_id: str, fields: dict[str, Any], motivo: str, author: str = "system"
    ) -> dict[str, Any]:
        return self._dependencies.project_service.create_perfil_version(perfil_id, fields, motivo, author)

    def compare_perfil_versions(self, perfil_id: str, version_a: str, version_b: str) -> dict[str, Any]:
        return self._dependencies.project_service.compare_perfil_versions(perfil_id, version_a, version_b)

    def list_contextos(self) -> list[dict[str, Any]]:
        return self._dependencies.project_service.list_contextos()

    def list_contexto_versions(self, contexto_id: str) -> list[dict[str, Any]]:
        return self._dependencies.project_service.list_contexto_versions(contexto_id)

    def create_contexto_version(
        self, contexto_id: str, fields: dict[str, Any], motivo: str, author: str = "system"
    ) -> dict[str, Any]:
        return self._dependencies.project_service.create_contexto_version(contexto_id, fields, motivo, author)

    def compare_contexto_versions(self, contexto_id: str, version_a: str, version_b: str) -> dict[str, Any]:
        return self._dependencies.project_service.compare_contexto_versions(contexto_id, version_a, version_b)

    # ── ADR-065: Temas ────────────────────────────────────────────────────────

    def list_temas(self) -> list[dict[str, Any]]:
        return self._dependencies.project_service.list_temas()

    def list_tema_versions(self, tema_id: str) -> list[dict[str, Any]]:
        return self._dependencies.project_service.list_tema_versions(tema_id)

    def create_tema_version(
        self, tema_id: str, fields: dict[str, Any], motivo: str, author: str = "system"
    ) -> dict[str, Any]:
        return self._dependencies.project_service.create_tema_version(tema_id, fields, motivo, author)

    def compare_tema_versions(self, tema_id: str, version_a: str, version_b: str) -> dict[str, Any]:
        return self._dependencies.project_service.compare_tema_versions(tema_id, version_a, version_b)

    # ── ADR-066: Jurisdiction overlays ───────────────────────────────────────

    def list_jurisdicoes(self) -> list[dict[str, Any]]:
        return self._dependencies.project_service.list_jurisdicoes()

    def list_jurisdicao_versions(self, jurisdicao_id: str) -> list[dict[str, Any]]:
        return self._dependencies.project_service.list_jurisdicao_versions(jurisdicao_id)

    def create_jurisdicao_version(
        self, jurisdicao_id: str, fields: dict[str, Any], motivo: str, author: str = "system"
    ) -> dict[str, Any]:
        return self._dependencies.project_service.create_jurisdicao_version(jurisdicao_id, fields, motivo, author)

    def compare_jurisdicao_versions(self, jurisdicao_id: str, version_a: str, version_b: str) -> dict[str, Any]:
        return self._dependencies.project_service.compare_jurisdicao_versions(jurisdicao_id, version_a, version_b)

    def run_project(
        self,
        project_id: str,
        *,
        base_version: str | None,
        fork_version: bool,
        skill_inputs_override: dict[str, dict[str, Any]],
        use_saved_overrides: bool,
        actor: str = "system",
    ) -> dict[str, Any]:
        return self._dependencies.pipeline_service.run_project(
            project_id,
            base_version=base_version,
            fork_version=fork_version,
            skill_inputs_override=skill_inputs_override,
            use_saved_overrides=use_saved_overrides,
            actor=actor,
        )

    def start_run_project(
        self,
        project_id: str,
        *,
        base_version: str | None,
        fork_version: bool,
        skill_inputs_override: dict[str, dict[str, Any]],
        use_saved_overrides: bool,
        actor: str = "system",
    ) -> dict[str, Any]:
        return self._dependencies.pipeline_service.start_run_project(
            project_id,
            base_version=base_version,
            fork_version=fork_version,
            skill_inputs_override=skill_inputs_override,
            use_saved_overrides=use_saved_overrides,
            actor=actor,
        )

    def list_runs(self, project_id: str) -> list[dict[str, Any]]:
        return self._dependencies.pipeline_service.list_runs(project_id)

    def get_run(self, project_id: str, run_id: str) -> dict[str, Any]:
        return self._dependencies.pipeline_service.get_run(project_id, run_id)

    def list_versions(self, project_id: str) -> list[str]:
        return self._dependencies.project_service.list_versions(project_id)

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
            from concilium.domain.services.cubo_analitico_builder import CuboAnaliticoBuilder

            cubo = CuboAnaliticoBuilder().build(canonical)
        return {"version": resolved_version, "cubo_analitico": cubo.to_dict() if cubo else None}

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
        if face == "tempo_natureza":
            payload = cubo.resumo_por_natureza_temporal(granularidade)
            rows = [
                {"periodo": periodo, "natureza": "direto", "valor_rs": float(vals.get("direto", 0.0))}
                for periodo, vals in payload.items()
            ] + [
                {
                    "periodo": periodo,
                    "natureza": "indireto",
                    "valor_rs": float(vals.get("indireto", 0.0)),
                }
                for periodo, vals in payload.items()
            ]
            rows.sort(key=lambda r: (str(r["periodo"]), str(r["natureza"])))
            columns = [
                {"id": "periodo", "label": "Período", "dtype": "str", "role": "x"},
                {"id": "natureza", "label": "Natureza", "dtype": "str", "role": "series"},
                {"id": "valor_rs", "label": "Valor (R$)", "dtype": "float", "role": "value"},
            ]
            return rows[:top_n], columns, "bar_stacked"

        if face == "tempo_componente":
            payload = cubo.composicao_preco_temporal(granularidade)
            rows: list[dict[str, Any]] = []
            for periodo, comp_dict in payload.items():
                for componente, valor in comp_dict.items():
                    rows.append({"periodo": periodo, "componente_bdi": componente, "valor_rs": float(valor)})
            rows.sort(key=lambda r: (str(r["periodo"]), -float(r["valor_rs"])))
            columns = [
                {"id": "periodo", "label": "Período", "dtype": "str", "role": "x"},
                {"id": "componente_bdi", "label": "Componente BDI", "dtype": "str", "role": "series"},
                {"id": "valor_rs", "label": "Valor (R$)", "dtype": "float", "role": "value"},
            ]
            return rows[:top_n], columns, "line"

        if face == "categoria_componente":
            payload = cubo.composicao_por_categoria()
            rows = [
                {"categoria": categoria, "componente_bdi": comp, "valor_rs": float(valor)}
                for categoria, comp_dict in payload.items()
                for comp, valor in comp_dict.items()
            ]
            rows.sort(key=lambda r: -float(r["valor_rs"]))
            columns = [
                {"id": "categoria", "label": "Categoria", "dtype": "str", "role": "y"},
                {"id": "componente_bdi", "label": "Componente BDI", "dtype": "str", "role": "x"},
                {"id": "valor_rs", "label": "Valor (R$)", "dtype": "float", "role": "value"},
            ]
            return rows[:top_n], columns, "heatmap"

        if face == "atividade_componente":
            grouped = cubo.group_by("atividade_id", "componente_bdi")
            rows = [
                {"atividade_id": atividade_id, "componente_bdi": componente, "valor_rs": float(valor)}
                for (atividade_id, componente), valor in grouped.items()
            ]
            rows.sort(key=lambda r: -float(r["valor_rs"]))
            columns = [
                {"id": "atividade_id", "label": "Atividade", "dtype": "str", "role": "y"},
                {"id": "componente_bdi", "label": "Componente BDI", "dtype": "str", "role": "x"},
                {"id": "valor_rs", "label": "Valor (R$)", "dtype": "float", "role": "value"},
            ]
            return rows[:top_n], columns, "heatmap"

        if face == "diesel_temporal":
            payload = cubo.consumo_diesel_temporal(granularidade)
            rows = [{"periodo": periodo, "consumo_diesel_l": float(valor)} for periodo, valor in payload.items()]
            columns = [
                {"id": "periodo", "label": "Período", "dtype": "str", "role": "x"},
                {"id": "consumo_diesel_l", "label": "Consumo Diesel (L)", "dtype": "float", "role": "value"},
            ]
            return rows[:top_n], columns, "line"

        raise ValueError(f"Face de projeção não suportada: {face}")

    @staticmethod
    def _bucket_from_week_iso(
        week_iso: str,
        granularidade: Literal["semana", "mes", "bimestre", "trimestre", "semestre", "ano"],
    ) -> str:
        if granularidade == "semana":
            return week_iso
        year_str, week_str = week_iso.split("-W", 1)
        anchor = date.fromisocalendar(int(year_str), int(week_str), 1)
        if granularidade == "mes":
            return f"{anchor.year:04d}-{anchor.month:02d}"
        if granularidade == "bimestre":
            bimestre = ((anchor.month - 1) // 2) + 1
            return f"{anchor.year:04d}-B{bimestre}"
        if granularidade == "trimestre":
            trimestre = ((anchor.month - 1) // 3) + 1
            return f"{anchor.year:04d}-T{trimestre}"
        if granularidade == "semestre":
            semestre = ((anchor.month - 1) // 6) + 1
            return f"{anchor.year:04d}-S{semestre}"
        if granularidade == "ano":
            return f"{anchor.year:04d}"
        raise ValueError(f"Granularidade inválida: {granularidade}")

    def _resolve_abc_curva_rows(
        self,
        canonical: Any,
        top_n: int,
        threshold_a: float,
        threshold_b: float,
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]], str, str, dict[str, Any]]:
        from concilium.domain.services.curva_abc_builder import CurvaABCBuilder

        curva = CurvaABCBuilder().build(canonical)
        rows: list[dict[str, Any]] = []
        for item in list(curva.itens)[:top_n]:
            classe = (
                "A"
                if item.pct_custo_acumulado <= threshold_a
                else ("B" if item.pct_custo_acumulado <= threshold_b else "C")
            )
            rows.append(
                {
                    "insumo_id": item.insumo_id,
                    "descricao": item.descricao,
                    "categoria": item.categoria.lower(),
                    "custo_total_rs": float(item.custo_total),
                    "pct_custo": float(item.pct_custo),
                    "pct_custo_acumulado": float(item.pct_custo_acumulado),
                    "classe_abc": classe,
                }
            )
        columns = [
            {"id": "insumo_id", "label": "Insumo", "dtype": "str", "role": "x"},
            {"id": "descricao", "label": "Descrição", "dtype": "str", "role": "label"},
            {"id": "categoria", "label": "Categoria", "dtype": "str", "role": "series"},
            {"id": "custo_total_rs", "label": "Custo Total (R$)", "dtype": "float", "role": "value"},
            {"id": "pct_custo", "label": "% Custo", "dtype": "float", "role": "value_aux"},
            {"id": "pct_custo_acumulado", "label": "% Acumulado", "dtype": "float", "role": "line"},
            {"id": "classe_abc", "label": "Classe ABC", "dtype": "str", "role": "class"},
        ]
        class_counts = {"A": 0, "B": 0, "C": 0}
        for row in rows:
            class_counts[str(row["classe_abc"])] += 1
        operator_meta = {
            "thresholds": {"a": threshold_a, "b": threshold_b},
            "class_counts": class_counts,
            "coverage_a": max((float(r["pct_custo_acumulado"]) for r in rows if r["classe_abc"] == "A"), default=0.0),
        }
        return rows, columns, "bar", "currency_brl", operator_meta

    def _resolve_s_curve_rows(
        self,
        canonical: Any,
        granularidade: Literal["semana", "mes", "bimestre", "trimestre", "semestre", "ano"],
        top_n: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]], str, str, dict[str, Any]]:
        from collections import defaultdict

        from concilium.domain.services.s_curve_builder import SCurveBuilder

        s_curve = SCurveBuilder().build(canonical)
        grouped: dict[str, dict[str, float]] = defaultdict(lambda: {"custo_semanal_rs": 0.0, "custo_acumulado_rs": 0.0})
        for idx, semana_iso in enumerate(s_curve.semanas_iso):
            bucket = self._bucket_from_week_iso(semana_iso, granularidade)
            grouped[bucket]["custo_semanal_rs"] += float(s_curve.custo_semanal[idx])
            grouped[bucket]["custo_acumulado_rs"] += float(s_curve.custo_semanal[idx])
        rows: list[dict[str, Any]] = []
        acum = 0.0
        for bucket in sorted(grouped.keys()):
            custo = float(grouped[bucket]["custo_semanal_rs"])
            acum += custo
            rows.append(
                {
                    "periodo": bucket,
                    "custo_semanal_rs": custo,
                    "custo_acumulado_rs": round(acum, 2),
                    "pct_acumulado": round(acum / float(s_curve.total_projeto), 6)
                    if s_curve.total_projeto > 0
                    else 0.0,
                }
            )
        columns = [
            {"id": "periodo", "label": "Período", "dtype": "str", "role": "x"},
            {"id": "custo_semanal_rs", "label": "Custo no Período (R$)", "dtype": "float", "role": "value"},
            {"id": "custo_acumulado_rs", "label": "Custo Acumulado (R$)", "dtype": "float", "role": "line"},
            {"id": "pct_acumulado", "label": "% Acumulado", "dtype": "float", "role": "line_aux"},
        ]
        return rows[:top_n], columns, "line", "currency_brl", {"total_projeto_rs": float(s_curve.total_projeto)}

    def _resolve_recursos_ativos_rows(
        self,
        canonical: Any,
        granularidade: Literal["semana", "mes", "bimestre", "trimestre", "semestre", "ano"],
        top_n: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]], str, str, dict[str, Any]]:
        from collections import defaultdict

        from concilium.domain.services.s_curve_builder import SCurveBuilder

        s_curve = SCurveBuilder().build(canonical)
        grouped: dict[str, dict[str, float]] = defaultdict(
            lambda: {
                "n_equipes_totais": 0.0,
                "n_equipamentos_unicos": 0.0,
                "equipamentos_unidades_ativas": 0.0,
            }
        )
        for agg in s_curve.agregacao_semanal:
            bucket = self._bucket_from_week_iso(str(agg.semana_iso), granularidade)
            grouped[bucket]["n_equipes_totais"] += float(agg.n_equipes_totais)
            grouped[bucket]["n_equipamentos_unicos"] = max(
                grouped[bucket]["n_equipamentos_unicos"], float(agg.n_equipamentos_unicos)
            )
            grouped[bucket]["equipamentos_unidades_ativas"] += float(sum(agg.equipamentos_ativos.values()))
        rows = [
            {
                "periodo": bucket,
                "n_equipes_totais": int(vals["n_equipes_totais"]),
                "n_equipamentos_unicos": int(vals["n_equipamentos_unicos"]),
                "equipamentos_unidades_ativas": int(vals["equipamentos_unidades_ativas"]),
            }
            for bucket, vals in sorted(grouped.items())
        ]
        columns = [
            {"id": "periodo", "label": "Período", "dtype": "str", "role": "x"},
            {"id": "n_equipes_totais", "label": "Nº Equipes", "dtype": "int", "role": "value"},
            {"id": "n_equipamentos_unicos", "label": "Equipamentos Únicos", "dtype": "int", "role": "value"},
            {
                "id": "equipamentos_unidades_ativas",
                "label": "Unidades de Equipamento Ativas",
                "dtype": "int",
                "role": "value",
            },
        ]
        operator_meta = {
            "aggregation_rule": "sum(n_equipes, unidades) + max(equipamentos_unicos) por bucket",
            "n_periodos": len(rows),
        }
        return rows[:top_n], columns, "line", "count", operator_meta

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
            from concilium.domain.services.cubo_analitico_builder import CuboAnaliticoBuilder

            cubo = CuboAnaliticoBuilder().build(canonical)

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

        bounded_top_n = max(1, min(int(top_n), 2000))
        cubo_filtrado = cubo.slice(categoria=categoria, atividade_id=atividade_id, componente_bdi=componente_bdi)

        if face == "abc_curva":
            rows, columns, chart_hint, unit_type, operator_meta = self._resolve_abc_curva_rows(
                canonical,
                bounded_top_n,
                abc_threshold_a,
                abc_threshold_b,
            )
        elif face == "s_curve_custo":
            rows, columns, chart_hint, unit_type, operator_meta = self._resolve_s_curve_rows(
                canonical,
                granularidade,
                bounded_top_n,
            )
        elif face == "recursos_ativos_tempo":
            rows, columns, chart_hint, unit_type, operator_meta = self._resolve_recursos_ativos_rows(
                canonical,
                granularidade,
                bounded_top_n,
            )
        else:
            rows, columns, chart_hint = self._resolve_cubo_projection_rows(
                cubo_filtrado, face, granularidade, bounded_top_n
            )
            unit_type = str(face_specs[face]["unit_type"])
            operator_meta = {}

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
