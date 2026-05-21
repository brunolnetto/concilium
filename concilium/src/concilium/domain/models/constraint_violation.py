from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ConstraintViolation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: str
    status: Literal["OK", "AVISO", "ERRO"]
    magnitude: float | None = None
    affected_items: list[str] = Field(default_factory=list)
    remediation_hint: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


__all__ = ["ConstraintViolation"]
