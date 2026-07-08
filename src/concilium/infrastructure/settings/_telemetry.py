"""Settings (parte extraída de settings.py) — grupo _telemetry."""

from __future__ import annotations

from dataclasses import dataclass

from ._core import _flag, _refresh_if_env_changed, _str


@dataclass(frozen=True)
class TelemetrySettings:
    """Observabilidade (ADR-095) e rate limiting (ADR-098).

    Variáveis OTEL padrão (OTEL_EXPORTER_OTLP_ENDPOINT, OTEL_SERVICE_NAME,
    OTEL_SDK_DISABLED) são lidas diretamente pelo OTEL SDK — não mapeadas aqui.
    """

    otel_console: bool
    """CONCILIUM__OTEL_CONSOLE — habilita console exporter OTEL em dev local."""

    otel_sdk_disabled: bool
    """OTEL_SDK_DISABLED — desativa telemetria OTEL por completo."""

    otel_service_name: str
    """OTEL_SERVICE_NAME — nome lógico do serviço exportado."""

    otlp_endpoint: str
    """OTEL_EXPORTER_OTLP_ENDPOINT — endpoint OTLP HTTP (sem sufixo /v1/*)."""

    rate_limit_global: str
    """CONCILIUM__RATE_LIMIT_GLOBAL — limite global de requests (default: 200/minute)."""

    rate_limit_storage_uri: str
    """CONCILIUM__RATE_LIMIT_STORAGE_URI — backend de rate limit (default: memory://)."""

    @classmethod
    def from_env(cls) -> TelemetrySettings:
        return cls(
            otel_console=_flag("CONCILIUM__OTEL_CONSOLE"),
            otel_sdk_disabled=_flag("OTEL_SDK_DISABLED"),
            otel_service_name=_str("OTEL_SERVICE_NAME", "concilium"),
            otlp_endpoint=_str("OTEL_EXPORTER_OTLP_ENDPOINT", ""),
            rate_limit_global=_str("CONCILIUM__RATE_LIMIT_GLOBAL", "200/minute"),
            rate_limit_storage_uri=_str("CONCILIUM__RATE_LIMIT_STORAGE_URI", "memory://"),
        )


_telemetry: TelemetrySettings | None = None


def get_telemetry() -> TelemetrySettings:
    _refresh_if_env_changed()
    global _telemetry
    if _telemetry is None:
        _telemetry = TelemetrySettings.from_env()
    return _telemetry




def _reset_telemetry() -> None:
    global _telemetry
    _telemetry = None
