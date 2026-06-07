"""ADR-091: Pool mínimo como variável de otimização.

O ``resource_pool`` (quantidade de cada tipo de recurso disponível) deixa de ser
uma entrada do usuário e passa a ser *derivado* do próprio problema de
planejamento. A única entrada de negócio é o objetivo:

    pool_config = {
        "objetivo": "minimizar_prazo" | "minimizar_custo" | "balanceado",
        "prazo_maximo_semanas": int | None,
        "restricoes_mercado": {tipo_recurso: N_max},   # opcional
    }

Estratégia de derivação
------------------------
1. ``peak_demand_r`` — pico de demanda concorrente quando o RCPSP roda **sem
   restrição de pool** (recursos ilimitados). É o pool que permite o menor
   makespan possível.
2. ``serial_min_r`` — ``max_i(e_{i,r})``: o suficiente para a atividade mais
   exigente isoladamente. Força execução quase-serial → pool mínimo, maior prazo.

Mapeamento objetivo → pool:
  - ``minimizar_prazo``  → ``peak_demand`` (paralelismo máximo)
  - ``minimizar_custo``  → ``serial_min``  (pool mínimo)
  - ``balanceado``       → menor pool (via bisseção entre os dois extremos) que
    ainda respeita ``prazo_maximo_semanas``. Sem prazo informado, recai em
    ``peak_demand`` (entrega factível e rápida).

Restrições de mercado, quando fornecidas, limitam o pool de cada recurso; se o
teto de mercado for inferior ao ``serial_min`` daquele recurso, o projeto é
inviável e isso é sinalizado em ``notas``.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .models import Activity, ActivityDAG, ResourcePool, ScheduleError
from .scheduler import SerialScheduler

_PRIORITY_RULE = "MINSLK"
_BISECT_ITERS = 12


def _serial_min(activities: list[Activity]) -> dict[str, int]:
    """``max_i(e_{i,r})`` — pool mínimo para viabilizar a atividade mais exigente."""
    smin: dict[str, int] = {}
    for a in activities:
        for r, q in a.required_resources.items():
            smin[r] = max(smin.get(r, 0), int(q))
    return smin


def _unlimited_pool(activities: list[Activity]) -> ResourcePool:
    """Pool com capacidade suficiente para paralelismo total (Σ demanda por recurso)."""
    cap: dict[str, int] = {}
    for a in activities:
        for r, q in a.required_resources.items():
            cap[r] = cap.get(r, 0) + int(q)
    return ResourcePool(resources={r: max(1, c) for r, c in cap.items()})


def _safe_horizon(activities: list[Activity]) -> int:
    """Horizonte garantidamente factível (execução totalmente serial)."""
    return sum(max(1, a.duration_weeks) for a in activities) + 1


def _peak_demand(scheduled: Any, resources: Iterable[str]) -> dict[str, int]:
    """Pico de uso concorrente por recurso ao longo do schedule (modelo flat)."""
    peak = {r: 0 for r in resources}
    acts = scheduled.scheduled_activities
    if not acts:
        return peak
    horizon = max(a.end_week for a in acts)
    for w in range(horizon + 1):
        usage = scheduled.get_weekly_resource_usage(w)
        for r, q in usage.items():
            if q > peak.get(r, 0):
                peak[r] = q
    return peak


def _makespan_with(activities: list[Activity], dag: ActivityDAG, pool: dict[str, int], horizon: int) -> int:
    """Makespan ao agendar com o pool dado. Retorna ``horizon+1`` se inviável."""
    try:
        sched = SerialScheduler(priority_rule=_PRIORITY_RULE).schedule(
            activities=activities,
            dag=dag,
            pool=ResourcePool(resources={k: max(1, int(v)) for k, v in pool.items()}),
            deadline_weeks=horizon,
        )
        return sched.makespan
    except ScheduleError:
        return horizon + 1


def _pool_at(serial: dict[str, int], peak: dict[str, int], alpha: float) -> dict[str, int]:
    """Interpolação por recurso entre ``serial_min`` (α=0) e ``peak_demand`` (α=1)."""
    return {r: int(round(serial[r] + alpha * (peak.get(r, serial[r]) - serial[r]))) for r in serial}


def _bisect_pool(
    activities: list[Activity],
    dag: ActivityDAG,
    serial: dict[str, int],
    peak: dict[str, int],
    prazo_max: int | None,
    horizon: int,
) -> dict[str, int]:
    """Menor pool (interpolado) cujo makespan ≤ ``prazo_max``.

    Sem prazo → ``peak`` (rápido e factível). Se nem ``peak`` cumpre o prazo,
    devolve ``peak`` (o melhor possível). Se ``serial`` já cumpre, devolve ``serial``.
    """
    if not prazo_max:
        return dict(peak)
    if _makespan_with(activities, dag, peak, horizon) > prazo_max:
        return dict(peak)
    if _makespan_with(activities, dag, serial, horizon) <= prazo_max:
        return dict(serial)
    lo, hi = 0.0, 1.0
    for _ in range(_BISECT_ITERS):
        mid = (lo + hi) / 2.0
        candidate = _pool_at(serial, peak, mid)
        if _makespan_with(activities, dag, candidate, horizon) <= prazo_max:
            hi = mid
        else:
            lo = mid
    return _pool_at(serial, peak, hi)


def inferir_pool_minimo(
    activities: list[Activity],
    dag: ActivityDAG,
    pool_config: dict[str, Any] | None = None,
    deadline_weeks: int | None = None,
    restricoes_mercado: dict[str, int] | None = None,
) -> tuple[dict[str, int], dict[str, Any]]:
    """Deriva o pool mínimo de recursos para o objetivo de negócio escolhido.

    Returns:
        (pool, diagnostico). ``diagnostico`` traz peak_demand, serial_min,
        makespan mínimo e notas — material para exibir o tradeoff tempo×custo.
    """
    pool_config = pool_config or {}
    objetivo = str(pool_config.get("objetivo") or "balanceado").strip().lower()
    prazo_max = pool_config.get("prazo_maximo_semanas") or deadline_weeks
    restricoes = dict(restricoes_mercado or pool_config.get("restricoes_mercado") or {})

    serial = _serial_min(activities)
    resources = list(serial.keys())
    horizon = _safe_horizon(activities)

    makespan_min = horizon
    peak = dict(serial)
    if resources:
        try:
            sched_unl = SerialScheduler(priority_rule=_PRIORITY_RULE).schedule(
                activities=activities,
                dag=dag,
                pool=_unlimited_pool(activities),
                deadline_weeks=horizon,
            )
            peak = _peak_demand(sched_unl, resources)
            makespan_min = sched_unl.makespan
        except ScheduleError:
            peak = dict(serial)

    if objetivo == "minimizar_prazo":
        pool = dict(peak)
    elif objetivo == "minimizar_custo":
        pool = dict(serial)
    else:  # balanceado (default)
        pool = _bisect_pool(activities, dag, serial, peak, prazo_max, horizon)

    notas: list[str] = []
    for r, cap in restricoes.items():
        if r in pool and pool[r] > int(cap):
            pool[r] = int(cap)
            notas.append(f"{r}: limitado a {int(cap)} unidades por restrição de mercado")
        if r in serial and int(cap) < serial[r]:
            notas.append(
                f"{r}: ATENÇÃO — teto de mercado {int(cap)} < mínimo viável {serial[r]} "
                "(projeto inviável sob essa restrição)"
            )

    pool = {r: max(1, int(q)) for r, q in pool.items()}

    makespan_escolhido = _makespan_with(activities, dag, pool, horizon) if resources else 0
    diagnostico: dict[str, Any] = {
        "objetivo": objetivo,
        "peak_demand": dict(peak),
        "serial_min": dict(serial),
        "pool_inferido": dict(pool),
        "makespan_minimo_semanas": int(makespan_min),
        "makespan_estimado_semanas": int(makespan_escolhido),
        "prazo_maximo_semanas": int(prazo_max) if prazo_max else None,
        "notas": notas,
    }
    return pool, diagnostico


def _activities_from_spec(spec: dict[str, Any], derived_req: dict[str, dict[str, int]] | None = None) -> list[Activity]:
    """Constrói ``Activity`` a partir de ``rcpsp_spec['activities']`` (dimensão de pool).

    ADR-091 Fase 1: quando uma atividade não traz ``required_resources`` explícito,
    usa o ``e_{i,r}`` derivado das equipes (``derived_req``), se disponível.
    """
    derived_req = derived_req or {}
    acts: list[Activity] = []
    for a in spec.get("activities", []) or []:
        if not isinstance(a, dict):
            continue
        item_id = a.get("item_id")
        if not item_id:
            continue
        dur = max(1, int(a.get("duration_weeks") or 1))
        req = a.get("required_resources")
        if not isinstance(req, dict) or not req:
            req = derived_req.get(str(item_id), {})
        acts.append(
            Activity(
                activity_id=str(item_id),
                description=str(a.get("descricao") or item_id),
                duration_weeks=dur,
                required_resources={str(k): int(v) for k, v in req.items()},
            )
        )
    return acts


def _dag_from_spec(spec: dict[str, Any], activities: list[Activity]) -> ActivityDAG:
    """DAG de precedência a partir de ``rcpsp_spec['precedence']`` (suporta threshold)."""
    valid_ids = {a.activity_id for a in activities}
    precedence: list[tuple[str, str]] = []
    thresholds: dict[tuple[str, str], float] = {}
    for edge in spec.get("precedence", []) or []:
        if not isinstance(edge, (list, tuple)) or len(edge) < 2:
            continue
        pred, succ = str(edge[0]), str(edge[1])
        if pred not in valid_ids or succ not in valid_ids:
            continue
        precedence.append((pred, succ))
        if len(edge) >= 3:
            try:
                thresholds[(pred, succ)] = float(edge[2])
            except (TypeError, ValueError):
                pass
    return ActivityDAG(activities=activities, precedence=precedence, thresholds=thresholds)


# ── ADR-091 Fase 1: mapeamento equip_id → tipo_recurso e derivação de e_{i,r} ──


def tipo_recurso_de_equip(equip_id: str, equip_tipo_map: dict[str, str] | None = None) -> str:
    """Resolve o tipo de recurso (pool) de um ``equip_id``.

    Prioriza um mapa explícito do catálogo; na ausência, usa a convenção
    ``EQUIP-{equip_id}`` (mesma adotada por ``_di_collect_max_equipe`` e pelos
    contratos de pool). Centralizar aqui evita divergência entre derivação de
    requisitos e construção de contratos.
    """
    if equip_tipo_map and equip_id in equip_tipo_map:
        return equip_tipo_map[equip_id]
    return f"EQUIP-{equip_id}"


def validar_equipamentos_mapeaveis(equipes: list[Any], equip_tipo_map: dict[str, str] | None) -> list[str]:
    """Retorna os ``equip_id`` sem mapeamento explícito no catálogo (DoD Fase 1).

    Lista vazia ⇒ toda EquipeDireta tem todos equipamentos mapeáveis. Quando
    ``equip_tipo_map`` é ``None`` a validação é desligada (convenção implícita).
    """
    if equip_tipo_map is None:
        return []
    faltantes: set[str] = set()
    for eq in equipes:
        for equip in getattr(eq, "equipamentos", []) or []:
            eid = getattr(equip, "equip_id", "") or ""
            if eid and eid not in equip_tipo_map:
                faltantes.add(eid)
    return sorted(faltantes)


def derivar_required_resources(
    equipes: list[Any], equip_tipo_map: dict[str, str] | None = None
) -> tuple[dict[str, dict[str, int]], list[str]]:
    """Deriva ``{item_id: {tipo_r: e_{i,r}}}`` a partir de ``EquipeDireta.equipamentos``.

    ADR-091 D4: ``e_{i,r} = num_equipes_base × Σ num_unidades`` dos equipamentos do
    item ``i`` que mapeiam para o tipo ``r`` — a demanda concorrente real da
    atividade. Retorna também avisos para equip_ids resolvidos por convenção
    (sem mapeamento explícito).
    """
    required: dict[str, dict[str, int]] = {}
    avisos: list[str] = []
    for eq in equipes:
        item_id = getattr(eq, "item_id", "") or ""
        if not item_id:
            continue
        n_equipes = max(1, int(getattr(eq, "num_equipes_base", 1) or 1))
        bucket = required.setdefault(item_id, {})
        for equip in getattr(eq, "equipamentos", []) or []:
            eid = getattr(equip, "equip_id", "") or ""
            n_unid = int(getattr(equip, "num_unidades", 0) or 0)
            if not eid or n_unid <= 0:
                continue
            tipo = tipo_recurso_de_equip(eid, equip_tipo_map)
            if equip_tipo_map is not None and eid not in equip_tipo_map:
                avisos.append(f"equip_id '{eid}' sem mapeamento explícito; convenção '{tipo}'")
            bucket[tipo] = bucket.get(tipo, 0) + n_unid * n_equipes
    return required, avisos


def inferir_pool_minimo_from_spec(
    spec: dict[str, Any],
    equipes: list[Any] | None = None,
    equip_tipo_map: dict[str, str] | None = None,
) -> tuple[dict[str, int], dict[str, Any]]:
    """Wrapper que extrai atividades/DAG/objetivo de um ``rcpsp_spec`` e infere o pool.

    Ponto de entrada usado por skill-04 (consumidor primário do pool) e por
    skill-05 (fallback idempotente). Idempotente: chamar várias vezes com a mesma
    spec produz o mesmo pool.

    ADR-091 Fase 1: quando ``equipes`` é fornecido, ``e_{i,r}`` é derivado de
    ``EquipeDireta.equipamentos`` para atividades sem ``required_resources`` na spec.
    """
    derived_req: dict[str, dict[str, int]] = {}
    if equipes:
        derived_req, _avisos = derivar_required_resources(equipes, equip_tipo_map)
    activities = _activities_from_spec(spec, derived_req)
    if not activities:
        return {}, {"objetivo": "n/a", "notas": ["sem atividades para inferir pool"]}
    dag = _dag_from_spec(spec, activities)
    pool_config = spec.get("pool_config") if isinstance(spec.get("pool_config"), dict) else {}
    deadline = spec.get("deadline_weeks")
    return inferir_pool_minimo(
        activities=activities,
        dag=dag,
        pool_config=pool_config,
        deadline_weeks=int(deadline) if deadline else None,
    )
