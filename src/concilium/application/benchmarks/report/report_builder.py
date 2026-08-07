"""Builder for benchmark HTML/JSON reports with quality gate analysis.

Orchestraates benchmark projection, delta computation, risk classification, and
recommendation generation for stakeholder reporting. Handles:
  - Ferramenta vs. reference data integration (pricing, costs, margins)
  - Delta analysis (absolute + percentual) with source attribution
  - Resource scheduling and peak workload computation
  - Quality gate classification (S0-S3) with decision logic (APROVADO/BLOQUEADO)
  - Action table lookup for recommended remediation by severity/metric
  - RCPSP schedule serialization (makespan, deadlines, resource peaks)

Gate decision logic: worst_severity + critical_metric_check → GO/NOGO determination.
Used by: ETL pipeline reporting, NEP-041 stakeholder dashboards.
"""

from __future__ import annotations

import importlib
from typing import Any

from ..spec.spec_loader import ProjectSpec
from .projection import BenchmarkProjection


def _load_inference_service() -> Any:
    """Dynamically load BenchmarkInferenceService from inference module.

    Raises RuntimeError if module/class unavailable.
    """
    mod = importlib.import_module("concilium.application.benchmarks.inference")
    svc_cls = getattr(mod, "BenchmarkInferenceService", None)
    if svc_cls is None:
        raise RuntimeError("BenchmarkInferenceService indisponivel")
    return svc_cls


def _add_ferramenta_data(confronto: dict[str, Any], projection: BenchmarkProjection) -> None:
    """Merge ferramenta (tool) attributes into confronto dict in-place.

    Copies: ferramenta metrics, preco_venda_fonte, ponto_equilibrio, breakdowns,
    actionable_insights.
    """
    if projection.ferramenta:
        confronto["ferramenta"] = projection.ferramenta
    _pvf = getattr(projection, "preco_venda_fonte", None)
    if _pvf:
        confronto["preco_venda_fonte"] = _pvf
    if projection.ponto_equilibrio_ferramenta:
        confronto["ponto_equilibrio_ferramenta"] = projection.ponto_equilibrio_ferramenta
    if projection.ferramenta_breakdown_direto:
        confronto["ferramenta_breakdown_direto"] = projection.ferramenta_breakdown_direto
    if projection.ferramenta_breakdown_indireto:
        confronto["ferramenta_breakdown_indireto"] = projection.ferramenta_breakdown_indireto
    if projection.actionable_insights:
        confronto["actionable_insights"] = projection.actionable_insights


def _build_deltas_from_confronto(ref_vals: dict[str, Any], fer_vals: dict[str, Any]) -> dict[str, Any]:
    """Compute delta (absolute, percentual) for key metrics: custo_direto, indireto, preco_venda.

    For preco_venda: includes fonte and homogeneo flag (source == 'total_com_bdi').
    Returns dict keyed by metric with {absoluto, percentual, fonte, homogeneo} entries.
    """
    deltas: dict[str, Any] = {}
    for key in ("custo_direto", "custo_indireto", "preco_venda"):
        ref_v = ref_vals.get(key)
        tool_v = fer_vals.get(key)
        if ref_v is not None and tool_v is not None:
            entry: dict[str, Any] = {
                "absoluto": round(tool_v - ref_v, 2),
                "percentual": round((tool_v - ref_v) / ref_v * 100, 2) if ref_v != 0 else None,
            }
            if key == "preco_venda":
                fonte = fer_vals.get("preco_venda_fonte", "indisponivel")
                entry["fonte"] = fonte
                entry["homogeneo"] = fonte == "total_com_bdi"
            deltas[key] = entry
    return deltas


def _compute_peak_recursos(scheduled_activities: list[Any], spec_acts: dict[str, Any]) -> dict[str, int]:
    """Find peak resource requirement (by type) across all weeks of schedule.

    Aggregates required_resources from spec_acts per activity per week,
    then returns max qty for each resource type.
    """
    by_week: dict[int, dict[str, int]] = {}
    for sa in scheduled_activities:
        req_res = (spec_acts.get(sa.activity_id) or {}).get("required_resources") or {}
        for w in range(sa.start_week, sa.end_week + 1):
            if w not in by_week:
                by_week[w] = {}
            for rtype, qty in req_res.items():
                by_week[w][rtype] = by_week[w].get(rtype, 0) + int(qty)
    peak: dict[str, int] = {}
    for week_usage in by_week.values():
        for rtype, qty in week_usage.items():
            if qty > peak.get(rtype, 0):
                peak[rtype] = qty
    return peak


def _build_rcpsp_schedule(canonical: Any, spec: ProjectSpec) -> dict[str, Any]:
    """Serialize RCPSP schedule from canonical cronograma and spec.

    Includes: algorithm, makespan, feasibility, deadline_weeks (if set), folga_semanas,
    activity details (start_week, end_week, duration), and peak resource requirements.
    """
    cron = canonical.cronograma
    rcpsp_spec = (spec.inputs_cronograma or {}).get("rcpsp_spec") or {}
    deadline_weeks = rcpsp_spec.get("deadline_weeks")
    rcpsp_sched: dict[str, Any] = {
        "algorithm": cron.algorithm,
        "makespan_weeks": cron.makespan_weeks,
        "is_feasible": cron.is_feasible,
        "was_relaxed": cron.was_relaxed,
    }
    if deadline_weeks is not None:
        rcpsp_sched["deadline_weeks"] = int(deadline_weeks)
        rcpsp_sched["folga_semanas"] = int(deadline_weeks) - cron.makespan_weeks
    if cron.scheduled_activities:
        rcpsp_sched["atividades"] = {
            sa.activity_id: {
                "start_week": sa.start_week,
                "end_week": sa.end_week,
                "duration_weeks": sa.duration_weeks,
            }
            for sa in cron.scheduled_activities
        }
        spec_acts = {a["item_id"]: a for a in rcpsp_spec.get("activities", [])}
        if spec_acts:
            peak = _compute_peak_recursos(cron.scheduled_activities, spec_acts)
            if peak:
                rcpsp_sched["pico_recursos"] = peak
    return rcpsp_sched


def _bq_get_cause(metric: str) -> str:
    """Map metric name to cause category for quality gate action routing.

    Routing: custo_direto → CATALOGO, indireto/margem → CONSOLIDACAO,
    preco_venda → PARAMETRIZACAO_BDI, else OUTROS.
    """
    if metric == "custo_direto":
        return "CATALOGO"
    if metric == "custo_indireto":
        return "CONSOLIDACAO"
    if metric == "preco_venda":
        return "PARAMETRIZACAO_BDI"
    if metric == "margem_pct":
        return "CONSOLIDACAO"
    return "OUTROS"


def _bq_build_gate_item(
    metric: str,
    delta: dict,
    confronto: dict,
    cause: str,
    classe: str,
    severity: str,
    phase: str,
    action: str,
    owner: str,
) -> dict:
    """Build a quality gate item with metric, delta, severity, SLA, and action.

    Severity S0 → no SLA, S1 → 48h, S2 → 24h, S3 → 0h (blocker).
    Status: NAO_APLICAVEL (S0) or ABERTA (S1-S3).
    """
    pct = delta.get("percentual")
    return {
        "metric": metric,
        "fase": phase,
        "valor_referencia": (confronto.get("referencia") or {}).get(metric),
        "valor_calculado": (confronto.get("ferramenta") or {}).get(metric),
        "delta_absoluto": delta.get("absoluto"),
        "delta_percentual": pct,
        "classe": classe,
        "severidade": severity,
        "causa_categoria": cause,
        "acao_recomendada": action,
        "owner": owner,
        "sla_horas": 0 if severity == "S0" else 48 if severity == "S1" else 24 if severity == "S2" else 0,
        "status_acao": "NAO_APLICAVEL" if severity == "S0" else "ABERTA",
    }


def _bq_compute_worst(gate_items: list) -> str:
    """Determine worst (max priority) severity across all gate items (S0 < S1 < S2 < S3)."""
    worst_rank = {"S0": 0, "S1": 1, "S2": 2, "S3": 3}
    return max((item["severidade"] for item in gate_items), key=lambda s: worst_rank.get(s, 0), default="S0")


def _bq_check_critical_over_10(gate_items: list, critical_metrics: set) -> bool:
    """Check if any critical metric exceeds 10% delta threshold (absolute value)."""
    return any(
        item["metric"] in critical_metrics
        and item["delta_percentual"] is not None
        and abs(float(item["delta_percentual"])) > 10
        for item in gate_items
    )


def _bq_get_decision(worst: str, has_critical: bool) -> str:
    """Determine pipeline decision based on worst severity and critical_metrics check.

    Logic: S3 → BLOQUEADO, S2 or has_critical → BLOQUEADO_COM_INVESTIGACAO,
    S1 → APROVADO_COM_RESSALVAS, else APROVADO.
    """
    if worst == "S3":
        return "BLOQUEADO"
    if worst == "S2" or has_critical:
        return "BLOQUEADO_COM_INVESTIGACAO"
    if worst == "S1":
        return "APROVADO_COM_RESSALVAS"
    return "APROVADO"


def _fallback_custo_total(ferramenta: dict) -> dict:
    """Compute custo_total as sum of direto + indireto if not already set."""
    if ferramenta.get("custo_total") is None:
        direto = ferramenta.get("custo_direto")
        indireto = ferramenta.get("custo_indireto")
        if direto is not None and indireto is not None:
            return {**ferramenta, "custo_total": round(direto + indireto, 2)}
    return ferramenta


def _build_composicao_item(ref_value, tool_value) -> dict | None:
    """Build composition comparison item (referencia vs. ferramenta with deltas).

    Returns None if both values None, else dict with delta_absoluto and delta_percentual.
    """
    if ref_value is None and tool_value is None:
        return None
    delta_abs = None
    delta_pct = None
    if ref_value is not None and tool_value is not None:
        delta_abs = round(tool_value - ref_value, 2)
        delta_pct = round((tool_value - ref_value) / ref_value * 100, 2) if ref_value != 0 else None
    return {
        "referencia": ref_value,
        "ferramenta": tool_value,
        "delta_absoluto": delta_abs,
        "delta_percentual": delta_pct,
    }


_ACTION_TABLE: dict[tuple[str, str], tuple[str, str]] = {
    ("S3", "custo_direto"): ("Bloquear pipeline e revalidar baseline de referencia", "engenharia-benchmarks"),
    ("S3", "custo_total"): ("Bloquear pipeline e revalidar baseline de referencia", "engenharia-benchmarks"),
    ("S3", "preco_venda"): ("Bloquear pipeline e revisar parametrizacao BDI", "engenharia-bdi"),
    ("S3", "*"): ("Bloquear pipeline e executar investigacao formal", "engenharia-benchmarks"),
    ("S2", "custo_direto"): ("Investigar derivacao da engine e reconciliar custo direto", "engenharia-benchmarks"),
    ("S2", "custo_total"): ("Investigar derivacao da engine e reconciliar custo direto", "engenharia-benchmarks"),
    ("S2", "preco_venda"): ("Revalidar BDI, tributacao e consolidacao financeira", "engenharia-bdi"),
    ("S2", "margem_pct"): ("Recalcular consolidacao e checar inconsistencias de margem", "engenharia-financeira"),
    ("S2", "*"): ("Investigar divergencia com evidencia do benchmark", "engenharia-benchmarks"),
    ("S1", "custo_direto"): ("Revisar baseline e confirmar arredondamento/derivacao", "engenharia-benchmarks"),
    ("S1", "custo_total"): ("Revisar baseline e confirmar arredondamento/derivacao", "engenharia-benchmarks"),
    ("S1", "preco_venda"): ("Revisar BDI e confirmar efeito de arredondamento", "engenharia-bdi"),
    ("S1", "*"): ("Registrar ressalva e monitorar tendencia", "engenharia-benchmarks"),
}


class BenchmarkReportBuilder:
    _PHASE_BY_METRIC = {
        "custo_direto": "06-consolidacao",
        "custo_indireto": "06-resultado-financeiro",
        "custo_total": "06-consolidacao",
        "preco_venda": "06-resultado-financeiro",
        "margem_pct": "06-consolidacao",
    }

    _CRITICAL_METRICS = {"custo_direto", "custo_total", "preco_venda", "margem_pct", "bdi_efetivo"}

    @staticmethod
    def _classify_delta(delta_pct: float | None) -> tuple[str, str]:
        if delta_pct is None:
            return "N/A", "S0"
        abs_delta = abs(delta_pct)
        if abs_delta <= 5:
            return "IDEAL", "S0"
        if abs_delta <= 15:
            return "ATENCAO", "S1"
        if abs_delta <= 30:
            return "PREOCUPANTE", "S2"
        return "CRITICO", "S3"

    @staticmethod
    def _format_phase(metric: str) -> str:
        return BenchmarkReportBuilder._PHASE_BY_METRIC.get(metric, "09-relatorio-e-artefatos")

    @staticmethod
    def _recommend_action(metric: str, severity: str) -> tuple[str, str]:
        return (
            _ACTION_TABLE.get((severity, metric))
            or _ACTION_TABLE.get((severity, "*"))
            or ("Sem acao corretiva obrigatoria", "benchmark-auditoria")
        )

    def _build_quality_gates(self, confronto: dict[str, Any]) -> dict[str, Any]:
        deltas = confronto.get("deltas") or {}
        gate_items: list[dict] = []
        for metric, delta in deltas.items():
            classe, severity = self._classify_delta(delta.get("percentual"))
            phase = self._format_phase(metric)
            action, owner = self._recommend_action(metric, severity)
            gate_items.append(
                _bq_build_gate_item(
                    metric,
                    delta,
                    confronto,
                    _bq_get_cause(metric),
                    classe,
                    severity,
                    phase,
                    action,
                    owner,
                )
            )
        worst = _bq_compute_worst(gate_items)
        has_critical = _bq_check_critical_over_10(gate_items, self._CRITICAL_METRICS)
        return {
            "decision": _bq_get_decision(worst, has_critical),
            "worst_severity": worst,
            "critical_metric_over_10pct": has_critical,
            "items": gate_items,
        }

    @staticmethod
    def _extract_referencia_confronto(ref: dict[str, Any]) -> dict[str, Any] | None:
        svc_cls = _load_inference_service()
        return svc_cls.derive(ref).reference_projection

    @staticmethod
    def _build_composicao_final(
        referencia: dict[str, Any] | None,
        ferramenta: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if referencia is None or ferramenta is None:
            return None
        ferramenta = _fallback_custo_total(ferramenta)
        itens = ["custo_direto", "custo_indireto", "custo_total", "preco_venda"]
        composicao: dict[str, Any] = {}
        for item in itens:
            entry = _build_composicao_item(referencia.get(item), ferramenta.get(item))
            if entry is not None:
                composicao[item] = entry
        return composicao or None

    def _finalize_confronto(self, confronto: dict[str, Any], ref: dict[str, Any] | None) -> None:
        if "referencia" in confronto and "ferramenta" in confronto:
            confronto["deltas"] = _build_deltas_from_confronto(confronto["referencia"], confronto["ferramenta"])
            composicao_final = self._build_composicao_final(confronto.get("referencia"), confronto.get("ferramenta"))
            if composicao_final is not None:
                confronto["composicao_final"] = composicao_final
        if "ferramenta_breakdown_direto" in confronto or "ferramenta_breakdown_indireto" in confronto:
            confronto["breakdown_por_fase"] = {
                "direto": confronto.get("ferramenta_breakdown_direto"),
                "indireto": confronto.get("ferramenta_breakdown_indireto"),
            }
        if ref and ref.get("ponto_de_equilibrio"):
            pe = ref["ponto_de_equilibrio"]
            confronto["ponto_equilibrio_referencia"] = {
                "total_hc": pe.get("total_hc"),
                "total_custo_fixo": pe.get("total_custo_fixo"),
                "equipes": len(pe.get("equipes", [])),
            }

    def build(
        self,
        spec: ProjectSpec,
        version: str | None,
        results_log: list[dict[str, Any]],
        ref: dict[str, Any] | None,
        canonical: Any,
        inference_pack: Any | None = None,
    ) -> dict[str, Any]:
        projection = BenchmarkProjection.from_canonical(canonical)
        confronto: dict[str, Any] = {}
        report: dict[str, Any] = {
            "projeto": spec.nome,
            "slug": spec.slug,
            "versao": version,
            "skills_log": results_log,
            "referencia_disponivel": ref is not None,
            "confronto": confronto,
        }
        if ref:
            ref_confronto = getattr(inference_pack, "reference_projection", None)
            if ref_confronto is None:
                ref_confronto = self._extract_referencia_confronto(ref)
            if ref_confronto is not None:
                confronto["referencia"] = ref_confronto
        _add_ferramenta_data(confronto, projection)
        self._finalize_confronto(confronto, ref)
        report["quality_gates"] = self._build_quality_gates(confronto)
        report["action_report"] = report["quality_gates"]["items"]
        report["status_final"] = report["quality_gates"]["decision"]
        if canonical is not None:
            cron = getattr(canonical, "cronograma", None)
            if cron is not None:
                report["rcpsp_schedule"] = _build_rcpsp_schedule(canonical, spec)
        if any(entry.get("status") == "ERRO" for entry in results_log):
            report["status_final"] = "INVIAVEL"
        return report
