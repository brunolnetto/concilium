"""DiagnosticoPEBuilder — decomposição causal do gap de PE (ADR-060).

Fórmulas exatas (ADR-060 §3):
  C_real = c_fixo/S × N_total + c_diesel/S × Q̃   (diesel cancela no gap)
  gap_direto = c_fixo/S × N_total × (1 − η_real)
  η_real = Σ p(t)n(t) / Σ n(t)
  ε_cross = η_real − p̄ + Cov(n,p)/n̄
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from concilium.domain.constants import SEMANAS_POR_MES
from concilium.domain.models.analytics.diagnostico_pe import (
    DiagnosticoPEItem,
    DiagnosticoPERelatorio,
    FatorPE,
)

_CROSS_TERM_THRESHOLD = 0.05


# ADR-082: fator efetivo η_j = fator_total = η_s · η_p · η_w
def _eta(d: Any) -> float:
    ft = getattr(d, "fator_total", None)
    return float(ft) if ft is not None else float(d.eficiencia)


# NEP-035: pesos = q_max_celula (capacidade teórica); fallback = n_j (retrocompat)
def _weight(d: Any) -> float:
    qmax = getattr(d, "q_max_celula", None)
    if qmax is not None and float(qmax) > 0:
        return float(qmax)
    return float(d.num_equipes)


def _compute_medias_semanais(active: list, T_weeks: int) -> dict[str, float]:
    """Calcula as médias por semana (clima, η_s, η_p, η_w, calendário) das semanas ativas."""
    return {
        "clima_medio": sum(float(getattr(d, "fator_clima", _eta(d))) for d in active) / T_weeks,
        "eta_s_medio": sum(float(getattr(d, "eta_s", 1.0)) for d in active) / T_weeks,
        "eta_p_medio": sum(float(getattr(d, "eta_p", float(getattr(d, "fator_clima", 1.0)))) for d in active) / T_weeks,
        "eta_w_medio": sum(float(getattr(d, "eta_w", float(d.eficiencia))) for d in active) / T_weeks,
        "calendario_medio": sum(float(getattr(d, "fator_calendario", 1.0)) for d in active) / T_weeks,
    }


def _compute_cross_term(
    p_medio: float, eta_real: float, prod_weighted: float, Q_max_total: float, T_weeks: int
) -> tuple[float, float]:
    """Calcula o termo cruzado (cov_np) e eps_cross (Seção 5 do modelo)."""
    p_medio_cap = prod_weighted / T_weeks if T_weeks > 0 else p_medio
    cov_np = p_medio_cap - p_medio * (Q_max_total / T_weeks)
    eps_cross = eta_real - p_medio + cov_np / max(Q_max_total / T_weeks, 1e-9)
    return cov_np, eps_cross


def _compute_item_metrics(active: list) -> tuple[dict[str, float], bool]:
    """Calcula η_real, p_medio, cov_np, eps_cross, validade a partir das semanas ativas.

    NEP-035 (Seção 5): agregação correta por capacidade máxima q_max_celula.

    A eficiência agregada é a média ponderada pelas capacidades:
        η_agg = Σ_j(η_j · q_max_j) / Σ_j(q_max_j)

    Quando os pesos q_max são iguais entre semanas (ramp plano) isso reduz à
    média simples. Quando variam (ramp/subalocação), a ponderação evita que
    semanas com alta capacidade (mais equipes) subdeterminem a eficiência média.

    O termo cruzado `eps_cross` (Cov(n, p)/n̄) quantifica o acoplamento entre
    fatores na agregação: eps_cross ≈ 0 indica que os fatores são separáveis no
    agregado; |eps_cross| > CROSS_TERM_THRESHOLD indica acoplamento material.
    """
    N_total = sum(d.num_equipes for d in active)

    Q_max_total = sum(_weight(d) for d in active)
    prod_weighted = sum(_eta(d) * _weight(d) for d in active)
    eta_real = prod_weighted / Q_max_total if Q_max_total > 0 else 1.0
    T_weeks = len(active)
    p_medio = sum(_eta(d) for d in active) / T_weeks
    medias = _compute_medias_semanais(active, T_weeks)
    calendario_medio = medias["calendario_medio"]
    calendario_ponderado_n = (
        sum(float(getattr(d, "fator_calendario", 1.0)) * _weight(d) for d in active) / Q_max_total
        if Q_max_total > 0
        else 1.0
    )
    n_medio = N_total / T_weeks
    # Termo cruzado calculado a partir dos pesos de capacidade (Seção 5 do modelo)
    cov_np, eps_cross = _compute_cross_term(p_medio, eta_real, prod_weighted, Q_max_total, T_weeks)
    validade = abs(cov_np / (n_medio * p_medio)) < _CROSS_TERM_THRESHOLD if n_medio * p_medio > 0 else True
    return {
        "N_total": N_total,
        "Q_max_total": Q_max_total,
        "prod_weighted": prod_weighted,
        "eta_real": eta_real,
        "T_weeks": T_weeks,
        "p_medio": p_medio,
        "clima_medio": medias["clima_medio"],
        "eta_s_medio": medias["eta_s_medio"],
        "eta_p_medio": medias["eta_p_medio"],
        "eta_w_medio": medias["eta_w_medio"],
        "calendario_medio": calendario_medio,
        "calendario_ponderado_n": calendario_ponderado_n,
        "n_medio": n_medio,
        "cov_np": cov_np,
        "eps_cross": eps_cross,
    }, validade


def _compute_f1_quantizacao(canonical_in: Any, resultado: Any, gap_total: float) -> float:
    pe_items = getattr(canonical_in, "ponto_equilibrio", None) or []
    gap_escala = sum(float(getattr(pe, "gap_escala_abs", 0.0) or 0.0) for pe in pe_items)
    if gap_escala <= 0:
        return 0.0
    proj_total = float(getattr(getattr(resultado, "custo", None), "total", 1) or 1)
    return abs(gap_total) * gap_escala / max(proj_total, 1.0)


def _build_gap_fatores(
    c_fixo_semanal: float,
    metrics: dict[str, float],
    ca: Any,
    canonical_in: Any,
    gap_total: float,
    resultado: Any,
) -> tuple[tuple[FatorPE, ...], float]:
    """Decompõe o gap em fatores causais e retorna (fatores, f1_rs)."""
    N_total = metrics["N_total"]
    eta_real = metrics["eta_real"]
    p_medio = metrics["p_medio"]
    clima_medio = metrics.get("clima_medio", p_medio)
    calendario_medio = metrics.get("calendario_medio", 1.0)
    calendario_ponderado_n = metrics.get("calendario_ponderado_n", calendario_medio)

    gap_direto_estimado = c_fixo_semanal * N_total * (1.0 - eta_real)
    gap_ind_estimado = float((ca.custo_indireto_atribuido if ca else 0) * (1.0 - eta_real))
    gap_total_estimado = gap_direto_estimado + gap_ind_estimado
    escala = abs(gap_total) / max(abs(gap_total_estimado), 1.0) if gap_total_estimado else 1.0

    # Base de indisponibilidade civil+climática separada por pesos relativos.
    indisponibilidade_total = c_fixo_semanal * N_total * max(0.0, 1.0 - p_medio) * escala
    peso_clima = max(0.0, 1.0 - clima_medio)
    peso_cal = max(0.0, 1.0 - calendario_medio)
    soma_pesos = peso_clima + peso_cal
    if soma_pesos > 0:
        f_eta_clima_rs = indisponibilidade_total * (peso_clima / soma_pesos)
        gap_cal_total_rs = indisponibilidade_total * (peso_cal / soma_pesos)
    else:
        f_eta_clima_rs = indisponibilidade_total
        gap_cal_total_rs = 0.0

    # Parcela evitável por alocação temporal (concentração em semanas com baixa operação civil).
    eps_cal_timing = max(0.0, calendario_medio - calendario_ponderado_n)
    f_calendario_rs = c_fixo_semanal * N_total * eps_cal_timing * escala
    f_calendario_rs = min(max(0.0, f_calendario_rs), gap_cal_total_rs)
    f_calendario_estrutural_rs = max(0.0, gap_cal_total_rs - f_calendario_rs)

    f_cross_rs = c_fixo_semanal * N_total * max(0.0, p_medio - eta_real) * escala
    f_ind_clima_rs = gap_ind_estimado * p_medio / max(eta_real, 0.01) * escala if eta_real < p_medio else 0.0
    f_ind_ramp_rs = max(0.0, gap_ind_estimado * escala - f_ind_clima_rs)
    f_residual_rs = max(
        0.0,
        abs(gap_total)
        - f_eta_clima_rs
        - f_calendario_rs
        - f_calendario_estrutural_rs
        - f_cross_rs
        - f_ind_clima_rs
        - f_ind_ramp_rs,
    )

    f1_rs = _compute_f1_quantizacao(canonical_in, resultado, gap_total)

    fatores_raw = [
        ("F_ETA_CLIMA", f_eta_clima_rs),
        ("F_CALENDARIO", f_calendario_rs),
        ("F_CALENDARIO_ESTRUTURAL", f_calendario_estrutural_rs),
        ("F_ETA_CROSS", f_cross_rs),
        ("F_IND_CLIMA", f_ind_clima_rs),
        ("F_IND_RAMP", f_ind_ramp_rs),
        ("F1_QUANTIZACAO", f1_rs),
        ("F_RESIDUAL", f_residual_rs),
    ]
    fatores = _build_fator_pe_tuple(fatores_raw)
    return fatores, f1_rs


def _resolve_pe_prices(pe: Any, plan: Any, ca: Any) -> tuple[float, float]:
    """Retorna (preco_venda, custo_real) priorizando dados de plano/ca sobre PE.

    ADR-162: `preco_venda` usa `sem_bdi` — PE compara custo×custo (BDI é margem
    deliberada aplicada depois do equilíbrio, ver `_balanco_pe.py::_bpe_build_lookup_maps`).
    Antes desta correção, este era o único ponto da máquina de PE ainda usando
    `com_bdi`, inconsistente com `_ponto_equilibrio.py` (venda_sem_bdi/pu_catalogo_unitario)
    e com `_compute_recalibracao_l` abaixo (mesmo arquivo, já usa `sem_bdi` para `C_cat`).
    """
    preco_venda = float(
        (plan.subtotal.sem_bdi.total if plan and plan.subtotal and plan.subtotal.sem_bdi else 0) or pe.custo_venda_cpu
    )
    custo_real = float((ca.custo_total_atividade if ca else 0) or pe.custo_operacional_real or pe.custo_fixo_equipe)
    return preco_venda, custo_real


def _compute_recalibracao_l(gap_total: float, plan: Any, T_efetivo: float) -> float:
    """Calcula delta_l necessário para fechar o gap de PE."""
    C_cat = float((plan.subtotal.sem_bdi.total if plan and plan.subtotal and plan.subtotal.sem_bdi else 0) or 1)
    return abs(gap_total) / max(C_cat / (1.0 - T_efetivo), 1.0) if C_cat > 0 else 0.0


def _resolve_cubo_analitico(canonical_in: Any) -> Any | None:
    cubo = getattr(canonical_in, "cubo_analitico", None)
    if cubo is not None:
        return cubo
    try:
        from concilium.domain.services.analytics.cubo_analitico_builder import CuboAnaliticoBuilder

        return CuboAnaliticoBuilder().build(canonical_in)
    except Exception:
        return None


def _build_activity_week_map(cubo: Any | None) -> dict[str, dict[str, dict[str, float]]]:
    if cubo is None:
        return {}

    per_activity: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    for celula in getattr(cubo, "celulas", ()):
        natureza = "direto" if getattr(celula, "componente_bdi", "") == "custo_direto" else "indireto"
        atividade = str(getattr(celula, "atividade_id", ""))
        semana = str(getattr(celula, "semana_iso", ""))
        if not atividade or not semana:
            continue
        week_data = per_activity[atividade].setdefault(semana, {"direto": 0.0, "indireto": 0.0, "total": 0.0})
        valor = float(getattr(celula, "valor_rs", 0.0) or 0.0)
        week_data[natureza] += valor
        week_data["total"] += valor

    return {atividade: dict(periodos) for atividade, periodos in per_activity.items()}


def _build_item_cubo_hint(
    activity_week_map: dict[str, dict[str, dict[str, float]]], atividade_id: str
) -> dict[str, Any]:
    periodos = activity_week_map.get(atividade_id) or {}
    if not periodos:
        return {}

    custo_direto = sum(float(v.get("direto", 0.0)) for v in periodos.values())
    custo_indireto = sum(float(v.get("indireto", 0.0)) for v in periodos.values())
    natureza = "direto" if custo_direto >= custo_indireto else "indireto"
    janela = max(periodos.items(), key=lambda kv: float(kv[1].get("total", 0.0)))[0]
    explicacao = (
        "Concentracao de custo direto na janela critica"
        if natureza == "direto"
        else "Concentracao de custo indireto na janela critica"
    )

    return {
        "janela_critica_iso": janela,
        "natureza_dominante": natureza,
        "custo_direto_cubo_rs": round(custo_direto, 2),
        "custo_indireto_cubo_rs": round(custo_indireto, 2),
        "explicacao_janela": f"{explicacao}: {janela}",
    }


def _build_explicacao_natureza_periodo(
    cubo: Any | None,
    activity_week_map: dict[str, dict[str, dict[str, float]]],
    itens_diag: list[DiagnosticoPEItem],
) -> dict[str, Any]:
    if cubo is None:
        return {}

    itens: dict[str, dict[str, Any]] = {}
    for item in itens_diag:
        hint = _build_item_cubo_hint(activity_week_map, item.atividade_id)
        if hint:
            itens[item.atividade_id] = hint

    janelas_prioritarias = sorted(
        (
            {
                "atividade_id": item.atividade_id,
                "descricao": item.descricao,
                "janela_iso": hint.get("janela_critica_iso"),
                "natureza": hint.get("natureza_dominante"),
                "gap_rs": round(abs(item.gap_rs), 2),
            }
            for item in itens_diag
            for hint in [itens.get(item.atividade_id, {})]
            if hint
        ),
        key=lambda entry: float(entry.get("gap_rs", 0.0)),
        reverse=True,
    )[:5]

    return {
        "fonte": "cubo_analitico",
        "resumo_global_natureza": cubo.resumo_por_natureza(),
        "resumo_natureza_por_periodo": {
            "semana": cubo.resumo_por_natureza_temporal("semana"),
            "mes": cubo.resumo_por_natureza_temporal("mes"),
        },
        "itens": itens,
        "janelas_prioritarias": janelas_prioritarias,
    }


def _resolve_active_distribuicao(equipe: Any, sa: Any) -> list | None:
    """Retorna as semanas com equipes ativas, ou None se equipe/sa/distribuição ausentes."""
    if not equipe or not sa or not sa.distribuicao_semanal:
        return None
    active = [d for d in sa.distribuicao_semanal.values() if d.num_equipes > 0]
    return active or None


def _build_pe_item(
    item_id: str,
    eap: Any,
    metrics: dict[str, float],
    fatores: tuple,
    preco_venda: float,
    custo_real: float,
    gap_total: float,
    validade_aprox: bool,
    L_aplicado: float,
    delta_l: float,
    item_cubo_hint: dict[str, Any] | None,
) -> DiagnosticoPEItem:
    """Monta o DiagnosticoPEItem a partir das métricas e fatores já calculados."""
    descricao = str(eap.descricao if eap and hasattr(eap, "descricao") else item_id)
    cpu_id = str(eap.cpu_id if eap else "?")
    hint = item_cubo_hint or {}

    return DiagnosticoPEItem(
        atividade_id=item_id,
        cpu_id=cpu_id,
        descricao=descricao[:80],
        preco_venda=round(preco_venda, 2),
        custo_realizado=round(custo_real, 2),
        gap_rs=round(gap_total, 2),
        pct_gap_sobre_venda=round(gap_total / max(preco_venda, 1.0), 4),
        eta_real=round(metrics["eta_real"], 4),
        p_medio_uniforme=round(metrics["p_medio"], 4),
        cov_n_p=round(metrics["cov_np"], 6),
        eps_cross=round(metrics["eps_cross"], 6),
        validez_aproximacao=validade_aprox,
        n_total=round(metrics["N_total"], 2),
        fatores=fatores,
        l_aplicado=round(L_aplicado, 4),
        l_requerido=round(L_aplicado + delta_l, 4),
        delta_l=round(delta_l, 4),
        janela_critica_iso=hint.get("janela_critica_iso"),
        natureza_dominante=hint.get("natureza_dominante"),
        custo_direto_cubo_rs=float(hint.get("custo_direto_cubo_rs", 0.0) or 0.0),
        custo_indireto_cubo_rs=float(hint.get("custo_indireto_cubo_rs", 0.0) or 0.0),
        explicacao_janela=hint.get("explicacao_janela"),
    )


def _process_pe_item(
    pe: Any,
    equipe_lookup: dict,
    sched_lookup: dict,
    plan_lookup: dict,
    ca_lookup: dict,
    eap_lookup: dict,
    L_aplicado: float,
    T_efetivo: float,
    canonical_in: Any,
    resultado: Any,
    item_cubo_hint: dict[str, Any] | None = None,
) -> tuple[DiagnosticoPEItem | None, bool]:
    """Processa um item PE e retorna (item_diagnóstico, cross_term_presente) ou (None, False)."""
    item_id = pe.item_id
    eap = eap_lookup.get(item_id)
    equipe = equipe_lookup.get(item_id)
    sa = sched_lookup.get(item_id)
    plan = plan_lookup.get(item_id)
    ca = ca_lookup.get(item_id)

    preco_venda, custo_real = _resolve_pe_prices(pe, plan, ca)
    gap_total = preco_venda - custo_real

    active = _resolve_active_distribuicao(equipe, sa)
    if active is None:
        return None, False
    assert equipe is not None  # narrowed: _resolve_active_distribuicao só retorna não-None se equipe é truthy

    metrics, validade_aprox = _compute_item_metrics(active)
    c_fixo_semanal = (equipe.custo_mao_obra_mensal + equipe.custo_equipamentos_mensal) / SEMANAS_POR_MES
    fatores, _ = _build_gap_fatores(c_fixo_semanal, metrics, ca, canonical_in, gap_total, resultado)

    delta_l = _compute_recalibracao_l(gap_total, plan, T_efetivo)

    item = _build_pe_item(
        item_id,
        eap,
        metrics,
        fatores,
        preco_venda,
        custo_real,
        gap_total,
        validade_aprox,
        L_aplicado,
        delta_l,
        item_cubo_hint,
    )
    return item, not validade_aprox


def _dpb_empty_relatorio(projeto_id: str) -> DiagnosticoPERelatorio:
    return DiagnosticoPERelatorio(
        projeto_id=projeto_id,
        gerado_em=datetime.now(UTC).isoformat(),
        n_itens_deficit=0,
        gap_total_rs=0.0,
        gap_evitavel_rs=0.0,
        gap_estrutural_rs=0.0,
        fator_dominante_label="—",
        aviso_cross_term=False,
        l_medio_requerido=0.0,
        itens_deficit=(),
        consistencia_validada=True,
        explicacao_natureza_periodo={},
    )


def _dpb_build_lookups(canonical_in: Any) -> tuple[dict, dict, dict, dict, dict]:
    cron = canonical_in.cronograma
    sched_lookup = _build_lookup_by_key(cron.scheduled_activities if cron else [], "activity_id")
    equipe_lookup = _build_lookup_by_key(canonical_in.equipes_diretas, "item_id")
    plan_lookup = _build_lookup_by_key(canonical_in.planejamento, "item_id")
    ca_lookup = _build_lookup_by_key(canonical_in.custos_atividades, "atividade_id")
    eap_lookup = _build_lookup_by_key(canonical_in.eap, "item_id")
    return sched_lookup, equipe_lookup, plan_lookup, ca_lookup, eap_lookup


def _build_lookup_by_key(items, key: str) -> dict:
    result: dict = {}
    if not items:
        return result
    for item in items:
        result[getattr(item, key)] = item
    return result


def _weighted_l_medio(itens_diag: list) -> float:
    if not itens_diag:
        return 0.0
    numerator = 0.0
    denominator = 0.0
    for i in itens_diag:
        w = abs(i.gap_rs)
        numerator += i.l_requerido * w
        denominator += w
    return numerator / max(denominator, 1.0)


def _dominant_fator(itens_diag: list) -> str:
    todas_causas: dict[str, float] = defaultdict(float)
    for item in itens_diag:
        for f in item.fatores:
            todas_causas[f.label] += f.gap_rs
    return max(todas_causas, key=lambda k: todas_causas[k]) if todas_causas else "—"


def _build_fator_pe_tuple(fatores_raw: list) -> tuple:
    total_attr = 0.0
    for _, v in fatores_raw:
        total_attr += v
    result = []
    for cod, v in sorted(fatores_raw, key=lambda kv: kv[1], reverse=True):
        if v > 0.50:
            result.append(FatorPE(codigo=cod, gap_rs=round(v, 2), pct_gap=round(v / max(total_attr, 1.0), 4)))
    return tuple(result)


def _build_relatorio_summary(
    projeto_id: str,
    itens_diag: list[DiagnosticoPEItem],
    cross_term_presente: bool,
    norm_tol_pct: float,
    explicacao_natureza_periodo: dict[str, Any] | None = None,
) -> DiagnosticoPERelatorio:
    gap_total_sum = sum(i.gap_rs for i in itens_diag)
    gap_evit = sum(i.gap_evitavel_rs for i in itens_diag)
    gap_estrt = sum(i.gap_estrutural_rs for i in itens_diag)

    fator_dom = _dominant_fator(itens_diag)

    l_medio = _weighted_l_medio(itens_diag)

    validacoes: list[str] = []
    if cross_term_presente:
        validacoes.append("VAL-PE-CROSS-TERM")
    sum_fatores = sum(sum(f.gap_rs for f in i.fatores) for i in itens_diag)
    consistencia = (
        abs(gap_total_sum) < 1.0 or abs(sum_fatores - abs(gap_total_sum)) / max(abs(gap_total_sum), 1.0) < norm_tol_pct
    )
    if not consistencia:
        validacoes.append("VAL-PE-NORM-FAIL")

    return DiagnosticoPERelatorio(
        projeto_id=projeto_id,
        gerado_em=datetime.now(UTC).isoformat(),
        n_itens_deficit=len(itens_diag),
        gap_total_rs=round(gap_total_sum, 2),
        gap_evitavel_rs=round(gap_evit, 2),
        gap_estrutural_rs=round(gap_estrt, 2),
        fator_dominante_label=fator_dom,
        aviso_cross_term=cross_term_presente,
        l_medio_requerido=round(l_medio, 4),
        itens_deficit=tuple(sorted(itens_diag, key=lambda i: i.gap_rs)),
        consistencia_validada=consistencia,
        validacoes_emitidas=tuple(validacoes),
        explicacao_natureza_periodo=explicacao_natureza_periodo or {},
    )


def _dpb_prepare_contexto(
    canonical_in: Any,
    bdi_rates: dict[str, float] | None = None,
) -> tuple[Any, dict, dict, dict, dict, dict, float, float, dict, dict]:
    """Prepara contexto e lookups: extrai proyecto_id, carrega estruturas de lookup,
    calcula L_aplicado e T_efetivo, resolve cubo e constrói activity_week_map.
    Retorna (resultado, sched_lookup, equipe_lookup, plan_lookup, ca_lookup,
    eap_lookup, L_aplicado, T_efetivo, cubo_resolvido, activity_week_map)."""
    resultado = canonical_in.resultado
    L_aplicado = float(getattr(getattr(resultado, "venda", None), "bdi_lucro_impostos", 0.09) or 0.09)
    T_efetivo = float((bdi_rates or {}).get("tributos_efetivo", 0.1338))

    sched_lookup, equipe_lookup, plan_lookup, ca_lookup, eap_lookup = _dpb_build_lookups(
        canonical_in
    )
    cubo = _resolve_cubo_analitico(canonical_in)
    activity_week_map = _build_activity_week_map(cubo)

    return (
        resultado,
        sched_lookup,
        equipe_lookup,
        plan_lookup,
        ca_lookup,
        eap_lookup,
        L_aplicado,
        T_efetivo,
        cubo,
        activity_week_map,
    )


def _dpb_processar_itens_deficit(
    deficit_items: list,
    resultado: Any,
    sched_lookup: dict,
    equipe_lookup: dict,
    plan_lookup: dict,
    ca_lookup: dict,
    eap_lookup: dict,
    L_aplicado: float,
    T_efetivo: float,
    canonical_in: Any,
    activity_week_map: dict,
) -> tuple[list, bool]:
    """Processa cada item deficit: constrói hints do cubo, chama _process_pe_item,
    coleta resultados e flag de cross-term. Retorna (itens_diag, cross_term_presente)."""
    itens_diag: list[DiagnosticoPEItem] = []
    cross_term_presente = False

    for pe in deficit_items:
        item_cubo_hint = _build_item_cubo_hint(activity_week_map, pe.item_id)
        item, cross = _process_pe_item(
            pe,
            equipe_lookup,
            sched_lookup,
            plan_lookup,
            ca_lookup,
            eap_lookup,
            L_aplicado,
            T_efetivo,
            canonical_in,
            resultado,
            item_cubo_hint,
        )
        if item is not None:
            itens_diag.append(item)
        if cross:
            cross_term_presente = True

    return itens_diag, cross_term_presente


class DiagnosticoPEBuilder:
    """Constrói DiagnosticoPERelatorio a partir do canonical pós-Skill 08."""

    # Tolerância de normalização: soma dos fatores ≈ gap_total
    NORM_TOL_PCT = 0.02  # 2%
    # Threshold para detectar cross-term significativo
    CROSS_TERM_THRESHOLD = 0.05

    def build(
        self,
        canonical_in: Any,
        bdi_rates: dict[str, float] | None = None,
    ) -> DiagnosticoPERelatorio:
        projeto_id = str(getattr(getattr(canonical_in, "projeto", None), "nome", "?"))
        deficit_items = [p for p in (canonical_in.ponto_equilibrio or []) if p.delta < 0]

        if not deficit_items:
            return _dpb_empty_relatorio(projeto_id)

        (
            resultado,
            sched_lookup,
            equipe_lookup,
            plan_lookup,
            ca_lookup,
            eap_lookup,
            L_aplicado,
            T_efetivo,
            cubo,
            activity_week_map,
        ) = _dpb_prepare_contexto(canonical_in, bdi_rates)

        itens_diag, cross_term_presente = _dpb_processar_itens_deficit(
            deficit_items,
            resultado,
            sched_lookup,
            equipe_lookup,
            plan_lookup,
            ca_lookup,
            eap_lookup,
            L_aplicado,
            T_efetivo,
            canonical_in,
            activity_week_map,
        )

        explicacao_natureza_periodo = _build_explicacao_natureza_periodo(cubo, activity_week_map, itens_diag)

        return _build_relatorio_summary(
            projeto_id,
            itens_diag,
            cross_term_presente,
            self.NORM_TOL_PCT,
            explicacao_natureza_periodo,
        )
