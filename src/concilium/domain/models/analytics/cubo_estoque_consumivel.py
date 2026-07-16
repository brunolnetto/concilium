"""Cubo de Estoque Consumível — ADR-128 F6.

Irmão do ``CuboPoolInstancial`` (ADR-086), na granularidade que o dado de consumíveis
permite: ``resource_id`` (não há instância/contrato numerado — consumíveis são fluxo/
estoque, não unidades reutilizáveis discretas).

``estado`` aqui é **saúde de estoque** (``normal``/``deficit``/``overflow``), não
**ocupação física** (``prod``/``idle``/``off``, como em pool) — uma divergência
deliberada: o F5 já move as atividades para sua posição FINAL pós-reparo, sem persistir
"quais semanas eram a posição original vs. atrasada" (só a contagem agregada
``delay_weeks`` sobrevive em ``EstoqueDelayCanonical``). Um estado "semana atrasada" não
seria reconstruível honestamente a partir só do canônico — por isso a causa (qual
atividade, quantas semanas) permanece exclusivamente em ``Cronograma.estoque_delays``,
nunca duplicada aqui.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

EstadoEstoque = Literal["normal", "deficit", "overflow"]


@dataclass(frozen=True)
class CelulaEstoqueConsumivel:
    """Grão atômico físico: nível de estoque de um recurso numa semana (ADR-128 F6)."""

    resource_id: str
    semana_iso: str
    estado: EstadoEstoque
    estoque_nivel: float
    consumo: float = 0.0
    producao: float = 0.0
    reabastecimento_externo: float = 0.0
    overflow: float = 0.0

    @property
    def fluxo_liquido(self) -> float:
        return round(self.producao + self.reabastecimento_externo - self.consumo, 2)


@dataclass(frozen=True)
class CuboEstoqueConsumivel:
    """Container do cubo de estoque — células físicas (ADR-128 F6)."""

    projeto_id: str
    gerado_em: str
    celulas: tuple[CelulaEstoqueConsumivel, ...] = field(default_factory=tuple)

    # ── Query primitives ──────────────────────────────────────────────────────
    def slice(
        self,
        *,
        resource_id: str | None = None,
        estado: EstadoEstoque | None = None,
        semana_iso: str | None = None,
    ) -> CuboEstoqueConsumivel:
        """Filtra células por qualquer combinação de dimensões."""

        def keep(c: CelulaEstoqueConsumivel) -> bool:
            return (
                (resource_id is None or c.resource_id == resource_id)
                and (estado is None or c.estado == estado)
                and (semana_iso is None or c.semana_iso == semana_iso)
            )

        return CuboEstoqueConsumivel(
            projeto_id=self.projeto_id,
            gerado_em=self.gerado_em,
            celulas=tuple(c for c in self.celulas if keep(c)),
        )

    def group_by(self, *dims: str, measure: str = "estoque_nivel") -> dict[tuple, float]:
        """Agrega ``measure`` por dimensões. measure ∈ estoque_nivel|consumo|producao|
        reabastecimento_externo|overflow|fluxo_liquido."""
        out: dict[tuple, float] = {}
        for c in self.celulas:
            key = tuple(getattr(c, d, "") for d in dims)
            out[key] = out.get(key, 0.0) + _measure_value(c, measure)
        return {k: round(v, 2) for k, v in out.items()}

    # ── Projeções ──────────────────────────────────────────────────────────────
    def estoque_por_semana(self, resource_id: str) -> dict[str, float]:
        """{semana_iso: nivel} para um recurso específico, em ordem de semana."""
        pares = [(c.semana_iso, c.estoque_nivel) for c in self.celulas if c.resource_id == resource_id]
        return dict(sorted(pares, key=lambda p: p[0]))

    def semanas_por_estado(self) -> dict[str, int]:
        out = {"normal": 0, "deficit": 0, "overflow": 0}
        for c in self.celulas:
            out[c.estado] += 1
        return out

    def overflow_total(self) -> float:
        return round(sum(c.overflow for c in self.celulas), 2)

    def consumo_total(self) -> float:
        return round(sum(c.consumo for c in self.celulas), 2)

    def producao_total(self) -> float:
        return round(sum(c.producao for c in self.celulas), 2)


def _measure_value(c: CelulaEstoqueConsumivel, measure: str) -> float:
    if measure == "fluxo_liquido":
        return c.fluxo_liquido
    if measure in ("estoque_nivel", "consumo", "producao", "reabastecimento_externo", "overflow"):
        return getattr(c, measure)
    return c.estoque_nivel
