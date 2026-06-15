"""Tests for ADR-011: Productivity as Computable Artifact."""

from __future__ import annotations

from concilium.domain.models.catalog.producao import (
    ComponenteCombustivel,
    ComponenteEquipamento,
    ComponenteMaoDeObra,
    ProdutividadeDetalhada,
)


class TestProdutividadeDetalhada:
    def _make_produtividade(
        self,
        producao_horaria: float = 239.04,
        custo_equip: float = 1170.73,
        custo_mo: float = 284.76,
        custo_comb: float = 304.07,
        horas_dia: int = 8,
        dias_semana: int = 5,
    ) -> ProdutividadeDetalhada:
        return ProdutividadeDetalhada(
            codigo="2.1",
            descricao="Escavação 1ª categoria DMT até 2000m",
            unidade="m3",
            componente_equipamento=ComponenteEquipamento(
                equipamentos=[{"equip": "Escavadeira 38T", "custo": custo_equip}],
                custo_horario_total=custo_equip,
            ),
            componente_mao_de_obra=ComponenteMaoDeObra(
                funcoes=[{"funcao": "Operador", "custo": custo_mo}],
                custo_horario_total=custo_mo,
            ),
            componente_combustivel=ComponenteCombustivel(
                equipamentos=[{"equip": "Escavadeira diesel", "custo": custo_comb}],
                custo_horario_total=custo_comb,
            ),
            producao_horaria=producao_horaria,
            horas_dia=horas_dia,
            dias_semana=dias_semana,
        )

    def test_producao_diaria_derivada(self):
        p = self._make_produtividade(producao_horaria=239.04, horas_dia=8)
        assert abs(p.producao_diaria - 239.04 * 8) < 0.01

    def test_producao_semanal_derivada(self):
        p = self._make_produtividade(producao_horaria=239.04, horas_dia=8, dias_semana=5)
        # 239.04 × 8 × 5 = 9561.6
        assert abs(p.producao_semanal - 9561.6) < 0.1

    def test_custo_unitario_derivado(self):
        p = self._make_produtividade(
            producao_horaria=239.04,
            custo_equip=1170.73,
            custo_mo=284.76,
            custo_comb=304.07,
        )
        custo_horario = 1170.73 + 284.76 + 304.07
        esperado = custo_horario / 239.04
        assert abs(p.custo_unitario - esperado) < 0.001

    def test_custo_horario_total_soma_componentes(self):
        p = self._make_produtividade(
            custo_equip=1170.73,
            custo_mo=284.76,
            custo_comb=304.07,
        )
        assert abs(p.custo_horario_total - (1170.73 + 284.76 + 304.07)) < 0.01

    def test_producao_n_equipes_linear(self):
        p = self._make_produtividade(producao_horaria=239.04)
        assert abs(p.producao_n_equipes(2) - 2 * p.producao_semanal) < 0.1

    def test_producao_n_equipes_com_eficiencia(self):
        p = self._make_produtividade(producao_horaria=239.04)
        result = p.producao_n_equipes(2, eficiencia=0.8)
        assert abs(result - 2 * p.producao_semanal * 0.8) < 0.1

    def test_granularidade_personalizada(self):
        # Regime 6 dias/semana, 10h/dia
        p = self._make_produtividade(producao_horaria=100.0, horas_dia=10, dias_semana=6)
        assert abs(p.producao_semanal - 100.0 * 10 * 6) < 0.01
