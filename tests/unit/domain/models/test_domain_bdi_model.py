"""Tests for concilium.domain.models.financial.bdi — covers missing lines per coverage report.

The module lives in src/concilium/domain/models/bdi/ (package).
bdi_total uses the MULTIPLICATIVE TCU formula:
    (1+AC)*(1+DF)*(1+R)*(1+CR)*(1+L) / (1-T) - 1
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from concilium.domain.constants import (
    BDI_COFINS,
    BDI_CSSL,
    BDI_IR,
    BDI_ISS,
    BDI_PIS,
)
from concilium.domain.models.financial.bdi import (
    CENARIOS_TRIBUTARIOS,
    DEFAULT_BDI_TABELA,
    AplicacaoTributaria,
    BdiPerfilDiff,
    CheckboxTributo,
    ComponentesBdi,
    DecomposicaoEquipamento,
    EncargosRegime,
    IndiretoComBdi,
    PerfilBdiProjeto,
    PerfilLucroProjeto,
    PerfilTributarioProjeto,
    TabelaBdi,
    TabelaEncargos,
    TaxRegimeVersion,
    TaxSimulationScenario,
    resolver_bdi_cbs_ibs,
    resolver_componentes_bdi,
)
from concilium.domain.models.financial.bdi._profiles import resolve_bdi_tabela

# ── Helpers ────────────────────────────────────────────────────────────────


def _make_comp(
    ac=0.05,
    df=0.015,
    r=0.01,
    cr=0.0,
    l=0.09,  # noqa: E741
    cofins=0.0,
    iss=BDI_ISS,
    pis=0.0,
    cssl=BDI_CSSL,
    ir=BDI_IR,
) -> ComponentesBdi:
    return ComponentesBdi(
        ac=ac,
        df=df,
        r=r,
        cr=cr,
        l=l,
        cofins=cofins,
        iss=iss,
        pis=pis,
        cssl=cssl,
        ir=ir,
    )


def _make_tabela_bdi(vigencia=date(2026, 4, 1)) -> TabelaBdi:
    comp = _make_comp()
    return TabelaBdi(
        mao_obra=comp,
        material=_make_comp(ac=0.0, df=0.0, r=0.0, cr=0.0, l=0.04, cofins=0.0, iss=0.0, pis=0.0, cssl=0.0, ir=0.0),
        servicos=comp,
        indireto=_make_comp(ac=0.05, df=0.015, r=0.01, cr=0.0, l=0.05),
        diesel=_make_comp(ac=0.0, df=0.0, r=0.0, cr=0.0, l=0.04, cofins=0.0, iss=0.0, pis=0.0, cssl=0.0, ir=0.0),
        data_vigencia=vigencia,
    )


def _checkbox(aplicavel: bool, aliquota: float) -> CheckboxTributo:
    return CheckboxTributo(aplicavel=aplicavel, aliquota=aliquota)


def _aplic(iss_ap=True, cofins_ap=False, pis_ap=False, cssl_ap=True, ir_ap=True) -> AplicacaoTributaria:
    return AplicacaoTributaria(
        iss=_checkbox(iss_ap, BDI_ISS),
        cofins=_checkbox(cofins_ap, BDI_COFINS),
        pis=_checkbox(pis_ap, BDI_PIS),
        cssl=_checkbox(cssl_ap, BDI_CSSL),
        ir=_checkbox(ir_ap, BDI_IR),
    )


def _aplic_all_disabled() -> AplicacaoTributaria:
    return AplicacaoTributaria(
        iss=_checkbox(False, BDI_ISS),
        cofins=_checkbox(False, BDI_COFINS),
        pis=_checkbox(False, BDI_PIS),
        cssl=_checkbox(False, BDI_CSSL),
        ir=_checkbox(False, BDI_IR),
    )


def _make_perfil(regime_version: TaxRegimeVersion = TaxRegimeVersion.PRE_REFORMA) -> PerfilBdiProjeto:
    trib = PerfilTributarioProjeto(
        regime="lucro_presumido",
        municipio="São Paulo",
        iss_aliquota_municipal=0.05,
        mao_obra=_aplic(),
        material=_aplic_all_disabled(),
        servicos=_aplic(),
        indireto=_aplic(),
        diesel=_aplic_all_disabled(),
    )
    lucro = PerfilLucroProjeto(
        mao_obra=0.09,
        material=0.04,
        servicos=0.09,
        indireto=0.05,
        diesel=0.04,
    )
    return PerfilBdiProjeto(
        projeto_id="proj-001",
        content_hash="abc123",
        confirmado_em=datetime(2026, 1, 1, tzinfo=UTC),
        confirmado_por="test@test.com",
        tributario=trib,
        lucro=lucro,
        regime_version=regime_version,
    )


# ── TaxRegimeVersion (StrEnum) ─────────────────────────────────────────────


def test_tax_regime_version_pre_reforma():
    assert TaxRegimeVersion.PRE_REFORMA == "pre_reforma"


def test_tax_regime_version_transicao():
    assert TaxRegimeVersion.TRANSICAO == "transicao"


def test_tax_regime_version_pleno():
    assert TaxRegimeVersion.PLENO_CBS_IBS == "pleno_cbs_ibs"


def test_tax_regime_version_from_string():
    rv = TaxRegimeVersion("transicao")
    assert rv is TaxRegimeVersion.TRANSICAO


def test_tax_regime_version_is_str():
    assert isinstance(TaxRegimeVersion.PRE_REFORMA, str)


# ── TaxSimulationScenario ─────────────────────────────────────────────────


def test_tributos_efetivos_pre_reforma_all_zero():
    scenario = TaxSimulationScenario(
        regime_version=TaxRegimeVersion.PRE_REFORMA,
        cbs_ibs_combined_rate=0.0,
        cssl_rate=0.0,
        ir_rate=0.0,
    )
    result = scenario.tributos_efetivos_por_categoria()
    for cat in ("mao_obra", "material", "servicos", "diesel", "indireto"):
        assert result[cat] == 0.0


def test_tributos_efetivos_pleno_mao_obra_no_credit():
    scenario = TaxSimulationScenario(
        regime_version=TaxRegimeVersion.PLENO_CBS_IBS,
        cbs_ibs_combined_rate=0.265,
        credit_ratio_mao_obra=0.0,
        cssl_rate=BDI_CSSL,
        ir_rate=BDI_IR,
    )
    result = scenario.tributos_efetivos_por_categoria()
    expected_mao = round(0.265 * 1.0 + BDI_CSSL + BDI_IR, 6)
    assert result["mao_obra"] == pytest.approx(expected_mao, abs=1e-5)


def test_tributos_efetivos_pleno_material_with_credit():
    scenario = TaxSimulationScenario(
        regime_version=TaxRegimeVersion.PLENO_CBS_IBS,
        cbs_ibs_combined_rate=0.265,
        credit_ratio_material=0.80,
        cssl_rate=BDI_CSSL,
        ir_rate=BDI_IR,
    )
    result = scenario.tributos_efetivos_por_categoria()
    expected_mat = round(0.265 * 0.20 + BDI_CSSL + BDI_IR, 6)
    assert result["material"] == pytest.approx(expected_mat, abs=1e-5)


def test_tributos_efetivos_indireto_equals_servicos():
    scenario = TaxSimulationScenario(
        regime_version=TaxRegimeVersion.PLENO_CBS_IBS,
        cbs_ibs_combined_rate=0.265,
        credit_ratio_servicos=0.70,
    )
    result = scenario.tributos_efetivos_por_categoria()
    assert result["indireto"] == result["servicos"]


def test_tributos_efetivos_all_categories_present():
    scenario = TaxSimulationScenario(regime_version=TaxRegimeVersion.TRANSICAO)
    result = scenario.tributos_efetivos_por_categoria()
    assert set(result.keys()) == {"mao_obra", "material", "servicos", "diesel", "indireto"}


def test_custo_carregamento_df_zero_lag():
    scenario = TaxSimulationScenario(
        regime_version=TaxRegimeVersion.PRE_REFORMA,
        cbs_ibs_combined_rate=0.265,
        credit_lag_semanas=0,
        taxa_financ_anual=0.12,
    )
    assert scenario.custo_carregamento_df(0.80) == 0.0


def test_custo_carregamento_df_nonzero():
    scenario = TaxSimulationScenario(
        regime_version=TaxRegimeVersion.PLENO_CBS_IBS,
        cbs_ibs_combined_rate=0.265,
        credit_lag_semanas=4,
        taxa_financ_anual=0.12,
    )
    credit_ratio = 0.80
    expected = round(0.265 * credit_ratio * (4 / 52.0) * 0.12, 6)
    assert scenario.custo_carregamento_df(credit_ratio) == pytest.approx(expected, abs=1e-7)


def test_custo_carregamento_df_zero_ratio():
    scenario = TaxSimulationScenario(
        regime_version=TaxRegimeVersion.PLENO_CBS_IBS,
        cbs_ibs_combined_rate=0.265,
        credit_lag_semanas=4,
        taxa_financ_anual=0.12,
    )
    assert scenario.custo_carregamento_df(0.0) == 0.0


def test_to_dict_contains_all_fields():
    scenario = TaxSimulationScenario(
        regime_version=TaxRegimeVersion.TRANSICAO,
        cbs_ibs_combined_rate=0.013,
        credit_ratio_mao_obra=0.0,
        credit_ratio_material=0.75,
        credit_ratio_servicos=0.60,
        credit_ratio_diesel=0.65,
        credit_lag_semanas=6,
        taxa_financ_anual=0.12,
        split_payment=False,
        cssl_rate=BDI_CSSL,
        ir_rate=BDI_IR,
    )
    d = scenario.to_dict()
    assert d["regime_version"] == "transicao"
    assert d["cbs_ibs_combined_rate"] == 0.013
    assert d["credit_ratio_material"] == 0.75
    assert d["credit_lag_semanas"] == 6
    assert d["split_payment"] is False
    assert "cssl_rate" in d
    assert "ir_rate" in d


def test_from_dict_roundtrip():
    scenario = TaxSimulationScenario(
        regime_version=TaxRegimeVersion.PLENO_CBS_IBS,
        cbs_ibs_combined_rate=0.265,
        credit_ratio_mao_obra=0.0,
        credit_ratio_material=0.80,
        credit_ratio_servicos=0.70,
        credit_ratio_diesel=0.72,
        credit_lag_semanas=4,
        taxa_financ_anual=0.12,
        split_payment=True,
        cssl_rate=BDI_CSSL,
        ir_rate=BDI_IR,
    )
    d = scenario.to_dict()
    scenario2 = TaxSimulationScenario.from_dict(d)
    assert scenario2.regime_version == scenario.regime_version
    assert scenario2.cbs_ibs_combined_rate == scenario.cbs_ibs_combined_rate
    assert scenario2.credit_ratio_material == scenario.credit_ratio_material
    assert scenario2.credit_lag_semanas == scenario.credit_lag_semanas
    assert scenario2.split_payment == scenario.split_payment


def test_from_dict_defaults():
    scenario = TaxSimulationScenario.from_dict({})
    assert scenario.regime_version == TaxRegimeVersion.PRE_REFORMA
    assert scenario.cbs_ibs_combined_rate == 0.0
    assert scenario.taxa_financ_anual == 0.12
    assert scenario.split_payment is False


def test_from_dict_pre_reforma():
    d = {"regime_version": "pre_reforma"}
    scenario = TaxSimulationScenario.from_dict(d)
    assert scenario.regime_version == TaxRegimeVersion.PRE_REFORMA


def test_cenarios_tributarios_keys():
    assert TaxRegimeVersion.PRE_REFORMA in CENARIOS_TRIBUTARIOS
    assert TaxRegimeVersion.TRANSICAO in CENARIOS_TRIBUTARIOS
    assert TaxRegimeVersion.PLENO_CBS_IBS in CENARIOS_TRIBUTARIOS


# ── ComponentesBdi ────────────────────────────────────────────────────────


def test_tributos_sum():
    comp = _make_comp(cofins=0.03, iss=0.05, pis=0.0065, cssl=0.0199, ir=0.0274)
    expected = round(0.03 + 0.05 + 0.0065 + 0.0199 + 0.0274, 6)
    assert comp.tributos == pytest.approx(expected, abs=1e-7)


def test_overhead_sum():
    comp = _make_comp(ac=0.05, df=0.015, r=0.01, cr=0.0, l=0.09)
    expected = round(0.05 + 0.015 + 0.01 + 0.0 + 0.09, 6)
    assert comp.overhead == pytest.approx(expected, abs=1e-7)


def test_bdi_total_multiplicative_formula():
    """bdi_total = (1+AC)*(1+DF)*(1+R)*(1+CR)*(1+L) / (1-T) - 1."""
    comp = _make_comp(
        ac=0.05, df=0.015, r=0.01, cr=0.0, l=0.09, cofins=0.0, iss=BDI_ISS, pis=0.0, cssl=BDI_CSSL, ir=BDI_IR
    )
    t = comp.tributos
    expected = round(
        (1 + 0.05) * (1 + 0.015) * (1 + 0.01) * (1 + 0.0) * (1 + 0.09) / (1 - t) - 1,
        6,
    )
    assert comp.bdi_total == pytest.approx(expected, abs=1e-7)


def test_bdi_total_raises_when_tributos_gte_1():
    comp = _make_comp(cofins=0.5, iss=0.5, pis=0.0, cssl=0.0, ir=0.0)
    with pytest.raises(ValueError, match="Tributos totais"):
        _ = comp.bdi_total


def test_bdi_total_zero_taxes_equals_overhead_product():
    comp = _make_comp(ac=0.05, df=0.015, r=0.01, cr=0.0, l=0.09, cofins=0.0, iss=0.0, pis=0.0, cssl=0.0, ir=0.0)
    expected = round((1.05) * (1.015) * (1.01) * (1.0) * (1.09) - 1, 6)
    assert comp.bdi_total == pytest.approx(expected, abs=1e-7)


def test_bdi_total_all_zero():
    comp = _make_comp(ac=0.0, df=0.0, r=0.0, cr=0.0, l=0.0, cofins=0.0, iss=0.0, pis=0.0, cssl=0.0, ir=0.0)
    assert comp.bdi_total == pytest.approx(0.0, abs=1e-7)


def test_decomposicao_sums_to_one():
    comp = _make_comp()
    d = comp.decomposicao_no_preco()
    total = sum(d.values())
    assert total == pytest.approx(1.0, abs=1e-5)


def test_decomposicao_keys():
    comp = _make_comp()
    d = comp.decomposicao_no_preco()
    expected_keys = {
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
    assert set(d.keys()) == expected_keys


def test_decomposicao_tributos_are_direct_fractions():
    comp = _make_comp(cofins=0.03, iss=0.05, pis=0.0065, cssl=0.0199, ir=0.0274)
    d = comp.decomposicao_no_preco()
    assert d["tributo_cofins"] == pytest.approx(0.03, abs=1e-7)
    assert d["tributo_iss"] == pytest.approx(0.05, abs=1e-7)
    assert d["tributo_pis"] == pytest.approx(0.0065, abs=1e-7)


def test_decomposicao_zero_overhead():
    comp = _make_comp(ac=0.0, df=0.0, r=0.0, cr=0.0, l=0.0)
    d = comp.decomposicao_no_preco()
    total = sum(d.values())
    assert total == pytest.approx(1.0, abs=1e-5)


# ── TabelaBdi.para_categoria ─────────────────────────────────────────────


def test_para_categoria_mao_obra():
    tabela = _make_tabela_bdi()
    assert tabela.para_categoria("MAO_OBRA") is tabela.mao_obra


def test_para_categoria_material():
    tabela = _make_tabela_bdi()
    assert tabela.para_categoria("MATERIAL") is tabela.material


def test_para_categoria_servicos():
    tabela = _make_tabela_bdi()
    assert tabela.para_categoria("SERVICOS") is tabela.servicos


def test_para_categoria_indireto():
    tabela = _make_tabela_bdi()
    assert tabela.para_categoria("INDIRETO") is tabela.indireto


def test_para_categoria_diesel_delegates_to_material():
    """ADR-090: DIESEL delegates to material ComponentesBdi."""
    tabela = _make_tabela_bdi()
    assert tabela.para_categoria("DIESEL") is tabela.material


def test_para_categoria_combustivel_delegates_to_material():
    """ADR-107: COMBUSTIVEL is canonical alias, also delegates to material."""
    tabela = _make_tabela_bdi()
    assert tabela.para_categoria("COMBUSTIVEL") is tabela.material


# ── EncargosRegime.total ──────────────────────────────────────────────────


def test_encargos_total_sum():
    enc = EncargosRegime(a=0.378, b=0.4784, c=0.4053, d=0.1907, e=0.1022, f=0.1924, judicial=0.03)
    expected = round(0.378 + 0.4784 + 0.4053 + 0.1907 + 0.1022 + 0.1924 + 0.03, 6)
    assert enc.total == pytest.approx(expected, abs=1e-6)


def test_encargos_total_zero():
    enc = EncargosRegime(a=0.0, b=0.0, c=0.0, d=0.0, e=0.0, f=0.0, judicial=0.0)
    assert enc.total == 0.0


def test_encargos_partial_fields():
    enc = EncargosRegime(a=0.1, b=0.2, c=0.0, d=0.0, e=0.0, f=0.0, judicial=0.0)
    assert enc.total == pytest.approx(0.3, abs=1e-7)


# ── IndiretoComBdi model_validator ────────────────────────────────────────


def test_indireto_com_bdi_valid():
    bdi = 0.25
    custo = 1000.0
    custo_com_bdi = round(custo * (1 + bdi), 2)
    obj = IndiretoComBdi(
        categoria="ADM",
        custo_sem_bdi=custo,
        bdi_aplicado=bdi,
        custo_com_bdi=custo_com_bdi,
    )
    assert obj.custo_com_bdi == custo_com_bdi


def test_indireto_com_bdi_top_category():
    obj = IndiretoComBdi(
        categoria="TOP",
        custo_sem_bdi=500.0,
        bdi_aplicado=0.10,
        custo_com_bdi=550.0,
    )
    assert obj.categoria == "TOP"


def test_indireto_com_bdi_raises_on_mismatch():
    with pytest.raises(ValidationError, match="custo_com_bdi"):
        IndiretoComBdi(
            categoria="LAB",
            custo_sem_bdi=1000.0,
            bdi_aplicado=0.10,
            custo_com_bdi=2000.0,  # should be 1100.0
        )


def test_indireto_com_bdi_tolerance_boundary():
    # Tolerance is 0.02 — accept value within tolerance
    obj = IndiretoComBdi(
        categoria="QSMS",
        custo_sem_bdi=1000.0,
        bdi_aplicado=0.10,
        custo_com_bdi=1100.01,  # expected=1100.00, diff=0.01 <= 0.02
    )
    assert obj is not None


def test_indireto_com_bdi_all_categories():
    for cat in ("TOP", "ADM", "LAB", "QSMS", "MOB"):
        obj = IndiretoComBdi(
            categoria=cat,
            custo_sem_bdi=100.0,
            bdi_aplicado=0.0,
            custo_com_bdi=100.0,
        )
        assert obj.categoria == cat


# ── DecomposicaoEquipamento ───────────────────────────────────────────────


def _make_decomp(**kwargs) -> DecomposicaoEquipamento:
    defaults = dict(
        equip_id="EQ-001",
        custo_hora_total=100.0,
        custo_mao_obra_h=40.0,
        custo_diesel_h=30.0,
        custo_material_h=10.0,
        custo_capital_h=20.0,
    )
    defaults.update(kwargs)
    return DecomposicaoEquipamento(**defaults)


def test_decomposicao_equip_valid():
    d = _make_decomp()
    assert d.equip_id == "EQ-001"


def test_decomposicao_equip_raises_on_mismatch():
    with pytest.raises(ValidationError, match="Soma dos componentes"):
        DecomposicaoEquipamento(
            equip_id="EQ-002",
            custo_hora_total=100.0,
            custo_mao_obra_h=10.0,
            custo_diesel_h=10.0,
            custo_material_h=10.0,
            custo_capital_h=10.0,  # total=40, but custo_hora_total=100
        )


def test_fracao_mao_obra():
    d = _make_decomp(
        custo_mao_obra_h=40.0, custo_capital_h=20.0, custo_hora_total=100.0, custo_diesel_h=30.0, custo_material_h=10.0
    )
    # (40+20)/100 = 0.60
    assert d.fracao_mao_obra == pytest.approx(0.60, abs=1e-7)


def test_fracao_diesel():
    d = _make_decomp()
    # 30/100 = 0.30
    assert d.fracao_diesel == pytest.approx(0.30, abs=1e-7)


def test_fracao_material():
    d = _make_decomp()
    # 10/100 = 0.10
    assert d.fracao_material == pytest.approx(0.10, abs=1e-7)


def test_fracoes_sum_to_one():
    d = _make_decomp()
    total = d.fracao_mao_obra + d.fracao_diesel + d.fracao_material
    assert total == pytest.approx(1.0, abs=1e-6)


def test_fracao_zero_diesel():
    d = _make_decomp(
        custo_diesel_h=0.0, custo_material_h=10.0, custo_mao_obra_h=70.0, custo_capital_h=20.0, custo_hora_total=100.0
    )
    assert d.fracao_diesel == 0.0


def test_decomposicao_equip_near_tolerance():
    # Within 0.01 tolerance
    d = DecomposicaoEquipamento(
        equip_id="EQ-003",
        custo_hora_total=100.0,
        custo_mao_obra_h=40.0,
        custo_diesel_h=30.005,  # total=100.005 — within 0.01
        custo_material_h=10.0,
        custo_capital_h=20.0,
    )
    assert d is not None


# ── resolver_componentes_bdi ──────────────────────────────────────────────


def test_resolver_componentes_bdi_applies_lucro():
    base = _make_tabela_bdi()
    perfil = _make_perfil()
    result = resolver_componentes_bdi(base, perfil)
    assert result.mao_obra.l == pytest.approx(0.09, abs=1e-7)
    assert result.material.l == pytest.approx(0.04, abs=1e-7)


def test_resolver_componentes_bdi_zeros_disabled_tributos():
    base = _make_tabela_bdi()
    perfil = _make_perfil()
    # material has all taxes disabled
    result = resolver_componentes_bdi(base, perfil)
    assert result.material.cofins == 0.0
    assert result.material.iss == 0.0
    assert result.material.pis == 0.0
    assert result.material.cssl == 0.0
    assert result.material.ir == 0.0


def test_resolver_componentes_bdi_preserves_ac():
    base = _make_tabela_bdi()
    perfil = _make_perfil()
    result = resolver_componentes_bdi(base, perfil)
    assert result.mao_obra.ac == base.mao_obra.ac
    assert result.indireto.ac == base.indireto.ac


def test_resolver_componentes_bdi_enables_tributos():
    base = _make_tabela_bdi()
    perfil = _make_perfil()
    result = resolver_componentes_bdi(base, perfil)
    # mao_obra has iss, cssl, ir enabled
    assert result.mao_obra.iss == pytest.approx(BDI_ISS, abs=1e-7)
    assert result.mao_obra.cssl == pytest.approx(BDI_CSSL, abs=1e-7)
    assert result.mao_obra.ir == pytest.approx(BDI_IR, abs=1e-7)


def test_resolver_componentes_bdi_preserves_date():
    base = _make_tabela_bdi(vigencia=date(2025, 1, 1))
    perfil = _make_perfil()
    result = resolver_componentes_bdi(base, perfil)
    assert result.data_vigencia == date(2025, 1, 1)


def test_resolver_componentes_bdi_all_categories_present():
    base = _make_tabela_bdi()
    perfil = _make_perfil()
    result = resolver_componentes_bdi(base, perfil)
    for cat in ("mao_obra", "material", "servicos", "indireto", "diesel"):
        assert hasattr(result, cat)


def test_resolver_componentes_bdi_disabled_cofins():
    """cofins=False should zero it out."""
    base = _make_tabela_bdi()
    # Make mao_obra have cofins disabled
    trib = PerfilTributarioProjeto(
        regime="lucro_presumido",
        municipio="Fortaleza",
        iss_aliquota_municipal=0.05,
        mao_obra=AplicacaoTributaria(
            iss=_checkbox(True, BDI_ISS),
            cofins=_checkbox(False, BDI_COFINS),  # disabled
            pis=_checkbox(False, BDI_PIS),
            cssl=_checkbox(True, BDI_CSSL),
            ir=_checkbox(True, BDI_IR),
        ),
        material=_aplic_all_disabled(),
        servicos=_aplic(),
        indireto=_aplic(),
        diesel=_aplic_all_disabled(),
    )
    lucro = PerfilLucroProjeto(mao_obra=0.09, material=0.04, servicos=0.09, indireto=0.05, diesel=0.04)
    perfil = PerfilBdiProjeto(
        projeto_id="proj-x",
        content_hash="hash-x",
        confirmado_em=datetime(2026, 1, 1, tzinfo=UTC),
        confirmado_por="user",
        tributario=trib,
        lucro=lucro,
    )
    result = resolver_componentes_bdi(base, perfil)
    assert result.mao_obra.cofins == 0.0
    assert result.mao_obra.iss == pytest.approx(BDI_ISS, abs=1e-7)


# ── resolver_bdi_cbs_ibs ─────────────────────────────────────────────────


def test_resolver_bdi_cbs_ibs_pre_reforma_noop():
    base = _make_tabela_bdi()
    scenario = CENARIOS_TRIBUTARIOS[TaxRegimeVersion.PRE_REFORMA]
    result = resolver_bdi_cbs_ibs(base, scenario)
    assert result is base


def test_resolver_bdi_cbs_ibs_pleno_zeros_iss_pis():
    base = _make_tabela_bdi()
    scenario = CENARIOS_TRIBUTARIOS[TaxRegimeVersion.PLENO_CBS_IBS]
    result = resolver_bdi_cbs_ibs(base, scenario)
    for cat in ("mao_obra", "material", "servicos", "indireto", "diesel"):
        comp = getattr(result, cat)
        assert comp.iss == 0.0
        assert comp.pis == 0.0


def test_resolver_bdi_cbs_ibs_pleno_cssl_ir_from_scenario():
    base = _make_tabela_bdi()
    scenario = CENARIOS_TRIBUTARIOS[TaxRegimeVersion.PLENO_CBS_IBS]
    result = resolver_bdi_cbs_ibs(base, scenario)
    for cat in ("mao_obra", "material", "servicos", "indireto", "diesel"):
        comp = getattr(result, cat)
        assert comp.cssl == pytest.approx(scenario.cssl_rate, abs=1e-7)
        assert comp.ir == pytest.approx(scenario.ir_rate, abs=1e-7)


def test_resolver_bdi_cbs_ibs_pleno_mao_obra_cofins_liquid():
    base = _make_tabela_bdi()
    scenario = CENARIOS_TRIBUTARIOS[TaxRegimeVersion.PLENO_CBS_IBS]
    result = resolver_bdi_cbs_ibs(base, scenario)
    # mao_obra credit_ratio=0.0 → cofins = cbs_ibs * 1.0
    expected_mao = round(scenario.cbs_ibs_combined_rate * (1 - scenario.credit_ratio_mao_obra), 6)
    assert result.mao_obra.cofins == pytest.approx(expected_mao, abs=1e-7)


def test_resolver_bdi_cbs_ibs_pleno_material_cofins_reduced():
    base = _make_tabela_bdi()
    scenario = CENARIOS_TRIBUTARIOS[TaxRegimeVersion.PLENO_CBS_IBS]
    result = resolver_bdi_cbs_ibs(base, scenario)
    # material credit_ratio=0.80 → cofins = cbs_ibs * 0.20
    expected_mat = round(scenario.cbs_ibs_combined_rate * (1 - scenario.credit_ratio_material), 6)
    assert result.material.cofins == pytest.approx(expected_mat, abs=1e-7)


def test_resolver_bdi_cbs_ibs_transicao_not_noop():
    base = _make_tabela_bdi()
    scenario = CENARIOS_TRIBUTARIOS[TaxRegimeVersion.TRANSICAO]
    result = resolver_bdi_cbs_ibs(base, scenario)
    assert result is not base
    for cat in ("mao_obra", "material", "servicos", "indireto", "diesel"):
        comp = getattr(result, cat)
        assert comp.iss == 0.0
        assert comp.pis == 0.0


def test_resolver_bdi_cbs_ibs_preserves_overhead_components():
    base = _make_tabela_bdi()
    scenario = CENARIOS_TRIBUTARIOS[TaxRegimeVersion.PLENO_CBS_IBS]
    result = resolver_bdi_cbs_ibs(base, scenario)
    assert result.mao_obra.ac == base.mao_obra.ac
    assert result.mao_obra.r == base.mao_obra.r
    assert result.mao_obra.cr == base.mao_obra.cr
    assert result.mao_obra.l == base.mao_obra.l


def test_resolver_bdi_cbs_ibs_preserves_date():
    base = _make_tabela_bdi(vigencia=date(2033, 1, 1))
    scenario = CENARIOS_TRIBUTARIOS[TaxRegimeVersion.PLENO_CBS_IBS]
    result = resolver_bdi_cbs_ibs(base, scenario)
    assert result.data_vigencia == date(2033, 1, 1)


def test_resolver_bdi_cbs_ibs_df_carregamento_added():
    base = _make_tabela_bdi()
    scenario = TaxSimulationScenario(
        regime_version=TaxRegimeVersion.PLENO_CBS_IBS,
        cbs_ibs_combined_rate=0.265,
        credit_ratio_mao_obra=0.0,
        credit_ratio_material=0.80,
        credit_ratio_servicos=0.70,
        credit_ratio_diesel=0.72,
        credit_lag_semanas=4,
        taxa_financ_anual=0.12,
    )
    result = resolver_bdi_cbs_ibs(base, scenario)
    # material has credit → df should increase
    df_base = base.material.df
    df_carregamento = scenario.custo_carregamento_df(scenario.credit_ratio_material)
    expected_df = min(0.99, round(df_base + df_carregamento, 6))
    assert result.material.df == pytest.approx(expected_df, abs=1e-7)


def test_resolver_bdi_cbs_ibs_indireto_uses_servicos_ratio():
    """indireto credit_ratio should be the same as servicos."""
    base = _make_tabela_bdi()
    scenario = TaxSimulationScenario(
        regime_version=TaxRegimeVersion.PLENO_CBS_IBS,
        cbs_ibs_combined_rate=0.265,
        credit_ratio_servicos=0.70,
        credit_lag_semanas=0,
        taxa_financ_anual=0.12,
    )
    result = resolver_bdi_cbs_ibs(base, scenario)
    expected_cofins = round(0.265 * (1 - 0.70), 6)
    assert result.indireto.cofins == pytest.approx(expected_cofins, abs=1e-7)
    assert result.indireto.cofins == result.servicos.cofins


# ── resolve_bdi_tabela ────────────────────────────────────────────────────


def test_resolve_bdi_tabela_none_returns_default():
    result = resolve_bdi_tabela(None)
    assert result is DEFAULT_BDI_TABELA


def test_resolve_bdi_tabela_dict_parses():
    tabela = _make_tabela_bdi()
    d = tabela.model_dump()
    result = resolve_bdi_tabela(d)
    assert isinstance(result, TabelaBdi)
    assert result.data_vigencia == tabela.data_vigencia


def test_resolve_bdi_tabela_instance_passthrough():
    tabela = _make_tabela_bdi()
    result = resolve_bdi_tabela(tabela)
    assert result is tabela


# ── DEFAULT_BDI_TABELA smoke test ─────────────────────────────────────────


def test_default_bdi_tabela_exists():
    assert DEFAULT_BDI_TABELA is not None


def test_default_bdi_mao_obra_bdi_positive():
    comp = DEFAULT_BDI_TABELA.mao_obra
    # BDI > 0 for mao_obra with overhead components
    assert comp.bdi_total > 0.0


def test_default_bdi_material_bdi_approx_4_pct():
    comp = DEFAULT_BDI_TABELA.material
    # Only l=0.04, no taxes → BDI = (1+0.04) - 1 = 0.04
    assert comp.bdi_total == pytest.approx(0.04, abs=1e-7)


def test_default_bdi_diesel_equals_material_bdi():
    # ADR-090: diesel = material (same 4%)
    assert DEFAULT_BDI_TABELA.diesel.bdi_total == pytest.approx(DEFAULT_BDI_TABELA.material.bdi_total, abs=1e-7)


# ── BdiPerfilDiff ─────────────────────────────────────────────────────────


def test_bdi_perfil_diff_construction():
    diff = BdiPerfilDiff(
        projeto_id="proj-001",
        versao_anterior=1,
        versao_nova=2,
        perfil_anterior_id="old-id",
        perfil_novo_id="new-id",
        motivo="Atualização de ISS municipal",
        campos_alterados=["tributario.mao_obra.iss.aliquota"],
        resumo="ISS alterado de 5% para 3%",
    )
    assert diff.projeto_id == "proj-001"
    assert diff.versao_anterior == 1
    assert diff.versao_nova == 2
    assert diff.motivo == "Atualização de ISS municipal"
    assert "tributario.mao_obra.iss.aliquota" in diff.campos_alterados


def test_bdi_perfil_diff_auto_diff_id():
    diff1 = BdiPerfilDiff(
        projeto_id="proj-002",
        versao_anterior=2,
        versao_nova=3,
        perfil_anterior_id="id-a",
        perfil_novo_id="id-b",
        motivo="Novo regime tributário",
        campos_alterados=["regime_version"],
        resumo="Mudança para Simples Nacional",
    )
    diff2 = BdiPerfilDiff(
        projeto_id="proj-002",
        versao_anterior=2,
        versao_nova=3,
        perfil_anterior_id="id-a",
        perfil_novo_id="id-b",
        motivo="Novo regime tributário",
        campos_alterados=["regime_version"],
        resumo="Mudança para Simples Nacional",
    )
    # Each instance gets a unique auto-generated diff_id
    assert diff1.diff_id != diff2.diff_id


def test_bdi_perfil_diff_gerado_em_is_datetime():
    diff = BdiPerfilDiff(
        projeto_id="proj-003",
        versao_anterior=1,
        versao_nova=2,
        perfil_anterior_id="old",
        perfil_novo_id="new",
        motivo="Teste",
        campos_alterados=[],
        resumo="Nenhuma alteração relevante",
    )
    assert isinstance(diff.gerado_em, datetime)


def test_bdi_perfil_diff_multiple_campos_alterados():
    campos = [
        "tributario.mao_obra.iss.aliquota",
        "tributario.servicos.cofins.aliquota",
        "lucro.material",
    ]
    diff = BdiPerfilDiff(
        projeto_id="proj-004",
        versao_anterior=3,
        versao_nova=4,
        perfil_anterior_id="v3-id",
        perfil_novo_id="v4-id",
        motivo="Revisão anual",
        campos_alterados=campos,
        resumo="3 campos alterados na revisão de abril/2026",
    )
    assert len(diff.campos_alterados) == 3
    assert diff.campos_alterados == campos


# ── TabelaEncargos / DEFAULT_ENCARGOS ────────────────────────────────────


def test_default_encargos_exists():
    from concilium.domain.models.financial.bdi import DEFAULT_ENCARGOS

    assert DEFAULT_ENCARGOS is not None


def test_default_encargos_horistas_total():
    from concilium.domain.models.financial.bdi import DEFAULT_ENCARGOS

    enc = DEFAULT_ENCARGOS.horistas
    expected = round(0.3780 + 0.4784 + 0.4053 + 0.1907 + 0.1022 + 0.1924 + 0.0300, 6)
    assert enc.total == pytest.approx(expected, abs=1e-6)


def test_default_encargos_mensalistas_total():
    from concilium.domain.models.financial.bdi import DEFAULT_ENCARGOS

    enc = DEFAULT_ENCARGOS.mensalistas
    expected = round(0.3780 + 0.0994 + 0.4030 + 0.0474 + 0.1022 + 0.0000 + 0.0300, 6)
    assert enc.total == pytest.approx(expected, abs=1e-6)


def test_default_encargos_horistas_greater_than_mensalistas():
    from concilium.domain.models.financial.bdi import DEFAULT_ENCARGOS

    assert DEFAULT_ENCARGOS.horistas.total > DEFAULT_ENCARGOS.mensalistas.total


def test_default_encargos_data_vigencia():
    from concilium.domain.models.financial.bdi import DEFAULT_ENCARGOS

    assert DEFAULT_ENCARGOS.data_vigencia == date(2026, 4, 1)


def test_tabela_encargos_construction():

    enc_h = EncargosRegime(a=0.20, b=0.10, c=0.05, d=0.02, e=0.03, f=0.04, judicial=0.01)
    enc_m = EncargosRegime(a=0.20, b=0.05, c=0.05, d=0.01, e=0.03, f=0.00, judicial=0.01)
    tabela = TabelaEncargos(
        horistas=enc_h,
        mensalistas=enc_m,
        data_vigencia=date(2025, 1, 1),
    )
    assert tabela.horistas.total == pytest.approx(enc_h.total, abs=1e-7)
    assert tabela.mensalistas.total == pytest.approx(enc_m.total, abs=1e-7)
    assert tabela.data_vigencia == date(2025, 1, 1)


# ── PerfilBdiProjeto versioning / regime_version ──────────────────────────


def test_perfil_bdi_projeto_default_regime():
    perfil = _make_perfil()
    assert perfil.regime_version == TaxRegimeVersion.PRE_REFORMA


def test_perfil_bdi_projeto_transicao_regime():
    perfil = _make_perfil(regime_version=TaxRegimeVersion.TRANSICAO)
    assert perfil.regime_version == TaxRegimeVersion.TRANSICAO


def test_perfil_bdi_projeto_pleno_regime():
    perfil = _make_perfil(regime_version=TaxRegimeVersion.PLENO_CBS_IBS)
    assert perfil.regime_version == TaxRegimeVersion.PLENO_CBS_IBS


def test_perfil_bdi_projeto_auto_perfil_id():
    p1 = _make_perfil()
    p2 = _make_perfil()
    assert p1.perfil_id != p2.perfil_id


def test_perfil_bdi_projeto_default_versao():
    perfil = _make_perfil()
    assert perfil.versao == 1


def test_perfil_bdi_projeto_all_lucro_categories():
    perfil = _make_perfil()
    assert perfil.lucro.mao_obra == pytest.approx(0.09, abs=1e-7)
    assert perfil.lucro.material == pytest.approx(0.04, abs=1e-7)
    assert perfil.lucro.servicos == pytest.approx(0.09, abs=1e-7)
    assert perfil.lucro.indireto == pytest.approx(0.05, abs=1e-7)
    assert perfil.lucro.diesel == pytest.approx(0.04, abs=1e-7)


# ── ComponentesBdi field validation ──────────────────────────────────────


def test_componentes_bdi_rejects_ac_gt_1():
    with pytest.raises(Exception):  # noqa: B017
        ComponentesBdi(
            ac=1.5,
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


def test_componentes_bdi_rejects_negative_field():
    with pytest.raises(Exception):  # noqa: B017
        ComponentesBdi(
            ac=-0.01,
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


def test_componentes_bdi_max_allowed_values():
    # All fields at their max allowed value (1.0 each for overhead, but tributos must not sum >= 1)
    # Only one tax at 0.99, rest zero
    comp = ComponentesBdi(
        ac=1.0,
        df=0.0,
        r=0.0,
        cr=0.0,
        l=0.0,
        cofins=0.99,
        iss=0.0,
        pis=0.0,
        cssl=0.0,
        ir=0.0,
    )
    bdi = comp.bdi_total
    expected = round((1 + 1.0) / (1 - 0.99) - 1, 6)
    assert bdi == pytest.approx(expected, abs=1e-5)


def test_bdi_total_with_all_overhead_components():
    # All overhead components set to verify multiplicative product
    comp = ComponentesBdi(
        ac=0.05,
        df=0.02,
        r=0.01,
        cr=0.005,
        l=0.10,
        cofins=0.0,
        iss=0.0,
        pis=0.0,
        cssl=0.0,
        ir=0.0,
    )
    expected = round((1.05) * (1.02) * (1.01) * (1.005) * (1.10) - 1, 6)
    assert comp.bdi_total == pytest.approx(expected, abs=1e-6)


def test_decomposicao_with_nonzero_cr():
    comp = ComponentesBdi(
        ac=0.05,
        df=0.015,
        r=0.01,
        cr=0.02,
        l=0.09,
        cofins=0.03,
        iss=0.05,
        pis=0.0065,
        cssl=0.0199,
        ir=0.0274,
    )
    d = comp.decomposicao_no_preco()
    total = sum(d.values())
    assert total == pytest.approx(1.0, abs=1e-5)
    assert d["overhead_cr"] > 0


# ── CENARIOS_TRIBUTARIOS smoke tests ────────────────────────────────────


def test_cenarios_tributarios_pre_reforma_noop_rates():
    scenario = CENARIOS_TRIBUTARIOS[TaxRegimeVersion.PRE_REFORMA]
    assert scenario.cbs_ibs_combined_rate == 0.0
    assert scenario.credit_lag_semanas == 0


def test_cenarios_tributarios_transicao_rates():
    scenario = CENARIOS_TRIBUTARIOS[TaxRegimeVersion.TRANSICAO]
    assert scenario.cbs_ibs_combined_rate == pytest.approx(0.013, abs=1e-7)
    assert scenario.credit_ratio_material == pytest.approx(0.75, abs=1e-7)
    assert scenario.credit_ratio_servicos == pytest.approx(0.60, abs=1e-7)
    assert scenario.credit_ratio_diesel == pytest.approx(0.65, abs=1e-7)
    assert scenario.credit_lag_semanas == 6
    assert scenario.split_payment is False


def test_cenarios_tributarios_pleno_rates():
    scenario = CENARIOS_TRIBUTARIOS[TaxRegimeVersion.PLENO_CBS_IBS]
    assert scenario.cbs_ibs_combined_rate == pytest.approx(0.265, abs=1e-7)
    assert scenario.credit_ratio_mao_obra == 0.0
    assert scenario.credit_ratio_material == pytest.approx(0.80, abs=1e-7)
    assert scenario.split_payment is True


# ── DEFAULT_BDI_TABELA additional smoke tests ─────────────────────────────


def test_default_bdi_tabela_data_vigencia():
    # Calibrated at 2026-03-01 from AGIS spreadsheet
    assert DEFAULT_BDI_TABELA.data_vigencia == date(2026, 3, 1)


def test_default_bdi_mao_obra_tributos():
    comp = DEFAULT_BDI_TABELA.mao_obra
    # ISS, CSSL, IR set; COFINS/PIS isentos
    assert comp.cofins == 0.0
    assert comp.pis == 0.0
    assert comp.iss == pytest.approx(BDI_ISS, abs=1e-7)
    assert comp.cssl == pytest.approx(BDI_CSSL, abs=1e-7)
    assert comp.ir == pytest.approx(BDI_IR, abs=1e-7)


def test_default_bdi_material_zero_taxes():
    comp = DEFAULT_BDI_TABELA.material
    assert comp.cofins == 0.0
    assert comp.iss == 0.0
    assert comp.pis == 0.0
    assert comp.cssl == 0.0
    assert comp.ir == 0.0


def test_default_bdi_indireto_bdi_positive():
    comp = DEFAULT_BDI_TABELA.indireto
    assert comp.bdi_total > 0.0


def test_default_bdi_servicos_matches_mao_obra_bdi():
    # Both use the same overhead+taxes profile
    assert DEFAULT_BDI_TABELA.servicos.bdi_total == pytest.approx(DEFAULT_BDI_TABELA.mao_obra.bdi_total, abs=1e-7)


# ── TabelaBdi.para_categoria with DEFAULT_BDI_TABELA ────────────────────


def test_para_categoria_diesel_on_default_is_material():
    # ADR-090: DIESEL always delegates to material (same 4%)
    assert DEFAULT_BDI_TABELA.para_categoria("DIESEL") is DEFAULT_BDI_TABELA.material


def test_para_categoria_combustivel_on_default_is_material():
    # ADR-107: COMBUSTIVEL canonical alias
    assert DEFAULT_BDI_TABELA.para_categoria("COMBUSTIVEL") is DEFAULT_BDI_TABELA.material


# ── IndiretoComBdi edge cases ─────────────────────────────────────────────


def test_indireto_com_bdi_zero_bdi():
    obj = IndiretoComBdi(
        categoria="MOB",
        custo_sem_bdi=0.0,
        bdi_aplicado=0.0,
        custo_com_bdi=0.0,
    )
    assert obj.custo_com_bdi == 0.0


def test_indireto_com_bdi_large_values():
    custo = 1_000_000.0
    bdi = 0.25
    custo_com_bdi = round(custo * (1 + bdi), 2)
    obj = IndiretoComBdi(
        categoria="TOP",
        custo_sem_bdi=custo,
        bdi_aplicado=bdi,
        custo_com_bdi=custo_com_bdi,
    )
    assert obj.custo_com_bdi == pytest.approx(1_250_000.0, abs=0.02)


def test_indireto_com_bdi_just_over_tolerance_raises():
    with pytest.raises(ValidationError):
        IndiretoComBdi(
            categoria="ADM",
            custo_sem_bdi=1000.0,
            bdi_aplicado=0.10,
            custo_com_bdi=1100.03,  # expected=1100.00, diff=0.03 > 0.02
        )


# ── DecomposicaoEquipamento edge cases ────────────────────────────────────


def test_decomposicao_equip_single_component():
    # Only mao_obra, no diesel or material
    d = DecomposicaoEquipamento(
        equip_id="EQ-MO-ONLY",
        custo_hora_total=50.0,
        custo_mao_obra_h=30.0,
        custo_diesel_h=0.0,
        custo_material_h=0.0,
        custo_capital_h=20.0,
    )
    assert d.fracao_mao_obra == pytest.approx(1.0, abs=1e-7)
    assert d.fracao_diesel == 0.0
    assert d.fracao_material == 0.0


def test_decomposicao_equip_at_exact_tolerance_boundary():
    # Exactly 0.009 difference — strictly less than 0.01, so accepted
    d = DecomposicaoEquipamento(
        equip_id="EQ-BOUNDARY",
        custo_hora_total=100.0,
        custo_mao_obra_h=40.0,
        custo_diesel_h=30.009,  # total=100.009 — within tolerance (< 0.01)
        custo_material_h=10.0,
        custo_capital_h=20.0,
    )
    assert d is not None


def test_decomposicao_equip_just_over_tolerance_raises():
    with pytest.raises(ValidationError, match="Soma dos componentes"):
        DecomposicaoEquipamento(
            equip_id="EQ-OVER",
            custo_hora_total=100.0,
            custo_mao_obra_h=40.0,
            custo_diesel_h=30.011,  # total=100.011 — just over tolerance (> 0.01)
            custo_material_h=10.0,
            custo_capital_h=20.0,
        )


# ── resolver_componentes_bdi: pis enabled ────────────────────────────────


def test_resolver_componentes_bdi_pis_enabled():
    base = _make_tabela_bdi()
    trib = PerfilTributarioProjeto(
        regime="lucro_real",
        municipio="Recife",
        iss_aliquota_municipal=0.02,
        mao_obra=AplicacaoTributaria(
            iss=_checkbox(True, BDI_ISS),
            cofins=_checkbox(True, BDI_COFINS),
            pis=_checkbox(True, BDI_PIS),  # enabled
            cssl=_checkbox(True, BDI_CSSL),
            ir=_checkbox(True, BDI_IR),
        ),
        material=_aplic_all_disabled(),
        servicos=_aplic(),
        indireto=_aplic(),
        diesel=_aplic_all_disabled(),
    )
    lucro = PerfilLucroProjeto(mao_obra=0.09, material=0.04, servicos=0.09, indireto=0.05, diesel=0.04)
    perfil = PerfilBdiProjeto(
        projeto_id="proj-pis",
        content_hash="hash-pis",
        confirmado_em=datetime(2026, 1, 1, tzinfo=UTC),
        confirmado_por="user",
        tributario=trib,
        lucro=lucro,
    )
    result = resolver_componentes_bdi(base, perfil)
    assert result.mao_obra.pis == pytest.approx(BDI_PIS, abs=1e-7)


def test_resolver_componentes_bdi_simples_nacional_regime():
    base = _make_tabela_bdi()
    trib = PerfilTributarioProjeto(
        regime="simples_nacional",
        municipio="Natal",
        iss_aliquota_municipal=0.03,
        mao_obra=_aplic_all_disabled(),
        material=_aplic_all_disabled(),
        servicos=_aplic_all_disabled(),
        indireto=_aplic_all_disabled(),
        diesel=_aplic_all_disabled(),
    )
    lucro = PerfilLucroProjeto(mao_obra=0.06, material=0.02, servicos=0.06, indireto=0.03, diesel=0.02)
    perfil = PerfilBdiProjeto(
        projeto_id="proj-simples",
        content_hash="hash-simples",
        confirmado_em=datetime(2026, 3, 1, tzinfo=UTC),
        confirmado_por="user",
        tributario=trib,
        lucro=lucro,
        regime_version=TaxRegimeVersion.PRE_REFORMA,
    )
    result = resolver_componentes_bdi(base, perfil)
    # All taxes disabled → all zero
    for cat in ("mao_obra", "material", "servicos", "indireto", "diesel"):
        comp = getattr(result, cat)
        assert comp.cofins == 0.0
        assert comp.iss == 0.0
        assert comp.pis == 0.0
        assert comp.cssl == 0.0
        assert comp.ir == 0.0


# ── resolver_bdi_cbs_ibs: df capped at 0.99 ──────────────────────────────


def test_resolver_bdi_cbs_ibs_df_capped_at_099():
    base = _make_tabela_bdi()
    # Construct a scenario where df_carregamento would push df > 0.99
    scenario = TaxSimulationScenario(
        regime_version=TaxRegimeVersion.PLENO_CBS_IBS,
        cbs_ibs_combined_rate=0.99,
        credit_ratio_mao_obra=0.99,
        credit_ratio_material=0.99,
        credit_ratio_servicos=0.99,
        credit_ratio_diesel=0.99,
        credit_lag_semanas=52,  # 1 year lag
        taxa_financ_anual=1.0,  # 100% financing cost
        cssl_rate=0.0,
        ir_rate=0.0,
    )
    result = resolver_bdi_cbs_ibs(base, scenario)
    for cat in ("mao_obra", "material", "servicos", "indireto", "diesel"):
        assert getattr(result, cat).df <= 0.99
