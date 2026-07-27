"""ADR-156 F1 — Composição de Funções por Tipo de Pool + Substituição Segura: TDD.

Cobre:
  - `extrair_composicao_funcoes_mo`: extrai {funcao_id: num_pessoas} de uma
    ComposicaoPadraoEquipe (mesma informação usada por _tipo_recurso_fungivel para
    gerar o hash de tipo_id, exposta aqui como função standalone).
  - `aplicar_roster_custo_real_mo`: substitui custo_unit_semanal_mo (e derivados)
    SÓ quando o roster cobre, com headcount suficiente, TODAS as funções da
    composição — nunca substituição parcial.

Escrito antes da implementação (red phase). Sem nenhuma mudança no orquestrador
real de skill-05 (ADR-157, futura) — funções puras testadas isoladamente.
"""

from __future__ import annotations

from datetime import date

from concilium.domain.models.canonical import MembroEquipeReal, RecursoContrato
from concilium.domain.models.catalog.catalogo import ComposicaoPadraoEquipe, EquipamentoEquipe, FuncaoEquipe
from concilium.domain.services.financial.roster_custo_mo_substituicao import (
    aplicar_roster_custo_real_mo,
    extrair_composicao_funcoes_mo,
)


def _composicao(**overrides) -> ComposicaoPadraoEquipe:
    defaults = dict(
        funcoes=[FuncaoEquipe(funcao_id="MO-OPER-ESCAV", num_pessoas=1)],
        equipamentos=[],
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
        composicao_funcoes_mo={"MO-OPER-ESCAV": 1},
    )
    defaults.update(overrides)
    return RecursoContrato(**defaults)


def _membro(**overrides) -> MembroEquipeReal:
    defaults = dict(
        individuo_id="joao-001",
        funcao_id="MO-OPER-ESCAV",
        salario_base_mensal=3000.0,
        categoria_sindical="horista",
        data_admissao=date(2026, 1, 1),
    )
    defaults.update(overrides)
    return MembroEquipeReal(**defaults)


class TestExtrairComposicaoFuncoesMo:
    def test_extrai_funcao_id_e_num_pessoas(self):
        composicao = _composicao(
            funcoes=[
                FuncaoEquipe(funcao_id="MO-OPER-ESCAV", num_pessoas=1),
                FuncaoEquipe(funcao_id="MO-MOTOR-CAM-BASC", num_pessoas=5),
            ]
        )
        assert extrair_composicao_funcoes_mo(composicao) == {
            "MO-OPER-ESCAV": 1,
            "MO-MOTOR-CAM-BASC": 5,
        }

    def test_composicao_sem_funcoes_retorna_vazio(self):
        composicao = _composicao(funcoes=[], equipamentos=[EquipamentoEquipe(equip_id="EQ-001", num_unidades=1)])
        assert extrair_composicao_funcoes_mo(composicao) == {}


class TestAplicarRosterCustoRealMo:
    def test_substitui_quando_cobertura_e_suficiente(self):
        contrato = _contrato()
        membro = _membro()
        resultado = aplicar_roster_custo_real_mo(contrato, [membro])
        assert resultado.custo_unit_semanal_mo != contrato.custo_unit_semanal_mo
        # eq/comb/mat preservados calibrados
        assert resultado.custo_unit_semanal_eq == contrato.custo_unit_semanal_eq
        assert resultado.custo_unit_semanal_comb == contrato.custo_unit_semanal_comb
        assert resultado.custo_unit_semanal_mat == contrato.custo_unit_semanal_mat
        # custo_unit_semanal e custo_total_contrato recalculados consistentemente
        esperado_semanal = round(
            resultado.custo_unit_semanal_mo
            + contrato.custo_unit_semanal_eq
            + contrato.custo_unit_semanal_comb
            + contrato.custo_unit_semanal_mat,
            4,
        )
        assert resultado.custo_unit_semanal == esperado_semanal
        assert resultado.custo_total_contrato == round(
            contrato.quantidade_contratada * esperado_semanal * contrato.semanas_contrato, 2
        )

    def test_nao_substitui_quando_cobertura_insuficiente(self):
        contrato = _contrato(composicao_funcoes_mo={"MO-OPER-ESCAV": 2})  # precisa de 2, roster só tem 1
        membro = _membro()
        resultado = aplicar_roster_custo_real_mo(contrato, [membro])
        assert resultado.custo_unit_semanal_mo == contrato.custo_unit_semanal_mo
        assert resultado.custo_unit_semanal == contrato.custo_unit_semanal
        assert resultado.custo_total_contrato == contrato.custo_total_contrato

    def test_nao_substitui_quando_composicao_vazia(self):
        contrato = _contrato(composicao_funcoes_mo={})
        membro = _membro()
        resultado = aplicar_roster_custo_real_mo(contrato, [membro])
        assert resultado is contrato or resultado.custo_unit_semanal_mo == contrato.custo_unit_semanal_mo

    def test_nao_substitui_quando_falta_funcao_da_composicao_multipla(self):
        contrato = _contrato(composicao_funcoes_mo={"MO-OPER-ESCAV": 1, "MO-ENCARREG-TERRA": 1})
        membro = _membro()  # só cobre MO-OPER-ESCAV, falta MO-ENCARREG-TERRA
        resultado = aplicar_roster_custo_real_mo(contrato, [membro])
        assert resultado.custo_unit_semanal_mo == contrato.custo_unit_semanal_mo

    def test_substitui_composicao_multipla_quando_todas_cobertas(self):
        contrato = _contrato(
            quantidade_contratada=1,
            composicao_funcoes_mo={"MO-OPER-ESCAV": 1, "MO-ENCARREG-TERRA": 1},
        )
        m1 = _membro(individuo_id="joao-001", funcao_id="MO-OPER-ESCAV")
        m2 = _membro(individuo_id="maria-002", funcao_id="MO-ENCARREG-TERRA")
        resultado = aplicar_roster_custo_real_mo(contrato, [m1, m2])
        assert resultado.custo_unit_semanal_mo != contrato.custo_unit_semanal_mo
        assert resultado.custo_unit_semanal_mo > 0

    def test_headcount_considera_quantidade_contratada(self):
        # quantidade_contratada=2 exige 2 pessoas para 1 vaga/equipe cada -> 2 no total
        contrato = _contrato(quantidade_contratada=2, composicao_funcoes_mo={"MO-OPER-ESCAV": 1})
        membro = _membro()  # só 1 pessoa distinta, precisa de 2
        resultado = aplicar_roster_custo_real_mo(contrato, [membro])
        assert resultado.custo_unit_semanal_mo == contrato.custo_unit_semanal_mo

    def test_nao_muta_contrato_original(self):
        contrato = _contrato()
        membro = _membro()
        aplicar_roster_custo_real_mo(contrato, [membro])
        assert contrato.custo_unit_semanal_mo == 600.0
