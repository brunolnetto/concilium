"""ADR-005 — ReplannValidator: validates replan candidates against hard constraints."""

from __future__ import annotations

from datetime import UTC, datetime

from concilium.application.replanning.models import ReplannCandidate
from concilium.domain.models.canonical import CanonicalModel, ValidacaoItem

_MAX_DEADLINE_EXTENSION_WEEKS = 2
_MIN_DAYS_BETWEEN_REPLANS = 7


class ReplannValidator:
    """Valida candidatos de replanejamento antes da execução."""

    def validate(
        self,
        candidate: ReplannCandidate,
        canonical: CanonicalModel,
    ) -> list[ValidacaoItem]:
        """Run all VAL-REPLAN-XX checks and return list of validations."""
        validacoes: list[ValidacaoItem] = []

        validacoes.extend(self._val_replan_02(candidate, canonical))
        validacoes.extend(self._val_replan_05(canonical))

        if not any(v.status == "ERRO" for v in validacoes):
            validacoes.append(ValidacaoItem(codigo="VAL-REPLAN-OK", status="OK"))

        return validacoes

    def _val_replan_02(
        self,
        candidate: ReplannCandidate,
        canonical: CanonicalModel,
    ) -> list[ValidacaoItem]:
        """VAL-REPLAN-02: Deadline extension within allowed tolerance."""
        validacoes: list[ValidacaoItem] = []
        if candidate.schedule_delta_weeks > _MAX_DEADLINE_EXTENSION_WEEKS:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-REPLAN-02",
                    status="AVISO",
                    mensagem=(
                        f"Candidato '{candidate.name}' estende o prazo em "
                        f"{candidate.schedule_delta_weeks:.1f} semanas "
                        f"(tolerância: {_MAX_DEADLINE_EXTENSION_WEEKS} semanas)."
                    ),
                )
            )
        return validacoes

    def _val_replan_05(
        self,
        canonical: CanonicalModel,
    ) -> list[ValidacaoItem]:
        """VAL-REPLAN-05: Frequency policy — no replan within 7 days of last replan."""
        validacoes: list[ValidacaoItem] = []
        if not canonical.replanning_history:
            return validacoes

        last = canonical.replanning_history[-1]
        last_approved_at = last.get("approved_at")
        if last_approved_at is None:
            return validacoes

        # Parse if string
        if isinstance(last_approved_at, str):
            try:
                last_dt = datetime.fromisoformat(last_approved_at.replace("Z", "+00:00"))
            except ValueError:
                return validacoes
        elif isinstance(last_approved_at, datetime):
            last_dt = last_approved_at
        else:
            return validacoes

        now = datetime.now(UTC)
        days_since = (now - last_dt).days
        if days_since < _MIN_DAYS_BETWEEN_REPLANS:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-REPLAN-05",
                    status="AVISO",
                    mensagem=(
                        f"Replanejamento proposto {days_since} dia(s) após o último. "
                        f"Mínimo recomendado: {_MIN_DAYS_BETWEEN_REPLANS} dias. "
                        "Risco de instabilidade no cronograma."
                    ),
                )
            )
        return validacoes
