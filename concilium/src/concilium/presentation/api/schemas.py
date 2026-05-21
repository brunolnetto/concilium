from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EapItemIn(BaseModel):
    item_id: str
    ordem: int
    cpu_id: str
    descricao: str
    unidade: str
    quantitativo: float


class CreateProjectRequest(BaseModel):
    nome: str | None = None
    contexto_id: str = "mendeslobo"
    benchmark_slug: str | None = None
    referencia_path: str | None = None
    tipo_obra: str = "terraplenagem"
    localizacao: str = "Brasil"
    coordenadas_lat: float = 0.0
    coordenadas_lng: float = 0.0
    data_inicio: str = "2026-01-01"
    data_termino: str = "2026-12-31"
    dias_semana: int = 6
    horas_dia: int = 8
    eap: list[EapItemIn] = Field(default_factory=list)


class CreateProjectResponse(BaseModel):
    project_id: str
    nome: str
    contexto_id: str
    current_version: str
    tipo_projeto: str = "hot_project"
    status_eap: str = "ATIVO"
    benchmark_slug: str | None = None
    benchmark_reference_file: str | None = None


class RunProjectRequest(BaseModel):
    base_version: str | None = None
    fork_version: bool = False
    skill_inputs_override: dict[str, dict[str, Any]] = Field(default_factory=dict)
    use_saved_overrides: bool = True
    # ADR-054 §9.1: independent toggle for WMP policy injection.
    # True (default) = inject mobilizacao_policy_override.json into Skill 04.
    # False = skip WMP even if the file exists (allows reverting to explicit allocation).
    use_mobilizacao_policy: bool = True


class RerunProjectRequest(BaseModel):
    base_run_id: str | None = None
    base_version: str | None = None
    fork_version: bool = True
    skill_inputs_override: dict[str, dict[str, Any]] = Field(default_factory=dict)
    use_saved_overrides: bool = True


class ForkVersionRequest(BaseModel):
    actor: str | None = None


class OverrideUpsertRequest(BaseModel):
    skill_id: str
    inputs: dict[str, Any]


class CompareRequest(BaseModel):
    left_version: str
    right_version: str


class RunProjectResponse(BaseModel):
    project_id: str
    run_id: str
    version: str
    status: str
    requested_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    base_version: str | None = None
    fork_version: bool = False
    skills_log: list[dict[str, Any]]
    skills_progress: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any]
    output_files: list[str]
    error: str | None = None


class RunStartResponse(BaseModel):
    project_id: str
    run_id: str
    status: str


# ADR-054: Workforce Mobilization Policy API schemas


class MobilizacaoPolicyIn(BaseModel):
    """API input for a workforce mobilization policy."""

    n_inicial: int = Field(ge=1)
    n_maximo: int = Field(ge=1)
    taxa_mobilizacao: float = Field(gt=0)
    taxa_desmobilizacao: float = Field(default=0.0, ge=0)
    semanas_plateau: int | None = Field(default=None, ge=0)


class MobilizacaoPolicyUpsertRequest(BaseModel):
    item_id: str
    policy: MobilizacaoPolicyIn


class DeliverablesConfigRequest(BaseModel):
    """PUT body for deliverables configuration."""

    outputs: dict[str, bool] = Field(default_factory=dict)


class SimulateRequest(BaseModel):
    """Request body for the stateless simulate endpoint."""

    item_id: str
    policy: MobilizacaoPolicyIn
    quantitativo: float = Field(gt=0)
    producao_horaria: float = Field(ge=0)
    dias_semana: int = Field(default=6, ge=1, le=7)
    horas_dia: int = Field(default=8, ge=1, le=24)
    semana_inicio: str | None = Field(
        default=None,
        description="ISO week key 'AAAA-Www' — anchors simulation to calendar for praticabilidade lookup.",
    )
    prat_semanal: dict[str, float] = Field(
        default_factory=dict,
        description="Practicability factors by ISO week. Overrides project praticabilidade for this simulation.",
    )
