"""Testes para fracao_dedicacao em composicao_padrao_equipe (ADR-132 D2, revisão).

Contexto: `concilium catalog validate -c mendeslobo` reportava 154 erros de
`num_pessoas`/`num_unidades` fracionário nos 4 CPUs Serra Verde/MINERACAO
(rateio de headcount/equipamento compartilhado entre n_frentes simultâneas).
Decisão: manter `num_pessoas`/`num_unidades` como contagem discreta inteira
e introduzir `fracao_dedicacao` (0 < x <= 1, default 1,0) para capturar o
rateio, sem sobrecarregar a contagem. `pu_calculator` multiplica
`quantidade × fracao_dedicacao` na acumulação de custo — estes testes cobrem
essa multiplicação diretamente nas funções de acumulação.
"""

from __future__ import annotations

from concilium.application.catalog.pu_calculator import (
    BreakdownPU,
    ParametrosCalculo,
    _acumular_custo_equipamentos,
    _acumular_custo_mo,
)


def _bd() -> BreakdownPU:
    return BreakdownPU(producao_id="PROD-TEST", valor_horario=1.0)


class TestFracaoDedicacaoMaoDeObra:
    def test_sem_fracao_dedicacao_comporta_como_1_0(self):
        """Retrocompat: ausência de fracao_dedicacao não altera o cálculo existente."""
        insumo_index = {"F0001": {"preco_unitario": 30.0, "unidade": "h"}}
        params = ParametrosCalculo()

        bd_sem_campo = _bd()
        _acumular_custo_mo(bd_sem_campo, [{"funcao_id": "F0001", "num_pessoas": 2}], insumo_index, params)

        bd_com_1 = _bd()
        _acumular_custo_mo(
            bd_com_1, [{"funcao_id": "F0001", "num_pessoas": 2, "fracao_dedicacao": 1.0}], insumo_index, params
        )

        assert bd_sem_campo.custo_mo_h == bd_com_1.custo_mo_h == 60.0

    def test_fracao_dedicacao_rateia_custo_proporcionalmente(self):
        """1 pessoa (num_pessoas=1) compartilhada entre 3 frentes (fracao=1/3)
        contribui 1/3 do custo horário desta função nesta frente."""
        insumo_index = {"F0001": {"preco_unitario": 30.0, "unidade": "h"}}
        params = ParametrosCalculo()

        bd = _bd()
        _acumular_custo_mo(
            bd, [{"funcao_id": "F0001", "num_pessoas": 1, "fracao_dedicacao": 0.3333}], insumo_index, params
        )

        assert round(bd.custo_mo_h, 4) == round(30.0 * 0.3333, 4)

    def test_tres_frentes_somam_ao_custo_de_uma_pessoa_integral(self):
        """Verificação de conservação: 3 frentes com fracao=1/3 cada somam ao
        custo de 1 pessoa integral (nenhum custo perdido ou duplicado no rateio)."""
        insumo_index = {"F0001": {"preco_unitario": 30.0, "unidade": "h"}}
        params = ParametrosCalculo()

        total = 0.0
        for _ in range(3):
            bd = _bd()
            _acumular_custo_mo(
                bd, [{"funcao_id": "F0001", "num_pessoas": 1, "fracao_dedicacao": 1 / 3}], insumo_index, params
            )
            total += bd.custo_mo_h

        assert round(total, 4) == 30.0

    def test_quantidade_no_item_reflete_fracao_efetiva(self):
        """O item de breakdown expõe a quantidade EFETIVA (num_pessoas × fracao),
        não a contagem nominal — necessário para auditoria do rateio."""
        insumo_index = {"F0001": {"preco_unitario": 30.0, "unidade": "h"}}
        params = ParametrosCalculo()

        bd = _bd()
        _acumular_custo_mo(
            bd, [{"funcao_id": "F0001", "num_pessoas": 1, "fracao_dedicacao": 0.3333}], insumo_index, params
        )

        assert bd.itens[0]["quantidade"] == 0.3333


class TestFracaoDedicacaoEquipamento:
    def test_sem_fracao_dedicacao_comporta_como_1_0(self):
        insumo_index = {"E0027": {"preco_unitario": 100.0}}
        params = ParametrosCalculo()

        bd_sem_campo = _bd()
        _acumular_custo_equipamentos(bd_sem_campo, [{"equip_id": "E0027", "num_unidades": 2}], insumo_index, params)

        bd_com_1 = _bd()
        _acumular_custo_equipamentos(
            bd_com_1, [{"equip_id": "E0027", "num_unidades": 2, "fracao_dedicacao": 1.0}], insumo_index, params
        )

        assert bd_sem_campo.custo_equip_h == bd_com_1.custo_equip_h == 200.0

    def test_fracao_dedicacao_rateia_custo_de_equipamento(self):
        insumo_index = {"E0027": {"preco_unitario": 138.8889}}
        params = ParametrosCalculo()

        bd = _bd()
        _acumular_custo_equipamentos(
            bd, [{"equip_id": "E0027", "num_unidades": 1, "fracao_dedicacao": 0.6667}], insumo_index, params
        )

        assert round(bd.custo_equip_h, 4) == round(138.8889 * 0.6667, 4)

    def test_fracao_dedicacao_rateia_diesel_proporcionalmente(self):
        """Consumo de diesel de uma unidade compartilhada também é rateado pela
        mesma fracao_dedicacao do equipamento — a unidade só está parcialmente
        alocada a esta frente, então seu consumo também é parcial aqui."""
        insumo_index = {"E0027": {"preco_unitario": 100.0}}
        params = ParametrosCalculo(preco_diesel=6.0)

        bd = _bd()
        _acumular_custo_equipamentos(
            bd,
            [{"equip_id": "E0027", "num_unidades": 1, "fracao_dedicacao": 0.5, "consumo_litros_hora": 10.0}],
            insumo_index,
            params,
        )

        assert bd.custo_diesel_h == 10.0 * 6.0 * 0.5
