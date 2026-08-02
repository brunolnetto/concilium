"""Testes para CuboRosterRealBuilder (ADR-174 F3).

Builder recebe roster_mo/roster_eq/catalogo como parâmetros explícitos (não
lidos do canonical) — roster é transiente por design (ADR-160/173), nunca
"baked-in" no canônico como recursos_consumiveis é.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from concilium.application.services.analytics.cubo_roster_real_builder import (
    CuboRosterRealBuilder,
)
from concilium.domain.models.canonical import AtivoEquipamentoReal, MembroEquipeReal
from concilium.domain.services.financial.roster_custo_equipamento import (
    custo_semanal_individual_eq,
)
from concilium.domain.services.financial.roster_custo_mo import (
    custo_semanal_individual_mo,
)


def _canonical(data_inicio="2026-01-01", data_termino="2026-01-31", nome="Projeto Teste"):
    projeto = SimpleNamespace(
        nome=nome,
        id="proj-1",
        data_inicio=date.fromisoformat(data_inicio),
        data_termino=date.fromisoformat(data_termino),
    )
    return SimpleNamespace(projeto=projeto)


def _membro(**overrides) -> MembroEquipeReal:
    defaults = dict(
        individuo_id="mo-001",
        funcao_id="MO-ARMADOR",
        salario_base_mensal=3000.0,
        data_admissao=date(2026, 1, 1),
    )
    defaults.update(overrides)
    return MembroEquipeReal(**defaults)


def _ativo(**overrides) -> AtivoEquipamentoReal:
    defaults = dict(
        ativo_id="eq-001",
        equip_id="EQ-ESCAVADEIRA",
        custo_locacao_mensal_real=12000.0,
        data_contrato_inicio=date(2026, 1, 1),
    )
    defaults.update(overrides)
    return AtivoEquipamentoReal(**defaults)


class TestCuboRosterRealBuilder:
    def test_projeto_id_do_canonical(self):
        cubo = CuboRosterRealBuilder().build(_canonical(), [], [], None)
        assert cubo.projeto_id == "Projeto Teste"

    def test_sem_roster_retorna_celulas_vazias(self):
        cubo = CuboRosterRealBuilder().build(_canonical(), [], [], None)
        assert cubo.celulas == ()

    def test_sem_datas_de_projeto_retorna_celulas_vazias(self):
        canonical_in = SimpleNamespace(projeto=SimpleNamespace(nome="X", id="1", data_inicio=None, data_termino=None))
        membro = _membro()
        cubo = CuboRosterRealBuilder().build(canonical_in, [membro], [], None)
        assert cubo.celulas == ()

    def test_membro_mo_gera_celulas_categoria_mao_obra(self):
        membro = _membro()
        cubo = CuboRosterRealBuilder().build(_canonical(), [membro], [], None)
        assert len(cubo.celulas) > 0
        assert all(c.categoria == "MAO_OBRA" for c in cubo.celulas)
        assert all(c.grupo_id == "MO-ARMADOR" for c in cubo.celulas)
        assert all(c.instancia_id == "mo-001" for c in cubo.celulas)

    def test_ativo_eq_gera_celulas_categoria_equipamento_sem_indireto(self):
        ativo = _ativo()
        cubo = CuboRosterRealBuilder().build(_canonical(), [], [ativo], None)
        assert len(cubo.celulas) > 0
        assert all(c.categoria == "EQUIPAMENTO" for c in cubo.celulas)
        assert all(c.custo_indireto == 0.0 for c in cubo.celulas)

    def test_soma_celulas_da_instancia_bate_com_chamada_direta(self):
        membro = _membro()
        catalogo = {
            "insumos": [
                {
                    "codigo": "EPI-CAPACETE-3M",
                    "tipo": "MATERIAL",
                    "preco_unitario": 360.0,
                    "status": "ativo",
                    "atributos_especificos": {"vida_util_dias": 360, "funcoes_aplicaveis": None},
                }
            ]
        }
        cubo = CuboRosterRealBuilder().build(_canonical(), [membro], [], catalogo)

        esperado = custo_semanal_individual_mo(membro, "2026-W01", "2026-W05", catalogo)
        soma_esperada = round(sum(item["custo_total"] for item in esperado), 2)
        soma_cubo = round(sum(c.custo_total for c in cubo.celulas), 2)
        assert soma_cubo == pytest.approx(soma_esperada)

    def test_soma_celulas_eq_bate_com_chamada_direta(self):
        ativo = _ativo()
        cubo = CuboRosterRealBuilder().build(_canonical(), [], [ativo], None)

        esperado = custo_semanal_individual_eq(ativo, "2026-W01", "2026-W05")
        soma_esperada = round(sum(item["custo_total"] for item in esperado), 2)
        soma_cubo = round(sum(c.custo_total for c in cubo.celulas), 2)
        assert soma_cubo == pytest.approx(soma_esperada)

    def test_multiplos_membros_e_ativos_combinados(self):
        m1 = _membro(individuo_id="mo-001", funcao_id="MO-ARMADOR")
        m2 = _membro(individuo_id="mo-002", funcao_id="MO-CARPINTEIRO")
        a1 = _ativo(ativo_id="eq-001", equip_id="EQ-ESCAVADEIRA")
        cubo = CuboRosterRealBuilder().build(_canonical(), [m1, m2], [a1], None)
        instancias = {c.instancia_id for c in cubo.celulas}
        assert instancias == {"mo-001", "mo-002", "eq-001"}
