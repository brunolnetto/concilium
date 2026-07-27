"""ADR-160 D1 — taxa_media_eq_idle_real: TDD.

Taxa média real de EQ ocioso (só locação, custo_real_eq_idle_semanal, ADR-158
D1) — mesma lógica de agregação de aplicar_roster_custo_real_eq (ADR-157),
trocando o numerador para o idle. Não verifica cobertura (responsabilidade do
chamador, ADR-160 D3).

Escrito antes da implementação (red phase).
"""

from __future__ import annotations

from datetime import date

from concilium.domain.models.canonical import AtivoEquipamentoReal, RecursoContrato
from concilium.domain.services.financial.roster_custo_equipamento import (
    taxa_media_eq_idle_real,
)


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


class TestTaxaMediaEqIdleReal:
    def test_taxa_media_calculada_a_partir_do_idle(self):
        contrato = _contrato()
        ativo = _ativo()
        taxa = taxa_media_eq_idle_real(contrato, [ativo])
        # cada semana arredonda a 2 casas (custo_real_eq_idle_semanal); com
        # quantidade_contratada=1 e 4 semanas ativas o todo, a média reproduz
        # exatamente o valor semanal arredondado.
        from concilium.domain.constants import SEMANAS_POR_MES

        esperado = round(20000.0 / SEMANAS_POR_MES, 2)
        assert taxa == esperado

    def test_taxa_menor_que_taxa_ativa_equivalente(self):
        from concilium.domain.constants import SEMANAS_POR_MES

        contrato = _contrato()
        ativo = _ativo()  # locação 20000 + manutenção 2000
        idle = taxa_media_eq_idle_real(contrato, [ativo])
        ativa_equivalente = round((20000.0 + 2000.0) / SEMANAS_POR_MES, 4)
        assert idle < ativa_equivalente

    def test_multiplos_equipamentos_na_composicao_somam(self):
        contrato = _contrato(composicao_equipamentos_eq={"EQ-E0019": 1, "EQ-E0007": 1})
        a1 = _ativo(ativo_id="ESC-001", equip_id="EQ-E0019", custo_locacao_mensal_real=20000.0)
        a2 = _ativo(ativo_id="CAM-001", equip_id="EQ-E0007", custo_locacao_mensal_real=10000.0)
        taxa = taxa_media_eq_idle_real(contrato, [a1, a2])
        from concilium.domain.constants import SEMANAS_POR_MES

        # equip_ids distintos são somados em custo_real_eq_idle_semanal separadamente
        # (cada um arredondado a 2 casas por semana antes de somar).
        esperado = round(20000.0 / SEMANAS_POR_MES, 2) + round(10000.0 / SEMANAS_POR_MES, 2)
        assert taxa == esperado

    def test_composicao_vazia_retorna_zero(self):
        contrato = _contrato(composicao_equipamentos_eq={})
        ativo = _ativo()
        assert taxa_media_eq_idle_real(contrato, [ativo]) == 0.0

    def test_quantidade_contratada_maior_que_um_divide_corretamente(self):
        contrato = _contrato(quantidade_contratada=2)
        a1 = _ativo(ativo_id="ESC-001")
        a2 = _ativo(ativo_id="ESC-002")
        taxa = taxa_media_eq_idle_real(contrato, [a1, a2])
        from concilium.domain.constants import SEMANAS_POR_MES

        # mesmo equip_id: a soma dos dois ativos é arredondada a 2 casas por
        # semana (custo_real_eq_idle_semanal), antes de dividir por quantidade_contratada.
        esperado = round(round(40000.0 / SEMANAS_POR_MES, 2) / 2, 4)
        assert taxa == esperado
