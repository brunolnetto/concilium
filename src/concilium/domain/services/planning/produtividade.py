"""One physical productivity definition across Skill 04 and workforce simulation.

F_i(m) is the installed hourly capacity of the actually mobilized composition.
Realizable productivity is rho_i,j = F_i(m_i,j) * p_i,j * c_j * eta_jornada.
Only the remaining physical scope caps weekly *delivery*, not rho_i,j.
"""
from __future__ import annotations

from math import isfinite


def produtividade_realizavel(
    capacidade_instalada: float,
    praticabilidade: float,
    calendario: float,
    jornada: float = 1.0,
) -> float:
    """Apply availability exactly once; preserve the input's time-based unit.

    Callers may pass hourly F(m) (returning hourly rho) or its weekly integral
    F(m)*H (returning weekly realizable capacity). They must not multiply the
    same factors again. Scope closure is applied separately afterwards.
    """
    values = (capacidade_instalada, praticabilidade, calendario, jornada)
    if not all(isfinite(value) for value in values):
        raise ValueError("physical capacity and availability must be finite")
    if capacidade_instalada < 0:
        raise ValueError("installed physical capacity cannot be negative")
    if not all(0.0 <= factor <= 1.0 for factor in values[1:]):
        raise ValueError("availability factors must lie in [0,1]")
    return capacidade_instalada * praticabilidade * calendario * jornada
