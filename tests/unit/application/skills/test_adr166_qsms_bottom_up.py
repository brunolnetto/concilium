"""ADR-166 D2 — Composição QSMS bottom-up (EPI+treinamento+exame por função): TDD.

Substitui a verba lump default ("EPIs e treinamentos" R$3000/mês,
`_dimensionamento.py:_composicao_default_por_categoria`) por um cálculo real
por função, usando o catálogo populado pela ADR-165 (vida_util_dias,
funcoes_aplicaveis) e o headcount direto (`EquipeDireta.funcoes`).

Escrito antes da implementação (red phase).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from concilium.domain.constants import SEMANAS_POR_MES

_DIAS_POR_MES = SEMANAS_POR_MES * 7
_ROOT = Path(__file__).resolve().parents[4]


def _load_dimensionamento():
    path = (
        _ROOT
        / "src/concilium/application/skills/manifests"
        / "06-resultado-financeiro/_indiretos/_skill_helpers/_dimensionamento.py"
    )
    spec = importlib.util.spec_from_file_location("adr166_dimensionamento", path)
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


class TestComposicaoQsmsBottomUp:
    def _import(self):
        return _load_dimensionamento()._composicao_qsms_bottom_up

    def test_sem_catalogo_retorna_none(self):
        fn = self._import()
        assert fn([_equipe([("MO-X", 1)])], None) is None

    def test_catalogo_sem_itens_rh_retorna_none(self):
        fn = self._import()
        catalogo = {"insumos": [_insumo("MA-CIMENTO", "MATERIAL", 30.0, None)]}
        assert fn([_equipe([("MO-X", 1)])], catalogo) is None

    def test_sem_equipes_diretas_retorna_none(self):
        fn = self._import()
        catalogo = {"insumos": [_insumo("EPI-CAPACETE-3M", "MATERIAL", 170.0, 360)]}
        assert fn([], catalogo) is None

    def test_item_comum_aplica_a_qualquer_funcao(self):
        fn = self._import()
        catalogo = {"insumos": [_insumo("EPI-CAPACETE-3M", "MATERIAL", 360.0, 360)]}
        comp = fn([_equipe([("MO-ARMADOR", 1)])], catalogo)
        assert comp is not None
        esperado = round(360.0 / 360 * _DIAS_POR_MES, 2)
        assert comp["verbas"]["custo_fixo_mensal"] == pytest.approx(esperado)

    def test_item_especifico_so_conta_para_funcao_listada(self):
        fn = self._import()
        catalogo = {
            "insumos": [
                _insumo("TRE-OP-MOTOSSERRA", "TREINAMENTO", 450.0, 360, funcoes_aplicaveis=["MO-OPERADOR-MOTOSSERRA"]),
            ]
        }
        comp_com = fn([_equipe([("MO-OPERADOR-MOTOSSERRA", 1)])], catalogo)
        comp_sem = fn([_equipe([("MO-ARMADOR", 1)])], catalogo)
        assert comp_com is not None
        assert comp_sem is None  # nenhum item se aplica a MO-ARMADOR aqui

    def test_funcoes_aplicaveis_vazia_nao_aplica_a_ninguem(self):
        fn = self._import()
        catalogo = {
            "insumos": [_insumo("TRE-NR22-MINERACAO", "TREINAMENTO", 315.0, 360, funcoes_aplicaveis=[])]
        }
        comp = fn([_equipe([("MO-ARMADOR", 1)]), _equipe([("MO-OPERADOR-MOTOSSERRA", 2)])], catalogo)
        assert comp is None

    def test_soma_por_headcount_da_funcao(self):
        fn = self._import()
        catalogo = {"insumos": [_insumo("EXA-CLINICO", "EXAME", 46.0, 360)]}
        comp = fn([_equipe([("MO-ARMADOR", 3)])], catalogo)
        unit = round(46.0 / 360 * _DIAS_POR_MES, 2)
        assert comp["verbas"]["custo_fixo_mensal"] == pytest.approx(round(unit * 3, 2), abs=0.05)

    def test_material_sem_prefixo_epi_e_ignorado(self):
        fn = self._import()
        catalogo = {"insumos": [_insumo("MA-AREIA", "MATERIAL", 100.0, 360)]}
        assert fn([_equipe([("MO-ARMADOR", 1)])], catalogo) is None

    def test_insumo_descontinuado_e_ignorado(self):
        fn = self._import()
        catalogo = {
            "insumos": [_insumo("EPI-CAPACETE-3M", "MATERIAL", 360.0, 360, status="descontinuado")]
        }
        assert fn([_equipe([("MO-ARMADOR", 1)])], catalogo) is None

    def test_itens_do_resultado_tem_um_por_funcao_com_custo(self):
        fn = self._import()
        catalogo = {"insumos": [_insumo("EPI-CAPACETE-3M", "MATERIAL", 360.0, 360)]}
        comp = fn(
            [_equipe([("MO-ARMADOR", 1), ("MO-CARPINTEIRO", 2)])],
            catalogo,
        )
        funcoes_no_resultado = {item["funcao_id"] for item in comp["verbas"]["itens"]}
        assert funcoes_no_resultado == {"MO-ARMADOR", "MO-CARPINTEIRO"}

    def test_soma_multiplos_itens_epi_treinamento_exame(self):
        fn = self._import()
        catalogo = {
            "insumos": [
                _insumo("EPI-CAPACETE-3M", "MATERIAL", 170.0, 360),
                _insumo("TRE-NR6-USO-EPI", "TREINAMENTO", 150.0, 360),
                _insumo("EXA-CLINICO", "EXAME", 46.0, 360),
            ]
        }
        comp = fn([_equipe([("MO-ARMADOR", 1)])], catalogo)
        esperado = round((170.0 + 150.0 + 46.0) / 360 * _DIAS_POR_MES, 2)
        assert comp["verbas"]["custo_fixo_mensal"] == pytest.approx(esperado, abs=0.05)
