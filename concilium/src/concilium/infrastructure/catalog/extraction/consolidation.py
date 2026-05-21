"""Consolida referÃªncia com dados de MO, equipamentos, material e CPUs do canonical."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DEFAULT_ROOT = Path(__file__).resolve().parents[5]


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _find_project_dir(slug: str, root: Path) -> Path | None:
    bench_data = root / "benchmarks" / "data"
    projects_root = root / "projetos"

    ref_path = bench_data / slug / "referencia.json"
    if not ref_path.exists():
        return None
    ref = _load_json(ref_path)
    project_name = ref.get("projeto")
    if not project_name:
        return None

    for d in projects_root.iterdir():
        if not d.is_dir():
            continue
        meta_path = d / "meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = _load_json(meta_path)
        except Exception:
            continue
        if meta.get("nome") == project_name:
            return d
    return None


def consolidate_reference(slug: str, root: Path | None = None) -> dict[str, Any]:
    """Consolida referÃªncia de um benchmark com dados de MO/equipes/planejamento do canonical.

    Retorna a referÃªncia enriquecida com dados reais do engine.
    """
    r = root or _DEFAULT_ROOT
    ref = _load_json(r / "benchmarks" / "data" / slug / "referencia.json")

    project_dir = _find_project_dir(slug, r)
    if not project_dir:
        return ref

    canonical = _load_json(project_dir / "v1" / "canonical.json")

    equipes_detalhes = [
        {
            "equipe_id": eq.get("equipe_id"),
            "item_id": eq.get("item_id"),
            "cpu_id": eq.get("cpu_id"),
            "nome": eq.get("nome"),
            "funcoes": eq.get("funcoes") or [],
            "equipamentos": eq.get("equipamentos") or [],
            "custo_total": eq.get("custo_total"),
            "custo_mao_obra_mensal": eq.get("custo_mao_obra_mensal"),
            "custo_equipamentos_mensal": eq.get("custo_equipamentos_mensal"),
            "custo_combustivel_total_mensal": eq.get("custo_combustivel_total_mensal"),
            "custo_material_mensal": eq.get("custo_material_mensal"),
            "quantitativo": eq.get("quantitativo"),
        }
        for eq in (canonical.get("equipes_diretas") or [])
    ]

    planejamento_detalhes = [
        {
            "item_id": p.get("item_id"),
            "descricao": p.get("descricao"),
            "quantitativo": p.get("quantitativo"),
            "subtotal_sem_bdi": p.get("subtotal", {}).get("sem_bdi"),
            "subtotal_com_bdi": p.get("subtotal", {}).get("com_bdi"),
        }
        for p in (canonical.get("planejamento") or [])
    ]

    return {
        **ref,
        "equipes_detalhadas": equipes_detalhes,
        "planejamento_detalhado": planejamento_detalhes,
        "_fonte": "canonical_consolidado",
    }
