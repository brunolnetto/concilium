"""ADR-169 — LAB só se aplica com TERRAPLENAGEM/PAVIMENTACAO no projeto: TDD.

Achado do engenheiro de planejamento (ex-engenheiro de campo): a verba de
laboratório (aluguel de equipamentos de ensaio) só existe em projetos com
atividades de terraplenagem ou pavimentação — hoje `_composicao_default_por_categoria`
aplica a verba de R$4.000/mês incondicionalmente, para qualquer projeto.

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
    spec = importlib.util.spec_from_file_location("adr169_dimensionamento", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _canonical_com_eap(itens: list[tuple[str, str]]):
    """itens: lista de (item_id, cpu_id)."""
    from types import SimpleNamespace

    from concilium.domain.models.canonical import EapItem

    eap = [EapItem(item_id=item_id, cpu_id=cpu_id, quantitativo=1.0) for item_id, cpu_id in itens]
    return SimpleNamespace(eap=eap)


def _catalogo_com_cpus(cpus: list[tuple[str, str]]):
    """cpus: lista de (codigo, categoria)."""
    return {"cpus": [{"codigo": codigo, "categoria": categoria} for codigo, categoria in cpus]}


class TestCategoriasCpuDoProjeto:
    def _fn(self):
        return _load_dimensionamento()._categorias_cpu_do_projeto

    def test_sem_catalogo_retorna_none(self):
        canonical = _canonical_com_eap([("I1", "CPU-1")])
        assert self._fn()(canonical, None) is None

    def test_sem_canonical_retorna_none(self):
        catalogo = _catalogo_com_cpus([("CPU-1", "TERRAPLENAGEM")])
        assert self._fn()(None, catalogo) is None

    def test_eap_vazia_retorna_none(self):
        canonical = _canonical_com_eap([])
        catalogo = _catalogo_com_cpus([("CPU-1", "TERRAPLENAGEM")])
        assert self._fn()(canonical, catalogo) is None

    def test_eap_com_terraplenagem_retorna_categoria(self):
        canonical = _canonical_com_eap([("I1", "CPU-1")])
        catalogo = _catalogo_com_cpus([("CPU-1", "TERRAPLENAGEM")])
        assert self._fn()(canonical, catalogo) == {"TERRAPLENAGEM"}

    def test_eap_so_com_drenagem_retorna_drenagem(self):
        canonical = _canonical_com_eap([("I1", "CPU-1")])
        catalogo = _catalogo_com_cpus([("CPU-1", "DRENAGEM")])
        assert self._fn()(canonical, catalogo) == {"DRENAGEM"}

    def test_multiplas_categorias(self):
        canonical = _canonical_com_eap([("I1", "CPU-1"), ("I2", "CPU-2")])
        catalogo = _catalogo_com_cpus([("CPU-1", "TERRAPLENAGEM"), ("CPU-2", "DRENAGEM")])
        assert self._fn()(canonical, catalogo) == {"TERRAPLENAGEM", "DRENAGEM"}


class TestComposicaoDefaultLabCondicional:
    def _fn(self):
        return _load_dimensionamento()._composicao_default_por_categoria

    def test_categorias_desconhecidas_aplica_lump_legado(self):
        """None (não foi possível determinar) preserva o comportamento antigo — sempre aplica."""
        result = self._fn()("LAB", cpu_categorias_presentes=None)
        assert result["verbas"]["custo_fixo_mensal"] == 4000.0

    def test_com_terraplenagem_aplica_verba(self):
        result = self._fn()("LAB", cpu_categorias_presentes={"TERRAPLENAGEM"})
        assert result["verbas"]["custo_fixo_mensal"] == 4000.0

    def test_com_pavimentacao_aplica_verba(self):
        result = self._fn()("LAB", cpu_categorias_presentes={"PAVIMENTACAO"})
        assert result["verbas"]["custo_fixo_mensal"] == 4000.0

    def test_sem_terraplenagem_ou_pavimentacao_custo_zero(self):
        result = self._fn()("LAB", cpu_categorias_presentes={"DRENAGEM", "SANEAMENTO"})
        assert result["verbas"]["custo_fixo_mensal"] == 0.0

    def test_conjunto_vazio_custo_zero(self):
        result = self._fn()("LAB", cpu_categorias_presentes=set())
        assert result["verbas"]["custo_fixo_mensal"] == 0.0

    def test_adm_nao_e_afetado_pelo_parametro_novo(self):
        result = self._fn()("ADM", cpu_categorias_presentes=set())
        assert result["verbas"]["custo_fixo_mensal"] == 3500.0
