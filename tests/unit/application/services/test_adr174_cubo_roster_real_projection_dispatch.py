"""Tests for cubo_roster_real_projection/_dispatch.py (ADR-174 F4 faces)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from concilium.application.services.analytics.cubo_roster_real_projection._dispatch import (
    _FACES,
    cubo_roster_real_projection_contract,
    resolve_cubo_roster_real_projection,
)
from concilium.domain.models.canonical import AtivoEquipamentoReal, MembroEquipeReal


def _canonical():
    return SimpleNamespace(
        projeto=SimpleNamespace(
            nome="Projeto Dispatch", id="proj-1", data_inicio=date(2026, 1, 1), data_termino=date(2026, 1, 31)
        )
    )


def _roster_mo():
    return [
        MembroEquipeReal(
            individuo_id="mo-001", funcao_id="MO-ARMADOR", salario_base_mensal=3000.0, data_admissao=date(2026, 1, 1)
        ),
        MembroEquipeReal(
            individuo_id="mo-002",
            funcao_id="MO-CARPINTEIRO",
            salario_base_mensal=2800.0,
            data_admissao=date(2026, 1, 1),
        ),
    ]


def _roster_eq():
    return [
        AtivoEquipamentoReal(
            ativo_id="eq-001",
            equip_id="EQ-ESCAVADEIRA",
            custo_locacao_mensal_real=12000.0,
            data_contrato_inicio=date(2026, 1, 1),
        )
    ]


class TestCuboRosterRealProjectionContract:
    def test_contrato_lista_todas_as_faces(self):
        contract = cubo_roster_real_projection_contract()
        assert set(contract["faces"]) == set(_FACES)
        assert contract["default_face"] == "resumo_por_instancia"


class TestCuboRosterRealProjectionDispatch:
    def test_default_face_e_resumo_por_instancia(self):
        result = resolve_cubo_roster_real_projection(_canonical(), _roster_mo(), _roster_eq())
        assert result["face"] == "resumo_por_instancia"
        instancias = {r["instancia_id"] for r in result["rows"]}
        assert instancias == {"mo-001", "mo-002", "eq-001"}

    def test_face_resumo_por_grupo(self):
        result = resolve_cubo_roster_real_projection(_canonical(), _roster_mo(), _roster_eq(), face="resumo_por_grupo")
        grupos = {r["grupo_id"] for r in result["rows"]}
        assert grupos == {"MO-ARMADOR", "MO-CARPINTEIRO", "EQ-ESCAVADEIRA"}

    def test_face_resumo_por_categoria(self):
        result = resolve_cubo_roster_real_projection(
            _canonical(), _roster_mo(), _roster_eq(), face="resumo_por_categoria"
        )
        categorias = {r["categoria"] for r in result["rows"]}
        assert categorias == {"MAO_OBRA", "EQUIPAMENTO"}

    def test_face_custo_temporal(self):
        result = resolve_cubo_roster_real_projection(_canonical(), _roster_mo(), _roster_eq(), face="custo_temporal")
        assert len(result["rows"]) > 0
        assert all("periodo" in r for r in result["rows"])

    def test_face_invalida_cai_no_default(self):
        result = resolve_cubo_roster_real_projection(_canonical(), _roster_mo(), face="nao_existe")
        assert result["face"] == "resumo_por_instancia"

    def test_granularidade_invalida_cai_em_mes(self):
        result = resolve_cubo_roster_real_projection(_canonical(), _roster_mo(), granularidade="decada")
        assert result["granularidade"] == "mes"

    def test_filtro_por_categoria(self):
        result = resolve_cubo_roster_real_projection(
            _canonical(), _roster_mo(), _roster_eq(), face="resumo_por_instancia", categoria="EQUIPAMENTO"
        )
        assert {r["categoria"] for r in result["rows"]} == {"EQUIPAMENTO"}
        assert result["filtros_aplicados"]["categoria"] == "EQUIPAMENTO"

    def test_filtro_por_instancia_id(self):
        result = resolve_cubo_roster_real_projection(
            _canonical(), _roster_mo(), _roster_eq(), face="resumo_por_instancia", instancia_id="mo-001"
        )
        assert {r["instancia_id"] for r in result["rows"]} == {"mo-001"}

    def test_truncamento_top_n(self):
        result = resolve_cubo_roster_real_projection(
            _canonical(), _roster_mo(), _roster_eq(), face="resumo_por_instancia", top_n=1
        )
        assert len(result["rows"]) == 1
        assert result["operator_meta"]["truncado"] is True

    def test_totais_presentes(self):
        result = resolve_cubo_roster_real_projection(_canonical(), _roster_mo(), _roster_eq())
        assert result["totais"]["custo_total_geral"] > 0
        assert set(result["totais"]["custo_por_categoria"]) == {"MAO_OBRA", "EQUIPAMENTO"}

    def test_sem_roster_retorna_rows_vazias_sem_erro(self):
        result = resolve_cubo_roster_real_projection(_canonical(), [], [])
        assert result["rows"] == []
        assert result["invariantes_ok"] is True
