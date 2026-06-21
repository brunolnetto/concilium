from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _load_skill04():
    root = Path(__file__).resolve().parents[2]
    mod_path = root / "src/concilium/application/skills/manifests/04-cronograma/skill.py"
    spec = importlib.util.spec_from_file_location("skill04_fungibilidade", mod_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_enrich_spec_resources_agrega_fases_em_tipo_fungivel():
    mod = _load_skill04()
    spec = {
        "activities": [
            {"item_id": "eap-1_0", "ramp_params": {"n_max": 3}},
            {"item_id": "eap-1_1", "ramp_params": {"n_max": 6}},
        ]
    }
    canonical = SimpleNamespace(
        projeto=SimpleNamespace(regime_trabalho=SimpleNamespace(horas_dia=12, dias_semana=7)),
        eap=[
            SimpleNamespace(item_id="eap-1_0", cpu_id="CPU-REJEITO-COMP-EQ1", quantitativo=1000.0),
            SimpleNamespace(item_id="eap-1_1", cpu_id="CPU-REJEITO-COMP-EQ2", quantitativo=1000.0),
        ],
    )
    cpu_lookup = {
        "CPU-REJEITO-COMP-EQ1": {"producao_id_ref": "PROD-1"},
        "CPU-REJEITO-COMP-EQ2": {"producao_id_ref": "PROD-2"},
    }
    producao_lookup = {
        "PROD-1": {"valor_horario": 10.0, "composicao_padrao_equipe": {"funcoes": [{"funcao_id": "F1"}]}},
        "PROD-2": {"valor_horario": 10.0, "composicao_padrao_equipe": {"funcoes": [{"funcao_id": "F1"}]}},
    }
    validacoes = []

    mod._enrich_spec_resources_from_catalog(spec, canonical, cpu_lookup, producao_lookup, 20, validacoes)

    acts = {a["item_id"]: a for a in spec["activities"]}
    tipo_0 = next(iter(acts["eap-1_0"]["required_resources"]))
    tipo_1 = next(iter(acts["eap-1_1"]["required_resources"]))
    assert tipo_0 == tipo_1
    assert tipo_0.startswith("EQUIPE-COMP-")
    assert acts["eap-1_0"]["required_resources"] == {tipo_0: 3}
    assert acts["eap-1_1"]["required_resources"] == {tipo_1: 6}
