"""Tier 1 coverage — domain/models/bdi.py."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from concilium.domain.constants import BDI_CSSL, BDI_IR
from concilium.domain.models.financial.bdi import (
    CENARIOS_TRIBUTARIOS,
    DEFAULT_BDI_TABELA,
    DEFAULT_ENCARGOS,
    BdiPerfilDiff,
    ComponentesBdi,
    DecomposicaoEquipamento,
    IndiretoComBdi,
    PerfilBdiProjeto,
    TabelaBdi,
    TaxRegimeVersion,
    TaxSimulationScenario,
    resolver_bdi_cbs_ibs,
    resolver_componentes_bdi,
)

# ── TaxRegimeVersion ──────────────────────────────────────────────────────────


class TestTaxRegimeVersion:
    def test_valores_str(self):
        assert TaxRegimeVersion.PRE_REFORMA == "pre_reforma"
        assert TaxRegimeVersion.TRANSICAO == "transicao"
        assert TaxRegimeVersion.PLENO_CBS_IBS == "pleno_cbs_ibs"


# ── TaxSimulationScenario ─────────────────────────────────────────────────────


class TestTaxSimulationScenario:
    def test_tributos_efetivos_pre_reforma_zerados(self):
        s = CENARIOS_TRIBUTARIOS[TaxRegimeVersion.PRE_REFORMA]
        t = s.tributos_efetivos_por_categoria()
        # CBS/IBS=0, apenas CSSL+IR
        for cat in ("mao_obra", "material", "servicos", "diesel", "indireto"):
            assert abs(t[cat] - (BDI_CSSL + BDI_IR)) < 1e-9

    def test_tributos_efetivos_pleno_cbs_ibs(self):
        s = CENARIOS_TRIBUTARIOS[TaxRegimeVersion.PLENO_CBS_IBS]
        t = s.tributos_efetivos_por_categoria()
        # mao_obra sem crédito → carga máxima
        assert t["mao_obra"] > t["material"]  # material tem credit_ratio=0.80

    def test_custo_carregamento_zero_sem_credito(self):
        s = TaxSimulationScenario(regime_version=TaxRegimeVersion.PRE_REFORMA)
        assert s.custo_carregamento_df(0.0) == 0.0

    def test_custo_carregamento_positivo_com_credito(self):
        s = CENARIOS_TRIBUTARIOS[TaxRegimeVersion.PLENO_CBS_IBS]
        custo = s.custo_carregamento_df(0.80)
        assert custo > 0.0

    def test_to_dict_round_trip(self):
        s = CENARIOS_TRIBUTARIOS[TaxRegimeVersion.TRANSICAO]
        d = s.to_dict()
        assert d["regime_version"] == "transicao"
        s2 = TaxSimulationScenario.from_dict(d)
        assert s2.regime_version == TaxRegimeVersion.TRANSICAO
        assert abs(s2.cbs_ibs_combined_rate - s.cbs_ibs_combined_rate) < 1e-9

    def test_from_dict_defaults(self):
        s = TaxSimulationScenario.from_dict({})
        assert s.regime_version == TaxRegimeVersion.PRE_REFORMA
        assert s.cbs_ibs_combined_rate == 0.0

    def test_split_payment_flag(self):
        s = CENARIOS_TRIBUTARIOS[TaxRegimeVersion.PLENO_CBS_IBS]
        assert s.split_payment is True


# ── ComponentesBdi ────────────────────────────────────────────────────────────


class TestComponentesBdi:
    def _mao_obra(self) -> ComponentesBdi:
        return DEFAULT_BDI_TABELA.mao_obra

    def test_tributos_soma(self):
        c = self._mao_obra()
        esperado = round(c.cofins + c.iss + c.pis + c.cssl + c.ir, 6)
        assert abs(c.tributos - esperado) < 1e-9

    def test_overhead_soma(self):
        c = self._mao_obra()
        esperado = round(c.ac + c.df + c.r + c.cr + c.l, 6)
        assert abs(c.overhead - esperado) < 1e-9

    def test_bdi_total_formula_tcu(self):
        # Sem tributos: BDI = overhead puro (fórmula simplificada exata)
        c = ComponentesBdi(
            ac=0.10,
            df=0.0,
            r=0.0,
            cr=0.0,
            l=0.0,
            cofins=0.0,
            iss=0.0,
            pis=0.0,
            cssl=0.0,
            ir=0.0,
        )
        assert abs(c.bdi_total - 0.10) < 1e-9

    def test_bdi_total_positivo_com_tributos(self):
        c = self._mao_obra()
        assert c.bdi_total > 0
        assert c.bdi_total < 1.0

    def test_bdi_total_material_menor_que_mao_obra(self):
        assert DEFAULT_BDI_TABELA.material.bdi_total < DEFAULT_BDI_TABELA.mao_obra.bdi_total

    def test_bdi_total_raises_se_tributos_iguais_1(self):
        c = ComponentesBdi(
            ac=0.0,
            df=0.0,
            r=0.0,
            cr=0.0,
            l=0.0,
            cofins=0.3,
            iss=0.3,
            pis=0.3,
            cssl=0.05,
            ir=0.05,
        )
        with pytest.raises(ValueError, match="Tributos totais"):
            _ = c.bdi_total

    def test_decomposicao_soma_1(self):
        c = self._mao_obra()
        d = c.decomposicao_no_preco()
        total = sum(d.values())
        assert abs(total - 1.0) < 1e-4, f"soma={total}"

    def test_decomposicao_chaves_esperadas(self):
        d = DEFAULT_BDI_TABELA.mao_obra.decomposicao_no_preco()
        chaves = {
            "custo_direto",
            "overhead_ac",
            "overhead_df",
            "overhead_r",
            "overhead_cr",
            "margem_l",
            "tributo_cofins",
            "tributo_iss",
            "tributo_pis",
            "tributo_cssl",
            "tributo_ir",
        }
        assert chaves == set(d.keys())

    def test_componentes_imutaveis(self):
        c = DEFAULT_BDI_TABELA.mao_obra
        with pytest.raises(ValidationError):
            c.ac = 0.99


# ── TabelaBdi ─────────────────────────────────────────────────────────────────


class TestTabelaBdi:
    def test_para_categoria_mao_obra(self):
        t = DEFAULT_BDI_TABELA
        assert t.para_categoria("MAO_OBRA") == t.mao_obra

    def test_para_categoria_diesel(self):
        assert DEFAULT_BDI_TABELA.para_categoria("DIESEL") == DEFAULT_BDI_TABELA.diesel

    def test_todas_categorias_tem_bdi_positivo(self):
        for cat in ("mao_obra", "material", "servicos", "indireto", "diesel"):
            comp = getattr(DEFAULT_BDI_TABELA, cat)
            assert comp.bdi_total > 0


# ── EncargosRegime ────────────────────────────────────────────────────────────


class TestEncargosRegime:
    def test_total_soma_todos_componentes(self):
        e = DEFAULT_ENCARGOS.horistas
        esperado = round(e.a + e.b + e.c + e.d + e.e + e.f + e.judicial, 6)
        assert abs(e.total - esperado) < 1e-9

    def test_horistas_maior_que_mensalistas(self):
        assert DEFAULT_ENCARGOS.horistas.total > DEFAULT_ENCARGOS.mensalistas.total

    def test_imutavel(self):
        with pytest.raises(ValidationError):
            DEFAULT_ENCARGOS.horistas.a = 0.0


# ── TabelaEncargos ────────────────────────────────────────────────────────────


class TestTabelaEncargos:
    def test_data_vigencia(self):
        assert DEFAULT_ENCARGOS.data_vigencia == date(2026, 4, 1)

    def test_encargos_nao_negativos(self):
        for campo in ("a", "b", "c", "d", "e", "f", "judicial"):
            assert getattr(DEFAULT_ENCARGOS.horistas, campo) >= 0


# ── IndiretoComBdi ────────────────────────────────────────────────────────────


class TestIndiretoComBdi:
    def test_valor_consistente(self):
        custo = 100_000.0
        bdi = 0.2237
        custo_com = round(custo * (1 + bdi), 2)
        i = IndiretoComBdi(
            categoria="TOP",
            custo_sem_bdi=custo,
            bdi_aplicado=bdi,
            custo_com_bdi=custo_com,
        )
        assert i.custo_com_bdi == custo_com

    def test_rejeita_valor_inconsistente(self):
        with pytest.raises(ValidationError, match="diverge"):
            IndiretoComBdi(
                categoria="ADM",
                custo_sem_bdi=100_000.0,
                bdi_aplicado=0.20,
                custo_com_bdi=999.0,
            )

    def test_todas_categorias_validas(self):
        for cat in ("TOP", "ADM", "LAB", "QSMS", "MOB"):
            IndiretoComBdi(
                categoria=cat,
                custo_sem_bdi=50_000.0,
                bdi_aplicado=0.10,
                custo_com_bdi=55_000.0,
            )


# ── DecomposicaoEquipamento ───────────────────────────────────────────────────


class TestDecomposicaoEquipamento:
    def _make(self) -> DecomposicaoEquipamento:
        return DecomposicaoEquipamento(
            equip_id="ESCAV-20T",
            custo_hora_total=100.0,
            custo_mao_obra_h=30.0,
            custo_diesel_h=40.0,
            custo_material_h=10.0,
            custo_capital_h=20.0,
        )

    def test_fracoes_somam_1(self):
        d = self._make()
        total = d.fracao_mao_obra + d.fracao_diesel + d.fracao_material
        assert abs(total - 1.0) < 1e-6

    def test_fracao_mao_obra_inclui_capital(self):
        d = self._make()
        # mao_obra_h=30 + capital_h=20 = 50/100 = 0.5
        assert abs(d.fracao_mao_obra - 0.5) < 1e-6

    def test_rejeita_soma_incorreta(self):
        with pytest.raises(ValidationError, match="Soma dos componentes"):
            DecomposicaoEquipamento(
                equip_id="X",
                custo_hora_total=100.0,
                custo_mao_obra_h=30.0,
                custo_diesel_h=40.0,
                custo_material_h=10.0,
                custo_capital_h=25.0,  # soma=105, não 100
            )

    def test_imutavel(self):
        d = self._make()
        with pytest.raises(ValidationError):
            d.equip_id = "OUTRO"


# ── resolver_componentes_bdi ──────────────────────────────────────────────────


class TestResolverComponentesBdi:
    def _make_perfil(self):
        from concilium.domain.models.financial.bdi import (
            AplicacaoTributaria,
            CheckboxTributo,
            PerfilLucroProjeto,
            PerfilTributarioProjeto,
        )

        def tributo_ativo(aliq):
            return CheckboxTributo(aplicavel=True, aliquota=aliq)
        tributo_zero = CheckboxTributo(aplicavel=False, aliquota=0.0)

        aplic = AplicacaoTributaria(
            iss=tributo_ativo(0.03),
            cofins=tributo_ativo(0.03),
            pis=tributo_ativo(0.0065),
            cssl=tributo_ativo(BDI_CSSL),
            ir=tributo_ativo(BDI_IR),
        )
        aplic_zero = AplicacaoTributaria(
            iss=tributo_zero,
            cofins=tributo_zero,
            pis=tributo_zero,
            cssl=tributo_zero,
            ir=tributo_zero,
        )
        trib = PerfilTributarioProjeto(
            regime="lucro_presumido",
            municipio="Goiânia",
            iss_aliquota_municipal=0.03,
            mao_obra=aplic,
            material=aplic_zero,
            servicos=aplic,
            indireto=aplic,
            diesel=aplic,
        )
        lucro = PerfilLucroProjeto(
            mao_obra=0.09,
            material=0.05,
            servicos=0.09,
            indireto=0.02,
            diesel=0.05,
        )
        return PerfilBdiProjeto(
            projeto_id="proj-001",
            content_hash="abc123",
            confirmado_em=datetime.now(UTC),
            confirmado_por="engenheiro",
            tributario=trib,
            lucro=lucro,
        )

    def test_retorna_tabela_bdi(self):
        perfil = self._make_perfil()
        tabela = resolver_componentes_bdi(DEFAULT_BDI_TABELA, perfil)
        assert isinstance(tabela, TabelaBdi)

    def test_lucro_aplicado(self):
        perfil = self._make_perfil()
        tabela = resolver_componentes_bdi(DEFAULT_BDI_TABELA, perfil)
        assert tabela.mao_obra.l == 0.09
        assert tabela.material.l == 0.05

    def test_tributos_zerados_quando_nao_aplicavel(self):
        perfil = self._make_perfil()
        tabela = resolver_componentes_bdi(DEFAULT_BDI_TABELA, perfil)
        assert tabela.material.iss == 0.0
        assert tabela.material.cofins == 0.0


# ── resolver_bdi_cbs_ibs ──────────────────────────────────────────────────────


class TestResolverBdiCbsIbs:
    def test_pre_reforma_retorna_base_inalterada(self):
        s = CENARIOS_TRIBUTARIOS[TaxRegimeVersion.PRE_REFORMA]
        resultado = resolver_bdi_cbs_ibs(DEFAULT_BDI_TABELA, s)
        assert resultado is DEFAULT_BDI_TABELA

    def test_pleno_cbs_ibs_modifica_tributos(self):
        s = CENARIOS_TRIBUTARIOS[TaxRegimeVersion.PLENO_CBS_IBS]
        resultado = resolver_bdi_cbs_ibs(DEFAULT_BDI_TABELA, s)
        assert resultado is not DEFAULT_BDI_TABELA
        # iss e pis devem ser zerados (substituídos por CBS/IBS em cofins)
        assert resultado.mao_obra.iss == 0.0
        assert resultado.mao_obra.pis == 0.0

    def test_transicao_cbs_ibs_menor_que_pleno(self):
        s_trans = CENARIOS_TRIBUTARIOS[TaxRegimeVersion.TRANSICAO]
        s_pleno = CENARIOS_TRIBUTARIOS[TaxRegimeVersion.PLENO_CBS_IBS]
        t_trans = resolver_bdi_cbs_ibs(DEFAULT_BDI_TABELA, s_trans)
        t_pleno = resolver_bdi_cbs_ibs(DEFAULT_BDI_TABELA, s_pleno)
        assert t_trans.mao_obra.cofins < t_pleno.mao_obra.cofins


# ── BdiPerfilDiff ─────────────────────────────────────────────────────────────


class TestBdiPerfilDiff:
    def test_instanciacao(self):
        d = BdiPerfilDiff(
            projeto_id="p1",
            versao_anterior=1,
            versao_nova=2,
            perfil_anterior_id="id-1",
            perfil_novo_id="id-2",
            motivo="ISS municipal alterado",
            campos_alterados=["tributario.mao_obra.iss.aliquota"],
            resumo="ISS passou de 3% para 4%",
        )
        assert d.versao_nova == 2
        assert len(d.campos_alterados) == 1

    def test_diff_id_gerado_automaticamente(self):
        d1 = BdiPerfilDiff(
            projeto_id="p1",
            versao_anterior=1,
            versao_nova=2,
            perfil_anterior_id="a",
            perfil_novo_id="b",
            motivo="X",
            campos_alterados=[],
            resumo="X",
        )
        d2 = BdiPerfilDiff(
            projeto_id="p1",
            versao_anterior=1,
            versao_nova=2,
            perfil_anterior_id="a",
            perfil_novo_id="b",
            motivo="X",
            campos_alterados=[],
            resumo="X",
        )
        assert d1.diff_id != d2.diff_id
