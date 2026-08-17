"""ADR-128 D2 — Restrição de disponibilidade de recursos consumíveis no motor RCPSP.

Projeta o nível de estoque de um ``ReplenishableResource`` semana a semana ao longo de um
cronograma proposto e, quando o estoque projetado ficar negativo, aplica um atraso à
atividade consumidora até que o reabastecimento acumulado torne o consumo viável —
análogo ao tratamento de recurso reutilizável indisponível (`ResourcePool`), mas com
contabilidade de fluxo em vez de contagem de unidades (ADR-128 §D2).

Limitação conhecida (documentada honestamente na ADR): o reparo por atraso desta primeira
fase desloca apenas a(s) atividade(s) que consomem o recurso, sem repropagar o atraso para
sucessores no DAG de precedências. Cronogramas onde a atividade atrasada tem sucessores
dependentes exigem uma segunda passada de resolução de precedências (fora do escopo desta
fase — ver ADR-128 Fase 2, nota "escopo amplo").
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence

from concilium.application.scheduling.models import ReplenishableResource, ScheduledActivity
from concilium.domain.models.catalog.disponibilidade_consumivel import DisponibilidadeConsumivel
from concilium.domain.models.project.constraint_violation import ConstraintViolation
from concilium.domain.validations.catalog import ValidationCode, make_violation

_MAX_DELAY_ITERATIONS = 500


def _taxa_por_semana(taxas: dict[str, float], scheduled: list[ScheduledActivity]) -> dict[int, float]:
    """Soma as taxas (consumo ou produção) das atividades ativas em cada semana."""
    por_t: dict[int, float] = defaultdict(float)
    for sa in scheduled:
        taxa = taxas.get(sa.activity_id)
        if not taxa:
            continue
        for t in range(sa.start_week, sa.end_week):
            por_t[t] += taxa
    return por_t


def _project_raw(
    disp: DisponibilidadeConsumivel, max_week: int, consumo_por_t: dict[int, float], producao_por_t: dict[int, float],
    *, deficit_at: int | None = None,
) -> tuple[dict[int, float], dict[int, float]]:
    """Passada única de projeção, com injeção opcional do déficit numa semana fixa."""
    taxa_max = disp.taxa_reabastecimento_max or 0.0
    cap = disp.capacidade_armazenamento
    niveis: dict[int, float] = {}
    overflow: dict[int, float] = {}
    estoque = disp.estoque_inicial
    for t in range(max_week):
        estoque = estoque + taxa_max + producao_por_t.get(t, 0.0)
        if cap is not None and estoque > cap:
            # Excedente sobre a pilha/tanque é descartado (VAL-ESTOQUE-CAP-01, AVISO) —
            # decisão econômica (bota-fora), não motivo de reparo de cronograma (ADR-139 D4).
            overflow[t] = estoque - cap
            estoque = cap
        estoque -= consumo_por_t.get(t, 0.0)
        if t == deficit_at:
            estoque += disp.deficit_provisionado_externamente
        niveis[t] = estoque
    return niveis, overflow


def _project(
    resource: ReplenishableResource, scheduled_activities: Iterable[ScheduledActivity]
) -> tuple[dict[int, float], dict[int, float]]:
    """Projeção semanal de (níveis de estoque, excedente descartado por capacidade)."""
    scheduled = list(scheduled_activities)
    if not scheduled:
        return {}, {}

    disp = resource.disponibilidade
    consumo_por_t = _taxa_por_semana(resource.consumo_por_semana, scheduled)
    producao_por_t = _taxa_por_semana(resource.producao_por_semana, scheduled)
    max_week = max(sa.end_week for sa in scheduled)

    niveis, overflow = _project_raw(disp, max_week, consumo_por_t, producao_por_t)
    if disp.deficit_provisionado_externamente > 0 and any(v < 0 for v in niveis.values()):
        # ADR-151: provisionamento externo conhecido, injetado just-in-time — não no
        # primeiro estoque negativo do recurso (que pode ser um déficit transitório
        # que o mecanismo de atraso do ADR-128 já resolveria sozinho), mas no início
        # do ÚLTIMO trecho contíguo de estoque negativo. Isso reserva o
        # provisionamento para o déficit estrutural genuíno mais tardio (ex.: uma
        # atividade consumidora sem produtora pareada) e deixa qualquer déficit
        # anterior, mais cedo e transitório, para o reparo por atraso resolver como
        # já fazia antes desta ADR — em vez de gastar o provisionamento no primeiro
        # estoque negativo encontrado, não necessariamente o que ele foi pensado
        # para cobrir. O "intervalo de conforto" é justamente não fixar a semana
        # exata de chegada, só garantir que chega a tempo do trecho final.
        neg_weeks = sorted(t for t, v in niveis.items() if v < 0)
        seg_start = neg_weeks[-1]
        for t in reversed(neg_weeks[:-1]):
            if t == seg_start - 1:
                seg_start = t
            else:
                break
        niveis, overflow = _project_raw(disp, max_week, consumo_por_t, producao_por_t, deficit_at=seg_start)
    return niveis, overflow


def project_estoque_semanal(
    resource: ReplenishableResource, scheduled_activities: Iterable[ScheduledActivity]
) -> dict[int, float]:
    """Projeta o balanço semanal de estoque (ADR-128 D2 + ADR-139 D4)::

        estoque[t] = estoque[t-1] + reabastecimento_externo[t] + producao_interna[t] - consumo[t]

    ``reabastecimento_externo[t]`` assume a taxa máxima declarada
    (``taxa_reabastecimento_max``, 0.0 quando não declarada) todo período.
    ``producao_interna[t]`` (ADR-139) é a soma de ``producao_por_semana`` das atividades
    produtoras ativas na semana ``t``; ``consumo[t]`` é o simétrico para
    ``consumo_por_semana`` (ativa: ``start_week <= t < end_week``). O estoque é limitado
    pela capacidade de armazenamento quando declarada — o excedente é descartado
    (ver ``project_overflow_semanal``).

    Retorna ``{}`` quando não há atividades agendadas (sem cronograma para projetar).
    """
    niveis, _ = _project(resource, scheduled_activities)
    return niveis


def project_overflow_semanal(
    resource: ReplenishableResource, scheduled_activities: Iterable[ScheduledActivity]
) -> dict[int, float]:
    """Excedente descartado por semana quando a projeção ultrapassa ``capacidade_armazenamento``.

    ADR-139 D4: para material de geração interna, ``capacidade_armazenamento`` modela a
    pilha/bota-espera limitada — produção acima dela é perdida (bota-fora), o que merece
    AVISO (``VAL-ESTOQUE-CAP-01``), nunca delay. Retorna ``{}`` sem capacidade declarada.
    """
    _, overflow = _project(resource, scheduled_activities)
    return overflow


def violation_estoque_acima_capacidade(
    resource: ReplenishableResource, scheduled_activities: Iterable[ScheduledActivity]
) -> ConstraintViolation | None:
    """``VAL-ESTOQUE-CAP-01`` (AVISO) quando a projeção descarta excedente; ``None`` caso contrário."""
    overflow = project_overflow_semanal(resource, scheduled_activities)
    if not overflow:
        return None
    return make_violation(
        ValidationCode.VAL_ESTOQUE_CAP_01,
        "AVISO",
        magnitude=round(sum(overflow.values()), 6),
        items=[f"{resource.resource_id}:semana-{t}" for t in sorted(overflow)],
        hint=(
            "Produção projetada excede capacidade_armazenamento — excedente descartado. "
            "Amplie a pilha/bota-espera, antecipe a consumidora ou reduza a taxa da produtora."
        ),
    )


def has_estoque_negativo(niveis: dict[int, float]) -> bool:
    """True se algum nível de estoque projetado for negativo (cronograma inviável)."""
    return any(v < 0 for v in niveis.values())


def custo_deficit_provisionado(disp: DisponibilidadeConsumivel) -> float:
    """Custo do déficit provisionado externamente (ADR-184: continuação da ADR-151 D4).

    ``deficit_provisionado_externamente × preco_provisionamento_externo``. Retorna
    ``0.0`` quando não há déficit ou quando o preço não foi declarado — mesmo
    comportamento (custo zero) de antes desta ADR, sem travar nada; a ausência de
    preço com déficit > 0 é reportada separadamente como aviso
    (``VAL-ESTOQUE-PROVISIONAMENTO-02``, ver ``_skill_helpers/_validacao.py``).
    """
    if disp.preco_provisionamento_externo is None:
        return 0.0
    return disp.deficit_provisionado_externamente * disp.preco_provisionamento_externo


def _find_delay_target(
    activities: Iterable[ScheduledActivity], resource: ReplenishableResource, t0: int
) -> ScheduledActivity | None:
    """Escolhe a candidata a atrasar: consome ``resource``, está ativa em ``t0`` e
    começa mais tarde entre as candidatas (heurística gulosa). ``None`` quando não há
    nenhuma atividade candidata (estoque inviável sem consumidora agendável)."""
    candidates = [
        sa
        for sa in activities
        if sa.start_week <= t0 < sa.end_week and resource.consumo_por_semana.get(sa.activity_id, 0.0)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda sa: sa.start_week)


def _is_delay_fixed_point(
    target: ScheduledActivity,
    offset: int,
    deficit: float,
    activity_anterior: str | None,
    offset_anterior: int | None,
    deficit_anterior: float | None,
) -> bool:
    """ADR-128 F5 (achado de performance): ponto fixo — mesma atividade, mesmo
    deslocamento relativo ao novo início e déficit que não progrediu desde a rodada
    anterior (ver nota completa em ``apply_replenishable_delay``)."""
    if deficit_anterior is None:
        return False
    return (
        target.activity_id == activity_anterior and offset == offset_anterior and deficit <= deficit_anterior
    )


def apply_replenishable_delay(
    scheduled_activities: Sequence[ScheduledActivity],
    resource: ReplenishableResource,
    delay_causes: dict[tuple[str, str], int] | None = None,
) -> list[ScheduledActivity]:
    """Atrasa, iterativamente, a atividade consumidora que gera o primeiro estoque negativo.

    Estratégia (ADR-128 §D2): a cada iteração, projeta o estoque; se algum ponto ficar
    negativo, identifica a primeira semana ``t0`` inviável e adia em uma semana a
    atividade que consome o recurso, está ativa em ``t0`` e começa mais tarde entre as
    candidatas (heurística gulosa — análoga a resolução de conflito em SGS de RCPSP).
    Repete até o estoque projetado ser não-negativo ou até ``_MAX_DELAY_ITERATIONS``.

    ADR-139 D4/A6: atividades produtoras (``producao_por_semana``) nunca são candidatas
    a delay — atrasar a produtora só reduz o estoque futuro, nunca o aumenta.

    ``delay_causes`` (ADR-128 F5), quando fornecido, acumula
    ``{(resource_id, activity_id): semanas_de_atraso}`` — permite ao chamador reportar
    causalmente qual recurso atrasou qual atividade, em vez de só um booleano "reparado".

    Não modifica as instâncias originais — retorna uma nova lista de ``ScheduledActivity``.
    """
    activities: dict[str, ScheduledActivity] = {
        sa.activity_id: ScheduledActivity(
            activity_id=sa.activity_id,
            start_week=sa.start_week,
            end_week=sa.end_week,
            duration_weeks=sa.duration_weeks,
            assigned_resources=dict(sa.assigned_resources),
            ramp_profile=sa.ramp_profile,
        )
        for sa in scheduled_activities
    }

    # ADR-128 F5 (achado de performance): sem reabastecimento suficiente (taxa máxima
    # zerada ou capacidade de armazenamento menor que o consumo semanal), a mesma
    # atividade é escolhida rodada após rodada e o déficit projetado no ponto de
    # violação — medido no MESMO deslocamento relativo ao novo início da atividade —
    # se repete indefinidamente: um ponto fixo que `_MAX_DELAY_ITERATIONS` (500) só
    # alcançaria depois de recomputar `_project` (custo O(semanas)) centenas de vezes.
    # Rastreia (atividade, deslocamento, déficit) da rodada anterior e interrompe assim
    # que o mesmo estado se repete sem melhora — nunca interrompe enquanto o
    # deslocamento ou o déficit ainda estiverem progredindo (ex.: reabastecimento
    # gradual acumulando estoque a cada semana adiada).
    activity_anterior: str | None = None
    offset_anterior: int | None = None
    deficit_anterior: float | None = None
    for _ in range(_MAX_DELAY_ITERATIONS):
        niveis = project_estoque_semanal(resource, activities.values())
        if not has_estoque_negativo(niveis):
            break
        t0 = min(t for t, v in niveis.items() if v < 0)
        target = _find_delay_target(activities.values(), resource, t0)
        if target is None:
            # Estoque inviável sem nenhuma atividade candidata a atrasar (ex.: déficit
            # já presente antes de qualquer consumo agendável) — não há reparo possível
            # nesta estratégia; interrompe sem lançar exceção, preservando o cronograma.
            break
        deficit = niveis[t0]
        offset = t0 - target.start_week
        if _is_delay_fixed_point(target, offset, deficit, activity_anterior, offset_anterior, deficit_anterior):
            break
        activity_anterior = target.activity_id
        offset_anterior = offset
        deficit_anterior = deficit
        target.start_week += 1
        target.end_week += 1
        if delay_causes is not None:
            key = (resource.resource_id, target.activity_id)
            delay_causes[key] = delay_causes.get(key, 0) + 1
    return list(activities.values())
