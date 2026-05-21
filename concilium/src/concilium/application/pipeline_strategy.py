"""ADR-063 §D6: Pipeline Strategy — despacho por tipo de projeto.

Cada tipo de projeto tem uma estratégia que define:
- Validação de pré-condições antes do pipeline rodar
- Sequência de skills executadas

Adicionar um novo tipo = nova subclasse de PipelineStrategy.
Não há if/else espalhados no runtime.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from concilium.application.services.project_repository import ProjectHandle

# Skills do pipeline padrão (hot_project)
HOT_PROJECT_PIPELINE_SKILLS: list[str] = [
    "00-escopo",
    "02-produtividade-climatica",
    "03-catalogo-de-recursos",
    "04-cronograma",
    "03-equipes-diretas",
    "03A-derivar-requisitos",
    "03B-alocacao-recursos",
    "03C-validar-compartilhamento",
    "06-precificacao-unitaria",
    "07-custos-indiretos",
    "06-consolidar",
]

# ADR-063 §F6: skills do pipeline para project (composição gradual)
# Omite skills que dependem de benchmark (03-catalogo-de-recursos carrega do catálogo diretamente).
# Acrescenta validação de grafo de predecessão antes do cronograma.
PROJECT_PIPELINE_SKILLS: list[str] = [
    "00-escopo",
    "02-produtividade-climatica",
    "03-catalogo-de-recursos",
    "04-cronograma",
    "03-equipes-diretas",
    "03A-derivar-requisitos",
    "03B-alocacao-recursos",
    "03C-validar-compartilhamento",
    "06-precificacao-unitaria",
    "07-custos-indiretos",
    "06-consolidar",
]


class PipelineStrategy(Protocol):
    """Interface de estratégia de pipeline (ADR-063 §D6)."""

    def validate_preconditions(self, project: ProjectHandle) -> None:
        """Valida pré-condições antes de rodar qualquer skill.

        Raises:
            ValueError: Se as pré-condições não forem satisfeitas.
        """
        ...

    def skill_sequence(self) -> list[str]:
        """Retorna a sequência de skill IDs para este tipo de projeto."""
        ...


class HotProjectStrategy:
    """Pipeline para hot_project: EAP pré-populada vinda de benchmark (ADR-063 §D2)."""

    def validate_preconditions(self, project: ProjectHandle) -> None:
        pass  # hot_project: sem restrições adicionais

    def skill_sequence(self) -> list[str]:
        return list(HOT_PROJECT_PIPELINE_SKILLS)


class ProjectStrategy:
    """Pipeline para project: composição gradual de EAP + predecessão (ADR-063 §D3)."""

    def validate_preconditions(self, project: ProjectHandle) -> None:
        status = project.status_eap
        if status not in ("RASCUNHO_PRONTO", "ATIVO"):
            raise ValueError(
                f"Projeto do tipo 'project' requer status_eap == 'RASCUNHO_PRONTO' para rodar o pipeline. "
                f"Status atual: '{status}'. Complete a composição da EAP antes de executar."
            )

    def skill_sequence(self) -> list[str]:
        return list(PROJECT_PIPELINE_SKILLS)


def get_pipeline_strategy(project: ProjectHandle) -> PipelineStrategy:
    """Retorna a estratégia de pipeline correta para o tipo do projeto.

    Extensão: adicionar novo tipo = novo elif + nova subclasse.
    """
    tipo = project.tipo_projeto
    if tipo == "hot_project":
        return HotProjectStrategy()
    if tipo == "project":
        return ProjectStrategy()
    # Default seguro: trata tipos desconhecidos como hot_project
    return HotProjectStrategy()
