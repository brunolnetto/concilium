"""ADR-173 F8/D13 — custo_semanal_individual_mo/_eq: lista de custo por semana
por instância (direto+indireto para MO, só direto para EQ), cuja soma é o
custo total de permanência real da instância no span informado.
"""

from __future__ import annotations

from datetime import date

import pytest

from concilium.domain.constants import SEMANAS_POR_MES
from concilium.domain.models.canonical import AtivoEquipamentoReal, MembroEquipeReal
from concilium.domain.services.financial.roster_custo_equipamento import (
    custo_real_eq_total,
    custo_semanal_individual_eq,
)
from concilium.domain.services.financial.roster_custo_mo import (
    custo_real_mo_indireto_total,
    custo_real_mo_total,
    custo_semanal_individual_mo,
)

_DIAS_POR_MES = SEMANAS_POR_MES * 7


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
        custo_manutencao_mensal_real=1500.0,
        data_contrato_inicio=date(2026, 1, 1),
    )
    defaults.update(overrides)
    return AtivoEquipamentoReal(**defaults)


def _insumo(codigo, tipo, preco, vida_util_dias=None, funcoes_aplicaveis=None):
    return {
        "codigo": codigo,
        "tipo": tipo,
        "descricao": codigo,
        "unidade": "unid",
        "preco_unitario": preco,
        "fonte_preco": "catalogo_proprio",
        "status": "ativo",
        "atributos_especificos": {
            "vida_util_dias": vida_util_dias,
            "funcoes_aplicaveis": funcoes_aplicaveis,
        },
    }


class TestCustoSemanalIndividualMo:
    def test_lista_vazia_sem_catalogo_ainda_tem_custo_direto(self):
        membro = _membro()
        item = custo_semanal_individual_mo(membro, "2026-W02", "2026-W02", None)[0]
        assert item["custo_indireto"] == 0.0
        assert item["custo_direto"] > 0.0
        assert item["custo_total"] == pytest.approx(item["custo_direto"])

    def test_soma_da_lista_bate_com_total_direto_mais_indireto(self):
        membro = _membro()
        catalogo = {"insumos": [_insumo("EPI-CAPACETE-3M", "MATERIAL", 360.0, 360)]}
        lista = custo_semanal_individual_mo(membro, "2026-W02", "2026-W05", catalogo)
        soma_total = round(sum(item["custo_total"] for item in lista), 2)
        esperado_direto = custo_real_mo_total([membro], membro.funcao_id, "2026-W02", "2026-W05")
        esperado_indireto = custo_real_mo_indireto_total([membro], membro.funcao_id, "2026-W02", "2026-W05", catalogo)
        assert soma_total == pytest.approx(round(esperado_direto + esperado_indireto, 2), abs=0.05)

    def test_semana_fora_do_span_de_admissao_nao_aparece(self):
        membro = _membro(data_admissao=date(2026, 1, 15))  # cai em 2026-W03
        lista = custo_semanal_individual_mo(membro, "2026-W02", "2026-W02", None)
        assert lista == []

    def test_semana_apos_desligamento_nao_aparece(self):
        membro = _membro(data_desligamento=date(2026, 1, 15))  # cai em 2026-W03
        lista = custo_semanal_individual_mo(membro, "2026-W02", "2026-W04", None)
        semanas = {item["semana"] for item in lista}
        assert "2026-W04" not in semanas
        assert "2026-W02" in semanas

    def test_cada_item_tem_semana_direto_indireto_total(self):
        membro = _membro()
        catalogo = {"insumos": [_insumo("EXA-CLINICO", "EXAME", 46.0, 360)]}
        lista = custo_semanal_individual_mo(membro, "2026-W02", "2026-W02", catalogo)
        item = lista[0]
        assert set(item) == {"semana", "custo_direto", "custo_indireto", "custo_total"}
        assert item["custo_total"] == pytest.approx(round(item["custo_direto"] + item["custo_indireto"], 2))


class TestCustoSemanalIndividualEq:
    def test_sem_custo_indireto_no_schema(self):
        ativo = _ativo()
        item = custo_semanal_individual_eq(ativo, "2026-W02", "2026-W02")[0]
        assert set(item) == {"semana", "custo_direto", "custo_total"}
        assert item["custo_total"] == item["custo_direto"]

    def test_soma_da_lista_bate_com_custo_real_eq_total(self):
        ativo = _ativo()
        lista = custo_semanal_individual_eq(ativo, "2026-W02", "2026-W05")
        soma_total = round(sum(item["custo_total"] for item in lista), 2)
        esperado = custo_real_eq_total([ativo], ativo.equip_id, "2026-W02", "2026-W05")
        assert soma_total == pytest.approx(esperado, abs=0.05)

    def test_semana_apos_fim_de_contrato_nao_aparece(self):
        ativo = _ativo(data_contrato_fim=date(2026, 1, 15))  # cai em 2026-W03
        lista = custo_semanal_individual_eq(ativo, "2026-W02", "2026-W04")
        semanas = {item["semana"] for item in lista}
        assert "2026-W04" not in semanas
        assert "2026-W02" in semanas
