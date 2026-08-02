"""ADR-173 F5/D7 — custo_real_mo_indireto_semanal/_total.

Custo indireto (EPI/TREINAMENTO/EXAME/BENEFICIO) por indivíduo real, paralelo a
`custo_real_mo_semanal`/`_total` (ADR-154, custo direto salário+encargos).
Reusa a mesma lógica de amortização/elegibilidade do ADR-166, agora compartilhada
via `rh_custo_catalogo.py` (ADR-173 F4) — sem reescrever a fórmula.
"""

from __future__ import annotations

from datetime import date

import pytest

from concilium.domain.constants import SEMANAS_POR_MES
from concilium.domain.models.canonical import MembroEquipeReal
from concilium.domain.services.financial.roster_custo_mo import (
    custo_real_mo_indireto_semanal,
    custo_real_mo_indireto_total,
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


class TestCustoRealMoIndiretoSemanal:
    def test_sem_catalogo_retorna_zero(self):
        membro = _membro()
        custo = custo_real_mo_indireto_semanal([membro], "MO-ARMADOR", "2026-W02", "2026-W02", None)
        assert custo["2026-W02"] == 0.0

    def test_catalogo_sem_itens_rh_retorna_zero(self):
        membro = _membro()
        catalogo = {"insumos": [_insumo("MA-CIMENTO", "MATERIAL", 30.0)]}
        custo = custo_real_mo_indireto_semanal([membro], "MO-ARMADOR", "2026-W02", "2026-W02", catalogo)
        assert custo["2026-W02"] == 0.0

    def test_item_comum_epi_conta_para_qualquer_funcao(self):
        membro = _membro()
        catalogo = {"insumos": [_insumo("EPI-CAPACETE-3M", "MATERIAL", 360.0, 360)]}
        custo = custo_real_mo_indireto_semanal([membro], "MO-ARMADOR", "2026-W02", "2026-W02", catalogo)
        esperado = round((360.0 / 360 * _DIAS_POR_MES) / SEMANAS_POR_MES, 2)
        assert custo["2026-W02"] == pytest.approx(esperado)

    def test_item_especifico_so_conta_para_funcao_listada(self):
        m_armador = _membro(individuo_id="mo-001", funcao_id="MO-ARMADOR")
        m_motosserra = _membro(individuo_id="mo-002", funcao_id="MO-OP-MOTOSSERRA")
        catalogo = {
            "insumos": [_insumo("TRE-X", "TREINAMENTO", 450.0, 360, funcoes_aplicaveis=["MO-OP-MOTOSSERRA"])]
        }
        custo_armador = custo_real_mo_indireto_semanal([m_armador], "MO-ARMADOR", "2026-W02", "2026-W02", catalogo)
        custo_motosserra = custo_real_mo_indireto_semanal(
            [m_motosserra], "MO-OP-MOTOSSERRA", "2026-W02", "2026-W02", catalogo
        )
        assert custo_armador["2026-W02"] == 0.0
        assert custo_motosserra["2026-W02"] > 0.0

    def test_beneficio_diario_amortizado_por_semana(self):
        membro = _membro()
        catalogo = {"insumos": [_insumo("BEN-ALMOCO", "BENEFICIO", 16.5, periodicidade_beneficio="diaria")]}
        custo = custo_real_mo_indireto_semanal([membro], "MO-ARMADOR", "2026-W02", "2026-W02", catalogo)
        esperado = round((16.5 * _DIAS_POR_MES) / SEMANAS_POR_MES, 2)
        assert custo["2026-W02"] == pytest.approx(esperado)

    def test_beneficio_exclui_pj_quando_positivamente_restrito(self):
        membro = _membro(funcao_id="MO-PJ")
        catalogo = {
            "insumos": [
                {"codigo": "MO-PJ", "tipo": "MAO_OBRA", "atributos_especificos": {"tipo_contrato": "PJ"}},
                _insumo(
                    "BEN-JANTAR", "BENEFICIO", 16.5, periodicidade_beneficio="diaria", aplicavel_tipo_contrato=["CLT"]
                ),
            ]
        }
        custo = custo_real_mo_indireto_semanal([membro], "MO-PJ", "2026-W02", "2026-W02", catalogo)
        assert custo["2026-W02"] == 0.0

    def test_membro_inativo_na_semana_nao_conta(self):
        membro = _membro(data_admissao=date(2026, 1, 15))  # cai em 2026-W03
        catalogo = {"insumos": [_insumo("EPI-CAPACETE-3M", "MATERIAL", 360.0, 360)]}
        custo = custo_real_mo_indireto_semanal([membro], "MO-ARMADOR", "2026-W02", "2026-W02", catalogo)
        assert custo["2026-W02"] == 0.0

    def test_multiplos_membros_somam(self):
        m1 = _membro(individuo_id="mo-001")
        m2 = _membro(individuo_id="mo-002")
        catalogo = {"insumos": [_insumo("EXA-CLINICO", "EXAME", 46.0, 360)]}
        custo_1 = custo_real_mo_indireto_semanal([m1], "MO-ARMADOR", "2026-W02", "2026-W02", catalogo)
        custo_2 = custo_real_mo_indireto_semanal([m1, m2], "MO-ARMADOR", "2026-W02", "2026-W02", catalogo)
        assert custo_2["2026-W02"] == pytest.approx(custo_1["2026-W02"] * 2, abs=0.02)

    def test_membro_de_outra_funcao_e_ignorado(self):
        membro = _membro(funcao_id="MO-ELETRICISTA")
        catalogo = {
            "insumos": [_insumo("TRE-X", "TREINAMENTO", 450.0, 360, funcoes_aplicaveis=["MO-ARMADOR"])]
        }
        custo = custo_real_mo_indireto_semanal([membro], "MO-ARMADOR", "2026-W02", "2026-W02", catalogo)
        assert custo["2026-W02"] == 0.0


class TestCustoRealMoIndiretoTotal:
    def test_total_e_soma_do_semanal(self):
        membro = _membro()
        catalogo = {"insumos": [_insumo("EPI-CAPACETE-3M", "MATERIAL", 360.0, 360)]}
        semanal = custo_real_mo_indireto_semanal([membro], "MO-ARMADOR", "2026-W02", "2026-W04", catalogo)
        total = custo_real_mo_indireto_total([membro], "MO-ARMADOR", "2026-W02", "2026-W04", catalogo)
        assert total == round(sum(semanal.values()), 2)
