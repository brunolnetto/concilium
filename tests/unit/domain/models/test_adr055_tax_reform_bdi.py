"""Tests for ADR-055: CBS/IBS tax reform BDI simulator.

Covers:
- TaxSimulationScenario value object: immutability, serialization
- tributos_efetivos_por_categoria: formula correctness
- custo_carregamento_df: lag cost calculation
- CENARIOS_TRIBUTARIOS: canonical scenarios
- resolver_bdi_cbs_ibs: TCU formula invariants
- Backward compat: PRE_REFORMA returns base table unchanged
- Credit ratio = 0: T_efetivo == T_bruto (no benefit)
- Credit ratio = 1: only CSSL + IR remain (full recovery)
- BDI with CBS/IBS < BDI with equivalent pre-reforma rates (credit reduces burden)
- PerfilBdiProjeto.regime_version default
"""

from __future__ import annotations

import math
from datetime import datetime

import pytest

from concilium.domain.models.financial.bdi import (
    CENARIOS_TRIBUTARIOS,
    DEFAULT_BDI_TABELA,
    ComponentesBdi,
    PerfilBdiProjeto,
    TaxRegimeVersion,
    TaxSimulationScenario,
    resolver_bdi_cbs_ibs,
    resolver_bdi_jurisdicao,
)

# ---------------------------------------------------------------------------
# TaxRegimeVersion
# ---------------------------------------------------------------------------


class TestTaxRegimeVersion:
    def test_three_values(self):
        assert len(TaxRegimeVersion) == 3

    def test_string_values(self):
        assert TaxRegimeVersion.PRE_REFORMA.value == "pre_reforma"
        assert TaxRegimeVersion.TRANSICAO.value == "transicao"
        assert TaxRegimeVersion.PLENO_CBS_IBS.value == "pleno_cbs_ibs"


# ---------------------------------------------------------------------------
# TaxSimulationScenario
# ---------------------------------------------------------------------------


class TestTaxSimulationScenario:
    def test_frozen_immutable(self):
        s = TaxSimulationScenario(
            regime_version=TaxRegimeVersion.TRANSICAO,
            cbs_ibs_combined_rate=0.013,
        )
        with pytest.raises((AttributeError, TypeError)):
            s.cbs_ibs_combined_rate = 0.5  # type: ignore[misc]

    def test_to_dict_round_trip(self):
        s = TaxSimulationScenario(
            regime_version=TaxRegimeVersion.PLENO_CBS_IBS,
            cbs_ibs_combined_rate=0.265,
            credit_ratio_material=0.80,
            credit_lag_semanas=4,
            split_payment=True,
        )
        d = s.to_dict()
        s2 = TaxSimulationScenario.from_dict(d)
        assert s2.regime_version == TaxRegimeVersion.PLENO_CBS_IBS
        assert s2.cbs_ibs_combined_rate == 0.265
        assert s2.credit_ratio_material == 0.80
        assert s2.credit_lag_semanas == 4
        assert s2.split_payment is True

    def test_tributos_efetivos_pre_reforma(self):
        """PRE_REFORMA: CBS_IBS=0, credit_ratio=0 → only CSSL+IR."""
        s = CENARIOS_TRIBUTARIOS[TaxRegimeVersion.PRE_REFORMA]
        t = s.tributos_efetivos_por_categoria()
        for cat, val in t.items():
            assert math.isclose(val, s.cssl_rate + s.ir_rate, rel_tol=1e-6), (
                f"PRE_REFORMA tributos_efetivos[{cat}] should be CSSL+IR={s.cssl_rate + s.ir_rate}, got {val}"
            )

    def test_tributos_efetivos_zero_credit(self):
        """credit_ratio=0: T_efetivo = CBS_IBS_bruto + CSSL + IR (no benefit)."""
        rate = 0.265
        s = TaxSimulationScenario(
            regime_version=TaxRegimeVersion.PLENO_CBS_IBS,
            cbs_ibs_combined_rate=rate,
            credit_ratio_mao_obra=0.0,
            credit_ratio_material=0.0,
            cssl_rate=0.02,
            ir_rate=0.03,
        )
        t = s.tributos_efetivos_por_categoria()
        expected = rate + 0.02 + 0.03
        assert math.isclose(t["mao_obra"], expected, rel_tol=1e-6)
        assert math.isclose(t["material"], expected, rel_tol=1e-6)

    def test_tributos_efetivos_full_credit(self):
        """credit_ratio=1: CBS/IBS fully recovered — only CSSL+IR remain."""
        rate = 0.265
        s = TaxSimulationScenario(
            regime_version=TaxRegimeVersion.PLENO_CBS_IBS,
            cbs_ibs_combined_rate=rate,
            credit_ratio_material=1.0,
            cssl_rate=0.02,
            ir_rate=0.03,
        )
        t = s.tributos_efetivos_por_categoria()
        assert math.isclose(t["material"], 0.02 + 0.03, rel_tol=1e-6)

    def test_tributos_efetivos_partial_credit(self):
        """Partial credit: T_ef = CBS_IBS×(1-ratio) + CSSL + IR."""
        rate, ratio, cssl, ir = 0.265, 0.75, 0.0199, 0.0274
        s = TaxSimulationScenario(
            regime_version=TaxRegimeVersion.PLENO_CBS_IBS,
            cbs_ibs_combined_rate=rate,
            credit_ratio_material=ratio,
            cssl_rate=cssl,
            ir_rate=ir,
        )
        expected_mat = rate * (1 - ratio) + cssl + ir
        t = s.tributos_efetivos_por_categoria()
        assert math.isclose(t["material"], expected_mat, rel_tol=1e-6)

    def test_tributos_efetivos_mao_obra_always_zero_credit(self):
        """MO never generates CBS/IBS credit — T_ef_MO = CBS_IBS_bruto + CSSL + IR."""
        s = CENARIOS_TRIBUTARIOS[TaxRegimeVersion.PLENO_CBS_IBS]
        t = s.tributos_efetivos_por_categoria()
        # MO credit_ratio = 0 in canonical scenario
        expected = s.cbs_ibs_combined_rate + s.cssl_rate + s.ir_rate
        assert math.isclose(t["mao_obra"], expected, rel_tol=1e-6)

    def test_custo_carregamento_zero_lag(self):
        s = TaxSimulationScenario(
            regime_version=TaxRegimeVersion.TRANSICAO,
            cbs_ibs_combined_rate=0.013,
            credit_lag_semanas=0,
        )
        assert s.custo_carregamento_df(credit_ratio=0.75) == 0.0

    def test_custo_carregamento_formula(self):
        """df_adicional = CBS_IBS × credit_ratio × (lag/52) × taxa."""
        rate, ratio, lag, taxa = 0.265, 0.80, 4, 0.12
        s = TaxSimulationScenario(
            regime_version=TaxRegimeVersion.PLENO_CBS_IBS,
            cbs_ibs_combined_rate=rate,
            credit_lag_semanas=lag,
            taxa_financ_anual=taxa,
        )
        expected = rate * ratio * (lag / 52.0) * taxa
        assert math.isclose(s.custo_carregamento_df(ratio), expected, abs_tol=1e-5)


# ---------------------------------------------------------------------------
# CENARIOS_TRIBUTARIOS
# ---------------------------------------------------------------------------


class TestCenariosTributarios:
    def test_all_three_regimes_present(self):
        assert TaxRegimeVersion.PRE_REFORMA in CENARIOS_TRIBUTARIOS
        assert TaxRegimeVersion.TRANSICAO in CENARIOS_TRIBUTARIOS
        assert TaxRegimeVersion.PLENO_CBS_IBS in CENARIOS_TRIBUTARIOS

    def test_pre_reforma_has_zero_cbs_ibs(self):
        s = CENARIOS_TRIBUTARIOS[TaxRegimeVersion.PRE_REFORMA]
        assert s.cbs_ibs_combined_rate == 0.0
        assert s.credit_lag_semanas == 0

    def test_pleno_has_split_payment(self):
        s = CENARIOS_TRIBUTARIOS[TaxRegimeVersion.PLENO_CBS_IBS]
        assert s.split_payment is True

    def test_pleno_rate_positive(self):
        s = CENARIOS_TRIBUTARIOS[TaxRegimeVersion.PLENO_CBS_IBS]
        assert s.cbs_ibs_combined_rate > 0

    def test_tributos_efetivos_pleno_material_less_than_bruto(self):
        """With credit_ratio > 0, T_efetivo < T_bruto."""
        s = CENARIOS_TRIBUTARIOS[TaxRegimeVersion.PLENO_CBS_IBS]
        t = s.tributos_efetivos_por_categoria()
        bruto = s.cbs_ibs_combined_rate + s.cssl_rate + s.ir_rate
        assert t["material"] < bruto


# ---------------------------------------------------------------------------
# resolver_bdi_cbs_ibs
# ---------------------------------------------------------------------------


class TestResolverBdiCbsIbs:
    def test_pre_reforma_returns_base_unchanged(self):
        """PRE_REFORMA is a noop — returns base table as-is."""
        scenario = CENARIOS_TRIBUTARIOS[TaxRegimeVersion.PRE_REFORMA]
        result = resolver_bdi_cbs_ibs(DEFAULT_BDI_TABELA, scenario)
        assert result is DEFAULT_BDI_TABELA

    def test_cbs_ibs_changes_bdi_total(self):
        """CBS/IBS scenario produces different BDI than PRE_REFORMA."""
        scenario = CENARIOS_TRIBUTARIOS[TaxRegimeVersion.PLENO_CBS_IBS]
        result = resolver_bdi_cbs_ibs(DEFAULT_BDI_TABELA, scenario)
        assert result is not DEFAULT_BDI_TABELA
        assert result.mao_obra.bdi_total != DEFAULT_BDI_TABELA.mao_obra.bdi_total

    def test_bdi_formula_still_valid_tcu(self):
        """TCU formula multiplicativa: (1+AC)(1+DF)(1+R)(1+CR)(1+L)/(1-T)-1 é válida para CBS/IBS."""
        scenario = CENARIOS_TRIBUTARIOS[TaxRegimeVersion.PLENO_CBS_IBS]
        tabela = resolver_bdi_cbs_ibs(DEFAULT_BDI_TABELA, scenario)
        for comp_name in ("mao_obra", "material", "diesel", "servicos", "indireto"):
            comp: ComponentesBdi = getattr(tabela, comp_name)
            # Fórmula multiplicativa TCU Acórdão 2622/2013
            overhead_mult = (1 + comp.ac) * (1 + comp.df) * (1 + comp.r) * (1 + comp.cr) * (1 + comp.l)
            T = comp.tributos
            expected_bdi = overhead_mult / (1 - T) - 1
            assert math.isclose(comp.bdi_total, expected_bdi, rel_tol=1e-5), (
                f"{comp_name}: formula mismatch bdi_total={comp.bdi_total}, expected={expected_bdi}"
            )

    def test_material_bdi_lower_with_full_credit_than_no_credit(self):
        """More credit recovery → lower T_ef → lower BDI for same cost base."""
        scenario_full = TaxSimulationScenario(
            regime_version=TaxRegimeVersion.PLENO_CBS_IBS,
            cbs_ibs_combined_rate=0.265,
            credit_ratio_material=0.90,
            cssl_rate=0.02,
            ir_rate=0.03,
        )
        scenario_zero = TaxSimulationScenario(
            regime_version=TaxRegimeVersion.PLENO_CBS_IBS,
            cbs_ibs_combined_rate=0.265,
            credit_ratio_material=0.0,
            cssl_rate=0.02,
            ir_rate=0.03,
        )
        t_full = resolver_bdi_cbs_ibs(DEFAULT_BDI_TABELA, scenario_full)
        t_zero = resolver_bdi_cbs_ibs(DEFAULT_BDI_TABELA, scenario_zero)
        assert t_full.material.bdi_total < t_zero.material.bdi_total

    def test_lag_cost_increases_df(self):
        """Credit lag adds to df component."""
        scenario_no_lag = TaxSimulationScenario(
            regime_version=TaxRegimeVersion.PLENO_CBS_IBS,
            cbs_ibs_combined_rate=0.265,
            credit_ratio_material=0.80,
            credit_lag_semanas=0,
        )
        scenario_with_lag = TaxSimulationScenario(
            regime_version=TaxRegimeVersion.PLENO_CBS_IBS,
            cbs_ibs_combined_rate=0.265,
            credit_ratio_material=0.80,
            credit_lag_semanas=8,
            taxa_financ_anual=0.12,
        )
        t_no_lag = resolver_bdi_cbs_ibs(DEFAULT_BDI_TABELA, scenario_no_lag)
        t_with_lag = resolver_bdi_cbs_ibs(DEFAULT_BDI_TABELA, scenario_with_lag)
        # Lag adds to df, which increases bdi
        assert t_with_lag.material.df > t_no_lag.material.df

    def test_overhead_components_preserved(self):
        """ac, r, cr, l from base table are preserved (only tributos and df change)."""
        scenario = CENARIOS_TRIBUTARIOS[TaxRegimeVersion.PLENO_CBS_IBS]
        result = resolver_bdi_cbs_ibs(DEFAULT_BDI_TABELA, scenario)
        for cat in ("mao_obra", "material", "diesel", "servicos", "indireto"):
            base_comp: ComponentesBdi = getattr(DEFAULT_BDI_TABELA, cat)
            res_comp: ComponentesBdi = getattr(result, cat)
            assert res_comp.ac == base_comp.ac
            assert res_comp.r == base_comp.r
            assert res_comp.cr == base_comp.cr
            assert res_comp.l == base_comp.l

    def test_iss_pis_zeroed_in_cbs_ibs(self):
        """iss and pis are zeroed in CBS/IBS regime — replaced by cofins (CBS+IBS net)."""
        scenario = CENARIOS_TRIBUTARIOS[TaxRegimeVersion.PLENO_CBS_IBS]
        result = resolver_bdi_cbs_ibs(DEFAULT_BDI_TABELA, scenario)
        assert result.mao_obra.iss == 0.0
        assert result.mao_obra.pis == 0.0
        assert result.material.iss == 0.0
        assert result.material.pis == 0.0


# ---------------------------------------------------------------------------
# resolver_bdi_jurisdicao (ADR-038 — fecha o gap "UF não influencia o BDI real")
# ---------------------------------------------------------------------------


class TestResolverBdiJurisdicao:
    def test_iss_sobrescrito_em_categorias_com_iss(self):
        """mao_obra/servicos/indireto têm ISS > 0 na base — devem receber a alíquota
        da jurisdição (ex.: BR-CE, 2%, diferente do default 5%)."""
        aliquotas = {"ISS": 0.02, "PIS": 0.0065, "COFINS": 0.03, "CPRB": 0.045}
        result = resolver_bdi_jurisdicao(DEFAULT_BDI_TABELA, aliquotas)
        assert result.mao_obra.iss == 0.02
        assert result.servicos.iss == 0.02
        assert result.indireto.iss == 0.02

    def test_material_diesel_nao_ganham_iss_por_nao_terem_na_base(self):
        """material/diesel têm ISS=0 na base (fornecimento de mercadoria, ADR-090) —
        jurisdição NUNCA deve fazer ISS passar a incidir sobre eles."""
        aliquotas = {"ISS": 0.05, "PIS": 0.0065, "COFINS": 0.03, "CPRB": 0.045}
        result = resolver_bdi_jurisdicao(DEFAULT_BDI_TABELA, aliquotas)
        assert result.material.iss == 0.0
        assert result.diesel.iss == 0.0

    def test_muda_bdi_total_quando_iss_diferente_do_default(self):
        aliquotas_ce = {"ISS": 0.02, "PIS": 0.0065, "COFINS": 0.03, "CPRB": 0.045}
        result = resolver_bdi_jurisdicao(DEFAULT_BDI_TABELA, aliquotas_ce)
        assert result.mao_obra.bdi_total != DEFAULT_BDI_TABELA.mao_obra.bdi_total
        # ISS menor -> T menor -> BDI menor (fórmula TCU: overhead/(1-T)-1, T no denominador)
        assert result.mao_obra.bdi_total < DEFAULT_BDI_TABELA.mao_obra.bdi_total

    def test_overhead_e_cssl_ir_preservados(self):
        aliquotas = {"ISS": 0.02, "PIS": 0.0065, "COFINS": 0.03, "CPRB": 0.045}
        result = resolver_bdi_jurisdicao(DEFAULT_BDI_TABELA, aliquotas)
        for cat in ("mao_obra", "material", "diesel", "servicos", "indireto"):
            base_comp: ComponentesBdi = getattr(DEFAULT_BDI_TABELA, cat)
            res_comp: ComponentesBdi = getattr(result, cat)
            assert res_comp.ac == base_comp.ac
            assert res_comp.df == base_comp.df
            assert res_comp.r == base_comp.r
            assert res_comp.cr == base_comp.cr
            assert res_comp.l == base_comp.l
            assert res_comp.cssl == base_comp.cssl
            assert res_comp.ir == base_comp.ir

    def test_aliquota_ausente_no_dict_preserva_base(self):
        """Dict só com ISS (sem PIS/COFINS) não zera os demais — mantém os da base."""
        result = resolver_bdi_jurisdicao(DEFAULT_BDI_TABELA, {"ISS": 0.02})
        assert result.mao_obra.iss == 0.02
        assert result.mao_obra.pis == DEFAULT_BDI_TABELA.mao_obra.pis
        assert result.mao_obra.cofins == DEFAULT_BDI_TABELA.mao_obra.cofins


# ---------------------------------------------------------------------------
# PerfilBdiProjeto backward compat
# ---------------------------------------------------------------------------


class TestPerfilBdiProjetoRegimeVersion:
    def test_default_regime_is_pre_reforma(self):
        """PerfilBdiProjeto defaults to PRE_REFORMA — backward compat."""
        from concilium.domain.models.financial.bdi import (
            AplicacaoTributaria,
            CheckboxTributo,
            PerfilLucroProjeto,
            PerfilTributarioProjeto,
        )

        _check = CheckboxTributo(aplicavel=False, aliquota=0.0)
        _aplic = AplicacaoTributaria(iss=_check, cofins=_check, pis=_check, cssl=_check, ir=_check)
        perfil = PerfilBdiProjeto(
            projeto_id="test-proj",
            content_hash="abc",
            confirmado_em=datetime(2026, 1, 1),
            confirmado_por="test",
            tributario=PerfilTributarioProjeto(
                regime="lucro_presumido",
                municipio="São Paulo",
                iss_aliquota_municipal=0.05,
                mao_obra=_aplic,
                material=_aplic,
                servicos=_aplic,
                indireto=_aplic,
                diesel=_aplic,
            ),
            lucro=PerfilLucroProjeto(mao_obra=0.09, material=0.05, servicos=0.09, indireto=0.02, diesel=0.05),
        )
        assert perfil.regime_version == TaxRegimeVersion.PRE_REFORMA
