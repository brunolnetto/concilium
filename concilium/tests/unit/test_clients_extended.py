"""Tests for clients/openmeteo.py and clients/fuel.py — missing coverage paths."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import httpx
import pytest

from concilium.infrastructure.clients.openmeteo import DadosClimaticosMensais, OpenMeteoClient

# ─────────────────────────────────────────────────────────────────────────────
#  Helpers — sample Open-Meteo payload
# ─────────────────────────────────────────────────────────────────────────────


def _make_payload(n_days: int = 5, prec_val: float = 12.0) -> dict:
    """Build a minimal valid Open-Meteo /v1/archive response."""
    dates = [f"2023-01-{d:02d}" for d in range(1, n_days + 1)]
    precs = [prec_val] * n_days
    return {
        "latitude": -3.75,
        "longitude": -38.58,
        "daily": {
            "time": dates,
            "precipitation_sum": precs,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
#  OpenMeteoClient
# ─────────────────────────────────────────────────────────────────────────────


class TestOpenMeteoClient:
    def test_parse_response_valid_payload(self):
        """_parse_response() aggregates precipitation by month and ISO week."""
        payload = _make_payload(n_days=5, prec_val=12.0)
        client = OpenMeteoClient(http_client=MagicMock())
        result = client._parse_response(payload, -3.75, -38.58, 2023)

        assert isinstance(result, DadosClimaticosMensais)
        assert result.ano_referencia == 2023
        # 5 days with 12mm each → 5mm≥, 10mm≥, 20mm=0 for January
        assert result.dias_precipitacao_mensal["01"]["5mm"] == 5
        assert result.dias_precipitacao_mensal["01"]["10mm"] == 5
        assert result.dias_precipitacao_mensal["01"]["20mm"] == 0

    def test_parse_response_none_prec_skipped(self):
        """_parse_response() skips None precipitation values."""
        payload = {
            "daily": {
                "time": ["2023-01-01", "2023-01-02", "2023-01-03"],
                "precipitation_sum": [None, 25.0, None],
            }
        }
        client = OpenMeteoClient(http_client=MagicMock())
        result = client._parse_response(payload, -3.75, -38.58, 2023)
        # Only the 25mm day counts
        assert result.dias_precipitacao_mensal["01"]["20mm"] == 1
        assert result.dias_precipitacao_mensal["01"]["5mm"] == 1

    def test_parse_response_malformed_raises(self):
        """_parse_response() raises ValueError if arrays length mismatch."""
        payload = {
            "daily": {
                "time": ["2023-01-01", "2023-01-02"],
                "precipitation_sum": [5.0],  # length mismatch
            }
        }
        client = OpenMeteoClient(http_client=MagicMock())
        with pytest.raises(ValueError, match="malformada"):
            client._parse_response(payload, -3.75, -38.58, 2023)

    def test_parse_response_empty_arrays_raises(self):
        """_parse_response() raises ValueError for empty daily arrays."""
        payload = {
            "daily": {
                "time": [],
                "precipitation_sum": [],
            }
        }
        client = OpenMeteoClient(http_client=MagicMock())
        with pytest.raises(ValueError):
            client._parse_response(payload, -3.75, -38.58, 2023)

    def test_parse_response_caches_result(self):
        """_parse_response() stores result in client._cache."""
        payload = _make_payload(n_days=3, prec_val=8.0)
        client = OpenMeteoClient(http_client=MagicMock())
        result = client._parse_response(payload, -3.75, -38.58, 2023)
        cache_key = (round(-3.75, 4), round(-38.58, 4), 2023)
        assert cache_key in client._cache
        assert client._cache[cache_key] is result

    def test_parse_response_semanal_keys(self):
        """_parse_response() populates dias_precipitacao_semanal with ISO week keys."""
        payload = _make_payload(n_days=7, prec_val=6.0)
        client = OpenMeteoClient(http_client=MagicMock())
        result = client._parse_response(payload, -3.75, -38.58, 2023)
        # Should have at least one week key
        assert len(result.dias_precipitacao_semanal) >= 1
        # All keys should match pattern YYYY-Www
        for key in result.dias_precipitacao_semanal:
            assert "-W" in key

    def test_fetch_dados_anuais_cache_hit(self):
        """fetch_dados_anuais() returns cached result without HTTP call."""
        client = OpenMeteoClient(http_client=MagicMock())
        # Pre-populate cache
        cached = DadosClimaticosMensais(
            latitude=-3.75,
            longitude=-38.58,
            ano_referencia=2023,
        )
        client._cache[(round(-3.75, 4), round(-38.58, 4), 2023)] = cached
        result = client.fetch_dados_anuais(-3.75, -38.58, 2023)
        assert result is cached
        client._http.get.assert_not_called()

    def test_fetch_dados_anuais_http_call(self):
        """fetch_dados_anuais() makes HTTP GET and parses response."""
        from pathlib import Path

        payload = _make_payload(n_days=31, prec_val=3.0)

        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = payload
        mock_http.get.return_value = mock_response

        with patch.object(
            OpenMeteoClient, "_disk_cache_path", return_value=Path("/nonexistent/__test_no_cache__.json")
        ):
            client = OpenMeteoClient(http_client=mock_http)
            result = client.fetch_dados_anuais(-3.75, -38.58, 2023)
        assert isinstance(result, DadosClimaticosMensais)
        assert result.ano_referencia == 2023
        mock_http.get.assert_called_once()

    def test_fetch_dados_anuais_http_error_propagates(self):
        """fetch_dados_anuais() propagates HTTP errors."""
        from pathlib import Path

        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock()
        )
        mock_http.get.return_value = mock_response

        with patch.object(
            OpenMeteoClient, "_disk_cache_path", return_value=Path("/nonexistent/__test_no_cache__.json")
        ):
            client = OpenMeteoClient(http_client=mock_http)
            with pytest.raises(httpx.HTTPStatusError):
                client.fetch_dados_anuais(-3.75, -38.58, 2023)

    def test_parse_response_threshold_buckets(self):
        """Each precipitation day increments correct threshold buckets."""
        # 3mm: no bucket; 7mm: 5mm only; 11mm: 5mm+10mm; 25mm: all 3
        payload = {
            "daily": {
                "time": ["2023-03-01", "2023-03-02", "2023-03-03", "2023-03-04"],
                "precipitation_sum": [3.0, 7.0, 11.0, 25.0],
            }
        }
        client = OpenMeteoClient(http_client=MagicMock())
        result = client._parse_response(payload, 0.0, 0.0, 2023)
        m = result.dias_precipitacao_mensal["03"]
        assert m["5mm"] == 3  # 7, 11, 25
        assert m["10mm"] == 2  # 11, 25
        assert m["20mm"] == 1  # 25

    def test_dados_climaticos_model_defaults(self):
        """DadosClimaticosMensais has expected default values."""
        d = DadosClimaticosMensais(latitude=0.0, longitude=0.0, ano_referencia=2023)
        assert d.fonte == "open-meteo"
        assert d.dias_precipitacao_mensal == {}
        assert d.dias_precipitacao_semanal == {}


# ─────────────────────────────────────────────────────────────────────────────
#  FuelPriceClient
# ─────────────────────────────────────────────────────────────────────────────


class TestFuelPriceClient:
    def _make_api_response(self) -> dict:
        return {
            "data_coleta": "2025-06-15 10:00:00",
            "fonte": "ANP",
            "moeda": "BRL",
            "error": None,
            "precos": {
                "diesel": {
                    "br": "5,50",
                    "sp": "5,30",
                    "go": "5,45",
                    "ce": "5,60",
                },
                "gasolina": {
                    "br": "6,10",
                    "sp": "5,90",
                    "go": "6,20",
                    "ce": "6,30",
                },
            },
        }

    def test_parse_state_valid(self):
        """parse_state() resolves known aliases."""
        from concilium.infrastructure.clients.fuel import State, parse_state

        assert parse_state("go") == State.GO
        assert parse_state("SP") == State.SP
        assert parse_state("brasil") == State.BR

    def test_parse_state_unknown_raises(self):
        """parse_state() raises ValueError for unknown state."""
        from concilium.infrastructure.clients.fuel import parse_state

        with pytest.raises(ValueError, match="Unknown state"):
            parse_state("xyz_invalid")

    def test_parse_fuel_valid(self):
        """parse_fuel() resolves known aliases."""
        from concilium.infrastructure.clients.fuel import FuelType, parse_fuel

        assert parse_fuel("diesel") == FuelType.DIESEL
        assert parse_fuel("gas") == FuelType.GASOLINA

    def test_parse_fuel_unknown_raises(self):
        """parse_fuel() raises ValueError for unknown fuel."""
        from concilium.infrastructure.clients.fuel import parse_fuel

        with pytest.raises(ValueError, match="Unknown fuel"):
            parse_fuel("kerosene")

    @patch("concilium.infrastructure.clients.fuel.requests.get")
    def test_get_price_returns_float(self, mock_get):
        """get_price() returns float price for a state/fuel combo."""
        from concilium.infrastructure.clients.fuel import FuelPriceClient, FuelType, State

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = self._make_api_response()
        mock_get.return_value = mock_response

        client = FuelPriceClient()
        price = client.get_price(State.BR, FuelType.DIESEL)
        assert isinstance(price, float)
        assert price == 5.50

    @patch("concilium.infrastructure.clients.fuel.requests.get")
    def test_get_all_returns_dict(self, mock_get):
        """get_all() returns dict of state → price."""
        from concilium.infrastructure.clients.fuel import FuelPriceClient, FuelType

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = self._make_api_response()
        mock_get.return_value = mock_response

        client = FuelPriceClient()
        result = client.get_all(FuelType.GASOLINA)
        assert isinstance(result, dict)
        assert "br" in result

    @patch("concilium.infrastructure.clients.fuel.requests.get")
    def test_get_metadata_populated(self, mock_get):
        """get_metadata() returns dict with source and timestamp."""
        from concilium.infrastructure.clients.fuel import FuelPriceClient

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = self._make_api_response()
        mock_get.return_value = mock_response

        client = FuelPriceClient()
        meta = client.get_metadata()
        assert meta["source"] == "ANP"
        assert meta["currency"] == "BRL"
        assert isinstance(meta["timestamp"], datetime)

    @patch("concilium.infrastructure.clients.fuel.requests.get")
    def test_api_error_flag_raises(self, mock_get):
        """_fetch() raises ValueError when API returns error flag."""
        from concilium.infrastructure.clients.fuel import FuelPriceClient, FuelType, State

        error_response = self._make_api_response()
        error_response["error"] = "Service unavailable"
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = error_response
        mock_get.return_value = mock_response

        client = FuelPriceClient()
        with pytest.raises(ValueError, match="error"):
            client.get_price(State.BR, FuelType.DIESEL)

    @patch("concilium.infrastructure.clients.fuel.requests.get")
    def test_validate_suspicious_price_raises(self, mock_get):
        """_validate() raises ValueError for suspicious prices (< 3 or > 15)."""
        from concilium.infrastructure.clients.fuel import FuelPriceClient, FuelType, State

        bad_response = self._make_api_response()
        bad_response["precos"]["diesel"]["br"] = "1,50"  # < 3 = suspicious
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = bad_response
        mock_get.return_value = mock_response

        client = FuelPriceClient()
        with pytest.raises(ValueError, match="Suspicious"):
            client.get_price(State.BR, FuelType.DIESEL)

    @patch("concilium.infrastructure.clients.fuel.requests.get")
    def test_cache_ttl_hit(self, mock_get):
        """_load() uses cache within TTL (HTTP call made only once)."""
        from concilium.infrastructure.clients.fuel import FuelPriceClient, FuelType, State

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = self._make_api_response()
        mock_get.return_value = mock_response

        client = FuelPriceClient()
        client.get_price(State.BR, FuelType.DIESEL)
        client.get_price(State.BR, FuelType.DIESEL)  # Should use cache
        # Only one HTTP call should have been made
        assert mock_get.call_count == 1

    @patch("concilium.infrastructure.clients.fuel.requests.get")
    def test_get_price_str_string_interface(self, mock_get):
        """get_price_str() accepts string state/fuel and returns float."""
        from concilium.infrastructure.clients.fuel import FuelPriceClient

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = self._make_api_response()
        mock_get.return_value = mock_response

        client = FuelPriceClient()
        price = client.get_price_str("go", "diesel")
        assert isinstance(price, float)
