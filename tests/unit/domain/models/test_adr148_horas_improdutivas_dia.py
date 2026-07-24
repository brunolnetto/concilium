"""ADR-148: horas_improdutivas_dia em RegimeTrabalho e eta_jornada."""

import pytest
from pydantic import ValidationError

from concilium.domain.models.canonical._base import RegimeTrabalho


class TestRegimeTrabalhoHorasImprodutivas:
    def test_default_e_0_5(self):
        regime = RegimeTrabalho(dias_semana=6, horas_dia=8)
        assert regime.horas_improdutivas_dia == 0.5

    def test_aceita_0_0_para_specs_legados(self):
        regime = RegimeTrabalho(dias_semana=6, horas_dia=8, horas_improdutivas_dia=0.0)
        assert regime.horas_improdutivas_dia == 0.0
        assert regime.eta_jornada == 1.0

    def test_rejeita_negativo(self):
        with pytest.raises(ValidationError):
            RegimeTrabalho(dias_semana=6, horas_dia=8, horas_improdutivas_dia=-0.1)

    def test_rejeita_igual_a_horas_dia(self):
        with pytest.raises(ValidationError):
            RegimeTrabalho(dias_semana=6, horas_dia=8, horas_improdutivas_dia=8)

    def test_rejeita_maior_que_horas_dia(self):
        with pytest.raises(ValidationError):
            RegimeTrabalho(dias_semana=6, horas_dia=8, horas_improdutivas_dia=9)


class TestEtaJornada:
    @pytest.mark.parametrize(
        ("horas_dia", "horas_improdutivas_dia", "esperado"),
        [
            (8, 0.5, 0.9375),
            (6, 0.5, 5.5 / 6),
            (10, 0.5, 0.95),
            (8, 0.0, 1.0),
        ],
    )
    def test_calculo_para_multiplos_regimes(self, horas_dia, horas_improdutivas_dia, esperado):
        regime = RegimeTrabalho(dias_semana=6, horas_dia=horas_dia, horas_improdutivas_dia=horas_improdutivas_dia)
        assert regime.eta_jornada == pytest.approx(esperado, abs=1e-9)

    def test_tempo_fixo_nao_e_fracao_constante(self):
        """ADR-148: horas_improdutivas_dia é tempo fixo, então eta_jornada varia com horas_dia."""
        regime_6h = RegimeTrabalho(dias_semana=6, horas_dia=6, horas_improdutivas_dia=0.5)
        regime_10h = RegimeTrabalho(dias_semana=6, horas_dia=10, horas_improdutivas_dia=0.5)
        assert regime_6h.eta_jornada < regime_10h.eta_jornada
