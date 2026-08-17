"""Skill 05 — Equipes e Alocação (helpers A, parte extraída de _skill_helpers_a.py)."""

from __future__ import annotations

from concilium.domain.models.canonical import (
    CadeiaPerpetuacao,
    CustoParticionadoItem,
)

try:
    from eule import euler as _euler
    from interval_sets import Interval, IntervalSet

    _EULE_AVAILABLE = True
except ImportError:
    _EULE_AVAILABLE = False



def _iter_intervals(obj) -> list:
    """Normaliza Interval | IntervalSet para lista de Interval — ADR-084 D2."""
    if not _EULE_AVAILABLE:
        return []
    if isinstance(obj, IntervalSet):
        return [] if obj.is_empty() else list(obj)
    try:
        return [] if obj.is_empty() else [obj]
    except Exception:
        return []


def _sucessor_critico_id(gap_end: float, atividades_sorted: list[dict]) -> str | None:
    """Primeira atividade que inicia em ou após gap_end — ADR-084 D2."""
    for a in atividades_sorted:
        if a["T_start"] >= gap_end - 1e-9:
            return a["item_id"]
    return None


def _init_item_float_maps(items_com_janela: list, *keys) -> tuple:
    """Returns N dicts {item_id: 0.0} — one per key."""
    return tuple({it["item_id"]: 0.0 for it in items_com_janela} for _ in keys)


def _impute_euler_regions(diagram, items_com_janela, c_unit_semana: float, qt: int) -> tuple:
    """Pass 1: produtivas. Returns (phi, custo_excl, custo_comp, overlap_sem)."""
    phi, custo_excl, custo_comp, overlap_sem = _init_item_float_maps(items_com_janela, 1, 2, 3, 4)
    for ids_ativas, region in diagram.items():
        duracao = region.measure()
        custo = duracao * c_unit_semana * qt
        n_ativas = len(ids_ativas)
        for aid in ids_ativas:
            if aid not in phi:
                continue
            parcela = custo / n_ativas
            phi[aid] += parcela
            if n_ativas == 1:
                custo_excl[aid] += parcela
            else:
                custo_comp[aid] += parcela
                overlap_sem[aid] += duracao
    return phi, custo_excl, custo_comp, overlap_sem


def _impute_mob_demob(cadeias, items_com_janela, phi: dict, c_mob: float, c_demob: float, qt: int) -> tuple:
    """Pass 2: mob/demob Shapley. Returns (mob_imputado, demob_imputado)."""
    item_to_cadeia = {}
    for cadeia in cadeias:
        for iid in cadeia.item_ids:
            item_to_cadeia[iid] = cadeia
    mob_imputado = {}
    demob_imputado = {}
    for it in items_com_janela:
        iid = it["item_id"]
        cadeia = item_to_cadeia.get(iid)
        n_members = len(cadeia.item_ids) if cadeia else 1
        mob_imputado[iid] = round(c_mob * qt / n_members, 2) if n_members > 0 else 0.0
        demob_imputado[iid] = round(c_demob * qt / n_members, 2) if n_members > 0 else 0.0
        phi[iid] += mob_imputado[iid] + demob_imputado[iid]
    return mob_imputado, demob_imputado


def _impute_gaps(
    diagram, items_com_janela, phi: dict, c_unit_semana: float, qt: int, T_contrato_start: float, T_contrato_end: float
) -> dict:
    """Pass 3: gap imputation to critical successor. Returns custo_ocioso (dict keyed by item_id)."""
    all_ivs = [iv for _, region in diagram.items() for iv in region]
    uniao_produtiva = IntervalSet(all_ivs) if all_ivs else IntervalSet([])
    janela = IntervalSet([Interval(T_contrato_start, T_contrato_end)])
    gaps_obj = janela - uniao_produtiva
    custo_ocioso = {it["item_id"]: 0.0 for it in items_com_janela}
    items_sorted = sorted(items_com_janela, key=lambda x: x["T_start"])
    for gap_iv in _iter_intervals(gaps_obj):
        critico_id = _sucessor_critico_id(gap_iv.end, items_sorted)
        if critico_id and critico_id in phi:
            custo_gap = gap_iv.length() * c_unit_semana * qt
            phi[critico_id] += custo_gap
            custo_ocioso[critico_id] += custo_gap
    return custo_ocioso


def _build_predecessor_map(items_com_janela: list, cadeias: list) -> dict:
    """Returns {item_id: predecessor_id or None} from cadeias."""
    predecessor_map: dict[str, str | None] = {it["item_id"]: None for it in items_com_janela}
    for cadeia in cadeias:
        for k, iid in enumerate(cadeia.item_ids):
            if k > 0:
                predecessor_map[iid] = cadeia.item_ids[k - 1]
    return predecessor_map


def particionar_contrato(
    items_com_janela: list[dict],
    c_mob: float,
    c_demob: float,
    c_unit_semana: float,
    quantidade_contratada: int,
    T_contrato_start: float,
    T_contrato_end: float,
    atribuicao: dict[str, tuple[float, str, float]],
    cadeias: list[CadeiaPerpetuacao],
) -> list[CustoParticionadoItem]:
    """Partição exata de custo por atividade via diagrama de Euler — ADR-084 D2.

    Usa eule[interval] para computar regiões produtivas (exclusivas e de sobreposição)
    e complemento para identificar gaps causalmente imputados ao sucessor crítico.

    Invariante: Σ custo_total_particionado == C_contrato_total  (via atribuicao ADR-071 D3).
    Mob/demob (custo_mob_imputado) é custo separado — não entra em custo_total_particionado
    mas é exposto por item para diagnóstico (campo custo_mob_imputado).

    Três fontes de custo atribuídas por atividade (ADR-084):
      1. Produtivo exclusivo  — custo em regiões onde só esta atividade está ativa
      2. Produtivo compartilhado (overlap) — custo em regiões de sobreposição com outra atividade,
           dividido igualmente (Shapley simétrico) entre os participantes da região
      3. Ocioso (gap) — custo imputado ao sucessor crítico pelos períodos de gap causados pela
           predecessão na DAG

    Parâmetros
    ----------
    items_com_janela   : lista de dicts com item_id, T_start, T_end, machine_weeks, required
    c_mob, c_demob     : custo de mobilização/desmobilização do contrato
    c_unit_semana      : custo unitário por máquina-semana
    quantidade_contratada : pool_size (número de unidades do recurso)
    T_contrato_start   : início do contrato em índice de semana
    T_contrato_end     : fim do contrato em índice de semana
    atribuicao         : {item_id: (custo_total, tipo, machine_weeks)} — ADR-071 D3
    cadeias            : cadeias de perpetuação para calcular predecessor_critico_id
    """
    qt = quantidade_contratada
    n = len(items_com_janela)
    if n == 0:
        return []

    # Predecessor por item (da cadeia de perpetuação)
    predecessor_map = _build_predecessor_map(items_com_janela, cadeias)

    # Se eule não disponível, delega ao caminho Fase 2
    if not _EULE_AVAILABLE:
        return _compute_particao_por_tipo(
            items=items_com_janela,
            cadeias=cadeias,
            atribuicao=atribuicao,
            custo_unit_semanal=c_unit_semana,
            quantidade_contratada=qt,
            c_mob=c_mob,
            c_demob=c_demob,
        )

    # Construir IntervalSet por atividade
    sets = {
        it["item_id"]: IntervalSet([Interval(it["T_start"], it["T_end"])])
        for it in items_com_janela
        if it["T_end"] > it["T_start"]
    }
    if not sets:
        return _compute_particao_por_tipo(
            items=items_com_janela,
            cadeias=cadeias,
            atribuicao=atribuicao,
            custo_unit_semanal=c_unit_semana,
            quantidade_contratada=qt,
            c_mob=c_mob,
            c_demob=c_demob,
        )

    # eule's public `euler()` stub types `SetsType` as `list|dict[..., list|set]`, but its
    # `adapt_sets()` registry (eule/adaptation.py) explicitly documents and supports custom
    # SetLike types like IntervalSet passed directly — the stub just doesn't reflect that.
    diagram = _euler(sets)  # ty: ignore[invalid-argument-type]

    phi, custo_excl, custo_comp, overlap_sem = _impute_euler_regions(diagram, items_com_janela, c_unit_semana, qt)
    mob_imputado, demob_imputado = _impute_mob_demob(cadeias, items_com_janela, phi, c_mob, c_demob, qt)
    custo_ocioso = _impute_gaps(diagram, items_com_janela, phi, c_unit_semana, qt, T_contrato_start, T_contrato_end)

    # 4. Montar CustoParticionadoItem
    result = [
        _build_particionado_item(
            it,
            it["item_id"],
            custo_excl,
            custo_comp,
            mob_imputado,
            demob_imputado,
            custo_ocioso,
            atribuicao,
            predecessor_map,
            overlap_sem,
            c_mob,
            c_demob,
            c_unit_semana,
            qt,
        )
        for it in items_com_janela
    ]

    return result


def _build_particionado_item(
    it: dict,
    iid: str,
    custo_excl: dict,
    custo_comp: dict,
    mob_imputado: dict,
    demob_imputado: dict,
    custo_ocioso: dict,
    atribuicao: dict,
    predecessor_map: dict,
    overlap_sem: dict,
    c_mob: float,
    c_demob: float,
    c_unit_semana: float,
    qt: int,
) -> CustoParticionadoItem:
    """Builds one CustoParticionadoItem from partitioned cost dicts."""
    required_i = it.get("required", qt)
    custo_autonomo = round(
        (it["T_end"] - it["T_start"]) * c_unit_semana * required_i + (c_mob + c_demob) * required_i, 2
    )
    mob_standalone = round((c_mob + c_demob) * required_i, 2)
    mob_imputado_i = round(mob_imputado[iid] + demob_imputado[iid], 2)
    economia_mob_i = round(max(0.0, mob_standalone - mob_imputado_i), 2)
    oci = round(custo_ocioso[iid], 2)
    # Autoridade financeira: proporcional a machine-weeks (ADR-071 D3).
    custo_total = round(atribuicao.get(iid, (0.0, "", 0.0))[0], 2)
    # economia_vs_autonomo: standalone (envelope+mob) vs pool (atribuicao+mob Shapley) — bases compatíveis.
    economia_vs_autonomo = round(custo_autonomo - (custo_total + mob_imputado_i), 2)
    return CustoParticionadoItem(
        item_id=iid,
        custo_produtivo=round(custo_excl[iid] + custo_comp[iid], 2),
        custo_mob_imputado=mob_imputado_i,
        custo_ocioso_imputado=oci,
        custo_total_particionado=custo_total,
        economia_mob=economia_mob_i,
        overhead_ocioso=oci,
        custo_produtivo_exclusivo=round(custo_excl[iid], 2),
        custo_produtivo_compartilhado=round(custo_comp[iid], 2),
        custo_demob_imputado=demob_imputado[iid],
        custo_total_autonomo=custo_autonomo,
        economia_vs_autonomo=economia_vs_autonomo,
        predecessor_critico_id=predecessor_map.get(iid),
        overlap_semanas=round(overlap_sem[iid], 4),
    )


def _compute_ocioso_para_item(iid: str, cadeia, item_by_id: dict, custo_unit_semanal: float, qt: int) -> float:
    """Computes idle gap cost for iid as successor in cadeia."""
    if cadeia is None:
        return 0.0
    chain_sorted = sorted(
        [item_by_id[x] for x in cadeia.item_ids if x in item_by_id], key=lambda x: (x["start_idx"], x["end_idx"])
    )
    total = 0.0
    for k, chain_it in enumerate(chain_sorted):
        if chain_it["item_id"] == iid and k > 0:
            prev = chain_sorted[k - 1]
            gap_weeks = max(0, chain_it["start_idx"] - prev["end_idx"])
            total += custo_unit_semanal * qt * gap_weeks
    return round(total, 2)


def _compute_particao_por_tipo(
    items: list[dict],
    cadeias: list[CadeiaPerpetuacao],
    atribuicao: dict[str, tuple[float, str, float]],
    custo_unit_semanal: float,
    quantidade_contratada: int,
    c_mob: float,
    c_demob: float,
) -> list[CustoParticionadoItem]:
    """Computa CustoParticionadoItem para cada item do tipo — ADR-083.

    Cada item recebe:
    - custo_produtivo: machine_weeks × custo_unit (custo de tempo produtivo direto)
    - custo_mob_imputado: Shapley igualitário do mob/demob da cadeia de perpetuação
    - custo_ocioso_imputado: custo do idle gap antes deste item (causalidade do sucessor)
    - custo_total_particionado: = custo_atribuido_i (ADR-071 D3 — autoridade de faturamento)
    - economia_mob: mob_standalone − mob_imputado (>0 quando pool economiza mob/demob)
    - overhead_ocioso: = custo_ocioso_imputado (custo de gap atribuído causalmente)

    Invariante: Σ custo_total_particionado = custo_total_contrato (via ADR-071 D3).
    """
    item_by_id = {it["item_id"]: it for it in items}
    qt = quantidade_contratada

    # Build item_id → chain lookup
    item_to_cadeia: dict[str, CadeiaPerpetuacao] = {}
    for cadeia in cadeias:
        for iid in cadeia.item_ids:
            item_to_cadeia[iid] = cadeia

    result: list[CustoParticionadoItem] = []

    for it in items:
        iid = it["item_id"]
        machine_weeks_i = it["machine_weeks"]
        required_i = it["required"]

        # Custo produtivo: tempo produtivo ao custo unitário do contrato
        custo_produtivo = round(custo_unit_semanal * machine_weeks_i, 2)

        # Mob/demob: Shapley igualitário dentro da cadeia
        cadeia = item_to_cadeia.get(iid)
        n_members = len(cadeia.item_ids) if cadeia else 1
        mob_chain_total = (c_mob + c_demob) * qt
        custo_mob_imputado = round(mob_chain_total / n_members, 2) if n_members > 0 else 0.0

        # Economia de mob vs. standalone (item teria pago c_mob+c_demob sozinho)
        mob_standalone = round((c_mob + c_demob) * required_i, 2)
        economia_mob = round(max(0.0, mob_standalone - custo_mob_imputado), 2)

        custo_ocioso_imputado = _compute_ocioso_para_item(iid, cadeia, item_by_id, custo_unit_semanal, qt)

        # custo_total_particionado = atribuição autoritativa (ADR-071 D3)
        custo_total_particionado = round(atribuicao.get(iid, (0.0, "", 0.0))[0], 2)

        # Baseline autônomo: custo se o item contratasse o recurso sozinho.
        # Mesma fórmula do caminho Euler (particionar_contrato) — garante que
        # gap_pool_overhead e economia_vs_autonomo sejam corretos mesmo sem eule.
        custo_autonomo = round(
            (it.get("T_end", 0.0) - it.get("T_start", 0.0)) * custo_unit_semanal * required_i
            + (c_mob + c_demob) * required_i,
            2,
        )

        result.append(
            CustoParticionadoItem(
                item_id=iid,
                custo_produtivo=custo_produtivo,
                custo_mob_imputado=custo_mob_imputado,
                custo_ocioso_imputado=custo_ocioso_imputado,
                custo_total_particionado=custo_total_particionado,
                economia_mob=economia_mob,
                overhead_ocioso=custo_ocioso_imputado,
                # Fase 3 — disponível mesmo no fallback sem eule (ADR-083/089 §historical-fix)
                # custo_produtivo_exclusivo = produtivo puro (sem sobreposição no fallback)
                custo_produtivo_exclusivo=custo_produtivo,
                custo_produtivo_compartilhado=0.0,
                custo_demob_imputado=round(custo_mob_imputado / 2, 2),  # 50/50 Shapley
                custo_total_autonomo=custo_autonomo,
                economia_vs_autonomo=round(custo_autonomo - custo_total_particionado, 2),
            )
        )

    return result


