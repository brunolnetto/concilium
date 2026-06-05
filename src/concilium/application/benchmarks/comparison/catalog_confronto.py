"""AnÃ¡lise de confronto de catÃ¡logo para um ou todos os benchmarks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DEFAULT_ROOT = Path(__file__).resolve().parents[5]


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _acc_process_cpu_refs(confronto: dict) -> list:
    """Retorna lista de cpu_ids nao encontrados no catalogo."""
    result = []
    for cpu_id, cpu_def in (confronto.get("cpu_referencias", {}).get("catalog_cpus") or {}).items():
        if cpu_def.get("status") == "NAO_ENCONTRADO_NO_CATALOGO":
            result.append(cpu_id)
    return result


def _acc_process_equipes(confronto: dict) -> tuple:
    """Classifica equipes por tipo de discrepancia (funcoes, equipamentos, custo zero)."""
    funcoes_vazias = []
    equipamentos_vazios = []
    zeradas = []
    for eq in confronto.get("equipes_confronto", {}).get("confronto") or []:
        disc = eq.get("discrepancias", {})
        if disc.get("funcoes_vazia"):
            funcoes_vazias.append({"item_id": eq.get("item_id"), "cpu_id": eq.get("cpu_id")})
        if disc.get("equipamentos_vazia"):
            equipamentos_vazios.append({"item_id": eq.get("item_id"), "cpu_id": eq.get("cpu_id")})
        if disc.get("custo_zero"):
            zeradas.append({"item_id": eq.get("item_id"), "nome": eq.get("nome")})
    return funcoes_vazias, equipamentos_vazios, zeradas


def analyze_catalog_confronto(slug: str, root: Path | None = None) -> dict[str, Any]:
    """Analisa o arquivo confronto_catalogo.json de um benchmark e retorna issues estruturadas."""
    r = root or _DEFAULT_ROOT
    confronto = _load_json(r / "benchmarks" / "data" / slug / "confronto_catalogo.json")
    if not confronto:
        return {}

    func_vaz, equip_vaz, zeradas = _acc_process_equipes(confronto)
    issues: dict[str, Any] = {
        "slug": slug,
        "cpus_nao_encontradas": _acc_process_cpu_refs(confronto),
        "equipes_com_funcoes_vazias": func_vaz,
        "equipes_com_equipamentos_vazios": equip_vaz,
        "equipes_zeradas": zeradas,
        "planejamento_zerados": [],
        "bdi_mismatch": False,
    }

    for item in confronto.get("planejamento_confronto", {}).get("confronto") or []:
        if item.get("engine_zerado"):
            issues["planejamento_zerados"].append(item.get("item_id"))

    return issues


def consolidate_all(root: Path | None = None) -> dict[str, Any]:
    """Consolida confrontos de catÃ¡logo de todos os benchmarks disponÃ­veis."""
    r = root or _DEFAULT_ROOT
    bench_root = r / "benchmarks" / "data"
    results = []
    for d in sorted(bench_root.iterdir()):
        if not d.is_dir():
            continue
        issues = analyze_catalog_confronto(d.name, root=r)
        if issues:
            results.append(issues)

    total_cpus_faltando = sum(len(i.get("cpus_nao_encontradas", [])) for i in results)
    total_equipes_zeradas = sum(len(i.get("equipes_zeradas", [])) for i in results)

    return {
        "total_benchmarks": len(results),
        "total_cpus_nao_encontradas": total_cpus_faltando,
        "total_equipes_zeradas": total_equipes_zeradas,
        "benchmarks": results,
    }
