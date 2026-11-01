"""Skill 06 — Resultado Financeiro (Consolidado, NEP-041 Fase 4).

Unifica o cluster financeiro em uma única skill gate:
  1. Precificação unitária (antiga 06)     → seção `planejamento`
  2. Custos indiretos (antiga 07)          → seção `indiretos`
  3. Consolidação financeira (antiga 08)   → seção `resultado`

Os três estágios são executados em sequência (06→07→08), preservando o fluxo de
dados exato: 08 depende das saídas de 06 e 07. Cada estágio produz seções
canônicas disjuntas, threaded pelo canônico. Comportamento numericamente idêntico
ao pipeline de 3 skills anterior.

A lógica de cada estágio permanece intacta nos sub-pacotes _precificacao/,
_indiretos/ e _consolidacao/ (cópias fiéis das skills originais, sem colisão de
nomes de helper).
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

from concilium.application.scheduling.pricing_report_adapter import (
    build_pricing_report_evidence_context,
)
from concilium.application.scheduling.skill06_p17_cost_reconciliation import (
    build_skill06_p17_reconciliation,
)
from concilium.application.scheduling.skill06_p18c_consumption_preview import (
    build_p18_skill06_preview,
)
from concilium.application.skills.base import SkillResult
from concilium.domain.models.canonical import CanonicalModel, ValidacaoItem

_HERE = Path(__file__).resolve().parent


def _load_estagio(subdir: str, func_name: str):
    """Carrega a run function de um sub-pacote de estágio via importlib.

    Registra um pacote sintético apontando para o diretório do estágio (mesma
    técnica de ``_ensure_skill_package`` em concilium/application/skills/__init__.py)
    para que os imports relativos dentro de ``{subdir}/skill.py``
    (``from ._skill_helpers_x import ...``) resolvam normalmente.
    """
    stage_dir = _HERE / subdir
    path = stage_dir / "skill.py"
    pkg_name = f"_concilium_resultado_financeiro_stage_{subdir.lstrip('_')}"
    mod_name = f"{pkg_name}.skill"

    if pkg_name not in sys.modules:
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(stage_dir)]
        pkg.__package__ = pkg_name
        sys.modules[pkg_name] = pkg

    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Não foi possível carregar spec para estágio: {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(mod_name, None)
        raise
    return getattr(mod, func_name)


_run_precificacao = _load_estagio("_precificacao", "run_precificacao_unitaria")
_run_indiretos = _load_estagio("_indiretos", "run_custos_indiretos")
_run_consolidacao = _load_estagio("_consolidacao", "run_consolidacao_financeira")


def _p23_fraction(value: object) -> str:
    """Serialize exact physical/financial values without float conversion."""
    from fractions import Fraction

    if type(value) is Fraction:
        return str(value)
    if type(value) is int:
        return str(value)
    raise ValueError("P23 inventory evidence requires exact rational values")


def _p23_inventory_snapshot(context: dict[str, object]) -> dict[str, object]:
    """Convert typed P18/P19 evidence into a stable, replayable JSON witness."""
    scope = context.get("inventory_scope")
    if scope is None:
        return {
            "schema": "concilium.p23.inventory-evidence.v1",
            "status": "UNKNOWN",
            "reason": str(context.get("source_build_error") or "inventory scope unavailable"),
        }

    consumption = context.get("consumption_journal")
    evidence_rows: list[dict[str, object]] = []
    if consumption is not None:
        for line in getattr(consumption, "evidence", ()):
            measure = line.measure
            evidence_rows.append({
                "source_id": line.source_id,
                "kind": line.kind,
                "activity_id": line.activity_id,
                "week": line.week,
                "good_id": measure.good_id,
                "physical_quantity": _p23_fraction(measure.physical_quantity),
                "physical_unit": measure.physical_unit,
                "priced_quantity": _p23_fraction(measure.priced_quantity),
                "price_unit": measure.price_unit,
                "exact_cost": _p23_fraction(measure.exact_cost),
                "category": line.category,
            })

    stock = context.get("stock_projection")
    stock_rows: list[dict[str, object]] = []
    if stock is not None:
        for row in getattr(stock, "rows", ()):
            stock_rows.append({
                "good_id": row.good_id,
                "week": row.week,
                "unit": row.unit,
                "opening": _p23_fraction(row.opening),
                "external_receipts": _p23_fraction(row.external_receipts),
                "internal_generation": _p23_fraction(row.internal_generation),
                "storage_overflow": _p23_fraction(row.storage_overflow),
                "physical_demand": _p23_fraction(row.physical_demand),
                "fulfilled": _p23_fraction(row.fulfilled),
                "shortage": _p23_fraction(row.shortage),
                "closing": _p23_fraction(row.closing),
            })

    provisioning = context.get("stock_provisioning_journal")
    goods: list[dict[str, object]] = []
    arrivals: list[dict[str, object]] = []
    purchases: list[dict[str, object]] = []
    calendar_weeks: list[str] = []
    currency: str | None = None
    if provisioning is not None:
        calendar_weeks = list(provisioning.calendar_weeks)
        currency = provisioning.currency
        for good_id, good in provisioning.goods:
            goods.append({
                "good_id": good_id,
                "unit": good.unit,
                "initial_quantity": _p23_fraction(good.initial_quantity),
                "capacity": (
                    _p23_fraction(good.capacity) if good.capacity is not None else None
                ),
                "lead_time_weeks": good.lead_time_weeks,
            })
        for arrival in provisioning.arrivals:
            arrivals.append({
                "source_id": arrival.source_id,
                "good_id": arrival.good_id,
                "arrival_week": arrival.arrival_week,
                "quantity": _p23_fraction(arrival.quantity),
                "unit": arrival.unit,
                "source": arrival.source,
                "ordered_week": arrival.ordered_week,
            })
        for purchase in provisioning.purchases:
            purchases.append({
                "source_id": purchase.source_id,
                "good_id": purchase.good_id,
                "ordered_week": purchase.ordered_week,
                "arrival_week": purchase.arrival_week,
                "quantity": _p23_fraction(purchase.quantity),
                "physical_unit": purchase.physical_unit,
                "unit_price": _p23_fraction(purchase.unit_price),
                "price_unit": purchase.price_unit,
                "price_source": purchase.price_source,
                "price_reference_date": purchase.price_reference_date,
                "currency": purchase.currency,
                "category": purchase.category,
            })

    holding = context.get("holding_journal")
    holding_rows: list[dict[str, object]] = []
    if holding is not None:
        for charge in holding.charges:
            holding_rows.append({
                "good_id": charge.good_id,
                "week": charge.week,
                "closing_in_stock_unit": _p23_fraction(charge.closing_in_stock_unit),
                "billable_stock": _p23_fraction(charge.billable_stock),
                "billable_unit": charge.billable_unit,
                "holding_cost": _p23_fraction(charge.holding_cost),
            })

    return {
        "schema": "concilium.p23.inventory-evidence.v1",
        "status": scope.status,
        "source": scope.source,
        "reference_id": scope.reference_id,
        "fingerprint": scope.fingerprint,
        "consumption_evidence": evidence_rows,
        "calendar_weeks": calendar_weeks,
        "goods": goods,
        "stock_rows": stock_rows,
        "arrivals": arrivals,
        "purchases": purchases,
        "currency": currency,
        "holding_charges": holding_rows,
    }


def run_resultado_financeiro(
    canonical_in: CanonicalModel,
    inputs: dict[str, Any],
    catalogo: dict[str, Any] | None = None,
    perfil: dict[str, Any] | None = None,
    catalog_session: object | None = None,
) -> SkillResult:
    """Executa precificação + indiretos + consolidação em um passo (NEP-041 F4).

    Estágio 1 (precificação): popula `planejamento` (PU + BDI por categoria).
    Estágio 2 (indiretos): popula `indiretos` (custos indiretos por categoria).
    Estágio 3 (consolidação): popula `resultado` (margem, venda, ponto_equilibrio).

    Ordem 06→07→08 preserva o fluxo de dados: consolidação depende das duas
    saídas anteriores. Validações de todos os estágios são consolidadas.
    """
    catalogo = catalogo or {}
    perfil = perfil or {}
    inputs = inputs or {}
    validacoes: list = []

    # P18-C3 is explicitly opt-in. Always invalidate a stale preview before
    # running any downstream stage; legacy finance remains the default path.
    enabled = inputs.get("p18_consumption_preview_enabled", False)
    canonical_start = canonical_in.model_copy(update={
        "p18_consumption_preview": None,
        "p17_cost_reconciliation": None,
        "p23_inventory_evidence": None,
    })
    if type(enabled) is not bool:
        return SkillResult(canonical_start, [ValidacaoItem(
            codigo="VAL-P18-CONSUMPTION-PREVIEW",
            status="ERRO",
            mensagem="p18_consumption_preview_enabled must be an explicit boolean.",
        )])

    # Estágio 1 — Precificação unitária (gate: sem planejamento não há receita)
    res_pre = _run_precificacao(canonical_start, inputs, catalogo, perfil, catalog_session)
    validacoes.extend(res_pre.validacoes)
    if res_pre.has_errors:
        # Falha de gate: aborta antes de consolidar (preserva semântica ADR-022)
        return SkillResult(res_pre.canonical, validacoes)
    canonical = res_pre.canonical

    # Estágio 2 — Custos indiretos
    res_ind = _run_indiretos(canonical, inputs, catalogo, perfil)
    validacoes.extend(res_ind.validacoes)
    canonical = res_ind.canonical

    # Optional P18-C3 projection is a separate sidecar. It only consumes the
    # exact Skill05 P16 witness + final Skill04 schedule + resolved catalog.
    # A missing/forged source blocks this opt-in request, never falling back to
    # legacy MAT/COMB estimates and never materializing a financial GO.
    if enabled:
        try:
            preview_record = build_p18_skill06_preview(canonical, catalogo)
        except (ValueError, TypeError, KeyError, OverflowError, ZeroDivisionError) as exc:
            validacoes.append(ValidacaoItem(
                codigo="VAL-P18-CONSUMPTION-PREVIEW",
                status="ERRO",
                mensagem=f"Physical consumption preview failed closed: {exc}",
            ))
            return SkillResult(
                canonical.model_copy(update={"p18_consumption_preview": None}),
                validacoes,
            )
        canonical = canonical.model_copy(update={"p18_consumption_preview": preview_record})
        validacoes.append(ValidacaoItem(
            codigo="VAL-P18-CONSUMPTION-PREVIEW",
            status="AVISO",
            mensagem=(
                "P18 source-backed physical-consumption preview recorded separately; "
                "legacy price/margin was not overridden and this is not PROJECT_GO."
            ),
        ))

    # P21-C accepts declarative JSON only. Rebuild typed P17/P18/P19/P20
    # evidence from this canonical schedule and the server-resolved catalog;
    # never trust serialized ledgers or caller-supplied dataclass-shaped objects.
    p23_inventory_evidence: dict[str, object] | None = None
    p21_declaration = inputs.get("p21_pricing_evidence")
    if p21_declaration is not None:
        if not enabled:
            p21_context: dict[str, object] = {
                "source_build_error": (
                    "P21 pricing evidence requires p18_consumption_preview_enabled=true"
                ),
            }
        elif not isinstance(p21_declaration, dict):
            p21_context = {
                "source_build_error": "p21_pricing_evidence must be a JSON object",
            }
        else:
            try:
                p21_context = build_pricing_report_evidence_context(
                    canonical,
                    catalogo,
                    p21_declaration,
                )
            except (ValueError, TypeError, KeyError, OverflowError, ZeroDivisionError) as exc:
                p21_context = {"source_build_error": str(exc)}
        inputs = {**inputs, "p21_pricing_evidence": p21_context}
        try:
            p23_inventory_evidence = _p23_inventory_snapshot(p21_context)
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
            p23_inventory_evidence = {
                "schema": "concilium.p23.inventory-evidence.v1",
                "status": "UNKNOWN",
                "reason": f"typed P18/P19 evidence serialization failed: {exc}",
            }

    # Estágio 3 — Consolidação financeira
    res_con = _run_consolidacao(canonical, inputs, perfil)
    validacoes.extend(res_con.validacoes)
    canonical = res_con.canonical

    # P17-C audits activity K against the exact pool K/V ledger. It never
    # rewrites the legacy financial result or creates a GO certificate.
    if enabled and not res_con.has_errors and canonical.p18_consumption_preview is not None:
        try:
            reconciliation = build_skill06_p17_reconciliation(canonical)
        except (ValueError, TypeError, KeyError, OverflowError, ZeroDivisionError) as exc:
            canonical = canonical.model_copy(update={"p17_cost_reconciliation": None})
            validacoes.append(ValidacaoItem(
                codigo="VAL-P17-SKILL06-RECONCILIATION",
                status="ERRO",
                mensagem=f"Skill06 K/V reconciliation failed closed: {exc}",
            ))
        else:
            canonical = canonical.model_copy(update={"p17_cost_reconciliation": reconciliation})
            if reconciliation["status"] != "RECONCILED":
                validacoes.append(ValidacaoItem(
                    codigo="VAL-P17-SKILL06-RECONCILIATION",
                    status="ERRO",
                    mensagem="Skill06 activity K does not reconcile to the exact P16/P17 pool ledger.",
                ))
            else:
                validacoes.append(ValidacaoItem(
                    codigo="VAL-P17-SKILL06-RECONCILIATION",
                    status="AVISO",
                    mensagem="P17 K/V reconciliation preview recorded; this is not PROJECT_GO.",
                ))

    if p23_inventory_evidence is not None:
        canonical = canonical.model_copy(update={
            "p23_inventory_evidence": p23_inventory_evidence,
        })
    return SkillResult(canonical, validacoes)
