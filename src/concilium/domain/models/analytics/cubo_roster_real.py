"""Cubo de Roster Real — ADR-174.

Irmão do ``CuboPoolInstancial`` (ADR-086) e do ``CuboEstoqueConsumivel``
(ADR-128 F6), na granularidade que o roster real (ADR-154/155/173) permite:
``instancia_id`` (indivíduo/ativo real — ``individuo_id``/``ativo_id``), nunca
o slot fungível do pool (``InstanciaRecurso.instancia_id``). Misturar as duas
noções de "instância" no mesmo cubo borraria a separação física/causal que é a
razão de existir do cubo ADR-086 — por isso este é um cubo novo, não uma
extensão.

Hierarquia (categoria > grupo > instância, confirmada com o usuário):
``categoria`` (``MAO_OBRA``/``EQUIPAMENTO``) > ``grupo_id`` (``funcao_id``/
``equip_id``) > ``instancia_id`` (``individuo_id``/``ativo_id``). Custo
direto/indireto/total são **medidas**, não dimensões — uma instância de MO
tem os dois valores simultaneamente, nunca um-ou-outro.

``custo_indireto`` é sempre ``0.0`` para ``categoria="EQUIPAMENTO"`` — não é
campo omitido, é medida presente e zerada (equipamento não tem análogo de
EPI/treinamento/exame/benefício, ADR-165 é conceito exclusivamente humano),
mantendo a célula uniforme entre categorias.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

CategoriaRosterReal = Literal["MAO_OBRA", "EQUIPAMENTO"]


@dataclass(frozen=True)
class CelulaRosterReal:
    """Grão atômico: custo de UMA instância real numa semana (ADR-174)."""

    categoria: CategoriaRosterReal
    grupo_id: str
    instancia_id: str
    semana_iso: str
    custo_direto: float
    custo_indireto: float
    custo_total: float


@dataclass(frozen=True)
class CuboRosterReal:
    """Container do cubo de roster real — células por instância×semana (ADR-174)."""

    projeto_id: str
    gerado_em: str
    celulas: tuple[CelulaRosterReal, ...] = field(default_factory=tuple)

    # ── Query primitives ──────────────────────────────────────────────────────
    def slice(
        self,
        *,
        categoria: CategoriaRosterReal | None = None,
        grupo_id: str | None = None,
        instancia_id: str | None = None,
        semana_iso: str | None = None,
    ) -> CuboRosterReal:
        """Filtra células por qualquer combinação de dimensões."""

        def keep(c: CelulaRosterReal) -> bool:
            return (
                (categoria is None or c.categoria == categoria)
                and (grupo_id is None or c.grupo_id == grupo_id)
                and (instancia_id is None or c.instancia_id == instancia_id)
                and (semana_iso is None or c.semana_iso == semana_iso)
            )

        return CuboRosterReal(
            projeto_id=self.projeto_id,
            gerado_em=self.gerado_em,
            celulas=tuple(c for c in self.celulas if keep(c)),
        )

    def group_by(self, *dims: str, measure: str = "custo_total") -> dict[tuple, float]:
        """Agrega ``measure`` por dimensões. measure ∈ custo_direto|custo_indireto|
        custo_total."""
        out: dict[tuple, float] = {}
        for c in self.celulas:
            key = tuple(getattr(c, d, "") for d in dims)
            out[key] = out.get(key, 0.0) + _measure_value(c, measure)
        return {k: round(v, 2) for k, v in out.items()}

    # ── Projeções ──────────────────────────────────────────────────────────────
    def custo_por_instancia(self, instancia_id: str) -> dict[str, float]:
        """{semana_iso: custo_total} para uma instância específica, em ordem de semana."""
        pares = [(c.semana_iso, c.custo_total) for c in self.celulas if c.instancia_id == instancia_id]
        return dict(sorted(pares, key=lambda p: p[0]))

    def custo_por_grupo(self) -> dict[str, float]:
        return {k[0]: v for k, v in self.group_by("grupo_id", measure="custo_total").items()}

    def custo_por_categoria(self) -> dict[str, float]:
        return {k[0]: v for k, v in self.group_by("categoria", measure="custo_total").items()}

    def custo_total_geral(self) -> float:
        return round(sum(c.custo_total for c in self.celulas), 2)


def _measure_value(c: CelulaRosterReal, measure: str) -> float:
    if measure in ("custo_direto", "custo_indireto", "custo_total"):
        return getattr(c, measure)
    return c.custo_total
