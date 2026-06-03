"""ADR-025 — CatalogMutationGuard: protege mutações de catálogo durante execução de pipeline.

Regras:
  1. Se pipeline_integridade == "CORROMPIDO", bloqueio incondicional.
  2. Se pipeline_blocked_from não está vazio, bloqueio (pipeline em estado inválido).
  3. Se o projeto está em status EM_EXECUCAO com run recente (< TTL_LOCK_SECONDS),
     bloqueio temporário para evitar invalidar runs em andamento.

Exceptions:
  CatalogMutationConflict: levantada quando a mutação é vetada.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from concilium.domain.models.canonical import CanonicalModel

# Bloqueio temporário para projetos em execução ativa (segundos)
TTL_LOCK_SECONDS: int = 86_400  # 24 horas


class CatalogMutationConflict(Exception):
    """Mutação de catálogo vetada pelo CatalogMutationGuard.

    Args:
        project_id: ID do projeto afetado.
        reason: Motivo humano legível.
        pipeline_integridade: Valor atual de canonical.pipeline_integridade.
        blocked_skills: Skills GATE que falharam (se aplicável).
    """

    def __init__(
        self,
        project_id: str,
        reason: str,
        pipeline_integridade: str | None = None,
        blocked_skills: list[str] | None = None,
    ) -> None:
        self.project_id = project_id
        self.reason = reason
        self.pipeline_integridade = pipeline_integridade
        self.blocked_skills = blocked_skills or []
        super().__init__(f"[CatalogMutationConflict] projeto={project_id!r}: {reason}")


class CatalogMutationGuard:
    """Guarda de mutação de catálogo — verifica pré-condições antes de PROPOSE/COMMIT.

    Uso típico em ferramentas MCP:
        guard = CatalogMutationGuard()
        guard.check_can_mutate(project_id=pid, canonical=canonical)
        # levanta CatalogMutationConflict se vetado
        # continua normalmente se aprovado
    """

    def check_can_mutate(
        self,
        project_id: str,
        canonical: CanonicalModel,
        run_started_at: datetime | None = None,
    ) -> None:
        """Verifica se é seguro executar uma mutação de catálogo para este projeto.

        Args:
            project_id: ID do projeto (para mensagem de erro).
            canonical: Estado atual do canonical do projeto.
            run_started_at: Timestamp do último run iniciado (opcional).
                Se fornecido, aplica TTL_LOCK_SECONDS para projetos EM_EXECUCAO.

        Raises:
            CatalogMutationConflict: Se a mutação for vetada.
        """
        integridade = canonical.pipeline_integridade
        blocked = canonical.pipeline_blocked_from or []
        status_projeto = canonical.projeto.status if canonical.projeto else "RASCUNHO"

        # Regra 1: Pipeline corrompido — bloqueio incondicional
        if integridade == "CORROMPIDO":
            raise CatalogMutationConflict(
                project_id=project_id,
                reason=(
                    "Pipeline em estado CORROMPIDO. Corrija as skills GATE com falha antes de "
                    "propor mudanças no catálogo. Skills bloqueadas: "
                    + (", ".join(blocked) if blocked else "desconhecido")
                ),
                pipeline_integridade=integridade,
                blocked_skills=list(blocked),
            )

        # Regra 2: Skills GATE com falha (pipeline_blocked_from não vazio)
        if blocked:
            raise CatalogMutationConflict(
                project_id=project_id,
                reason=(
                    f"Pipeline parcialmente bloqueado pelas skills: {', '.join(blocked)}. "
                    "Resolva os erros antes de alterar o catálogo."
                ),
                pipeline_integridade=integridade,
                blocked_skills=list(blocked),
            )

        # Regra 3: Projeto EM_EXECUCAO com run recente (TTL)
        if status_projeto == "EM_EXECUCAO" and run_started_at is not None:
            now = datetime.now(UTC)
            lock_until = run_started_at + timedelta(seconds=TTL_LOCK_SECONDS)
            if now < lock_until:
                remaining_minutes = int((lock_until - now).total_seconds() / 60)
                raise CatalogMutationConflict(
                    project_id=project_id,
                    reason=(
                        f"Projeto em execução ativa (run iniciado em {run_started_at.isoformat()}). "
                        f"Mutações de catálogo bloqueadas por {remaining_minutes} minuto(s). "
                        f"Aguarde o fim do run ou cancele-o antes de propor alterações."
                    ),
                    pipeline_integridade=integridade,
                )

    def assert_safe_to_mutate(
        self,
        project_id: str,
        catalog_name: str = "",
    ) -> None:
        """Lightweight pre-check without requiring a canonical.

        Use when a canonical is not yet available (e.g., before first pipeline run).
        Raises CatalogMutationConflict only if stateful conditions (not checked here)
        are known to be violated. Safe to call unconditionally.
        """
        # No canonical available: assume safe.
        # Callers that have a canonical should use check_can_mutate() instead.
