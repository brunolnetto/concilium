from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class DecisionVariables(BaseModel):
    dv1_crew_template: dict[str, str] | None = None  # {atividade_id: template_id}
    dv2_num_equipes: dict[str, dict[str, int]] | None = None  # {atividade_id: {periodo: count}}
    dv3_start_offset: dict[str, int] | None = None  # {atividade_id: offset_days}
    dv4_indirect_policy: Literal["lean", "standard", "robust"] | None = None


__all__ = ["DecisionVariables"]
