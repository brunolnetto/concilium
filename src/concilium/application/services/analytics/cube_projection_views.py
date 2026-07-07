"""Shared projection builders for analytical cube visualizations and API payloads."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Literal

FaceGranularity = Literal["semana", "mes", "bimestre", "trimestre", "semestre", "ano"]

FACE_UNIT_TYPES: dict[str, str] = {
    "tempo_natureza": "currency_brl",
    "tempo_componente": "currency_brl",
    "direto_temporal_categoria": "currency_brl",
    "indireto_temporal_categoria": "currency_brl",
    "categoria_componente": "currency_brl",
    "atividade_componente": "currency_brl",
    "diesel_temporal": "volume_liters",
    "abc_curva": "currency_brl",
    "s_curve_custo": "currency_brl",
    "recursos_ativos_tempo": "count",
}

# Componentes BDI de overhead e tributos — usados para agregação
_OVERHEAD_COMPONENTS = frozenset({"overhead_ac", "overhead_df", "overhead_r", "overhead_cr"})
_TRIBUTO_COMPONENTS = frozenset({"tributo_cofins", "tributo_iss", "tributo_pis", "tributo_cssl", "tributo_ir"})


def _normalize_bdi_component(component: str) -> str:
    """Normaliza componentes BDI para buckets de visualizacao estaveis."""
    if component in _OVERHEAD_COMPONENTS:
        return "Overhead BDI"
    if component in _TRIBUTO_COMPONENTS:
        return "Tributos"
    if component == "margem_l":
        return "Lucro (L)"
    if component in {"custo_direto", "custo_indireto"}:
        return "Custo operacional"
    return component


def _build_bdi_multipliers_from_cubo(cubo: Any) -> dict[str, float]:
    """Extrai multiplicadores implicitos de BDI a partir da composicao real do cubo.

    Os multiplicadores sao razoes sobre custo_operacional, mantendo o comportamento
    deterministico com base no proprio dataset do projeto.
    """
    totals: dict[str, float] = defaultdict(float)
    for celula in getattr(cubo, "celulas", None) or []:
        norm = _normalize_bdi_component(str(getattr(celula, "componente_bdi", "")))
        totals[norm] += float(getattr(celula, "valor_rs", 0.0) or 0.0)
    base = float(totals.get("Custo operacional", 0.0))
    if base <= 0.0:
        return {"Overhead BDI": 0.0, "Lucro (L)": 0.0, "Tributos": 0.0}
    return {
        "Overhead BDI": float(totals.get("Overhead BDI", 0.0)) / base,
        "Lucro (L)": float(totals.get("Lucro (L)", 0.0)) / base,
        "Tributos": float(totals.get("Tributos", 0.0)) / base,
    }


def _split_operational_cost_with_bdi(base_cost: float, multipliers: dict[str, float]) -> dict[str, float]:
    """Decompoe um custo operacional em custo+overhead+lucro+tributos."""
    base = float(base_cost or 0.0)
    return {
        "Custo operacional": base,
        "Overhead BDI": base * float(multipliers.get("Overhead BDI", 0.0)),
        "Lucro (L)": base * float(multipliers.get("Lucro (L)", 0.0)),
        "Tributos": base * float(multipliers.get("Tributos", 0.0)),
    }


def _build_pool_particao_by_item(canonical: Any) -> dict[str, float]:
    result: dict[str, float] = {}
    if not canonical:
        return result
    for contrato in getattr(canonical, "contratos_recurso", None) or []:
        for part in getattr(contrato, "particao_por_item", None) or []:
            item_id = str(getattr(part, "item_id", "") or "")
            if not item_id:
                continue
            result[item_id] = result.get(item_id, 0.0) + float(getattr(part, "custo_total_particionado", 0.0) or 0.0)
    return result


def _accumulate_direto_base_by_item(cubo: Any) -> dict[str, float]:
    """Soma valor_rs de custo_direto (exceto material) por atividade_id."""
    base_by_item: dict[str, float] = defaultdict(float)
    for celula in getattr(cubo, "celulas", None) or []:
        if str(getattr(celula, "componente_bdi", "")) != "custo_direto":
            continue
        if str(getattr(celula, "categoria", "")) == "material":
            continue
        item_id = str(getattr(celula, "atividade_id", "") or "")
        if not item_id:
            continue
        base_by_item[item_id] += float(getattr(celula, "valor_rs", 0.0) or 0.0)
    return base_by_item


def _build_pool_scaling_by_item(canonical: Any, cubo: Any) -> dict[str, float]:
    """Escala custos diretos por item para aderir ao custo particionado de pool.

    A escala é aplicada apenas para categorias pool-driven (mao_obra/equipamento/diesel),
    preservando material sem ajuste forçado por partição.
    """
    particao = _build_pool_particao_by_item(canonical)
    if not particao:
        return {}
    base_by_item = _accumulate_direto_base_by_item(cubo)
    scaling: dict[str, float] = {}
    for item_id, alvo in particao.items():
        base = float(base_by_item.get(item_id, 0.0))
        if base > 0.0 and alvo > 0.0:
            scaling[item_id] = alvo / base
    return scaling


def _iter_scaled_cubo_cells(canonical: Any, cubo: Any):
    """Itera células diretas do cubo aplicando escala de pool particionado por atividade.

    Filtra exclusivamente natureza='direto' — células indiretas (IND-*) têm seu
    próprio canal de leitura via _iter_indireto_cubo_cells.
    """
    scaling = _build_pool_scaling_by_item(canonical, cubo)
    for celula in getattr(cubo, "celulas", None) or []:
        if str(getattr(celula, "natureza", "direto") or "direto") != "direto":
            continue
        valor = float(getattr(celula, "valor_rs", 0.0) or 0.0)
        item_id = str(getattr(celula, "atividade_id", "") or "")
        categoria = str(getattr(celula, "categoria", "") or "")
        if categoria != "material":
            valor *= float(scaling.get(item_id, 1.0))
        yield celula, valor


def _iter_indireto_cubo_cells(cubo: Any):
    """Itera células indiretas (natureza='indireto') do cubo enriquecido."""
    for celula in getattr(cubo, "celulas", None) or []:
        if str(getattr(celula, "natureza", "") or "") == "indireto":
            yield celula, float(getattr(celula, "valor_rs", 0.0) or 0.0)


def _extract_cost_from_dict_entry(entry: dict[Any, Any]) -> float | None:
    """Extrai custo de um dict-entry, ou None se nenhum campo reconhecido estiver presente."""
    for key in ("custo_total", "custo_mensal_total", "custo_mensal", "valor", "custo"):
        if key in entry and isinstance(entry.get(key), (int, float)):
            return float(entry.get(key) or 0.0)
    qtd = float(entry.get("quantidade", 0.0) or 0.0)
    unit = float(entry.get("custo_unitario", 0.0) or 0.0)
    if qtd > 0.0 and unit > 0.0:
        return qtd * unit
    return None


def _extract_cost_from_entry(entry: Any) -> float:
    if isinstance(entry, dict):
        cost = _extract_cost_from_dict_entry(entry)
        if cost is not None:
            return cost
    return float(getattr(entry, "custo_total", 0.0) or 0.0)


def _indireto_list(ind: Any, attr: str) -> list[Any]:
    """Retorna a lista no atributo `attr` de um indireto, ou [] quando ausente/None."""
    return getattr(ind, attr, None) or []


def _mob_custo_total(mob: Any) -> float:
    return float(getattr(mob, "custo_total", 0.0) or 0.0)


def _decompose_indireto_costs(ind: Any) -> tuple[float, float, float]:
    """Decompoe um indireto em (mao_obra, equipamento, verbas), rebalanceados por custo_total."""
    mao = sum(_extract_cost_from_entry(x) for x in _indireto_list(ind, "funcoes"))
    eq = sum(_extract_cost_from_entry(x) for x in _indireto_list(ind, "equipamentos"))
    verbas = sum(_extract_cost_from_entry(x) for x in _indireto_list(ind, "verbas_mensais"))
    verbas += sum(_extract_cost_from_entry(x) for x in _indireto_list(ind, "verbas_fixas"))
    verbas += sum(_mob_custo_total(mob) for mob in _indireto_list(ind, "mobilizacoes"))
    sub = mao + eq + verbas
    custo_total = float(getattr(ind, "custo_total", 0.0) or 0.0)
    if sub > 0.0 and custo_total > 0.0:
        factor = custo_total / sub
        mao *= factor
        eq *= factor
        verbas *= factor
    elif custo_total > 0.0:
        verbas += custo_total
    return mao, eq, verbas


def _build_indireto_component_totals(canonical: Any) -> dict[str, float]:
    """Agrupa indiretos em mao_obra, equipamento e verbas."""
    totals = {"mao_obra": 0.0, "equipamento": 0.0, "verbas": 0.0}
    for ind in getattr(canonical, "indiretos", None) or []:
        mao, eq, verbas = _decompose_indireto_costs(ind)
        totals["mao_obra"] += mao
        totals["equipamento"] += eq
        totals["verbas"] += verbas
    return totals


def _indireto_component_shares(canonical: Any) -> dict[str, float]:
    totals = _build_indireto_component_totals(canonical)
    total = totals["mao_obra"] + totals["equipamento"] + totals["verbas"]
    if total <= 0.0:
        return {"mao_obra": 0.0, "equipamento": 0.0, "verbas": 1.0}
    return {k: float(v) / total for k, v in totals.items()}


def _custo_indireto_por_periodo(canonical: Any, granularidade: FaceGranularity) -> dict[str, float]:
    """Mapeia canonical.indiretos_semanal para buckets por granularidade.

    O campo IndiretoSemanal.semana é um índice (offset 0-based) na lista de semanas ISO
    ordenadas do cronograma. Aqui reconstruímos a lista de semanas para fazer o mapeamento.
    """
    acts = []
    cronograma = getattr(canonical, "cronograma", None)
    if cronograma:
        acts = getattr(cronograma, "scheduled_activities", None) or []
    if not acts:
        return {}
    semanas_set: set[str] = set()
    for act in acts:
        for wk in getattr(act, "distribuicao_semanal", None) or {}:
            semanas_set.add(wk)
    semanas_sorted = sorted(semanas_set)
    result: dict[str, float] = defaultdict(float)
    for ind in getattr(canonical, "indiretos_semanal", None) or []:
        offset = ind.semana
        if 0 <= offset < len(semanas_sorted):
            bucket = bucket_from_week_iso(semanas_sorted[offset], granularidade)
            result[bucket] += ind.custo_semanal
    return dict(result)


def _mob_eventos_por_periodo(canonical: Any, granularidade: FaceGranularity) -> dict[str, int]:
    """Conta eventos de mobilização/desmobilização por bucket temporal a partir das instâncias."""
    result: dict[str, int] = defaultdict(int)
    for inst in getattr(canonical, "instancias_recurso", None) or []:
        for key in ("semana_mobilizacao", "semana_desmobilizacao"):
            semana_iso = str(getattr(inst, key, "") or "")
            if not semana_iso:
                continue
            bucket = bucket_from_week_iso(semana_iso, granularidade)
            result[bucket] += 1
    return dict(result)


def bucket_from_week_iso(week_iso: str, granularidade: FaceGranularity) -> str:
    if granularidade == "semana":
        return week_iso
    year_str, week_str = week_iso.split("-W", 1)
    anchor = date.fromisocalendar(int(year_str), int(week_str), 1)
    if granularidade == "mes":
        return f"{anchor.year:04d}-{anchor.month:02d}"
    if granularidade == "bimestre":
        bimestre = ((anchor.month - 1) // 2) + 1
        return f"{anchor.year:04d}-B{bimestre}"
    if granularidade == "trimestre":
        trimestre = ((anchor.month - 1) // 3) + 1
        return f"{anchor.year:04d}-T{trimestre}"
    if granularidade == "semestre":
        semestre = ((anchor.month - 1) // 6) + 1
        return f"{anchor.year:04d}-S{semestre}"
    if granularidade == "ano":
        return f"{anchor.year:04d}"
    raise ValueError(f"Granularidade inválida: {granularidade}")


def _resolve_direto_temporal_categoria_rows(
    cubo: Any, canonical: Any, granularidade: FaceGranularity, top_n: int
) -> tuple[list[dict[str, Any]], list[dict[str, str]], str]:
    categories = ("MAO_OBRA", "EQUIP", "MAT", "COMB")
    cat_map = {
        "mao_obra": "MAO_OBRA",
        "equipamento": "EQUIP",
        "material": "MAT",
        "diesel": "COMB",
    }
    aggregated: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for celula, valor_cell in _iter_scaled_cubo_cells(canonical, cubo):
        comp = str(getattr(celula, "componente_bdi", "") or "")
        if comp != "custo_direto":
            continue
        cat_key = cat_map.get(str(getattr(celula, "categoria", "") or ""))
        if not cat_key:
            continue
        bucket = bucket_from_week_iso(str(getattr(celula, "semana_iso", "") or ""), granularidade)
        if bucket:
            aggregated[bucket][cat_key] += float(valor_cell)
    buckets = sorted(aggregated.keys())
    rows: list[dict[str, Any]] = []
    for bucket in buckets:
        for cat in categories:
            rows.append(
                {
                    "periodo": bucket,
                    "categoria_direto": cat,
                    "valor_rs": float(aggregated[bucket].get(cat, 0.0)),
                }
            )
    columns = [
        {"id": "periodo", "label": "Período", "dtype": "str", "role": "x"},
        {"id": "categoria_direto", "label": "Categoria Direta", "dtype": "str", "role": "series"},
        {"id": "valor_rs", "label": "Valor (R$)", "dtype": "float", "role": "value"},
    ]
    return rows[:top_n], columns, "bar_stacked"


def _indireto_categoria_from_atividade_id(aid: str) -> str:
    return aid.replace("IND-", "", 1).upper() if aid.startswith("IND-") else aid.upper()


def _accrue_indireto_temporal_cell(
    celula: Any,
    granularidade: FaceGranularity,
    categories: tuple[str, ...],
    aggregated: dict[str, dict[str, float]],
) -> None:
    nat = str(getattr(celula, "natureza", "") or "")
    comp = str(getattr(celula, "componente_bdi", "") or "")
    if nat != "indireto" or comp != "custo_direto":
        return
    cat = _indireto_categoria_from_atividade_id(str(getattr(celula, "atividade_id", "") or ""))
    if cat not in categories:
        return
    bucket = bucket_from_week_iso(str(getattr(celula, "semana_iso", "") or ""), granularidade)
    if bucket:
        aggregated[bucket][cat] += float(getattr(celula, "valor_rs", 0.0) or 0.0)


def _collect_indireto_temporal_cells(
    canonical: Any, granularidade: FaceGranularity, categories: tuple[str, ...]
) -> dict[str, dict[str, float]]:
    aggregated: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    cubo_obj = getattr(canonical, "cubo_analitico", None)
    cells = getattr(cubo_obj, "celulas", None) if cubo_obj is not None else None
    if cells:
        for celula in cells:
            _accrue_indireto_temporal_cell(celula, granularidade, categories, aggregated)
    return aggregated


def _rebalance_mob_by_eventos(
    aggregated: dict[str, dict[str, float]], canonical: Any, granularidade: FaceGranularity
) -> None:
    """Rebalanceia MOB por eventos reais do pool quando houver instâncias com
    mobilizações/desmobilizações intermediárias: evita falso sinal de concentração
    apenas no início/fim quando o indireto semanal veio agregado por driver de projeto.
    """
    if not canonical:
        return
    eventos_mob = _mob_eventos_por_periodo(canonical, granularidade)
    total_eventos = sum(eventos_mob.values())
    total_mob = sum(v.get("MOB", 0.0) for v in aggregated.values())
    if total_eventos > 0 and total_mob > 0.0 and len(eventos_mob) > 2:
        for b in list(aggregated.keys()):
            aggregated[b]["MOB"] = 0.0
        for bucket, n_evt in eventos_mob.items():
            aggregated[bucket]["MOB"] += total_mob * (float(n_evt) / float(total_eventos))


def _sum_indiretos_by_categoria(canonical: Any, categories: tuple[str, ...]) -> dict[str, float]:
    by_cat_total: dict[str, float] = {k: 0.0 for k in categories}
    for ind in getattr(canonical, "indiretos", None) or []:
        cat = str(getattr(ind, "categoria", "") or "").upper()
        if cat in by_cat_total:
            by_cat_total[cat] += float(getattr(ind, "custo_total", 0.0) or 0.0)
    return by_cat_total


def _category_shares_from_totals(by_cat_total: dict[str, float], categories: tuple[str, ...]) -> dict[str, float]:
    total_ind = sum(by_cat_total.values())
    if not by_cat_total:
        return {k: 1.0 / len(categories) for k in categories}
    return {k: (v / total_ind if total_ind > 0 else (1.0 / len(categories))) for k, v in by_cat_total.items()}


def _fallback_indireto_temporal_shares(
    aggregated: dict[str, dict[str, float]],
    canonical: Any,
    granularidade: FaceGranularity,
    categories: tuple[str, ...],
) -> None:
    """Fallback: se não houver células indiretas no cubo, distribui o indireto semanal
    por shares de categoria (ADM/TOP/LAB/QSMS/MOB) medidos em canonical.indiretos.
    """
    if aggregated or not canonical:
        return
    indireto_bucket = _custo_indireto_por_periodo(canonical, granularidade)
    by_cat_total = _sum_indiretos_by_categoria(canonical, categories)
    shares = _category_shares_from_totals(by_cat_total, categories)
    for bucket, total_bucket in indireto_bucket.items():
        for cat in categories:
            aggregated[bucket][cat] += float(total_bucket) * float(shares.get(cat, 0.0))


def _resolve_indireto_temporal_categoria_rows(
    canonical: Any, granularidade: FaceGranularity, top_n: int
) -> tuple[list[dict[str, Any]], list[dict[str, str]], str]:
    categories = ("ADM", "TOP", "LAB", "QSMS", "MOB")
    aggregated = _collect_indireto_temporal_cells(canonical, granularidade, categories)
    _rebalance_mob_by_eventos(aggregated, canonical, granularidade)
    _fallback_indireto_temporal_shares(aggregated, canonical, granularidade, categories)

    buckets = sorted(aggregated.keys())
    rows: list[dict[str, Any]] = []
    for bucket in buckets:
        for cat in categories:
            rows.append(
                {
                    "periodo": bucket,
                    "categoria_indireto": cat,
                    "valor_rs": float(aggregated[bucket].get(cat, 0.0)),
                }
            )
    columns = [
        {"id": "periodo", "label": "Período", "dtype": "str", "role": "x"},
        {"id": "categoria_indireto", "label": "Categoria Indireta", "dtype": "str", "role": "series"},
        {"id": "valor_rs", "label": "Valor (R$)", "dtype": "float", "role": "value"},
    ]
    return rows[:top_n], columns, "bar_stacked"


def _accrue_tempo_natureza_cell(
    c: Any,
    granularidade: FaceGranularity,
    direto_por_bucket: dict[str, float],
    indireto_por_bucket: dict[str, float],
) -> None:
    nat = str(getattr(c, "natureza", "") or "")
    comp = str(getattr(c, "componente_bdi", "") or "")
    val = float(getattr(c, "valor_rs", 0.0) or 0.0)
    bucket = bucket_from_week_iso(str(getattr(c, "semana_iso", "") or ""), granularidade)
    if not bucket:
        return
    if nat == "direto" and comp == "custo_direto":
        direto_por_bucket[bucket] += val
    elif nat == "indireto" and comp == "custo_direto":
        indireto_por_bucket[bucket] += val


def _accumulate_tempo_natureza_from_cubo(
    cubo_obj: Any, granularidade: FaceGranularity
) -> tuple[dict[str, float], dict[str, float]]:
    """Acumula custo direto/indireto por bucket a partir das células do cubo_analitico."""
    direto_por_bucket: dict[str, float] = defaultdict(float)
    indireto_por_bucket: dict[str, float] = defaultdict(float)
    for c in cubo_obj.celulas:
        _accrue_tempo_natureza_cell(c, granularidade, direto_por_bucket, indireto_por_bucket)
    return direto_por_bucket, indireto_por_bucket


def _accumulate_tempo_natureza_from_scurve(
    canonical: Any, granularidade: FaceGranularity
) -> tuple[dict[str, float], dict[str, float]]:
    """Fallback: acumula custo direto/indireto por bucket via SCurveBuilder quando cubo não está disponível."""
    from concilium.domain.services.analytics.s_curve_builder import SCurveBuilder

    direto_por_bucket: dict[str, float] = defaultdict(float)
    indireto_por_bucket: dict[str, float] = defaultdict(float)
    s_curve = SCurveBuilder().build(canonical)
    for agg in s_curve.agregacao_semanal:
        bucket = bucket_from_week_iso(str(agg.semana_iso), granularidade)
        direto_por_bucket[bucket] += float(agg.custo_direto_semana or 0.0)
        indireto_por_bucket[bucket] += float(agg.custo_indireto_semana or 0.0)
    return direto_por_bucket, indireto_por_bucket


def _resolve_tempo_natureza_rows(
    canonical: Any, granularidade: FaceGranularity, top_n: int
) -> tuple[list[dict[str, Any]], list[dict[str, str]], str]:
    # Usar cubo_analitico enriquecido (fonte primária analítica).
    # O cubo tem cells natureza='direto' (escalonadas ao PUxQ) e natureza='indireto'
    # adicionadas pelo enriquecimento financeiro do CuboAnaliticoBuilder.
    # Filtramos componente_bdi='custo_direto' para não somar os overlays de BDI.
    cubo_obj = getattr(canonical, "cubo_analitico", None)
    if cubo_obj is not None and getattr(cubo_obj, "celulas", None):
        direto_por_bucket, indireto_por_bucket = _accumulate_tempo_natureza_from_cubo(cubo_obj, granularidade)
    else:
        direto_por_bucket, indireto_por_bucket = _accumulate_tempo_natureza_from_scurve(canonical, granularidade)

    all_buckets = sorted(set(direto_por_bucket) | set(indireto_por_bucket))
    rows = [{"periodo": b, "natureza": "direto", "valor_rs": direto_por_bucket.get(b, 0.0)} for b in all_buckets] + [
        {"periodo": b, "natureza": "indireto", "valor_rs": indireto_por_bucket.get(b, 0.0)} for b in all_buckets
    ]
    rows.sort(key=lambda row: (str(row["periodo"]), str(row["natureza"])))
    columns = [
        {"id": "periodo", "label": "Período", "dtype": "str", "role": "x"},
        {"id": "natureza", "label": "Natureza", "dtype": "str", "role": "series"},
        {"id": "valor_rs", "label": "Valor (R$)", "dtype": "float", "role": "value"},
    ]
    return rows[:top_n], columns, "bar_stacked"


def _resolve_tempo_componente_rows(
    cubo: Any, canonical: Any, granularidade: FaceGranularity, top_n: int
) -> tuple[list[dict[str, Any]], list[dict[str, str]], str]:
    aggregated: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for celula, valor_cell in _iter_scaled_cubo_cells(canonical, cubo):
        bucket = bucket_from_week_iso(str(celula.semana_iso), granularidade)
        comp = _normalize_bdi_component(str(getattr(celula, "componente_bdi", "")))
        aggregated[bucket][comp] += float(valor_cell)
    # Adicionar custo_indireto de canonical.indiretos_semanal com o mesmo breakdown BDI.
    if canonical:
        bdi_multipliers = _build_bdi_multipliers_from_cubo(cubo)
        indireto_por_bucket = _custo_indireto_por_periodo(canonical, granularidade)
        for bucket, custo in indireto_por_bucket.items():
            for comp_name, comp_value in _split_operational_cost_with_bdi(custo, bdi_multipliers).items():
                aggregated[bucket][comp_name] += comp_value
    rows: list[dict[str, Any]] = []
    for periodo, comp_dict in aggregated.items():
        for componente, valor in comp_dict.items():
            rows.append({"periodo": periodo, "componente_bdi": componente, "valor_rs": float(valor)})
    rows.sort(key=lambda row: (str(row["periodo"]), -float(row["valor_rs"])))
    columns = [
        {"id": "periodo", "label": "Período", "dtype": "str", "role": "x"},
        {"id": "componente_bdi", "label": "Componente BDI", "dtype": "str", "role": "series"},
        {"id": "valor_rs", "label": "Valor (R$)", "dtype": "float", "role": "value"},
    ]
    return rows[:top_n], columns, "line"


def _accrue_indireto_categoria_componente(
    ind: Any, bdi_multipliers: dict[str, float], aggregated_cat: dict[str, dict[str, float]]
) -> None:
    mao, eq, verbas = _decompose_indireto_costs(ind)
    for cat_key, cat_cost in (("mao_obra", mao), ("equipamento", eq), ("verbas", verbas)):
        if cat_cost <= 0.0:
            continue
        for comp_name, comp_val in _split_operational_cost_with_bdi(cat_cost, bdi_multipliers).items():
            aggregated_cat[f"indireto.{cat_key}"][comp_name] += comp_val


def _resolve_categoria_componente_rows(
    cubo: Any, canonical: Any, top_n: int
) -> tuple[list[dict[str, Any]], list[dict[str, str]], str]:
    # Agrupa por {direto,indireto}.{categoria} com o mesmo breakdown de componentes.
    # Direto: células do cubo com natureza='direto' (via _iter_scaled_cubo_cells).
    # Indireto: lido de canonical.indiretos decomposto em mao_obra/equipamento/verbas.
    aggregated_cat: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    bdi_multipliers = _build_bdi_multipliers_from_cubo(cubo)
    for celula, valor_cell in _iter_scaled_cubo_cells(canonical, cubo):
        natureza_key = f"direto.{str(getattr(celula, 'categoria', '') or '')}"
        agg_comp = _normalize_bdi_component(str(getattr(celula, "componente_bdi", "")))
        aggregated_cat[natureza_key][agg_comp] += float(valor_cell)
    # Indiretos de canonical.indiretos, decompostos em mao_obra/equipamento/verbas
    if canonical:
        for ind in getattr(canonical, "indiretos", None) or []:
            _accrue_indireto_categoria_componente(ind, bdi_multipliers, aggregated_cat)
    rows = [
        {"categoria": natureza_key, "componente_bdi": comp, "valor_rs": float(valor)}
        for natureza_key, comp_dict in aggregated_cat.items()
        for comp, valor in comp_dict.items()
    ]
    rows.sort(key=lambda row: -float(row["valor_rs"]))
    columns = [
        {"id": "categoria", "label": "Natureza.Categoria", "dtype": "str", "role": "y"},
        {"id": "componente_bdi", "label": "Componente", "dtype": "str", "role": "x"},
        {"id": "valor_rs", "label": "Valor (R$)", "dtype": "float", "role": "value"},
    ]
    return rows[:top_n], columns, "heatmap"


def _accrue_indireto_atividade_componente(
    ind: Any, bdi_multipliers: dict[str, float], aggregated_atv: dict[str, dict[str, float]]
) -> None:
    cat = str(getattr(ind, "categoria", "") or "")
    custo_total_ind = float(getattr(ind, "custo_total", 0.0) or 0.0)
    if not cat or custo_total_ind <= 0.0:
        return
    ind_key = f"indireto.{cat}"
    for comp_name, comp_val in _split_operational_cost_with_bdi(custo_total_ind, bdi_multipliers).items():
        aggregated_atv[ind_key][comp_name] += comp_val


def _resolve_atividade_componente_rows(
    cubo: Any, canonical: Any, top_n: int
) -> tuple[list[dict[str, Any]], list[dict[str, str]], str]:
    # Chave composta {direto,indireto}.{atividade} com breakdown simétrico de componentes.
    # Direto: células cubo natureza='direto' → chave direto.eap-1_X
    # Indireto: células cubo natureza='indireto' → chave indireto.IND-{cat}
    aggregated_atv: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    bdi_multipliers = _build_bdi_multipliers_from_cubo(cubo)
    for celula, valor_cell in _iter_scaled_cubo_cells(canonical, cubo):
        natureza_key = f"direto.{str(getattr(celula, 'atividade_id', '') or '')}"
        agg_comp = _normalize_bdi_component(str(getattr(celula, "componente_bdi", "")))
        aggregated_atv[natureza_key][agg_comp] += float(valor_cell)
    # Indiretos de canonical.indiretos usando ind.categoria como chave
    if canonical:
        for ind in getattr(canonical, "indiretos", None) or []:
            _accrue_indireto_atividade_componente(ind, bdi_multipliers, aggregated_atv)
    rows = [
        {"atividade_id": natureza_key, "componente_bdi": comp, "valor_rs": float(valor)}
        for natureza_key, comp_dict in aggregated_atv.items()
        for comp, valor in comp_dict.items()
    ]
    rows.sort(key=lambda row: -float(row["valor_rs"]))
    columns = [
        {"id": "atividade_id", "label": "Atividade", "dtype": "str", "role": "y"},
        {"id": "componente_bdi", "label": "Componente", "dtype": "str", "role": "x"},
        {"id": "valor_rs", "label": "Valor (R$)", "dtype": "float", "role": "value"},
    ]
    return rows[:top_n], columns, "heatmap"


def _resolve_diesel_temporal_rows(
    cubo: Any, granularidade: FaceGranularity, top_n: int
) -> tuple[list[dict[str, Any]], list[dict[str, str]], str]:
    # Agregar por mês, empilhado pelas top atividades consumidoras de diesel
    per_atividade_por_bucket: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for celula in getattr(cubo, "celulas", None) or []:
        diesel_l = float(getattr(celula, "consumo_diesel_L", 0.0) or 0.0)
        if diesel_l > 0:
            bucket = bucket_from_week_iso(str(celula.semana_iso), granularidade)
            per_atividade_por_bucket[bucket][str(celula.atividade_id)] += diesel_l
    totais_por_atividade: dict[str, float] = defaultdict(float)
    for at_dict in per_atividade_por_bucket.values():
        for aid, v in at_dict.items():
            totais_por_atividade[aid] += v
    top_atividades = sorted(totais_por_atividade, key=lambda a: -totais_por_atividade[a])[:4]
    rows = []
    for bucket in sorted(per_atividade_por_bucket):
        for aid in top_atividades:
            rows.append(
                {
                    "periodo": bucket,
                    "atividade_id": aid,
                    "consumo_diesel_l": per_atividade_por_bucket[bucket].get(aid, 0.0),
                }
            )
    columns = [
        {"id": "periodo", "label": "Período", "dtype": "str", "role": "x"},
        {"id": "atividade_id", "label": "Atividade", "dtype": "str", "role": "series"},
        {"id": "consumo_diesel_l", "label": "Consumo Diesel (L)", "dtype": "float", "role": "value"},
    ]
    return rows[:top_n], columns, "bar_stacked"


def resolve_cubo_projection_rows(
    cubo: Any,
    face: str,
    granularidade: FaceGranularity,
    top_n: int,
    canonical: Any = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], str]:
    if face == "direto_temporal_categoria":
        return _resolve_direto_temporal_categoria_rows(cubo, canonical, granularidade, top_n)

    if face == "indireto_temporal_categoria":
        return _resolve_indireto_temporal_categoria_rows(canonical, granularidade, top_n)

    if face == "tempo_natureza":
        return _resolve_tempo_natureza_rows(canonical, granularidade, top_n)

    if face == "tempo_componente":
        return _resolve_tempo_componente_rows(cubo, canonical, granularidade, top_n)

    if face == "categoria_componente":
        return _resolve_categoria_componente_rows(cubo, canonical, top_n)

    if face == "atividade_componente":
        return _resolve_atividade_componente_rows(cubo, canonical, top_n)

    if face == "diesel_temporal":
        return _resolve_diesel_temporal_rows(cubo, granularidade, top_n)

    raise ValueError(f"Face de projeção não suportada: {face}")


def resolve_abc_curva_rows(
    canonical: Any,
    top_n: int,
    threshold_a: float,
    threshold_b: float,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], str, str, dict[str, Any]]:
    from concilium.domain.services.analytics.curva_abc_builder import CurvaABCBuilder

    curva = CurvaABCBuilder().build(canonical)
    rows: list[dict[str, Any]] = []
    for item in list(curva.itens)[:top_n]:
        classe = (
            "A"
            if item.pct_custo_acumulado <= threshold_a
            else ("B" if item.pct_custo_acumulado <= threshold_b else "C")
        )
        rows.append(
            {
                "insumo_id": item.insumo_id,
                "descricao": item.descricao,
                "categoria": item.categoria.lower(),
                "custo_total_rs": float(item.custo_total),
                "pct_custo": float(item.pct_custo),
                "pct_custo_acumulado": float(item.pct_custo_acumulado),
                "classe_abc": classe,
            }
        )
    columns = [
        {"id": "insumo_id", "label": "Insumo", "dtype": "str", "role": "x"},
        {"id": "descricao", "label": "Descrição", "dtype": "str", "role": "label"},
        {"id": "categoria", "label": "Categoria", "dtype": "str", "role": "series"},
        {"id": "custo_total_rs", "label": "Custo Total (R$)", "dtype": "float", "role": "value"},
        {"id": "pct_custo", "label": "% Custo", "dtype": "float", "role": "value_aux"},
        {"id": "pct_custo_acumulado", "label": "% Acumulado", "dtype": "float", "role": "line"},
        {"id": "classe_abc", "label": "Classe ABC", "dtype": "str", "role": "class"},
    ]
    class_counts = {"A": 0, "B": 0, "C": 0}
    for row in rows:
        class_counts[str(row["classe_abc"])] += 1
    operator_meta = {
        "thresholds": {"a": threshold_a, "b": threshold_b},
        "class_counts": class_counts,
        "coverage_a": max((float(row["pct_custo_acumulado"]) for row in rows if row["classe_abc"] == "A"), default=0.0),
    }
    return rows, columns, "bar", FACE_UNIT_TYPES["abc_curva"], operator_meta


def resolve_s_curve_rows(
    canonical: Any,
    granularidade: FaceGranularity,
    top_n: int,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], str, str, dict[str, Any]]:
    from concilium.domain.services.analytics.s_curve_builder import SCurveBuilder

    s_curve = SCurveBuilder().build(canonical)
    grouped: dict[str, dict[str, float]] = defaultdict(lambda: {"custo_semanal_rs": 0.0, "custo_acumulado_rs": 0.0})
    for idx, semana_iso in enumerate(s_curve.semanas_iso):
        bucket = bucket_from_week_iso(semana_iso, granularidade)
        grouped[bucket]["custo_semanal_rs"] += float(s_curve.custo_semanal[idx])
        grouped[bucket]["custo_acumulado_rs"] += float(s_curve.custo_semanal[idx])
    rows: list[dict[str, Any]] = []
    acumulado = 0.0
    for bucket in sorted(grouped.keys()):
        custo = float(grouped[bucket]["custo_semanal_rs"])
        acumulado += custo
        rows.append(
            {
                "periodo": bucket,
                "custo_semanal_rs": custo,
                "custo_acumulado_rs": round(acumulado, 2),
                "pct_acumulado": round(acumulado / float(s_curve.total_projeto), 6)
                if s_curve.total_projeto > 0
                else 0.0,
            }
        )
    columns = [
        {"id": "periodo", "label": "Período", "dtype": "str", "role": "x"},
        {"id": "custo_semanal_rs", "label": "Custo no Período (R$)", "dtype": "float", "role": "value"},
        {"id": "custo_acumulado_rs", "label": "Custo Acumulado (R$)", "dtype": "float", "role": "line"},
        {"id": "pct_acumulado", "label": "% Acumulado", "dtype": "float", "role": "line_aux"},
    ]
    return (
        rows[:top_n],
        columns,
        "line",
        FACE_UNIT_TYPES["s_curve_custo"],
        {"total_projeto_rs": float(s_curve.total_projeto)},
    )


def resolve_recursos_ativos_rows(
    canonical: Any,
    granularidade: FaceGranularity,
    top_n: int,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], str, str, dict[str, Any]]:
    from concilium.domain.services.analytics.s_curve_builder import SCurveBuilder

    s_curve = SCurveBuilder().build(canonical)
    grouped: dict[str, dict[str, float]] = defaultdict(
        lambda: {
            "n_equipes_totais": 0.0,
            "n_equipamentos_unicos": 0.0,
            "equipamentos_unidades_ativas": 0.0,
        }
    )
    for agg in s_curve.agregacao_semanal:
        bucket = bucket_from_week_iso(str(agg.semana_iso), granularidade)
        grouped[bucket]["n_equipes_totais"] += float(agg.n_equipes_totais)
        grouped[bucket]["n_equipamentos_unicos"] = max(
            grouped[bucket]["n_equipamentos_unicos"], float(agg.n_equipamentos_unicos)
        )
        grouped[bucket]["equipamentos_unidades_ativas"] += float(sum(agg.equipamentos_ativos.values()))
    rows = [
        {
            "periodo": bucket,
            "n_equipes_totais": int(vals["n_equipes_totais"]),
            "n_equipamentos_unicos": int(vals["n_equipamentos_unicos"]),
            "equipamentos_unidades_ativas": int(vals["equipamentos_unidades_ativas"]),
        }
        for bucket, vals in sorted(grouped.items())
    ]
    columns = [
        {"id": "periodo", "label": "Período", "dtype": "str", "role": "x"},
        {"id": "n_equipes_totais", "label": "Nº Equipes", "dtype": "int", "role": "value"},
        {"id": "n_equipamentos_unicos", "label": "Equipamentos Únicos", "dtype": "int", "role": "value"},
        {
            "id": "equipamentos_unidades_ativas",
            "label": "Unidades de Equipamento Ativas",
            "dtype": "int",
            "role": "value",
        },
    ]
    operator_meta = {
        "aggregation_rule": "sum(n_equipes, unidades) + max(equipamentos_unicos) por bucket",
        "n_periodos": len(rows),
    }
    return rows[:top_n], columns, "line", FACE_UNIT_TYPES["recursos_ativos_tempo"], operator_meta


def build_cube_projection_payload(
    *,
    canonical: Any,
    cubo: Any,
    face: str,
    granularidade: FaceGranularity,
    top_n: int,
    abc_threshold_a: float = 0.80,
    abc_threshold_b: float = 0.95,
) -> dict[str, Any]:
    if face == "abc_curva":
        rows, columns, chart_hint, unit_type, operator_meta = resolve_abc_curva_rows(
            canonical, top_n, abc_threshold_a, abc_threshold_b
        )
    elif face == "s_curve_custo":
        rows, columns, chart_hint, unit_type, operator_meta = resolve_s_curve_rows(canonical, granularidade, top_n)
    elif face == "recursos_ativos_tempo":
        rows, columns, chart_hint, unit_type, operator_meta = resolve_recursos_ativos_rows(
            canonical, granularidade, top_n
        )
    else:
        rows, columns, chart_hint = resolve_cubo_projection_rows(cubo, face, granularidade, top_n, canonical=canonical)
        unit_type = FACE_UNIT_TYPES[face]
        operator_meta = {}
    return {
        "face": face,
        "granularidade": granularidade,
        "rows": rows,
        "columns": columns,
        "chart_hint": chart_hint,
        "unit_type": unit_type,
        "operator_meta": operator_meta,
    }
