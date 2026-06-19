from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _load_skill05_helpers_a():
    root = Path(__file__).resolve().parents[2]
    mod_path = root / "src/concilium/application/skills/manifests/05-equipes-e-alocacao/_skill_helpers_a.py"
    spec = importlib.util.spec_from_file_location("skill05_helpers_a_fuel", mod_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_resolve_consumo_sem_override_faz_fallback_insumo():
    """Sem override (None), _resolve_consumo_equip usa o valor do insumo no catálogo."""
    mod = _load_skill05_helpers_a()
    atrib = {"consumo_litros_hora": 12.0}

    consumo, code = mod._resolve_consumo_equip(atrib, consumo_override_proj=None, consumo_override_cpu=None, preco_diesel=7.0)

    assert consumo == 12.0
    assert code == "VAL-EQUIP-COMB-02"


def test_resolve_consumo_override_zero_forca_sem_combustivel():
    """Override explícito de 0.0 força consumo=0.0 (equipamento sem combustível neste contexto).

    Para usar o valor do catálogo, passar None em vez de 0.0.
    """
    mod = _load_skill05_helpers_a()
    atrib = {"consumo_litros_hora": 12.0}

    consumo, code = mod._resolve_consumo_equip(atrib, consumo_override_proj=0.0, consumo_override_cpu=None, preco_diesel=7.0)

    assert consumo == 0.0
    assert code == "VAL-EQUIP-COMB-01"


def test_alias_enriquece_consumo_por_codigo_planilha_e_descricao():
    mod = _load_skill05_helpers_a()
    repo = SimpleNamespace(
        _insumos={
            "E0027": {
                "codigo": "E0027",
                "tipo": "EQUIPAMENTO",
                "descricao": "Rolo compactador liso",
                "atributos_especificos": {},
            },
            "EQ-ROLO-LISO": {
                "codigo": "EQ-ROLO-LISO",
                "tipo": "EQUIPAMENTO",
                "descricao": "Rolo compactador liso",
                "atributos_especificos": {
                    "codigo_planilha": "E0027",
                    "consumo_litros_hora": 7.0,
                    "tipo_combustivel": "Diesel S10",
                },
            },
        }
    )
    ctx = SimpleNamespace(repo=repo)

    attrs = mod._best_alias_equip_attrs(ctx, "E0027", "Rolo compactador liso")

    assert attrs.get("consumo_litros_hora") == 7.0
    assert attrs.get("tipo_combustivel") == "Diesel S10"
