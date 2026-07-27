"""ADR-157 F1 — Composição de Equipamentos por Tipo de Pool + Substituição Segura: TDD.

Espelho de test_adr156_composicao_funcoes_substituicao_roster.py, trocando
funcao_id/FuncaoEquipe/MembroEquipeReal por equip_id/EquipamentoEquipe/
AtivoEquipamentoReal. Escrito antes da implementação (red phase). Sem nenhuma
mudança no orquestrador real de skill-05 — funções puras testadas isoladamente.
"""

from __future__ import annotations

from datetime import date

from concilium.domain.models.canonical import AtivoEquipamentoReal, RecursoContrato
from concilium.domain.models.catalog.catalogo import ComposicaoPadraoEquipe, EquipamentoEquipe, FuncaoEquipe
from concilium.domain.services.financial.roster_custo_eq_substituicao import (
    aplicar_roster_custo_real_eq,
    extrair_composicao_equipamentos_eq,
)


def _composicao(**overrides) -> ComposicaoPadraoEquipe:
    defaults = dict(
        funcoes=[FuncaoEquipe(funcao_id="MO-OPER-ESCAV", num_pessoas=1)],
        equipamentos=[EquipamentoEquipe(equip_id="EQ-E0019", num_unidades=1)],
    )
    defaults.update(overrides)
    return ComposicaoPadraoEquipe(**defaults)


def _contrato(**overrides) -> RecursoContrato:
    defaults = dict(
        contrato_id="contrato-esc-3cat",
        tipo_id="ESC-3CAT",
        quantidade_contratada=1,
        semana_inicio="2026-W01",
        semana_fim="2026-W04",
        semanas_contrato=4,
        custo_unit_semanal=1000.0,
        custo_total_contrato=4000.0,
        custo_unit_semanal_mo=600.0,
        custo_unit_semanal_eq=300.0,
        custo_unit_semanal_comb=80.0,
        custo_unit_semanal_mat=20.0,
        composicao_equipamentos_eq={"EQ-E0019": 1},
    )
    defaults.update(overrides)
    return RecursoContrato(**defaults)


def _ativo(**overrides) -> AtivoEquipamentoReal:
    defaults = dict(
        ativo_id="ESC-001",
        equip_id="EQ-E0019",
        custo_locacao_mensal_real=20000.0,
        custo_manutencao_mensal_real=2000.0,
        data_contrato_inicio=date(2026, 1, 1),
    )
    defaults.update(overrides)
    return AtivoEquipamentoReal(**defaults)


class TestExtrairComposicaoEquipamentosEq:
    def test_extrai_equip_id_e_num_unidades(self):
        composicao = _composicao(
            equipamentos=[
                EquipamentoEquipe(equip_id="EQ-E0019", num_unidades=1),
                EquipamentoEquipe(equip_id="EQ-E0007", num_unidades=4),
            ]
        )
        assert extrair_composicao_equipamentos_eq(composicao) == {
            "EQ-E0019": 1,
            "EQ-E0007": 4,
        }

    def test_composicao_sem_equipamentos_retorna_vazio(self):
        composicao = _composicao(equipamentos=[], funcoes=[FuncaoEquipe(funcao_id="MO-OPER-ESCAV", num_pessoas=1)])
        assert extrair_composicao_equipamentos_eq(composicao) == {}


class TestAplicarRosterCustoRealEq:
    def test_substitui_quando_cobertura_e_suficiente(self):
        contrato = _contrato()
        ativo = _ativo()
        resultado = aplicar_roster_custo_real_eq(contrato, [ativo])
        assert resultado.custo_unit_semanal_eq != contrato.custo_unit_semanal_eq
        assert resultado.custo_unit_semanal_mo == contrato.custo_unit_semanal_mo
        assert resultado.custo_unit_semanal_comb == contrato.custo_unit_semanal_comb
        assert resultado.custo_unit_semanal_mat == contrato.custo_unit_semanal_mat
        esperado_semanal = round(
            contrato.custo_unit_semanal_mo
            + resultado.custo_unit_semanal_eq
            + contrato.custo_unit_semanal_comb
            + contrato.custo_unit_semanal_mat,
            4,
        )
        assert resultado.custo_unit_semanal == esperado_semanal
        assert resultado.custo_total_contrato == round(
            contrato.quantidade_contratada * esperado_semanal * contrato.semanas_contrato, 2
        )

    def test_nao_substitui_quando_cobertura_insuficiente(self):
        contrato = _contrato(composicao_equipamentos_eq={"EQ-E0019": 2})
        ativo = _ativo()
        resultado = aplicar_roster_custo_real_eq(contrato, [ativo])
        assert resultado.custo_unit_semanal_eq == contrato.custo_unit_semanal_eq
        assert resultado.custo_total_contrato == contrato.custo_total_contrato

    def test_nao_substitui_quando_composicao_vazia(self):
        contrato = _contrato(composicao_equipamentos_eq={})
        ativo = _ativo()
        resultado = aplicar_roster_custo_real_eq(contrato, [ativo])
        assert resultado.custo_unit_semanal_eq == contrato.custo_unit_semanal_eq

    def test_nao_substitui_quando_falta_equipamento_da_composicao_multipla(self):
        contrato = _contrato(composicao_equipamentos_eq={"EQ-E0019": 1, "EQ-E0007": 1})
        ativo = _ativo()  # só cobre EQ-E0019
        resultado = aplicar_roster_custo_real_eq(contrato, [ativo])
        assert resultado.custo_unit_semanal_eq == contrato.custo_unit_semanal_eq

    def test_substitui_composicao_multipla_quando_todas_cobertas(self):
        contrato = _contrato(composicao_equipamentos_eq={"EQ-E0019": 1, "EQ-E0007": 1})
        a1 = _ativo(ativo_id="ESC-001", equip_id="EQ-E0019")
        a2 = _ativo(ativo_id="CAM-001", equip_id="EQ-E0007")
        resultado = aplicar_roster_custo_real_eq(contrato, [a1, a2])
        assert resultado.custo_unit_semanal_eq != contrato.custo_unit_semanal_eq
        assert resultado.custo_unit_semanal_eq > 0

    def test_headcount_considera_quantidade_contratada(self):
        contrato = _contrato(quantidade_contratada=2, composicao_equipamentos_eq={"EQ-E0019": 1})
        ativo = _ativo()  # só 1 ativo distinto, precisa de 2
        resultado = aplicar_roster_custo_real_eq(contrato, [ativo])
        assert resultado.custo_unit_semanal_eq == contrato.custo_unit_semanal_eq

    def test_nao_muta_contrato_original(self):
        contrato = _contrato()
        ativo = _ativo()
        aplicar_roster_custo_real_eq(contrato, [ativo])
        assert contrato.custo_unit_semanal_eq == 300.0
