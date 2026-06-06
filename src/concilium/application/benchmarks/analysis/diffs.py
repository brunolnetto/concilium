"""Diffs simples entre canonical e extracted_references (sem dependÃªncias pesadas)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DEFAULT_ROOT = Path(__file__).resolve().parents[5]


def _ce_compare_item(item_id: str, can_eq: dict, ref_eq: dict) -> list:
    """Compara um item de equipe e retorna suas discrepancias."""
    diffs = []
    can_func = len(can_eq.get("funcoes", []))
    ref_func = len(ref_eq.get("funcoes", []))
    if can_func != ref_func:
        diffs.append(
            {
                "item_id": item_id,
                "campo": "funcoes_count",
                "canonical": can_func,
                "referencia": ref_func,
                "delta": can_func - ref_func,
            }
        )
    can_eqp = len(can_eq.get("equipamentos", []))
    ref_eqp = len(ref_eq.get("equipamentos", []))
    if can_eqp != ref_eqp:
        diffs.append(
            {
                "item_id": item_id,
                "campo": "equipamentos_count",
                "canonical": can_eqp,
                "referencia": ref_eqp,
                "delta": can_eqp - ref_eqp,
            }
        )
    can_cost = can_eq.get("custo_total", 0.0)
    ref_cost = (ref_eq.get("custos") or {}).get("total", ref_eq.get("custo_total", 0.0))
    if abs(can_cost - ref_cost) > 0.01:
        diffs.append(
            {
                "item_id": item_id,
                "campo": "custo_total",
                "canonical": round(can_cost, 2),
                "referencia": round(ref_cost, 2),
                "delta": round(can_cost - ref_cost, 2),
            }
        )
    return diffs


def _compare_equipes(canonical_equipes: list, ref_equipes: list) -> list[dict[str, Any]]:
    can_dict = {eq["item_id"]: eq for eq in canonical_equipes if eq.get("item_id")}
    ref_dict = {eq.get("item_id"): eq for eq in ref_equipes if eq.get("item_id")}
    discrepancias: list[dict[str, Any]] = []
    for item_id, can_eq in can_dict.items():
        if item_id not in ref_dict:
            continue
        discrepancias.extend(_ce_compare_item(item_id, can_eq, ref_dict[item_id]))
    return discrepancias


def _find_benchmark_report(slug: str, root: Path) -> Path | None:
    """Localiza benchmark_report.json: caminho organizado primeiro, fallback histórico."""
    organized = root / "benchmarks" / "data" / slug.upper() / "artifacts" / "outputs" / "benchmark_report.json"
    if organized.exists():
        return organized
    for p in [root / f"benchmark_{slug.lower()}.json"] + list(root.glob(f"benchmark_{slug.lower()}*.json")):
        if p.exists():
            return p
    return None


def _gdfs_load_canonical(projeto_nome: str, r: Path) -> dict:
    """Localiza e carrega canonical.json do projeto pelo nome."""
    for d in (r / "projetos").iterdir():
        if not d.is_dir():
            continue
        meta_path = d / "meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if meta.get("nome") == projeto_nome:
            can_path = d / "v1" / "canonical.json"
            if can_path.exists():
                return json.loads(can_path.read_text(encoding="utf-8"))
            break
    return {}


def generate_diffs_for_slug(slug: str, root: Path | None = None) -> dict[str, Any] | None:
    """Gera diffs simples para um slug. Retorna None se extracted_references nao existir."""
    r = root or _DEFAULT_ROOT
    extracted_ref_path = r / "benchmarks" / "extracted_references" / f"iteracao_referencias_{slug.lower()}.json"

    if not extracted_ref_path.exists():
        return None

    with open(extracted_ref_path, encoding="utf-8") as f:
        extracted = json.load(f)

    bench_path = _find_benchmark_report(slug, r)
    if bench_path is None:
        return None

    with open(bench_path, encoding="utf-8") as f:
        bench = json.load(f)

    projeto_nome = bench.get("projeto") or slug
    canonical = _gdfs_load_canonical(projeto_nome, r)

    equipes_diffs = _compare_equipes(
        canonical.get("equipes_diretas", []),
        extracted.get("equipes", {}).get("equipes", []),
    )
    return {
        "slug": slug,
        "equipes": {"total": len(equipes_diffs), "discrepancias": equipes_diffs},
    }
