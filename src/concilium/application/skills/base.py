"""Tipos base compartilhados por todas as skills do pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING

from concilium.domain.models.canonical import CanonicalModel, ValidacaoItem

if TYPE_CHECKING:
    from concilium.domain.models.artifact import ArtifactEnvelope


class SkillResult:
    """Resultado retornado por qualquer skill. Carrega canônico atualizado + validações.

    O campo ``artifacts`` (opcional) transporta artefatos tipados ADR-018
    produzidos pela skill (ex: ArtifactEnvelope[RelatorioCriticidade]).
    O runtime persiste o canônico; os artefatos são responsabilidade do
    consumidor (MCP tool ou teste) que decidirá como armazená-los.
    """

    def __init__(
        self,
        canonical: CanonicalModel,
        validacoes: list[ValidacaoItem],
        artifacts: list[ArtifactEnvelope] | None = None,
    ) -> None:
        self.canonical = canonical
        self.validacoes = validacoes
        self.has_errors = any(v.status == "ERRO" for v in validacoes)
        self.artifacts: list[ArtifactEnvelope] = artifacts or []
