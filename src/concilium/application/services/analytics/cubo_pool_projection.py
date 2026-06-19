"""Projeções (faces) do Cubo de Pool Instancial — ADR-086 Fases 3-4.

Espelha o contrato de projeção do ADR-069 (CuboAnalitico):
``{face, granularidade, unit_type, chart_hint, columns[], rows[], operator_meta, totais, narrativa[]}``.

Separação rígida (ADR-086 H4):
  - Faces **físicas** (do CuboPoolInstancial): o que cada slot fez — nunca imputam idle/mob a atividade.
    - Faces **causais/estruturais** (de CustoParticionadoItem / CadeiaPerpetuacao): a quem imputamos,
        sempre com baseline homogênea explícita ao lado.

Cada face inclui ``narrativa``: frases descritivas geradas dos próprios dados, com caveats explícitos.
"""

from __future__ import annotations

from typing import Any

from concilium.application.services.analytics.cube_projection_views import bucket_from_week_iso
from concilium.domain.services.analytics.cubo_pool_builder import (
    CuboPoolInstancialBuilder,
    validar_invariantes_cubo_pool,
)

_COMP_LABEL = {"mo": "Mão-de-obra", "eq": "Equipamento", "comb": "Combustível", "mat": "Material"}
_ESTADO_LABEL = {"prod": "Produtivo", "idle": "Ocioso", "off": "Desmobilizado"}

# Matriz de contrato: faces × metadados (ADR-086 D6.1)
_FACES: dict[str, dict] = {
    "utilizacao_temporal": {
        "label": "Utilização no tempo",
        "natureza": "fisica",
        "unit_type": "count",
        "chart_hint": "bar_stacked",
    },
    "custo_estado_componente": {
        "label": "Custo por estado × componente",
        "natureza": "fisica",
        "unit_type": "currency_brl",
        "chart_hint": "heatmap",
    },
    "instancia_ciclo_vida": {
        "label": "Ciclo de vida por instância",
        "natureza": "fisica",
        "unit_type": "currency_brl",
        "chart_hint": "table",
    },
    "atividade_instancia": {
        "label": "Rastreabilidade atividade ↔ slot",
        "natureza": "fisica",
        "unit_type": "count",
        "chart_hint": "table",
    },
    "causa_custo": {
        "label": "Causa do custo (Euler)",
        "natureza": "causal",
        "unit_type": "currency_brl",
        "chart_hint": "bar_stacked",
    },
    "economia_pool": {
        "label": "Economia vs. execução autônoma",
        "natureza": "causal",
        "unit_type": "currency_brl",
        "chart_hint": "bar",
    },
    "cadeia_perpetuacao": {
        "label": "Cadeias de perpetuação",
        "natureza": "estrutural",
        "unit_type": "count",
        "chart_hint": "table",
    },
}

_GRANULARIDADES = ["semana", "mes", "trimestre", "ano"]


def _planejamento_sem_bdi_total(plan: Any) -> float:
    subtotal = getattr(plan, "subtotal", None)
    sem_bdi = getattr(subtotal, "sem_bdi", None) if subtotal is not None else None
    total = getattr(sem_bdi, "total", 0.0) if sem_bdi is not None else 0.0
    return round(float(total or 0.0), 2)


def _autonomo_total_por_item(eq: Any) -> float:
    """Retorna baseline autônomo total do item, expandindo custo por frente quando necessário."""
    custo_1_frente = float(getattr(eq, "custo_total_autonomo", 0.0) or 0.0)
    if custo_1_frente <= 0.0:
        return 0.0
    n_frentes = max(1, int(getattr(eq, "num_equipes_base", 1) or 1))
    return round(custo_1_frente * n_frentes, 2)


def _baseline_homogenea_por_item(canonical_in: Any) -> tuple[dict[str, float], dict[str, str]]:
    """Retorna baseline por item no mesmo referencial do planejamento (sem BDI).

    Preferência:
    1. subtotal.sem_bdi.total do planejamento (referencial homogêneo de orçamento)
    2. custo_total_autonomo operacional expandido por frentes (fallback legado)
    """
    baseline: dict[str, float] = {}
    source: dict[str, str] = {}

    for plan in getattr(canonical_in, "planejamento", None) or []:
        item_id = str(getattr(plan, "item_id", "") or "")
        if not item_id:
            continue
        total = _planejamento_sem_bdi_total(plan)
        if total > 0.0:
            baseline[item_id] = total
            source[item_id] = "planejamento_sem_bdi"

    for eq in getattr(canonical_in, "equipes_diretas", None) or []:
        item_id = str(getattr(eq, "item_id", "") or "")
        if not item_id or item_id in baseline:
            continue
        total = _autonomo_total_por_item(eq)
        if total > 0.0:
            baseline[item_id] = total
            source[item_id] = "operacional_autonomo_fallback"

    return baseline, source


def _count_mob_demob_por_periodo(cubo: Any, granularidade: str) -> dict[str, dict[str, int]]:
    """Conta eventos de mobilização e desmobilização por bucket temporal."""
    counts: dict[str, dict[str, int]] = {}

    def _bucket(week_label: str) -> str:
        txt = str(week_label or "")
        if not txt:
            return ""
        if "-W" not in txt:
            return txt
        return bucket_from_week_iso(txt, granularidade)

    for data in (cubo.ciclo_vida_instancias() or {}).values():
        semana_mob = str(data.get("semana_mob", "") or "")
        semana_demob = str(data.get("semana_demob", "") or "")
        if semana_mob:
            bucket = _bucket(semana_mob)
            counts.setdefault(bucket, {"mob": 0, "demob": 0})["mob"] += 1
        if semana_demob:
            bucket = _bucket(semana_demob)
            counts.setdefault(bucket, {"mob": 0, "demob": 0})["demob"] += 1
    return counts


def cubo_pool_projection_contract() -> dict:
    """Contrato navegável: faces disponíveis × granularidades × naturezas (ADR-086 D6.1)."""
    return {
        "version": "adr086-v1",
        "faces": {
            name: {
                "label": m["label"],
                "natureza": m["natureza"],
                "unit_type": m["unit_type"],
                "chart_hint": m["chart_hint"],
            }
            for name, m in _FACES.items()
        },
        "granularidades": _GRANULARIDADES,
        "naturezas": ["fisica", "causal", "estrutural"],
        "default_face": "instancia_ciclo_vida",
        "default_granularidade": "mes",
    }


def _fmt(v: float) -> str:
    return f"R$ {v:,.0f}"


def resolve_cubo_pool_projection(
    canonical_in: Any,
    *,
    face: str = "instancia_ciclo_vida",
    granularidade: str = "mes",
    top_n: int = 300,
    atividade_id: str | None = None,
    instancia_id: str | None = None,
    gerado_em: str = "",
) -> dict:
    """Resolve uma face do cubo de pool. Retorna o contrato de projeção (ADR-086 D4/D5)."""
    if face not in _FACES:
        face = "instancia_ciclo_vida"
    meta = _FACES[face]

    cubo = CuboPoolInstancialBuilder().build(canonical_in, gerado_em=gerado_em)
    contratos = list(getattr(canonical_in, "contratos_recurso", None) or [])
    cadeias = list(getattr(canonical_in, "cadeias_perpetuacao", None) or [])

    # Filtros opcionais
    if atividade_id or instancia_id:
        tipo = inst_num = None
        if instancia_id and "-" in instancia_id:
            tipo, _, num = instancia_id.rpartition("-")
            inst_num = int(num) if num.isdigit() else None
        cubo = cubo.slice(
            atividade_id=atividade_id if face in ("atividade_instancia",) else None,
            tipo_id=tipo,
            instancia_numero=inst_num,
        )

    # Baseline homogênea por item: planejamento sem BDI quando disponível; fallback
    # operacional apenas para projetos/fixtures sem planejamento consolidado.
    baseline_por_item, baseline_source_by_item = _baseline_homogenea_por_item(canonical_in)

    dispatch = {
        "utilizacao_temporal": _face_utilizacao_temporal,
        "custo_estado_componente": _face_custo_estado_componente,
        "instancia_ciclo_vida": _face_ciclo_vida,
        "atividade_instancia": _face_atividade_instancia,
        "causa_custo": _face_causa_custo,
        "economia_pool": _face_economia_pool,
        "cadeia_perpetuacao": _face_cadeia_perpetuacao,
    }
    columns, rows, narrativa, operator_meta = dispatch[face](
        cubo,
        contratos,
        cadeias,
        granularidade=granularidade,
        atividade_id=atividade_id,
        top_n=top_n,
        baseline_por_item=baseline_por_item,
        baseline_source_by_item=baseline_source_by_item,
    )

    truncado = len(rows) > top_n
    if truncado:
        operator_meta = {**operator_meta, "truncado": True, "linhas_totais": len(rows)}
        narrativa = [*narrativa, f"⚠ Exibindo {top_n} de {len(rows)} linhas (truncado)."]
        rows = rows[:top_n]

    # Invariantes de honestidade (H1/H3)
    violacoes = validar_invariantes_cubo_pool(cubo, contratos)

    return {
        "version": "adr086-v1",
        "face": face,
        "natureza": meta["natureza"],
        "granularidade": granularidade,
        "unit_type": meta["unit_type"],
        "chart_hint": meta["chart_hint"],
        "columns": columns,
        "rows": rows,
        "narrativa": narrativa,
        "operator_meta": operator_meta,
        "totais": {
            "custo_total_pool": cubo.custo_total,
            "custo_por_estado": cubo.custo_por_estado(),
            "custo_por_componente": cubo.custo_por_componente(),
            "semanas_por_estado": cubo.semanas_por_estado(),
        },
        "invariantes_ok": not violacoes,
        "invariantes_violacoes": violacoes,
        "filtros_aplicados": {"atividade_id": atividade_id, "instancia_id": instancia_id, "top_n": top_n},
    }


# ── Faces físicas ─────────────────────────────────────────────────────────────


def _face_utilizacao_temporal(cubo, contratos, cadeias, *, granularidade, **_):
    util = cubo.utilizacao_temporal(granularidade)
    periodos = sorted({p for (p, _e) in util})
    mob_demob = _count_mob_demob_por_periodo(cubo, granularidade)
    rows = []
    for p in periodos:
        rows.append(
            {
                "periodo": p,
                "prod": util.get((p, "prod"), 0),
                "idle": util.get((p, "idle"), 0),
                "off": util.get((p, "off"), 0),
                "mob": mob_demob.get(p, {}).get("mob", 0),
                "demob": mob_demob.get(p, {}).get("demob", 0),
            }
        )
    columns = [
        {"id": "periodo", "label": "Período", "dtype": "str", "role": "x"},
        {"id": "prod", "label": "Produtivo", "dtype": "int", "role": "series"},
        {"id": "idle", "label": "Ocioso", "dtype": "int", "role": "series"},
        {"id": "off", "label": "Desmobilizado", "dtype": "int", "role": "series"},
        {"id": "mob", "label": "Mobilizações", "dtype": "int", "role": "value"},
        {"id": "demob", "label": "Desmobilizações", "dtype": "int", "role": "value"},
    ]
    sem = cubo.semanas_por_estado()
    total_slot_sem = sum(sem.values()) or 1
    total_mob = sum(r["mob"] for r in rows)
    total_demob = sum(r["demob"] for r in rows)
    narrativa = [
        f"Slot-semanas: {sem['prod']} produtivas, {sem['idle']} ociosas, {sem['off']} desmobilizadas "
        f"(off = recurso liberado, não faturado — {sem['off'] / total_slot_sem * 100:.0f}% do total).",
    ]
    if sem["idle"]:
        narrativa.append(
            "Semanas ociosas mantêm MO integral (CLT) e equipamento a taxa de locação reduzida; "
            "combustível e material zerados (sem operação)."
        )
    if total_mob or total_demob:
        narrativa.append(
            f"Eventos temporais do pool: {total_mob} mobilização(ões) e {total_demob} desmobilização(ões) "
            "distribuídas ao longo das fases do projeto."
        )
    if sem["off"]:
        narrativa.append(
            "Desmobilizado (off) no início do horizonte significa slot ainda não mobilizado para operação; "
            "não representa desmobilização antecipada após produção."
        )
    return columns, rows, narrativa, {}


def _face_custo_estado_componente(cubo, contratos, cadeias, **_):
    cec = cubo.custo_estado_componente()
    rows = []
    for estado in ("prod", "idle", "off"):
        for comp in ("mo", "eq", "comb", "mat"):
            v = cec.get((estado, comp), 0.0)
            if v:
                rows.append({"estado": _ESTADO_LABEL[estado], "componente": _COMP_LABEL[comp], "valor_rs": round(v, 2)})
    columns = [
        {"id": "estado", "label": "Estado", "dtype": "str", "role": "y"},
        {"id": "componente", "label": "Componente", "dtype": "str", "role": "x"},
        {"id": "valor_rs", "label": "Valor (R$)", "dtype": "float", "role": "value"},
    ]
    por_estado = cubo.custo_por_estado()
    narrativa = [
        f"Produtivo {_fmt(por_estado['prod'])} · Ocioso {_fmt(por_estado['idle'])} · "
        f"Desmobilizado {_fmt(por_estado['off'])} (sempre R$ 0 — recurso liberado).",
    ]
    idle_mo = cec.get(("idle", "mo"), 0.0)
    idle_eq = cec.get(("idle", "eq"), 0.0)
    if idle_mo or idle_eq:
        narrativa.append(
            f"Ociosidade: MO {_fmt(idle_mo)} (integral, CLT) + EQ {_fmt(idle_eq)} (locação reduzida). "
            "Combustível/material não incorrem ociosos."
        )
    comb_total = cec.get(("prod", "comb"), 0.0) + cec.get(("idle", "comb"), 0.0)
    mat_total = cec.get(("prod", "mat"), 0.0) + cec.get(("idle", "mat"), 0.0)
    if comb_total <= 0.0:
        narrativa.append("Combustível aparece zerado nesta execução (sem custo de diesel consolidado no pool instancial).")
    if mat_total <= 0.0:
        narrativa.append("Material aparece zerado nesta execução do pool instancial.")
    return columns, rows, narrativa, {}


def _face_ciclo_vida(cubo, contratos, cadeias, *, top_n=300, **_):
    cv = cubo.ciclo_vida_instancias()
    contrato_por_id = {c.contrato_id: c for c in contratos}
    rows = []
    for iid, d in sorted(cv.items()):
        rows.append(
            {
                "instancia_id": iid,
                "tipo_id": d["tipo_id"],
                "semana_mob": d["semana_mob"],
                "semana_demob": d["semana_demob"],
                "prod_w": d["prod_w"],
                "idle_w": d["idle_w"],
                "off_w": d["off_w"],
                "custo_mo": d["custo_mo"],
                "custo_eq": d["custo_eq"],
                "custo_comb": d["custo_comb"],
                "custo_mat": d["custo_mat"],
                "custo_total": d["custo_total"],
            }
        )
    rows.sort(key=lambda r: -r["custo_total"])
    columns = [
        {"id": "instancia_id", "label": "Instância", "dtype": "str", "role": "class"},
        {"id": "semana_mob", "label": "Mobilização", "dtype": "str", "role": "x"},
        {"id": "semana_demob", "label": "Desmobilização", "dtype": "str", "role": "x"},
        {"id": "prod_w", "label": "Prod (sem)", "dtype": "int", "role": "value"},
        {"id": "idle_w", "label": "Ocioso (sem)", "dtype": "int", "role": "value"},
        {"id": "off_w", "label": "Off (sem)", "dtype": "int", "role": "value"},
        {"id": "custo_mo", "label": "MO (R$)", "dtype": "float", "role": "value"},
        {"id": "custo_eq", "label": "EQ (R$)", "dtype": "float", "role": "value"},
        {"id": "custo_total", "label": "Total (R$)", "dtype": "float", "role": "value"},
    ]
    narrativa: list[str] = []
    for r in rows[:6]:
        off_txt = f", {r['off_w']} sem. off (liberada)" if r["off_w"] else ""
        idle_txt = f", {r['idle_w']} ociosas" if r["idle_w"] else ", 0 ociosas"
        narrativa.append(
            f"{r['instancia_id']}: mobilizada na sem. {r['semana_mob']}, {r['prod_w']} sem. produtivas{idle_txt}{off_txt}. "
            f"Custo {_fmt(r['custo_total'])} — MO {_fmt(r['custo_mo'])} (integral), EQ {_fmt(r['custo_eq'])}."
        )
    return columns, rows, narrativa, {"n_instancias": len(rows)}


def _face_atividade_instancia(cubo, contratos, cadeias, *, atividade_id=None, **_):
    ai = cubo.atividade_instancia()
    rows = []
    for (atv, iid), d in sorted(ai.items()):
        rows.append(
            {
                "atividade_id": atv,
                "instancia_id": iid,
                "semana_inicio": d["semana_inicio"],
                "semana_fim": d["semana_fim"],
                "machine_weeks": d["machine_weeks"],
                "custo": d["custo"],
            }
        )
    rows.sort(key=lambda r: (r["atividade_id"], r["instancia_id"]))
    columns = [
        {"id": "atividade_id", "label": "Atividade", "dtype": "str", "role": "class"},
        {"id": "instancia_id", "label": "Slot", "dtype": "str", "role": "series"},
        {"id": "semana_inicio", "label": "Início", "dtype": "str", "role": "x"},
        {"id": "semana_fim", "label": "Fim", "dtype": "str", "role": "x"},
        {"id": "machine_weeks", "label": "Machine-weeks", "dtype": "int", "role": "value"},
        {"id": "custo", "label": "Custo (R$)", "dtype": "float", "role": "value"},
    ]
    n_atv = len({r["atividade_id"] for r in rows})
    n_slots = len({r["instancia_id"] for r in rows})
    narrativa = [
        f"{n_atv} atividade(s) servidas por {n_slots} slot(s) — rastreabilidade física (apenas semanas "
        "produtivas; ociosidade/mob NÃO são imputadas a atividades aqui, ver faces causais)."
    ]
    return columns, rows, narrativa, {}


# ── Faces causais / estruturais ────────────────────────────────────────────────


def _iter_particoes(contratos):
    for c in contratos:
        for p in getattr(c, "particao_por_item", None) or []:
            yield c, p


def _face_causa_custo(cubo, contratos, cadeias, *, top_n=300, **_):
    rows = []
    for _c, p in _iter_particoes(contratos):
        rows.append(
            {
                "atividade_id": p.item_id,
                "produtivo_exclusivo": round(p.custo_produtivo_exclusivo, 2),
                "produtivo_compartilhado": round(p.custo_produtivo_compartilhado, 2),
                "ocioso_imputado": round(p.custo_ocioso_imputado, 2),
                "mob_demob_imputado": round(p.custo_mob_imputado + p.custo_demob_imputado, 2),
                "total_imputado": round(p.custo_total_particionado, 2),
                "predecessor_critico": p.predecessor_critico_id or "",
                "overlap_semanas": round(p.overlap_semanas, 1),
            }
        )
    rows.sort(key=lambda r: -r["total_imputado"])
    columns = [
        {"id": "atividade_id", "label": "Atividade", "dtype": "str", "role": "x"},
        {"id": "produtivo_exclusivo", "label": "Produtivo exclusivo", "dtype": "float", "role": "series"},
        {"id": "produtivo_compartilhado", "label": "Produtivo compartilhado", "dtype": "float", "role": "series"},
        {"id": "ocioso_imputado", "label": "Ocioso imputado", "dtype": "float", "role": "series"},
        {"id": "mob_demob_imputado", "label": "Mob/Demob imputado", "dtype": "float", "role": "series"},
        {"id": "total_imputado", "label": "Total imputado", "dtype": "float", "role": "value"},
    ]
    narrativa = [
        "Imputação CAUSAL (não física): custo de gap ocioso é atribuído ao sucessor que o causou "
        "(ADR-083); mob/demob é rateado igualmente na cadeia de perpetuação (ADR-073).",
    ]
    for r in rows[:4]:
        if r["ocioso_imputado"] > 0 and r["predecessor_critico"]:
            narrativa.append(
                f"{r['atividade_id']}: {_fmt(r['ocioso_imputado'])} de ociosidade imputada como sucessor de "
                f"{r['predecessor_critico']} ({r['overlap_semanas']} sem. sobreposição)."
            )
    return columns, rows, narrativa, {}


def _face_economia_pool(cubo, contratos, cadeias, *, top_n=300, baseline_por_item=None, baseline_source_by_item=None, **_):
    baseline_por_item = baseline_por_item or {}
    baseline_source_by_item = baseline_source_by_item or {}
    rows = []
    tot_aut = tot_inst = tot_inst_prod = tot_burden = 0.0
    sem_baseline = 0
    fallback_count = 0
    for _c, p in _iter_particoes(contratos):
        inst = round(p.custo_total_particionado, 2)
        inst_prod = round(float(p.custo_produtivo_exclusivo or 0.0) + float(p.custo_produtivo_compartilhado or 0.0), 2)
        burden = round(
            float(p.custo_ocioso_imputado or 0.0)
            + float(p.custo_mob_imputado or 0.0)
            + float(p.custo_demob_imputado or 0.0),
            2,
        )
        # Baseline homogênea: planejamento sem BDI; fallback operacional apenas quando
        # o item não tem planejamento consolidado disponível.
        aut = round(baseline_por_item.get(p.item_id, 0.0) or float(p.custo_total_autonomo or 0.0), 2)
        baseline_source = baseline_source_by_item.get(p.item_id, "particao_fallback")
        if aut <= 0:
            sem_baseline += 1
        if baseline_source != "planejamento_sem_bdi":
            fallback_count += 1
        eco = round(aut - inst, 2)
        eco_prod = round(aut - inst_prod, 2)
        tot_aut += aut
        tot_inst += inst
        tot_inst_prod += inst_prod
        tot_burden += burden
        rows.append(
            {
                "atividade_id": p.item_id,
                "custo_autonomo": aut,
                "custo_instancial": inst,
                "custo_instancial_produtivo": inst_prod,
                "burden_pool": burden,
                "economia": eco,
                "economia_produtiva": eco_prod,
                "economia_pct": round((eco / aut * 100) if aut > 0 else 0.0, 1),
                "economia_produtiva_pct": round((eco_prod / aut * 100) if aut > 0 else 0.0, 1),
                "baseline_disponivel": aut > 0,
                "baseline_source": baseline_source,
            }
        )
    rows.sort(key=lambda r: -r["economia"])
    columns = [
        {"id": "atividade_id", "label": "Atividade", "dtype": "str", "role": "x"},
        {"id": "custo_autonomo", "label": "Baseline homogênea (R$)", "dtype": "float", "role": "series"},
        {"id": "custo_instancial", "label": "Instancial (R$)", "dtype": "float", "role": "series"},
        {"id": "economia", "label": "Economia (R$)", "dtype": "float", "role": "value"},
        {"id": "economia_pct", "label": "Economia (%)", "dtype": "float", "role": "value"},
    ]
    eco_total = round(tot_aut - tot_inst, 2)
    eco_prod_total = round(tot_aut - tot_inst_prod, 2)
    narrativa = [
        f"Baseline homogênea (planejamento sem BDI) {_fmt(tot_aut)} vs. instancial (pool) {_fmt(tot_inst)} → "
        f"economia líquida {_fmt(eco_total)} ({(eco_total / tot_aut * 100) if tot_aut else 0:.1f}%).",
        "Economia sempre apresentada contra baseline homogênea explícita no mesmo referencial do planejamento.",
        f"Leitura operacional: instancial produtivo {_fmt(tot_inst_prod)} + burden de pool "
        f"(ocioso+mob/demob) {_fmt(tot_burden)}.",
        f"Economia produtiva (sem burden): {_fmt(eco_prod_total)} "
        f"({(eco_prod_total / tot_aut * 100) if tot_aut else 0:.1f}%).",
    ]
    if fallback_count:
        narrativa.append(
            f"⚠ {fallback_count} atividade(s) usam fallback operacional por ausência de baseline de planejamento consolidado."
        )
    if eco_total < 0:
        narrativa.append(
            "Economia negativa: o pool ficou acima da baseline homogênea. Em obras sequenciais sem compartilhamento "
            "efetivo entre fases, isso tende a refletir burden contratual frente ao orçamento, não ganho operacional perdido."
        )
    if sem_baseline:
        narrativa.append(f"⚠ {sem_baseline} atividade(s) sem baseline disponível (economia não calculável).")
    return (
        columns,
        rows,
        narrativa,
        {
            "custo_autonomo_total": round(tot_aut, 2),
            "custo_instancial_total": round(tot_inst, 2),
            "custo_instancial_produtivo_total": round(tot_inst_prod, 2),
            "burden_pool_total": round(tot_burden, 2),
            "economia_total": eco_total,
            "economia_produtiva_total": eco_prod_total,
            "itens_sem_baseline": sem_baseline,
            "baseline_kind": "planejamento_sem_bdi",
            "itens_fallback_operacional": fallback_count,
        },
    )


def _face_cadeia_perpetuacao(cubo, contratos, cadeias, *, top_n=300, **_):
    rows = []
    for ch in cadeias:
        rows.append(
            {
                "cadeia_id": ch.cadeia_id,
                "tipo_id": ch.tipo_id,
                "atividades": " → ".join(ch.item_ids),
                "n_atividades": len(ch.item_ids),
                "semanas_ativas": ch.semanas_ativas,
                "semanas_ociosas": ch.semanas_ociosas,
                "n_mob_demob": ch.n_mobilizacoes + ch.n_desmobilizacoes,
                "custo_standby": round(ch.custo_standby, 2),
            }
        )
    rows.sort(key=lambda r: (-r["n_atividades"], r["cadeia_id"]))
    columns = [
        {"id": "cadeia_id", "label": "Cadeia", "dtype": "str", "role": "class"},
        {"id": "tipo_id", "label": "Tipo", "dtype": "str", "role": "series"},
        {"id": "atividades", "label": "Atividades perpetuadas", "dtype": "str", "role": "x"},
        {"id": "semanas_ativas", "label": "Ativas", "dtype": "int", "role": "value"},
        {"id": "semanas_ociosas", "label": "Ociosas", "dtype": "int", "role": "value"},
        {"id": "n_mob_demob", "label": "Mob+Demob", "dtype": "int", "role": "value"},
        {"id": "custo_standby", "label": "Standby (R$)", "dtype": "float", "role": "value"},
    ]
    multi = [r for r in rows if r["n_atividades"] > 1]
    narrativa = [
        f"{len(rows)} cadeia(s) de perpetuação; {len(multi)} agregam ≥2 atividades com frota mantida "
        "entre elas (1 mob + 1 demob por cadeia, evitando remobilização)."
    ]
    for r in multi[:4]:
        narrativa.append(
            f"{r['cadeia_id']} ({r['tipo_id']}): {r['atividades']} — {r['semanas_ativas']} sem. ativas, "
            f"{r['semanas_ociosas']} ociosas, standby {_fmt(r['custo_standby'])}."
        )
    return columns, rows, narrativa, {"n_cadeias": len(rows), "n_cadeias_multi": len(multi)}
