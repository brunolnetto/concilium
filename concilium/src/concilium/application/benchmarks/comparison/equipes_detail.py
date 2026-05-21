"""ComposiÃ§Ã£o detalhada de equipes: catÃ¡logo esperado vs. alocado no engine."""

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


def build_equipes_detail(slug: str, root: Path | None = None) -> dict[str, Any]:
    """Retorna equipes com discrepÃ¢ncias entre catÃ¡logo (esperado) e engine (alocado).

    Args:
        slug: ex. "CTC"
        root: raiz do repositÃ³rio
    """
    r = root or _DEFAULT_ROOT
    bench_root = r / "benchmarks" / "data"
    cpus_dir = r / "config" / "catalogos" / "mendeslobo" / "cpus"

    referencia = _load_json(bench_root / slug / "referencia.json")
    eap_itens = {item.get("item_id"): item for item in (referencia.get("eap") or [])}

    equipes_com_discrepancias = []
    for eq_ref in referencia.get("equipes_detalhadas") or []:
        cpu_id = eq_ref.get("cpu_id")
        item_id = eq_ref.get("item_id")
        eap_item = eap_itens.get(item_id, {})

        cpu_cat = _load_cpu(cpu_id, cpus_dir) if cpu_id else {}
        cpu_equipe = cpu_cat.get("equipe", {})

        funcoes_ref = eq_ref.get("funcoes", [])
        equipamentos_ref = eq_ref.get("equipamentos", [])
        funcoes_esperadas = cpu_equipe.get("funcoes", [])
        equipamentos_esperados = cpu_equipe.get("equipamentos", [])

        if (len(funcoes_ref) == 0 and len(funcoes_esperadas) > 0) or (
            len(equipamentos_ref) == 0 and len(equipamentos_esperados) > 0
        ):
            equipes_com_discrepancias.append(
                {
                    "item_id": item_id,
                    "equipe_id": eq_ref.get("equipe_id"),
                    "nome": eq_ref.get("nome"),
                    "cpu_id": cpu_id,
                    "eap_descricao": eap_item.get("descricao"),
                    "eap_quantitativo": eap_item.get("quantitativo"),
                    "eap_unidade": eap_item.get("unidade"),
                    "alocado_no_engine": {
                        "funcoes": funcoes_ref,
                        "equipamentos": equipamentos_ref,
                        "custo_total": eq_ref.get("custo_total"),
                        "custo_mao_obra_mensal": eq_ref.get("custo_mao_obra_mensal"),
                        "custo_equipamentos_mensal": eq_ref.get("custo_equipamentos_mensal"),
                    },
                    "esperado_no_catalogo": {
                        "funcoes": funcoes_esperadas,
                        "equipamentos": equipamentos_esperados,
                        "composicao_itens": cpu_cat.get("composicao_itens", []),
                    },
                }
            )

    return {
        "slug": slug,
        "total_equipes_com_discrepancias": len(equipes_com_discrepancias),
        "equipes": equipes_com_discrepancias,
    }
