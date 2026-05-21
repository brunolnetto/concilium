from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from concilium.application.benchmarks.batch import discover_benchmark_slugs
from concilium.application.services.audit_service import AuditService
from concilium.application.services.override_service import OverrideService
from concilium.application.services.pipeline_service import PipelineService
from concilium.application.services.project_input_builder import ProjectInputBuilder
from concilium.application.services.project_repository import ProjectRepository
from concilium.application.services.project_service import ProjectService


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
        """Create or replace a CPU in the master catalog (ADR-067).

        Validates required fields, writes the JSON file, busts bundle cache,
        and appends an audit entry.
        """
        import json as _json
        from datetime import UTC, datetime

        # D4: minimal validation
        errors: list[str] = []
        if not cpu_data.get("codigo"):
            errors.append("Campo 'codigo' é obrigatório.")
        elif str(cpu_data["codigo"]) != cpu_id:
            errors.append(f"'codigo' no body ({cpu_data['codigo']}) deve coincidir com o cpu_id do path ({cpu_id}).")
        if not cpu_data.get("descricao"):
            errors.append("Campo 'descricao' é obrigatório.")
        if not cpu_data.get("unidade"):
            errors.append("Campo 'unidade' é obrigatório.")
        if "composicao_itens" in cpu_data and not isinstance(cpu_data["composicao_itens"], list):
            errors.append("'composicao_itens' deve ser uma lista.")
        if not motivo:
            errors.append("Campo 'motivo' é obrigatório para auditoria.")
        if errors:
            raise ValueError("; ".join(errors))

        cats_dir = self.config_root / "catalogos" / catalog_id
        if not cats_dir.exists():
            raise FileNotFoundError(f"Catálogo '{catalog_id}' não encontrado em {cats_dir}")

        cpus_dir = cats_dir / "cpus"
        cpus_dir.mkdir(parents=True, exist_ok=True)
        cpu_file = cpus_dir / f"{cpu_id}.json"

        # Preserve previous state for audit
        previous: dict | None = None
        if cpu_file.exists():
            try:
                previous = _json.loads(cpu_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        # Write new CPU definition
        cpu_file.write_text(
            _json.dumps(cpu_data, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

        # D2: invalidate bundle cache
        bundle = cats_dir / ".catalog_bundle.json"
        if bundle.exists():
            bundle.unlink()

        # D3: audit entry
        saved_at = datetime.now(UTC).isoformat()
        audit_path = cats_dir / ".catalog_audit.jsonl"
        audit_entry = {
            "event": "upsert_cpu",
            "cpu_id": cpu_id,
            "catalog_id": catalog_id,
            "actor": actor,
            "motivo": motivo,
            "timestamp": saved_at,
            "previous_snapshot": previous,
        }
        with audit_path.open("a", encoding="utf-8") as fh:
            fh.write(_json.dumps(audit_entry, ensure_ascii=False, default=str) + "\n")

        return {
            "catalog_id": catalog_id,
            "cpu_id": cpu_id,
            "saved_at": saved_at,
            "bundle_invalidated": not bundle.exists(),
        }

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

    @staticmethod
    def _enrich_cpus_with_producao(cat: dict) -> list[dict]:
        """Join producao_id_ref → valor_horario and equipe onto each CPU object.

        Complexity: O(P + C) where P = len(producoes), C = len(cpus).
        Single dict-lookup pass — no nested iteration.
        This is a read-time join; nothing is mutated on disk.
        """
        # O(P): build lookup once
        prod_lookup: dict[str, Any] = {p["id"]: p for p in cat.get("producoes", []) if "id" in p}
        # O(C): one pass over CPUs, O(1) lookup per entry
        enriched: list[dict] = []
        for cpu in cat.get("cpus", []):
            if not isinstance(cpu, dict):
                continue
            prod_ref = cpu.get("producao_id_ref")
            prod = prod_lookup.get(prod_ref) if prod_ref else None
            if prod:
                patch: dict = {}
                if not cpu.get("producao_horaria") and prod.get("valor_horario") is not None:
                    patch["producao_horaria"] = prod["valor_horario"]
                if not cpu.get("equipe") and prod.get("equipe"):
                    patch["equipe"] = prod["equipe"]
                if patch:
                    cpu = {**cpu, **patch}
            enriched.append(cpu)
        return enriched  # total O(P + C)

    def _get_enriched_cpus(self, catalog_id: str) -> list[dict[str, Any]]:
        """Return enriched CPUs for a catalog, using mtime-keyed cache.

        Cache key: bundle file mtime (nanoseconds).  When ADR-067 writes a CPU
        and deletes the bundle, mtime changes on rebuild → cache auto-invalidates.
        Falls back to no-cache if bundle doesn't exist yet.
        """
        from concilium.application.runtime import Runtime

        bundle = self.config_root / "catalogos" / catalog_id / ".catalog_bundle.json"
        try:
            mtime = bundle.stat().st_mtime_ns if bundle.exists() else 0
        except OSError:
            mtime = 0

        cached = self._enriched_cache.get(catalog_id)
        if cached is not None and cached[0] == mtime:
            return cached[1]

        rt = Runtime(self.config_root)
        cat = rt.load_catalogo(catalog_id)
        enriched = self._enrich_cpus_with_producao(cat)

        # Re-read mtime: load_catalogo may have just created the bundle file
        try:
            mtime = bundle.stat().st_mtime_ns if bundle.exists() else 0
        except OSError:
            mtime = 0

        self._enriched_cache[catalog_id] = (mtime, enriched)
        return enriched

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
                for cpu in self._get_enriched_cpus(cid):
                    if q_lower in (cpu.get("codigo") or "").lower() or q_lower in (cpu.get("descricao") or "").lower():
                        results.append({**cpu, "_catalog_id": cid})
                    if len(results) >= limit:
                        break
            except Exception:
                continue
            if len(results) >= limit:
                break
        return {"q": q, "items": results[:limit], "total": len(results)}

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
        from concilium.domain.models.mobilizacao import MobilizacaoPolicy
        from concilium.domain.services.mobilizacao_simulator import WorkforcePolicySimulator

        policy = MobilizacaoPolicy(**req["policy"])
        simulator = WorkforcePolicySimulator()

        prat_semanal = req.get("prat_semanal") or {}
        semana_inicio = req.get("semana_inicio")
        semanas_iso: dict[int, str] | None = None

        if semana_inicio and prat_semanal:
            # Derive enough offsets for the guard bound
            import math

            policy.producao_horaria if hasattr(policy, "producao_horaria") else None
            prod = float(req.get("producao_horaria") or 0)
            q = float(req.get("quantitativo") or 0)
            m, h = int(req.get("dias_semana", 6)), int(req.get("horas_dia", 8))
            base = prod * m * h * policy.n_maximo
            nominal = math.ceil(q / base) if base > 0 else 1
            n_weeks = WorkforcePolicySimulator.MAX_MULTIPLIER * max(1, nominal)
            semanas_iso = WorkforcePolicySimulator.derive_semanas_iso(semana_inicio, n_weeks)

        curva = simulator.simulate(
            policy=policy,
            atividade_id=req["item_id"],
            quantitativo=float(req["quantitativo"]),
            producao_horaria=float(req["producao_horaria"]),
            dias_semana=int(req.get("dias_semana", 6)),
            horas_dia=int(req.get("horas_dia", 8)),
            prat_semanal=prat_semanal or None,
            semanas_iso_por_offset=semanas_iso,
        )
        return curva.model_dump()


def _build_wmp_lookup(iterable, key_field: str) -> dict:
    """Generic lookup builder: list of dicts -> {key: dict}."""
    result: dict = {}
    for item in iterable or []:
        if isinstance(item, dict) and item.get(key_field):
            result[item[key_field]] = item
    return result


def _resolve_producao_horaria(eap_item: dict, cpu_lookup: dict, producao_lookup: dict) -> float:
    """Resolve producao horaria P from EAP->CPU->Producao chain."""
    cpu_id = eap_item.get("cpu_id", "")
    cpu = cpu_lookup.get(cpu_id, {})
    prod_id = cpu.get("producao_id_ref") or cpu.get("producao_id")
    return float((producao_lookup.get(prod_id) or {}).get("valor_horario") or cpu.get("producao_horaria") or 0.0)


def _build_wmp_codigo(curva: Any, policy: Any) -> str:
    """Determine WMP validation codigo from curve state."""
    if curva.is_complete:
        return "VAL-WMP-OK"
    if policy.semanas_plateau and policy.taxa_desmobilizacao > 0:
        return "VAL-WMP-DESMOB"
    return "VAL-WMP-05"


def _process_wmp_policy(
    sim: Any, item_id: str, policy_dict: dict, eap_items: dict, cpu_lookup: dict, producao_lookup: dict, results: list
) -> None:
    """Process one WMP policy: validate, resolve P, simulate, append result."""
    from concilium.domain.models.mobilizacao import MobilizacaoPolicy

    try:
        policy = MobilizacaoPolicy(**{k: v for k, v in policy_dict.items() if v is not None or k == "semanas_plateau"})
    except Exception as exc:
        results.append(
            {"codigo": "VAL-WMP-03", "status": "ERRO", "mensagem": f"'{item_id}': política inválida — {exc}"}
        )
        return

    eap = eap_items.get(item_id, {})
    Q = float(eap.get("quantitativo", 0))
    if Q <= 0:
        results.append(
            {"codigo": "VAL-WMP-04", "status": "AVISO", "mensagem": f"'{item_id}': Q={Q} não disponível na referência."}
        )
        return

    P = _resolve_producao_horaria(eap, cpu_lookup, producao_lookup)
    if P <= 0:
        results.append(
            {
                "codigo": "VAL-WMP-02",
                "status": "AVISO",
                "mensagem": f"'{item_id}': produtividade não resolvida (P={P}). CPU '{eap.get('cpu_id', '')}'.",
            }
        )

    curva = sim.simulate(
        policy=policy,
        atividade_id=item_id,
        quantitativo=Q,
        producao_horaria=max(P, 0),
        dias_semana=6,
        horas_dia=8,
    )
    results.append(
        {
            "codigo": _build_wmp_codigo(curva, policy),
            "status": "OK" if curva.is_complete else "AVISO",
            "mensagem": f"'{item_id}': {curva.duration_weeks} sem., pico={curva.peak_teams}, completa={curva.is_complete}.",
            "duration_weeks": curva.duration_weeks,
            "peak_teams": curva.peak_teams,
            "delivered": curva.delivered,
            "quantitativo_alvo": Q,
            "is_complete": curva.is_complete,
        }
    )

    def validate_mobilizacao_policies(self, project_id: str) -> list[dict]:
        """ADR-054 Phase 3: Validate all saved WMP policies without running the full pipeline.

        Resolves productivities, simulates each policy, and returns structured validation
        items — same VAL-WMP-* codes as the Skill 04 expansion step.
        """
        from concilium.domain.services.mobilizacao_simulator import WorkforcePolicySimulator

        policies = self._dependencies.override_service.get_mobilizacao_policies(project_id)
        if not policies:
            return [{"codigo": "VAL-WMP-NONE", "status": "OK", "mensagem": "Nenhuma política WMP salva."}]

        try:
            reference = self._dependencies.project_service.get_benchmark_reference(project_id)
        except FileNotFoundError:
            reference = {}

        eap_items = _build_wmp_lookup((reference.get("cpus") or {}).get("itens_eap", []), "item_id")
        cpu_lookup = _build_wmp_lookup(reference.get("catalog", {}).get("cpus", []) or [], "codigo")
        producao_lookup = _build_wmp_lookup(reference.get("catalog", {}).get("produtividades", []) or [], "id")

        sim = WorkforcePolicySimulator()
        results: list[dict] = []
        for item_id, policy_dict in policies.items():
            _process_wmp_policy(sim, item_id, policy_dict, eap_items, cpu_lookup, producao_lookup, results)
        return results

    # ADR-054: Deliverables configuration

    def get_deliverables_config(self, project_id: str) -> dict:
        return self._dependencies.override_service.get_deliverables_config(project_id)

    def put_deliverables_config(self, project_id: str, config: dict, actor: str = "system") -> dict:
        return self._dependencies.override_service.put_deliverables_config(project_id, config, actor=actor)
