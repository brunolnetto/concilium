from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


def _load_helpers_a():
    root = Path(__file__).resolve().parents[4]
    helper = (
        root / "src/concilium/application/skills/manifests/09-relatorio-e-artefatos/_skill_helpers/__init__.py"
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


def test_bgs_add_financeiro_faz_fallback_quando_versao_proporcional_falha():
    """Se `_b._cash_flow_rows` (proporcional ao cronograma físico) lançar exceção
    (ex.: canonical_in sem `contratos_recurso`), `_bgs_add_financeiro` deve capturar
    e usar a distribuição uniforme local (`_cash_flow.py`) como fallback."""
    mod = _load_helpers_a()
    canonical_in = SimpleNamespace(
        resultado=SimpleNamespace(
            venda=SimpleNamespace(total_com_bdi=1000.0),
            custo=SimpleNamespace(total=800.0),
        )
        # nota: sem `contratos_recurso` — faz `_b._cash_flow_rows` lançar AttributeError
    )
    project_months = [(2026, 7), (2026, 8)]
    graficos: dict = {}

    mod._bgs_add_financeiro(graficos, canonical_in, project_months)

    assert "financeiro" in graficos
    assert len(graficos["financeiro"]["labels"]) == 2
    assert graficos["financeiro"]["receita"] == [500.0, 500.0]
    assert graficos["financeiro"]["despesa"] == [400.0, 400.0]
    assert graficos["financeiro"]["saldo"] == [100.0, 100.0]
