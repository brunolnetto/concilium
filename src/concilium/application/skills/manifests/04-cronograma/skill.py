"""Skill 02 — Cronograma Unificado (Semanal com Agregação Mensal).

Dual-mode scheduling:
  Mode 1: MANUAL_ALLOCATION — Planejador fornece num_equipes_por_item
          Usa lógica Skill 02 (cálculo de produção)

  Mode 2: AUTO_SCHEDULE — Otimização automática (DAG + recursos + prazo)
          Fallback chain: heurísticas -> relax -> MILP

Saída unificada: Cronograma com scheduled_activities (semanal) + distribuicao_mensal (mensal)

DEPRECATION NOTICE (ADR-105):
  spec.rcpsp_spec is deprecated in favor of automatic MOB window inference.
  Use infer_mob_windows() with meta.data_inicio/termino + spec.eap.predecessores.
  Target removal: v4.0. Migration guide: docs/engineering/ADR-105-migration.md
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

from concilium.application.scheduling import (
    Activity,
    ActivityDAG,
    ResourcePool,
    explore_schedules,
    select_scheduling_algorithm,
)
from concilium.application.scheduling.mob_scheduling import infer_mob_windows
from concilium.application.skills.base import SkillResult
from concilium.domain.models.canonical import (
    AtividadeIntervalo,
    CalendarioOperacionalSemanal,
    CanonicalModel,
    Cronograma,
    DistribuicaoSemanal,
    ScheduleCandidateCanonical,
    ScheduledActivityCanonical,
    ValidacaoItem,
)

# ════════════════════════════════════════════════════════════════════════════════
# SECTION 1: HELPERS FROM SKILL 02 (Manual Mode — Weekly Calculation)
# ════════════════════════════════════════════════════════════════════════════════


def _iso_week_key(d: date) -> str:
    """Retorna a chave de semana ISO 'AAAA-Www' para uma data."""
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _semanas_entre(inicio: date, fim: date) -> list[str]:
    """Lista de chaves 'AAAA-Www' das semanas ISO que cobrem o intervalo [inicio, fim]."""
    semanas: list[str] = []
    seen: set[str] = set()
    d = inicio
    while d <= fim:
        key = _iso_week_key(d)
        if key not in seen:
            seen.add(key)
            semanas.append(key)
        d += timedelta(days=1)
    return semanas


def _build_cpu_lookup(catalogo: dict[str, Any]) -> dict[str, dict]:
    """Indexa CPUs do catálogo por código."""
    return {c["codigo"]: c for c in catalogo.get("cpus", [])}


def _build_producao_lookup(catalogo: dict[str, Any]) -> dict[str, dict]:
    """Indexa artefatos de produtividade por id (ADR-007)."""
    # Suporta tanto 'producoes' (ADR) quanto 'produtividades' (implementação)
    lista = catalogo.get("produtividades", []) or catalogo.get("producoes", [])
    return {p["id"]: p for p in lista}


def _build_insumos_lookup(catalogo: dict[str, Any]) -> dict[str, dict]:
    """Indexa insumos do catálogo por código."""
    return {ins["codigo"]: ins for ins in catalogo.get("insumos", []) if ins.get("codigo")}


def _custo_hora_equipe(
    composicao: dict,
    insumos_lookup: dict[str, dict],
    horas_mes: float,
    taxa_encargos: float,
    custo_hora_referencia: float | None = None,
) -> float:
    """Computa custo horário total da equipe a partir da composição padrão.

    Quando ``custo_hora_referencia`` está disponível (planilha AGIS 2026-05), usa-o
    diretamente sem precisar de lookup de insumos — elimina dependência de catálogo e
    garante identidade exata P_canonico = C (produção da planilha).

    Fórmula (NEP-029 D2):
      custo_hora_mo  = Σ funcoes: n_pessoas × (preco_unit / horas_mes) × (1 + taxa_encargos)
                       onde preco_unit está em R$/mês quando unidade='mes',
                            ou em R$/h quando unidade='h'
      custo_hora_eq  = Σ equips: n_unidades × preco_hora_equip       (unidade='h')
      custo_hora_comb = Σ equips: n_unidades × consumo_L_h × preco_diesel
      total          = custo_hora_mo + custo_hora_eq + custo_hora_comb

    Diesel é buscado pelos códigos MA-DIESEL-S10, MA-DIESEL ou MA-DIESEL-ESCALA.
    Retorna 0.0 se a composição estiver incompleta (insumos não encontrados).
    """
    if custo_hora_referencia and custo_hora_referencia > 0:
        return float(custo_hora_referencia)
    custo_hora = 0.0

    # ── Mão de obra ──────────────────────────────────────────────────────────
    for func in composicao.get("funcoes", []):
        fid = func.get("funcao_id") or ""
        n = float(func.get("num_pessoas", 1) or 1)  # planilha usa frações (0.5, 0.17)
        ins = insumos_lookup.get(fid)
        if not ins:
            continue
        pu = float(ins.get("preco_unitario", 0) or 0)
        unidade = str(ins.get("unidade", "mes")).lower()
        if unidade in ("h", "hora"):
            # Taxa horária já em R$/h.
            # Se o insumo indica que encargos já estão incluídos (convenção AGIS-FN-*),
            # não aplicar taxa_encargos adicionalmente.
            nota = str((ins.get("atributos_especificos") or {}).get("nota", "")).lower()
            ja_com_encargos = "inclui encargos" in nota  # substring sem acentos
            encargos = 0.0 if ja_com_encargos else taxa_encargos
            custo_hora += n * pu * (1.0 + encargos)
        else:
            # Taxa mensal → converte para horária e aplica encargos
            taxa_hora = pu / horas_mes if horas_mes > 0 else 0.0
            custo_hora += n * taxa_hora * (1.0 + taxa_encargos)

    # ── Equipamentos ─────────────────────────────────────────────────────────
    diesel_ins: dict | None = None
    for cod in ("MA-DIESEL-S10", "MA-DIESEL", "MA-DIESEL-ESCALA"):
        if cod in insumos_lookup:
            diesel_ins = insumos_lookup[cod]
            break

    for equip in composicao.get("equipamentos", []):
        eid = equip.get("equip_id") or ""
        n = float(equip.get("num_unidades", 1) or 1)  # planilha usa frações (0.17)
        ins = insumos_lookup.get(eid)
        if ins:
            pu = float(ins.get("preco_unitario", 0) or 0)
            custo_hora += n * pu  # equipment insumos are in R$/h

        # Combustível — consumo em L/h pode vir do registro de producao (dois nomes:
        # consumo_litros_hora_estimado ou consumo_litros_hora) ou do insumo de equip.
        consumo = float(equip.get("consumo_litros_hora_estimado") or equip.get("consumo_litros_hora") or 0)
        if consumo == 0 and ins:
            consumo = float((ins.get("atributos_especificos") or {}).get("consumo_litros_hora", 0) or 0)
        if consumo > 0 and diesel_ins:
            # Usa preco_unitario (referência da planilha, ex: 6,99 R$/L).
            # Preço regionalizado (SICRO) é referência de mercado regional, não o
            # preço contratual — não usar para calibração de produtividade.
            preco_diesel = float(diesel_ins.get("preco_unitario", 0) or 0)
            custo_hora += n * consumo * preco_diesel

    return custo_hora


def _enrich_producao_canonico(
    cpu_lookup: dict[str, dict],
    producao_lookup: dict[str, dict],
    insumos_lookup: dict[str, dict],
    horas_mes: float,
    taxa_encargos: float,
    validacoes: list,
) -> None:
    """NEP-029 D2: enriquece producao_lookup com valor_horario_canonico.

    Para cada CPU que possui precos_unitarios_sbdi.total > 0, deriva a
    produtividade canônica P_canonico = custo_hora_equipe / PU_sbdi de modo
    que P_engine = P_catalog por construção:

        custo_direto_engine = custo_hora × Q / P_canonico = PU_sbdi × Q

    O valor é gravado em producao_lookup[prod_id]['valor_horario_canonico'] e
    _resolve_productivity o prefere sobre 'valor_horario'. Isso garante que
    fe_nec = 1/η_p (apenas clima), eliminando o resíduo de mismatch de base.

    Emite VAL-PROD-CANONICO por CPU reportando o ratio P_canonico/P_original
    para rastreabilidade.
    """
    for cpu in cpu_lookup.values():
        cpu_id = cpu.get("codigo") or "?"
        pu_sbdi = float((cpu.get("precos_unitarios_sbdi") or {}).get("total") or 0)
        if pu_sbdi <= 0:
            continue

        prod_id = cpu.get("producao_id_ref") or ""
        prod = producao_lookup.get(prod_id)
        if not prod:
            continue

        # composicao_padrao_equipe está no producao record (ADR-053)
        composicao = prod.get("composicao_padrao_equipe") or {}
        if not composicao:
            continue

        # Prioriza o custo horário de referência da planilha (gravado no registro de producao)
        # — zero dependência de lookup de insumos, identidade exata P_canonico = C.
        custo_hora_ref = prod.get("custo_hora_total_referencia")
        custo_hora = _custo_hora_equipe(
            composicao,
            insumos_lookup,
            horas_mes,
            taxa_encargos,
            custo_hora_referencia=custo_hora_ref,
        )
        if custo_hora <= 0:
            continue

        P_canonico = custo_hora / pu_sbdi
        P_original = float(prod.get("valor_horario") or prod.get("producao_horaria") or 0)

        ratio = P_canonico / P_original if P_original > 0 else None

        # Guarda de ratio: só aplicar P_canonico quando a discrepância é calibração
        # (≤50% de diferença). Discrepâncias acima disso indicam dado de catálogo
        # inconsistente (e.g., valor_horario padrão copiado incorretamente) — sinalizar
        # como VAL-PROD-INCONSISTENCIA e preservar P_original para não quebrar o scheduler.
        _RATIO_MIN, _RATIO_MAX = 0.5, 2.0
        if ratio is not None and not (_RATIO_MIN <= ratio <= _RATIO_MAX):
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-PROD-INCONSISTENCIA",
                    status="AVISO",
                    mensagem=(
                        f"CPU {cpu_id}: ratio P_can/P_orig={ratio:.3f} fora do intervalo aceitável "
                        f"[{_RATIO_MIN},{_RATIO_MAX}]. "
                        f"P_canonico={P_canonico:.2f} vs P_original={P_original:.2f}. "
                        f"PU_sbdi={pu_sbdi:.4f} implica custo={custo_hora:.1f} R$/h → "
                        "valor_horario ou precos_unitarios_sbdi precisa correção no catálogo."
                    ),
                )
            )
            continue  # não aplica P_canonico — preserva P_original

        prod["valor_horario_canonico"] = P_canonico

        ratio_txt = f" (ratio={ratio:.3f})" if ratio else ""
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PROD-CANONICO",
                status="OK",
                mensagem=(
                    f"CPU {cpu_id}: P_canonico={P_canonico:.2f} "
                    f"[custo_hora={custo_hora:.2f}/PU_sbdi={pu_sbdi:.4f}]{ratio_txt}. "
                    "fe_nec → 1/η_p (resíduo de base eliminado)."
                ),
            )
        )


def _lookup_eficiencia(
    semana_key: str,
    prat_semanal: dict[str, float],
    prat_mensal: dict[str, float],
) -> float:
    """Busca eficiência para a semana. Fallback: média mensal do mês correspondente."""
    if prat_semanal and semana_key in prat_semanal:
        return prat_semanal[semana_key]

    if prat_mensal:
        year_str, week_str = semana_key.split("-W")
        week_num = int(week_str)
        month_num = max(1, min(12, (week_num - 1) // 4 + 1))
        month_key = f"{month_num:02d}"
        if month_key in prat_mensal:
            return prat_mensal[month_key]

    return 1.0


def _build_dist_cell(
    producao_semanal_base: float,
    num_eq: int,
    n_max: int,
    fator_clima: float,
    fator_calendario: float,
    quantitativo: float,
    qtd_acumulada: float,
    M_max: float = 1.0,
) -> DistribuicaoSemanal:
    """Monta uma célula semanal com decomposição causal completa (NEP-035).

    Decomposição η = η_s · η_p · η_w onde:
      η_s  = n_j / n_max                  (alocação — fração da força máxima planejada)
      η_p  = fator_clima × fator_calendario (praticabilidade)
      η_w  = m_ij / M_max                  (gestão; M_max=1.0 até calibração)
      η    = η_s · η_p · η_w = fator_total

    q_max_celula = producao_semanal_base × n_max × M_max  (capacidade teórica semanal)
    perda_fisica = q_max_celula × η_s - q_executada        (produção perdida em unidades físicas)

    eficiencia = η_w = m_ij/M_max = utilização (≠ praticabilidade; corrige ADR-082-cons)
    """
    n_max_safe = max(1, n_max)
    n_eq_safe = max(0, num_eq)
    praticabilidade = fator_clima * fator_calendario
    eta_s = min(1.0, n_eq_safe / n_max_safe)
    eta_p = praticabilidade
    q_max = producao_semanal_base * n_max_safe * M_max
    capacidade_real = q_max * eta_s * eta_p
    qtd_remanescente = max(0.0, quantitativo - qtd_acumulada)
    qtd_executada = min(capacidade_real, qtd_remanescente)
    eta_w = (qtd_executada / (capacidade_real * M_max)) if capacidade_real > 0 else 0.0
    eta_w = min(1.0, eta_w)
    eta_total = eta_s * eta_p * eta_w
    perda = max(0.0, q_max - qtd_executada)
    qtd_acumulada_nova = qtd_acumulada + qtd_executada
    pct = qtd_acumulada_nova / quantitativo if quantitativo > 0 else 0.0
    return DistribuicaoSemanal(
        num_equipes=n_eq_safe,
        qtd_executada=round(qtd_executada, 2),
        qtd_acumulada=round(qtd_acumulada_nova, 2),
        pct=round(pct, 4),
        eficiencia=round(eta_w, 4),
        fator_clima=round(fator_clima, 4),
        fator_calendario=round(fator_calendario, 4),
        fator_total=round(eta_total, 4),
        eta_s=round(eta_s, 4),
        eta_p=round(eta_p, 4),
        eta_w=round(eta_w, 4),
        q_max_celula=round(q_max, 2),
        perda_fisica=round(perda, 2),
    )


def _week_to_month(semana_key: str) -> str:
    """Converte 'AAAA-Www' para 'MM-YYYY'."""
    year_str, week_str = semana_key.split("-W")
    week_num = int(week_str)
    month_num = max(1, min(12, (week_num - 1) // 4 + 1))
    return f"{month_num:02d}-{year_str}"


def _event_occurs_on_day(evento: dict[str, Any], day: date) -> bool:
    """Avalia recorrência anual/unica para um dia civil."""
    try:
        inicio = date.fromisoformat(str(evento.get("inicio")))
        fim = date.fromisoformat(str(evento.get("fim")))
    except Exception:
        return False

    recorrencia = str(evento.get("recorrencia") or "anual")
    if recorrencia == "anual":
        if inicio.month > fim.month or (inicio.month == fim.month and inicio.day > fim.day):
            # Janela anual atravessando ano civil (ex.: 20/12 a 10/01)
            start_ref = date(day.year, inicio.month, inicio.day)
            end_ref = date(day.year + 1, fim.month, fim.day)
            prev_start = date(day.year - 1, inicio.month, inicio.day)
            prev_end = date(day.year, fim.month, fim.day)
            return (start_ref <= day <= end_ref) or (prev_start <= day <= prev_end)
        return (day.month, day.day) >= (inicio.month, inicio.day) and (day.month, day.day) <= (fim.month, fim.day)

    return inicio <= day <= fim


def _build_fator_calendario_semanal(
    semanas_obra: list[str],
    data_inicio: date,
    dias_semana_regime: int,
    calendario_config: dict[str, Any] | None,
) -> tuple[dict[str, float], list[CalendarioOperacionalSemanal]]:
    eventos = list((calendario_config or {}).get("eventos", []) or [])
    fatores: dict[str, float] = {}
    artefato: list[CalendarioOperacionalSemanal] = []

    for idx, semana_key in enumerate(semanas_obra):
        week_start = data_inicio + timedelta(weeks=idx)
        dias_uteis_base = float(dias_semana_regime)
        dias_uteis_efetivos = 0.0
        eventos_aplicados: set[str] = set()

        for d in range(dias_semana_regime):
            dia = week_start + timedelta(days=d)
            fator_dia = 1.0
            for evento in eventos:
                if not isinstance(evento, dict):
                    continue
                if _event_occurs_on_day(evento, dia):
                    fator_evt = float(evento.get("fator_operacao", 0.0) or 0.0)
                    fator_dia = min(fator_dia, max(0.0, min(1.0, fator_evt)))
                    if evento.get("id"):
                        eventos_aplicados.add(str(evento["id"]))
            dias_uteis_efetivos += fator_dia

        fator = dias_uteis_efetivos / dias_uteis_base if dias_uteis_base > 0 else 1.0
        fatores[semana_key] = round(max(0.0, min(1.0, fator)), 4)
        artefato.append(
            CalendarioOperacionalSemanal(
                semana_iso=semana_key,
                dias_uteis_base=round(dias_uteis_base, 2),
                dias_uteis_efetivos=round(dias_uteis_efetivos, 2),
                fator_calendario=fatores[semana_key],
                eventos_aplicados=tuple(sorted(eventos_aplicados)),
            )
        )

    return fatores, artefato


# ════════════════════════════════════════════════════════════════════════════════
# SECTION 2: HELPERS FOR AUTO MODE (Scheduling)
# ════════════════════════════════════════════════════════════════════════════════


def _weeks_between(start: date, end: date) -> int:
    """Conta semanas entre duas datas."""
    return max(1, ((end - start).days // 7) + 1)


def _extract_activities(
    canonical_in: CanonicalModel,
    cpu_lookup: dict | None = None,
    producao_lookup: dict | None = None,
    validacoes: list | None = None,
) -> list[Activity]:
    """Extrai atividades do canônico (atividades ou EAP).

    Calcula duração produtiva de cada atividade baseada em ADR-072:
      duration_weeks = ceil(quantitativo / (produtividade × horas_dia × dias_semana × n_equipes))

    Se cpu_lookup/producao_lookup não fornecidos, usa duration_weeks=1 como default.
    """
    activities: list[Activity] = []
    if canonical_in.atividades:
        for act in canonical_in.atividades:
            activities.append(
                Activity(
                    activity_id=act.atividade_id,
                    description=act.descricao,
                    duration_weeks=1,  # TODO: calcular duração produtiva de atividades diretas
                    required_resources={},
                )
            )
        return activities

    # Fallback to EAP: activity_id is item_id (without "-atv-1" suffix)
    # Matches DAG precedence keys which use item_id directly (ADR-081)
    # ADR-072 Direção A: calcular duração produtiva se catálogos disponíveis
    validacoes = validacoes or []
    import sys
    for item in canonical_in.eap:
        activity_id = item.item_id

        # Calcular duração produtiva se catálogos disponíveis
        duration_weeks = 1  # default
        if cpu_lookup and producao_lookup:
            # Usar 1 equipe como default se não especificado
            computed = _compute_productive_weeks(item.item_id, 1, canonical_in, cpu_lookup, producao_lookup, validacoes)
            if computed:
                duration_weeks = computed
            import sys

        activities.append(
            Activity(
                activity_id=activity_id,
                description=item.descricao or f"Item {item.item_id}",
                duration_weeks=duration_weeks,
                required_resources={},
            )
        )
    return activities


def _extract_dag(
    canonical: CanonicalModel,
    activity_ids: list[str],
    activities: list[Activity] | None = None,
) -> ActivityDAG:
    """Extrai DAG do canônico ou infere sequência linear.

    Se activities for None, extrai do canônico (legacy path).
    Caso contrário, usa as activities fornecidas (com duração produtiva já calculada).

    ADR-081: Extrai completion_threshold_pct da EAP (predecessores).
    """
    # ── Extrair arestas e thresholds ──────────────────────────────────────────
    edge_thresholds: dict[tuple[str, str], float] = {}

    if canonical.eap:
        for item in canonical.eap:
            for pred in item.predecessores_tipados():
                # activity_id é item_id direto (não "item_id-atv-1")
                # ver: ScheduledActivityCanonical.activity_id = item.item_id
                key = (pred.item_id, item.item_id)
                edge_thresholds[key] = float(pred.completion_threshold_pct)

    # Se não há predecessores na EAP, inferir sequência linear
    if not edge_thresholds:
        if canonical.activity_dag and canonical.activity_dag.arestas:
            for edge in canonical.activity_dag.arestas:
                edge_thresholds[(edge.de, edge.para)] = 1.0
        else:
            for i in range(len(activity_ids) - 1):
                edge_thresholds[(activity_ids[i], activity_ids[i + 1])] = 1.0

    precedence = list(edge_thresholds.keys())

    # ADR-072: Use pre-computed activities if provided, otherwise extract from canonical
    acts = activities if activities is not None else _extract_activities(canonical)
    return ActivityDAG(activities=acts, precedence=precedence, thresholds=edge_thresholds)


def _extract_pool(canonical: CanonicalModel) -> ResourcePool:
    """Extrai pool de recursos."""
    if not canonical.recurso_pool:
        return ResourcePool(resources={})
    resources: dict[str, int] = {}
    for item in canonical.recurso_pool:
        resources[item.tipo_id] = resources.get(item.tipo_id, 0) + int(item.quantidade_total)
    return ResourcePool(resources=resources)


def _relax_pool(pool: ResourcePool, factor: float = 1.1) -> ResourcePool:
    """Retorna novo ResourcePool com capacidades multiplicadas por factor."""
    return ResourcePool(resources={k: max(1, int(v * factor)) for k, v in pool.resources.items()})


# ────────────────────────────────────────────────────────────────────────────
# Extratores baseados em rcpsp_spec (ADR-046)
# ────────────────────────────────────────────────────────────────────────────


def _compute_ramp_profile(
    duration_weeks: int,
    ramp_params: dict,
    n_pico: int,
) -> list[float]:
    """ADR-074: Derive normalized ramp profile from ramp_params.

    Returns a list of *duration_weeks* floats in [0.0, 1.0] where 1.0 = peak demand.

    ramp_params keys:
      n_inicial: int            starting resource count at week 0 (default: 0)
      taxa_mobilizacao: float   resource units added per week during ramp-up
                                (default: n_pico → instant ramp = flat at plateau)
      taxa_desmobilizacao: float resource units removed per week during ramp-down
                                (default: same as taxa_mobilizacao)

    The three phases are:
      Ramp-up:    t in [0, T_up)            → floor(n_inicial + taxa_mob * (t+1)), clamped to n_pico
      Plateau:    t in [T_up, T_up+T_plat)  → n_pico
      Ramp-down:  t in [T_up+T_plat, end)   → max(0, n_pico - taxa_demob * (offset+1))

    If T_up + T_down > duration_weeks the plateau is 0 and ramp-down is truncated.
    """
    if duration_weeks <= 0 or n_pico <= 0:
        return [0.0] * max(0, duration_weeks)

    n_init = int(ramp_params.get("n_inicial", 0))
    # Default: ramp up in 1 step (instant = flat at peak)
    taxa_mob = float(ramp_params.get("taxa_mobilizacao", float(n_pico)))
    taxa_demob = float(ramp_params.get("taxa_desmobilizacao", taxa_mob))

    # Phase durations
    if taxa_mob > 0 and n_pico > n_init:
        t_up = math.ceil((n_pico - n_init) / taxa_mob)
    else:
        t_up = 0
    if taxa_demob > 0:
        t_down = math.ceil(n_pico / taxa_demob)
    else:
        t_down = 0

    t_plateau = max(0, duration_weeks - t_up - t_down)
    # If ramp phases exceed duration, truncate ramp-down
    if t_up + t_down > duration_weeks:
        t_down = max(0, duration_weeks - t_up)
        t_plateau = 0

    profile: list[float] = []
    for t in range(duration_weeks):
        if t < t_up:
            val = min(float(n_pico), n_init + taxa_mob * (t + 1))
        elif t < t_up + t_plateau:
            val = float(n_pico)
        else:
            offset = t - t_up - t_plateau
            val = max(0.0, n_pico - taxa_demob * (offset + 1))
        profile.append(round(min(1.0, val / n_pico), 6))

    return profile


def _mean_praticabilidade(canonical_in: CanonicalModel) -> float:
    """Praticabilidade média do projeto (Σ percentual_produtivo_semanal / N).

    ADR-082-cons: usada para dimensionar a duração produtiva de forma consistente
    com a produção semanal climática — sem isso, a duração (P nominal) é curta
    demais e Σ q_ij < Q (sub-entrega). Retorna 1.0 quando não há dado climático
    (projetos sem praticabilidade ficam inalterados).
    """
    prat = getattr(canonical_in, "praticabilidade", None)
    sem = None
    if isinstance(prat, dict):
        sem = prat.get("percentual_produtivo_semanal")
    elif prat is not None:
        sem = getattr(prat, "percentual_produtivo_semanal", None)
    if isinstance(sem, dict) and sem:
        vals = [float(v) for v in sem.values() if isinstance(v, (int, float)) and v > 0]
        if vals:
            return max(0.05, min(1.0, sum(vals) / len(vals)))
    return 1.0


def _compute_productive_weeks(
    item_id: str,
    n_resources: int,
    canonical_in: CanonicalModel,
    cpu_lookup: dict,
    producao_lookup: dict,
    validacoes: list,
) -> int | None:
    """ADR-072 (Direção A): duração produtiva = ceil(Q / (P × h/dia × d/sem × n_resources)).

    Nota (ADR-082-cons): a praticabilidade NÃO entra aqui — estender a duração por
    clima tornaria o RCPSP inviável sob prazos apertados (decisão de prazo/pool,
    não default silencioso). A sub-entrega resultante (Σ q_ij < Q quando clima < 1)
    é tornada explícita pela checagem de completude (VAL-CRON-01) em ambos os modos.
    Retorna None quando não é possível calcular.
    """
    eap_item = next((e for e in canonical_in.eap if e.item_id == item_id), None)
    if not eap_item:
        return None
    Q = float(getattr(eap_item, "quantitativo", 0))
    if Q <= 0:
        return None
    cpu_id = getattr(eap_item, "cpu_id", "") or ""
    cpu = cpu_lookup.get(cpu_id)
    if not cpu:
        return None
    P = _resolve_productivity(cpu, producao_lookup, validacoes)
    if not P or P <= 0:
        return None
    regime = canonical_in.projeto.regime_trabalho
    prod_per_week = P * regime.horas_dia * regime.dias_semana * n_resources
    if prod_per_week <= 0:
        return None
    result = max(1, math.ceil(Q / prod_per_week))
    return result


def _extract_activities_from_spec(
    spec: dict,
    canonical_in: CanonicalModel | None = None,
    cpu_lookup: dict | None = None,
    producao_lookup: dict | None = None,
    validacoes: list | None = None,
) -> list[Activity]:
    """Extrai atividades a partir de rcpsp_spec (ADR-046, ADR-072, ADR-074).

    Quando ``canonical_in``, ``cpu_lookup`` e ``producao_lookup`` são
    fornecidos, aplica Direção A (ADR-072): substitui ``duration_weeks`` pela
    duração produtiva calculada a partir de Q / taxa de produção, mantendo a
    janela original em ``window_weeks`` para restrição de corredor.

    ADR-074: Quando ``ramp_params`` presente na atividade da spec, deriva
    ``ramp_profile`` normalizado (lista de floats [0,1] com length = duration_weeks).
    O ramp é aplicado após a redução de duração para a duração produtiva.
    """
    use_productive = canonical_in is not None and cpu_lookup is not None and producao_lookup is not None
    activities = []
    for i, a in enumerate(spec["activities"]):
        window_w = int(a["duration_weeks"])
        productive_w = window_w  # fallback: sem alteração
        if use_productive:
            n_res = max(1, sum(a.get("required_resources", {}).values()))
            computed = _compute_productive_weeks(
                a["item_id"],
                n_res,
                canonical_in,  # type: ignore[arg-type]
                cpu_lookup,  # type: ignore[arg-type]
                producao_lookup,  # type: ignore[arg-type]
                validacoes or [],
            )
            if computed is not None and computed < window_w:
                productive_w = computed
            # else: keep productive_w = window_w (fallback)

        # ADR-074: derive ramp_profile from ramp_params if present
        ramp_profile: list[float] | None = None
        ramp_params = a.get("ramp_params")
        if ramp_params and isinstance(ramp_params, dict) and productive_w > 0:
            req = dict(a.get("required_resources", {}))
            n_pico = max(req.values()) if req else 1
            ramp_profile = _compute_ramp_profile(productive_w, ramp_params, n_pico)

        activities.append(
            Activity(
                activity_id=a["item_id"],
                description=a.get("descricao", a["item_id"]),
                duration_weeks=productive_w,
                required_resources=dict(a.get("required_resources", {})),
                window_weeks=window_w if productive_w < window_w else None,
                ramp_profile=ramp_profile,
            )
        )
    return activities


def _extract_pool_from_spec(spec: dict, canonical_in: CanonicalModel | None = None) -> ResourcePool:
    """Extrai (ou infere) o pool de recursos a partir de rcpsp_spec.

    ADR-046: pool explícito é usado como está.
    ADR-091: quando ``resource_pool`` está ausente/vazio, o pool é *derivado* do
    problema (atividades + precedência + objetivo de negócio em ``pool_config``).
    Atividades sem ``required_resources`` na spec têm ``e_{i,r}`` derivado de
    ``EquipeDireta.equipamentos`` (Fase 1). O pool inferido é gravado de volta em
    ``spec['resource_pool']`` — assim skill-05 e a persistência enxergam o mesmo
    pool — e o diagnóstico do tradeoff tempo×custo fica em ``spec['pool_inferido_diag']``.
    """
    explicit = spec.get("resource_pool") or {}
    if explicit:
        return ResourcePool(resources={k: int(v) for k, v in explicit.items()})

    from concilium.application.scheduling import inferir_pool_minimo_from_spec

    equipes = list(getattr(canonical_in, "equipes_diretas", []) or []) if canonical_in else None
    pool, diag = inferir_pool_minimo_from_spec(spec, equipes=equipes)
    spec["resource_pool"] = dict(pool)
    spec["pool_inferido_diag"] = diag
    return ResourcePool(resources={k: int(v) for k, v in pool.items()})


def _extract_dag_from_spec(
    spec: dict,
    activities: list[Activity],
    eap_items: list | None = None,
) -> ActivityDAG:
    """ADR-081: Extrai DAG de precedência do rcpsp_spec e/ou da EAP.

    Fontes (por prioridade):
    1. eap[].predecessores  — fonte canônica, inclui completion_threshold_pct
    2. rcpsp_spec.precedence — override/suplemento (para par já na EAP, prevalece)

    Formato suportado para rcpsp_spec.precedence:
      - [pred_id, succ_id]            → θ=1.0 (FS clássico)
      - [pred_id, succ_id, theta]     → θ=float fornecido
    """
    from concilium.application.skills.manifests._04_cronograma_skill_helpers import (
        extract_dag_from_spec_or_eap,
    )

    return extract_dag_from_spec_or_eap(spec, activities, eap_items)


def _to_canonical_candidate(
    heuristic: str,
    schedule_output: Any,
    quality_score: float,
    relaxed: bool = False,
) -> ScheduleCandidateCanonical:
    """Converte schedule output para ScheduleCandidateCanonical."""
    return ScheduleCandidateCanonical(
        heuristic=heuristic,
        scheduled_activities=[
            ScheduledActivityCanonical(
                activity_id=a.activity_id,
                start_week=a.start_week,
                end_week=a.end_week,
                duration_weeks=a.duration_weeks,
                assigned_resources=dict(a.assigned_resources),
                ramp_profile=a.ramp_profile,  # ADR-074: propagate for distribuicao_semanal
            )
            for a in schedule_output.scheduled_activities
        ],
        makespan=schedule_output.makespan,
        quality_score=round(quality_score, 6),
        metrics={
            "resource_leveling_score": schedule_output.metrics.resource_leveling_score,
            "idle_time": float(schedule_output.metrics.idle_time),
            "activity_fragmentation": float(schedule_output.metrics.activity_fragmentation),
            "critical_path_slack_min": schedule_output.metrics.critical_path_slack_min,
            "resource_utilization_avg": schedule_output.metrics.resource_utilization_avg,
        },
        relaxed=relaxed,
    )


def _try_milp(
    activities: list[Activity],
    dag: ActivityDAG,
    pool: ResourcePool,
    deadline_weeks: int,
    timeout_seconds: int = 30,
) -> ScheduleCandidateCanonical | None:
    """Tenta resolver com MILP (opcional, lazy import)."""
    try:
        from concilium.application.scheduling.milp import MILPScheduler

        scheduler = MILPScheduler(timeout_seconds=timeout_seconds)
        sched = scheduler.schedule(
            activities=activities,
            dag=dag,
            pool=pool,
            deadline_weeks=deadline_weeks,
        )
        quality = sched.metrics.quality_score(deadline_weeks=deadline_weeks)
        return _to_canonical_candidate("MILP", sched, quality, relaxed=False)
    except (ImportError, Exception):
        return None


# ════════════════════════════════════════════════════════════════════════════════
# SECTION 3: NEW BRIDGE HELPERS (Mode Execution & Aggregation)
# ════════════════════════════════════════════════════════════════════════════════


def _validate_preconditions(canonical: CanonicalModel, validacoes: list[ValidacaoItem]) -> bool:
    """Validações comuns a ambos os modos."""
    if not canonical.projeto:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-CRON-PRECONDICAO",
                status="ERRO",
                mensagem="Projeto não definido no canônico.",
            )
        )
        return False

    if not canonical.eap:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-CRON-PRECONDICAO",
                status="ERRO",
                mensagem="EAP vazia no canônico.",
            )
        )
        return False

    if not canonical.praticabilidade:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-CRON-PRECONDICAO",
                status="AVISO",
                mensagem="Praticabilidade não calculada; usando 100% de produtividade.",
            )
        )

    return True


def _can_extract_dag(canonical: CanonicalModel) -> bool:
    """Verifica se atividades ou DAG estão disponíveis para auto-schedule."""
    return bool(canonical.activity_dag or canonical.atividades or canonical.eap)


def _resolve_productivity(
    cpu: dict,
    producao_lookup: dict[str, dict],
    validacoes: list[ValidacaoItem],
) -> float:
    """Resolve produtividade da CPU via producao_id_ref (ADR-053 Fase 3).

    Usa 'valor_horario' do registro de producao para o scheduling. 'valor_horario_canonico'
    (NEP-029 D2) é populado pelo _enrich_producao_canonico() como indicador de calibração
    mas NÃO é usado para scheduling — seu uso é no PE builder para fe_nec ajustado.
    A atualização do catalog é feita manualmente após validação humana.

    Also checks for stored productivity data in cpu_meta (from enrichment).
    """
    # First check if productivity was enriched directly from project data
    cpu_meta = cpu.get("cpu_meta", {})
    if isinstance(cpu_meta, dict) and "producao_horaria" in cpu_meta:
        valor = cpu_meta.get("producao_horaria")
        if valor is not None and isinstance(valor, (int, float)):
            return float(valor)

    prod_id_ref = cpu.get("producao_id_ref")
    if prod_id_ref and prod_id_ref in producao_lookup:
        prod_item = producao_lookup[prod_id_ref]
        valor = prod_item.get("valor_horario")
        if valor is None:
            valor = prod_item.get("producao_horaria")
            if valor is not None:
                validacoes.append(
                    ValidacaoItem(
                        codigo="VAL-PROD-04-PROD-LEGACY",
                        status="AVISO",
                        mensagem=(
                            f"Produtividade {prod_id_ref} usa campo legado 'producao_horaria'. "
                            "Migre para 'valor_horario'."
                        ),
                    )
                )
        if valor is not None and isinstance(valor, (int, float)):
            return float(valor)

    if "producao_horaria" in cpu or "producao_id" in cpu:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PROD-04-DEPRECATED",
                status="AVISO",
                mensagem=(
                    f"CPU {cpu.get('codigo')} usa campos legados (producao_horaria/producao_id). "
                    "Atualize para producao_id_ref."
                ),
            )
        )

    validacoes.append(
        ValidacaoItem(
            codigo="VAL-PROD-04",
            status="AVISO",
            mensagem=f"Produtividade não encontrada para CPU {cpu.get('codigo')} (producao_id_ref); assumindo 1000.0.",
        )
    )
    # Use high default productivity (1000 units/hour) when CPU not found
    # Allows scheduling to proceed; actual productivity should come from catalog
    # This is a graceful degradation allowing benchmarks to execute despite missing data
    return 1000.0


def _build_activity_item_map(canonical: CanonicalModel) -> dict[str, str]:
    """Mapeia activity_id -> item_id.

    Sempre inclui item_id→item_id como base (cobertura de AUTO/RCPSP onde o
    solver usa item_id como activity_id). Sobrepõe com atividade_id→eap_item_id
    quando atividades explícitas existem (modo MANUAL).
    """
    mapping: dict[str, str] = {}
    # Fallback: item_id direto (RCPSP/AUTO — activity_id == item_id)
    for item in canonical.eap:
        mapping[item.item_id] = item.item_id
    # Override: atividade_id → eap_item_id (MANUAL — UUIDs de atividades)
    if canonical.atividades:
        for act in canonical.atividades:
            mapping[act.atividade_id] = act.eap_item_id
    return mapping


def _find_item_by_id(eap: list, item_id: str):
    """Encontra item na EAP por item_id."""
    for item in eap:
        if item.item_id == item_id:
            return item
    return None


def _infer_teams_from_resources(
    assigned_resources: dict[str, int],
    cpu: dict,
    week_offset: int,
    total_weeks: int,
    ramp_profile: list[float] | None = None,
) -> int:
    """Infere num_equipes a partir de assigned_resources.

    ADR-046: assigned_resources é demanda por semana (unidades/semana),
    não total acumulado. Retorna a soma direta das unidades de recurso
    alocadas, que corresponde ao número de equipes ativas nessa semana.

    ADR-074: Quando ``ramp_profile`` é fornecido, escala a demanda peak pelo
    fator da semana. ``ramp_profile[week_offset]`` ∈ [0.0, 1.0] onde 1.0 = pico.

    Minimalista fallback: Quando assigned_resources está vazio (pool vazio em AUTO_SCHEDULE),
    retorna 1 equipe por semana para permitir que skill-05 calcule custos. Isso é uma
    heurística padrão que representa "1 equipe típica para essa atividade".
    """
    if not assigned_resources:
        return 1
    peak = int(sum(assigned_resources.values()))
    if ramp_profile is not None and week_offset < len(ramp_profile):
        return max(0, round(peak * ramp_profile[week_offset]))
    return peak


def _aggregate_to_monthly(distribuicao_por_item: dict[str, dict[str, DistribuicaoSemanal]]) -> dict[str, dict]:
    """Agrega distribuicao_semanal em distribuicao_mensal."""
    monthly_agg: dict[str, dict] = {}
    for item_id, distribuicao_semanal in distribuicao_por_item.items():
        for semana_key, dist_semanal in distribuicao_semanal.items():
            month_str = _week_to_month(semana_key)
            if month_str not in monthly_agg:
                monthly_agg[month_str] = {"qtd_executada": 0.0, "num_itens": 0, "atividades": []}
            monthly_agg[month_str]["qtd_executada"] += dist_semanal.qtd_executada
            if item_id not in monthly_agg[month_str]["atividades"]:
                monthly_agg[month_str]["atividades"].append(item_id)
            monthly_agg[month_str]["num_itens"] += 1
    return monthly_agg


# ════════════════════════════════════════════════════════════════════════════════
# SECTION 4: MODE EXECUTION FUNCTIONS (MERGED)
# ════════════════════════════════════════════════════════════════════════════════


def _emm_find_vazios(item_id: str, distribuicao: dict, semanas_obra: list) -> list[str]:
    """Finds gap weeks inside productive periods."""
    semanas_produtivas = [s for s, d in distribuicao.items() if d.num_equipes > 0]
    if len(semanas_produtivas) < 2:
        return []
    inicio_idx = semanas_obra.index(semanas_produtivas[0])
    fim_idx = semanas_obra.index(semanas_produtivas[-1])
    return [
        f"{item_id}@{semanas_obra[i]}"
        for i in range(inicio_idx + 1, fim_idx)
        if distribuicao[semanas_obra[i]].num_equipes == 0
    ]


def _emm_process_item(
    item: Any,
    cpu: dict,
    producao_lookup: dict,
    regime: Any,
    prat_semanal: dict,
    prat_mensal: dict,
    fator_calendario_semanal: dict[str, float],
    semanas_obra: list,
    num_equipes_por_item: dict,
    validacoes: list,
) -> tuple[dict, list, list]:
    """Computes distribuicao and error lists for a single EAP item."""
    P = _resolve_productivity(cpu, producao_lookup, validacoes)
    producao_semanal_base = P * regime.horas_dia * regime.dias_semana
    equipes_semanas = num_equipes_por_item.get(item.item_id, {})
    # NEP-035: n_max = pico de alocação planejado para a atividade (η_s = n_j / n_max)
    n_max = max((max(0, equipes_semanas.get(s, 0)) for s in semanas_obra), default=1) or 1
    distribuicao = {}
    qtd_acumulada = 0.0
    for semana_key in semanas_obra:
        num_eq = max(0, equipes_semanas.get(semana_key, 0))
        fator_clima = _lookup_eficiencia(semana_key, prat_semanal, prat_mensal)
        fator_calendario = fator_calendario_semanal.get(semana_key, 1.0)
        cell = _build_dist_cell(
            producao_semanal_base,
            num_eq,
            n_max,
            fator_clima,
            fator_calendario,
            item.quantitativo,
            qtd_acumulada,
        )
        qtd_acumulada = cell.qtd_acumulada
        distribuicao[semana_key] = cell
    erros_completude = []
    pct_completude = qtd_acumulada / item.quantitativo if item.quantitativo > 0 else 0.0
    if pct_completude < 0.999:
        erros_completude.append((item.item_id, round(pct_completude, 4)))
    erros_vazios = _emm_find_vazios(item.item_id, distribuicao, semanas_obra)
    return distribuicao, erros_completude, erros_vazios


def _execute_manual_mode(
    canonical_in: CanonicalModel,
    num_equipes_por_item: dict[str, dict[str, int]],
    semanas_obra: list[str],
    cpu_lookup: dict[str, dict],
    producao_lookup: dict[str, dict],
    regime: Any,
    prat_semanal: dict[str, float],
    prat_mensal: dict[str, float],
    fator_calendario_semanal: dict[str, float],
    catalogo: dict[str, Any],
    validacoes: list[ValidacaoItem],
) -> dict[str, dict[str, DistribuicaoSemanal]]:
    """Executa lógica Skill 02 (modo manual)."""
    distribuicao_por_item: dict[str, dict[str, DistribuicaoSemanal]] = {}
    erros_completude_all = []
    erros_vazios_all = []

    for item in canonical_in.eap:
        cpu = cpu_lookup.get(item.cpu_id)
        if not cpu:
            # CPU not found in catalog - create synthetic CPU with reasonable defaults
            # This allows scheduling to proceed with sensible assumptions
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-EAP-01",
                    status="AVISO",
                    mensagem=f"CPU {item.cpu_id} (item {item.item_id}) não encontrada no catálogo; usando CPU sintética.",
                )
            )
            # Create synthetic CPU with reasonable defaults for scheduling
            cpu = {
                "codigo": item.cpu_id,
                "descricao": f"CPU sintética para {item.item_id}",
                "producao_id_ref": None,  # Will trigger default productivity of 100.0
            }
        dist, erros_c, erros_v = _emm_process_item(
            item,
            cpu,
            producao_lookup,
            regime,
            prat_semanal,
            prat_mensal,
            fator_calendario_semanal,
            semanas_obra,
            num_equipes_por_item,
            validacoes,
        )
        distribuicao_por_item[item.item_id] = dist
        erros_completude_all.extend(erros_c)
        erros_vazios_all.extend(erros_v)

    if erros_completude_all:
        msg = "; ".join([f"{iid}={pct * 100:.1f}%" for iid, pct in erros_completude_all])
        # ADR-082: Incomplete items are warnings, not errors. Climate/schedule constraints
        # may reduce capacity below project requirements. Decision to extend schedule or add
        # teams is a business decision (ADR-091), not a technical blocker.
        validacoes.append(ValidacaoItem(codigo="VAL-CRON-01", status="AVISO", mensagem=f"Itens não completados: {msg}"))
    if erros_vazios_all:
        # ADR-082: Scheduling gaps are warnings, not errors. May indicate suboptimal
        # allocation but don't prevent schedule execution.
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-CRON-02", status="AVISO", mensagem=f"Gaps detectados: {'; '.join(erros_vazios_all[:5])}"
            )
        )
    return distribuicao_por_item


def _rasfc_extract_inputs(
    canonical_in: CanonicalModel,
    inputs: dict,
    validacoes: list,
    cpu_lookup: dict | None = None,
    producao_lookup: dict | None = None,
) -> tuple[list, Any, Any, int] | None:
    """Extracts (activities, dag, pool, deadline_weeks) from spec or canonical. Returns None on error."""
    rcpsp_spec = inputs.get("rcpsp_spec")
    if rcpsp_spec and isinstance(rcpsp_spec, dict):
        # ADR-091 Fase 4: pool_config é entrada de negócio first-class. Quando
        # fornecido em inputs (ou pela UI/formulário QQP/EAP), é propagado para a
        # spec antes da inferência, sem expor resource_pool ao usuário.
        pool_config_in = inputs.get("pool_config")
        if isinstance(pool_config_in, dict) and "pool_config" not in rcpsp_spec:
            rcpsp_spec["pool_config"] = pool_config_in
        # ADR-072: pass lookups so productive duration is computed
        activities = _extract_activities_from_spec(rcpsp_spec, canonical_in, cpu_lookup, producao_lookup, validacoes)
        if not activities:
            validacoes.append(
                ValidacaoItem(codigo="VAL-SCHED-01", status="ERRO", mensagem="rcpsp_spec sem atividades.")
            )
            return None
        pool = _extract_pool_from_spec(rcpsp_spec, canonical_in)
        # ADR-091: se o pool foi inferido, registra o tradeoff tempo×custo
        diag = rcpsp_spec.get("pool_inferido_diag")
        if isinstance(diag, dict):
            notas = "; ".join(diag.get("notas", [])) or "sem restrições adicionais"
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-POOL-INFER",
                    status="OK",
                    mensagem=(
                        f"Pool inferido (objetivo={diag.get('objetivo')}): "
                        f"{diag.get('pool_inferido')} | makespan~{diag.get('makespan_estimado_semanas')}sem "
                        f"(mín {diag.get('makespan_minimo_semanas')}sem) | {notas}"
                    ),
                )
            )
        # ADR-081: passa eap_items para derivar precedência com thresholds
        dag = _extract_dag_from_spec(rcpsp_spec, activities, eap_items=canonical_in.eap or [])
    else:
        activities = _extract_activities(canonical_in, cpu_lookup, producao_lookup, validacoes)
        if not activities:
            validacoes.append(ValidacaoItem(codigo="VAL-SCHED-01", status="ERRO", mensagem="Sem atividades."))
            return None
        # ADR-072: pass pre-computed activities to preserve duration_weeks calculation
        dag = _extract_dag(canonical_in, [a.activity_id for a in activities], activities=activities)
        pool = _extract_pool(canonical_in)

    if not pool.resources:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-SCHED-02", status="AVISO", mensagem="Pool vazio — agendando sem restrições de recursos."
            )
        )

    deadline_weeks = int(
        inputs.get("deadline_weeks")
        or (rcpsp_spec.get("deadline_weeks") if isinstance(rcpsp_spec, dict) else None)
        or _weeks_between(canonical_in.projeto.data_inicio, canonical_in.projeto.data_termino)
    )
    return activities, dag, pool, deadline_weeks


def _rasfc_run_heuristics(
    activities: list, dag: Any, pool: Any, deadline_weeks: int, inputs: dict, validacoes: list
) -> tuple[list, bool]:
    """Runs heuristic scheduling with optional pool relaxation. Returns (candidates_canonical, relaxed_flag)."""
    strategy = select_scheduling_algorithm(
        num_activities=len(activities),
        num_resource_types=max(1, len(pool.resources)),
        contract_duration_weeks=deadline_weeks,
        deadline_margin_pct=float(inputs.get("deadline_margin_pct", 0.2)),
        criticality=str(inputs.get("criticality", "medium")),
    )
    if inputs.get("algorithm"):
        strategy.algorithm = str(inputs["algorithm"])
    if inputs.get("heuristics"):
        strategy.heuristics = list(inputs["heuristics"])

    heuristics = strategy.heuristics or ["MINSLK"]
    explored = explore_schedules(
        activities=activities,
        dag=dag,
        pool=pool,
        deadline_weeks=deadline_weeks,
        heuristics=heuristics,
        top_n=int(inputs.get("top_n", 3)),
        strategy=strategy,
    )
    relaxed_flag = False

    if not explored:
        relaxed_pool = _relax_pool(pool)
        explored = explore_schedules(
            activities=activities,
            dag=dag,
            pool=relaxed_pool,
            deadline_weeks=deadline_weeks,
            heuristics=heuristics,
            top_n=3,
            strategy=strategy,
        )
        if explored:
            relaxed_flag = True
            validacoes.append(ValidacaoItem(codigo="VAL-SCHED-03", status="AVISO", mensagem="Pool relaxado 110%."))

    return [
        _to_canonical_candidate(r.heuristic, r.schedule, r.quality_score, relaxed_flag) for r in explored
    ], relaxed_flag


def _run_auto_schedule_fallback_chain(
    canonical_in: CanonicalModel,
    inputs: dict[str, Any],
    validacoes: list[ValidacaoItem],
    cpu_lookup: dict | None = None,
    producao_lookup: dict | None = None,
) -> tuple[list[ScheduleCandidateCanonical], ScheduleCandidateCanonical | None]:
    """Executa fallback chain (heurísticas -> relax -> MILP).

    ADR-046: se inputs contiver 'rcpsp_spec', usa extratores baseados na spec
    em vez de tentar derivar do canônico (que pode estar incompleto).
    ADR-072: cpu_lookup/producao_lookup usados para derivar duração produtiva.
    """
    _rcpsp_spec = inputs.get("rcpsp_spec")
    extracted = _rasfc_extract_inputs(canonical_in, inputs, validacoes, cpu_lookup, producao_lookup)
    if extracted is None:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-SCHED-EXTRACT-FAIL",
                status="ERRO",
                mensagem="Falha ao extrair inputs de cronograma (atividades, DAG, pool ou deadline inválidos)."
            )
        )
        return [], None
    activities, dag, pool, deadline_weeks = extracted

    candidates_canonical, _relaxed = _rasfc_run_heuristics(activities, dag, pool, deadline_weeks, inputs, validacoes)

    if not candidates_canonical:
        milp_candidate = _try_milp(activities, dag, pool, deadline_weeks, timeout_seconds=30)
        if milp_candidate:
            candidates_canonical = [milp_candidate]
            validacoes.append(ValidacaoItem(codigo="VAL-SCHED-04", status="AVISO", mensagem="MILP usado."))

    if not candidates_canonical:
        validacoes.append(ValidacaoItem(codigo="VAL-SCHED-05", status="ERRO", mensagem="Cronograma inviável."))
        return [], None

    best_candidate = candidates_canonical[0]
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-SCHED-OK",
            status="OK",
            mensagem=f"{best_candidate.heuristic} (qualidade {best_candidate.quality_score:.4f})",
        )
    )
    return candidates_canonical, best_candidate


def _convert_schedule_to_distribuicao(
    schedule_selected: ScheduleCandidateCanonical,
    canonical_in: CanonicalModel,
    semanas_obra: list[str],
    cpu_lookup: dict[str, dict],
    producao_lookup: dict[str, dict],
    regime: Any,
    prat_semanal: dict[str, float],
    prat_mensal: dict[str, float],
    fator_calendario_semanal: dict[str, float],
    validacoes: list[ValidacaoItem],
) -> dict[str, dict[str, DistribuicaoSemanal]]:
    """Converte scheduled activities para distribuicao_semanal."""

    distribuicao_por_item: dict[str, dict[str, DistribuicaoSemanal]] = {}
    activity_to_item = _build_activity_item_map(canonical_in)

    for sa in schedule_selected.scheduled_activities:
        item_id = activity_to_item.get(sa.activity_id)
        if not item_id:
            validacoes.append(
                ValidacaoItem(codigo="VAL-CRON-CONVERT", status="AVISO", mensagem=f"{sa.activity_id} não mapeada.")
            )
            continue

        item = _find_item_by_id(canonical_in.eap, item_id)
        if not item:
            continue

        cpu = cpu_lookup.get(item.cpu_id)
        if not cpu:
            # CPU not found - create synthetic CPU for scheduling to proceed
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-EAP-01",
                    status="AVISO",
                    mensagem=f"CPU {item.cpu_id} não encontrada no catálogo; usando CPU sintética.",
                )
            )
            # Create synthetic CPU with reasonable defaults
            cpu = {
                "codigo": item.cpu_id,
                "descricao": f"CPU sintética para {item.item_id}",
                "producao_id_ref": None,
            }

        P = _resolve_productivity(cpu, producao_lookup, validacoes)
        producao_semanal_base = P * regime.horas_dia * regime.dias_semana
        # NEP-035: pré-cômputo de n_max (pico de alocação da atividade) para η_s = n_j/n_max.
        # Dupla passagem: 1ª leve sobre offsets para determinar o pico; 2ª constrói as células.
        ramp = getattr(sa, "ramp_profile", None)
        n_max = (
            max(
                (
                    _infer_teams_from_resources(sa.assigned_resources, cpu, off, sa.duration_weeks, ramp_profile=ramp)
                    for off in range(sa.duration_weeks)
                ),
                default=1,
            )
            or 1
        )
        distribuicao = {}
        qtd_acumulada = 0.0

        for week_offset in range(sa.duration_weeks):
            week_num = sa.start_week + week_offset
            semana_key = (
                semanas_obra[week_num]
                if week_num < len(semanas_obra)
                else _iso_week_key(canonical_in.projeto.data_inicio + timedelta(weeks=week_num))
            )

            inferred_num_equipes = _infer_teams_from_resources(
                sa.assigned_resources,
                cpu,
                week_offset,
                sa.duration_weeks,
                ramp_profile=ramp,
            )
            fator_clima = _lookup_eficiencia(semana_key, prat_semanal, prat_mensal)
            fator_calendario = fator_calendario_semanal.get(semana_key, 1.0)
            cell = _build_dist_cell(
                producao_semanal_base,
                inferred_num_equipes,
                n_max,
                fator_clima,
                fator_calendario,
                item.quantitativo,
                qtd_acumulada,
            )
            qtd_acumulada = cell.qtd_acumulada
            distribuicao[semana_key] = cell

        # DEBUG: verificar distribuição final
        if item.item_id in ["eap-1_0", "eap-1_1"]:
            for semana, dist in sorted(distribuicao.items())[:3]:
                print(f"  {semana}: qtd_executada={dist.qtd_executada:.1f}", file=_sys_distribuicao.stderr)
        distribuicao_por_item[item.item_id] = distribuicao

        # ADR-082-cons: checagem de completude também no caminho AUTO_SCHEDULE
        # (antes só existia no modo manual) — torna VISÍVEL a sub-entrega Σ q_ij < Q
        # antes silenciosa. Não bloqueia (AVISO): entregar Q sob clima é decisão de
        # prazo/pool (estender janela ou +equipes — ADR-091), não um default.
        if item.quantitativo > 0:
            pct_completude = qtd_acumulada / item.quantitativo
            if pct_completude < 0.999:
                p_bar = _mean_praticabilidade(canonical_in)
                semanas_nec = math.ceil(sa.duration_weeks / p_bar) if p_bar > 0 else sa.duration_weeks
                validacoes.append(
                    ValidacaoItem(
                        codigo="VAL-CRON-01",
                        status="AVISO",
                        mensagem=(
                            f"Item '{item_id}' sub-entrega: Σ q_ij = {pct_completude * 100:.1f}% de Q na "
                            f"janela agendada ({sa.duration_weeks}sem). Clima reduz a produção semanal além "
                            f"da capacidade da janela. Para entregar Q (p̄={p_bar:.2f}): ~{semanas_nec}sem "
                            "OU +equipes (decisão de prazo/pool — ADR-091)."
                        ),
                    )
                )

        distribuicao_por_item[item_id] = distribuicao

    return distribuicao_por_item


# ════════════════════════════════════════════════════════════════════════════════
# SECTION 5: POOL CONSTRAINT CHECK
# ════════════════════════════════════════════════════════════════════════════════


def _cpv_get_equip_needed(cpu: dict) -> dict[str, int]:
    """Returns {equip_id: num_unidades} from CPU config."""
    team = cpu.get("equipe") or cpu.get("composicao_padrao_equipe") or {}
    return {e["equip_id"]: e["num_unidades"] for e in team.get("equipamentos", [])}


def _cpv_build_usage(
    canonical_in: CanonicalModel,
    cpu_lookup: dict[str, dict],
    distribuicao_por_item: dict[str, dict[str, DistribuicaoSemanal]],
) -> dict[str, dict[str, int]]:
    usage: dict[str, dict[str, int]] = {}
    for item in canonical_in.eap or []:
        cpu = cpu_lookup.get(item.cpu_id)
        if not cpu:
            continue
        equip_needed = _cpv_get_equip_needed(cpu)
        if not equip_needed:
            continue
        dist = distribuicao_por_item.get(item.item_id, {})
        for semana, d in dist.items():
            if d.num_equipes <= 0:
                continue
            week_usage = usage.setdefault(semana, {})
            for tipo_id, units_per_team in equip_needed.items():
                week_usage[tipo_id] = week_usage.get(tipo_id, 0) + d.num_equipes * units_per_team
    return usage


def _cpv_process_violations(
    usage: dict[str, dict[str, int]],
    pool: dict[str, int],
    validacoes: list[ValidacaoItem],
) -> list:
    from concilium.domain.models.constraint_violation import ConstraintViolation

    violations = []
    reported: set[str] = set()
    for semana, week_usage in sorted(usage.items()):
        for tipo_id, total_used in week_usage.items():
            available = pool.get(tipo_id)
            if available is None or total_used <= available:
                continue
            magnitude = float(total_used - available)
            violations.append(
                ConstraintViolation(
                    code="VAL-POOL-01",
                    status="ERRO",
                    magnitude=magnitude,
                    affected_items=[semana],
                    remediation_hint=f"Reduzir equipes de {tipo_id} em {semana} em {int(magnitude)}",
                )
            )
            key = f"{tipo_id}@{semana}"
            if key not in reported:
                reported.add(key)
                validacoes.append(
                    ValidacaoItem(
                        codigo="VAL-POOL-01",
                        status="ERRO",
                        mensagem=f"Pool excedido: {tipo_id} requer {total_used}, disponível {available} em {semana}",
                    )
                )
    return violations


def _check_pool_violations(
    canonical_in: CanonicalModel,
    distribuicao_por_item: dict[str, dict[str, DistribuicaoSemanal]],
    cpu_lookup: dict[str, dict],
    validacoes: list[ValidacaoItem],
):
    """Verifica violações de pool de recursos. Retorna lista de ConstraintViolation."""
    pool = {r.tipo_id: r.quantidade_total for r in (canonical_in.recurso_pool or [])}
    if not pool:
        return []
    usage = _cpv_build_usage(canonical_in, cpu_lookup, distribuicao_por_item)
    return _cpv_process_violations(usage, pool, validacoes)


# ════════════════════════════════════════════════════════════════════════════════
# SECTION 6: MAIN ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════════


def _check_wmp_pool(
    item_id: str,
    cpu: dict,
    policy: object,
    pool: dict,
    validacoes: list,
) -> None:
    if not pool:
        return
    for e in (cpu.get("equipe") or {}).get("equipamentos", []):
        eid = e.get("equip_id") or e.get("tipo_id")
        if not eid or eid not in pool:
            continue
        units = int(e.get("num_unidades", 1))
        peak_demand = policy.n_maximo * units  # type: ignore[union-attr]
        if peak_demand > pool[eid]:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-WMP-POOL",
                    status="AVISO",
                    mensagem=(
                        f"WMP '{item_id}': n_maximo={policy.n_maximo} x "  # type: ignore[union-attr]
                        f"{eid}({units}/equipe) -> demanda_pico={peak_demand} "
                        f"excede pool={pool[eid]}. Reduza n_maximo ou amplie o pool."
                    ),
                )
            )


def _check_wmp_desmob(
    item_id: str,
    curva: object,
    policy: object,
    Q: float,
    P: float,
    validacoes: list,
) -> None:
    if not curva.incompleta:  # type: ignore[union-attr]
        return
    if policy.semanas_plateau is not None and policy.taxa_desmobilizacao > 0:  # type: ignore[union-attr]
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-WMP-DESMOB",
                status="AVISO",
                mensagem=(
                    f"WMP '{item_id}': desmobilizacao forcada pelo plateau={policy.semanas_plateau} sem."
                    f" antes de entregar Q={Q:.0f}. Aumente n_maximo ou semanas_plateau."
                ),
            )
        )  # type: ignore[union-attr]
    else:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-WMP-05",
                status="AVISO",
                mensagem=(
                    f"WMP '{item_id}': simulacao nao completou Q={Q:.0f} (P={P:.2f} un/h)."
                    " Verifique produtividade e politica."
                ),
            )
        )


def _build_wmp_policy(item_id: str, policy_dict: dict, validacoes: list) -> object | None:
    from concilium.domain.models.mobilizacao import MobilizacaoPolicy

    try:
        return MobilizacaoPolicy(**{k: v for k, v in policy_dict.items() if v is not None or k == "semanas_plateau"})
    except Exception as exc:
        validacoes.append(
            ValidacaoItem(codigo="VAL-WMP-03", status="AVISO", mensagem=f"WMP '{item_id}': politica invalida ({exc}).")
        )
        return None


def _run_wmp_simulation(
    sim: object,
    policy: object,
    item_id: str,
    Q: float,
    P: float,
    regime: object,
    prat_semanal: dict,
    semanas_obra: list,
    guard: int,
) -> object:
    semanas_iso = {t: semanas_obra[t] for t in range(min(guard, len(semanas_obra)))}
    return sim.simulate(  # type: ignore[union-attr]
        policy=policy,
        atividade_id=item_id,
        quantitativo=Q,
        producao_horaria=P,
        dias_semana=regime.dias_semana,  # type: ignore[union-attr]
        horas_dia=regime.horas_dia,  # type: ignore[union-attr]
        prat_semanal=prat_semanal or None,
        semanas_iso_por_offset=semanas_iso,
    )


def _process_single_wmp_policy(
    item_id: str,
    policy_dict: dict,
    eap_lookup: dict,
    cpu_lookup: dict,
    producao_lookup: dict,
    pool: dict,
    sim: object,
    regime: object,
    prat_semanal: dict,
    semanas_obra: list,
    semanas_set: set,
    result: dict,
    curves: list,
    validacoes: list,
) -> None:
    if item_id in result:
        return

    eap_item = eap_lookup.get(item_id)
    if not eap_item:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-WMP-01",
                status="AVISO",
                mensagem=f"Politica WMP '{item_id}' ignorada - item nao encontrado na EAP.",
            )
        )
        return

    cpu_id = getattr(eap_item, "cpu_id", "") or ""
    cpu = cpu_lookup.get(cpu_id)
    if not cpu:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-WMP-02",
                status="AVISO",
                mensagem=f"WMP '{item_id}': CPU '{cpu_id}' nao encontrada no catalogo.",
            )
        )
        return

    policy = _build_wmp_policy(item_id, policy_dict, validacoes)
    if policy is None:
        return

    _check_wmp_pool(item_id, cpu, policy, pool, validacoes)

    P = _resolve_productivity(cpu, producao_lookup, validacoes)
    Q = float(getattr(eap_item, "quantitativo", 0))
    if Q <= 0:
        validacoes.append(
            ValidacaoItem(codigo="VAL-WMP-04", status="AVISO", mensagem=f"WMP '{item_id}': quantitativo={Q} invalido.")
        )
        return

    prod_base = P * regime.dias_semana * regime.horas_dia * policy.n_maximo  # type: ignore[union-attr]
    nominal = math.ceil(Q / prod_base) if prod_base > 0 else 1
    from concilium.domain.services.mobilizacao_simulator import WorkforcePolicySimulator

    guard = WorkforcePolicySimulator.MAX_MULTIPLIER * max(1, nominal)

    curva = _run_wmp_simulation(sim, policy, item_id, Q, P, regime, prat_semanal, semanas_obra, guard)
    _check_wmp_desmob(item_id, curva, policy, Q, P, validacoes)

    curves.append(curva)
    week_map = {k: v for k, v in curva.to_num_equipes_por_semana().items() if k in semanas_set}
    result[item_id] = week_map
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-WMP-OK",
            status="OK",
            mensagem=(
                f"WMP '{item_id}': {curva.duration_weeks} sem.,"
                f" pico={curva.peak_teams} equipes, completa={curva.is_complete}."
            ),
        )
    )


def _extract_praticabilidade(canonical_in: object) -> tuple[dict, dict]:
    p = getattr(canonical_in, "praticabilidade", None)
    prat_semanal = (p.percentual_produtivo_semanal if p else {}) or {}
    prat_mensal = (p.percentual_produtivo_mensal if p else {}) or {}
    return prat_semanal, prat_mensal


def _determine_mode_and_distribuicao(
    canonical_in: object,
    inputs: dict,
    num_equipes_por_item: object,
    semanas_obra: list,
    cpu_lookup: dict,
    producao_lookup: dict,
    regime: object,
    prat_semanal: dict,
    prat_mensal: dict,
    fator_calendario_semanal: dict[str, float],
    catalogo: dict,
    validacoes: list,
) -> tuple[str | None, dict, list, object, bool]:
    """Returns (mode, distribuicao_por_item, schedule_candidates, schedule_selected, failed)."""
    rcpsp_spec = inputs.get("rcpsp_spec")
    if rcpsp_spec and isinstance(rcpsp_spec, dict):
        mode = "AUTO_SCHEDULE (rcpsp_spec)"
        validacoes.append(ValidacaoItem(codigo="VAL-CRON-MODE", status="OK", mensagem="Modo AUTO (rcpsp_spec)."))
        # ADR-072: pass lookups for productive-duration derivation
        schedule_candidates, schedule_selected = _run_auto_schedule_fallback_chain(
            canonical_in, inputs, validacoes, cpu_lookup, producao_lookup
        )
        if not schedule_selected:
            return mode, {}, schedule_candidates, None, True
        distribuicao_por_item = _convert_schedule_to_distribuicao(
            schedule_selected,
            canonical_in,
            semanas_obra,
            cpu_lookup,
            producao_lookup,
            regime,
            prat_semanal,
            prat_mensal,
            fator_calendario_semanal,
            validacoes,
        )
        return mode, distribuicao_por_item, schedule_candidates, schedule_selected, False

    elif num_equipes_por_item is not None and isinstance(num_equipes_por_item, dict):
        mode = "MANUAL_ALLOCATION"
        validacoes.append(ValidacaoItem(codigo="VAL-CRON-MODE", status="OK", mensagem="Modo MANUAL."))
        distribuicao_por_item = _execute_manual_mode(
            canonical_in,
            num_equipes_por_item,
            semanas_obra,
            cpu_lookup,
            producao_lookup,
            regime,
            prat_semanal,
            prat_mensal,
            fator_calendario_semanal,
            catalogo,
            validacoes,
        )
        return mode, distribuicao_por_item, [], None, False

    elif _can_extract_dag(canonical_in):
        mode = "AUTO_SCHEDULE"
        validacoes.append(ValidacaoItem(codigo="VAL-CRON-MODE", status="OK", mensagem="Modo AUTO."))
        # ADR-072: pass lookups for productive-duration derivation
        schedule_candidates, schedule_selected = _run_auto_schedule_fallback_chain(
            canonical_in, inputs, validacoes, cpu_lookup, producao_lookup
        )
        if not schedule_selected:
            return mode, {}, schedule_candidates, None, True
        distribuicao_por_item = _convert_schedule_to_distribuicao(
            schedule_selected,
            canonical_in,
            semanas_obra,
            cpu_lookup,
            producao_lookup,
            regime,
            prat_semanal,
            prat_mensal,
            fator_calendario_semanal,
            validacoes,
        )
        return mode, distribuicao_por_item, schedule_candidates, schedule_selected, False

    else:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-CRON-MODE",
                status="ERRO",
                mensagem="Nenhum modo detectado: forneca 'num_equipes_por_item' ou DAG + recursos.",
            )
        )
        return None, {}, [], None, True


def _build_scheduled_activities(
    canonical_in: object,
    distribuicao_por_item: dict,
    semanas_obra: list,
    schedule_selected: object | None = None,
) -> list:
    from datetime import timedelta

    # Build lookup: activity_id → assigned_resources from the scheduler output.
    # In AUTO mode, schedule_selected is a ScheduleCandidateCanonical whose
    # scheduled_activities carry the RCPSP resource assignments.  In MANUAL mode
    # schedule_selected is None (or has no activities), so assigned_resources stays
    # empty — which is correct, as manual allocation doesn't model RCPSP resources.
    assigned_lookup: dict[str, dict] = {}
    if schedule_selected is not None:
        for sa in getattr(schedule_selected, "scheduled_activities", []):
            ar = getattr(sa, "assigned_resources", None)
            if ar:
                assigned_lookup[sa.activity_id] = dict(ar)

    scheduled_activities_out = []

    # ADR-072: Preservar duração original do scheduler em vez de recalcular
    # Constrói mapa de item_id → duration_weeks do schedule_selected
    # (activity_id do scheduler tem formato "item_id-atv-1", need to extract item_id)
    duration_lookup = {}
    if schedule_selected is not None and getattr(schedule_selected, "scheduled_activities", None):
        for sa in schedule_selected.scheduled_activities:
            activity_id = getattr(sa, "activity_id", None)
            duration = getattr(sa, "duration_weeks", None)
            if activity_id and duration:
                # Extract item_id from activity_id (format: "item_id-atv-1")
                # activity_id pode ser "eap-1_0-atv-1" ou simplesmente "eap-1_0"
                if "-atv-" in activity_id:
                    item_id = activity_id.rsplit("-atv-", 1)[0]
                else:
                    item_id = activity_id
                duration_lookup[item_id] = duration

    for item in canonical_in.eap:  # type: ignore[union-attr]
        distribuicao_semanal = distribuicao_por_item.get(item.item_id, {})
        semanas_com_producao = [s for s, d in distribuicao_semanal.items() if d.qtd_executada > 0]
        start_week = semanas_obra.index(semanas_com_producao[0]) if semanas_com_producao else 0
        end_week = semanas_obra.index(semanas_com_producao[-1]) if semanas_com_producao else 0
        data_inicio = canonical_in.projeto.data_inicio + timedelta(weeks=start_week)  # type: ignore[union-attr]
        data_fim = canonical_in.projeto.data_inicio + timedelta(weeks=end_week + 1)  # type: ignore[union-attr]

        # ADR-072: Use original duration from scheduler if available
        duration_from_scheduler = duration_lookup.get(item.item_id, None)
        if duration_from_scheduler is not None:
            duration_weeks = duration_from_scheduler
        else:
            # Fallback: calculate from scheduled weeks if no scheduler duration
            duration_weeks = max(1, end_week - start_week + 1)

        scheduled_activities_out.append(
            ScheduledActivityCanonical(
                activity_id=item.item_id,
                start_week=start_week,
                end_week=end_week,
                duration_weeks=duration_weeks,
                data_inicio=data_inicio,
                data_fim=data_fim,
                distribuicao_semanal=distribuicao_semanal,
                assigned_resources=assigned_lookup.get(item.item_id, {}),
            )
        )
    return scheduled_activities_out


def _build_cronograma_out(
    mode: str | None,
    schedule_selected: object,
    scheduled_activities_out: list,
    semanas_obra: list,
    distribuicao_mensal: dict,
    validacoes: list,
) -> object:
    AVAILABLE_SCHEDULE_ALGORITHMS = ("MINSLK", "LPT", "MAXRES", "ES", "GR", "MILP", "CP-SAT", "LNS")
    if mode == "MANUAL_ALLOCATION":
        _algo = "manual_allocation"
    elif schedule_selected and schedule_selected.heuristic in AVAILABLE_SCHEDULE_ALGORITHMS:  # type: ignore[union-attr]
        _algo = schedule_selected.heuristic  # type: ignore[union-attr]
    else:
        _algo = "MINSLK"

    return Cronograma(
        algorithm=_algo,
        quality_score=schedule_selected.quality_score if schedule_selected else 0.0,  # type: ignore[union-attr]
        makespan_weeks=schedule_selected.makespan if schedule_selected else len(semanas_obra),  # type: ignore[union-attr]
        is_feasible=not any(v.status == "ERRO" for v in validacoes),
        was_relaxed=schedule_selected.relaxed if schedule_selected else False,  # type: ignore[union-attr]
        scheduled_activities=scheduled_activities_out,
        distribuicao_mensal=distribuicao_mensal,
        pct_completude=1.0,
    )


def _build_intervalos_and_campanhas(
    canonical_in: object,
    cronograma_out: object,
    scheduled_activities_out: list,
    validacoes: list,
) -> tuple[list, object]:
    intervalos = []
    for sa in scheduled_activities_out:
        intervalos.extend(AtividadeIntervalo.from_scheduled_activity(sa))

    analise_campanhas = None
    try:
        from concilium.domain.services.campanha_equipamento_builder import CampanhaEquipamentoBuilder

        _temp = canonical_in.model_copy(update={"cronograma": cronograma_out})  # type: ignore[union-attr]
        analise_campanhas = CampanhaEquipamentoBuilder().build(_temp)
        if analise_campanhas.alertas_custo_duplicado:
            for alert in analise_campanhas.alertas_custo_duplicado:
                validacoes.append(ValidacaoItem(codigo="VAL-CAMP-01", status="AVISO", mensagem=alert))
    except Exception as _camp_exc:
        import logging as _camp_log

        _camp_log.getLogger(__name__).warning("CampanhaEquipamento falhou (best-effort): %s", _camp_exc)

    return intervalos, analise_campanhas


def _expand_mobilizacao_policies(
    canonical_in: CanonicalModel,
    policies: dict[str, dict],
    existing_allocation: dict[str, dict[str, int]] | None,
    semanas_obra: list[str],
    cpu_lookup: dict[str, dict],
    producao_lookup: dict[str, dict],
    regime: Any,
    prat_semanal: dict[str, float],
    validacoes: list[ValidacaoItem],
) -> tuple[dict[str, dict[str, int]], list]:
    """ADR-054 Phase 3: Convert WMP policies into per-week team allocations for MANUAL mode."""
    from concilium.domain.services.mobilizacao_simulator import WorkforcePolicySimulator

    result: dict[str, dict[str, int]] = dict(existing_allocation or {})
    curves: list = []
    semanas_set = set(semanas_obra)
    eap_lookup = {item.item_id: item for item in (canonical_in.eap or [])}
    pool = {r.tipo_id: r.quantidade_total for r in (canonical_in.recurso_pool or [])}
    sim = WorkforcePolicySimulator()

    merged_policies: dict[str, dict] = dict(policies)
    for atividade in canonical_in.atividades or []:
        if atividade.mobilizacao_policy is not None:
            merged_policies[atividade.eap_item_id] = atividade.mobilizacao_policy.model_dump()

    for item_id, policy_dict in merged_policies.items():
        _process_single_wmp_policy(
            item_id,
            policy_dict,
            eap_lookup,
            cpu_lookup,
            producao_lookup,
            pool,
            sim,
            regime,
            prat_semanal,
            semanas_obra,
            semanas_set,
            result,
            curves,
            validacoes,
        )

    return result, curves


def run_cronograma(
    canonical_in: CanonicalModel,
    inputs: dict[str, Any],
    catalogo: dict[str, Any] | None = None,
    **_kwargs: Any,
) -> SkillResult:
    """Gera cronograma semanal unificado com agregacao mensal. Modo: manual ou automatico."""
    validacoes: list[ValidacaoItem] = []
    catalogo = catalogo or {}

    if not _validate_preconditions(canonical_in, validacoes):
        return SkillResult(canonical_in, validacoes)

    regime = canonical_in.projeto.regime_trabalho
    semanas_obra = _semanas_entre(canonical_in.projeto.data_inicio, canonical_in.projeto.data_termino)
    cpu_lookup = _build_cpu_lookup(catalogo)
    producao_lookup = _build_producao_lookup(catalogo)
    # NEP-029 D2: enriquecer producao_lookup com P_canonico = custo_hora / PU_sbdi.
    # NEP-029 D2: enriquece producao_lookup com P_canonico = custo_hora/PU_sbdi.
    # IMPORTANTE: P_canonico fica em 'valor_horario_canonico' mas NÃO substitui
    # 'valor_horario' para o scheduling (_resolve_productivity não o consome).
    # Finalidade: indicador diagnóstico de calibração — fe_nec_ajustado via PE builder.
    # Atualização de catálogo é passo manual explícito, não automático de runtime.
    insumos_lookup = _build_insumos_lookup(catalogo)
    horas_mes = regime.horas_dia * regime.dias_semana * 4.345  # semanas/mês
    taxa_encargos = float(inputs.get("taxa_encargos_mo", 1.0))  # default 100% encargos
    _enrich_producao_canonico(cpu_lookup, producao_lookup, insumos_lookup, horas_mes, taxa_encargos, validacoes)
    prat_semanal, prat_mensal = _extract_praticabilidade(canonical_in)
    calendario_config = (
        inputs.get("calendario_operacional") if isinstance(inputs.get("calendario_operacional"), dict) else {}
    )
    fator_calendario_semanal, calendario_operacional = _build_fator_calendario_semanal(
        semanas_obra,
        canonical_in.projeto.data_inicio,
        regime.dias_semana,
        calendario_config,
    )

    num_equipes_por_item = inputs.get("num_equipes_por_item")

    wmp_curves: list = []
    mobilizacao_policies = inputs.get("mobilizacao_policies")
    if mobilizacao_policies and isinstance(mobilizacao_policies, dict):
        num_equipes_por_item, wmp_curves = _expand_mobilizacao_policies(
            canonical_in,
            mobilizacao_policies,
            num_equipes_por_item,
            semanas_obra,
            cpu_lookup,
            producao_lookup,
            regime,
            prat_semanal,
            validacoes,
        )

    mode, distribuicao_por_item, schedule_candidates, schedule_selected, failed = _determine_mode_and_distribuicao(
        canonical_in,
        inputs,
        num_equipes_por_item,
        semanas_obra,
        cpu_lookup,
        producao_lookup,
        regime,
        prat_semanal,
        prat_mensal,
        fator_calendario_semanal,
        catalogo,
        validacoes,
    )
    if failed:
        return SkillResult(canonical_in, validacoes)

    pool_violations = _check_pool_violations(canonical_in, distribuicao_por_item, cpu_lookup, validacoes)
    scheduled_activities_out = _build_scheduled_activities(
        canonical_in, distribuicao_por_item, semanas_obra, schedule_selected
    )
    distribuicao_mensal = _aggregate_to_monthly(distribuicao_por_item)
    cronograma_out = _build_cronograma_out(
        mode, schedule_selected, scheduled_activities_out, semanas_obra, distribuicao_mensal, validacoes
    )
    intervalos, analise_campanhas = _build_intervalos_and_campanhas(
        canonical_in, cronograma_out, scheduled_activities_out, validacoes
    )

    # ADR-105: Inferir janelas de mobilização automaticamente
    mob_schedule = None
    try:
        meta_dict = {
            "data_inicio": canonical_in.projeto.data_inicio.isoformat(),
            "data_termino": canonical_in.projeto.data_termino.isoformat(),
        }
        eap_list = [
            {
                "item_id": item.item_id,
                "predecessores": [{"item_id": p.item_id} for p in item.predecessores] if item.predecessores else [],
            }
            for item in canonical_in.eap
        ]
        mob_schedule = infer_mob_windows(meta_dict, eap_list)
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-MOB-SCHEDULE-OK",
                status="OK",
                mensagem="Janelas de mobilização inferidas com sucesso (ADR-105).",
            )
        )
    except Exception as e:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-MOB-SCHEDULE-ERRO",
                status="AVISO",
                mensagem=f"Falha ao inferir janelas de mobilização: {str(e)}",
            )
        )

    update_dict = {
        "cronograma": cronograma_out,
        "intervalos_atividade": intervalos,
        "fator_calendario_semanal": fator_calendario_semanal,
        "calendario_operacional": calendario_operacional,
        "constraint_violations": pool_violations if pool_violations else canonical_in.constraint_violations,
        "curvas_forca": wmp_curves if wmp_curves else canonical_in.curvas_forca,
        "analise_campanhas": analise_campanhas,
    }
    if mob_schedule:
        update_dict["mob_schedule"] = mob_schedule

    updated_canonical = canonical_in.model_copy(update=update_dict)

    validacoes.append(
        ValidacaoItem(
            codigo="VAL-CRON-OK",
            status="OK",
            mensagem=(
                f"Cronograma ({mode}): {len(scheduled_activities_out)} atividades, {len(distribuicao_mensal)} meses."
            ),
        )
    )

    return SkillResult(updated_canonical, validacoes)
