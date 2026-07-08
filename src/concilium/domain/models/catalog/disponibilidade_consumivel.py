"""ADR-128 — Disponibilidade de Recursos Consumíveis (estoque, taxa de reabastecimento, lead time).

Modela a restrição *opcional* de disponibilidade de recursos consumíveis (diesel/combustível,
material) usada como entrada do motor RCPSP (`concilium.application.scheduling`). O opt-in é
`Insumo.disponibilidade: DisponibilidadeConsumivel | None = None` (`catalogo.py`) — ausência de
uma instância (`disponibilidade=None`) equivale a disponibilidade irrestrita, preservando o
comportamento histórico do sistema sem qualquer mudança (ADR-128 D1, D2).

Atenção: uma vez que `DisponibilidadeConsumivel` É instanciada, seus defaults NÃO significam
"irrestrito" — `estoque_inicial=0.0` é estoque vazio e `taxa_reabastecimento_max=None` é tratada
como 0.0 pelo motor (sem reabastecimento), o que pode tornar qualquer consumo inviável. A
representação de "sem limite" é a ausência do objeto, não os defaults dos seus campos.

`parse_prazo_entrega` implementa o pré-requisito de normalização descrito na ADR-128 §D1:
`AtributosInsumo.prazo_entrega` é hoje texto livre (`"Imediato"`, `"15 dias"`, ...), não um
número — não pode alimentar `lead_time_reabastecimento_dias: float` sem essa etapa.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PRAZO_IMEDIATO_RE = re.compile(r"imediat", re.IGNORECASE)
_PRAZO_DIAS_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*dias?", re.IGNORECASE)


@dataclass
class DisponibilidadeConsumivel:
    """Estoque/capacidade de um recurso consumível (ADR-128 D1).

    Todos os campos são opcionais — a ausência de valor representa "não modelado", não
    zero. `estoque_inicial` é a única exceção: seu default `0.0` é um valor concreto
    (estoque vazio), não "sem limite".

    Nota de implementação: a ADR descreve os campos sem valor default para
    `capacidade_armazenamento`/`taxa_reabastecimento_max`/`lead_time_reabastecimento_dias`,
    o que violaria a ordenação de campos de dataclass (não-default após default). Como a
    própria decisão os trata como opcionais, aqui todos recebem default `None` exceto
    `estoque_inicial`.
    """

    capacidade_armazenamento: float | None = None
    estoque_inicial: float = 0.0
    taxa_reabastecimento_max: float | None = None
    lead_time_reabastecimento_dias: float | None = None

    def __post_init__(self) -> None:
        if self.capacidade_armazenamento is not None and self.capacidade_armazenamento < 0:
            raise ValueError(f"capacidade_armazenamento must be >= 0, got {self.capacidade_armazenamento}")
        if self.estoque_inicial < 0:
            raise ValueError(f"estoque_inicial must be >= 0, got {self.estoque_inicial}")
        if self.taxa_reabastecimento_max is not None and self.taxa_reabastecimento_max < 0:
            raise ValueError(f"taxa_reabastecimento_max must be >= 0, got {self.taxa_reabastecimento_max}")
        if self.lead_time_reabastecimento_dias is not None and self.lead_time_reabastecimento_dias < 0:
            raise ValueError(
                f"lead_time_reabastecimento_dias must be >= 0, got {self.lead_time_reabastecimento_dias}"
            )
        if self.capacidade_armazenamento is not None and self.estoque_inicial > self.capacidade_armazenamento:
            raise ValueError(
                f"estoque_inicial ({self.estoque_inicial}) must be <= capacidade_armazenamento "
                f"({self.capacidade_armazenamento})"
            )

    @classmethod
    def from_prazo_entrega(
        cls,
        prazo_entrega: str | None,
        *,
        capacidade_armazenamento: float | None = None,
        estoque_inicial: float = 0.0,
        taxa_reabastecimento_max: float | None = None,
    ) -> DisponibilidadeConsumivel:
        """Constrói a partir de `AtributosInsumo.prazo_entrega` (ADR-128 §D1).

        Reaproveita o campo de catálogo já existente como fonte de
        `lead_time_reabastecimento_dias`, em vez de introduzir um campo numérico
        duplicado — via `parse_prazo_entrega` (normalização texto livre → dias).
        """
        return cls(
            capacidade_armazenamento=capacidade_armazenamento,
            estoque_inicial=estoque_inicial,
            taxa_reabastecimento_max=taxa_reabastecimento_max,
            lead_time_reabastecimento_dias=parse_prazo_entrega(prazo_entrega),
        )


def parse_prazo_entrega(texto: str | None) -> float | None:
    """Normaliza `AtributosInsumo.prazo_entrega` (texto livre) para dias numéricos (ADR-128 F3).

    Regras, calibradas pelos valores reais hoje presentes no catálogo:
      - `None` ou string vazia/em branco → `None` (sem dado)
      - contém "imediat[o]" (case-insensitive) → `0.0`
      - contém "N dia(s)" (aceita vírgula decimal, ex.: "2,5 dias") → `N` como `float`
      - qualquer outro texto não reconhecido → `None` (ignorado silenciosamente, sem
        lançar exceção — dado de catálogo em texto livre é inerentemente heterogêneo)
    """
    if texto is None:
        return None
    texto_norm = texto.strip()
    if not texto_norm:
        return None
    if _PRAZO_IMEDIATO_RE.search(texto_norm):
        return 0.0
    match = _PRAZO_DIAS_RE.search(texto_norm)
    if match:
        return float(match.group(1).replace(",", "."))
    return None
