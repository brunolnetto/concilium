"""Testes para geo_diesel_resolver — orquestração ADR-129 D2/D3/D4/D5.

Combina Escopo (coordenadas + raio_cotacao_km) + MunicipioReferenceClient
(proximidade/desempate por população) + FuelPriceClient (preço por UF) para
decidir a UF de referência e o preço final de diesel, com fallback documentado
em cada etapa (opt-in por raio_cotacao_km, placeholder de coordenadas,
indisponibilidade das APIs externas).
"""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import MagicMock

import pytest

from concilium.application.services.catalog.geo_diesel_resolver import (
    resolver_preco_diesel_escopo,
    resolver_uf_por_proximidade,
)
from concilium.domain.constants import PRECO_DIESEL_REFERENCIA
from concilium.domain.models.project.escopo import Escopo
from concilium.infrastructure.clients.municipios import MunicipioReferenceClient


def _escopo(**overrides) -> Escopo:
    base = dict(
        escopo_id="lote-a",
        projeto_id="proj-1",
        nome="Lote A",
        tipo_obra="terraplenagem",
        localizacao="Fortaleza-CE",
        coordenadas_lat=-3.7172,
        coordenadas_lng=-38.5433,
        data_inicio=date(2026, 1, 1),
        data_termino=date(2026, 12, 31),
        jurisdicao_id="BR-CE",
    )
    base.update(overrides)
    return Escopo(**base)


@pytest.fixture
def municipio_client(tmp_path):
    data = {
        "municipios": [
            {
                "codigo_ibge": "2304400",
                "nome": "Fortaleza",
                "uf": "CE",
                "latitude": -3.7172,
                "longitude": -38.5433,
                "populacao": 2686612,
            },
            {
                "codigo_ibge": "3550308",
                "nome": "Sao Paulo",
                "uf": "SP",
                "latitude": -23.5505,
                "longitude": -46.6333,
                "populacao": 12300000,
            },
        ]
    }
    path = tmp_path / "municipios.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return MunicipioReferenceClient(dataset_path=path)


class TestResolverUfPorProximidade:
    def test_retorna_uf_do_municipio_mais_proximo_dentro_do_raio(self, municipio_client):
        escopo = _escopo(raio_cotacao_km=100.0)
        uf = resolver_uf_por_proximidade(escopo, municipio_client)
        assert uf == "CE"

    def test_none_quando_raio_cotacao_km_ausente(self, municipio_client):
        escopo = _escopo(raio_cotacao_km=None)
        uf = resolver_uf_por_proximidade(escopo, municipio_client)
        assert uf is None

    def test_none_quando_coordenadas_sao_placeholder(self, municipio_client):
        escopo = _escopo(raio_cotacao_km=100.0, coordenadas_lat=0.0, coordenadas_lng=0.0)
        uf = resolver_uf_por_proximidade(escopo, municipio_client)
        assert uf is None

    def test_none_quando_nenhum_municipio_dentro_do_raio(self, municipio_client):
        # Sítio de obra remoto, longe de qualquer município do dataset, raio curto
        escopo = _escopo(
            raio_cotacao_km=10.0,
            coordenadas_lat=-31.77,
            coordenadas_lng=-52.34,  # sul do RS, longe de CE e SP
        )
        uf = resolver_uf_por_proximidade(escopo, municipio_client)
        assert uf is None


class TestResolverPrecoDieselEscopo:
    def test_usa_proximidade_e_fuel_client_quando_ambos_disponiveis(self, municipio_client):
        escopo = _escopo(raio_cotacao_km=100.0)
        fuel_client = MagicMock()
        fuel_client.get_price_str.return_value = 5.75

        preco, fonte = resolver_preco_diesel_escopo(escopo, municipio_client, fuel_client)

        assert preco == 5.75
        assert fonte == "fuel_api"
        fuel_client.get_price_str.assert_called_once_with("ce", "diesel")

    def test_fallback_para_jurisdicao_id_quando_sem_raio(self, municipio_client):
        """Sem raio_cotacao_km, cai para a UF de jurisdicao_id (comportamento por UF, ADR-066)."""
        escopo = _escopo(raio_cotacao_km=None, jurisdicao_id="BR-SP")
        fuel_client = MagicMock()
        fuel_client.get_price_str.return_value = 6.05

        preco, fonte = resolver_preco_diesel_escopo(escopo, municipio_client, fuel_client)

        assert preco == 6.05
        assert fonte == "fuel_api"
        fuel_client.get_price_str.assert_called_once_with("sp", "diesel")

    def test_fallback_constante_quando_nada_disponivel(self, municipio_client):
        escopo = _escopo(raio_cotacao_km=None, jurisdicao_id=None)

        preco, fonte = resolver_preco_diesel_escopo(escopo, municipio_client, fuel_client=None)

        assert preco == PRECO_DIESEL_REFERENCIA
        assert fonte == "fallback_constante"

    def test_fallback_constante_quando_fuel_api_falha(self, municipio_client):
        escopo = _escopo(raio_cotacao_km=100.0)
        fuel_client = MagicMock()
        fuel_client.get_price_str.side_effect = ConnectionError("timeout")

        preco, fonte = resolver_preco_diesel_escopo(escopo, municipio_client, fuel_client)

        assert preco == PRECO_DIESEL_REFERENCIA
        assert fonte == "fallback_constante"
