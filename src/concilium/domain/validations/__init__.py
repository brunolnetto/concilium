"""Validadores de regras do Concilium.

ADR-029 Fase 2: módulos movidos de concilium.validations -> concilium.domain.validations.
O pacote concilium.validations mantém um shim de retrocompatibilidade por 1 sprint.
"""

from .catalog import ValidationCode, make_violation
from .cpu_insumo import ValidadorCPUInsumo

__all__ = ["ValidadorCPUInsumo", "ValidationCode", "make_violation"]
