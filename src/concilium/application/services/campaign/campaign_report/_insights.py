"""ADR-070 — Campaign report generation — derivação de insights automáticos."""

from __future__ import annotations


def _insight_best_lever(resumos: list[dict], metrica: str, label: str) -> str | None:
    """Finds the resumo with the widest marginal range for a metric and formats an insight."""
    candidatos = [r for r in resumos if r.get("metrica") == metrica]
    if not candidatos:
        return None
    best = max(
        candidatos,
        key=lambda r: _marginal_range(r.get("medias", [])),
    )
    return f"Lever mais impactante em {label}: **{best['dimensao']}** (tendência: {best['tendencia']})"


def _insight_paralelismo_from_resumos(para_resumos: list[dict]) -> str | None:
    all_medias = [m for r in para_resumos for m in r.get("medias", []) if m is not None]
    if not all_medias:
        return None
    avg_para = sum(all_medias) / len(all_medias)
    return f"Paralelismo médio: {avg_para:.1f} atividades/semana"


def _insight_paralelismo_from_cenarios(cenarios: list[dict]) -> str | None:
    paras = [
        c.get("vetor_O", {}).get("paralelismo_medio")
        for c in cenarios
        if c.get("vetor_O", {}).get("paralelismo_medio") is not None
    ]
    if not paras:
        return None
    avg_para = sum(paras) / len(paras)
    return f"Paralelismo médio (cenários viáveis): {avg_para:.1f} atividades/semana"


def _insight_paralelismo(resumos: list[dict], cenarios: list[dict]) -> str | None:
    para_resumos = [r for r in resumos if r.get("metrica") == "paralelismo_medio"]
    if para_resumos:
        return _insight_paralelismo_from_resumos(para_resumos)
    return _insight_paralelismo_from_cenarios(cenarios)


def _shares_de(cenarios: list[dict], campo: str) -> list[float]:
    return [c.get("vetor_EF", {}).get(campo) for c in cenarios if c.get("vetor_EF", {}).get(campo) is not None]


def _insight_composicao_custo(cenarios: list[dict]) -> str | None:
    eq_shares = _shares_de(cenarios, "share_eq_pct")
    mo_shares = _shares_de(cenarios, "share_mo_pct")
    if not eq_shares and not mo_shares:
        return None
    avg_eq = (sum(eq_shares) / len(eq_shares) * 100) if eq_shares else 0.0
    avg_mo = (sum(mo_shares) / len(mo_shares) * 100) if mo_shares else 0.0
    dominant = "equipamento" if avg_eq > avg_mo else "mão-de-obra"
    dom_pct = avg_eq if avg_eq > avg_mo else avg_mo
    return f"Composição de custo dominante: {dom_pct:.1f}% {dominant}"


def _insight_fallback_viabilidade(cenarios: list[dict]) -> str:
    n_vi = sum(1 for c in cenarios if c.get("viabilidade") in {"APROVADO", "APROVADO_COM_RESSALVAS"})
    n_tot = len(cenarios)
    return f"Taxa de viabilidade: {n_vi}/{n_tot} cenários aprovados"


def _derive_insights(cubo: dict, cenarios: list[dict]) -> list[str]:
    """Auto-derive 3-5 bullet insights from marginal effects and scenario data."""
    insights: list[str] = []
    resumos = cubo.get("resumos_marginais", [])

    prazo_insight = _insight_best_lever(resumos, "prazo_semanas", "prazo")
    if prazo_insight:
        insights.append(prazo_insight)

    margem_insight = _insight_best_lever(resumos, "margem_pct", "margem")
    if margem_insight:
        insights.append(margem_insight)

    para_insight = _insight_paralelismo(resumos, cenarios)
    if para_insight:
        insights.append(para_insight)

    custo_insight = _insight_composicao_custo(cenarios)
    if custo_insight:
        insights.append(custo_insight)

    if not insights:
        insights.append(_insight_fallback_viabilidade(cenarios))

    return insights[:5]


def _marginal_range(medias: list) -> float:
    valid = [m for m in medias if m is not None]
    if len(valid) < 2:
        return 0.0
    return abs(max(valid) - min(valid))


