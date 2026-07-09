from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


def _load_helpers_a():
    root = Path(__file__).resolve().parents[2]
    helper = (
        root / "src/concilium/application/skills/manifests/10-relatorio-e-artefatos/_skill_helpers/__init__.py"
    )
    spec = importlib.util.spec_from_file_location(
        "_skill_helpers_a_09_graficos", helper, submodule_search_locations=[str(helper.parent)]
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_skill_helpers_a_09_graficos"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_bgs_accumulate_week_agrega_turnos_na_mesma_funcao_base():
    mod = _load_helpers_a()
    eq = SimpleNamespace(
        equipamentos=[],
        funcoes=[
            SimpleNamespace(
                descricao="Serra Verde — Operador de Escavadeira (Diurno, 12×36)",
                funcao_id="SV-P0040-D",
                num_pessoas=2.0,
            ),
            SimpleNamespace(
                descricao="Serra Verde — Operador de Escavadeira (Noturno, 12×36)",
                funcao_id="SV-P0040-N",
                num_pessoas=1.0,
            ),
        ],
    )
    dist = SimpleNamespace(num_equipes=1.0)
    equip_totals: dict[str, float] = {}
    mo_totals: dict[str, float] = {}
    mo_by_funcao: dict[str, dict[str, float]] = {}

    mod._bgs_accumulate_week("2026-W32", dist, eq, equip_totals, mo_totals, 1.0, {}, mo_by_funcao)

    assert list(mo_by_funcao) == ["Serra Verde — Operador de Escavadeira"]
    assert mo_by_funcao["Serra Verde — Operador de Escavadeira"]["2026-W32"] == 3.0
