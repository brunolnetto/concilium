"""Contratos tipados de execução do Runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SkillExecutionContract:
    """Contrato unico de execucao de uma skill."""

    skill_id: str
    signature: list[str]
    required_inputs: list[str]
    optional_inputs: list[str]
    depends_on_skills: list[str]
    produces_section: str | None
    output_schema: dict[str, Any]
