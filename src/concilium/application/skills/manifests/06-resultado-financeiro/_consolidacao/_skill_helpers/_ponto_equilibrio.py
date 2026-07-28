"""Skill 06 (_consolidacao) — Consolidação Financeira (parte extraída de _skill_helpers_a.py)."""

from __future__ import annotations

from typing import Any, Literal

from concilium.domain.models.canonical import (
    LeverEquilibrio,
    PontoEquilibrio,
    ValidacaoItem,
)

from ._resultado import _build_diagnostico_lesao, _lesao_from_sched  # ty: ignore[unresolved-import]
from ._venda_custo import _cpu_familia  # ty: ignore[unresolved-import]


def _pe_custo_autonomo_e_gap_pool(
    equipe: Any,
    custo_operacional_real: float,
    n_frentes: int,
    idle_por_item: dict | None,
) -> tuple[float, float]:
    """ADR-076: custo_total_autonomo (ADR-091: 1 frente × n_frentes) e gap_pool_overhead.

    gap_pool_overhead usa idle real quando idle_por_item está disponível (pool ativo);
    caso contrário, fallback para diferença entre custo operacional e custo autônomo.
    """
    _custo_1fr_autonomo = float(getattr(equipe, "custo_total_autonomo", 0.0) or 0.0)
    if _custo_1fr_autonomo <= 0 and custo_operacional_real > 0:
        _custo_1fr_autonomo = custo_operacional_real
    custo_total_autonomo = _custo_1fr_autonomo * n_frentes

    idle_item = (idle_por_item or {}).get(equipe.item_id, 0.0)
    if idle_por_item is not None:
        gap_pool_overhead = round(float(idle_item), 2)
    else:
        gap_pool_overhead = round(float(max(0.0, custo_operacional_real - custo_total_autonomo)), 2)
    return custo_total_autonomo, gap_pool_overhead


def _pe_frentes_nec(
    venda_sem_bdi: float, custo_total_autonomo: float, custo_operacional_real: float, custo_venda_total: float
) -> float:
    frentes_nec = 1.0
    if venda_sem_bdi > 0 and custo_total_autonomo > 0:
        frentes_nec = round(custo_total_autonomo / venda_sem_bdi, 4)
    elif custo_total_autonomo <= 0 and custo_venda_total > 0:
        frentes_nec = round(custo_operacional_real / custo_venda_total, 4)
    # ADR-076 Fallback: se frentes_nec >> 10 (absurdo), usar 1 como conservador
    if frentes_nec > 10.0:
        frentes_nec = 1.0
    return frentes_nec


def _pe_pu_calibrado(pu_catalogo_unitario: float, custo_total_autonomo: float, q: float) -> tuple[float, float]:
    pu_aut_unit = custo_total_autonomo / q if custo_total_autonomo > 0 else 0.0
    pu_calibrado_unitario = round(max(pu_catalogo_unitario, pu_aut_unit), 4)
    ajuste_minimo_pct = 0.0
    if pu_catalogo_unitario > 0:
        ajuste_minimo_pct = round((pu_calibrado_unitario - pu_catalogo_unitario) / pu_catalogo_unitario * 100, 2)
    return pu_calibrado_unitario, ajuste_minimo_pct


def _pe_plan_calibracao(
    plan: Any,
    custo_total_autonomo: float,
    custo_operacional_real: float,
    custo_venda_total: float,
) -> tuple[float, float, float, float]:
    """ADR-076 Opção C/D: PU catálogo/calibrado, ajuste mínimo e frentes necessárias.

    fe_nec = custo_total_autonomo / (PU_sbdi × Q) = 1/η_p. NOTA: PU_sbdi JÁ inclui
    encargos no numerador (nota NEP-029: B_base×(1+enc)) — não remover encargos aqui.
    """
    if not (plan is not None and plan.subtotal and plan.quantitativo and plan.quantitativo > 0):
        return 0.0, 0.0, 0.0, 1.0

    Q = float(plan.quantitativo)
    venda_sem_bdi = float(plan.subtotal.sem_bdi.total if (plan.subtotal and plan.subtotal.sem_bdi) else 0.0)
    pu_catalogo_unitario = round(venda_sem_bdi / Q, 4) if Q > 0 else 0.0

    frentes_nec = _pe_frentes_nec(venda_sem_bdi, custo_total_autonomo, custo_operacional_real, custo_venda_total)
    pu_calibrado_unitario, ajuste_minimo_pct = _pe_pu_calibrado(pu_catalogo_unitario, custo_total_autonomo, Q)

    return pu_catalogo_unitario, pu_calibrado_unitario, ajuste_minimo_pct, frentes_nec


def _pe_lesao_e_equipes_efetivas(
    equipe: Any,
    permanencia_base: float,
    sched_por_item: dict | None,
) -> tuple[dict, float, int, float, float, int]:
    """ADR-076 Lesão de Produtividade (via distribuicao_semanal)."""
    lesao: dict = {}
    sched = (sched_por_item or {}).get(equipe.item_id)
    if sched is not None:
        lesao = _lesao_from_sched(sched)

    n_equipes_ef = (
        round(lesao["team_weeks"] / lesao["active_weeks"], 2)
        if lesao and lesao.get("active_weeks", 0) > 0
        else round(permanencia_base / float(getattr(equipe, "permanencia_meses", 1.0) or 1.0), 2)
    )
    semanas_ativas_v = lesao.get("active_weeks", 0)
    fator_clima_v = lesao.get("fator_clima", 1.0)
    fator_cal_v = lesao.get("fator_cal", 1.0)
    semanas_lesadas_v = lesao.get("semanas_lesadas_clima", 0)
    return lesao, n_equipes_ef, semanas_ativas_v, fator_clima_v, fator_cal_v, semanas_lesadas_v


def _pe_machine_weeks(lesao: dict) -> tuple[float, float, float]:
    """TD-3: machine-weeks brutas/efetivas e η_real a partir do dict de lesão."""
    machine_weeks_brutas = float(lesao.get("team_weeks", 0)) if lesao else 0.0
    # TD-3: usar eMW exacto (Σ m_{ij}·η_j) de fator_total quando disponível
    machine_weeks_efetivas = float(lesao.get("effective_machine_weeks", 0)) if lesao else 0.0
    if machine_weeks_efetivas == 0 and machine_weeks_brutas > 0:
        # fallback para produto das médias se effective_machine_weeks não computado
        _feta = float(lesao.get("fator_clima", 1.0)) * float(lesao.get("fator_cal", 1.0)) if lesao else 1.0
        machine_weeks_efetivas = round(machine_weeks_brutas * _feta, 4)
    eta_real = round(machine_weeks_efetivas / machine_weeks_brutas, 4) if machine_weeks_brutas > 0 else 1.0
    return machine_weeks_brutas, machine_weeks_efetivas, eta_real


def _pe_camada2_producao(
    plan: Any, custo_total_autonomo: float, lesao: dict
) -> tuple[float, float, float, float, float]:
    """NEP-042 Camada 2 — PU operacional autônomo, machine-weeks, η_real."""
    _Q = float((plan.quantitativo if plan else 0) or 0)
    pu_operacional_autonomo = round(custo_total_autonomo / _Q, 4) if _Q > 0 and custo_total_autonomo > 0 else 0.0
    machine_weeks_brutas, machine_weeks_efetivas, eta_real = _pe_machine_weeks(lesao)
    return _Q, pu_operacional_autonomo, machine_weeks_brutas, machine_weeks_efetivas, eta_real


def _pe_camada3_pool(
    equipe: Any, pool_total_por_item: dict | None, q: float, custo_total_autonomo: float
) -> tuple[float, float, float]:
    """NEP-042 / ADR-091 Camada 3 — custo pool instancial agregado e PU pool.

    pool_total_por_item já armazena o custo total de todas as frentes — não
    multiplicar por n_frentes (evitar dupla contagem).
    """
    _raw_pool = float((pool_total_por_item or {}).get(equipe.item_id, 0.0))
    custo_pool_total = round(_raw_pool, 2) if _raw_pool > 0 else 0.0
    custo_pool_por_unidade = round(custo_pool_total / q, 4) if q > 0 and custo_pool_total > 0 else 0.0
    economia_pool_abs = round(custo_total_autonomo - custo_pool_total, 2)
    return custo_pool_total, custo_pool_por_unidade, economia_pool_abs


def _pe_gap_praticabilidade_abs(fator_clima_v: float, plan: Any, q: float) -> float:
    """ADR-083 §4: gap excedente C_eps por η̄ < 1 (clima/terreno).

    NEP-043: C_eps = (PU_mo + PU_eq) × Q × (1/η - 1). Diesel NÃO integra C_eps: ocorre
    por produção (não por calendário), é constante em Q. Apenas MO e EQ acumulam custo
    em intervalos não produtivos (extensão do prazo). fator_clima_v é a média ponderada
    de η por team-weeks; gap = 0 quando η = 1.
    """
    gap_praticabilidade_abs = 0.0
    if 0.0 < fator_clima_v < 0.9999 and plan is not None and q > 0:
        # fator_clima_v == 0.0 (perda climática total em todas as semanas) é
        # excluído acima: 1/η divergiria (ZeroDivisionError). Nesse cenário extremo
        # o gap de praticabilidade não é quantificável por este modelo linear.
        _pu = plan.preco_unitario if plan and plan.preco_unitario else None
        _pu_mo_eq = (
            float((getattr(_pu, "mao_obra", 0.0) or 0.0) + (getattr(_pu, "equipamentos", 0.0) or 0.0)) if _pu else 0.0
        )
        if _pu_mo_eq > 0:
            # PU_mo_eq × Q já representa o custo total de MO+EQ para a atividade completa;
            # não multiplicar por n_frentes (PU×Q é total, não por frente).
            gap_praticabilidade_abs = round(_pu_mo_eq * q * (1.0 / fator_clima_v - 1.0), 2)
    return gap_praticabilidade_abs


def _pe_gap_escala_abs(equipe: Any, n_equipes_ef: float, custo_fixo_total: float) -> float:
    """Custo adicional por usar N>1 equipes vs 1 equipe × permanência nominal."""
    perm_nom = float(getattr(equipe, "permanencia_meses", 0.0) or 0.0)
    custo_base_cat = equipe.custo_fixo_mensal * perm_nom if perm_nom > 0 else custo_fixo_total / max(n_equipes_ef, 1.0)
    return round(custo_base_cat * max(0.0, n_equipes_ef - 1.0), 2)


# ADR-162: share (0.5=empate) fora de [1-LIMIAR, LIMIAR] declara causa única; dentro
# da faixa (interação material entre as duas causas) declara "MISTO". Mesmo espírito
# da banda de tolerância de VAL-PROD-VS-PU (10%), só que centrada em 50% em vez de 100%.
_CAUSA_DOMINANTE_LIMIAR_SHARE = 0.65


def _pe_causa_dominante(
    plan: Any,
    custo_venda_total: float,
    custo_fixo_total: float,
    custo_operacional_real: float,
    machine_weeks_brutas: float,
    horas_dia: float,
    dias_semana: float,
) -> tuple[Literal["CRONOGRAMA", "PRECIFICACAO", "MISTO", "INDETERMINADO"], float, float]:
    """ADR-162 D1: decompõe delta (= custo_venda_total − custo_fixo_total) em duas causas.

        H_i           = horas_dia · dias_semana · machine_weeks_brutas      (real, pós-cronograma)
        H_cat         = Q_i / ρ_i                                          (nominal, catálogo)
        γ_i^v         = custo_venda_total / H_cat                          (taxa de venda)
        γ_i^o         = custo_fixo_total / H_i                             (taxa operacional real)

    Partição SIMÉTRICA (Shapley/Bennet — resolve a ambiguidade clássica de decomposição
    preço×quantidade em dois fatores: a convenção "ingênua" atribuiria o termo de
    interação (γ_i^v−γ_i^o)·(H_cat−H_i) inteiro a uma das duas causas, dependendo de qual
    convenção se escolhe — arbitrário e sujeito a inverter o rótulo "dominante" trocando
    de convenção. A partição simétrica divide essa interação meio a meio):

        T_cronograma   = (H_cat − H_i) · (γ_i^v + γ_i^o) / 2
        T_precificacao = (γ_i^v − γ_i^o) · (H_cat + H_i) / 2

    T_cronograma + T_precificacao == delta por construção (verificado algebricamente:
    os termos cruzados γ_i^v·H_i e γ_i^o·H_cat se cancelam na soma).

    causa_dominante por participação relativa (share = |T_cronograma| / (|T_cronograma| +
    |T_precificacao|)), não por "quem é maior" simples — uma divisão 51/49 não sustenta
    afirmar uma causa única:
      - share >= LIMIAR (0.65)      -> "CRONOGRAMA"
      - share <= 1 - LIMIAR (0.35)  -> "PRECIFICACAO"
      - caso contrário               -> "MISTO" (nenhuma causa isolada explica a maior parte)

    "INDETERMINADO" (nunca um valor inventado) quando:
      - ρ_i (plan.produtividade_catalogo) não resolvido — Fonte 1 bottom-up (NEP-032) não
        aplicou para este item (override manual, ou fallback de composição — issue #132);
      - H_i real não resolvível — custo_operacional_real <= 0 ou schedule ainda ausente
        (machine_weeks_brutas <= 0) — P5: causa_dominante é sempre diagnóstico pós-cronograma,
        nunca validação prospectiva de mobilização.
    """
    q = float(getattr(plan, "quantitativo", 0.0) or 0.0) if plan else 0.0
    rho = float(getattr(plan, "produtividade_catalogo", 0.0) or 0.0) if plan else 0.0
    h_i = horas_dia * dias_semana * machine_weeks_brutas

    if q <= 0 or rho <= 0 or h_i <= 0 or custo_operacional_real <= 0:
        return "INDETERMINADO", 0.0, 0.0

    h_cat = q / rho
    gamma_v = custo_venda_total / h_cat
    gamma_o = custo_fixo_total / h_i

    t_cronograma = (h_cat - h_i) * (gamma_v + gamma_o) / 2.0
    t_precificacao = (gamma_v - gamma_o) * (h_cat + h_i) / 2.0

    denom = abs(t_cronograma) + abs(t_precificacao)
    if denom <= 0:
        # Ambos os termos nulos (delta ~0 e sem gap de taxa nem de horas) — não há causa
        # a atribuir, mas os dados existem (diferente de INDETERMINADO): "MISTO" é o rótulo
        # honesto para "nenhuma causa presente", não "não foi possível calcular".
        causa: Literal["CRONOGRAMA", "PRECIFICACAO", "MISTO"] = "MISTO"
    else:
        share_cronograma = abs(t_cronograma) / denom
        if share_cronograma >= _CAUSA_DOMINANTE_LIMIAR_SHARE:
            causa = "CRONOGRAMA"
        elif share_cronograma <= 1.0 - _CAUSA_DOMINANTE_LIMIAR_SHARE:
            causa = "PRECIFICACAO"
        else:
            causa = "MISTO"

    return causa, round(t_cronograma, 2), round(t_precificacao, 2)


def _pe_status_frentes(frentes_nec: float) -> Literal["OK", "AVISO", "CRITICO"]:
    """Threshold status_frentes: OK ≤ 1.25, AVISO ≤ 1.5, CRITICO > 1.5."""
    if frentes_nec <= 1.25:
        return "OK"
    if frentes_nec <= 1.5:
        return "AVISO"
    return "CRITICO"


def _pe_lever_gap_escala(
    gap_escala_abs: float, n_equipes_ef: float, custo_venda_total: float
) -> LeverEquilibrio | None:
    if gap_escala_abs <= 0:
        return None
    _cv = custo_venda_total
    return LeverEquilibrio(
        id="fechar_gap_escala",
        tipo="custo",
        descricao=f"Paralelismo: {n_equipes_ef:.1f}x frentes (quantizacao de equipes)",
        delta_margin=round(gap_escala_abs, 2),
        delta_margin_pct=round(gap_escala_abs / _cv, 6) if _cv > 0 else 0.0,
        viavel=n_equipes_ef > 1.05,
        restricoes=[f"Sequencializar estende prazo +{(n_equipes_ef - 1.0) * 100:.0f}%"] if n_equipes_ef > 1.5 else [],
    )


def _pe_lever_gap_praticabilidade(
    gap_praticabilidade_abs: float, fator_clima_v: float, custo_venda_total: float
) -> LeverEquilibrio | None:
    if gap_praticabilidade_abs <= 0:
        return None
    _cv = custo_venda_total
    return LeverEquilibrio(
        id="fechar_gap_praticabilidade",
        tipo="custo",
        descricao=f"Praticabilidade: eta={fator_clima_v:.1%} aproveitamento efetivo",
        delta_margin=round(gap_praticabilidade_abs, 2),
        delta_margin_pct=round(gap_praticabilidade_abs / _cv, 6) if _cv > 0 else 0.0,
        viavel=True,
        restricoes=[],
    )


def _pe_lever_gap_pool(
    gap_pool_overhead: float, particao_por_item: dict | None, equipe: Any, custo_venda_total: float
) -> LeverEquilibrio | None:
    """ADR-083: decompor gap_pool em overhead de ociosidade e economia de mob/demob."""
    if gap_pool_overhead <= 0:
        return None
    _cv = custo_venda_total
    _particao = (particao_por_item or {}).get(equipe.item_id)
    _pool_restricoes: list[str] = []
    if _particao is not None:
        if _particao.overhead_ocioso > 0:
            _pool_restricoes.append(f"Ociosidade de gap: R$ {_particao.overhead_ocioso:,.0f}")
        if _particao.economia_mob > 0:
            _pool_restricoes.append(f"Economia mob/demob: −R$ {_particao.economia_mob:,.0f}")
        _saldo = _particao.overhead_ocioso - _particao.economia_mob
        _pool_restricoes.append(
            f"Saldo pool ({'+overhead' if _saldo > 0 else 'economia líquida'}): R$ {abs(_saldo):,.0f}"
        )
        # ADR-084 Fase 4: exibir predecessor_critico_id e overlap_semanas quando disponíveis
        if getattr(_particao, "predecessor_critico_id", None):
            _pool_restricoes.append(f"Predecessor critico: {_particao.predecessor_critico_id}")
        if getattr(_particao, "overlap_semanas", 0.0) > 0:
            _pool_restricoes.append(f"Sobreposicao: {_particao.overlap_semanas:.1f} semanas")
    return LeverEquilibrio(
        id="fechar_gap_pool",
        tipo="custo",
        descricao="ResourcePool: overhead mob/demob e ociosidade de contrato",
        delta_margin=round(gap_pool_overhead, 2),
        delta_margin_pct=round(gap_pool_overhead / _cv, 6) if _cv > 0 else 0.0,
        viavel=True,
        restricoes=_pool_restricoes,
    )


def _pe_lever_revisao_bdi(delta: float, ajuste_minimo_pct: float, custo_venda_total: float) -> LeverEquilibrio | None:
    if delta >= 0:
        return None
    _cv = custo_venda_total
    return LeverEquilibrio(
        id="revisao_bdi_minima",
        tipo="preco",
        descricao=(
            f"BDI: +{ajuste_minimo_pct:.1f}% no PU catalogo para PE nulo"
            if ajuste_minimo_pct > 0
            else "BDI: revisao minima de preco para cobrir ineficiencia"
        ),
        delta_margin=round(-delta, 2),
        delta_margin_pct=round(-delta / _cv, 6) if _cv > 0 else 0.0,
        viavel=True,
        restricoes=["Lever de precificacao — fora do alcance do planejador"],
    )


def _pe_build_levers(
    n_equipes_ef: float,
    gap_escala_abs: float,
    gap_praticabilidade_abs: float,
    fator_clima_v: float,
    gap_pool_overhead: float,
    particao_por_item: dict | None,
    equipe: Any,
    delta: float,
    ajuste_minimo_pct: float,
    custo_venda_total: float,
) -> list:
    """ADR-082: Levers de ajuste do ponto de equilíbrio."""
    levers: list = []
    for lever in (
        _pe_lever_gap_escala(gap_escala_abs, n_equipes_ef, custo_venda_total),
        _pe_lever_gap_praticabilidade(gap_praticabilidade_abs, fator_clima_v, custo_venda_total),
        _pe_lever_gap_pool(gap_pool_overhead, particao_por_item, equipe, custo_venda_total),
        _pe_lever_revisao_bdi(delta, ajuste_minimo_pct, custo_venda_total),
    ):
        if lever is not None:
            levers.append(lever)
    return levers


def _build_pe_for_equipe(
    equipe: Any,
    venda_por_item: dict,
    planejamento_por_item: dict | None = None,
    sched_por_item: dict | None = None,
    particao_por_item: dict | None = None,
    idle_por_item: dict | None = None,
    pool_total_por_item: dict | None = None,
    regime: Any = None,
) -> PontoEquilibrio | None:
    """Constrói PontoEquilibrio para uma equipe. Retorna None se custo_fixo ≤ 0.

    ADR-076:
    - planejamento_por_item: frentes_equivalentes_necessarias (Opção C) e calibração PU (Opção D).
    - sched_por_item: fatores de lesão de produtividade (fator_clima, n_equipes, semanas_lesadas).
    ADR-083:
    - particao_por_item: {item_id: CustoParticionadoItem} — decomposição causal do gap_pool.
    ADR-162:
    - regime: RegimeTrabalho do projeto (horas_dia/dias_semana) — usado só por causa_dominante
      para converter machine_weeks_brutas em horas reais (H_i). None -> causa_dominante="INDETERMINADO".
    """
    permanencia_base = float(
        getattr(equipe, "permanencia_efetiva_meses", 0.0) or getattr(equipe, "permanencia_meses", 0.0) or 1.0
    )
    custo_fixo_total = equipe.custo_fixo_mensal * permanencia_base
    if custo_fixo_total <= 0:
        return None
    custo_venda_total = venda_por_item.get(equipe.item_id, 0.0)
    delta = custo_venda_total - custo_fixo_total
    custo_operacional_real = float(equipe.custo_total or 0.0)
    frentes = custo_operacional_real / custo_fixo_total if custo_fixo_total > 0 else 1.0

    # ADR-091: custo_total já armazena o custo total de todas as frentes (normalizado em
    # skill-05). _n_frentes mantido apenas para gap_escala e diagnóstico.
    _n_frentes = max(1, int(getattr(equipe, "num_equipes_base", 1) or 1))

    custo_total_autonomo, gap_pool_overhead = _pe_custo_autonomo_e_gap_pool(
        equipe, custo_operacional_real, _n_frentes, idle_por_item
    )

    plan = (planejamento_por_item or {}).get(equipe.item_id)
    pu_catalogo_unitario, pu_calibrado_unitario, ajuste_minimo_pct, frentes_nec = _pe_plan_calibracao(
        plan, custo_total_autonomo, custo_operacional_real, custo_venda_total
    )

    lesao, n_equipes_ef, semanas_ativas_v, fator_clima_v, fator_cal_v, semanas_lesadas_v = _pe_lesao_e_equipes_efetivas(
        equipe, permanencia_base, sched_por_item
    )

    _Q, pu_operacional_autonomo, machine_weeks_brutas, machine_weeks_efetivas, eta_real = _pe_camada2_producao(
        plan, custo_total_autonomo, lesao
    )

    horas_dia = float(getattr(regime, "horas_dia", 0.0) or 0.0)
    dias_semana = float(getattr(regime, "dias_semana", 0.0) or 0.0)
    causa_dominante, t_cronograma, t_precificacao = _pe_causa_dominante(
        plan, custo_venda_total, custo_fixo_total, custo_operacional_real, machine_weeks_brutas, horas_dia, dias_semana
    )

    custo_pool_total, custo_pool_por_unidade, economia_pool_abs = _pe_camada3_pool(
        equipe, pool_total_por_item, _Q, custo_total_autonomo
    )

    gap_praticabilidade_abs = _pe_gap_praticabilidade_abs(fator_clima_v, plan, _Q)
    gap_escala_abs = _pe_gap_escala_abs(equipe, n_equipes_ef, custo_fixo_total)

    diag = _build_diagnostico_lesao(
        n_equipes=n_equipes_ef,
        fator_clima=fator_clima_v,
        semanas_lesadas=semanas_lesadas_v,
        semanas_ativas=semanas_ativas_v,
        gap_escala=gap_escala_abs,
        gap_pool=gap_pool_overhead,
    )

    status_frentes = _pe_status_frentes(frentes_nec)

    levers = _pe_build_levers(
        n_equipes_ef,
        gap_escala_abs,
        gap_praticabilidade_abs,
        fator_clima_v,
        gap_pool_overhead,
        particao_por_item,
        equipe,
        delta,
        ajuste_minimo_pct,
        custo_venda_total,
    )

    return PontoEquilibrio(
        item_id=equipe.item_id,
        custo_fixo_equipe=round(custo_fixo_total, 2),
        custo_venda_cpu=round(custo_venda_total, 2),
        delta=round(delta, 2),
        delta_pct=round(delta / custo_fixo_total, 5),
        status_validacao="OK" if delta >= 0 else "ERRO",
        custo_operacional_real=round(custo_operacional_real, 2),
        frentes_equivalentes=round(frentes, 2),
        # ADR-076 Opção C
        frentes_equivalentes_necessarias=frentes_nec,
        gap_pool_overhead=gap_pool_overhead,
        status_frentes=status_frentes,
        # ADR-076 Opção D
        pu_catalogo_unitario=pu_catalogo_unitario,
        pu_calibrado_unitario=pu_calibrado_unitario,
        ajuste_minimo_pct=ajuste_minimo_pct,
        gap_praticabilidade_abs=gap_praticabilidade_abs,
        gap_pool_abs=round(-economia_pool_abs, 2) if economia_pool_abs != 0 else gap_pool_overhead,
        # ADR-076 Justificativa de Lesão
        n_equipes_efetivo=n_equipes_ef,
        semanas_ativas=semanas_ativas_v,
        fator_clima_medio=fator_clima_v,
        fator_calendario_medio=fator_cal_v,
        semanas_lesadas_clima=semanas_lesadas_v,
        gap_escala_abs=gap_escala_abs,
        diagnostico_lesao=diag,
        # ADR-082
        levers_equilibrio=levers,
        # NEP-042: três camadas de precificação
        pu_operacional_autonomo=pu_operacional_autonomo,
        machine_weeks_brutas=machine_weeks_brutas,
        machine_weeks_efetivas=machine_weeks_efetivas,
        eta_real=eta_real,
        custo_pool_total=custo_pool_total,
        custo_pool_por_unidade=custo_pool_por_unidade,
        economia_pool_abs=economia_pool_abs,
        # ADR-162 D1
        causa_dominante=causa_dominante,
        t_cronograma=t_cronograma,
        t_precificacao=t_precificacao,
    )


def _validate_pe_duplo_risco(pe: PontoEquilibrio, validacoes: list) -> None:
    if pe.confianca_pe and pe.confianca_pe in ("MEDIA", "BAIXA") and pe.status_validacao == "ERRO":
        severidade = "AVISO" if pe.confianca_pe == "MEDIA" else "ERRO"
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PE-PU-DUPLO-RISCO",
                status=severidade,
                mensagem=(
                    f"Item '{pe.item_id}': PE DEFICITÁRIO com confiança"
                    f" {pe.confianca_pe.upper()} na PU ({pe.validacao_pu_status})."
                    f" {pe.diagnostico_pu or ''}"
                ),
            )
        )


def _validate_prod_vs_pu(pe: PontoEquilibrio, validacoes: list) -> None:
    """VAL-PROD-VS-PU (ADR-082-cons): divergência de produtividade engine ↔ catálogo.

    O custo operacional excede o de catálogo por um fator ``fe_nec``. Parte é
    explicável por clima (fator_clima_medio). O **resíduo** não-climático isola o
    desencontro entre a produtividade do engine (valor_horario, skill-04) e a
    embutida no PU planilha-first (skill-06):

        residuo = fe_nec × fator_clima_medio
        residuo ≈ 1 → gap puramente climático (P consistente)
        residuo ≠ 1 → P_engine diverge de P_catálogo (calibração a reconciliar)

    Emite AVISO quando |residuo − 1| > 10% — o número que fecha a base de cálculo.
    """
    fe_nec = pe.frentes_equivalentes_necessarias
    clima = pe.fator_clima_medio or 1.0
    if fe_nec <= 0 or clima <= 0:
        return
    residuo = fe_nec * clima
    if abs(residuo - 1.0) <= 0.10:
        return
    sentido = (
        "P_engine < P_catálogo (operacional mais barato)"
        if residuo < 1.0
        else ("P_engine > P_catálogo (operacional mais caro)")
    )
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-PROD-VS-PU",
            status="AVISO",
            mensagem=(
                f"Item '{pe.item_id}': divergência de produtividade {(residuo - 1.0) * 100:+.1f}% "
                f"não explicada por clima (fe_nec={fe_nec:.2f} × clima={clima:.2f} = {residuo:.2f}). "
                f"{sentido}. Reconciliar valor_horario (producao) com o PU de catálogo "
                f"(cat={pe.pu_catalogo_unitario:.3f} vs calibrado={pe.pu_calibrado_unitario:.3f})."
            ),
        )
    )


def _validate_prod_pu_fallback_desync(
    item_id: str,
    sched_por_item: dict | None,
    planejamento_por_item: dict | None,
    validacoes: list,
) -> None:
    """VAL-PROD-PU-FALLBACK-DESYNC (issue #132): correlaciona os DOIS fallbacks independentes.

    skill-04 (`_resolve_productivity`) e skill-06 (`_resolve_preco_cat_item`) resolvem
    produtividade/preço de forma independente para a mesma CPU. Quando ambos caem em
    fallback para o MESMO item — schedule usa P=1000 un/h arbitrário (sem
    `producao_id_ref` resolvível) e a precificação cai na Fonte 2 (composicao_itens ×
    preco_insumo, sem nenhum conceito de produtividade horária) — a tese central do
    sistema (ADR-060: venda e custo derivam da mesma `Producao.valor_horario`) quebra
    silenciosamente: nem o custo operacional nem o preço de venda têm base real de
    produtividade, e o ponto de equilíbrio resultante é inconclusivo.

    NOTA: fallback isolado em um único lado já é sinalizado individualmente por
    VAL-PROD-04 (skill-04) e implicitamente pela ausência de VAL-PLAN-BOTTOM-UP
    (skill-06) — esta validação é especificamente sobre a CORRELAÇÃO dos dois.
    """
    sched = (sched_por_item or {}).get(item_id)
    plan = (planejamento_por_item or {}).get(item_id)
    if sched is None or plan is None:
        return
    if not (
        getattr(sched, "produtividade_fallback_aplicada", False)
        and getattr(plan, "precificacao_via_fallback_composicao", False)
    ):
        return
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-PROD-PU-FALLBACK-DESYNC",
            status="AVISO",
            mensagem=(
                f"Item '{item_id}': produtividade do schedule (P=1000 un/h, fallback) e preço "
                "unitário (composicao_itens, sem base de produtividade) vieram de fontes "
                "desconectadas — nem venda nem custo operacional têm base real de produtividade "
                "para este item. Ponto de equilíbrio inconclusivo; resolva producao_id_ref na CPU."
            ),
        )
    )


def _validate_frentes_necessarias(pe: PontoEquilibrio, validacoes: list) -> None:
    """VAL-FRENTES-NECESSARIAS-ALTA (ADR-076): execução autônoma supera o PU de catálogo.

    Threshold: OK ≤ 1.25, AVISO ≤ 1.5, CRITICO > 1.5.
    Emite AVISO ou ERRO dependendo do grau de desvio.
    """
    if pe.frentes_equivalentes_necessarias <= 1.25:
        return
    status_val = "ERRO" if pe.frentes_equivalentes_necessarias > 1.5 else "AVISO"
    desvio_pct = (pe.frentes_equivalentes_necessarias - 1.0) * 100
    ajuste_info = f" PU calibrado: +{pe.ajuste_minimo_pct:.1f}%." if pe.ajuste_minimo_pct > 0 else ""
    pool_info = f" Pool overhead: R$ {pe.gap_pool_abs:,.2f}." if pe.gap_pool_abs > 0 else ""
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-FRENTES-NECESSARIAS-ALTA",
            status=status_val,
            mensagem=(
                f"Item '{pe.item_id}': custo autônomo {desvio_pct:.1f}% acima do PU de catálogo"
                f" ({pe.frentes_equivalentes_necessarias:.2f}× frentes necessárias)."
                f"{ajuste_info}{pool_info}"
            ),
        )
    )


def _validate_pe_particao(pe: PontoEquilibrio, validacoes: list) -> None:
    # Compat: custo_realizado foi substituído por custo_operacional_real no modelo canônico.
    custo_realizado = float(getattr(pe, "custo_realizado", 0.0) or getattr(pe, "custo_operacional_real", 0.0) or 0.0)
    if pe.frentes_equivalentes > 1.05 and custo_realizado > 0:
        delta_op = pe.custo_venda_cpu - pe.custo_operacional_real
        if delta_op >= 0:
            return
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PONTO-EQUILIBRIO-PARTICAO",
                status="AVISO",
                mensagem=(
                    f"Item '{pe.item_id}': ~{pe.frentes_equivalentes:.2f} frentes equivalentes."
                    f" Delta operacional: R$ {delta_op:,.2f}."
                ),
            )
        )


def _apm_build_familia_rows(pe_por_item: dict, equipe_by_item: dict) -> dict:
    """Groups PE items by CPU family."""
    familia_rows: dict = {}
    for item_id, pe_item in pe_por_item.items():
        eq = equipe_by_item.get(item_id)
        fam = _cpu_familia(eq.cpu_id if eq else "")
        if fam:
            familia_rows.setdefault(fam, []).append((item_id, pe_item))
    return familia_rows


def _apm_process_familia(fam: str, rows: list, validacoes: list) -> None:
    """Downgrades ERRO to AVISO for PE items in a family with positive aggregate delta."""
    if len(rows) < 2:
        return
    delta_fam = sum(r[1].delta for r in rows)
    erros_fam = [r for r in rows if r[1].status_validacao == "ERRO"]
    if not (erros_fam and delta_fam >= 0):
        return
    for _, pe_item in erros_fam:
        pe_item.status_validacao = "AVISO"
    ids = ", ".join(i for i, _ in erros_fam)
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-PONTO-EQUILIBRIO-MITIGACAO",
            status="AVISO",
            mensagem=(
                f"Família '{fam}' com itens originalmente em ERRO ({ids})"
                f" mas saldo agregado positivo (Δfam = R$ {delta_fam:,.2f})."
                " Criticidade rebaixada para AVISO."
            ),
        )
    )


def _apply_pe_mitigacao(pe_items: list[PontoEquilibrio], equipe_by_item: dict, validacoes: list) -> None:
    pe_por_item = {p.item_id: p for p in pe_items}
    familia_rows = _apm_build_familia_rows(pe_por_item, equipe_by_item)
    for fam, rows in familia_rows.items():
        _apm_process_familia(fam, rows, validacoes)


