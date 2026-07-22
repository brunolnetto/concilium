"""Base genérica para os cubos de observabilidade Gold (ADR-147).

Mesmo padrão de CuboAnalitico (domain/models/analytics/cubo_analitico.py,
ADR-087): tupla imutável de células no grão atômico + .slice()/.query()
derivam qualquer projeção sob demanda, em vez de pré-computar relatórios
(como GoldAggregator faz hoje com build_sli_diario/build_fallback_rate_por_skill).

Diferença deliberada de CuboAnalitico: lá, uma única medida (valor_rs) cobre
todas as categorias de custo e group_by() só soma, em Python puro. Aqui as
medidas são heterogêneas (percentil, contagem, valor livre) — GoldAggregator
já usa DuckDB para percentis hoje; .query() generaliza esse mesmo motor por
dimensão, em vez de fixo em (date, skill_id).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, ClassVar, Generic, TypeVar

CelulaT = TypeVar("CelulaT")


@dataclass(frozen=True)
class Cubo(Generic[CelulaT]):
    """Tupla imutável de células. Subclasses declaram `_sql_types` (coluna → tipo DuckDB)."""

    celulas: tuple[CelulaT, ...]

    _sql_types: ClassVar[dict[str, str]] = {}

    def slice(self, **filtros: Any) -> Cubo[CelulaT]:
        """Filtra células por igualdade exata. Filtros com valor None são ignorados —
        permite `cubo.slice(project_id=maybe_none)` sem `if` externo no chamador."""
        ativos = {k: v for k, v in filtros.items() if v is not None}

        def match(c: CelulaT) -> bool:
            return all(getattr(c, k) == v for k, v in ativos.items())

        return type(self)(celulas=tuple(c for c in self.celulas if match(c)))

    def query(
        self,
        group_by: list[str],
        aggs: dict[str, str],
        where: str | None = None,
        order_by: str | None = None,
    ) -> list[dict[str, Any]]:
        """Agrega células via DuckDB.

        Args:
            group_by: colunas ou expressões com alias, usando exatamente " AS " maiúsculo
                (ex.: "COALESCE(skill_id, 'unknown') AS skill_id") — usado para extrair o
                nome da coluna de saída. Usa GROUP BY ALL internamente — DuckDB agrupa por
                todo item do SELECT que não é agregação, então expressões com alias
                funcionam sem repetir a expressão inteira no GROUP BY.
            aggs: {alias: expressão_sql} — ex. {"p95_ms": "percentile_cont(duration_ms, 0.95)"}.
            where: filtro SQL aplicado antes do agrupamento (ex.: "skill_id IS NOT NULL").
            order_by: cláusula ORDER BY completa (ex.: "fallback_rate DESC NULLS LAST").
        """
        import duckdb

        if not self.celulas:
            return []

        cols = [f.name for f in fields(self.celulas[0])]
        col_defs = ", ".join(f"{c} {self._sql_types.get(c, 'TEXT')}" for c in cols)
        con = duckdb.connect(":memory:")
        con.execute(f"CREATE TABLE cells ({col_defs})")

        rows = [tuple(getattr(c, col) for col in cols) for c in self.celulas]
        placeholders = ", ".join("?" for _ in cols)
        con.executemany(f"INSERT INTO cells VALUES ({placeholders})", rows)

        select_list = ", ".join([*group_by, *(f"{expr} AS {alias}" for alias, expr in aggs.items())])
        sql = f"SELECT {select_list} FROM cells"
        if where:
            sql += f" WHERE {where}"
        sql += " GROUP BY ALL"
        if order_by:
            sql += f" ORDER BY {order_by}"

        result = con.execute(sql).fetchall()
        # group_by com alias usa exatamente " AS " (maiúsculo) — ver docstring.
        out_cols = [c.split(" AS ")[-1].strip() if " AS " in c else c for c in group_by]
        out_cols = [*out_cols, *aggs.keys()]
        return [dict(zip(out_cols, row, strict=True)) for row in result]
