"""ADR-170 — Alojamento passa a ser um BENEFICIO catalogado (BEN-ALOJAMENTO): TDD.

Substitui o hardcoded (3 quartos, 2 pessoas/quarto, R$4.000/mês) da ADR-168
por dado real do catálogo, preservando a prioridade: override de perfil
(`cat["alojamento"]`/`regra["alojamento"]`) > catálogo (`BEN-ALOJAMENTO`) >
hardcoded (só se nem perfil nem catálogo tiverem o dado).

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
    spec = importlib.util.spec_from_file_location("adr170_dimensionamento", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _beneficio_alojamento(preco=4000.0, quartos=3, pessoas=2, status="ativo"):
    return {
        "codigo": "BEN-ALOJAMENTO",
        "tipo": "BENEFICIO",
        "preco_unitario": preco,
        "status": status,
        "atributos_especificos": {
            "periodicidade_beneficio": "mensal",
            "quartos_por_casa": quartos,
            "pessoas_por_quarto": pessoas,
        },
    }


class TestAlojamentoConfigDoCatalogo:
    def _fn(self):
        return _load_dimensionamento()._alojamento_config_do_catalogo

    def test_sem_catalogo_retorna_none(self):
        assert self._fn()(None) is None

    def test_catalogo_sem_ben_alojamento_retorna_none(self):
        assert self._fn()({"insumos": []}) is None

    def test_catalogo_com_ben_alojamento_retorna_config(self):
        catalogo = {"insumos": [_beneficio_alojamento(preco=4500.0, quartos=4, pessoas=3)]}
        cfg = self._fn()(catalogo)
        assert cfg == {"quartos_por_casa": 4, "pessoas_por_quarto": 3, "valor_aluguel_mensal": 4500.0}

    def test_ben_alojamento_descontinuado_e_ignorado(self):
        catalogo = {"insumos": [_beneficio_alojamento(status="descontinuado")]}
        assert self._fn()(catalogo) is None


class TestComposicaoDefaultAdmPrioridadeFontes:
    def _fn(self):
        return _load_dimensionamento()._composicao_default_por_categoria

    def _equipes(self, num_pessoas: int):
        from concilium.domain.models.canonical import EquipeDireta, FuncaoEquipeDireta

        return [
            EquipeDireta(
                item_id="eq-1",
                custo_total=0.0,
                funcoes=[FuncaoEquipeDireta(funcao_id="MO-ARMADOR", num_pessoas=num_pessoas)],
            )
        ]

    def test_sem_perfil_e_sem_catalogo_usa_hardcoded(self):
        result = self._fn()("ADM", self._equipes(7), None, None, None)
        # hardcoded: 6/casa -> 2 casas x 4000 = 8000
        assert result["verbas"]["custo_fixo_mensal"] == 8000.0

    def test_sem_perfil_com_catalogo_usa_dado_do_catalogo(self):
        catalogo = {"insumos": [_beneficio_alojamento(preco=5000.0, quartos=5, pessoas=1)]}
        result = self._fn()("ADM", self._equipes(5), None, None, catalogo)
        # capacidade do catálogo: 5/casa -> 1 casa x 5000 (não 4000 hardcoded)
        assert result["verbas"]["custo_fixo_mensal"] == 5000.0

    def test_perfil_sobrepoe_catalogo(self):
        catalogo = {"insumos": [_beneficio_alojamento(preco=5000.0, quartos=5, pessoas=1)]}
        perfil_cfg = {"valor_aluguel_mensal": 9999.0}
        result = self._fn()("ADM", self._equipes(5), perfil_cfg, None, catalogo)
        # perfil sobrepõe só valor_aluguel_mensal; capacidade (5/casa) ainda vem do catálogo
        assert result["verbas"]["custo_fixo_mensal"] == 9999.0

    def test_catalogo_sem_ben_alojamento_cai_no_hardcoded(self):
        result = self._fn()("ADM", self._equipes(7), None, None, {"insumos": []})
        assert result["verbas"]["custo_fixo_mensal"] == 8000.0
