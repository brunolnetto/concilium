"""Schemas Pydantic e tipos para ferramentas MCP (ADR-025/ADR-031)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class TaxProfileSchema(BaseModel):
    jurisdicao_id: str
    municipio: str | None = None
    iss_aliquota: float
    regime_default: str
    cofins: float
    pis: float
    cssl: float
    ir: float
    encargos_horistas: float
    encargos_mensalistas: float
    fonte: str


class CatalogDraftSchema(BaseModel):
    draft_id: str
    status: str
    entity_type: str
    catalog_name: str
    diff_preview: str
    proximos_passos: str


class ReplanSimResult(BaseModel):
    project_id: str
    tipo: str
    parametros_aplicados: dict[str, Any]
    persisted: bool = False
    baseline: dict[str, Any]
    simulado: dict[str, Any]
    delta: dict[str, str]
    nota: str


class ResumoProjetoSchema(BaseModel):
    project_id: str
    venda_total_com_bdi: float
    custo_total: float
    resultado_financeiro: float
    margem_pct: float
    status_margem: str
    breakdown_escopos: list[dict[str, Any]]
    avisos: list[str]
