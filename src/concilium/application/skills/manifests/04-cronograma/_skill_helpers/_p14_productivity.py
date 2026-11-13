"""P14-C: fail-closed physical-productivity provenance and stale-output invalidation."""
from __future__ import annotations

import math
from typing import Any

from concilium.domain.models.canonical import CanonicalModel, ValidacaoItem


def _invalidate_rejected_schedule(canonical: CanonicalModel) -> CanonicalModel:
    """Remove stale schedule-derived outputs after a rejected schedule attempt."""
    return canonical.model_copy(
        update={
            **_invalidate_derived_costs(canonical),
            "cronograma": None,
            "intervalos_atividade": [],
            "curvas_forca": [],
            "analise_campanhas": None,
            "mob_schedule": None,
            "p15_physical_resolution": None,
        }
    )


def _invalidate_derived_costs(canonical: CanonicalModel) -> dict[str, Any]:
    """Clear stale economic outputs while retaining declared resource configuration."""
    # Skill 05 now tags inferred types/default pools explicitly. For old persisted
    # snapshots, classify a missing-provenance FUNC-/EQUIP- type as inferred only
    # when its matching legacy synthetic pool (1000/1000, zero acquisition cost)
    # was recognized above. Explicit Skill 03 configuration is always preserved.
    legacy_inferred_type_ids = {
        pool.tipo_id
        for pool in (canonical.recurso_pool or [])
        if pool.proveniencia == "DERIVADO_SKILL05"
        and pool.tipo_id.startswith(("FUNC-", "EQUIP-"))
    }
    return {
        "tipos_recurso": [
            item for item in (canonical.tipos_recurso or [])
            if item.proveniencia != "DERIVADO_SKILL05"
            and not (
                item.id in legacy_inferred_type_ids
                and "proveniencia" not in item.model_fields_set
            )
        ],
        "recurso_pool": [
            item for item in (canonical.recurso_pool or [])
            if item.proveniencia != "DERIVADO_SKILL05"
        ],
        "equipes_diretas": [],
        "resultado": None,
        "resultado_reconciliado": None,
        "ponto_equilibrio": [],
        "custos_atividades": [],
        "diagnostico_pe": None,
        "backtracking_pe": None,
        "memorial_calculo_bdi": None,
        "tabela_bdi_efetiva": None,
        "contratos_recurso": [],
        "cadeias_perpetuacao": [],
        "instancias_recurso": [],
        "composicao_equipes_atividade": [],
        "resumo_utilizacao_contratos": [],
        "relatorio_oportunidades": None,
        "requisitos": [],
        "alocacoes": [],
        "conflitos_pico": [],
        "recursos_consumiveis": [],
        "resumo_estoque_consumiveis": [],
        "indiretos": [],
        "indiretos_semanal": [],
        "indiretos_com_bdi": [],
        "bridge_analysis": None,
        "cost_criticality_report": None,
        "criticality_report": None,
        "replan_suggestions": None,
        "plan_space_result": None,
        "cpu_exposure_perfis": [],
        "relatorio_criticidade": None,
        "relatorio_sensibilidade": None,
        "relatorio_intervencao": None,
        "curva_abc_insumo": None,
        "s_curve": None,
        "cubo_analitico": None,
    }



def _normalize_output_quantity_unit(raw: str) -> str:
    """Canonicalize spelling of an output quantity, never convert dimensions."""
    return raw.strip().casefold().replace("³", "3").replace(" ", "")


def _capacity_output_quantity_unit(raw: str) -> str:
    """Read a declared hourly capacity as an output quantity per hour.

    CapacidadeElemento stores capacidade_horaria; both the legacy plain
    quantity ("m3") and explicit hourly rate ("m³/h") represent m3/h.
    No cross-dimension conversion (e.g. tonnes to cubic metres) is inferred.
    """
    unit = _normalize_output_quantity_unit(raw)
    for suffix in ("/hour", "/hora", "/hr", "/h"):
        if unit.endswith(suffix):
            return unit[: -len(suffix)]
    return unit


def _positive_finite_rate(raw: Any) -> bool:
    """Reject invalid/oversized numeric inputs without raising before the gate."""
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return False
    try:
        value = float(raw)
    except (OverflowError, ValueError):
        return False
    return math.isfinite(value) and value > 0


def _preflight_physical_productivity(
    canonical: CanonicalModel,
    cpu_lookup: dict,
    producao_lookup: dict,
    *,
    certified: bool,
    validacoes: list[ValidacaoItem],
) -> tuple[bool, bool]:
    """Validate real physical source and numeric rate before calling a solver.

    An identifier/field spelling is NOT a calibration. In the absence of
    graph + versioned external source, a rate is an exploratory assumption.
    The downstream project-wide GO certificate remains outside Skill04.
    """
    invalid = False
    unverified = False
    for item in canonical.eap or []:
        cpu = cpu_lookup.get(item.cpu_id) or {}
        meta = cpu.get("cpu_meta") or {}
        if not isinstance(meta, dict):
            meta = {}
        prod_id = cpu.get("producao_id_ref")
        prod = producao_lookup.get(prod_id) if prod_id else None
        if not isinstance(prod, dict):
            prod = {}
        item_invalid = False
        for name, raw in (
            ("cpu_meta.producao_horaria", meta.get("producao_horaria")),
            ("producao_horaria", prod.get("producao_horaria")),
            ("valor_horario", prod.get("valor_horario")),
        ):
            if raw is not None and not _positive_finite_rate(raw):
                invalid = True
                item_invalid = True
                validacoes.append(
                    ValidacaoItem(
                        codigo="VAL-CRON-PROD-INVALID",
                        status="ERRO",
                        mensagem=f"F(m) inválido em {item.item_id}/{name}; exigir taxa física positiva e finita.",
                    )
                )
        # An existing graph is not necessarily a usable physical graph.
        # Validate the *actual* typed capacity, references and output units
        # before the manual/automatic scheduler can throw or assume capacity.
        raw_graph = prod.get("grafo_sinergia")
        has_graph = isinstance(raw_graph, dict) and bool(raw_graph)
        graph_verified = False
        if raw_graph is not None and not isinstance(raw_graph, dict):
            invalid = True
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-CRON-PROD-INVALID",
                    status="ERRO",
                    mensagem=f"F(m) inválido em {item.item_id}: grafo físico malformado.",
                )
            )
        if has_graph:
            from concilium.domain.services.sinergia_equipe import (
                construir_producao_catalogo_para_sinergia,
                resolver_producao_efetiva,
            )

            # Pydantic float coercion accepts booleans and can conceal invalid
            # non-bottleneck capacities. Validate *every* raw physical rate
            # before graph construction, float conversion or max-flow.
            for collection in ("capacidades", "arestas_fluxo"):
                entries = raw_graph.get(collection, [])
                if not isinstance(entries, list):
                    entries = [None]
                for index, entry in enumerate(entries):
                    raw_rate = entry.get("capacidade_horaria") if isinstance(entry, dict) else None
                    if not _positive_finite_rate(raw_rate):
                        item_invalid = True
                        invalid = True
                        validacoes.append(
                            ValidacaoItem(
                                codigo="VAL-CRON-PROD-INVALID",
                                status="ERRO",
                                mensagem=(
                                    f"F(m) inválido em {item.item_id}/grafo_sinergia."
                                    f"{collection}[{index}].capacidade_horaria: "
                                    "exigir número físico positivo, finito e não booleano."
                                ),
                            )
                        )
            typed = None
            if not item_invalid:
                typed = construir_producao_catalogo_para_sinergia(prod)
                if typed is not None:
                    resolution = resolver_producao_efetiva(typed)
                    derived = resolution.derivacao
                    physical_rate = derived.producao_horaria_derivada if derived else None
                    graph_verified = (
                        not any(v.status == "ERRO" for v in resolution.validacoes)
                        and physical_rate is not None
                        and math.isfinite(physical_rate)
                        and physical_rate > 0
                    )
            if not graph_verified and not item_invalid:
                invalid = True
                validacoes.append(
                    ValidacaoItem(
                        codigo="VAL-CRON-PROD-INVALID",
                        status="ERRO",
                        mensagem=f"F(m) inválido em {item.item_id}: grafo sem capacidade física validável.",
                    )
                )

            # Dimensional checks must reach the *internal* rate inputs as
            # well as the output label; relabeling t/h as m3/h proves nothing.
            # Flow edges have no separate unit field in their schema and
            # inherit the output unit by the catalog contract.
            unit_eap = _normalize_output_quantity_unit(str(item.unidade or ""))
            unit_producao = _normalize_output_quantity_unit(str(prod.get("unidade") or ""))
            if not unit_eap or unit_eap != unit_producao:
                invalid = True
                validacoes.append(
                    ValidacaoItem(
                        codigo="VAL-CRON-PROD-UNIT",
                        status="ERRO",
                        mensagem=(
                            f"Unidade física incompatível em {item.item_id}: "
                            f"EAP={item.unidade!r}, produtividade={prod.get('unidade')!r}; "
                            "conversão dimensional não demonstrada."
                        ),
                    )
                )
            if typed is not None and typed.grafo_sinergia is not None:
                mismatched_capacity_ids = [
                    cap.elemento_id
                    for cap in typed.grafo_sinergia.capacidades
                    if not unit_producao or _capacity_output_quantity_unit(cap.unidade) != unit_producao
                ]
                if mismatched_capacity_ids:
                    invalid = True
                    graph_verified = False
                    validacoes.append(
                        ValidacaoItem(
                            codigo="VAL-CRON-PROD-UNIT",
                            status="ERRO",
                            mensagem=(
                                f"Capacidades de F(m) em unidade diferente de {prod.get('unidade')!r} "
                                f"para {item.item_id}: {sorted(mismatched_capacity_ids)}."
                            ),
                        )
                    )

        source_info = prod.get("origem")
        audit_info = prod.get("auditoria")
        source_info = source_info if isinstance(source_info, dict) else {}
        audit_info = audit_info if isinstance(audit_info, dict) else {}
        origin = source_info.get("fonte_id") or prod.get("source_id") or prod.get("fonte")
        version = audit_info.get("versao") or prod.get("source_version") or prod.get("versao")
        # The versioned Producao contract stores these under origem/auditoria;
        # producao_horaria can be the derived output of a physical graph.
        # cpu_meta.producao_horaria overrides the graph and is not proof.
        source_proved = (
            bool(prod_id) and graph_verified and isinstance(origin, str)
            and bool(origin.strip()) and isinstance(version, str)
            and bool(version.strip()) and "producao_horaria" not in meta
        )
        if not source_proved:
            unverified = True
            if certified:
                validacoes.append(
                    ValidacaoItem(
                        codigo="VAL-CRON-PROD-CERT",
                        status="ERRO",
                        mensagem=(
                            f"NOGO: {item.item_id} sem grafo F(m), versão/fonte física "
                            "documentada ou com taxa legada que substitui o grafo."
                        ),
                    )
                )
    return invalid, unverified
