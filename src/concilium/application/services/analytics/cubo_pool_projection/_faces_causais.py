"""Projeções (faces) do Cubo de Pool Instancial — ADR-086 Fases 3-4.

Faces causais/estruturais (causa do custo, economia de pool, cadeia de perpetuação).
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import TypedDict

from concilium.domain.models.canonical import CustoParticionadoItem, RecursoContrato

from ._shared import _fmt


def _iter_particoes(
    contratos: Sequence[RecursoContrato],
) -> Iterator[tuple[RecursoContrato, CustoParticionadoItem]]:
    for c in contratos:
        for p in c.particao_por_item:
            yield c, p


class _CausaCustoRow(TypedDict):
    atividade_id: str
    produtivo_exclusivo: float
    produtivo_compartilhado: float
    ocioso_imputado: float
    mob_demob_imputado: float
    total_imputado: float
    predecessor_critico: str
    overlap_semanas: float


def _face_causa_custo(cubo, contratos, cadeias, *, top_n=300, **_):
    rows: list[_CausaCustoRow] = []
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


def _row_economia_pool(p, baseline_por_item: dict, baseline_source_by_item: dict) -> dict:
    """Monta uma linha de economia de pool para uma partição, com os campos derivados."""
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
    eco = round(aut - inst, 2)
    eco_prod = round(aut - inst_prod, 2)
    return {
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


def _rows_economia_pool(contratos, baseline_por_item: dict, baseline_source_by_item: dict) -> tuple[list, dict]:
    """Constrói as rows de economia de pool e acumula totais/contadores."""
    rows = []
    tot_aut = tot_inst = tot_inst_prod = tot_burden = 0.0
    sem_baseline = 0
    fallback_count = 0
    for _c, p in _iter_particoes(contratos):
        row = _row_economia_pool(p, baseline_por_item, baseline_source_by_item)
        if row["custo_autonomo"] <= 0:
            sem_baseline += 1
        if row["baseline_source"] != "planejamento_sem_bdi":
            fallback_count += 1
        tot_aut += row["custo_autonomo"]
        tot_inst += row["custo_instancial"]
        tot_inst_prod += row["custo_instancial_produtivo"]
        tot_burden += row["burden_pool"]
        rows.append(row)
    rows.sort(key=lambda r: -r["economia"])
    totais = {
        "tot_aut": tot_aut,
        "tot_inst": tot_inst,
        "tot_inst_prod": tot_inst_prod,
        "tot_burden": tot_burden,
        "sem_baseline": sem_baseline,
        "fallback_count": fallback_count,
    }
    return rows, totais


def _narrativa_economia_pool(totais: dict, eco_total: float, eco_prod_total: float) -> list[str]:
    tot_aut = totais["tot_aut"]
    narrativa = [
        f"Baseline homogênea (planejamento sem BDI) {_fmt(tot_aut)} vs. instancial (pool) {_fmt(totais['tot_inst'])} "
        f"→ economia líquida {_fmt(eco_total)} ({(eco_total / tot_aut * 100) if tot_aut else 0:.1f}%).",
        "Economia sempre apresentada contra baseline homogênea explícita no mesmo referencial do planejamento.",
        f"Leitura operacional: instancial produtivo {_fmt(totais['tot_inst_prod'])} + burden de pool "
        f"(ocioso+mob/demob) {_fmt(totais['tot_burden'])}.",
        f"Economia produtiva (sem burden): {_fmt(eco_prod_total)} "
        f"({(eco_prod_total / tot_aut * 100) if tot_aut else 0:.1f}%).",
    ]
    if totais["fallback_count"]:
        narrativa.append(
            f"⚠ {totais['fallback_count']} atividade(s) usam fallback operacional "
            "por ausência de baseline de planejamento consolidado."
        )
    if eco_total < 0:
        narrativa.append(
            "Economia negativa: o pool ficou acima da baseline homogênea. Em obras sequenciais sem compartilhamento "
            "efetivo entre fases, isso tende a refletir burden contratual frente ao orçamento, "
            "não ganho operacional perdido."
        )
    if totais["sem_baseline"]:
        narrativa.append(f"⚠ {totais['sem_baseline']} atividade(s) sem baseline disponível (economia não calculável).")
    return narrativa


def _face_economia_pool(
    cubo, contratos, cadeias, *, top_n=300, baseline_por_item=None, baseline_source_by_item=None, **_
):
    baseline_por_item = baseline_por_item or {}
    baseline_source_by_item = baseline_source_by_item or {}
    rows, totais = _rows_economia_pool(contratos, baseline_por_item, baseline_source_by_item)
    columns = [
        {"id": "atividade_id", "label": "Atividade", "dtype": "str", "role": "x"},
        {"id": "custo_autonomo", "label": "Baseline homogênea (R$)", "dtype": "float", "role": "series"},
        {"id": "custo_instancial", "label": "Instancial (R$)", "dtype": "float", "role": "series"},
        {"id": "economia", "label": "Economia (R$)", "dtype": "float", "role": "value"},
        {"id": "economia_pct", "label": "Economia (%)", "dtype": "float", "role": "value"},
    ]
    eco_total = round(totais["tot_aut"] - totais["tot_inst"], 2)
    eco_prod_total = round(totais["tot_aut"] - totais["tot_inst_prod"], 2)
    narrativa = _narrativa_economia_pool(totais, eco_total, eco_prod_total)
    return (
        columns,
        rows,
        narrativa,
        {
            "custo_autonomo_total": round(totais["tot_aut"], 2),
            "custo_instancial_total": round(totais["tot_inst"], 2),
            "custo_instancial_produtivo_total": round(totais["tot_inst_prod"], 2),
            "burden_pool_total": round(totais["tot_burden"], 2),
            "economia_total": eco_total,
            "economia_produtiva_total": eco_prod_total,
            "itens_sem_baseline": totais["sem_baseline"],
            "baseline_kind": "planejamento_sem_bdi",
            "itens_fallback_operacional": totais["fallback_count"],
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


