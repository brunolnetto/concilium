"""Testes unitários do Conversor de Unidades (ADR-034)."""

import pytest

from concilium.domain.services.conversor_unidades import ConversorUnidades, UnidadeIncompativelError


def test_conversao_massa():
    # Tonelada para kg
    assert ConversorUnidades.converter(1.0, "t", "kg") == 1000.0
    # kg para tonelada
    assert ConversorUnidades.converter(500.0, "kg", "t") == 0.5
    # ton para t (sinônimos)
    assert ConversorUnidades.converter(1.5, "ton", "t") == 1.5


def test_conversao_volume():
    # m3 para litro
    assert ConversorUnidades.converter(1.0, "m3", "l") == 1000.0
    # litro para m3
    assert ConversorUnidades.converter(2500.0, "litro", "m3") == 2.5


def test_conversao_tempo():
    # mês para h (base CLT 220h)
    assert ConversorUnidades.converter(1.0, "mes", "h") == 220.0
    # dia para h
    assert ConversorUnidades.converter(2.0, "dia", "h") == 16.0


def test_unidade_incompativel_dispara_erro():
    with pytest.raises(UnidadeIncompativelError):
        ConversorUnidades.converter(100.0, "kg", "m3")


def test_normalizacao_case_insensitive():
    assert ConversorUnidades.converter(1.0, "KG", "T") == 0.001
    assert ConversorUnidades.converter(1000.0, "  l  ", "M3") == 1.0


def test_resolver_coeficiente_cpu():
    # Cenário: Engenheiro especificou 400kg na CPU, mas insumo está em 't' no catálogo.
    # O cálculo de custo deve usar 0.4.
    valor_ajustado = ConversorUnidades.resolver_coeficiente_cpu(400.0, "kg", "t")
    assert valor_ajustado == 0.4


def test_sao_compativeis():
    assert ConversorUnidades.sao_compativeis("kg", "t") is True
    assert ConversorUnidades.sao_compativeis("m", "km") is True
    assert ConversorUnidades.sao_compativeis("kg", "m3") is False
