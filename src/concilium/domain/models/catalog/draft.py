"""ADR-025 — Política MCP: Governança de mutações de catálogo, tributação e referências.

CatalogDraft: ciclo PROPOSE -> HiL -> COMMIT com trilha de auditoria.
TaxProfile: perfil tributário por jurisdição/município.
CatalogMutationGuard: impede mutações durante execução de pipeline.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

# ── D1 — Permissões ───────────────────────────────────────────────────────


class CatalogPermission(StrEnum):
    READ = "read"  # qualquer agente autenticado (default)
    PROPOSE = "propose"  # cria draft; requer revisão HiL
    COMMIT = "commit"  # aplica draft aprovado; requer papel catalog_editor
    ADMIN = "admin"  # deleção, renomeação, schema; requer diretoria_operacoes


# ── D2 — Catalog Draft ───────────────────────────────────────────────────


class CatalogDraft(BaseModel):
    """Draft de mutação de catálogo em espera de aprovação HiL (ADR-025 §D2).

    Ciclo de vida: pending_review -> approved -> committed
                                 -> rejected
    """

    model_config = ConfigDict(extra="ignore")

    draft_id: str = Field(default_factory=lambda: str(uuid4()))
    catalog_name: str  # ex: "mendeslobo"
    entity_type: Literal["cpu", "insumo", "produtividade"]
    operation: Literal["upsert", "delete"]
    proposed_by: str
    proposed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: Literal["pending_review", "approved", "rejected", "committed"] = "pending_review"

    entity_before: dict | None = None  # None se criação nova
    entity_after: dict  # estado proposto
    diff_preview: str = ""  # resumo legível das mudanças

    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_notes: str | None = None

    commit_snapshot_id: str | None = None  # preenchido após commit (ADR-024 snapshot_id)

    def approve(self, reviewed_by: str, notes: str | None = None) -> CatalogDraft:
        return self.model_copy(
            update={
                "status": "approved",
                "reviewed_by": reviewed_by,
                "reviewed_at": datetime.now(UTC),
                "review_notes": notes,
            }
        )

    def reject(self, reviewed_by: str, notes: str | None = None) -> CatalogDraft:
        return self.model_copy(
            update={
                "status": "rejected",
                "reviewed_by": reviewed_by,
                "reviewed_at": datetime.now(UTC),
                "review_notes": notes,
            }
        )

    def commit(self, snapshot_id: str) -> CatalogDraft:
        if self.status != "approved":
            raise ValueError(f"Só é possível commitar drafts aprovados. Status atual: {self.status}")
        return self.model_copy(
            update={
                "status": "committed",
                "commit_snapshot_id": snapshot_id,
            }
        )


# ── D3 — Tax Profile ─────────────────────────────────────────────────────


class TaxProfile(BaseModel):
    """Perfil tributário de uma jurisdição/município (ADR-025 §D3).

    Fonte: config/jurisdicoes/{jurisdicao_id}.json + overrides municipais.
    Usado para pré-preencher o formulário HiL de criação de projeto (ADR-023 §D6).
    """

    model_config = ConfigDict(frozen=True)

    jurisdicao_id: str  # ex: "BR"
    municipio: str | None = None  # ex: "Minaçu/GO"
    iss_aliquota: float = Field(ge=0, le=0.05, description="ISS local; max legal 5%")
    regime_default: Literal["lucro_presumido", "simples_nacional", "lucro_real"]
    cofins: float = Field(ge=0, le=1)
    pis: float = Field(ge=0, le=1)
    cssl: float = Field(ge=0, le=1)
    ir: float = Field(ge=0, le=1)
    encargos_horistas: float = Field(ge=0, description="Ex: 1.777 = 177,7%")
    encargos_mensalistas: float = Field(ge=0, description="Ex: 1.060 = 106,0%")
    fonte: str = ""  # ex: "BR.json v2024"


class TaxProfileUpdateResult(BaseModel):
    """Resultado de update_tax_profile (ADR-025 §D4)."""

    model_config = ConfigDict(frozen=True)

    jurisdicao_id: str
    municipio: str | None
    campos_alterados: list[str]
    snapshot_id: str  # CatalogSnapshot gerado após a mudança
    projetos_notificados: list[str]  # projetos ativos que recebem BdiPerfilDiff
    aprovado_por: str
    alterado_em: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ── D4 — Referência imutável ──────────────────────────────────────────────


class ReferenciaItem(BaseModel):
    """Item de tabela de referência externa (SICRO / SINAPI / GoInfra)."""

    model_config = ConfigDict(frozen=True)

    codigo_referencia: str
    descricao: str
    unidade: str
    preco_unitario: float = Field(ge=0)
    data_referencia: str  # ISO date string ex: "2024-10-01"
    provedor: Literal["SICRO", "SINAPI", "GoInfra"]
    versao: str  # ex: "2024"
    fonte_url: str | None = None
    imutavel: bool = True  # marcado True na importação; nunca alterado


class ReferenciaImportResult(BaseModel):
    """Resultado de import_referencia (ADMIN) (ADR-025 §D3)."""

    model_config = ConfigDict(frozen=True)

    provedor: Literal["SICRO", "SINAPI", "GoInfra"]
    versao: str
    itens_importados: int
    snapshot_id: str  # CatalogSnapshot gerado
    versao_anterior_superseded: str | None  # versão marcada como superseded_by
    aprovado_por: str
    importado_em: datetime = Field(default_factory=lambda: datetime.now(UTC))
