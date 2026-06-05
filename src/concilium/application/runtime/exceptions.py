"""Exceções e contrato de execução do Runtime."""

from __future__ import annotations

class RuntimeError(Exception):
    """Erro de orquestracao do pipeline."""


class RuntimeDomainError(RuntimeError):
    """Erro de dominio (pre-condicao, regra de negocio, contrato)."""


class RuntimeTechnicalError(RuntimeError):
    """Erro tecnico inesperado durante execucao."""


# Compat retroativa: símbolos movidos para módulos dedicados.
from .contracts import SkillExecutionContract  # noqa: E402,F401
from .gates import _GATE_SKILLS  # noqa: E402,F401
