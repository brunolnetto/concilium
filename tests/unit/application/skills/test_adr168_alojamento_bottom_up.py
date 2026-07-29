"""ADR-168 — Composição de Alojamento bottom-up (ADM): TDD.

Substitui a verba lump "Alojamento" (R$3.500/mês fixo) por um cálculo de
número de casas necessárias a partir do headcount direto: cada casa comporta
`quartos_por_casa × pessoas_por_quarto` pessoas (default 3×2=6), ao valor de
aluguel informado (default R$4.000/mês/casa) — ambos configuráveis.

Escrito antes da implementação (red phase).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]


def _load_dimensionamento():
    path = (
        _ROOT
        / "src/concilium/application/skills/manifests"
        / "06-resultado-financeiro/_indiretos/_skill_helpers/_dimensionamento.py"
    )
    spec = importlib.util.spec_from_file_location("adr168_dimensionamento", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestCustoAlojamentoBottomUp:
    def _fn(self):
        return _load_dimensionamento()._custo_alojamento_bottom_up

    def test_headcount_zero_retorna_none(self):
        assert self._fn()(0) is None

    def test_headcount_negativo_retorna_none(self):
        assert self._fn()(-1) is None

    def test_uma_casa_cobre_headcount_ate_capacidade(self):
        # default 3 quartos x 2 pessoas = 6/casa
        comp = self._fn()(6)
        assert comp["itens"][0]["quantidade"] == 1
        assert comp["custo_fixo_mensal"] == 4000.0

    def test_headcount_acima_da_capacidade_arredonda_para_cima(self):
        comp = self._fn()(7)
        assert comp["itens"][0]["quantidade"] == 2
        assert comp["custo_fixo_mensal"] == 8000.0

    def test_headcount_pequeno_ainda_paga_uma_casa_inteira(self):
        comp = self._fn()(1)
        assert comp["itens"][0]["quantidade"] == 1
        assert comp["custo_fixo_mensal"] == 4000.0

    def test_configuracao_customizada_de_capacidade_e_valor(self):
        comp = self._fn()(10, quartos_por_casa=5, pessoas_por_quarto=2, valor_aluguel_mensal=6000.0)
        # capacidade 10/casa -> 1 casa
        assert comp["itens"][0]["quantidade"] == 1
        assert comp["custo_fixo_mensal"] == 6000.0

    def test_capacidade_zero_retorna_none(self):
        assert self._fn()(10, quartos_por_casa=0) is None


class TestComposicaoDefaultAdmComAlojamento:
    def _fn(self):
        return _load_dimensionamento()._composicao_default_por_categoria

    def test_adm_sem_equipes_usa_lump_default_alojamento(self):
        result = self._fn()("ADM")
        assert result["verbas"]["custo_fixo_mensal"] == 3500.0
        assert result["verbas"]["itens"][0]["descricao"] == "Alojamento"

    def test_adm_com_equipes_usa_bottom_up_de_casas(self):
        from concilium.domain.models.canonical import EquipeDireta, FuncaoEquipeDireta

        equipes = [
            EquipeDireta(
                item_id="eq-1",
                custo_total=0.0,
                funcoes=[FuncaoEquipeDireta(funcao_id="MO-ARMADOR", num_pessoas=7)],
            )
        ]
        result = self._fn()("ADM", equipes)
        # 7 pessoas / 6 por casa -> 2 casas x 4000 = 8000 (não mais 3500 fixo)
        assert result["verbas"]["custo_fixo_mensal"] == 8000.0

    def test_adm_com_alojamento_config_customizado(self):
        from concilium.domain.models.canonical import EquipeDireta, FuncaoEquipeDireta

        equipes = [
            EquipeDireta(
                item_id="eq-1",
                custo_total=0.0,
                funcoes=[FuncaoEquipeDireta(funcao_id="MO-ARMADOR", num_pessoas=4)],
            )
        ]
        result = self._fn()("ADM", equipes, {"quartos_por_casa": 4, "pessoas_por_quarto": 1, "valor_aluguel_mensal": 5000.0})
        # capacidade 4/casa -> 1 casa x 5000
        assert result["verbas"]["custo_fixo_mensal"] == 5000.0

    def test_adm_coordenador_mo_nao_e_afetado(self):
        """O item Coordenador (P0092, ADR-167) continua igual independente do alojamento."""
        result = self._fn()("ADM")
        assert result["mao_de_obra"]["itens"][0]["funcao_id"] == "P0092"

    def test_top_ignora_parametros_novos_sem_quebrar(self):
        from concilium.domain.models.canonical import EquipeDireta, FuncaoEquipeDireta

        equipes = [EquipeDireta(item_id="eq-1", custo_total=0.0, funcoes=[FuncaoEquipeDireta(funcao_id="P0057", num_pessoas=5)])]
        result = self._fn()("TOP", equipes)
        assert result["mao_de_obra"]["itens"][0]["funcao_id"] == "P0057"
