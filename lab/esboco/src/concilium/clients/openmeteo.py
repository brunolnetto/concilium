"""Cliente para Open-Meteo Historical Weather API (gratuita, sem chave).

Endpoint: https://archive-api.open-meteo.com/v1/archive
Documentação: https://open-meteo.com/en/docs/historical-weather-api

Para a skill de praticabilidade, precisamos de precipitação diária por mês.
Estratégia: consultar o ano histórico mais recente disponível e agregar por mês.
"""

import logging
from datetime import date

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class DadosClimaticosMensais(BaseModel):
    """Estatísticas climáticas agregadas por mês para uma localização."""

    latitude: float
    longitude: float
    ano_referencia: int
    fonte: str = "open-meteo"
    # Para cada mês "01"-"12": número de dias com precipitação >= cada threshold
    dias_precipitacao_mensal: dict[str, dict[str, int]] = Field(default_factory=dict)
    # estrutura: {"01": {"5mm": 3, "10mm": 1, "20mm": 0}, "02": {...}, ...}


class OpenMeteoClient:
    """Cliente HTTP para Open-Meteo. Implementa cache em memória por (lat, lng, ano)."""

    BASE_URL = "https://archive-api.open-meteo.com/v1/archive"
    TIMEOUT_SECONDS = 30

    def __init__(self, http_client: httpx.Client | None = None):
        self._http = http_client or httpx.Client(timeout=self.TIMEOUT_SECONDS)
        self._cache: dict[tuple[float, float, int], DadosClimaticosMensais] = {}

    def fetch_dados_anuais(
        self, latitude: float, longitude: float, ano: int
    ) -> DadosClimaticosMensais:
        """Consulta a API e agrega precipitação diária por mês.

        Retorna número de dias com precipitação >= 5mm, >= 10mm, >= 20mm para cada mês.
        Esses thresholds correspondem aos limiares possíveis em perfis (DEC do projeto).
        """
        cache_key = (round(latitude, 4), round(longitude, 4), ano)
        if cache_key in self._cache:
            return self._cache[cache_key]

        start = date(ano, 1, 1).isoformat()
        end = date(ano, 12, 31).isoformat()
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start,
            "end_date": end,
            "daily": "precipitation_sum",
            "timezone": "auto",
        }

        logger.info("Consultando Open-Meteo: lat=%.4f lng=%.4f ano=%d", latitude, longitude, ano)
        response = self._http.get(self.BASE_URL, params=params)
        response.raise_for_status()
        payload = response.json()

        return self._parse_response(payload, latitude, longitude, ano)

    def _parse_response(
        self, payload: dict, latitude: float, longitude: float, ano: int
    ) -> DadosClimaticosMensais:
        """Parse resposta Open-Meteo em estatísticas mensais."""
        daily = payload.get("daily", {})
        dates: list[str] = daily.get("time", [])
        precs: list[float | None] = daily.get("precipitation_sum", [])

        if not dates or len(dates) != len(precs):
            raise ValueError("Resposta Open-Meteo malformada: arrays inconsistentes")

        # Inicializa contadores por mês
        thresholds = [5, 10, 20]
        meses: dict[str, dict[str, int]] = {
            f"{m:02d}": {f"{t}mm": 0 for t in thresholds} for m in range(1, 13)
        }

        for date_str, prec in zip(dates, precs, strict=True):
            if prec is None:
                continue
            mes = date_str[5:7]  # "YYYY-MM-DD" → "MM"
            for t in thresholds:
                if prec >= t:
                    meses[mes][f"{t}mm"] += 1

        result = DadosClimaticosMensais(
            latitude=latitude,
            longitude=longitude,
            ano_referencia=ano,
            dias_precipitacao_mensal=meses,
        )
        self._cache[(round(latitude, 4), round(longitude, 4), ano)] = result
        return result
