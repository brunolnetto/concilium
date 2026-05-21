from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from concilium.domain.services.project_rules import (
    calculate_deltas,
    resolve_compare_version,
    validate_delete_version,
)

from .audit_service import AuditService
from .project_files import DEFAULT_PROJECT_FILES, ProjectFiles
from .project_repository import ProjectRepository
from .service_support import build_summary


def _try_enrich_cpu_with_prod(cpu: dict[str, Any], prod_lkp: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(cpu, dict):
        return cpu
    ref = cpu.get("producao_id_ref")
    prod = prod_lkp.get(ref) if ref else None
    if not prod:
        return cpu
    patch: dict[str, Any] = {}
    if not cpu.get("producao_horaria") and prod.get("valor_horario") is not None:
        patch["producao_horaria"] = prod["valor_horario"]
    if not cpu.get("equipe") and prod.get("equipe"):
        patch["equipe"] = prod["equipe"]
    if patch:
        cpu = {**cpu, **patch}
    return cpu


def _build_joined_cpus(cpus_snap: list[Any], prods: list[Any]) -> list[Any]:
    prod_lkp = {p["id"]: p for p in prods if isinstance(p, dict) and "id" in p}
    return [_try_enrich_cpu_with_prod(cpu, prod_lkp) for cpu in cpus_snap]


def _build_catalog_from_snapshot(cat: dict[str, Any]) -> dict[str, Any]:
    cpus_snap = cat.get("cpus") or []
    prods = cat.get("produtividades") or cat.get("producoes", [])
    catalog: dict[str, Any] = {}
    if cpus_snap and prods:
        catalog["cpus"] = _build_joined_cpus(cpus_snap, prods)
    elif cpus_snap:
        catalog["cpus"] = cpus_snap
    insumos = cat.get("insumos") or []
    if insumos:
        catalog["insumos"] = insumos
    if prods:
        catalog["produtividades"] = prods
    return catalog


def _enrich_payload_catalog(payload: dict[str, Any], project: Any) -> None:
    try:
        import json as _json2
        from pathlib import Path

        snaps_dir: Path = Path(project.root).resolve() / "snapshots"
        cat_files = sorted(snaps_dir.glob("catalogo-*.json"))
        if cat_files:
            cat = _json2.loads(cat_files[-1].read_text(encoding="utf-8"))
            catalog = _build_catalog_from_snapshot(cat)
            if catalog:
                payload["catalog"] = catalog
                project.write_json("benchmark_reference.json", payload)
    except Exception:
        pass


def _enrich_payload_encargos(payload: dict[str, Any], project: Any) -> None:
    try:
        import json as _json

        snaps_dir = project.root / "snapshots"
        juris_files = sorted(snaps_dir.glob("jurisdicao-*.json"))
        if juris_files:
            juris = _json.loads(juris_files[-1].read_text(encoding="utf-8"))
            motor = juris.get("motor_encargos_sociais") or {}
            payload["encargos_sociais"] = {
                "pj": 0.0,
                "clt_mensalista": float(motor.get("percentual_mensalista") or 1.06),
                "clt_horista": float(motor.get("percentual_total") or 1.777),
            }
    except Exception:
        pass


def _compute_bdi_for_categoria(comps: Any) -> float | None:
    if not isinstance(comps, dict) or "ac" not in comps:
        return None
    ac = float(comps.get("ac", 0))
    df = float(comps.get("df", 0))
    r = float(comps.get("r", 0))
    cr = float(comps.get("cr", 0))
    lucro = float(comps.get("l") or comps.get("lucro") or 0)
    t = sum(float(comps.get(k, 0)) for k in ("cofins", "iss", "pis", "cssl", "ir"))
    return ((1 + ac + df + r + cr + lucro) / (1 - t) - 1) if t < 1 else 0.0


def _compute_flat_bdi(tabela_bdi: dict[str, Any]) -> dict[str, float]:
    flat: dict[str, float] = {}
    for cat, comps in tabela_bdi.items():
        bdi = _compute_bdi_for_categoria(comps)
        if bdi is None:
            continue
        flat[cat] = round(bdi, 6)
    if flat and "equipamentos" not in flat:
        flat["equipamentos"] = round(0.70 * flat.get("mao_obra", 0.0) + 0.30 * flat.get("diesel", 0.0), 6)
    if flat and "servicos" not in flat:
        flat["servicos"] = flat.get("mao_obra", 0.0)
    return flat


def _enrich_payload_bdi(payload: dict[str, Any]) -> None:
    try:
        s6 = (payload.get("skill_inputs") or {}).get("06-precificacao-unitaria") or {}
        tabela_bdi = s6.get("tabela_bdi") or {}
        if not (tabela_bdi and isinstance(tabela_bdi, dict)):
            return
        flat = _compute_flat_bdi(tabela_bdi)
        if flat:
            payload.setdefault("skill_inputs", {}).setdefault("06-precificacao-unitaria", {})["bdi_aplicado"] = flat
    except Exception:
        pass


def _cp_build_meta_kwargs(inputs_escopo: dict, req: object) -> dict:
    """Extracts nested coordenadas/regime_trabalho kwargs with or-fallback."""
    return {
        "coordenadas_lat": (inputs_escopo.get("coordenadas") or {}).get("lat", req.coordenadas_lat),
        "coordenadas_lng": (inputs_escopo.get("coordenadas") or {}).get("lng", req.coordenadas_lng),
        "dias_semana": (inputs_escopo.get("regime_trabalho") or {}).get("dias_semana", req.dias_semana),
        "horas_dia": (inputs_escopo.get("regime_trabalho") or {}).get("horas_dia", req.horas_dia),
    }


def _cp_embed_catalog_if_needed(project: object, benchmark_reference: object, files: object) -> None:
    """Embeds catalog snapshot into ref_to_save if not already present, then saves."""
    if benchmark_reference is None:
        return
    ref_to_save = dict(benchmark_reference)
    if not ref_to_save.get("catalog"):
        try:
            import json as _jcat
            from pathlib import Path

            snaps_dir = Path(project.root).resolve() / "snapshots"
            cat_files = sorted(snaps_dir.glob("catalogo-*.json"))
            if cat_files:
                cat = _jcat.loads(cat_files[-1].read_text(encoding="utf-8"))
                catalog: dict = {}
                if cat.get("cpus"):
                    catalog["cpus"] = cat["cpus"]
                if cat.get("insumos"):
                    catalog["insumos"] = cat["insumos"]
                if cat.get("produtividades"):
                    catalog["produtividades"] = cat["produtividades"]
                if catalog:
                    ref_to_save["catalog"] = catalog
        except Exception:
            pass
    project.write_json(files.benchmark_reference, ref_to_save)


def _cp_save_perfil_context(
    project: object,
    contexto_version: str | None,
    perfil_id: str | None,
    perfil_version: str | None,
) -> None:
    """Persists ADR-062 context/perfil versions into meta.json if any are set."""
    if not (contexto_version or perfil_id or perfil_version):
        return
    meta = dict(project.meta)
    if contexto_version:
        meta["contexto_version"] = contexto_version
    if perfil_id:
        meta["perfil_id"] = perfil_id
    if perfil_version:
        meta["perfil_version"] = perfil_version
    project.write_json("meta.json", meta)


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
        contexto_version: str | None = None,  # ADR-062
        perfil_id: str | None = None,  # ADR-062
        perfil_version: str | None = None,  # ADR-062
    ) -> dict[str, Any]:
        project_name = req.nome or inputs_escopo.get("nome") or f"Prototype {benchmark_slug or 'Project'}"
        catalogo_base = benchmark_slug or getattr(req, "catalogo_base", None)
        project = self._repository.create_project(project_name, req.contexto_id, catalogo_base=catalogo_base)
        tipo_projeto = "hot_project" if benchmark_slug else "project"
        status_eap = "ATIVO" if tipo_projeto == "hot_project" else "RASCUNHO"
        project.update_meta(
            tipo_obra=inputs_escopo.get("tipo_obra", req.tipo_obra),
            localizacao=inputs_escopo.get("localizacao", req.localizacao),
            data_inicio=inputs_escopo.get("data_inicio", req.data_inicio),
            data_termino=inputs_escopo.get("data_termino", req.data_termino),
            **_cp_build_meta_kwargs(inputs_escopo, req),
            tipo_projeto=tipo_projeto,
            status_eap=status_eap,
            benchmark_slug=benchmark_slug,
        )
        version = project.new_version()
        project.write_json(self._files.skill_inputs, skill_inputs)
        project.write_json(self._files.overrides, {})
        _cp_embed_catalog_if_needed(project, benchmark_reference, self._files)
        _cp_save_perfil_context(project, contexto_version, perfil_id, perfil_version)
        payload = {
            "project_id": project.meta["id"],
            "nome": project_name,
            "contexto_id": req.contexto_id,
            "contexto_version": contexto_version,
            "current_version": version,
            "tipo_projeto": tipo_projeto,
            "status_eap": status_eap,
            "benchmark_slug": benchmark_slug,
            "benchmark_reference_file": self._files.benchmark_reference if benchmark_reference is not None else None,
        }
        self._audit_service.log(project, action="create_project", actor=actor, payload=req.model_dump(), result=payload)
        return payload

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
        from concilium.domain.models.canonical import EapItem
        from concilium.domain.services.eap_dag_validator import validar_dag_predecessores

        project = self._repository.get_project(project_id)
        meta = project.meta
        if meta.get("tipo_projeto", "hot_project") == "hot_project":
            raise ValueError("EAP não pode ser editada diretamente em projetos do tipo hot_project.")

        # Validate and parse items
        parsed: list[EapItem] = []
        for i, item in enumerate(eap_items):
            if "ordem" not in item:
                item = {**item, "ordem": i + 1}
            parsed.append(EapItem.model_validate(item))

        # ADR-063 §D4: validate DAG
        validar_dag_predecessores(parsed)

        # Persist
        project.write_json(self._files.eap_items, [it.model_dump() for it in parsed])

        # Update status_eap
        has_items = len(parsed) > 0
        all_cpus_set = all(bool(it.cpu_id) for it in parsed)
        new_status = "RASCUNHO_PRONTO" if has_items and all_cpus_set else "RASCUNHO"
        project.update_meta(status_eap=new_status)

        self._audit_service.log(
            project, action="upsert_eap", actor=actor, payload={"count": len(parsed)}, result={"status_eap": new_status}
        )
        return {"project_id": project_id, "status_eap": new_status, "count": len(parsed)}

    def list_versions(self, project_id: str) -> list[str]:
        return self._repository.get_project(project_id).list_versions()

    def delete_version(self, project_id: str, version: str, actor: str = "system") -> dict[str, Any]:
        project = self._repository.get_project(project_id)
        versions = project.list_versions()
        if version not in versions:
            raise FileNotFoundError(f"Versao '{version}' nao encontrada.")

        meta = project.meta
        validate_delete_version(meta.get("tipo_projeto", "hot_project"), versions, version)

        project.delete_tree(version)

        remaining = [item for item in versions if item != version]
        remaining_sorted = sorted(
            remaining,
            key=lambda item: int(item[1:]) if item.startswith("v") and item[1:].isdigit() else -1,
        )

        current = meta.get("current_version")
        next_current = current
        if current == version:
            next_current = remaining_sorted[-1] if remaining_sorted else None

        approved_versions = [item for item in (meta.get("approved_versions") or []) if item != version]
        project.update_meta(current_version=next_current, approved_versions=approved_versions)

        runs = project.read_json(self._files.runs, [])
        orphaned_runs = 0
        if isinstance(runs, list):
            for run in runs:
                if not isinstance(run, dict):
                    continue
                if run.get("version") == version or run.get("base_version") == version:
                    orphaned_runs += 1

        payload = {
            "project_id": project_id,
            "deleted_version": version,
            "current_version": next_current,
            "versions": remaining_sorted,
            "orphaned_runs": orphaned_runs,
        }
        self._audit_service.log(
            project, action="delete_version", actor=actor, payload={"version": version}, result=payload
        )
        return payload

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
            return {"version": None, "outputs": [], "intermediate": []}

        outputs = project.list_output_files(resolved_version)
        intermediate = project.list_file_names(f"{resolved_version}/intermediate")
        return {"version": resolved_version, "outputs": outputs, "intermediate": intermediate}

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
        else:
            raise ValueError("kind deve ser 'outputs' ou 'intermediate'.")

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
        return payload
