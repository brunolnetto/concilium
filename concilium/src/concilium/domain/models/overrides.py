"""ADR-040 — Schemas de Override de Catálogo a nível de Projeto.

Permitem calibrar preços e parâmetros do catálogo master para o contexto
específico de um projeto, sem modificar o catálogo compartilhado.

Estrutura de arquivo por projeto:
    projetos/{uuid}/overrides/
    ├── insumos_override.json   — dict[codigo, InsumoOverride]
    ├── cpus_override.json      — dict[codigo, CPUOverride]
    └── bdi_override.json       — BDIOverride (objeto único)
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class InsumoOverride(BaseModel):
    """Override de preço e/ou atributos de um insumo específico no contexto do projeto.

    O campo `preco_calibrado` sobrepõe toda a cascata de resolução (ADR-040 §D2),
    incluindo preços regionais SICRO e o master base.
    """

    model_config = ConfigDict(extra="forbid")

    codigo: str = Field(description="Código do insumo no catálogo master.")
    preco_calibrado: float = Field(ge=0, description="Preço efetivo para este projeto (R$/unidade).")
    motivo: str = Field(description="Justificativa técnica ou comercial para o override.")
    aprovado_por: str = Field(description="Responsável pela aprovação do override.")
    aprovado_em: datetime = Field(description="Timestamp de aprovação.")
    valido_ate: date | None = Field(
        default=None,
        description="Data de expiração do override. None = válido até aprovação de novo override.",
    )
    fonte_cotacao: str | None = Field(
        default=None,
        description="Referência da cotação (ex.: 'NF 2024/0042 — Fornecedor X').",
    )


class CPUOverride(BaseModel):
    """Override de parâmetros de uma CPU específica no contexto do projeto.

    Permite ajustar produtividade, permanência e composição sem modificar o
    catálogo master. Útil para calibração baseada em dados de campo.
    """

    model_config = ConfigDict(extra="forbid")

    codigo: str = Field(description="Código da CPU no catálogo master.")
    producao_horaria_calibrada: float | None = Field(
        default=None,
        gt=0,
        description="Produtividade real medida em campo (unidade/h).",
    )
    permanencia_meses_calibrada: float | None = Field(
        default=None,
        gt=0,
        description="Permanência de equipe efetiva (meses), se diferente do padrão da CPU.",
    )
    motivo: str = Field(description="Justificativa para o override.")
    aprovado_por: str
    aprovado_em: datetime
    observacoes: str | None = None


class BDIOverride(BaseModel):
    """Override das alíquotas de BDI para o projeto inteiro.

    Sobrepõe tanto o DEFAULT_BDI_TABELA quanto o motor_tributario_bdi da jurisdição.
    Deve ser usado apenas quando há decisão explícita da diretoria (ex.: regime tributário
    especial negociado para o contrato).
    """

    model_config = ConfigDict(extra="forbid")

    material: float | None = Field(default=None, ge=0, le=0.50)
    diesel: float | None = Field(default=None, ge=0, le=0.50)
    mao_obra: float | None = Field(default=None, ge=0, le=0.50)
    equipamentos: float | None = Field(default=None, ge=0, le=0.50)
    motivo: str = Field(description="Justificativa para o override de BDI.")
    aprovado_por: str
    aprovado_em: datetime

    def como_dict_bdi(self) -> dict[str, float]:
        """Retorna apenas as categorias com valor definido, no formato aceito pela Skill 04."""
        return {
            k: v
            for k, v in {
                "material": self.material,
                "diesel": self.diesel,
                "mao_obra": self.mao_obra,
                "equipamentos": self.equipamentos,
            }.items()
            if v is not None
        }


# ── Tipo agrupado para carga pelo LifecycleCoordinator ───────────────────────


class ProjectOverrides(BaseModel):
    """Container de todos os overrides carregados para um projeto."""

    model_config = ConfigDict(extra="forbid")

    insumos: dict[str, Any] = Field(
        default_factory=dict,
        description="dict[codigo, InsumoOverride] — raw para compatibilidade com resolver_preco.",
    )
    cpus: dict[str, CPUOverride] = Field(default_factory=dict)
    bdi: BDIOverride | None = None
