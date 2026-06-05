#!/usr/bin/env python3
"""Controlled pruning for benchmark referencia.json files.

Keeps only fields required for deterministic benchmark execution:
- project identity and date window
- EAP item list (from cpus.itens_eap)
- cronograma weeks/activities required for team sizing
- BDI aggregate rates used by spec_loader
- indirect cost blocks used by spec_loader
- benchmark confrontation reference targets

Usage:
    python scripts/prune_benchmark_reference.py AGIS
    python scripts/prune_benchmark_reference.py AGIS --dry-run
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BENCH_ROOT = ROOT / "benchmarks" / "data"


def _pick_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _build_min_eap(ref: dict[str, Any], scheduled_item_ids: set[str] | None = None) -> dict[str, Any]:
    itens = (ref.get("cpus") or {}).get("itens_eap") or []
    out: list[dict[str, Any]] = []
    for i in itens:
        if not isinstance(i, dict):
            continue
        has_cronograma = i.get("has_cronograma")
        item_id = i.get("item_id")
        if has_cronograma is None and scheduled_item_ids is not None and item_id is not None:
            has_cronograma = str(item_id) in scheduled_item_ids

        item = {
            "item_id": i.get("item_id"),
            "ordem": i.get("ordem"),
            "item_planilha": i.get("item_planilha"),
            "cpu_id": i.get("cpu_id"),
            "descricao": i.get("descricao"),
            "unidade": i.get("unidade"),
            "quantitativo": i.get("quantitativo"),
            "has_cronograma": has_cronograma,
        }
        out.append({k: v for k, v in item.items() if v is not None})
    return {"itens_eap": out}




def _build_min_cronograma(ref: dict[str, Any]) -> dict[str, Any] | None:
    cron = ref.get("cronograma")
    if not isinstance(cron, dict):
        return None

    semanas = cron.get("semanas") if isinstance(cron.get("semanas"), dict) else {}
    semanas_out: dict[str, dict[str, Any]] = {}
    for key, row in semanas.items():
        if not isinstance(row, dict):
            continue
        slim = {
            "data_inicio": row.get("data_inicio"),
            "data_fim": row.get("data_fim"),
        }
        semanas_out[str(key)] = {k: v for k, v in slim.items() if v is not None}

    atividades = cron.get("atividades") if isinstance(cron.get("atividades"), list) else []
    atividades_out: list[dict[str, Any]] = []
    atividades_execucao_ids: list[str] = []
    atividades_planejamento_ids: list[str] = []
    for a in atividades:
        if not isinstance(a, dict):
            continue
        semanas_a = a.get("semanas") if isinstance(a.get("semanas"), dict) else {}
        semanas_a_out: dict[str, dict[str, Any]] = {}
        for w, wr in semanas_a.items():
            if isinstance(wr, dict):
                n = wr.get("num_equipes")
                if n is not None:
                    semanas_a_out[str(w)] = {"num_equipes": n}
        item = {
            "item_id": a.get("item_id"),
            "activity_id": a.get("activity_id"),
            "quantitativo": a.get("quantitativo"),
            "producao_diaria": a.get("producao_diaria"),
            "semanas": semanas_a_out,
        }
        item = {k: v for k, v in item.items() if v is not None and not (k == "semanas" and not v)}
        if item:
            atividades_out.append(item)

            item_id = item.get("item_id") or item.get("activity_id")
            if item_id is not None:
                has_execucao = False
                semanas_item = item.get("semanas") if isinstance(item.get("semanas"), dict) else {}
                for wr in semanas_item.values():
                    if isinstance(wr, dict):
                        n = wr.get("num_equipes")
                        if isinstance(n, (int, float)) and n > 0:
                            has_execucao = True
                            break
                if has_execucao:
                    atividades_execucao_ids.append(str(item_id))
                else:
                    atividades_planejamento_ids.append(str(item_id))

    grupos_execucao: list[dict[str, Any]] = []
    equipes_mapping = ref.get("equipes_eap_mapping")
    if isinstance(equipes_mapping, dict):
        exec_set = set(atividades_execucao_ids)
        for equipe_id, item_ids in equipes_mapping.items():
            if not isinstance(item_ids, list):
                continue
            ids_norm = [str(iid) for iid in item_ids if iid is not None]
            ids_exec = [iid for iid in ids_norm if iid in exec_set]
            ids_fin = [iid for iid in ids_norm if iid not in exec_set]
            grupos_execucao.append(
                {
                    "grupo_id": str(equipe_id),
                    "item_ids": ids_norm,
                    "item_ids_execucao": ids_exec,
                    "item_ids_financeiro": ids_fin,
                    "requires_merge_schedule": bool(ids_fin and not ids_exec),
                }
            )

    out = {
        "semanas": semanas_out,
        "atividades": atividades_out,
        "atividades_execucao_ids": atividades_execucao_ids,
        "atividades_planejamento_ids": atividades_planejamento_ids,
        "resumo_coverage": {
            "total_atividades": len(atividades_out),
            "total_execucao": len(atividades_execucao_ids),
            "total_planejamento": len(atividades_planejamento_ids),
        },
    }
    if grupos_execucao:
        out["grupos_execucao"] = grupos_execucao
    return out


def _build_min_bdi(ref: dict[str, Any]) -> dict[str, Any] | None:
    bdi = ref.get("bdi")
    if not isinstance(bdi, dict):
        return None

    stats = bdi.get("estatisticas_componentes") if isinstance(bdi.get("estatisticas_componentes"), dict) else None
    if stats:
        out_stats: dict[str, dict[str, float]] = {}
        for key in ("materiais", "material", "diesel", "mao_obra", "equipamentos", "servicos", "indireto"):
            row = stats.get(key)
            if isinstance(row, dict):
                media = _pick_float(row.get("media"))
                if media is not None:
                    out_stats[key] = {"media": media}
        if out_stats:
            return {"estatisticas_componentes": out_stats}

    por_item = bdi.get("por_item") if isinstance(bdi.get("por_item"), list) else []
    sample = por_item[0] if por_item and isinstance(por_item[0], dict) else {}
    bdi_item = sample.get("bdi") if isinstance(sample.get("bdi"), dict) else {}
    if not bdi_item:
        return None

    # Build a synthetic stat block from first item for deterministic replay.
    out_stats: dict[str, dict[str, float]] = {}
    mapping = {
        "material": "material",
        "diesel": "diesel",
        "mao_obra": "mao_obra",
        "equipamentos": "equipamentos",
        "servicos": "servicos",
        "indireto": "indireto",
    }
    for src, dst in mapping.items():
        value = _pick_float(bdi_item.get(src))
        if value is not None:
            out_stats[dst] = {"media": value}
    if "material" in out_stats and "materiais" not in out_stats:
        out_stats["materiais"] = {"media": out_stats["material"]["media"]}

    return {"estatisticas_componentes": out_stats} if out_stats else None


def _build_min_indiretos(ref: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    detail = ref.get("indiretos_detalhamento")
    if not isinstance(detail, dict):
        detail = ref.get("indiretos_detalhados")

    detalhe_out: dict[str, dict[str, float]] = {}
    raw_rows: list[dict[str, Any]] = []

    if isinstance(detail, dict):
        for cat, row in detail.items():
            if not isinstance(row, dict):
                continue
            mensal = _pick_float(row.get("custo_fixo_mensal_total") or row.get("mao_de_obra_mensal"))
            total = _pick_float(row.get("custo_fixo_total") or row.get("custo_total"))
            cat_key = str(cat).upper()

            out_row: dict[str, float] = {}
            if mensal is not None:
                out_row["custo_fixo_mensal_total"] = mensal
            if total is not None:
                out_row["custo_fixo_total"] = total
            if out_row:
                detalhe_out[cat_key] = out_row

            if total is not None:
                raw_rows.append({"categoria": cat_key, "custo_total": total, "permanencia_meses": None})
            elif mensal is not None:
                raw_rows.append({"categoria": cat_key, "custo_total": mensal, "permanencia_meses": 1.0})

    indiretos_out = {"raw_indiretos": raw_rows} if raw_rows else None
    detalhe_out_final = detalhe_out if detalhe_out else None
    return detalhe_out_final, indiretos_out


def _build_min_resultado(ref: dict[str, Any]) -> dict[str, Any]:
    resultado = ref.get("resultado") if isinstance(ref.get("resultado"), dict) else {}
    confronto_ref = resultado.get("benchmark_confronto_referencia") if isinstance(resultado.get("benchmark_confronto_referencia"), dict) else {}

    venda = ((resultado.get("canonical") or {}).get("venda") or {}) if isinstance(resultado.get("canonical"), dict) else {}
    bdi_lucro = _pick_float(resultado.get("bdi_lucro_impostos"))
    if bdi_lucro is None:
        bdi_lucro = _pick_float(venda.get("bdi_lucro_impostos"))
    if bdi_lucro is None:
        bdi_lucro = 0.15

    return {
        "bdi_lucro_impostos": bdi_lucro,
        "benchmark_confronto_referencia": {
            "custo_direto": confronto_ref.get("custo_direto"),
            "custo_indireto": confronto_ref.get("custo_indireto"),
            "custo_total": confronto_ref.get("custo_total"),
            "preco_venda": confronto_ref.get("preco_venda"),
        },
    }


def prune_reference(ref: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}

    for key in ("id", "projeto", "data_inicio", "data_termino", "localizacao", "coordenadas", "regime_trabalho"):
        if key in ref:
            out[key] = ref.get(key)

    cron = _build_min_cronograma(ref)

    scheduled_item_ids: set[str] = set()
    if cron and isinstance(cron.get("atividades_execucao_ids"), list):
        scheduled_item_ids = {str(item_id) for item_id in cron.get("atividades_execucao_ids", [])}

    cpus = _build_min_eap(ref, scheduled_item_ids=scheduled_item_ids)
    if cpus.get("itens_eap"):
        out["cpus"] = cpus

    if cron:
        out["cronograma"] = cron

    bdi = _build_min_bdi(ref)
    if bdi:
        out["bdi"] = bdi

    ind_det, ind_raw = _build_min_indiretos(ref)
    if ind_det:
        out["indiretos_detalhamento"] = ind_det
    if ind_raw:
        out["indiretos"] = ind_raw

    out["resultado"] = _build_min_resultado(ref)

    return out


def _summary(ref: dict[str, Any]) -> dict[str, int]:
    cpus = (ref.get("cpus") or {}).get("itens_eap") or []
    atividades = (ref.get("cronograma") or {}).get("atividades") or []
    semanas = (ref.get("cronograma") or {}).get("semanas") or {}
    return {
        "cpus_itens_eap": len(cpus),
        "cronograma_atividades": len(atividades),
        "cronograma_semanas": len(semanas),
        "top_level_keys": len(ref.keys()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Prune benchmark referencia.json keeping minimal deterministic fields.")
    parser.add_argument("slug", help="Benchmark slug, e.g. AGIS")
    parser.add_argument("--dry-run", action="store_true", help="Do not write changes")
    args = parser.parse_args()

    slug = args.slug.upper()
    ref_path = BENCH_ROOT / slug / "referencia.json"
    if not ref_path.exists():
        raise SystemExit(f"referencia.json not found: {ref_path}")

    original = json.loads(ref_path.read_text(encoding="utf-8"))
    pruned = prune_reference(original)

    before = _summary(original)
    after = _summary(pruned)

    if args.dry_run:
        print("[DRY-RUN] No file written")
    else:
        timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = ref_path.with_name(f"referencia.backup.{timestamp}.json")
        backup_path.write_text(json.dumps(original, ensure_ascii=False, indent=2), encoding="utf-8")
        ref_path.write_text(json.dumps(pruned, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Backup: {backup_path}")
        print(f"Pruned : {ref_path}")

    print("Before:", before)
    print("After :", after)


if __name__ == "__main__":
    main()
