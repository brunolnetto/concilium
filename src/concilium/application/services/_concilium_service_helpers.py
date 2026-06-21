"""Private helpers extracted from concilium_service.py."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from concilium.application.services.concilium_service import ConciliumService


def _validate_cpu_data(cpu_data: dict, cpu_id: str, motivo: str) -> None:
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


def _build_prod_lookup(producoes: list) -> dict:
    lookup = {}
    for p in producoes:
        if "id" in p:
            lookup[p["id"]] = p
    return lookup


def _enrich_cpu_with_prod(cpu: dict, prod_lookup: dict) -> dict:
    prod_ref = cpu.get("producao_id_ref")
    prod = prod_lookup.get(prod_ref) if prod_ref else None
    if not prod:
        return cpu
    patch: dict = {}
    if not cpu.get("producao_horaria") and prod.get("valor_horario") is not None:
        patch["producao_horaria"] = prod["valor_horario"]
    prod_equipe = prod.get("equipe")
    if not isinstance(prod_equipe, dict):
        prod_equipe = prod.get("composicao_padrao_equipe")
    if not cpu.get("equipe") and isinstance(prod_equipe, dict):
        patch["equipe"] = prod_equipe
    return {**cpu, **patch} if patch else cpu


def _enrich_cpus_with_producao(cat: dict) -> list[dict]:
    """Join producao_id_ref -> valor_horario onto each CPU object.

    Complexity: O(P + C) where P = len(producoes), C = len(cpus).
    Single dict-lookup pass — no nested iteration.
    This is a read-time join; nothing is mutated on disk.
    """
    producoes = cat.get("produtividades") or cat.get("producoes", [])
    prod_lookup = _build_prod_lookup(producoes)
    enriched: list[dict] = []
    for cpu in cat.get("cpus", []):
        if not isinstance(cpu, dict):
            continue
        enriched.append(_enrich_cpu_with_prod(cpu, prod_lookup))
    return enriched


def _cs_upsert_catalog_cpu(
    svc: ConciliumService,
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

    _validate_cpu_data(cpu_data, cpu_id, motivo)

    cats_dir = svc.config_root / "catalogos" / catalog_id
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


def _cs_get_enriched_cpus(svc: ConciliumService, catalog_id: str) -> list[dict[str, Any]]:
    """Return enriched CPUs for a catalog, using mtime-keyed cache.

    Cache key: bundle file mtime (nanoseconds).  When ADR-067 writes a CPU
    and deletes the bundle, mtime changes on rebuild → cache auto-invalidates.
    Falls back to no-cache if bundle doesn't exist yet.
    """
    from concilium.application.runtime import Runtime

    bundle = svc.config_root / "catalogos" / catalog_id / ".catalog_bundle.json"
    try:
        mtime = bundle.stat().st_mtime_ns if bundle.exists() else 0
    except OSError:
        mtime = 0

    cached = svc._enriched_cache.get(catalog_id)
    if cached is not None and cached[0] == mtime:
        return cached[1]

    rt = Runtime(svc.config_root)
    cat = rt.load_catalogo(catalog_id)
    enriched = _enrich_cpus_with_producao(cat)

    # Re-read mtime: load_catalogo may have just created the bundle file
    try:
        mtime = bundle.stat().st_mtime_ns if bundle.exists() else 0
    except OSError:
        mtime = 0

    svc._enriched_cache[catalog_id] = (mtime, enriched)
    return enriched


def _cs_simulate_mobilizacao_policy(project_id: str, req: dict[str, Any]) -> dict[str, Any]:
    from concilium.domain.models.planning.mobilizacao import MobilizacaoPolicy
    from concilium.domain.services.planning.mobilizacao_simulator import WorkforcePolicySimulator

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
    # Nível 1: tabela de produção (mais específica)
    prod_entry = producao_lookup.get(prod_id) if prod_id else None
    valor = prod_entry.get("valor_horario") if prod_entry is not None else None
    if valor is not None:
        return float(valor)
    # Nível 2: campo direto na CPU
    valor = cpu.get("producao_horaria")
    if valor is not None:
        return float(valor)
    # Nível 3: ausente — 0 é fallback explícito (não valor calculado)
    logger.debug("Produção horária não encontrada para cpu_id=%s prod_id=%s — retornando 0.0", cpu_id, prod_id)
    return 0.0


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
    from concilium.domain.models.planning.mobilizacao import MobilizacaoPolicy

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
            "mensagem": (
                f"'{item_id}': {curva.duration_weeks} sem., pico={curva.peak_teams}, completa={curva.is_complete}."
            ),
            "duration_weeks": curva.duration_weeks,
            "peak_teams": curva.peak_teams,
            "delivered": curva.delivered,
            "quantitativo_alvo": Q,
            "is_complete": curva.is_complete,
        }
    )


def _cs_validate_mobilizacao_policies(svc: ConciliumService, project_id: str) -> list[dict[str, Any]]:
    """Validate all saved WMP policies without running the full pipeline."""
    from concilium.domain.services.planning.mobilizacao_simulator import WorkforcePolicySimulator

    policies = svc._dependencies.override_service.get_mobilizacao_policies(project_id)
    if not policies:
        return [{"codigo": "VAL-WMP-NONE", "status": "OK", "mensagem": "Nenhuma política WMP salva."}]

    try:
        reference = svc._dependencies.project_service.get_benchmark_reference(project_id)
    except FileNotFoundError:
        reference = {}

    eap_items = _build_wmp_lookup((reference.get("cpus") or {}).get("itens_eap", []), "item_id")
    cpu_lookup = _build_wmp_lookup(reference.get("catalog", {}).get("cpus", []) or [], "codigo")
    producao_lookup = _build_wmp_lookup(reference.get("catalog", {}).get("produtividades", []) or [], "id")

    sim = WorkforcePolicySimulator()
    results: list[dict[str, Any]] = []
    for item_id, policy_dict in policies.items():
        _process_wmp_policy(sim, item_id, policy_dict, eap_items, cpu_lookup, producao_lookup, results)
    return results
