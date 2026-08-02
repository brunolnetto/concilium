"""ADR-173 F7 — _composicao_qsms_bottom_up com roster_mo (custo indireto individualizado).

Quando o roster cobre integralmente uma função (mesmo critério de
`roster_cobre_composicao_mo`, skill-05), a contagem real de indivíduos
substitui o headcount agregado de `equipes_diretas` só para aquela função —
nunca substituição parcial, mesma disciplina do custo direto (ADR-156).
"""

from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

import pytest

from concilium.domain.constants import SEMANAS_POR_MES
from concilium.domain.models.canonical import MembroEquipeReal

_DIAS_POR_MES = SEMANAS_POR_MES * 7
_ROOT = Path(__file__).resolve().parents[4]


def _load_dimensionamento():
    path = (
        _ROOT
        / "src/concilium/application/skills/manifests"
        / "06-resultado-financeiro/_indiretos/_skill_helpers/_dimensionamento.py"
    )
    spec = importlib.util.spec_from_file_location("adr173_dimensionamento", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _equipe(funcoes: list[tuple[str, int]]):
    from concilium.domain.models.canonical import EquipeDireta, FuncaoEquipeDireta

    return EquipeDireta(
        item_id="test",
        custo_total=0.0,
        funcoes=[FuncaoEquipeDireta(funcao_id=fid, num_pessoas=n) for fid, n in funcoes],
    )


def _insumo(codigo: str, tipo: str, preco: float, vida_util_dias: int | None, funcoes_aplicaveis=None, status="ativo"):
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
        },
    }


def _membro(**overrides) -> MembroEquipeReal:
    defaults = dict(
        individuo_id="mo-001",
        funcao_id="MO-ARMADOR",
        salario_base_mensal=3000.0,
        data_admissao=date(2026, 1, 1),
    )
    defaults.update(overrides)
    return MembroEquipeReal(**defaults)


class TestComposicaoQsmsBottomUpComRoster:
    def _fn(self):
        return _load_dimensionamento()._composicao_qsms_bottom_up

    def test_sem_roster_comportamento_identico_ao_adr166(self):
        fn = self._fn()
        catalogo = {"insumos": [_insumo("EPI-CAPACETE-3M", "MATERIAL", 360.0, 360)]}
        comp = fn([_equipe([("MO-ARMADOR", 1)])], catalogo, None)
        esperado = round(360.0 / 360 * _DIAS_POR_MES, 2)
        assert comp["verbas"]["custo_fixo_mensal"] == pytest.approx(esperado)

    def test_roster_cobre_funcao_usa_contagem_real(self):
        fn = self._fn()
        catalogo = {"insumos": [_insumo("EPI-CAPACETE-3M", "MATERIAL", 360.0, 360)]}
        # equipes_diretas diz 1 pessoa, mas o roster real tem 2 (turnover dentro do mês)
        roster = [
            _membro(individuo_id="mo-001", funcao_id="MO-ARMADOR"),
            _membro(individuo_id="mo-002", funcao_id="MO-ARMADOR"),
        ]
        comp = fn([_equipe([("MO-ARMADOR", 1)])], catalogo, roster)
        item = comp["verbas"]["itens"][0]
        assert item["quantidade"] == 2
        unit = 360.0 / 360 * _DIAS_POR_MES
        assert item["valor_mensal"] == pytest.approx(round(unit * 2, 2))

    def test_roster_nao_cobre_funcao_mantem_headcount_agregado(self):
        fn = self._fn()
        catalogo = {"insumos": [_insumo("EPI-CAPACETE-3M", "MATERIAL", 360.0, 360)]}
        # equipes_diretas diz 3 pessoas, roster só tem 1 — cobertura insuficiente
        roster = [_membro(individuo_id="mo-001", funcao_id="MO-ARMADOR")]
        comp = fn([_equipe([("MO-ARMADOR", 3)])], catalogo, roster)
        item = comp["verbas"]["itens"][0]
        assert item["quantidade"] == 3

    def test_roster_de_outra_funcao_nao_afeta(self):
        fn = self._fn()
        catalogo = {"insumos": [_insumo("EPI-CAPACETE-3M", "MATERIAL", 360.0, 360)]}
        roster = [_membro(individuo_id="mo-001", funcao_id="MO-CARPINTEIRO")]
        comp = fn([_equipe([("MO-ARMADOR", 1)])], catalogo, roster)
        item = comp["verbas"]["itens"][0]
        assert item["quantidade"] == 1  # headcount agregado, roster não cobre MO-ARMADOR

    def test_multiplas_funcoes_cobertura_mista(self):
        fn = self._fn()
        catalogo = {"insumos": [_insumo("EPI-CAPACETE-3M", "MATERIAL", 360.0, 360)]}
        roster = [
            _membro(individuo_id="mo-001", funcao_id="MO-ARMADOR"),
            _membro(individuo_id="mo-002", funcao_id="MO-ARMADOR"),
        ]  # cobre ARMADOR (2>=1), não cobre CARPINTEIRO (0<1)
        comp = fn([_equipe([("MO-ARMADOR", 1), ("MO-CARPINTEIRO", 1)])], catalogo, roster)
        por_funcao = {item["funcao_id"]: item["quantidade"] for item in comp["verbas"]["itens"]}
        assert por_funcao["MO-ARMADOR"] == 2
        assert por_funcao["MO-CARPINTEIRO"] == 1
