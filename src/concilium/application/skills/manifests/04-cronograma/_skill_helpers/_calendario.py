"""Skill 04 — Cronograma (parte extraída de skill.py)."""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

from concilium.application.scheduling import (
    Activity,
    ActivityDAG,
    ResourcePool,
)
from concilium.domain.models.canonical import (
    CalendarioOperacionalSemanal,
    CanonicalModel,
    ValidacaoItem,
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


#: Default de `observar_pontos_facultativos` (escolha de configuração de
#: projeto, ADR-068 — não um fato do warehouse de feriados) quando o projeto
#: não define `inputs["observar_pontos_facultativos"]` explicitamente. Ponto
#: facultativo é binário, não uma fração de produtividade: ou a obra segue
#: trabalhando normalmente nesse dia (não observa -> fator 1.0, o default) ou
#: para inteiramente, igual a um feriado (observa -> fator 0.0). Ajustável
#: entre versões do mesmo projeto para comparar o efeito no custo/cronograma.
OBSERVAR_PONTOS_FACULTATIVOS_DEFAULT = False


def _resolve_fator_evento(evento: dict[str, Any], observar_pontos_facultativos: bool) -> float:
    """Resolve o fator_operacao de um evento: valor explícito > default por tipo.

    tipo="feriado" sem fator_operacao explícito é 0.0 (parada integral,
    estrutural — não é uma escolha). tipo="ponto_facultativo" sem valor
    explícito é binário: 0.0 se o projeto optou por observá-lo (parada
    integral, igual a um feriado), 1.0 se não (dia normal) — nunca um valor
    intermediário, pontos facultativos não têm meio-termo de adesão parcial.
    """
    fo = evento.get("fator_operacao")
    if fo is not None:
        return float(fo)
    if evento.get("tipo") == "ponto_facultativo":
        return 0.0 if observar_pontos_facultativos else 1.0
    return 0.0


def _compute_dias_uteis_efetivos_semana(
    week_start: date,
    dias_semana_regime: int,
    eventos: list,
    observar_pontos_facultativos: bool = OBSERVAR_PONTOS_FACULTATIVOS_DEFAULT,
) -> tuple[float, set[str]]:
    """Calcula os dias úteis efetivos e os eventos aplicados em uma semana, dia a dia."""
    dias_uteis_efetivos = 0.0
    eventos_aplicados: set[str] = set()

    for d in range(dias_semana_regime):
        dia = week_start + timedelta(days=d)
        fator_dia = 1.0
        for evento in eventos:
            if not isinstance(evento, dict):
                continue
            if _event_occurs_on_day(evento, dia):
                fator_evt = _resolve_fator_evento(evento, observar_pontos_facultativos)
                fator_dia = min(fator_dia, max(0.0, min(1.0, fator_evt)))
                if evento.get("id"):
                    eventos_aplicados.add(str(evento["id"]))
        dias_uteis_efetivos += fator_dia

    return dias_uteis_efetivos, eventos_aplicados


def _build_fator_calendario_semanal(
    semanas_obra: list[str],
    data_inicio: date,
    dias_semana_regime: int,
    calendario_config: dict[str, Any] | None,
    observar_pontos_facultativos: bool = OBSERVAR_PONTOS_FACULTATIVOS_DEFAULT,
) -> tuple[dict[str, float], list[CalendarioOperacionalSemanal]]:
    eventos = list((calendario_config or {}).get("eventos", []) or [])
    fatores: dict[str, float] = {}
    artefato: list[CalendarioOperacionalSemanal] = []

    for idx, semana_key in enumerate(semanas_obra):
        week_start = data_inicio + timedelta(weeks=idx)
        dias_uteis_base = float(dias_semana_regime)

        dias_uteis_efetivos, eventos_aplicados = _compute_dias_uteis_efetivos_semana(
            week_start, dias_semana_regime, eventos, observar_pontos_facultativos
        )

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
    for item in canonical_in.eap:
        activity_id = item.item_id

        # Calcular duração produtiva se catálogos disponíveis
        duration_weeks = 1  # default
        if cpu_lookup and producao_lookup:
            # Usar 1 equipe como default se não especificado
            computed = _compute_productive_weeks(item.item_id, 1, canonical_in, cpu_lookup, producao_lookup, validacoes)
            if computed:
                duration_weeks = computed

        activities.append(
            Activity(
                activity_id=activity_id,
                description=item.descricao or f"Item {item.item_id}",
                duration_weeks=duration_weeks,
                required_resources={},
            )
        )
    return activities


def _build_item_to_activity_map(canonical: CanonicalModel) -> dict[str, str]:
    """Mapeia item_id (EAP) -> primeira activity_id correspondente (ADR-072/081).

    Quando `canonical.atividades` está populado (auto-derivado por
    `run_escopo_e_eap`, uma `Atividade` por item via `_build_atividades_for_item`),
    `_extract_activities` usa `atividade_id` (sufixo "-atv-N") como activity_id em
    vez do `item_id` puro — sem este mapeamento, as arestas de precedência
    extraídas da EAP (chaveadas por item_id) não batem com os ids usados pelo
    CP-SAT, deixando FS silenciosamente sem efeito (guarda em
    `_add_fs_precedence_constraints`) e lançando `KeyError` para SS/FF (sem
    guarda equivalente em `_add_extended_precedence_constraints`). Mantém "uma
    atividade por item para scheduling" — mesma simplificação já assumida por
    `_build_item_to_first_activity` na skill 01.
    """
    mapping: dict[str, str] = {}
    for act in getattr(canonical, "atividades", None) or []:
        mapping.setdefault(act.eap_item_id, act.atividade_id)
    return mapping


def _extract_edge_thresholds_from_eap(canonical: CanonicalModel) -> tuple[dict[tuple[str, str], float], list]:
    """Extrai edge_thresholds e precedências estendidas (SS/FF) a partir dos predecessores da EAP.

    ADR-081: Extrai completion_threshold_pct da EAP (predecessores).
    """
    from concilium.application.scheduling.cpsat_scheduler import ExtendedPrecedence as _EP

    edge_thresholds: dict[tuple[str, str], float] = {}
    extended: list[_EP] = []
    item_to_activity = _build_item_to_activity_map(canonical)

    if canonical.eap:
        for item in canonical.eap:
            succ_id = item_to_activity.get(item.item_id, item.item_id)
            for pred in item.predecessores_tipados():
                pred_id = item_to_activity.get(pred.item_id, pred.item_id)
                key = (pred_id, succ_id)
                tipo = str(getattr(pred, "tipo", "FS") or "FS").upper()
                lag = int(getattr(pred, "lag", 0) or 0)
                if tipo == "FS":
                    edge_thresholds[key] = float(pred.completion_threshold_pct)
                elif tipo == "SS":
                    edge_thresholds[key] = 1.0  # sentinela topológico
                    extended.append(_EP(pred=pred_id, succ=succ_id, tipo="SS", lag=lag))
                elif tipo == "FF":
                    edge_thresholds[key] = 1.0  # sentinela topológico
                    extended.append(_EP(pred=pred_id, succ=succ_id, tipo="FF", lag=lag))

    return edge_thresholds, extended


def _infer_linear_edge_thresholds(canonical: CanonicalModel, activity_ids: list[str]) -> dict[tuple[str, str], float]:
    """Infere edge_thresholds a partir do activity_dag existente ou de uma sequência linear."""
    edge_thresholds: dict[tuple[str, str], float] = {}
    if canonical.activity_dag and canonical.activity_dag.arestas:
        for edge in canonical.activity_dag.arestas:
            edge_thresholds[(edge.de, edge.para)] = 1.0
    else:
        for i in range(len(activity_ids) - 1):
            edge_thresholds[(activity_ids[i], activity_ids[i + 1])] = 1.0
    return edge_thresholds


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
    edge_thresholds, extended = _extract_edge_thresholds_from_eap(canonical)

    # Se não há predecessores na EAP, inferir sequência linear
    if not edge_thresholds:
        edge_thresholds = _infer_linear_edge_thresholds(canonical, activity_ids)

    precedence = list(edge_thresholds.keys())

    # ADR-072: Use pre-computed activities if provided, otherwise extract from canonical
    acts = activities if activities is not None else _extract_activities(canonical)
    return ActivityDAG(
        activities=acts, precedence=precedence, thresholds=edge_thresholds, extended_precedences=extended
    )


def _extract_pool(canonical: CanonicalModel) -> ResourcePool:
    """Extrai pool de recursos."""
    if not canonical.recurso_pool:
        return ResourcePool(resources={})
    resources: dict[str, int] = {}
    for item in canonical.recurso_pool:
        resources[item.tipo_id] = resources.get(item.tipo_id, 0) + int(item.quantidade_total)
    return ResourcePool(resources=resources)


def _relax_pool(pool: ResourcePool, factor: float = 1.1, deficit: dict[str, int] | None = None) -> ResourcePool:
    """Retorna novo ResourcePool com capacidades multiplicadas por factor.

    ADR-128 F7 (issue #117): `deficit`, quando fornecido (tipicamente
    `ScheduleOutput.pool_deficit` de uma tentativa anterior que falhou por
    capacidade de pool), sobrescreve o percentual heurístico com o pico real de
    demanda para os recursos ali listados — o percentual sozinho pode não crescer
    nada para capacidades pequenas (`int(4 * 1.1) == 4`) e nunca é garantidamente
    suficiente. Recursos fora de `deficit` (ou fora do `pool` original) continuam
    seguindo o percentual de sempre.
    """
    deficit = deficit or {}
    return ResourcePool(
        resources={k: deficit.get(k, max(1, int(v * factor))) for k, v in pool.resources.items()}
    )


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
            # Ramp-up: ceil garante que a semana tem equipes suficientes (ativa antes de plena)
            val = min(n_pico, math.ceil(n_init + taxa_mob * (t + 1)))
        elif t < t_up + t_plateau:
            val = n_pico
        else:
            # Ramp-down: floor garante contagem inteira decrescente
            offset = t - t_up - t_plateau
            val = max(0, math.floor(n_pico - taxa_demob * (offset + 1)))
        # Fração exata: val é int → val/n_pico codifica num_equipes sem arredondamento duplo
        profile.append(val / n_pico)

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
    """ADR-072 (Direção A): duração produtiva = ceil(Q / (P × h/dia × d/sem × η_jornada × n_resources)).

    Nota (ADR-082-cons): a praticabilidade (clima/calendário) NÃO entra aqui — estender a
    duração por clima tornaria o RCPSP inviável sob prazos apertados (decisão de prazo/pool,
    não default silencioso). A sub-entrega resultante (Σ q_ij < Q quando clima < 1)
    é tornada explícita pela checagem de completude (VAL-CRON-01) em ambos os modos.

    Nota (ADR-148): η_jornada (fração produtiva do dia) ENTRA aqui, ao contrário de
    clima/calendário — é determinístico e estrutural (sempre verdadeiro), não um risco
    variável. Excluí-lo faria todo item disparar VAL-CRON-01 permanentemente.

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
    P, _is_fallback = _resolve_productivity(cpu, producao_lookup, validacoes)
    if not P or P <= 0:
        return None
    regime = canonical_in.projeto.regime_trabalho
    prod_per_week = P * regime.horas_dia * regime.dias_semana * regime.eta_jornada * n_resources
    if prod_per_week <= 0:
        return None
    return max(1, math.ceil(Q / prod_per_week))


def _resolve_productivity_from_cpu_meta(cpu: dict) -> float | None:
    """Verifica se a produtividade foi enriquecida diretamente em cpu_meta."""
    cpu_meta = cpu.get("cpu_meta", {})
    if isinstance(cpu_meta, dict) and "producao_horaria" in cpu_meta:
        valor = cpu_meta.get("producao_horaria")
        if valor is not None and isinstance(valor, (int, float)):
            return float(valor)
    return None


def _resolve_productivity_from_lookup(
    cpu: dict,
    producao_lookup: dict[str, dict],
    validacoes: list[ValidacaoItem],
) -> float | None:
    """Resolve produtividade via producao_id_ref no producao_lookup, avisando sobre campo legado."""
    prod_id_ref = cpu.get("producao_id_ref")
    if not (prod_id_ref and prod_id_ref in producao_lookup):
        return None

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
                        f"Produtividade {prod_id_ref} usa campo legado 'producao_horaria'. Migre para 'valor_horario'."
                    ),
                )
            )
    if valor is not None and isinstance(valor, (int, float)):
        return float(valor)
    return None


def _warn_legacy_productivity_fields(cpu: dict, validacoes: list[ValidacaoItem]) -> None:
    """Avisa quando a CPU usa campos legados de produtividade (producao_horaria/producao_id)."""
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


def _resolve_productivity(
    cpu: dict,
    producao_lookup: dict[str, dict],
    validacoes: list[ValidacaoItem],
) -> tuple[float, bool]:
    """Resolve produtividade da CPU via producao_id_ref (ADR-053 Fase 3).

    Usa 'valor_horario' do registro de producao para o scheduling. 'valor_horario_canonico'
    (NEP-029 D2) é populado pelo _enrich_producao_canonico() como indicador de calibração
    mas NÃO é usado para scheduling — seu uso é no PE builder para fe_nec ajustado.
    A atualização do catalog é feita manualmente após validação humana.

    Also checks for stored productivity data in cpu_meta (from enrichment).

    Retorna (P, is_fallback) — is_fallback=True apenas quando P veio do default
    arbitrário de 1000.0 (issue #132: sinaliza item cuja produtividade não tem base
    real, para correlacionar com o fallback de precificação em skill-06).
    """
    # First check if productivity was enriched directly from project data
    valor = _resolve_productivity_from_cpu_meta(cpu)
    if valor is not None:
        return valor, False

    valor = _resolve_productivity_from_lookup(cpu, producao_lookup, validacoes)
    if valor is not None:
        return valor, False

    _warn_legacy_productivity_fields(cpu, validacoes)

    validacoes.append(
        ValidacaoItem(
            codigo="VAL-PROD-04",
            status="AVISO",
            mensagem=(
                f"Produtividade não encontrada para CPU {cpu.get('codigo')} (producao_id_ref); assumindo 1000.0. "
                "A duração/custo desta atividade não reflete produtividade real; se o PU também não tiver base "
                "bottom-up, o ponto de equilíbrio deste item é inconclusivo."
            ),
        )
    )
    # Use high default productivity (1000 units/hour) when CPU not found
    # Allows scheduling to proceed; actual productivity should come from catalog
    # This is a graceful degradation allowing benchmarks to execute despite missing data
    return 1000.0, True


__all__ = [
    "OBSERVAR_PONTOS_FACULTATIVOS_DEFAULT",
    "_build_fator_calendario_semanal",
    "_compute_dias_uteis_efetivos_semana",
    "_compute_productive_weeks",
    "_compute_ramp_profile",
    "_event_occurs_on_day",
    "_extract_activities",
    "_extract_dag",
    "_extract_edge_thresholds_from_eap",
    "_extract_pool",
    "_infer_linear_edge_thresholds",
    "_mean_praticabilidade",
    "_relax_pool",
    "_resolve_fator_evento",
    "_resolve_productivity",
    "_resolve_productivity_from_cpu_meta",
    "_resolve_productivity_from_lookup",
    "_warn_legacy_productivity_fields",
    "_week_to_month",
    "_weeks_between",
]
