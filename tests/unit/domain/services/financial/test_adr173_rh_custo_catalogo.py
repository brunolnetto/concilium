"""ADR-173 F4 — domain/services/financial/rh_custo_catalogo.py (extraído do ADR-166).

Testes de regressão: mesma lógica de amortização/elegibilidade que vivia em
`_dimensionamento.py`/`_mob.py` (skill-06), agora em módulo de domínio
compartilhado, reusado também por `roster_custo_mo.py` (ADR-173 F5).
"""

from __future__ import annotations

import pytest

from concilium.domain.constants import SEMANAS_POR_MES
from concilium.domain.services.financial.rh_custo_catalogo import (
    DIAS_POR_MES,
    beneficios_ativos,
    custo_mensal_beneficio_por_funcao,
    custo_mensal_rh_por_funcao,
    rh_insumos_por_tipo,
    tipo_contrato_por_funcao,
)

_DIAS_POR_MES = SEMANAS_POR_MES * 7


def _insumo(codigo, tipo, preco, vida_util_dias=None, funcoes_aplicaveis=None, status="ativo", **extra):
    return {
        "codigo": codigo,
        "tipo": tipo,
        "descricao": codigo,
        "unidade": "unid",
        "preco_unitario": preco,
        "fonte_preco": "catalogo_proprio",
        "status": status,
        "atributos_especificos": {
            "vida_util_dias": vida_util_dias,
            "funcoes_aplicaveis": funcoes_aplicaveis,
            **extra,
        },
    }


class TestDiasPorMes:
    def test_valor(self):
        assert DIAS_POR_MES == pytest.approx(_DIAS_POR_MES)


class TestRhInsumosPorTipo:
    def test_sem_catalogo(self):
        assert rh_insumos_por_tipo(None) == ([], [], [])

    def test_separa_por_tipo_e_ignora_descontinuado(self):
        catalogo = {
            "insumos": [
                _insumo("EPI-CAPACETE-3M", "MATERIAL", 170.0, 360),
                _insumo("TRE-NR6-USO-EPI", "TREINAMENTO", 150.0, 360),
                _insumo("EXA-CLINICO", "EXAME", 46.0, 360),
                _insumo("MA-AREIA", "MATERIAL", 100.0, 360),  # sem prefixo EPI-
                _insumo("EPI-OLD", "MATERIAL", 50.0, 360, status="descontinuado"),
            ]
        }
        epis, treinamentos, exames = rh_insumos_por_tipo(catalogo)
        assert [i["codigo"] for i in epis] == ["EPI-CAPACETE-3M"]
        assert [i["codigo"] for i in treinamentos] == ["TRE-NR6-USO-EPI"]
        assert [i["codigo"] for i in exames] == ["EXA-CLINICO"]


class TestCustoMensalRhPorFuncao:
    def test_item_comum(self):
        epis = [_insumo("EPI-CAPACETE-3M", "MATERIAL", 360.0, 360)]
        esperado = 360.0 / 360 * _DIAS_POR_MES
        assert custo_mensal_rh_por_funcao("MO-ARMADOR", epis) == pytest.approx(esperado)

    def test_item_especifico(self):
        treinamentos = [_insumo("TRE-X", "TREINAMENTO", 450.0, 360, funcoes_aplicaveis=["MO-OP-MOTOSSERRA"])]
        assert custo_mensal_rh_por_funcao("MO-ARMADOR", treinamentos) == 0.0
        assert custo_mensal_rh_por_funcao("MO-OP-MOTOSSERRA", treinamentos) > 0.0

    def test_sem_vida_util_ignorado(self):
        epis = [_insumo("EPI-X", "MATERIAL", 100.0, None)]
        assert custo_mensal_rh_por_funcao("MO-ARMADOR", epis) == 0.0


class TestBeneficiosAtivos:
    def test_sem_catalogo(self):
        assert beneficios_ativos(None) == []

    def test_filtra_tipo_e_status(self):
        catalogo = {
            "insumos": [
                _insumo("BEN-VALE-ALIMENTACAO", "BENEFICIO", 1260.0),
                _insumo("MA-AREIA", "MATERIAL", 100.0),
                _insumo("BEN-OLD", "BENEFICIO", 50.0, status="descontinuado"),
            ]
        }
        out = beneficios_ativos(catalogo)
        assert [i["codigo"] for i in out] == ["BEN-VALE-ALIMENTACAO"]


class TestTipoContratoPorFuncao:
    def test_mapeia_mao_obra(self):
        catalogo = {
            "insumos": [
                {"codigo": "MO-ARMADOR", "tipo": "MAO_OBRA", "atributos_especificos": {"tipo_contrato": "CLT"}},
                {"codigo": "MO-PJ", "tipo": "MAO_OBRA", "atributos_especificos": {"tipo_contrato": "PJ"}},
                {"codigo": "MA-AREIA", "tipo": "MATERIAL", "atributos_especificos": {}},
            ]
        }
        out = tipo_contrato_por_funcao(catalogo)
        assert out == {"MO-ARMADOR": "CLT", "MO-PJ": "PJ"}


class TestCustoMensalBeneficioPorFuncao:
    def test_diaria_converte_para_mensal(self):
        beneficios = [_insumo("BEN-ALMOCO", "BENEFICIO", 16.5, periodicidade_beneficio="diaria")]
        esperado = 16.5 * _DIAS_POR_MES
        assert custo_mensal_beneficio_por_funcao("MO-ARMADOR", beneficios, "CLT") == pytest.approx(esperado)

    def test_mensal_direto(self):
        beneficios = [_insumo("BEN-SEGURO-VIDA", "BENEFICIO", 35.0, periodicidade_beneficio="mensal")]
        assert custo_mensal_beneficio_por_funcao("MO-ARMADOR", beneficios, "CLT") == pytest.approx(35.0)

    def test_exclui_pj_quando_positivamente_restrito(self):
        beneficios = [
            _insumo(
                "BEN-JANTAR", "BENEFICIO", 16.5, periodicidade_beneficio="diaria", aplicavel_tipo_contrato=["CLT"]
            )
        ]
        assert custo_mensal_beneficio_por_funcao("MO-X", beneficios, "PJ") == 0.0

    def test_regime_desconhecido_recebe_beneficio(self):
        beneficios = [
            _insumo(
                "BEN-JANTAR", "BENEFICIO", 16.5, periodicidade_beneficio="diaria", aplicavel_tipo_contrato=["CLT"]
            )
        ]
        assert custo_mensal_beneficio_por_funcao("MO-X", beneficios, None) > 0.0
