"""Projeções (faces) do Cubo de Pool Instancial — ADR-086 Fases 3-4.

Espelha o contrato de projeção do ADR-069 (CuboAnalitico):
``{face, granularidade, unit_type, chart_hint, columns[], rows[], operator_meta, totais, narrativa[]}``.

Separação rígida (ADR-086 H4):
  - Faces **físicas** (do CuboPoolInstancial): o que cada slot fez — nunca imputam idle/mob a atividade.
  - Faces **causais/estruturais** (de CustoParticionadoItem / CadeiaPerpetuacao): a quem imputamos,
    sempre com o baseline autônomo ao lado.

Cada face inclui ``narrativa``: frases descritivas geradas dos próprios dados, com caveats explícitos.
"""

from __future__ import annotations

from typing import Any

from concilium.domain.services.cubo_pool_builder import (
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

    # Baseline autônomo autoritativo por item (ADR-085): EquipeDireta.custo_total_autonomo.
    autonomo_por_item: dict[str, float] = {}
    for eq in getattr(canonical_in, "equipes_diretas", None) or []:
        iid = getattr(eq, "item_id", "")
        if iid:
            autonomo_por_item[iid] = float(getattr(eq, "custo_total_autonomo", 0.0) or 0.0)

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
        autonomo_por_item=autonomo_por_item,
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
    rows = []
    for p in periodos:
        rows.append(
            {
                "periodo": p,
                "prod": util.get((p, "prod"), 0),
                "idle": util.get((p, "idle"), 0),
                "off": util.get((p, "off"), 0),
            }
        )
    columns = [
        {"id": "periodo", "label": "Período", "dtype": "str", "role": "x"},
        {"id": "prod", "label": "Produtivo", "dtype": "int", "role": "series"},
        {"id": "idle", "label": "Ocioso", "dtype": "int", "role": "series"},
        {"id": "off", "label": "Desmobilizado", "dtype": "int", "role": "series"},
    ]
    sem = cubo.semanas_por_estado()
    total_slot_sem = sum(sem.values()) or 1
    narrativa = [
        f"Slot-semanas: {sem['prod']} produtivas, {sem['idle']} ociosas, {sem['off']} desmobilizadas "
        f"(off = recurso liberado, não faturado — {sem['off'] / total_slot_sem * 100:.0f}% do total).",
    ]
    if sem["idle"]:
        narrativa.append(
            "Semanas ociosas mantêm MO integral (CLT) e equipamento a taxa de locação reduzida; "
            "combustível e material zerados (sem operação)."
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


def _face_economia_pool(cubo, contratos, cadeias, *, top_n=300, autonomo_por_item=None, **_):
    autonomo_por_item = autonomo_por_item or {}
    rows = []
    tot_aut = tot_inst = 0.0
    sem_baseline = 0
    for _c, p in _iter_particoes(contratos):
        inst = round(p.custo_total_particionado, 2)
        # Baseline autoritativo: EquipeDireta.custo_total_autonomo (ADR-085); fallback à partição.
        aut = round(autonomo_por_item.get(p.item_id, 0.0) or float(p.custo_total_autonomo or 0.0), 2)
        if aut <= 0:
            sem_baseline += 1
        eco = round(aut - inst, 2)
        tot_aut += aut
        tot_inst += inst
        rows.append(
            {
                "atividade_id": p.item_id,
                "custo_autonomo": aut,
                "custo_instancial": inst,
                "economia": eco,
                "economia_pct": round((eco / aut * 100) if aut > 0 else 0.0, 1),
                "baseline_disponivel": aut > 0,
            }
        )
    rows.sort(key=lambda r: -r["economia"])
    columns = [
        {"id": "atividade_id", "label": "Atividade", "dtype": "str", "role": "x"},
        {"id": "custo_autonomo", "label": "Autônomo (R$)", "dtype": "float", "role": "series"},
        {"id": "custo_instancial", "label": "Instancial (R$)", "dtype": "float", "role": "series"},
        {"id": "economia", "label": "Economia (R$)", "dtype": "float", "role": "value"},
        {"id": "economia_pct", "label": "Economia (%)", "dtype": "float", "role": "value"},
    ]
    eco_total = round(tot_aut - tot_inst, 2)
    narrativa = [
        f"Baseline autônomo {_fmt(tot_aut)} vs. instancial (pool) {_fmt(tot_inst)} → "
        f"economia líquida {_fmt(eco_total)} ({(eco_total / tot_aut * 100) if tot_aut else 0:.1f}%).",
        "Economia sempre apresentada contra o baseline autônomo explícito (ADR-086 H4).",
    ]
    if eco_total < 0:
        narrativa.append(
            "Economia negativa: o pool custa ~igual ao autônomo aqui — o ganho do pool é evitar a "
            "superestimação monolítica (span×pico), não reduzir o trabalho; gaps são liberados (off)."
        )
    if sem_baseline:
        narrativa.append(f"⚠ {sem_baseline} atividade(s) sem baseline autônomo disponível (economia não calculável).")
    return (
        columns,
        rows,
        narrativa,
        {
            "custo_autonomo_total": round(tot_aut, 2),
            "custo_instancial_total": round(tot_inst, 2),
            "economia_total": eco_total,
            "itens_sem_baseline": sem_baseline,
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
