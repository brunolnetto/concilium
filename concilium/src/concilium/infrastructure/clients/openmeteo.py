"""Cliente para Open-Meteo Historical Weather API (gratuita, sem chave).

Endpoint: https://archive-api.open-meteo.com/v1/archive
Documentação: https://open-meteo.com/en/docs/historical-weather-api

Para a skill de praticabilidade, precisamos de precipitação diária por semana ISO.
Estratégia: consultar o ano histórico mais recente disponível e agregar por semana ISO.
"""

import hashlib
import logging
import time
from datetime import date
from datetime import date as _date
from pathlib import Path

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Usa home dir para compartilhar cache entre Windows e WSL/Linux.
# tempfile.gettempdir() retorna caminhos diferentes entre os dois ambientes (/tmp vs %TEMP%),
# enquanto Path.home() resolve para o mesmo usuário em ambos.
_CLIMATE_CACHE_DIR = Path.home() / ".concilium_cache" / "climate"
_CLIMATE_CACHE_TTL = 30 * 24 * 3600  # 30 dias


class DadosClimaticosMensais(BaseModel):
    """Estatísticas climáticas agregadas por mês e por semana ISO para uma localização."""

    latitude: float
    longitude: float
    ano_referencia: int
    fonte: str = "open-meteo"
    # Para cada mês "01"-"12": número de dias com precipitação >= cada threshold
    dias_precipitacao_mensal: dict[str, dict[str, int]] = Field(default_factory=dict)
    # estrutura: {"01": {"5mm": 3, "10mm": 1, "20mm": 0}, "02": {...}, ...}

    # Para cada semana ISO "AAAA-Www" (ex. "2024-W01"): número de dias com precipitação >= threshold
    # estrutura: {"2024-W01": {"5mm": 2, "10mm": 1, "20mm": 0}, ...}
    dias_precipitacao_semanal: dict[str, dict[str, int]] = Field(default_factory=dict)


class OpenMeteoClient:
    """Cliente HTTP para Open-Meteo. Implementa cache em memória por (lat, lng, ano)."""

    BASE_URL = "https://archive-api.open-meteo.com/v1/archive"
    TIMEOUT_SECONDS = 30

    def __init__(self, http_client: httpx.Client | None = None):
        self._http = http_client or httpx.Client(timeout=self.TIMEOUT_SECONDS)
        self._cache: dict[tuple[float, float, int], DadosClimaticosMensais] = {}

    @staticmethod
    def _disk_cache_path(latitude: float, longitude: float, ano: int) -> Path:
        key = f"{round(latitude, 4)}_{round(longitude, 4)}_{ano}"
        fname = hashlib.md5(key.encode()).hexdigest()[:16]
        return _CLIMATE_CACHE_DIR / f"{fname}.json"

    def fetch_dados_anuais(self, latitude: float, longitude: float, ano: int) -> DadosClimaticosMensais:
        """Consulta a API e agrega precipitação diária por mês.

        Retorna número de dias com precipitação >= 5mm, >= 10mm, >= 20mm para cada mês.
        Esses thresholds correspondem aos limiares possíveis em perfis (DEC do projeto).
        Cache em memória (por instância) + cache em disco com TTL de 30 dias.
        """
        cache_key = (round(latitude, 4), round(longitude, 4), ano)
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Verifica cache em disco
        disk_path = self._disk_cache_path(latitude, longitude, ano)
        if disk_path.exists():
            try:
                age = time.time() - disk_path.stat().st_mtime
                if age < _CLIMATE_CACHE_TTL:
                    dados = DadosClimaticosMensais.model_validate_json(disk_path.read_text(encoding="utf-8"))
                    self._cache[cache_key] = dados
                    logger.debug("Cache disco: lat=%.4f lng=%.4f ano=%d", latitude, longitude, ano)
                    return dados
            except Exception:
                pass  # cache corrompido — busca da API

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
        response = self._http.get(self.BASE_URL, params=params)  # type: ignore[arg-type]
        response.raise_for_status()
        payload = response.json()

        result = self._parse_response(payload, latitude, longitude, ano)

        # Persiste no cache de disco (best-effort)
        try:
            _CLIMATE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            disk_path.write_text(result.model_dump_json(), encoding="utf-8")
        except Exception:
            pass

        return result

    def _parse_response(self, payload: dict, latitude: float, longitude: float, ano: int) -> DadosClimaticosMensais:
        """Parse resposta Open-Meteo em estatísticas mensais e semanais."""
        daily = payload.get("daily", {})
        dates: list[str] = daily.get("time", [])
        precs: list[float | None] = daily.get("precipitation_sum", [])

        if not dates or len(dates) != len(precs):
            raise ValueError("Resposta Open-Meteo malformada: arrays inconsistentes")

        # Inicializa contadores por mês
        thresholds = [5, 10, 20]
        meses: dict[str, dict[str, int]] = {f"{m:02d}": {f"{t}mm": 0 for t in thresholds} for m in range(1, 13)}
        # Contadores por semana ISO — inicializados conforme dados
        semanas: dict[str, dict[str, int]] = {}

        for date_str, prec in zip(dates, precs, strict=True):
            if prec is None:
                continue
            mes = date_str[5:7]  # "YYYY-MM-DD" -> "MM"
            d = _date.fromisoformat(date_str)
            iso = d.isocalendar()
            semana_key = f"{iso.year}-W{iso.week:02d}"
            if semana_key not in semanas:
                semanas[semana_key] = {f"{t}mm": 0 for t in thresholds}
            for t in thresholds:
                if prec >= t:
                    meses[mes][f"{t}mm"] += 1
                    semanas[semana_key][f"{t}mm"] += 1

        result = DadosClimaticosMensais(
            latitude=latitude,
            longitude=longitude,
            ano_referencia=ano,
            dias_precipitacao_mensal=meses,
            dias_precipitacao_semanal=semanas,
        )
        self._cache[(round(latitude, 4), round(longitude, 4), ano)] = result
        return result
