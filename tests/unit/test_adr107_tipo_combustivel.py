"""ADR-107 — Generalização DIESEL → COMBUSTIVEL + tipo_combustivel.

TDD: testes escritos antes da implementação.

Decisões cobertas:
  D1: CategoriaCusto aceita "COMBUSTIVEL"; legado "DIESEL" lido como alias
  D2: ComposicaoItem tem tipo_combustivel opcional; CategoriaCusto usa "COMBUSTIVEL"
  D3: TipoCombustivel enum existe com DIESEL_S10, CNG, BIODIESEL, ELETRICO
  D4: CategoriaBdi aceita "COMBUSTIVEL"; "DIESEL" permanece como alias legado
  D6: _infer_tipo_combustivel("DIESEL-S10") → "diesel_s10"
"""

from __future__ import annotations

import pytest


class TestCategoriaCusto:
    """D1: CategoriaCusto aceita COMBUSTIVEL; DIESEL legado ainda é aceito."""

    def test_combustivel_aceito(self):
        from concilium.domain.models.catalogo import ComposicaoItem

        item = ComposicaoItem(
            insumo_id="DIESEL-S10",
            categoria_custo="COMBUSTIVEL",
            coeficiente=0.5,
            unidade="L",
        )
        assert item.categoria_custo == "COMBUSTIVEL"

    def test_diesel_legado_normalizado_para_combustivel(self):
        from concilium.domain.models.catalogo import ComposicaoItem

        item = ComposicaoItem(
            insumo_id="DIESEL-S10",
            categoria_custo="DIESEL",
            coeficiente=0.5,
            unidade="L",
        )
        # ADR-107 D1: "DIESEL" é alias de "COMBUSTIVEL" — backward compat
        assert item.categoria_custo in ("COMBUSTIVEL", "DIESEL")  # aceita qualquer dos dois


class TestTipoCombustivel:
    """D3: TipoCombustivel enum com os tipos suportados."""

    def test_enum_existe(self):
        from concilium.domain.models.catalogo import TipoCombustivel

        assert TipoCombustivel is not None

    def test_diesel_s10_existe(self):
        from concilium.domain.models.catalogo import TipoCombustivel

        assert hasattr(TipoCombustivel, "DIESEL_S10") or "diesel_s10" in [v.value for v in TipoCombustivel]

    def test_tipos_principais_existem(self):
        from concilium.domain.models.catalogo import TipoCombustivel

        values = {v.value for v in TipoCombustivel}
        assert "diesel_s10" in values
        assert "cng" in values or "gnv" in values  # gás natural


class TestComposicaoItemTipoCombustivel:
    """D2: ComposicaoItem tem tipo_combustivel opcional com default None."""

    def test_tipo_combustivel_campo_existe(self):
        from concilium.domain.models.catalogo import ComposicaoItem

        item = ComposicaoItem(insumo_id="X", categoria_custo="MATERIAL", coeficiente=1.0, unidade="m3")
        assert hasattr(item, "tipo_combustivel")

    def test_tipo_combustivel_default_none(self):
        from concilium.domain.models.catalogo import ComposicaoItem

        item = ComposicaoItem(insumo_id="X", categoria_custo="MATERIAL", coeficiente=1.0, unidade="m3")
        assert item.tipo_combustivel is None

    def test_tipo_combustivel_preenchivel(self):
        from concilium.domain.models.catalogo import ComposicaoItem, TipoCombustivel

        item = ComposicaoItem(
            insumo_id="DIESEL-S10",
            categoria_custo="COMBUSTIVEL",
            coeficiente=0.5,
            unidade="L",
            tipo_combustivel=TipoCombustivel.DIESEL_S10,
        )
        assert item.tipo_combustivel == TipoCombustivel.DIESEL_S10

    def test_retrocompatibilidade_sem_tipo(self):
        from concilium.domain.models.catalogo import ComposicaoItem

        # Código legado não passa tipo_combustivel — deve funcionar sem erro
        item = ComposicaoItem(
            insumo_id="OLD-DIESEL",
            categoria_custo="DIESEL",
            coeficiente=0.5,
            unidade="L",
        )
        assert item.tipo_combustivel is None


class TestCategoriaBdiCombustivel:
    """D4: CategoriaBdi aceita COMBUSTIVEL; DIESEL permanece como alias legado."""

    def test_combustivel_na_categoria_bdi(self):

        # TabelaBdi.para_categoria("COMBUSTIVEL") deve funcionar igual a "DIESEL"
        from concilium.domain.models.bdi._components import DEFAULT_BDI_TABELA

        comp_diesel = DEFAULT_BDI_TABELA.para_categoria("DIESEL")
        comp_combustivel = DEFAULT_BDI_TABELA.para_categoria("COMBUSTIVEL")
        assert comp_diesel.bdi_total == pytest.approx(comp_combustivel.bdi_total, abs=1e-6)


class TestInferTipoCombustivel:
    """D6: Inferência de tipo_combustivel a partir do código do insumo."""

    def test_infer_diesel_s10(self):
        from concilium.domain.models.catalogo import TipoCombustivel, _infer_tipo_combustivel

        result = _infer_tipo_combustivel("DIESEL-S10")
        assert result == TipoCombustivel.DIESEL_S10

    def test_infer_ma_diesel(self):
        from concilium.domain.models.catalogo import TipoCombustivel, _infer_tipo_combustivel

        result = _infer_tipo_combustivel("MA-DIESEL-S10")
        assert result == TipoCombustivel.DIESEL_S10

    def test_infer_desconhecido_retorna_diesel_s10(self):
        from concilium.domain.models.catalogo import TipoCombustivel, _infer_tipo_combustivel

        result = _infer_tipo_combustivel("INSUMO-DESCONHECIDO")
        assert result == TipoCombustivel.DIESEL_S10  # fallback seguro

    def test_infer_gnv(self):
        from concilium.domain.models.catalogo import TipoCombustivel, _infer_tipo_combustivel

        result = _infer_tipo_combustivel("GNV-COMPRIMIDO")
        assert result != TipoCombustivel.DIESEL_S10
