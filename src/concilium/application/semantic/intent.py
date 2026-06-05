"""Modelos de intenção semântica — v1.0 (ADR-001).

Representa a intenção estruturada de um item de escopo do cliente,
extraída de texto bruto antes da resolução para CPU.

Invariantes:
- ``unit`` nunca vazio (raise SemanticParseError)
- ``domain`` == "other" requer missing_attributes populado
- ``dimensions`` são sempre estruturadas (nunca texto em qualifiers)
- ``raw_text`` sempre preservado intacto para rastreabilidade
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DomainType = Literal["earthwork", "pavement", "drainage", "structure", "other"]


class Dimension(BaseModel):
    """Atributo quantitativo explícito de um item de escopo."""

    model_config = ConfigDict(extra="forbid")

    name: str  # nome canônico: "thickness", "depth", "dmt", "pipe_diameter"
    value: float
    unit: str  # unidade canônica normalizada: "cm", "m", "mm", "m3"


class ExtractionConfidence(BaseModel):
    """Confiança por campo extraído. Explícito — nunca implícito."""

    model_config = ConfigDict(extra="ignore")

    domain: float = Field(ge=0.0, le=1.0)
    activity_type: float = Field(ge=0.0, le=1.0)
    unit: float = Field(ge=0.0, le=1.0)
    dimensions: float = Field(ge=0.0, le=1.0)
    materials: float = Field(ge=0.0, le=1.0, default=0.0)


class SemanticIntent(BaseModel):
    """Representação canônica de um item de escopo do cliente.

    É uma *hipótese estruturada de intenção* — não é verdade absoluta.
    Gaps explícitos (None) são preferíveis a inferências silenciosas.

    Produzida pelo SemanticExtractor. Consumida pelo Resolver.
    """

    model_config = ConfigDict(extra="forbid")

    # Origem
    raw_text: str
    scope_item_id: str  # ID gerado pelo chamador para rastreabilidade

    # Classificação
    domain: DomainType
    activity_type: str  # vocab controlado: "cut_fill", "embankment_compaction", …

    # Atributos físicos
    unit: str  # normalizado: "m2", "m3", "m", "un", "ton"
    dimensions: list[Dimension] = Field(default_factory=list)
    qualifiers: list[str] = Field(default_factory=list)

    # Composição material
    materials: list[str] = Field(default_factory=list)  # IDs canônicos
    method: str | None = None  # "mechanized", "manual", "mixed"

    # Contexto de execução
    context: dict[str, str | float | bool] = Field(default_factory=dict)
    # ex: {"location_type": "urban", "access": "restricted", "soil_class": "C"}

    # Qualidade da extração
    extraction_confidence: ExtractionConfidence

    # Atributos ausentes explícitos
    missing_attributes: list[str] = Field(default_factory=list)

    # Sinaliza se passou por LLM fallback (deve ser auditado)
    used_llm_fallback: bool = False

    def dimension_value(self, name: str) -> float | None:
        """Retorna o valor da dimensão com o nome canônico dado, ou None."""
        for d in self.dimensions:
            if d.name == name:
                return d.value
        return None

    def has_dimension(self, name: str) -> bool:
        """Verdadeiro se dimensions contém o nome canônico dado."""
        return any(d.name == name for d in self.dimensions)


class SemanticParseError(Exception):
    """Falha ao construir SemanticIntent válido.

    Propagada explicitamente — nunca silenciada.
    Falha em qualquer invariante obrigatório gera esta exceção.

    Attributes:
        raw_text: Texto original de entrada (truncado a 120 chars).
        reason:   Código curto da causa (ex. "missing_unit").
        missing:  Lista de campos obrigatórios ausentes.
    """

    CODES = frozenset(
        {
            "missing_unit",
            "ambiguous_activity",
            "dimension_in_freetext",
            "unsupported_category",
            "conflicting_dimensions",
            "domain_other_no_missing",
        }
    )

    def __init__(
        self,
        raw_text: str,
        reason: str,
        missing: list[str] | None = None,
    ) -> None:
        self.raw_text = raw_text[:120]
        self.reason = reason
        self.missing = missing or []
        super().__init__(
            f"SemanticParseError[{reason}]: input='{self.raw_text}'"
            + (f" | missing={self.missing}" if self.missing else "")
        )


__all__ = [
    "DomainType",
    "Dimension",
    "ExtractionConfidence",
    "SemanticIntent",
    "SemanticParseError",
]
