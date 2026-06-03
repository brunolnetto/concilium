"""ADR-003 — Weekly Progress Tracking Models.

Tracks actual vs. planned progress per activity per ISO week.
Append-only: ProgressUpdate is never modified after creation.
"""

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class ProgressUpdate(BaseModel):
    """Registro imutável de progresso semanal para uma atividade."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    update_id: str = Field(default_factory=lambda: str(uuid4()))
    activity_id: str
    week_key: str  # ISO "AAAA-Www" (ex: "2026-W23")
    quantidade_realizada: float = Field(ge=0)
    efficiency_observed: float = Field(ge=0.0, le=1.0)
    recorded_by: str
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    notes: str | None = None


class ActivityProgress(BaseModel):
    """Estado derivado de progresso de uma atividade — calculado a partir dos updates."""

    model_config = ConfigDict(extra="ignore")

    activity_id: str
    quantidade_planejada_total: float = Field(ge=0)
    quantidade_realizada_total: float = Field(ge=0)
    pct_completude: float = Field(ge=0.0, le=1.0)
    delay_weeks: float  # positivo = atrasado, negativo = adiantado
    updates: list[ProgressUpdate] = Field(default_factory=list)


class WeeklyProgressReport(BaseModel):
    """Snapshot de progresso do projeto em uma semana específica."""

    model_config = ConfigDict(extra="ignore")

    project_id: str
    week_key: str
    activities: list[ActivityProgress] = Field(default_factory=list)
    spi: float  # Schedule Performance Index = realizado / planejado (1.0 = no prazo)
    forecast_completion_week: int  # Semana projetada de conclusão
    drift_alerts: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
