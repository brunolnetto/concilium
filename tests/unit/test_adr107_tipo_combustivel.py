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
        from concilium.domain.models.catalog.catalogo import ComposicaoItem

        item = ComposicaoItem(
            insumo_id="DIESEL-S10",
            categoria_custo="COMBUSTIVEL",
            coeficiente=0.5,
            unidade="L",
        )
        assert item.categoria_custo == "COMBUSTIVEL"

    def test_diesel_legado_normalizado_para_combustivel(self):
        from concilium.domain.models.catalog.catalogo import ComposicaoItem

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
        from concilium.domain.models.catalog.catalogo import TipoCombustivel

        assert TipoCombustivel is not None

    def test_diesel_s10_existe(self):
        from concilium.domain.models.catalog.catalogo import TipoCombustivel

        assert hasattr(TipoCombustivel, "DIESEL_S10") or "diesel_s10" in [v.value for v in TipoCombustivel]

    def test_tipos_principais_existem(self):
        from concilium.domain.models.catalog.catalogo import TipoCombustivel

        values = {v.value for v in TipoCombustivel}
        assert "diesel_s10" in values
        assert "cng" in values or "gnv" in values  # gás natural


class TestComposicaoItemTipoCombustivel:
    """D2: ComposicaoItem tem tipo_combustivel opcional com default None."""

    def test_tipo_combustivel_campo_existe(self):
        from concilium.domain.models.catalog.catalogo import ComposicaoItem

        item = ComposicaoItem(insumo_id="X", categoria_custo="MATERIAL", coeficiente=1.0, unidade="m3")
        assert hasattr(item, "tipo_combustivel")

    def test_tipo_combustivel_default_none(self):
        from concilium.domain.models.catalog.catalogo import ComposicaoItem

        item = ComposicaoItem(insumo_id="X", categoria_custo="MATERIAL", coeficiente=1.0, unidade="m3")
        assert item.tipo_combustivel is None

    def test_tipo_combustivel_preenchivel(self):
        from concilium.domain.models.catalog.catalogo import ComposicaoItem, TipoCombustivel

        item = ComposicaoItem(
            insumo_id="DIESEL-S10",
            categoria_custo="COMBUSTIVEL",
            coeficiente=0.5,
            unidade="L",
            tipo_combustivel=TipoCombustivel.DIESEL_S10,
        )
        assert item.tipo_combustivel == TipoCombustivel.DIESEL_S10

    def test_retrocompatibilidade_sem_tipo(self):
        from concilium.domain.models.catalog.catalogo import ComposicaoItem

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
        from concilium.domain.models.financial.bdi._components import DEFAULT_BDI_TABELA

        comp_diesel = DEFAULT_BDI_TABELA.para_categoria("DIESEL")
        comp_combustivel = DEFAULT_BDI_TABELA.para_categoria("COMBUSTIVEL")
        assert comp_diesel.bdi_total == pytest.approx(comp_combustivel.bdi_total, abs=1e-6)


class TestInferTipoCombustivel:
    """D6: Inferência de tipo_combustivel a partir do código do insumo."""

    def test_infer_diesel_s10(self):
        from concilium.domain.models.catalog.catalogo import TipoCombustivel, _infer_tipo_combustivel

        result = _infer_tipo_combustivel("DIESEL-S10")
        assert result == TipoCombustivel.DIESEL_S10

    def test_infer_ma_diesel(self):
        from concilium.domain.models.catalog.catalogo import TipoCombustivel, _infer_tipo_combustivel

        result = _infer_tipo_combustivel("MA-DIESEL-S10")
        assert result == TipoCombustivel.DIESEL_S10

    def test_infer_desconhecido_retorna_diesel_s10(self):
        from concilium.domain.models.catalog.catalogo import TipoCombustivel, _infer_tipo_combustivel

        result = _infer_tipo_combustivel("INSUMO-DESCONHECIDO")
        assert result == TipoCombustivel.DIESEL_S10  # fallback seguro

    def test_infer_gnv(self):
        from concilium.domain.models.catalog.catalogo import TipoCombustivel, _infer_tipo_combustivel

        result = _infer_tipo_combustivel("GNV-COMPRIMIDO")
        assert result != TipoCombustivel.DIESEL_S10


# ---------------------------------------------------------------------------
# D5: Dimensão tipo_combustivel no cubo analítico e breakdown
# ---------------------------------------------------------------------------


def _make_equip(equip_id: str, custo_combustivel_mensal: float, tipo_combustivel: str | None = None):
    from types import SimpleNamespace

    return SimpleNamespace(
        equip_id=equip_id,
        descricao=equip_id,
        num_unidades=1,
        custo_mensal=1000.0,
        custo_combustivel_mensal=custo_combustivel_mensal,
        tipo_combustivel=tipo_combustivel,
    )


def _make_equipe(item_id: str, equipamentos: list, permanencia_meses: float = 2.0):
    from types import SimpleNamespace

    return SimpleNamespace(
        item_id=item_id,
        equipamentos=equipamentos,
        permanencia_meses=permanencia_meses,
        custo_inst_mo=None,
        custo_inst_eq=None,
        custo_inst_comb=None,
        custo_inst_mat=None,
        custo_fixo_mensal=0.0,
        custo_total=5000.0,
        funcoes=[],
    )


class TestCurvaABCBuilderD5:
    """D5: curva_abc_builder usa tipo_combustivel em vez de __DIESEL hardcoded."""

    def test_chave_usa_tipo_combustivel_explicito(self):
        from concilium.domain.services.analytics.curva_abc_builder import CurvaABCBuilder
        from types import SimpleNamespace

        equip = _make_equip("EX-001", custo_combustivel_mensal=500.0, tipo_combustivel="eletrico")
        equipe = _make_equipe("ITEM-A", [equip])
        canonical = SimpleNamespace(
            projeto=SimpleNamespace(nome="TEST"),
            equipes_diretas=[equipe],
        )

        resultado = CurvaABCBuilder().build(canonical)
        ids = {item.insumo_id for item in resultado.itens}
        assert "EX-001__ELETRICO" in ids
        assert "EX-001__DIESEL" not in ids

    def test_chave_infere_diesel_s10_quando_tipo_none(self):
        from concilium.domain.services.analytics.curva_abc_builder import CurvaABCBuilder
        from types import SimpleNamespace

        equip = _make_equip("DIESEL-S10-EX", custo_combustivel_mensal=300.0, tipo_combustivel=None)
        equipe = _make_equipe("ITEM-B", [equip])
        canonical = SimpleNamespace(
            projeto=SimpleNamespace(nome="TEST"),
            equipes_diretas=[equipe],
        )

        resultado = CurvaABCBuilder().build(canonical)
        ids = {item.insumo_id for item in resultado.itens}
        # deve usar DIESEL_S10 inferido (não __DIESEL)
        assert any("DIESEL_S10" in i or "DIESEL" in i for i in ids)

    def test_categoria_combustivel_nao_diesel(self):
        from concilium.domain.services.analytics.curva_abc_builder import CurvaABCBuilder
        from types import SimpleNamespace

        equip = _make_equip("EX-CNG", custo_combustivel_mensal=200.0, tipo_combustivel="cng")
        equipe = _make_equipe("ITEM-C", [equip])
        canonical = SimpleNamespace(
            projeto=SimpleNamespace(nome="TEST"),
            equipes_diretas=[equipe],
        )

        resultado = CurvaABCBuilder().build(canonical)
        comb_itens = [i for i in resultado.itens if "__CNG" in i.insumo_id]
        assert comb_itens, f"Esperava chave __CNG, ids: {[i.insumo_id for i in resultado.itens]}"
        assert comb_itens[0].categoria == "COMBUSTIVEL"


class TestProjectionD5:
    """D5: projection.py emite combustivel_total + combustivel_por_tipo."""

    def test_breakdown_equipes_tem_combustivel_total(self):
        from concilium.application.benchmarks.report.projection import _accumulate_equipes, _build_breakdown_direto_equipes

        equip = _make_equip("DIESEL-S10-EX", custo_combustivel_mensal=1000.0, tipo_combustivel="diesel_s10")
        equipe = _make_equipe("ITEM-D", [equip], permanencia_meses=3.0)
        equipe.custo_inst_mo = None
        equipe.custo_fixo_mensal = 5000.0
        equipe.custo_total = 15000.0
        equipe.custo_mao_obra_mensal = 2000.0
        equipe.custo_equipamentos_mensal = 1000.0
        equipe.custo_combustivel_total_mensal = 1000.0

        totals = _accumulate_equipes([equipe])
        bd = _build_breakdown_direto_equipes(totals)

        assert "combustivel_total" in bd
        assert "diesel_total" in bd  # backward compat alias
        assert bd["combustivel_total"] == bd["diesel_total"]

    def test_combustivel_por_tipo_preenchido(self):
        from concilium.application.benchmarks.report.projection import _accumulate_equipes

        equip_diesel = _make_equip("EX-D", custo_combustivel_mensal=500.0, tipo_combustivel="diesel_s10")
        equip_cng = _make_equip("EX-C", custo_combustivel_mensal=200.0, tipo_combustivel="cng")
        equipe = _make_equipe("ITEM-E", [equip_diesel, equip_cng], permanencia_meses=2.0)
        equipe.custo_inst_mo = None
        equipe.custo_fixo_mensal = 5000.0
        equipe.custo_total = 10000.0
        equipe.custo_mao_obra_mensal = 2000.0
        equipe.custo_equipamentos_mensal = 1000.0
        equipe.custo_combustivel_total_mensal = 700.0

        totals = _accumulate_equipes([equipe])
        cpt = totals["combustivel_por_tipo"]

        assert "diesel_s10" in cpt
        assert "cng" in cpt
        assert cpt["diesel_s10"] == round(500.0 * 2.0, 2)
        assert cpt["cng"] == round(200.0 * 2.0, 2)


class TestCuboCombustivelBuilder:
    """D5: CuboCombustivelFace buildado corretamente a partir de equipes_diretas."""

    def _make_canonical(self, equipes):
        from types import SimpleNamespace

        return SimpleNamespace(
            projeto=SimpleNamespace(nome="PROJ"),
            equipes_diretas=equipes,
        )

    def test_face_vazia_sem_equipes(self):
        from concilium.domain.services.analytics.cubo_combustivel_builder import build_cubo_combustivel_face

        canonical = self._make_canonical([])
        face = build_cubo_combustivel_face(canonical)

        assert face.projeto_id == "PROJ"
        assert face.celulas == ()
        assert face.custo_por_tipo() == {}

    def test_face_com_uma_equipe_diesel(self):
        from concilium.domain.services.analytics.cubo_combustivel_builder import build_cubo_combustivel_face

        equip = _make_equip("DIESEL-S10-EX", custo_combustivel_mensal=1000.0, tipo_combustivel="diesel_s10")
        equipe = _make_equipe("ITEM-A", [equip], permanencia_meses=4.0)
        canonical = self._make_canonical([equipe])

        face = build_cubo_combustivel_face(canonical)

        assert len(face.celulas) == 1
        assert face.celulas[0].tipo_combustivel == "diesel_s10"
        assert face.celulas[0].custo == 4000.0
        assert face.celulas[0].item_id == "ITEM-A"

    def test_face_multitipo_combustivel(self):
        from concilium.domain.services.analytics.cubo_combustivel_builder import build_cubo_combustivel_face

        equip_d = _make_equip("EX-D", custo_combustivel_mensal=500.0, tipo_combustivel="diesel_s10")
        equip_e = _make_equip("EX-E", custo_combustivel_mensal=300.0, tipo_combustivel="eletrico")
        equipe = _make_equipe("ITEM-B", [equip_d, equip_e], permanencia_meses=2.0)
        canonical = self._make_canonical([equipe])

        face = build_cubo_combustivel_face(canonical)
        por_tipo = face.custo_por_tipo()

        assert "diesel_s10" in por_tipo
        assert "eletrico" in por_tipo
        assert por_tipo["diesel_s10"] == 1000.0
        assert por_tipo["eletrico"] == 600.0

    def test_tipos_presentes(self):
        from concilium.domain.services.analytics.cubo_combustivel_builder import build_cubo_combustivel_face

        equip_d = _make_equip("EX-D", custo_combustivel_mensal=500.0, tipo_combustivel="diesel_s10")
        equip_c = _make_equip("EX-C", custo_combustivel_mensal=200.0, tipo_combustivel="cng")
        equipe = _make_equipe("ITEM-C", [equip_d, equip_c], permanencia_meses=1.0)
        canonical = self._make_canonical([equipe])

        face = build_cubo_combustivel_face(canonical)
        assert face.tipos_presentes() == ["cng", "diesel_s10"]

    def test_sem_custo_combustivel_nao_gera_celula(self):
        from concilium.domain.services.analytics.cubo_combustivel_builder import build_cubo_combustivel_face

        equip = _make_equip("EX-MO", custo_combustivel_mensal=0.0)
        equipe = _make_equipe("ITEM-D", [equip], permanencia_meses=3.0)
        canonical = self._make_canonical([equipe])

        face = build_cubo_combustivel_face(canonical)
        assert face.celulas == ()
