"""Private helpers extracted from project_service.py."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

from .project_files import ProjectFiles
from .project_repository import ProjectHandle

if TYPE_CHECKING:
    from pathlib import Path

    from concilium.application.services.project.project_service._host_protocol import ProjectServiceHost


class _CreateProjectRequestLike(Protocol):
    """Forma mínima esperada de req em _ps_create_project.

    Evita importar CreateProjectRequest (presentation/api/schemas.py) na camada
    de application — só descreve os campos/método realmente acessados aqui.
    """

    nome: str | None
    contexto_id: str
    tipo_obra: str
    localizacao: str
    data_inicio: str
    data_termino: str
    coordenadas_lat: float
    coordenadas_lng: float
    dias_semana: int
    horas_dia: int

    def model_dump(self) -> dict[str, Any]: ...


def _try_enrich_cpu_with_prod(cpu: dict[str, Any], prod_lkp: dict[str, Any]) -> dict[str, Any]:
    """Enrich CPU with production template defaults (producao_horaria, equipe).

    Resolves CPU.producao_id_ref in prod_lkp, merges missing fields from template.
    Returns enriched CPU dict (copy if modified, original if not).
    """
    if not isinstance(cpu, dict):
        return cpu
    ref = cpu.get("producao_id_ref")
    prod = prod_lkp.get(ref) if ref else None
    if not prod:
        return cpu
    patch: dict[str, Any] = {}
    if not cpu.get("producao_horaria") and prod.get("valor_horario") is not None:
        patch["producao_horaria"] = prod["valor_horario"]
    prod_equipe = prod.get("equipe")
    if not isinstance(prod_equipe, dict):
        prod_equipe = prod.get("composicao_padrao_equipe")
    if not cpu.get("equipe") and isinstance(prod_equipe, dict):
        patch["equipe"] = prod_equipe
    if patch:
        cpu = {**cpu, **patch}
    return cpu


def _build_joined_cpus(cpus_snap: list[Any], prods: list[Any]) -> list[Any]:
    """Join CPU snapshot with production templates (enrichment for hourly rate + equipe).

    Maps prods by id, applies _try_enrich_cpu_with_prod to each CPU.
    """
    prod_lkp = {p["id"]: p for p in prods if isinstance(p, dict) and "id" in p}
    return [_try_enrich_cpu_with_prod(cpu, prod_lkp) for cpu in cpus_snap]


def _build_catalog_from_snapshot(cat: dict[str, Any]) -> dict[str, Any]:
    """Build composite catalog dict from snapshot (CPUs + insumos + productions).

    Enriches CPUs with production templates, preserves insumos and produtividades.
    Returns flattened dict ready for use.
    """
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


def _load_resolved_catalog_items(project: Any) -> dict[str, Any] | None:
    """Load catalog from project.load_resolved_catalog() (ADR-066 Phase 8).

    On-demand, version-specific catalog (filtered by CPU usage in EAP).
    Returns None if unavailable or empty.
    """
    load_resolved = getattr(project, "load_resolved_catalog", None)
    if not callable(load_resolved):
        return None
    try:
        resolved = load_resolved()
    except Exception:
        return None
    items = resolved.get("items") if isinstance(resolved, dict) else None
    if isinstance(items, dict) and (items.get("cpus") or items.get("insumos")):
        return items
    return None


def _load_snapshot_catalog(project: Any) -> dict[str, Any] | None:
    """Load legacy snapshot catalog from disk (retrocompat for old projects).

    Reads catalogo-*.json from snapshots/ dir, returns latest.
    """
    try:
        import json as _json2
        from pathlib import Path

        snaps_dir: Path = Path(project.root).resolve() / "snapshots"
        cat_files = sorted(snaps_dir.glob("catalogo-*.json"))
        if not cat_files:
            return None
        return _json2.loads(cat_files[-1].read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_cpus_from_catalog_dir(cat_dir: Path) -> list[Any]:
    """Load CPUs from catalog directory (cpus/{codigo}.json or cpus.json aggregate)."""
    import json

    cpu_dir = cat_dir / "cpus"
    if cpu_dir.exists():
        return [json.loads(f.read_text(encoding="utf-8")) for f in cpu_dir.glob("*.json")]
    aggregate = cat_dir / "cpus.json"
    if aggregate.exists():
        data = json.loads(aggregate.read_text(encoding="utf-8"))
        return list(data.get("cpus", data)) if isinstance(data, dict) else list(data)
    return []


def _load_insumos_from_catalog_dir(cat_dir: Path) -> list[Any]:
    """Load insumos from catalog directory (insumos/{tipo}/{codigo}.json files)."""
    import json

    insumos: list[Any] = []
    insumos_dir = cat_dir / "insumos"
    if insumos_dir.exists():
        for f in insumos_dir.glob("*.json"):
            data = json.loads(f.read_text(encoding="utf-8"))
            insumos.extend(data if isinstance(data, list) else [data])
    return insumos


def _load_producoes_from_catalog_dir(cat_dir: Path) -> list[Any]:
    """Load production templates from catalog directory (producoes/ or produtividades/)."""
    import json

    producoes: list[Any] = []
    for dname in ("producoes", "produtividades"):
        p_dir = cat_dir / dname
        if p_dir.exists():
            producoes.extend(json.loads(f.read_text(encoding="utf-8")) for f in p_dir.glob("*.json"))
    return producoes


def _load_live_catalog(project: Any) -> dict[str, Any] | None:
    """Load live master catalog from config/catalogos/{catalogo_base} (ADR-066 Phase 8).

    Fallback when no snapshot or resolved_catalog available. Sources resolve_cpu() uses.
    Returns None if unavailable or empty.
    """
    try:
        from pathlib import Path

        catalogo_base = (project.meta or {}).get("catalogo_base")
        if not catalogo_base:
            return None
        concilium_root = Path(project.root).resolve().parents[1]
        cat_dir = concilium_root / "config" / "catalogos" / catalogo_base

        cpus = _load_cpus_from_catalog_dir(cat_dir)
        insumos = _load_insumos_from_catalog_dir(cat_dir)
        producoes = _load_producoes_from_catalog_dir(cat_dir)

        if not cpus and not insumos:
            return None
        return {"cpus": cpus, "insumos": insumos, "produtividades": producoes}
    except Exception:
        return None


def _resolve_benchmark_catalog_source(project: Any) -> dict[str, Any] | None:
    """Resolve catalog source in priority order (ADR-066 Phase 8).

    Priority: resolved_catalog.json (on-demand) → snapshot (legacy) → live master.
    Returns None if none available.
    """
    return _load_resolved_catalog_items(project) or _load_snapshot_catalog(project) or _load_live_catalog(project)


def _enrich_payload_catalog(payload: dict[str, Any], project: Any) -> None:
    """Enrich benchmark_reference payload with catalog (CPUs + insumos) if available.

    Resolves source via _resolve_benchmark_catalog_source, persists to project.
    """
    try:
        cat = _resolve_benchmark_catalog_source(project)
        if cat:
            catalog = _build_catalog_from_snapshot(cat)
            if catalog:
                payload["catalog"] = catalog
                project.write_json("benchmark_reference.json", payload)
    except Exception:
        pass


def _enrich_payload_encargos(payload: dict[str, Any], project: Any) -> None:
    """Enrich payload with social charge rates (PJ, CLT-mensalista, CLT-horista) from snapshot."""
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
    """Compute BDI factor from component dict (ac, df, r, cr, lucro, impostos).

    Formula: ((1 + ac + df + r + cr + lucro) / (1 - impostos)) - 1.
    Returns None if missing ac field or t >= 1 (undefined).
    """
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
    """Flatten BDI table (categoria -> components) to single-value dict.

    Computes BDI per category via _compute_bdi_for_categoria, includes fallbacks
    for equipamentos and servicos (ADR-023 §D3 revised).
    """
    flat: dict[str, float] = {}
    for cat, comps in tabela_bdi.items():
        bdi = _compute_bdi_for_categoria(comps)
        if bdi is None:
            continue
        flat[cat] = round(bdi, 6)
    if flat and "equipamentos" not in flat:
        if "servicos" in flat:
            flat["equipamentos"] = flat["servicos"]
        else:
            # ADR-023 §D3 revisado: locação de equipamento sem ISS (SV-31) → taxa de material
            flat["equipamentos"] = flat.get("material", 0.0)
    if flat and "servicos" not in flat:
        flat["servicos"] = flat.get("mao_obra", 0.0)
    return flat


def _enrich_payload_bdi(payload: dict[str, Any]) -> None:
    """Enrich payload with computed BDI (bdi_aplicado) from skill 06 tabela_bdi."""
    try:
        s6 = (payload.get("skill_inputs") or {}).get("06-resultado-financeiro") or {}  # NEP-041 F4
        tabela_bdi = s6.get("tabela_bdi") or {}
        if not (tabela_bdi and isinstance(tabela_bdi, dict)):
            return
        flat = _compute_flat_bdi(tabela_bdi)
        if flat:
            payload.setdefault("skill_inputs", {}).setdefault("06-resultado-financeiro", {})["bdi_aplicado"] = flat
    except Exception:
        pass


def _cp_build_meta_kwargs(inputs_escopo: dict[str, Any], req: _CreateProjectRequestLike) -> dict[str, Any]:
    """Extract nested coordenadas/regime_trabalho with or-fallback from request."""
    return {
        "coordenadas_lat": (inputs_escopo.get("coordenadas") or {}).get("lat", req.coordenadas_lat),
        "coordenadas_lng": (inputs_escopo.get("coordenadas") or {}).get("lng", req.coordenadas_lng),
        "dias_semana": (inputs_escopo.get("regime_trabalho") or {}).get("dias_semana", req.dias_semana),
        "horas_dia": (inputs_escopo.get("regime_trabalho") or {}).get("horas_dia", req.horas_dia),
    }


def _cp_embed_catalog_if_needed(
    project: ProjectHandle, benchmark_reference: dict[str, Any] | None, files: ProjectFiles
) -> None:
    """Embed catalog snapshot into benchmark_reference if not already present, then save."""
    if benchmark_reference is None:
        return
    ref_to_save = dict(benchmark_reference)
    if not ref_to_save.get("catalog"):
        try:
            cat = _resolve_benchmark_catalog_source(project)
            if cat:
                catalog = _build_catalog_from_snapshot(cat)
                if catalog:
                    ref_to_save["catalog"] = catalog
        except Exception:
            pass
    project.write_json(files.benchmark_reference, ref_to_save)


def _resolve_catalogo_base_from_context(svc: ProjectServiceHost, contexto_id: str) -> str | None:
    """Resolve canonical catalog_id from contexto version metadata (ADR-062).

    Falls back to contexto_id if versions unavailable.
    """
    try:
        versions = svc.list_contexto_versions(contexto_id)
    except Exception:
        versions = []
    if not versions:
        return contexto_id or None
    current = versions[-1] if isinstance(versions, list) and versions else {}
    catalog_id = str((current or {}).get("catalogo_id") or "").strip()
    if catalog_id:
        return catalog_id
    return contexto_id or None


def _cp_save_perfil_context(
    project: ProjectHandle,
    contexto_version: str | None,
    perfil_id: str | None,
    perfil_version: str | None,
) -> None:
    """Persist ADR-062 context/perfil versions to project meta.json (if any set)."""
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


def _sort_versions(versions: list) -> list:
    """Sort version strings (v1, v2, ...) by numeric suffix, non-versioned last."""
    return sorted(
        versions,
        key=lambda item: int(item[1:]) if item.startswith("v") and item[1:].isdigit() else -1,
    )


def _count_orphaned_runs(runs: list, version: str) -> int:
    """Count runs that reference deleted version as base or current version."""
    count = 0
    if not isinstance(runs, list):
        return count
    for run in runs:
        if not isinstance(run, dict):
            continue
        if run.get("version") == version or run.get("base_version") == version:
            count += 1
    return count


def _ps_create_project(
    svc: ProjectServiceHost,
    req: _CreateProjectRequestLike,
    inputs_escopo: dict[str, Any],
    skill_inputs: dict[str, dict[str, Any]],
    benchmark_slug: str | None,
    benchmark_reference: dict[str, Any] | None,
    actor: str = "system",
    contexto_version: str | None = None,  # ADR-062
    perfil_id: str | None = None,  # ADR-062
    perfil_version: str | None = None,  # ADR-062
) -> dict[str, Any]:
    """Create new project with versioning, skill inputs, benchmark reference, and audit trail.

    Resolves catalogo_base from context, creates initial version, writes artifacts,
    enriches benchmark_reference with catalog/encargos/BDI, logs action.
    """
    project_name = req.nome or inputs_escopo.get("nome") or f"Prototype {benchmark_slug or 'Project'}"
    # catalogo_base drives project-level CPU resolution and must be a real catalog id.
    # benchmark_slug identifies a dataset/template and is not necessarily a catalog id.
    catalogo_base = _resolve_catalogo_base_from_context(svc, req.contexto_id)
    if not catalogo_base:
        catalogo_base = inputs_escopo.get("snapshot_catalogo_id") or getattr(req, "catalogo_base", None)
    project = svc._repository.create_project(project_name, req.contexto_id, catalogo_base=catalogo_base)
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
        # ADR-126 D1: owner_id inicializado a partir do actor atual — campo do
        # projeto (não da versão), distinto de criado_por/role_criador (ADR-119).
        owner_id=actor,
        owner_assigned_at=datetime.now(UTC).isoformat(),
    )
    version = project.new_version()
    project.write_json(svc._files.skill_inputs, skill_inputs)
    project.write_json(svc._files.overrides, {})
    _cp_embed_catalog_if_needed(project, benchmark_reference, svc._files)
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
        "benchmark_reference_file": svc._files.benchmark_reference if benchmark_reference is not None else None,
    }
    svc._audit_service.log(project, action="create_project", actor=actor, payload=req.model_dump(), result=payload)
    return payload


def _ps_upsert_eap(
    svc: ProjectServiceHost, project_id: str, eap_items: list[dict[str, Any]], actor: str = "system"
) -> dict[str, Any]:
    """Upsert EAP items (work breakdown structure) with DAG validation (ADR-063).

    Validates EapItem schema, checks DAG predecessor constraints, persists, updates status_eap.
    Returns new status (RASCUNHO_PRONTO if all CPUs set, else RASCUNHO).
    """
    from concilium.domain.models.canonical import EapItem
    from concilium.domain.services.eap_dag_validator import validar_dag_predecessores

    project = svc._repository.get_project(project_id)
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
    project.write_json(svc._files.eap_items, [it.model_dump() for it in parsed])

    # Update status_eap
    has_items = len(parsed) > 0
    all_cpus_set = all(bool(it.cpu_id) for it in parsed)
    new_status = "RASCUNHO_PRONTO" if has_items and all_cpus_set else "RASCUNHO"
    project.update_meta(status_eap=new_status)

    svc._audit_service.log(
        project, action="upsert_eap", actor=actor, payload={"count": len(parsed)}, result={"status_eap": new_status}
    )
    return {"project_id": project_id, "status_eap": new_status, "count": len(parsed)}


def _ps_delete_version(svc: ProjectServiceHost, project_id: str, version: str, actor: str = "system") -> dict[str, Any]:
    """Delete project version with cascade updates (current_version, approved_versions, orphaned runs).

    Validates deletion constraints, removes version tree, updates meta, counts orphaned runs.
    """
    from concilium.domain.services.versioning import validate_delete_version

    project = svc._repository.get_project(project_id)
    versions = project.list_versions()
    if version not in versions:
        raise FileNotFoundError(f"Versao '{version}' nao encontrada.")

    meta = project.meta
    validate_delete_version(meta.get("tipo_projeto", "hot_project"), versions, version)

    project.delete_tree(version)

    remaining_sorted = _sort_versions([v for v in versions if v != version])
    current = meta.get("current_version")
    next_current = (
        remaining_sorted[-1] if current == version and remaining_sorted else (None if current == version else current)
    )
    approved_versions = [v for v in (meta.get("approved_versions") or []) if v != version]
    project.update_meta(current_version=next_current, approved_versions=approved_versions)
    orphaned_runs = _count_orphaned_runs(project.read_json(svc._files.runs, []), version)
    payload = {
        "project_id": project_id,
        "deleted_version": version,
        "current_version": next_current,
        "versions": remaining_sorted,
        "orphaned_runs": orphaned_runs,
    }
    svc._audit_service.log(project, action="delete_version", actor=actor, payload={"version": version}, result=payload)
    return payload


def _ps_delete_project(svc: ProjectServiceHost, project_id: str, actor: str = "system") -> dict[str, Any]:
    """Delete entire project directory (irrevocable)."""
    import shutil

    project = svc._repository.get_project(project_id)
    root = project.root
    if not root.exists():
        raise FileNotFoundError(f"Projeto '{project_id}' não encontrado.")

    summary = {
        "project_id": project_id,
        "versions": project.list_versions(),
        "current_version": project.current_version(),
    }
    shutil.rmtree(root)
    return {"project_id": project_id, "deleted": True, "summary": summary}
