"""Tests for ADR-009: Indirect Costs as First-Class Models."""

from __future__ import annotations

from concilium.domain.constants import SEMANAS_POR_MES
from concilium.domain.models.canonical import (
    IndirectoCategoria,
    IndirectoCostComponent,
    IndiretoSemanal,
)


class TestIndirectoCostComponent:
    def test_create_basic(self):
        comp = IndirectoCostComponent(nome="MÃO DE OBRA", custo_fixo_mensal=10000.0)
        assert comp.nome == "MÃO DE OBRA"
        assert comp.custo_fixo_mensal == 10000.0
        assert comp.itens == []

    def test_create_with_items(self):
        comp = IndirectoCostComponent(
            nome="EQUIPAMENTOS",
            custo_fixo_mensal=5000.0,
            itens=[{"equipamento": "Veículo leve", "custo": 4000.0}],
        )
        assert len(comp.itens) == 1


class TestIndirectoCategoria:
    def test_permanencia_custo_semanal(self):
        cat = IndirectoCategoria(
            categoria="TOP",
            driver="permanencia",
            custo_fixo_mensal=119817.76,
        )
        assert cat.driver == "permanencia"
        assert abs(cat.custo_semanal - (119817.76 / SEMANAS_POR_MES)) < 0.10

    def test_one_time_custo_semanal_zero(self):
        cat = IndirectoCategoria(
            categoria="MOB",
            driver="one_time",
            custo_fixo_total=6265184.86,
        )
        assert cat.custo_semanal == 0.0

    def test_custo_total_para_semanas_permanencia(self):
        cat = IndirectoCategoria(
            categoria="ADM",
            driver="permanencia",
            custo_fixo_mensal=1219468.24,
        )
        custo_24 = cat.custo_total_para_semanas(24)
        esperado = round((1219468.24 / SEMANAS_POR_MES) * 24, 2)
        assert abs(custo_24 - esperado) < 1.0

    def test_custo_total_para_semanas_one_time(self):
        cat = IndirectoCategoria(
            categoria="MOB",
            driver="one_time",
            custo_fixo_total=6265184.86,
        )
        assert cat.custo_total_para_semanas(24) == 6265184.86
        assert cat.custo_total_para_semanas(52) == 6265184.86

    def test_all_permanencia_categories(self):
        for cat_id in ["TOP", "ADM", "LAB", "QSMS"]:
            cat = IndirectoCategoria(categoria=cat_id, driver="permanencia", custo_fixo_mensal=10000.0)
            assert cat.custo_semanal > 0

    def test_mob_is_one_time(self):
        cat = IndirectoCategoria(categoria="MOB", driver="one_time", custo_fixo_total=5000000.0)
        assert cat.custo_semanal == 0.0
        # total unchanged regardless of duration
        assert cat.custo_total_para_semanas(10) == cat.custo_total_para_semanas(50)

    def test_with_components(self):
        mo = IndirectoCostComponent(nome="MO TOP", custo_fixo_mensal=94433.76)
        eq = IndirectoCostComponent(nome="EQ TOP", custo_fixo_mensal=22384.0)
        vb = IndirectoCostComponent(nome="VERBAS TOP", custo_fixo_mensal=3000.0)
        cat = IndirectoCategoria(
            categoria="TOP",
            driver="permanencia",
            mao_de_obra=mo,
            equipamentos=eq,
            verbas=vb,
            custo_fixo_mensal=119817.76,
        )
        assert cat.mao_de_obra is not None
        assert cat.equipamentos is not None
        assert cat.verbas is not None


class TestIndiretoSemanal:
    def test_create(self):
        s = IndiretoSemanal(semana=0, categoria="TOP", custo_semanal=27665.65, ativa=True)
        assert s.semana == 0
        assert s.categoria == "TOP"
        assert s.ativa is True

    def test_mob_inactive_weeks(self):
        s = IndiretoSemanal(semana=5, categoria="MOB", custo_semanal=0.0, ativa=False)
        assert s.ativa is False
        assert s.custo_semanal == 0.0

    def test_mob_active_first_last_weeks(self):
        s_first = IndiretoSemanal(semana=0, categoria="MOB", custo_semanal=3132592.43, ativa=True)
        s_last = IndiretoSemanal(semana=23, categoria="MOB", custo_semanal=3132592.43, ativa=True)
        assert s_first.ativa is True
        assert s_last.ativa is True
