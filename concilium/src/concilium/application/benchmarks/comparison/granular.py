"""ComparaÃ§Ã£o granular variÃ¡vel-a-variÃ¡vel: catÃ¡logo vs. engine."""

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


def _load_cpu(cpu_id: str, cpus_dir: Path) -> dict[str, Any]:
    return _load_json(cpus_dir / f"{cpu_id}.json")


def build_granular_comparison(slug: str, root: Path | None = None) -> dict[str, Any]:
    """ConstrÃ³i comparaÃ§Ã£o variÃ¡vel-a-variÃ¡vel para um benchmark.

    Args:
        slug: ex. "CTC"
        root: raiz do repositÃ³rio (padrÃ£o: detectado automaticamente)
    """
    r = root or _DEFAULT_ROOT
    bench_root = r / "benchmarks" / "data"
    cpus_dir = r / "config" / "catalogos" / "mendeslobo" / "cpus"

    referencia = _load_json(bench_root / slug / "referencia.json")
    extracao = _load_json(bench_root / slug / "extracao_intermediarios.json")

    eap_itens = {item.get("item_id"): item for item in (referencia.get("eap") or [])}
    equipes_ref = {eq.get("item_id"): eq for eq in (referencia.get("equipes_detalhadas") or [])}

    etapa_equipes = (extracao.get("etapas") or {}).get("03_equipes_e_alocacao", {})
    equipes_engine = {eq.get("item_id"): eq for eq in (etapa_equipes.get("equipes") or [])}

    etapa_planej = (extracao.get("etapas") or {}).get("04_planejamento_bdi", {})
    itens_zerados = {item.get("item_id"): item for item in (etapa_planej.get("itens_com_qtd_e_custo_zero") or [])}
    composicao_zerada = {
        item.get("item_id"): item for item in (extracao.get("disparidades") or {}).get("equipes_zeradas", [])
    }

    comparacao = []
    for eap_id, eap_item in eap_itens.items():
        cpu_id = eap_item.get("cpu_id")
        cpu_cat = _load_cpu(cpu_id, cpus_dir) if cpu_id else {}

        eq_ref = equipes_ref.get(eap_id, {})
        eq_engine = equipes_engine.get(eap_id, {})

        comparacao.append(
            {
                "item_id": eap_id,
                "cpu_id": cpu_id,
                "descricao": eap_item.get("descricao"),
                "catalogo": {
                    "producao_horaria": cpu_cat.get("producao_horaria"),
                    "unidade": cpu_cat.get("unidade"),
                    "funcoes_count": len((cpu_cat.get("equipe") or {}).get("funcoes", [])),
                    "equipamentos_count": len((cpu_cat.get("equipe") or {}).get("equipamentos", [])),
                    "composicao_count": len(cpu_cat.get("composicao_itens", [])),
                },
                "referencia": {
                    "funcoes_count": len(eq_ref.get("funcoes", [])),
                    "equipamentos_count": len(eq_ref.get("equipamentos", [])),
                    "custo_total": eq_ref.get("custo_total"),
                    "custo_mao_obra_mensal": eq_ref.get("custo_mao_obra_mensal"),
                    "custo_equipamentos_mensal": eq_ref.get("custo_equipamentos_mensal"),
                    "custo_combustivel_total_mensal": eq_ref.get("custo_combustivel_total_mensal"),
                },
                "engine": {
                    "funcoes_count": len(eq_engine.get("funcoes", [])),
                    "equipamentos_count": len(eq_engine.get("equipamentos", [])),
                    "custo_total": eq_engine.get("custo_total"),
                },
                "flags": {
                    "zerado_no_planejamento": eap_id in itens_zerados,
                    "composicao_zerada": eap_id in composicao_zerada,
                    "cpu_ausente_no_catalogo": not bool(cpu_cat),
                },
            }
        )

    return {"slug": slug, "comparacao": comparacao, "total": len(comparacao)}
