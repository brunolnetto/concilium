"""Tests for ADR-057: Memorial de Cálculo BDI — auditabilidade ponta a ponta.

Covers:
- MemorialEncargos: grupo totals, vigencia
- MemorialBDICategoria: fonte_bdi, override flag, bdi_total
- MemorialDecomposicao: invariant soma==1.0 for all categories
- MemorialCalculoBDI.to_dict(): JSON-serializable
- MemorialBDIBuilder: deterministic given same inputs
- Override detection (DEFAULT_BDI_TABELA vs manual)
"""

from __future__ import annotations

import json
import math

import pytest

from concilium.domain.constants import (
    ENCARGOS_CLT,
    ENCARGOS_MENSALISTA,
)
from concilium.domain.models.financial.bdi import DEFAULT_BDI_TABELA
from concilium.domain.models.financial.memorial_bdi import (
    MemorialCalculoBDI,
)
from concilium.domain.services.financial.memorial_bdi_builder import MemorialBDIBuilder

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_minimal_canonical():
    """Create a minimal CanonicalModel for testing."""
    from concilium.application.skills import run_escopo_e_eap

    inputs = {
        "nome": "Test Memorial",
        "tipo_obra": "terraplenagem",
        "localizacao": "BR",
        "coordenadas": {"lat": 0.0, "lng": 0.0},
        "regime_trabalho": {"dias_semana": 6, "horas_dia": 8},
        "data_inicio": "2026-06-01",
        "data_termino": "2027-06-01",
        "eap": [
            {
                "item_id": "eap-01",
                "ordem": 1,
                "cpu_id": "CPU-01",
                "descricao": "Escavacao",
                "unidade": "m3",
                "quantitativo": 10000.0,
            },
        ],
        "contexto_id": "test",
        "snapshot_catalogo_id": "snap",
        "snapshot_perfil_id": "snap",
    }
    return run_escopo_e_eap(None, inputs).canonical


# ---------------------------------------------------------------------------
# MemorialEncargos
# ---------------------------------------------------------------------------


class TestMemorialEncargos:
    def test_horista_total_matches_constant(self):
        from concilium.domain.services.financial.memorial_bdi_builder import MemorialBDIBuilder

        enc = MemorialBDIBuilder._build_encargos("horista_clt")
        assert math.isclose(enc.total, ENCARGOS_CLT, abs_tol=1e-4)

    def test_mensalista_total_matches_constant(self):
        from concilium.domain.services.financial.memorial_bdi_builder import MemorialBDIBuilder

        enc = MemorialBDIBuilder._build_encargos("mensalista_clt")
        assert math.isclose(enc.total, ENCARGOS_MENSALISTA, abs_tol=1e-4)

    def test_grupo_sum_equals_total(self):
        from concilium.domain.services.financial.memorial_bdi_builder import MemorialBDIBuilder

        for regime in ("horista_clt", "mensalista_clt"):
            enc = MemorialBDIBuilder._build_encargos(regime)
            computed = round(
                enc.grupo_a + enc.grupo_b + enc.grupo_c + enc.grupo_d + enc.grupo_e + enc.grupo_f + enc.judicial, 4
            )
            assert math.isclose(computed, enc.total, abs_tol=1e-4), f"Regime {regime}: {computed} != {enc.total}"

    def test_mensalista_grupo_f_is_zero(self):
        from concilium.domain.services.financial.memorial_bdi_builder import MemorialBDIBuilder

        enc = MemorialBDIBuilder._build_encargos("mensalista_clt")
        assert enc.grupo_f == 0.0

    def test_horista_grupo_f_positive(self):
        from concilium.domain.services.financial.memorial_bdi_builder import MemorialBDIBuilder

        enc = MemorialBDIBuilder._build_encargos("horista_clt")
        assert enc.grupo_f > 0.0

    def test_vigencia_set(self):
        from concilium.domain.services.financial.memorial_bdi_builder import MemorialBDIBuilder

        enc = MemorialBDIBuilder._build_encargos("horista_clt")
        assert enc.vigencia == "2026-04-01"
        assert "constants.py" in enc.fonte or "rfi_catalog" in enc.fonte


# ---------------------------------------------------------------------------
# MemorialBDICategoria
# ---------------------------------------------------------------------------


class TestMemorialBDICategoria:
    def test_bdi_total_matches_componentesbdi(self):
        from concilium.domain.services.financial.memorial_bdi_builder import MemorialBDIBuilder

        for cat in ["mao_obra", "material", "servicos", "indireto", "diesel"]:
            comp = getattr(DEFAULT_BDI_TABELA, cat)
            mem = MemorialBDIBuilder._build_bdi_categoria(cat, comp, "DEFAULT_BDI_TABELA", "pre_reforma", False)
            assert math.isclose(mem.bdi_total, comp.bdi_total, rel_tol=1e-6)

    def test_overhead_total_correct(self):
        from concilium.domain.services.financial.memorial_bdi_builder import MemorialBDIBuilder

        comp = DEFAULT_BDI_TABELA.mao_obra
        mem = MemorialBDIBuilder._build_bdi_categoria("mao_obra", comp, "DEFAULT", "pre_reforma", False)
        expected_oh = comp.ac + comp.df + comp.r + comp.cr + comp.l
        assert math.isclose(mem.overhead_total, expected_oh, rel_tol=1e-6)

    def test_tributos_total_correct(self):
        """tributos_total deve refletir a configuração real do DEFAULT calibrado."""
        from concilium.domain.services.financial.memorial_bdi_builder import MemorialBDIBuilder

        comp = DEFAULT_BDI_TABELA.mao_obra
        mem = MemorialBDIBuilder._build_bdi_categoria("mao_obra", comp, "DEFAULT", "pre_reforma", False)
        # DEFAULT calibrado AGIS: COFINS=0%, PIS=0%; T = ISS + CSSL + IR = 9.73%
        expected_t = comp.cofins + comp.iss + comp.pis + comp.cssl + comp.ir
        assert math.isclose(mem.tributos_total, expected_t, abs_tol=1e-6)

    def test_material_has_zero_tributos(self):
        from concilium.domain.services.financial.memorial_bdi_builder import MemorialBDIBuilder

        comp = DEFAULT_BDI_TABELA.material
        mem = MemorialBDIBuilder._build_bdi_categoria("material", comp, "DEFAULT", "pre_reforma", False)
        assert mem.tributos_total == 0.0

    def test_override_flag_propagated(self):
        from concilium.domain.services.financial.memorial_bdi_builder import MemorialBDIBuilder

        comp = DEFAULT_BDI_TABELA.mao_obra
        mem = MemorialBDIBuilder._build_bdi_categoria("mao_obra", comp, "inputs.bdi_aplicado", "pre_reforma", True)
        assert mem.override_aplicado is True
        assert mem.fonte_bdi == "inputs.bdi_aplicado"

    def test_frozen_immutable(self):
        from concilium.domain.services.financial.memorial_bdi_builder import MemorialBDIBuilder

        comp = DEFAULT_BDI_TABELA.mao_obra
        mem = MemorialBDIBuilder._build_bdi_categoria("mao_obra", comp, "DEFAULT", "pre_reforma", False)
        with pytest.raises((AttributeError, TypeError)):
            mem.bdi_total = 0.99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# MemorialDecomposicao — invariant soma == 1.0
# ---------------------------------------------------------------------------


class TestMemorialDecomposicao:
    @pytest.mark.parametrize("cat", ["mao_obra", "material", "servicos", "indireto", "diesel"])
    def test_soma_equals_one(self, cat: str):
        """INVARIANT: All decomposicao components sum to 1.0 (100% of selling price)."""
        from concilium.domain.services.financial.memorial_bdi_builder import MemorialBDIBuilder

        comp = getattr(DEFAULT_BDI_TABELA, cat)
        mem = MemorialBDIBuilder._build_decomposicao(cat, comp)
        assert abs(mem.soma - 1.0) < 0.001, f"Category {cat}: soma={mem.soma}, expected 1.0"

    def test_custo_direto_mao_obra(self):
        """For mao_obra: custo_direto ≈ 77.49% (calibração AGIS — T=9.73% vs 13.38% antigo)."""
        from concilium.domain.services.financial.memorial_bdi_builder import MemorialBDIBuilder

        comp = DEFAULT_BDI_TABELA.mao_obra
        mem = MemorialBDIBuilder._build_decomposicao("mao_obra", comp)
        # C/PV = (1-T)/(1+OH) = (1-0.0973)/(1+0.165) = 0.9027/1.165 ≈ 0.7749
        assert math.isclose(mem.custo_direto_pct, 0.7749, abs_tol=0.002)

    def test_margem_mao_obra(self):
        """Margem L contribui ~6.97% do preço de venda para mao_obra (calibração AGIS)."""
        from concilium.domain.services.financial.memorial_bdi_builder import MemorialBDIBuilder

        comp = DEFAULT_BDI_TABELA.mao_obra
        mem = MemorialBDIBuilder._build_decomposicao("mao_obra", comp)
        # margem_l = L × C/PV = 0.09 × 0.7749 ≈ 0.0697
        assert math.isclose(mem.margem_l_pct, 0.0697, abs_tol=0.002)

    def test_tributos_por_categoria(self):
        """Tributos do DEFAULT calibrado AGIS: isenção COFINS/PIS; diesel/material sem tributos."""
        from concilium.domain.services.financial.memorial_bdi_builder import MemorialBDIBuilder

        # mao_obra, servicos, indireto: ISS=5% + CSSL=1.99% + IR=2.74% = 9.73%
        for cat in ["mao_obra", "servicos", "indireto"]:
            comp = getattr(DEFAULT_BDI_TABELA, cat)
            mem = MemorialBDIBuilder._build_decomposicao(cat, comp)
            t = mem.tributos_total_pct
            assert math.isclose(t, 0.0973, abs_tol=1e-3), f"{cat}: tributos={t:.4f} (esperado ≈ 0.0973)"

        # diesel e material: sem tributos sobre fornecimento de insumo
        for cat in ["diesel", "material"]:
            comp = getattr(DEFAULT_BDI_TABELA, cat)
            mem = MemorialBDIBuilder._build_decomposicao(cat, comp)
            assert mem.tributos_total_pct == 0.0, f"{cat}: tributos deveriam ser 0"

    def test_material_zero_tributos(self):
        """Material tem tributos zerados."""
        from concilium.domain.services.financial.memorial_bdi_builder import MemorialBDIBuilder

        comp = DEFAULT_BDI_TABELA.material
        mem = MemorialBDIBuilder._build_decomposicao("material", comp)
        assert mem.tributos_total_pct == 0.0

    def test_decomposicao_all_positive(self):
        """All decomposition values must be >= 0."""
        from concilium.domain.services.financial.memorial_bdi_builder import MemorialBDIBuilder

        for cat in ["mao_obra", "material", "servicos", "indireto", "diesel"]:
            comp = getattr(DEFAULT_BDI_TABELA, cat)
            mem = MemorialBDIBuilder._build_decomposicao(cat, comp)
            import dataclasses

            for f in dataclasses.fields(mem):
                if f.name not in ("categoria", "soma"):
                    val = getattr(mem, f.name)
                    assert val >= 0, f"{cat}.{f.name} = {val} < 0"


# ---------------------------------------------------------------------------
# MemorialCalculoBDI — builder integration
# ---------------------------------------------------------------------------


class TestMemorialCalculoBDI:
    def test_builder_produces_memorial(self):
        canonical = _make_minimal_canonical()
        memorial = MemorialBDIBuilder().build(
            canonical_in=canonical,
            bdi_fonte="DEFAULT_BDI_TABELA",
            regime_version="pre_reforma",
        )
        assert isinstance(memorial, MemorialCalculoBDI)

    def test_builder_deterministic(self):
        """Same canonical → same memorial (excluding timestamp gerado_em)."""
        canonical = _make_minimal_canonical()
        m1 = MemorialBDIBuilder().build(canonical, "DEFAULT_BDI_TABELA", "pre_reforma")
        m2 = MemorialBDIBuilder().build(canonical, "DEFAULT_BDI_TABELA", "pre_reforma")
        d1 = m1.to_dict()
        d2 = m2.to_dict()
        # gerado_em is a wall-clock timestamp — exclude from determinism check
        d1.get("meta", {}).pop("gerado_em", None)
        d2.get("meta", {}).pop("gerado_em", None)
        assert d1 == d2

    def test_all_five_categories_present(self):
        canonical = _make_minimal_canonical()
        memorial = MemorialBDIBuilder().build(canonical, "DEFAULT_BDI_TABELA", "pre_reforma")
        for cat in ["mao_obra", "material", "servicos", "indireto", "diesel"]:
            assert cat in memorial.bdi_por_categoria
            assert cat in memorial.decomposicao_por_categoria

    def test_all_decomposicoes_soma_one(self):
        canonical = _make_minimal_canonical()
        memorial = MemorialBDIBuilder().build(canonical, "DEFAULT_BDI_TABELA", "pre_reforma")
        for cat, mem in memorial.decomposicao_por_categoria.items():
            assert abs(mem.soma - 1.0) < 0.001, f"{cat} soma={mem.soma}"

    def test_to_dict_json_serializable(self):
        canonical = _make_minimal_canonical()
        memorial = MemorialBDIBuilder().build(canonical, "DEFAULT_BDI_TABELA", "pre_reforma")
        d = memorial.to_dict()
        # Should not raise
        json_str = json.dumps(d, ensure_ascii=False, default=str)
        assert len(json_str) > 100

    def test_encargos_horista_vigencia(self):
        canonical = _make_minimal_canonical()
        memorial = MemorialBDIBuilder().build(canonical, "DEFAULT_BDI_TABELA", "pre_reforma")
        assert memorial.encargos_horista.vigencia == "2026-04-01"
        assert memorial.encargos_mensalista.vigencia == "2026-04-01"

    def test_fonte_bdi_default_when_no_override(self):
        canonical = _make_minimal_canonical()
        memorial = MemorialBDIBuilder().build(canonical, "DEFAULT_BDI_TABELA", "pre_reforma", override_aplicado=False)
        for _cat, bdi in memorial.bdi_por_categoria.items():
            assert bdi.fonte_bdi == "DEFAULT_BDI_TABELA"
            assert bdi.override_aplicado is False

    def test_override_flag_when_manual(self):
        canonical = _make_minimal_canonical()
        memorial = MemorialBDIBuilder().build(canonical, "inputs.bdi_aplicado", "pre_reforma", override_aplicado=True)
        for _cat, bdi in memorial.bdi_por_categoria.items():
            assert bdi.fonte_bdi == "inputs.bdi_aplicado"
            assert bdi.override_aplicado is True

    def test_regime_version_stored(self):
        canonical = _make_minimal_canonical()
        for regime in ["pre_reforma", "transicao", "pleno_cbs_ibs"]:
            memorial = MemorialBDIBuilder().build(canonical, "DEFAULT_BDI_TABELA", regime)
            assert memorial.meta.regime_tributario == regime
            for _cat, bdi in memorial.bdi_por_categoria.items():
                assert bdi.regime_version == regime
