"""ResultadoConsolidadoProjeto — agregação financeira cross-escopo (ADR-031 §D8)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

StatusMargem = Literal["VERDE", "AMARELO", "VERMELHO"]


class BreakdownEscopo(BaseModel):
    """Contribuição individual de um escopo para o resultado consolidado."""

    model_config = ConfigDict(extra="ignore")

    escopo_id: str
    nome: str
    plano_id: str
    status_plano: str
    venda_com_bdi: float
    custo_total: float
    resultado_financeiro: float
    margem_pct: float
    status_margem: StatusMargem
    # Peso relativo deste escopo no total do projeto (venda_com_bdi / venda_total)
    peso_relativo: float = Field(ge=0, le=1)


class ResultadoConsolidadoProjeto(BaseModel):
    """Resultado financeiro agregado de todos os escopos incluídos (ADR-031 §D8).

    Calculado on-the-fly a partir dos canônicos dos planos aprovados (ou mais
    avançados). Não é persistido em nenhum canonical individual.
    """

    model_config = ConfigDict(extra="ignore")

    projeto_id: str
    # IDs dos escopos incluídos nesta consolidação
    escopos_incluidos: list[str]
    # IDs de escopos excluídos (sem plano aprovado/ativo ou resultado ausente)
    escopos_excluidos: list[str] = Field(default_factory=list)
    venda_total_com_bdi: float
    custo_total: float
    resultado_financeiro: float
    margem_pct: float  # resultado_financeiro / venda_total_com_bdi
    status_margem: StatusMargem
    # Breakdown por escopo
    breakdown: list[BreakdownEscopo] = Field(default_factory=list)
    # Avisos sobre estado parcial (ex.: escopos sem resultado ainda)
    avisos: list[str] = Field(default_factory=list)

    @classmethod
    def _status_for(cls, margem_pct: float) -> StatusMargem:
        if margem_pct >= 0.08:
            return "VERDE"
        if margem_pct >= 0.04:
            return "AMARELO"
        return "VERMELHO"

    @classmethod
    def calcular(
        cls,
        projeto_id: str,
        breakdown: list[BreakdownEscopo],
        escopos_excluidos: list[str] | None = None,
        avisos: list[str] | None = None,
    ) -> ResultadoConsolidadoProjeto:
        """Constrói o resultado consolidado a partir da lista de breakdowns."""
        venda_total = sum(b.venda_com_bdi for b in breakdown)
        custo_total = sum(b.custo_total for b in breakdown)
        resultado = venda_total - custo_total
        margem = resultado / venda_total if venda_total > 0 else 0.0

        # Atualiza pesos relativos
        itens = [
            b.model_copy(update={"peso_relativo": b.venda_com_bdi / venda_total if venda_total > 0 else 0.0})
            for b in breakdown
        ]

        return cls(
            projeto_id=projeto_id,
            escopos_incluidos=[b.escopo_id for b in itens],
            escopos_excluidos=escopos_excluidos or [],
            venda_total_com_bdi=round(venda_total, 2),
            custo_total=round(custo_total, 2),
            resultado_financeiro=round(resultado, 2),
            margem_pct=round(margem, 4),
            status_margem=cls._status_for(margem),
            breakdown=itens,
            avisos=avisos or [],
        )
