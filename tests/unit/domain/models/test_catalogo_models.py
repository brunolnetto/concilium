"""Coverage batch 8 — scoring, resolver, phase_classifier, catalogo, health."""

from __future__ import annotations

import pytest

# catalogo.py lines 38, 40, 42: _infer_tipo_combustivel branches
# ---------------------------------------------------------------------------


class TestInferTipoCombustivel:
    def _infer(self, id_):
        from concilium.domain.models.catalog.catalogo import _infer_tipo_combustivel

        return _infer_tipo_combustivel(id_)

    def test_biodiesel_b100(self):
        """Line 38: 'BIODIESEL' in upper → TipoCombustivel.BIODIESEL."""
        from concilium.domain.models.catalog.catalogo import TipoCombustivel

        assert self._infer("EQ-BIODIESEL-01") == TipoCombustivel.BIODIESEL

    def test_b100_keyword(self):
        """Line 38: 'B100' in upper → TipoCombustivel.BIODIESEL."""
        from concilium.domain.models.catalog.catalogo import TipoCombustivel

        assert self._infer("EQ-B100-MOTOR") == TipoCombustivel.BIODIESEL

    def test_eletrico(self):
        """Line 40: 'ELETRIC' in upper → TipoCombustivel.ELETRICO."""
        from concilium.domain.models.catalog.catalogo import TipoCombustivel

        assert self._infer("EQ-ELETRICO-01") == TipoCombustivel.ELETRICO

    def test_diesel_s500(self):
        """Line 42: 'S500' in upper → TipoCombustivel.DIESEL_S500."""
        from concilium.domain.models.catalog.catalogo import TipoCombustivel

        assert self._infer("EQ-MOTOR-S500") == TipoCombustivel.DIESEL_S500


# ---------------------------------------------------------------------------


# catalogo.py lines 78-82: ClasseCompartilhamento._validate_fields_per_class
# ---------------------------------------------------------------------------


class TestClasseCompartilhamentoValidator:
    def test_valid_exclusivo_dedicado(self):
        """Lines 78, 80, 82: exclusivo_dedicado without fracao_uso → valid."""
        from concilium.domain.models.catalog.catalogo import ClasseCompartilhamento

        obj = ClasseCompartilhamento(classe="exclusivo_dedicado")
        assert obj.classe == "exclusivo_dedicado"

    def test_exclusivo_compartilhavel_without_fracao_raises(self):
        """Lines 78-79: exclusivo_compartilhavel without fracao_uso → ValueError."""
        import pydantic

        from concilium.domain.models.catalog.catalogo import ClasseCompartilhamento

        with pytest.raises((ValueError, pydantic.ValidationError)):
            ClasseCompartilhamento(classe="exclusivo_compartilhavel", fracao_uso=None)

    def test_concorrente_compartilhavel_with_fracao_raises(self):
        """Lines 80-81: concorrente_compartilhavel with fracao_uso set → ValueError."""
        import pydantic

        from concilium.domain.models.catalog.catalogo import ClasseCompartilhamento

        with pytest.raises((ValueError, pydantic.ValidationError)):
            ClasseCompartilhamento(classe="concorrente_compartilhavel", fracao_uso=0.5)

    def test_valid_concorrente_compartilhavel(self):
        """Lines 78, 80, 82: concorrente_compartilhavel without fracao_uso → valid."""
        from concilium.domain.models.catalog.catalogo import ClasseCompartilhamento

        obj = ClasseCompartilhamento(classe="concorrente_compartilhavel")
        assert obj.fracao_uso is None


# ---------------------------------------------------------------------------


# catalogo.py line 169: Insumo._normalizar_unidade field validator
# ---------------------------------------------------------------------------


class TestInsumoNormalizarUnidade:
    def test_create_insumo_triggers_normalizer(self):
        """Line 169: creating Insumo calls _normalizar_unidade on the unidade field."""
        from concilium.domain.models.catalog.catalogo import Insumo

        insumo = Insumo(
            codigo="MAT-001",
            tipo="MATERIAL",
            descricao="Concreto usinado",
            unidade="M3",
            preco_unitario=350.0,
            fonte_preco="catalogo_proprio",
        )
        assert insumo.unidade is not None


# ---------------------------------------------------------------------------


# catalogo.py line 336: CPU._validar_producao_e_coeficientes raises for empty ref
# ---------------------------------------------------------------------------


class TestCPUValidatorEmptyProducaoRef:
    def test_empty_producao_id_ref_raises(self):
        """Line 336: producao_id_ref is '' (falsy) → validator raises ValueError."""
        import pydantic

        from concilium.domain.models.catalog.catalogo import CPU

        with pytest.raises((ValueError, pydantic.ValidationError), match="producao_id_ref"):
            CPU(
                codigo="CPU-001",
                descricao="Test CPU",
                unidade="m3",
                origem="PROPRIA",
                producao_id_ref="",
                categoria="TERRAPLENAGEM",
            )


# ---------------------------------------------------------------------------

