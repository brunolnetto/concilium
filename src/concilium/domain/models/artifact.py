"""ADR-018 — Typed Artifact System.

ArtifactEnvelope: envelope imutável com metadata + payload tipado.
Adotado por artefatos que cruzam fronteiras de camada ou estão sujeitos
a governança (Producao, CanonicalModel, Resultado, Observacao, etc.).

Não aplicado a: ValidacaoItem (ephemeral), configurações internas (Praticabilidade).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any, Generic, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T", bound=BaseModel)


class ArtifactState(StrEnum):
    DRAFT = "draft"  # criado, ainda não commitado
    COMMITTED = "committed"  # válido, imutável
    SUPERSEDED = "superseded"  # substituído por versão mais nova
    DEPRECATED = "deprecated"  # legível, não deve mais ser produzido
    REJECTED = "rejected"  # falhou na validação ou governança


class ArtifactKind(StrEnum):
    CANONICAL = "canonical"  # CanonicalModel snapshot por versão
    PRODUCAO = "producao"  # artefato de produtividade (ADR-007)
    OBSERVACAO = "observacao"  # observação de catálogo (ADR-017)
    PROPOSTA = "proposta"  # proposta de atualização (ADR-017)
    DECISAO = "decisao"  # log de decisão técnica (Skill 11)
    RESULTADO = "resultado"  # resultado financeiro (Skill 06)
    RELATORIO = "relatorio"  # relatório de saída (Skill 07)
    # ADR-023
    BDI_PERFIL_DIFF = "bdi_perfil_diff"  # diff entre versões de PerfilBdiProjeto
    # ADR-024
    CATALOG_SNAPSHOT = "catalog_snapshot"  # snapshot imutável de catálogo
    CATALOG_DIFF = "catalog_diff"  # diff entre snapshots consecutivos
    # ADR-025
    CATALOG_DRAFT = "catalog_draft"  # proposta de mutação (PROPOSE->COMMIT)
    # ADR-026
    RELATORIO_CRITICIDADE = "relatorio_criticidade"  # ranking Pareto (Skill 15)
    RELATORIO_SENSIBILIDADE = "relatorio_sensibilidade"  # levers de margem (Skill 16)
    RELATORIO_INTERVENCAO = "relatorio_intervencao"  # eixos de intervenção (Skill 17)
    RELATORIO_EXECUTIVO = "relatorio_executivo"  # bridge waterfall executivo (Skill 15)


class ArtifactRef(BaseModel):
    """Referência estável e imutável a uma versão específica de artefato."""

    model_config = ConfigDict(frozen=True)

    artifact_id: str
    version: str
    kind: ArtifactKind
    schema_name: str
    schema_version: str
    content_hash: str


class ArtifactMeta(BaseModel):
    """Metadados do envelope — separados do payload, indexáveis."""

    model_config = ConfigDict(frozen=True)

    artifact_id: str = Field(default_factory=lambda: str(uuid4()))
    version: str = "1.0.0"
    kind: ArtifactKind
    schema_name: str
    schema_version: str

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: str  # Skill ID ou nome da operação MCP
    trace_id: str | None = None  # compartilhado por toda a sessão Claude (D3)

    parent_refs: list[ArtifactRef] = Field(default_factory=list)
    state: ArtifactState = ArtifactState.DRAFT
    content_hash: str  # SHA-256 do payload JSON

    # ADR-024: snapshot do catálogo vigente no momento do run
    catalog_snapshot_id: str | None = None
    # ADR-023 §D6: versão do PerfilBdiProjeto usado neste run
    bdi_perfil_id: str | None = None
    # ADR-025 §D6: referências externas consultadas (ex: ["SICRO_2024_CE"])
    referencia_ids: list[str] = Field(default_factory=list)


class ArtifactEnvelope(BaseModel, Generic[T]):
    """Artefato imutável: metadata + payload tipado (ADR-018 §D1)."""

    model_config = ConfigDict(frozen=True)

    meta: ArtifactMeta
    payload: T

    def ref(self) -> ArtifactRef:
        return ArtifactRef(
            artifact_id=self.meta.artifact_id,
            version=self.meta.version,
            kind=self.meta.kind,
            schema_name=self.meta.schema_name,
            schema_version=self.meta.schema_version,
            content_hash=self.meta.content_hash,
        )

    @classmethod
    def create(
        cls,
        payload: T,
        kind: ArtifactKind,
        schema_name: str,
        schema_version: str,
        created_by: str,
        trace_id: str | None = None,
        parent_refs: list[ArtifactRef] | None = None,
        version: str = "1.0.0",
    ) -> ArtifactEnvelope[T]:
        if hasattr(payload, "model_dump_json"):
            payload_json = payload.model_dump_json()
        else:
            import json

            payload_json = json.dumps(payload, default=str, ensure_ascii=False)
        content_hash = sha256(payload_json.encode()).hexdigest()
        meta = ArtifactMeta(
            kind=kind,
            schema_name=schema_name,
            schema_version=schema_version,
            created_by=created_by,
            trace_id=trace_id,
            parent_refs=parent_refs or [],
            content_hash=content_hash,
            version=version,
        )
        return cls(meta=meta, payload=payload)


# ── Registry ──────────────────────────────────────────────────────────────────


class ConciliumArtifactRegistry:
    """Mapeia schema_name -> classe Pydantic para validação sem tipos hardcoded."""

    _schemas: dict[str, type[BaseModel]] = {}

    @classmethod
    def register(cls, name: str, model: type[BaseModel]) -> None:
        cls._schemas[name] = model

    @classmethod
    def validate(cls, schema_name: str, data: dict[str, Any]) -> BaseModel:
        model = cls._schemas.get(schema_name)
        if not model:
            raise ValueError(f"Schema desconhecido: '{schema_name}'. Registre com ConciliumArtifactRegistry.register()")
        return model.model_validate(data)

    @classmethod
    def known_schemas(cls) -> list[str]:
        return list(cls._schemas.keys())


def _register_defaults() -> None:
    from concilium.domain.models.project.observacao import (
        ObservacaoClasseRecurso,
        ObservacaoCPUAusente,
        ObservacaoCustoInsumo,
        ObservacaoProdutividade,
        PropostaAtualizacao,
    )
    from concilium.domain.models.catalog.producao import Producao

    ConciliumArtifactRegistry.register("Producao", Producao)
    ConciliumArtifactRegistry.register("ObservacaoProdutividade", ObservacaoProdutividade)
    ConciliumArtifactRegistry.register("ObservacaoCustoInsumo", ObservacaoCustoInsumo)
    ConciliumArtifactRegistry.register("ObservacaoClasseRecurso", ObservacaoClasseRecurso)
    ConciliumArtifactRegistry.register("ObservacaoCPUAusente", ObservacaoCPUAusente)
    ConciliumArtifactRegistry.register("PropostaAtualizacao", PropostaAtualizacao)


# Registra schemas padrão ao importar o módulo (lazy — CanonicalModel/Resultado
# são registrados pelos seus próprios módulos para evitar imports circulares)
_register_defaults()
