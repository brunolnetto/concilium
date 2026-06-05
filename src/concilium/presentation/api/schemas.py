from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    # True = requires a project-local benchmark_reference.catalog baseline; no master fallback.
    use_strict_catalog_baseline: bool = False


class RerunProjectRequest(BaseModel):
    base_run_id: str | None = None
    base_version: str | None = None
    fork_version: bool = True
    skill_inputs_override: dict[str, dict[str, Any]] = Field(default_factory=dict)
    use_saved_overrides: bool = True
    use_mobilizacao_policy: bool = True
    use_strict_catalog_baseline: bool = False


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
    use_mobilizacao_policy: bool = True
    use_strict_catalog_baseline: bool = False
    catalogo_base_origem: str | None = None
    catalogo_base_hash: str | None = None
    skills_log: list[dict[str, Any]]
    skills_progress: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any]
    output_files: list[str]
    error: str | None = None


class RunStartResponse(BaseModel):
    project_id: str
    run_id: str
    status: str
    use_mobilizacao_policy: bool = True
    use_strict_catalog_baseline: bool = False


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


class SimulateCalendarioOperacionalRequest(BaseModel):
    """Override pontual de fator de calendário para simulação semanal."""

    fator_calendario_semanal: dict[str, float] = Field(default_factory=dict)


# ADR-062/065/066: typed contracts for versioned configuration endpoints


class RangeInput(BaseModel):
    min: float
    max: float


class ConfigVersionCreateRequest(BaseModel):
    """Base request for POST /api/{entity}/{id}/versions.

    Supports both payload shapes already used by UI:
    - {"motivo": "...", "fields": {...}, "_make_current": true}
    - {"motivo": "...", <fieldA>: ..., <fieldB>: ...}
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    motivo: str = Field(min_length=1)
    fields: dict[str, Any] | None = None
    make_current: bool | None = Field(default=None, alias="_make_current")

    def extract_fields(self) -> dict[str, Any]:
        """Return normalized fields regardless of request shape."""
        payload = self.model_dump(exclude_none=True, by_alias=True)
        explicit = payload.pop("fields", None)
        payload.pop("motivo", None)
        payload.pop("_make_current", None)
        if isinstance(explicit, dict):
            return explicit
        return payload


class PerfilVersionCreateRequest(ConfigVersionCreateRequest):
    faixa_margem_alvo: RangeInput | None = None
    faixa_margem_aceitavel: RangeInput | None = None
    razao_indireto_direto_alvo: RangeInput | None = None

    @model_validator(mode="after")
    def validate_ranges(self) -> "PerfilVersionCreateRequest":
        for label, faixa, lower, upper in (
            ("faixa_margem_alvo", self.faixa_margem_alvo, 0.0, 1.0),
            ("faixa_margem_aceitavel", self.faixa_margem_aceitavel, 0.0, 1.0),
            ("razao_indireto_direto_alvo", self.razao_indireto_direto_alvo, 0.0, 2.0),
        ):
            if faixa is None:
                continue
            if faixa.min > faixa.max:
                raise ValueError(f"{label}: min deve ser <= max")
            if faixa.min < lower or faixa.max > upper:
                raise ValueError(f"{label}: valores fora do intervalo permitido [{lower}, {upper}]")
        return self


class ContextoVersionCreateRequest(ConfigVersionCreateRequest):
    catalogo_id: str | None = None
    jurisdicao_id: str | None = None
    perfil_id: str | None = None
    referencia_id: str | None = None
    tema_id: str | None = None
    nome: str | None = None
    descricao: str | None = None


class TemaVersionCreateRequest(ConfigVersionCreateRequest):
    empresa: str | None = None
    perfil_exibicao: str | None = None
    cores: dict[str, str] | None = None
    fontes: dict[str, Any] | None = None


class JurisdicaoVersionCreateRequest(ConfigVersionCreateRequest):
    cpus: dict[str, Any] | None = None
    insumos: dict[str, Any] | None = None
    provedores_referencia: list[dict[str, Any]] | None = None


class ConfigEntityListResponse(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)


class ConfigEntityVersionsResponse(BaseModel):
    versions: list[dict[str, Any]] = Field(default_factory=list)
    perfil_id: str | None = None
    contexto_id: str | None = None
    tema_id: str | None = None
    jurisdicao_id: str | None = None


class ConfigVersionCreateResponse(BaseModel):
    version: str
    created_at: str | None = None
    created_by: str | None = None
    motivo: str | None = None
    model_config = ConfigDict(extra="allow")


class ConfigCompareResponse(BaseModel):
    entity_id: str
    subdir: str
    version_a: str
    version_b: str
    changed: dict[str, Any] = Field(default_factory=dict)
    unchanged: list[str] = Field(default_factory=list)
