"""Settings (parte extraída de settings.py) — grupo _catalog_digest (ADR-141)."""

from __future__ import annotations

from dataclasses import dataclass

from ._core import _flag, _int


@dataclass(frozen=True)
class CatalogDigestSettings:
    """Configuração do digest periódico de rascunhos de catálogo pendentes (ADR-141)."""

    enabled: bool
    """CONCILIUM__CATALOG_DIGEST_ENABLED — habilita o scheduler do digest (default: False)."""

    interval_hours: int
    """CONCILIUM__CATALOG_DIGEST_INTERVAL_HOURS — intervalo entre execuções do digest (default: 24h)."""

    @classmethod
    def from_env(cls) -> CatalogDigestSettings:
        return cls(
            enabled=_flag("CONCILIUM__CATALOG_DIGEST_ENABLED"),
            interval_hours=_int("CONCILIUM__CATALOG_DIGEST_INTERVAL_HOURS", 24),
        )


_catalog_digest: CatalogDigestSettings | None = None


def get_catalog_digest() -> CatalogDigestSettings:
    global _catalog_digest
    if _catalog_digest is None:
        _catalog_digest = CatalogDigestSettings.from_env()
    return _catalog_digest


def _reset_catalog_digest() -> None:
    """Invalida o singleton — usar em fixtures de teste para isolar env vars."""
    global _catalog_digest
    _catalog_digest = None
