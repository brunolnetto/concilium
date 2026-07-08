"""Testes para resolver_preco_diesel_uf — reconexão do FuelPriceClient (ADR-129 D3).

`pu_calculator.resolver_preco_diesel_uf` consulta o FuelPriceClient por UF quando
disponível, com fallback documentado para PRECO_DIESEL_REFERENCIA em caso de
indisponibilidade da API externa ou ausência de UF/client.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from concilium.application.catalog.pu_calculator import resolver_preco_diesel_uf
from concilium.domain.constants import PRECO_DIESEL_REFERENCIA


class TestResolverPrecoDieselUf:
    def test_usa_fuel_client_quando_disponivel(self):
        fuel_client = MagicMock()
        fuel_client.get_price_str.return_value = 5.89

        preco, fonte = resolver_preco_diesel_uf("CE", fuel_client)

        assert preco == 5.89
        assert fonte == "fuel_api"
        fuel_client.get_price_str.assert_called_once_with("ce", "diesel")

    def test_fallback_quando_client_e_none(self):
        preco, fonte = resolver_preco_diesel_uf("CE", None)

        assert preco == PRECO_DIESEL_REFERENCIA
        assert fonte == "fallback_constante"

    def test_fallback_quando_uf_e_none(self):
        fuel_client = MagicMock()

        preco, fonte = resolver_preco_diesel_uf(None, fuel_client)

        assert preco == PRECO_DIESEL_REFERENCIA
        assert fonte == "fallback_constante"
        fuel_client.get_price_str.assert_not_called()

    def test_fallback_quando_client_lanca_excecao(self):
        """API externa indisponível (timeout, erro HTTP, UF desconhecida na API) — rede de segurança."""
        fuel_client = MagicMock()
        fuel_client.get_price_str.side_effect = ConnectionError("timeout")

        preco, fonte = resolver_preco_diesel_uf("CE", fuel_client)

        assert preco == PRECO_DIESEL_REFERENCIA
        assert fonte == "fallback_constante"

    def test_normaliza_uf_para_minusculas(self):
        fuel_client = MagicMock()
        fuel_client.get_price_str.return_value = 6.10

        resolver_preco_diesel_uf("SP", fuel_client)

        fuel_client.get_price_str.assert_called_once_with("sp", "diesel")
