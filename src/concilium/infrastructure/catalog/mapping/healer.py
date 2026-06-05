"""Normalização de IDs de insumos e chaves 3NF no catálogo.

Migrado de scripts/heal_catalog.py
"""

from __future__ import annotations

import json
from pathlib import Path

_DEFAULT_ROOT = Path(__file__).resolve().parents[5]


def _heal_producoes(cat_root: Path, id_map: dict, remap_funcoes, remap_equipamentos) -> None:
    for f in (cat_root / "producoes").glob("*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        equipe = data.pop("composicao_padrao_equipe", None) or data.get("equipe")
        if equipe:
            remap_funcoes(equipe)
            remap_equipamentos(equipe)
            data["equipe"] = equipe
        f.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _heal_cpus(cat_root: Path, id_map: dict, remap_funcoes, remap_equipamentos) -> None:
    for f in (cat_root / "cpus").glob("*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        for item in data.get("composicao_itens", []):
            iid = item.get("insumo_id", "")
            item["insumo_id"] = id_map.get(iid) or id_map.get(f"MA-{iid}", iid)
        equipe = data.pop("composicao_padrao_equipe", None) or data.get("equipe")
        if equipe:
            remap_funcoes(equipe)
            remap_equipamentos(equipe)
            pid = data.get("producao_id")
            if pid:
                data.pop("equipe", None)
            else:
                data["equipe"] = equipe
        f.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def heal_catalog(catalog_root: Path | None = None) -> str:
    """Normaliza IDs de insumos (MO-, EQ-, MA-) e chaves 3NF no catálogo.

    Args:
        catalog_root: raiz do catálogo (padrão: config/catalogos/mendeslobo)

    Returns:
        Mensagem de conclusão.
    """
    cat_root = catalog_root or (_DEFAULT_ROOT / "config" / "catalogos" / "mendeslobo")

    id_map: dict[str, str] = {}
    for folder, prefix in (("mao_obra", "MO-"), ("equipamento", "EQ-"), ("material", "MA-")):
        d = cat_root / "insumos" / folder
        if d.exists():
            for f in d.glob("*.json"):
                clean_id = f.stem.replace(prefix, "")
                id_map[clean_id] = f.stem
                id_map[f.stem] = f.stem

    def _remap_funcoes(equipe: dict) -> None:
        for func in equipe.get("funcoes", []):
            fid = func.get("funcao_id", "")
            func["funcao_id"] = id_map.get(fid) or id_map.get(f"MO-{fid}", fid)

    def _remap_equipamentos(equipe: dict) -> None:
        for equip in equipe.get("equipamentos", []):
            eid = equip.get("equip_id", "")
            equip["equip_id"] = id_map.get(eid) or id_map.get(f"EQ-{eid}", eid)

    _heal_producoes(cat_root, id_map, _remap_funcoes, _remap_equipamentos)
    _heal_cpus(cat_root, id_map, _remap_funcoes, _remap_equipamentos)
    return "Cura concluída. Todas as referências e chaves 3NF foram normalizadas."
