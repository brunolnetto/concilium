"""Skill 04 — Cronograma (parte extraída de skill.py)."""

from __future__ import annotations

import math
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from concilium.application.scheduling.models import ReplenishableResource
from concilium.domain.constants import TETO_EXTENSAO_CRONOGRAMA_SEMANAS
from concilium.domain.models.canonical import (
    CanonicalModel,
    DistribuicaoSemanal,
    RegimeTrabalho,
    ScheduleCandidateCanonical,
    ValidacaoItem,
)

from ._calendario import _resolve_productivity  # ty: ignore[unresolved-import]
from ._custos import _build_dist_cell, _iso_week_key, _lookup_eficiencia  # ty: ignore[unresolved-import]
from ._validacao import (  # ty: ignore[unresolved-import]
    _build_activity_item_map,
    _extract_taxa_desmobilizacao_fracao,
    _find_item_by_id,
    _infer_teams_from_resources,
    _producao_maxima_com_rampa_down,
    _rasfc_extract_inputs,
    _rasfc_run_heuristics,
)

if TYPE_CHECKING:
    from concilium.domain.models.planning.mobilizacao import CurvaForca, MobilizacaoPolicy
    from concilium.domain.services.planning.mobilizacao_simulator import WorkforcePolicySimulator


def _run_auto_schedule_fallback_chain(
    canonical_in: CanonicalModel,
    inputs: dict[str, Any],
    validacoes: list[ValidacaoItem],
    cpu_lookup: dict | None = None,
    producao_lookup: dict | None = None,
    insumos_lookup: dict | None = None,
) -> tuple[list[ScheduleCandidateCanonical], ScheduleCandidateCanonical | None, list[ReplenishableResource]]:
    """Executa fallback chain (heurísticas -> relax).

    ADR-046: se inputs contiver 'rcpsp_spec', usa extratores baseados na spec
    em vez de tentar derivar do canônico (que pode estar incompleto).
    ADR-072: cpu_lookup/producao_lookup usados para derivar duração produtiva.
    ADR-128 F5: insumos_lookup usado (com o pareamento atividade→Producao extraído
    junto de cpu_lookup/producao_lookup) para montar ReplenishableResource, quando
    aplicável — opt-in, ver _build_replenishable_resources_if_any.
    ADR-128 F6: o 3º elemento do retorno propaga a lista de ReplenishableResource
    efetivamente aplicada, para skill.py persistir a contabilização canônica.
    """
    extracted = _rasfc_extract_inputs(canonical_in, inputs, validacoes, cpu_lookup, producao_lookup)
    if extracted is None:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-SCHED-EXTRACT-FAIL",
                status="ERRO",
                mensagem="Falha ao extrair inputs de cronograma (atividades, DAG, pool ou deadline inválidos).",
            )
        )
        return [], None, []
    activities, dag, pool, deadline_weeks, producoes_por_atividade = extracted

    candidates_canonical, _relaxed, replenishable_resources = _rasfc_run_heuristics(
        activities,
        dag,
        pool,
        deadline_weeks,
        inputs,
        validacoes,
        producoes_por_atividade,
        insumos_lookup,
        inputs.get("logistica_consumiveis"),
    )

    if not candidates_canonical:
        validacoes.append(ValidacaoItem(codigo="VAL-SCHED-05", status="ERRO", mensagem="Cronograma inviável."))
        return [], None, []

    best_candidate = candidates_canonical[0]
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-SCHED-OK",
            status="OK",
            mensagem=f"{best_candidate.heuristic} (qualidade {best_candidate.quality_score:.4f})",
        )
    )
    return candidates_canonical, best_candidate, replenishable_resources


def _resolve_item_for_scheduled_activity(
    sa: Any,
    activity_to_item: dict[str, str],
    canonical_in: CanonicalModel,
    validacoes: list[ValidacaoItem],
) -> tuple[str, Any] | None:
    """Resolve (item_id, item) para a scheduled activity; retorna None se deve ser pulada."""
    item_id = activity_to_item.get(sa.activity_id)
    if not item_id:
        validacoes.append(
            ValidacaoItem(codigo="VAL-CRON-CONVERT", status="AVISO", mensagem=f"{sa.activity_id} não mapeada.")
        )
        return None

    item = _find_item_by_id(canonical_in.eap, item_id)
    if not item:
        return None

    return item_id, item


def _resolve_cpu_for_item(item: Any, cpu_lookup: dict[str, dict], validacoes: list[ValidacaoItem]) -> dict:
    """Resolve a CPU do item, criando uma CPU sintética (com AVISO) se não encontrada no catálogo."""
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
    return cpu


def _compute_activity_n_max(sa: Any, cpu: dict, ramp: Any) -> int:
    """Pré-computa n_max (pico de alocação da atividade) para η_s = n_j/n_max (NEP-035)."""
    # Dupla passagem: 1ª leve sobre offsets para determinar o pico; 2ª constrói as células.
    return (
        max(
            (
                _infer_teams_from_resources(sa.assigned_resources, cpu, off, sa.duration_weeks, ramp_profile=ramp)
                for off in range(sa.duration_weeks)
            ),
            default=1,
        )
        or 1
    )


def _build_activity_distribuicao(
    sa: Any,
    item: Any,
    cpu: dict,
    ramp: Any,
    n_max: int,
    producao_semanal_base: float,
    semanas_obra: list[str],
    canonical_in: CanonicalModel,
    prat_semanal: dict[str, float],
    prat_mensal: dict[str, float],
    fator_calendario_semanal: dict[str, float],
    fator_jornada: float = 1.0,
) -> tuple[dict[str, DistribuicaoSemanal], float]:
    """Constrói a distribuição semanal (célula a célula) de uma scheduled activity.

    Estende além de `sa.duration_weeks` (duração nominal do RCPSP, calculada com
    produtividade nominal, sem antecipar clima/calendário/jornada real) quando η_p real
    reduz a produção semanal a ponto de não completar `item.quantitativo` dentro da
    janela original — sempre terminamos o quantitativo da atividade. Antes disso, o
    déficit só gerava um AVISO não-bloqueante (VAL-CRON-01) e ficava incompleto.

    Semanas extras (week_num além de `len(semanas_obra)`) repetem o mesmo padrão de
    clima/calendário da última semana real conhecida (`last_fator_clima`/
    `last_fator_calendario`) — sem isso, `_lookup_eficiencia`/`.get(..., 1.0)` recairiam
    no default de clima perfeito para semanas fora da tabela conhecida.

    Gate de ramp-down orientado a estado, não a calendário: `ramp_profile` (ADR-074) foi
    calculado ANTES de saber se a atividade ia sub-entregar, ancorando o início do
    ramp-down numa duração nominal que pode estar errada — deixado sem correção, isso
    tanto deixa a equipe encolher enquanto ainda falta muito quantitativo (rampa ancorada
    no fim errado) quanto nunca deixa a equipe encolher durante a extensão (fallback de
    `_infer_teams_from_resources` sempre volta ao pico). Em vez de confiar na posição no
    array, extraímos μ⁻ dele (`_extract_taxa_desmobilizacao_fracao`) e decidimos toda
    semana, com o estado real (Q remanescente), se é seguro começar/continuar a
    desmobilização agora (`_producao_maxima_com_rampa_down`) — nunca prevendo clima
    futuro, só usando o que já é fato. Quando o item não tem nenhum trecho de
    desmobilização declarado (μ⁻ indeterminável), o comportamento é idêntico ao anterior
    (sem gate, sem mudança).

    Teto de segurança: `TETO_EXTENSAO_CRONOGRAMA_SEMANAS` (10 anos) — nunca estende
    indefinidamente (ex: clima=0 por muitas semanas seguidas).
    """
    distribuicao: dict[str, DistribuicaoSemanal] = {}
    qtd_acumulada = 0.0
    # Último clima/calendário real conhecido (dentro de semanas_obra) — repetido nas
    # semanas de extensão em vez de recair no default 1.0 de _lookup_eficiencia/.get,
    # que assumiria clima perfeito "de graça" para semanas que não existiam no
    # cronograma original.
    last_fator_clima = 1.0
    last_fator_calendario = 1.0
    # Tolerância de 99,9% (mesmo critério de _warn_if_activity_underdelivers) em vez de
    # `qtd_acumulada < item.quantitativo` exato: `_build_dist_cell` arredonda qtd_acumulada
    # a 2 casas decimais a cada semana, então um resíduo residual menor que a granularidade
    # do arredondamento (ex: 0,003 de 676.519) nunca converge — cada incremento semanal é
    # absorvido pelo round() e a atividade nunca "termina", estendendo até o teto de 10 anos
    # só por arredondamento (achado real no AGIS: eap-1_6).
    quantitativo_min = item.quantitativo * 0.999

    taxa_desmob_fracao = _extract_taxa_desmobilizacao_fracao(ramp)
    frac_atual: float | None = None  # None = gate ainda dormente (ramp-up em curso)

    week_offset = 0
    while week_offset < sa.duration_weeks or (
        qtd_acumulada < quantitativo_min and week_offset < TETO_EXTENSAO_CRONOGRAMA_SEMANAS
    ):
        week_num = sa.start_week + week_offset
        if week_num < len(semanas_obra):
            semana_key = semanas_obra[week_num]
            fator_clima = _lookup_eficiencia(semana_key, prat_semanal, prat_mensal)
            fator_calendario = fator_calendario_semanal.get(semana_key, 1.0)
            last_fator_clima = fator_clima
            last_fator_calendario = fator_calendario
        else:
            semana_key = _iso_week_key(canonical_in.projeto.data_inicio + timedelta(weeks=week_num))
            fator_clima = last_fator_clima
            fator_calendario = last_fator_calendario

        equipes_estatico = _infer_teams_from_resources(
            sa.assigned_resources,
            cpu,
            week_offset,
            sa.duration_weeks,
            ramp_profile=ramp,
        )

        if taxa_desmob_fracao is None:
            inferred_num_equipes = equipes_estatico
        else:
            if frac_atual is None and n_max > 0 and equipes_estatico >= n_max:
                frac_atual = 1.0  # atingiu o pico pela 1ª vez: gate passa a decidir
            if frac_atual is None:
                inferred_num_equipes = equipes_estatico
            else:
                frac_candidata = max(0.0, frac_atual - taxa_desmob_fracao)
                capacidade_pico_semanal = producao_semanal_base * n_max * fator_clima * fator_calendario * fator_jornada
                producao_max_se_reduzir = _producao_maxima_com_rampa_down(
                    frac_candidata, taxa_desmob_fracao, capacidade_pico_semanal
                )
                qtd_remanescente_pre_semana = max(0.0, item.quantitativo - qtd_acumulada)
                if producao_max_se_reduzir >= qtd_remanescente_pre_semana:
                    frac_atual = frac_candidata
                inferred_num_equipes = max(0, round(frac_atual * n_max))
        cell = _build_dist_cell(
            producao_semanal_base,
            inferred_num_equipes,
            n_max,
            fator_clima,
            fator_calendario,
            item.quantitativo,
            qtd_acumulada,
            fator_jornada=fator_jornada,
        )
        qtd_acumulada = cell.qtd_acumulada
        distribuicao[semana_key] = cell
        week_offset += 1

    return distribuicao, qtd_acumulada


def _warn_if_activity_underdelivers(
    item: Any,
    item_id: str,
    sa: Any,
    qtd_acumulada: float,
    validacoes: list[ValidacaoItem],
) -> None:
    """AVISO quando mesmo o teto de extensão (10 anos) não bastou para entregar Q.

    `_build_activity_distribuicao` já estende a janela automaticamente além de
    `sa.duration_weeks`, repetindo o padrão de alocação/clima das últimas semanas,
    até Σ q_ij atingir 100% do quantitativo ou até TETO_EXTENSAO_CRONOGRAMA_SEMANAS.
    Este AVISO só dispara no caso patológico em que nem o teto de 10 anos bastou —
    sinal de que a praticabilidade da região é baixa demais para a atividade convergir.
    """
    if item.quantitativo <= 0:
        return
    pct_completude = qtd_acumulada / item.quantitativo
    if pct_completude < 0.999:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-CRON-01",
                status="AVISO",
                mensagem=(
                    f"Item '{item_id}' não atinge 100% do quantitativo mesmo após estender o "
                    f"cronograma até o teto de segurança ({TETO_EXTENSAO_CRONOGRAMA_SEMANAS} "
                    f"semanas): Σ q_ij = {pct_completude * 100:.1f}% de Q. Praticabilidade da "
                    "região é extremamente baixa — revisar clima/calendário/jornada ou "
                    "considerar +equipes (ADR-091)."
                ),
            )
        )


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
) -> tuple[dict[str, dict[str, DistribuicaoSemanal]], set[str]]:
    """Converte scheduled activities para distribuicao_semanal.

    Retorna também `fallback_item_ids` (issue #132): item_ids cuja produtividade foi
    resolvida via fallback arbitrário (P=1000 un/h), para correlacionar com o fallback
    de precificação em skill-06 e detectar quando ambos os lados do ponto de equilíbrio
    ficam sem base real de produtividade para o mesmo item.
    """

    distribuicao_por_item: dict[str, dict[str, DistribuicaoSemanal]] = {}
    fallback_item_ids: set[str] = set()
    activity_to_item = _build_activity_item_map(canonical_in)

    for sa in schedule_selected.scheduled_activities:
        resolved = _resolve_item_for_scheduled_activity(sa, activity_to_item, canonical_in, validacoes)
        if resolved is None:
            continue
        item_id, item = resolved

        cpu = _resolve_cpu_for_item(item, cpu_lookup, validacoes)

        P, is_fallback = _resolve_productivity(cpu, producao_lookup, validacoes)
        if is_fallback:
            fallback_item_ids.add(item_id)
        producao_semanal_base = P * regime.horas_dia * regime.dias_semana
        # NEP-035: pré-cômputo de n_max (pico de alocação da atividade) para η_s = n_j/n_max.
        ramp = getattr(sa, "ramp_profile", None)
        n_max = _compute_activity_n_max(sa, cpu, ramp)

        distribuicao, qtd_acumulada = _build_activity_distribuicao(
            sa,
            item,
            cpu,
            ramp,
            n_max,
            producao_semanal_base,
            semanas_obra,
            canonical_in,
            prat_semanal,
            prat_mensal,
            fator_calendario_semanal,
            fator_jornada=regime.eta_jornada,
        )

        _warn_if_activity_underdelivers(item, item_id, sa, qtd_acumulada, validacoes)

        distribuicao_por_item[item_id] = distribuicao

    return distribuicao_por_item, fallback_item_ids


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
    from concilium.domain.models.project.constraint_violation import ConstraintViolation

    violations = []
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
            # key=f"{tipo_id}@{semana}" é único por iteração (semana/tipo_id não repetem
            # dentro deste loop), então o dedup por `reported` nunca disparava — removido.
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


def _check_wmp_pool(
    item_id: str,
    cpu: dict,
    policy: MobilizacaoPolicy,
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
        peak_demand = policy.n_maximo * units
        if peak_demand > pool[eid]:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-WMP-POOL",
                    status="AVISO",
                    mensagem=(
                        f"WMP '{item_id}': n_maximo={policy.n_maximo} x "
                        f"{eid}({units}/equipe) -> demanda_pico={peak_demand} "
                        f"excede pool={pool[eid]}. Reduza n_maximo ou amplie o pool."
                    ),
                )
            )


def _check_wmp_desmob(
    item_id: str,
    curva: CurvaForca,
    policy: MobilizacaoPolicy,
    Q: float,
    P: float,
    validacoes: list,
) -> None:
    if not curva.incompleta:
        return
    if policy.semanas_plateau is not None and policy.taxa_desmobilizacao > 0:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-WMP-DESMOB",
                status="AVISO",
                mensagem=(
                    f"WMP '{item_id}': desmobilizacao forcada pelo plateau={policy.semanas_plateau} sem."
                    f" antes de entregar Q={Q:.0f}. Aumente n_maximo ou semanas_plateau."
                ),
            )
        )
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


def _build_wmp_policy(item_id: str, policy_dict: dict, validacoes: list) -> MobilizacaoPolicy | None:
    from concilium.domain.models.planning.mobilizacao import MobilizacaoPolicy

    try:
        return MobilizacaoPolicy(**{k: v for k, v in policy_dict.items() if v is not None or k == "semanas_plateau"})
    except Exception as exc:
        validacoes.append(
            ValidacaoItem(codigo="VAL-WMP-03", status="AVISO", mensagem=f"WMP '{item_id}': politica invalida ({exc}).")
        )
        return None


def _run_wmp_simulation(
    sim: WorkforcePolicySimulator,
    policy: MobilizacaoPolicy,
    item_id: str,
    Q: float,
    P: float,
    regime: RegimeTrabalho,
    prat_semanal: dict,
    semanas_obra: list,
    guard: int,
) -> CurvaForca:
    semanas_iso = {t: semanas_obra[t] for t in range(min(guard, len(semanas_obra)))}
    return sim.simulate(
        policy=policy,
        atividade_id=item_id,
        quantitativo=Q,
        producao_horaria=P,
        dias_semana=regime.dias_semana,
        horas_dia=regime.horas_dia,
        prat_semanal=prat_semanal or None,
        semanas_iso_por_offset=semanas_iso,
        eta_jornada=regime.eta_jornada,
    )


def _process_single_wmp_policy(
    item_id: str,
    policy_dict: dict,
    eap_lookup: dict,
    cpu_lookup: dict,
    producao_lookup: dict,
    pool: dict,
    sim: WorkforcePolicySimulator,
    regime: RegimeTrabalho,
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

    P, _is_fallback = _resolve_productivity(cpu, producao_lookup, validacoes)
    Q = float(getattr(eap_item, "quantitativo", 0))
    if Q <= 0:
        validacoes.append(
            ValidacaoItem(codigo="VAL-WMP-04", status="AVISO", mensagem=f"WMP '{item_id}': quantitativo={Q} invalido.")
        )
        return

    prod_base = P * regime.dias_semana * regime.horas_dia * regime.eta_jornada * policy.n_maximo
    nominal = math.ceil(Q / prod_base) if prod_base > 0 else 1
    from concilium.domain.services.planning.mobilizacao_simulator import WorkforcePolicySimulator

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


__all__ = [
    "_build_activity_distribuicao",
    "_build_wmp_policy",
    "_check_pool_violations",
    "_check_wmp_desmob",
    "_check_wmp_pool",
    "_compute_activity_n_max",
    "_convert_schedule_to_distribuicao",
    "_cpv_build_usage",
    "_cpv_get_equip_needed",
    "_cpv_process_violations",
    "_process_single_wmp_policy",
    "_resolve_cpu_for_item",
    "_resolve_item_for_scheduled_activity",
    "_run_auto_schedule_fallback_chain",
    "_run_wmp_simulation",
    "_warn_if_activity_underdelivers",
]
