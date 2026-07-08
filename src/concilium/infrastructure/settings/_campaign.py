"""Settings (parte extraída de settings.py) — grupo _campaign."""

from __future__ import annotations

from dataclasses import dataclass

from ._core import _int, _refresh_if_env_changed


@dataclass(frozen=True)
class CampaignSettings:
    """Configuração do motor de exploração de campanha GO (ADR-070, ADR-109)."""

    cardinality_threshold: int
    """CONCILIUM__CAMPAIGN_CARDINALITY_THRESHOLD — cardinalidade máxima para busca exaustiva
    sem aviso (ADR-109: fronteira de tratabilidade). Acima desse valor, executar_campanha()
    emite warnings.warn sugerindo busca guiada (default: 10000)."""

    max_workers: int
    """CONCILIUM__CAMPAIGN_MAX_WORKERS — número de workers paralelos para avaliação de cenários
    (default: 6). Afeta o cálculo de tempo estimado no aviso de tratabilidade."""

    seconds_per_scenario: int
    """CONCILIUM__CAMPAIGN_SECONDS_PER_SCENARIO — estimativa de tempo por cenário em segundos
    usada no cálculo de aviso de tratabilidade (default: 6)."""

    @classmethod
    def from_env(cls) -> CampaignSettings:
        return cls(
            cardinality_threshold=_int("CONCILIUM__CAMPAIGN_CARDINALITY_THRESHOLD", 10_000),
            max_workers=_int("CONCILIUM__CAMPAIGN_MAX_WORKERS", 6),
            seconds_per_scenario=_int("CONCILIUM__CAMPAIGN_SECONDS_PER_SCENARIO", 6),
        )


_campaign: CampaignSettings | None = None


def get_campaign() -> CampaignSettings:
    _refresh_if_env_changed()
    global _campaign
    if _campaign is None:
        _campaign = CampaignSettings.from_env()
    return _campaign




def _reset_campaign() -> None:
    global _campaign
    _campaign = None
