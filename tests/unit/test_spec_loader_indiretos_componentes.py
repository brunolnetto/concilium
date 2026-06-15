"""Spec loader — propagação de equipamentos/verbas dos indiretos (auditoria AGIS 2026-06-11).

TDD: testes escritos antes da correção.

Contexto: a planilha AGIS decompõe os indiretos em MO + EQUIPAMENTOS + VERBAS
(indiretos.adm.txt: 415.101,27 + 271.467,37 + 377.870,83 = 1.064.439,47/mês),
mas o normalize do spec_loader descartava equipamentos/verbas — só `mao_obra[]`
chegava ao skill de indiretos, e o resto caía no resíduo (verba, taxa indireta).

Correção: spec.indiretos[] aceita `equipamentos_mensal_total` e `verbas_mensal_total`;
o loader os converte em componentes IndirectoCostComponent no categorias_config,
permitindo BDI fiel por sub-categoria (equip → 4% como na planilha; verba → 25,2%).
"""

from __future__ import annotations

import pytest

from concilium.application.benchmarks.spec.spec_loader import BenchmarkSpecLoader


def _ref_minimo_com_indiretos() -> dict:
    return {
        "slug": "TESTE",
        "meta": {
            "projeto": "Teste Indiretos",
            "data_inicio": "2026-01-01",
            "data_termino": "2026-12-31",
            "localizacao": "BR",
        },
        "spec": {
            "eap": [{"item_id": "i1", "ordem": 1, "descricao": "Item", "unidade": "m3", "quantitativo": 100.0}],
            "indiretos": [
                {
                    "categoria": "ADM",
                    "driver": "mensal",
                    "custo_fixo_mensal_total": 1_064_439.47,
                    "mao_obra": [
                        {
                            "codigo": "P1",
                            "funcao": "ENG",
                            "quantidade": 1,
                            "salario_base": 10_000.0,
                            "custo_unitario": 415_101.27,
                        },
                    ],
                    "equipamentos_mensal_total": 271_467.37,
                    "verbas_mensal_total": 377_870.83,
                },
                {
                    "categoria": "LAB",
                    "driver": "mensal",
                    "custo_fixo_mensal_total": 10_847.25,
                    "mao_obra": [
                        {
                            "codigo": "P2",
                            "funcao": "LABORATORISTA",
                            "quantidade": 1,
                            "salario_base": 5_000.0,
                            "custo_unitario": 10_847.25,
                        },
                    ],
                },
            ],
        },
        "resultado": {},
    }


def _load_spec(ref: dict):
    from pathlib import Path

    loader = BenchmarkSpecLoader(Path("config"))
    return loader.load_from_dict(ref, Path("/tmp/teste-ref.json"))


def _cat_cfg(spec, categoria: str) -> dict:
    cfgs = spec.inputs_indiretos.get("categorias_config", [])
    return next((c for c in cfgs if c.get("categoria") == categoria), {})


class TestComponentesPropagados:
    def test_equipamentos_chega_ao_config(self):
        spec = _load_spec(_ref_minimo_com_indiretos())
        adm = _cat_cfg(spec, "ADM")
        eq = adm.get("equipamentos")
        assert eq is not None, "componente equipamentos não propagado"
        assert eq["custo_fixo_mensal"] == pytest.approx(271_467.37, abs=0.01)

    def test_verbas_chega_ao_config(self):
        spec = _load_spec(_ref_minimo_com_indiretos())
        adm = _cat_cfg(spec, "ADM")
        vb = adm.get("verbas")
        assert vb is not None, "componente verbas não propagado"
        assert vb["custo_fixo_mensal"] == pytest.approx(377_870.83, abs=0.01)

    def test_mao_obra_continua_propagada(self):
        spec = _load_spec(_ref_minimo_com_indiretos())
        adm = _cat_cfg(spec, "ADM")
        mo = adm.get("mao_de_obra")
        assert mo is not None
        assert mo["custo_fixo_mensal"] == pytest.approx(415_101.27, abs=0.01)

    def test_categoria_sem_componentes_extras_nao_quebra(self):
        """LAB (sem equipamentos/verbas no spec) continua funcionando."""
        spec = _load_spec(_ref_minimo_com_indiretos())
        lab = _cat_cfg(spec, "LAB")
        assert lab.get("categoria") == "LAB"
        assert lab.get("equipamentos") is None
        assert lab.get("verbas") is None

    def test_config_valida_como_indireto_categoria(self):
        """O config produzido instancia IndirectoCategoria sem erro (caminho do skill)."""
        from concilium.domain.models.canonical import IndirectoCategoria

        spec = _load_spec(_ref_minimo_com_indiretos())
        adm = _cat_cfg(spec, "ADM")
        cat_obj = IndirectoCategoria(**adm)
        assert cat_obj.equipamentos is not None
        assert cat_obj.equipamentos.custo_fixo_mensal == pytest.approx(271_467.37, abs=0.01)
        assert cat_obj.verbas.custo_fixo_mensal == pytest.approx(377_870.83, abs=0.01)
