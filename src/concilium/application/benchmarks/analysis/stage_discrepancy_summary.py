"""SumarizaÃ§Ã£o de discrepÃ¢ncias por etapa em todos os benchmarks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DEFAULT_ROOT = Path(__file__).resolve().parents[5]


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _find_praticabilidade_keys(obj: Any, path: str = "") -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            current = f"{path}.{k}" if path else str(k)
            key_l = str(k).lower()
            if "pratic" in key_l or "produtiv" in key_l:
                hits.append({"path": current, "value": v})
            hits.extend(_find_praticabilidade_keys(v, current))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits.extend(_find_praticabilidade_keys(v, f"{path}[{i}]"))
    return hits


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _lgrs_sum_action_report(action_report: list) -> tuple:
    """Sumariza action_report em contadores de severidade e acoes abertas."""
    by_severity: dict[str, int] = {}
    abertos = 0
    for item in action_report:
        sev = str(item.get("severidade") or "S0")
        by_severity[sev] = by_severity.get(sev, 0) + 1
        if str(item.get("status_acao") or "").upper() == "ABERTA":
            abertos += 1
    return by_severity, abertos


def _load_gate_report_for_slug(slug: str | None, root: Path) -> dict[str, Any]:
    if not slug:
        return {}

    slug_norm = str(slug).strip().lower()
    candidates = [
        root / "benchmarks" / "data" / slug_norm.upper() / "artifacts" / "outputs" / "benchmark_report.json",
        root / f"benchmark_{slug_norm}.json",
        root.parent / f"benchmark_{slug_norm}.json",
    ]

    report_path = next((p for p in candidates if p.exists()), None)
    if report_path is None:
        return {}

    report = _load_json(report_path)
    quality_gates = report.get("quality_gates") or {}
    action_report = report.get("action_report") or []
    by_severity, abertos = _lgrs_sum_action_report(action_report)

    decision = report.get("status_final") or quality_gates.get("decision") or "NAO_DISPONIVEL"
    gate_decision = quality_gates.get("decision") or decision
    worst_severity = quality_gates.get("worst_severity")
    if gate_decision == "NOT_EVALUATED":
        # A partial comparison may have diagnostic item severities, but no
        # aggregate worst severity is valid until every required metric exists.
        worst_severity = None
    elif worst_severity is None:
        worst_severity = "S0"

    return {
        "status_final": decision,
        "decision": gate_decision,
        "worst_severity": worst_severity,
        "critical_metric_over_10pct": quality_gates.get("critical_metric_over_10pct"),
        "action_report_total": len(action_report),
        "action_report_abertas": abertos,
        "action_report_por_severidade": by_severity,
    }


def _ct_parse_sections(trace: dict) -> tuple:
    """Parse etapas dict, consolidacao, alignment, and disparidades from a trace."""
    prat = (trace.get("etapas") or {}).get("01_praticabilidade") or {}
    consolidacao = (trace.get("etapas") or {}).get("06_consolidacao") or {}
    alignment = consolidacao.get("benchmark_alignment") or {}
    disparidades = trace.get("disparidades") or {}
    return prat, consolidacao, alignment, disparidades


def _ct_sum_equipes_costs(equipes_det: list) -> tuple:
    """Sum monthly cost totals from equipes_detalhadas list."""
    total_mo = sum(float(eq.get("custo_mao_obra_mensal") or 0) for eq in equipes_det)
    total_eq = sum(float(eq.get("custo_equipamentos_mensal") or 0) for eq in equipes_det)
    total_diesel = sum(float(eq.get("custo_combustivel_total_mensal") or 0) for eq in equipes_det)
    total_mat = sum(float(eq.get("custo_material_mensal") or 0) for eq in equipes_det)
    return total_mo, total_eq, total_diesel, total_mat


def _bs_count_flag_rows(rows: list) -> tuple:
    """Count rows matching each boolean flag."""
    sem_prat = sum(1 for r in rows if (r.get("flags") or {}).get("sem_praticabilidade_planilha_fonte"))
    com_eq = sum(1 for r in rows if (r.get("flags") or {}).get("tem_zerados_em_equipes"))
    com_pl = sum(1 for r in rows if (r.get("flags") or {}).get("tem_zerados_em_planejamento"))
    return sem_prat, com_eq, com_pl


def _bs_aggregate_gates(rows: list) -> tuple:
    """Aggregate quality gate status/severity counts and counters."""
    status_counts: dict = {}
    severity_counts: dict = {}
    gates_missing = 0
    critical_metric_over_10pct = 0
    action_report_abertas = 0
    for row in rows:
        gates = row.get("quality_gates") or {}
        status = str(gates.get("status_final") or "NAO_DISPONIVEL")
        gate_decision = str(gates.get("decision") or status)
        raw_severity = gates.get("worst_severity")
        if gate_decision == "NOT_EVALUATED":
            sev = "NAO_AVALIADA"
        elif raw_severity is None:
            sev = "S0"
        else:
            sev = str(raw_severity)
        status_counts[status] = status_counts.get(status, 0) + 1
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        if status == "NAO_DISPONIVEL":
            gates_missing += 1
        if gates.get("critical_metric_over_10pct"):
            critical_metric_over_10pct += 1
        action_report_abertas += int(gates.get("action_report_abertas") or 0)
    return status_counts, severity_counts, gates_missing, critical_metric_over_10pct, action_report_abertas


def _collect_trace(path: Path, root: Path) -> dict[str, Any]:
    trace = _load_json(path)
    referencia_path = Path((trace.get("paths") or {}).get("referencia") or "")
    referencia = _load_json(referencia_path) if referencia_path.exists() else {}

    prat, consolidacao, alignment, disparidades = _ct_parse_sections(trace)
    gates = _load_gate_report_for_slug(trace.get("slug"), root)

    itens_zero = disparidades.get("itens_planejamento_zerados_com_quantidade") or []
    equipes_zero = disparidades.get("equipes_zeradas") or []
    praticabilidade_refs = _find_praticabilidade_keys(referencia)

    equipes_det = referencia.get("equipes_detalhadas") or []
    total_mo_ref, total_eq_ref, total_diesel_ref, total_material_ref = _ct_sum_equipes_costs(equipes_det)

    return {
        "slug": trace.get("slug"),
        "projeto": trace.get("projeto"),
        "praticabilidade_tool": {
            "fonte": prat.get("fonte"),
            "semanas_total": prat.get("semanas_total"),
            "semanas_media": prat.get("semanas_media"),
            "semanas_min": prat.get("semanas_min"),
            "semanas_max": prat.get("semanas_max"),
            "meses_media": prat.get("meses_media"),
        },
        "praticabilidade_planilha_fonte": {
            "campos_encontrados": praticabilidade_refs,
            "disponivel": bool(praticabilidade_refs),
        },
        "composicao_referencia": {
            "mao_obra_mensal_total": round(total_mo_ref, 2),
            "equipamentos_mensal_total": round(total_eq_ref, 2),
            "diesel_mensal_total": round(total_diesel_ref, 2),
            "material_mensal_total": round(total_material_ref, 2),
            "equipes_consolidadas": len(equipes_det),
        },
        "discrepancias_etapas": {
            "qtd_equipes_zeradas": len(equipes_zero),
            "qtd_itens_planejamento_zerados": len(itens_zero),
            "gap_orcamento_vs_preco_plus_eq": _safe_float(
                disparidades.get("gap_orcamento_itens_vs_tool_preco_plus_eq")
            ),
            "gap_orcamento_vs_preco_com_bdi_catalogo": _safe_float(
                disparidades.get("gap_orcamento_itens_vs_tool_preco_com_bdi_catalogo")
            ),
            "alignment_aplicada": bool(alignment.get("aplicada")),
            "erro_bruto_vs_ref": alignment.get("erro_vs_referencia"),
        },
        "flags": {
            "tem_zerados_em_equipes": len(equipes_zero) > 0,
            "tem_zerados_em_planejamento": len(itens_zero) > 0,
            "sem_praticabilidade_planilha_fonte": not bool(praticabilidade_refs),
        },
        "quality_gates": gates,
        "paths": trace.get("paths"),
    }


def _severity_score(item: dict[str, Any]) -> float:
    d = item.get("discrepancias_etapas") or {}
    gap_plus = abs(_safe_float(d.get("gap_orcamento_vs_preco_plus_eq")) or 0.0)
    gap_cat = abs(_safe_float(d.get("gap_orcamento_vs_preco_com_bdi_catalogo")) or 0.0)
    z_eq = float(d.get("qtd_equipes_zeradas") or 0) * 1_000_000.0
    z_pl = float(d.get("qtd_itens_planejamento_zerados") or 0) * 1_000_000.0
    return gap_plus + gap_cat + z_eq + z_pl


def build_summary(root: Path | None = None) -> dict[str, Any]:
    """ConstrÃ³i sumÃ¡rio de discrepÃ¢ncias por etapa para todos os benchmarks."""
    base_root = root or _DEFAULT_ROOT
    bench_data = base_root / "benchmarks" / "data"
    rows: list[dict[str, Any]] = []
    for d in sorted(bench_data.iterdir()):
        if not d.is_dir():
            continue
        trace_path = d / "extracao_intermediarios.json"
        if not trace_path.exists():
            continue
        rows.append(_collect_trace(trace_path, base_root))

    ranked = sorted(rows, key=_severity_score, reverse=True)
    total = len(rows)
    sem_prat_fonte, com_eq_zero, com_pl_zero = _bs_count_flag_rows(rows)
    status_counts, severity_counts, gates_missing, critical_metric_over_10pct, action_report_abertas = (
        _bs_aggregate_gates(rows)
    )

    return {
        "meta": {
            "total_benchmarks_com_extracao": total,
            "benchmarks_sem_praticabilidade_na_planilha_fonte": sem_prat_fonte,
            "benchmarks_com_equipes_zeradas": com_eq_zero,
            "benchmarks_com_itens_planejamento_zerados": com_pl_zero,
            "quality_gate_status_counts": status_counts,
            "quality_gate_severity_counts": severity_counts,
            "benchmarks_sem_quality_gate": gates_missing,
            "benchmarks_critical_metric_over_10pct": critical_metric_over_10pct,
            "acoes_granulares_abertas_total": action_report_abertas,
        },
        "top_discrepancias": ranked[:10],
        "benchmarks": rows,
    }
