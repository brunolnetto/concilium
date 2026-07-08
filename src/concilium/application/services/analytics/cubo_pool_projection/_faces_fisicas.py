"""Projeções (faces) do Cubo de Pool Instancial — ADR-086 Fases 3-4.

Faces físicas (utilização temporal, custo por estado, ciclo de vida, atividade↔instância).
"""

from __future__ import annotations

from ._shared import _COMP_LABEL, _ESTADO_LABEL, _count_mob_demob_por_periodo, _fmt


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
        narrativa.append(
            "Combustível aparece zerado nesta execução (sem custo de diesel consolidado no pool instancial)."
        )
    if mat_total <= 0.0:
        narrativa.append("Material aparece zerado nesta execução do pool instancial.")
    return columns, rows, narrativa, {}


def _face_ciclo_vida(cubo, contratos, cadeias, *, top_n=300, **_):
    cv = cubo.ciclo_vida_instancias()
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
            f"{r['instancia_id']}: mobilizada na sem. {r['semana_mob']}, "
            f"{r['prod_w']} sem. produtivas{idle_txt}{off_txt}. "
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


