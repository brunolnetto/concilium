"""Validadores de regras do Concilium.

ADR-029 Fase 2: módulos movidos de concilium.validations -> concilium.domain.validations.
O pacote concilium.validations mantém uma camada temporária de retrocompatibilidade.
"""

from .catalog import ValidationCode, make_violation
from .cpu_insumo import ValidadorCPUInsumo

__all__ = ["ValidadorCPUInsumo", "ValidationCode", "make_violation"]
