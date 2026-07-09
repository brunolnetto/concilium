"""ADR-090 (correção) — resíduo não-decomposto de indireto vai para verba, não MO.

TDD: testes escritos antes da correção.

Contexto (auditoria AGIS 2026-06-11):
  O spec do AGIS decompõe apenas `mao_obra[]` (≈35% do custo mensal de ADM); o
  restante (equipamentos 271k + verbas 378k mensais da planilha) não vem decomposto.
  `_sub_custos_indireto` escalava o custo_total INTEIRO pela única fração presente
  (MO), classificando 100% do ADM como custo_mao_obra → BDI de MO (30%) sobre uma
  massa que na planilha leva 25,2% (verba/indireto). Efeito B2: +1,7M na venda.

Regra corrigida:
  Se Σ componentes mensais < custo_fixo_mensal da categoria, o resíduo mensal é
  classificado como verba (taxa de indireto — conservadora, igual ao fallback
  documentado para composição totalmente ausente).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from concilium.domain.models.canonical import IndirectoCategoria, IndirectoCostComponent


def _load_helpers_b():
    path = (
        Path(__file__).resolve().parents[2]
        / "src/concilium/application/skills/manifests"
        / "06-resultado-financeiro/_indiretos/_skill_helpers/__init__.py"
    )
    spec = importlib.util.spec_from_file_location(
        "ind_helpers_b_test", path, submodule_search_locations=[str(path.parent)]
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ind_helpers_b_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def _cat(mensal_total: float, mo_mensal: float = 0.0, eq_mensal: float = 0.0, verba_mensal: float = 0.0):
    def comp(v):
        return IndirectoCostComponent(nome="comp", custo_fixo_mensal=v) if v > 0 else None

    return IndirectoCategoria(
        categoria="ADM",
        driver="permanencia",
        custo_fixo_mensal=mensal_total,
        mao_de_obra=comp(mo_mensal),
        equipamentos=comp(eq_mensal),
        verbas=comp(verba_mensal),
    )


class TestResiduoIndiretoVaiParaVerba:
    def test_composicao_parcial_residuo_em_verba(self):
        """Caso AGIS: só MO decomposta (35% do mensal) → resíduo (65%) em verba."""
        mod = _load_helpers_b()
        # mensal_total=1000, MO=350 → resíduo 650 vai para verba
        cat = _cat(mensal_total=1000.0, mo_mensal=350.0)
        subs = mod._sub_custos_indireto(cat, custo_total=15_000.0)  # 15 meses
        assert subs["custo_mao_obra"] + subs["custo_encargos"] == pytest.approx(0.35 * 15_000.0, abs=1.0)
        assert subs["custo_verba"] == pytest.approx(0.65 * 15_000.0, abs=1.0)
        assert subs["custo_equipamentos"] == pytest.approx(0.0)

    def test_composicao_completa_sem_residuo(self):
        """Componentes explicam 100% do mensal → comportamento atual preservado."""
        mod = _load_helpers_b()
        cat = _cat(mensal_total=1000.0, mo_mensal=400.0, eq_mensal=250.0, verba_mensal=350.0)
        subs = mod._sub_custos_indireto(cat, custo_total=10_000.0)
        assert subs["custo_mao_obra"] + subs["custo_encargos"] == pytest.approx(4_000.0, abs=1.0)
        assert subs["custo_equipamentos"] == pytest.approx(2_500.0, abs=1.0)
        assert subs["custo_verba"] == pytest.approx(3_500.0, abs=1.0)

    def test_sem_composicao_fallback_verba_total(self):
        """Sem componentes: fallback existente — tudo em verba."""
        mod = _load_helpers_b()
        cat = _cat(mensal_total=1000.0)
        subs = mod._sub_custos_indireto(cat, custo_total=5_000.0)
        assert subs["custo_verba"] == pytest.approx(5_000.0)
        assert subs["custo_mao_obra"] == pytest.approx(0.0)

    def test_soma_subs_igual_custo_total(self):
        """Invariante: Σ sub-custos == custo_total em todos os cenários."""
        mod = _load_helpers_b()
        for cat in (
            _cat(1000.0, mo_mensal=350.0),
            _cat(1000.0, mo_mensal=400.0, eq_mensal=250.0, verba_mensal=350.0),
            _cat(1000.0),
            _cat(0.0, mo_mensal=500.0),  # mensal_total desconhecido → componentes são a base
        ):
            subs = mod._sub_custos_indireto(cat, custo_total=8_000.0)
            soma = sum(subs.values())
            assert soma == pytest.approx(8_000.0, abs=1.0), f"Σ={soma} cat={cat.custo_fixo_mensal}"

    def test_mensal_total_desconhecido_usa_componentes(self):
        """custo_fixo_mensal=0 (desconhecido): scale pelos componentes (sem resíduo)."""
        mod = _load_helpers_b()
        cat = _cat(mensal_total=0.0, mo_mensal=500.0)
        subs = mod._sub_custos_indireto(cat, custo_total=6_000.0)
        assert subs["custo_mao_obra"] + subs["custo_encargos"] == pytest.approx(6_000.0, abs=1.0)
