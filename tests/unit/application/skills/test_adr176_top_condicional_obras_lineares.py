"""ADR-176 — TOP só se aplica em obras lineares (TERRAPLENAGEM/PAVIMENTACAO/
DRENAGEM/SANEAMENTO): TDD.

Mesmo padrão da ADR-169 (LAB condicional): `_composicao_default_por_categoria`
aplicava o Topógrafo (`P0057`) incondicionalmente, para qualquer projeto — sem
nenhum gate por categoria de CPU, ao contrário do LAB.

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
    spec = importlib.util.spec_from_file_location("adr176_dimensionamento", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestComposicaoDefaultTopCondicional:
    def _fn(self):
        return _load_dimensionamento()._composicao_default_por_categoria

    def _quantidade(self, result):
        return result["mao_de_obra"]["itens"][0]["quantidade"]

    def test_categorias_desconhecidas_aplica_lump_legado(self):
        """None (não foi possível determinar) preserva o comportamento antigo — sempre aplica."""
        result = self._fn()("TOP", cpu_categorias_presentes=None)
        assert self._quantidade(result) == 1

    def test_com_terraplenagem_aplica(self):
        result = self._fn()("TOP", cpu_categorias_presentes={"TERRAPLENAGEM"})
        assert self._quantidade(result) == 1

    def test_com_pavimentacao_aplica(self):
        result = self._fn()("TOP", cpu_categorias_presentes={"PAVIMENTACAO"})
        assert self._quantidade(result) == 1

    def test_com_drenagem_aplica(self):
        result = self._fn()("TOP", cpu_categorias_presentes={"DRENAGEM"})
        assert self._quantidade(result) == 1

    def test_com_saneamento_aplica(self):
        result = self._fn()("TOP", cpu_categorias_presentes={"SANEAMENTO"})
        assert self._quantidade(result) == 1

    def test_so_obras_arte_quantidade_zero(self):
        result = self._fn()("TOP", cpu_categorias_presentes={"OBRAS_ARTE"})
        assert self._quantidade(result) == 0

    def test_so_diversos_quantidade_zero(self):
        result = self._fn()("TOP", cpu_categorias_presentes={"DIVERSOS"})
        assert self._quantidade(result) == 0

    def test_conjunto_vazio_quantidade_zero(self):
        result = self._fn()("TOP", cpu_categorias_presentes=set())
        assert self._quantidade(result) == 0

    def test_adm_nao_e_afetado_pelo_gate_de_top(self):
        result = self._fn()("ADM", cpu_categorias_presentes=set())
        assert result["verbas"]["custo_fixo_mensal"] == 3500.0
