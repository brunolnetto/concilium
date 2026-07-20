"""Settings (parte extraída de settings.py) — grupo _visibility_digest (ADR-143)."""

from __future__ import annotations

from dataclasses import dataclass

from ._core import _flag, _int


@dataclass(frozen=True)
class VisibilityDigestSettings:
    """Configuração do digest periódico de "quem me consultou" (ADR-143 D7/D8)."""

    enabled: bool
    """CONCILIUM__VISIBILITY_DIGEST_ENABLED — habilita o scheduler do digest (default: False)."""

    interval_seconds: int
    """CONCILIUM__VISIBILITY_DIGEST_INTERVAL_SECONDS — intervalo entre execuções (default: 300s/5min).

    Bem menor que o digest de catálogo (ADR-141, 24h): time-gating por conteúdo
    (D8) garante que o tick sozinho não envia nada sem consulta nova pendente.
    """

    @classmethod
    def from_env(cls) -> VisibilityDigestSettings:
        return cls(
            enabled=_flag("CONCILIUM__VISIBILITY_DIGEST_ENABLED"),
            interval_seconds=_int("CONCILIUM__VISIBILITY_DIGEST_INTERVAL_SECONDS", 300),
        )


_visibility_digest: VisibilityDigestSettings | None = None


def get_visibility_digest() -> VisibilityDigestSettings:
    global _visibility_digest
    if _visibility_digest is None:
        _visibility_digest = VisibilityDigestSettings.from_env()
    return _visibility_digest


def _reset_visibility_digest() -> None:
    """Invalida o singleton — usar em fixtures de teste para isolar env vars."""
    global _visibility_digest
    _visibility_digest = None
