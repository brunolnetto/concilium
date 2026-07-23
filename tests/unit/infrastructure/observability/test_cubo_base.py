"""Testes para a base genérica Cubo (ADR-147, migração de Gold para cubos).

Mesmo padrão de CuboAnalitico (domain/models/analytics/cubo_analitico.py,
ADR-087): tupla imutável de células + .slice()/.query() derivam qualquer
projeção sob demanda. Diferença deliberada: aqui as medidas são heterogêneas
(percentil, contagem, média) — .query() usa DuckDB como motor de agregação
genérico por dimensão, em vez de soma pura em Python.

Testado com uma célula de exemplo (_CelulaTeste/_CuboTeste) — os 4 cubos reais
(CuboSpans/CuboLogs/CuboMetricas/CuboToolInvocations) têm seus próprios testes
de mapeamento Silver→célula; aqui o alvo é só o mecanismo slice/query.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import pytest

from concilium.infrastructure.observability.cubo_base import Cubo


@dataclass(frozen=True)
class _CelulaTeste:
    date: str
    categoria: str | None
    valor: int


class _CuboTeste(Cubo[_CelulaTeste]):
    _sql_types: ClassVar[dict[str, str]] = {"date": "TEXT", "categoria": "TEXT", "valor": "INTEGER"}


def _cubo(*celulas: _CelulaTeste) -> _CuboTeste:
    return _CuboTeste(celulas=tuple(celulas))


class TestSlice:
    def test_filters_by_exact_match(self):
        cubo = _cubo(
            _CelulaTeste("2026-07-21", "a", 1),
            _CelulaTeste("2026-07-21", "b", 2),
        )

        result = cubo.slice(categoria="a")

        assert len(result.celulas) == 1
        assert result.celulas[0].categoria == "a"

    def test_multiple_filters_are_conjunctive(self):
        cubo = _cubo(
            _CelulaTeste("2026-07-21", "a", 1),
            _CelulaTeste("2026-07-22", "a", 2),
        )

        result = cubo.slice(date="2026-07-21", categoria="a")

        assert len(result.celulas) == 1

    def test_none_valued_filters_are_ignored(self):
        """slice(categoria=maybe_none) não deve exigir um `if` externo do chamador."""
        cubo = _cubo(_CelulaTeste("2026-07-21", "a", 1), _CelulaTeste("2026-07-21", "b", 2))

        result = cubo.slice(categoria=None)

        assert len(result.celulas) == 2

    def test_returns_same_concrete_type(self):
        cubo = _cubo(_CelulaTeste("2026-07-21", "a", 1))

        result = cubo.slice(categoria="a")

        assert isinstance(result, _CuboTeste)

    def test_no_match_returns_empty(self):
        cubo = _cubo(_CelulaTeste("2026-07-21", "a", 1))

        result = cubo.slice(categoria="z")

        assert result.celulas == ()


class TestQuery:
    def test_empty_cubo_returns_empty_list(self):
        cubo = _cubo()

        assert cubo.query(group_by=["categoria"], aggs={"n": "count(*)"}) == []

    def test_groups_and_aggregates(self):
        cubo = _cubo(
            _CelulaTeste("2026-07-21", "a", 10),
            _CelulaTeste("2026-07-21", "a", 20),
            _CelulaTeste("2026-07-21", "b", 5),
        )

        rows = cubo.query(group_by=["categoria"], aggs={"total": "sum(valor)", "n": "count(*)"})

        by_cat = {r["categoria"]: r for r in rows}
        assert by_cat["a"]["total"] == 30
        assert by_cat["a"]["n"] == 2
        assert by_cat["b"]["total"] == 5
        assert by_cat["b"]["n"] == 1

    def test_where_filters_before_grouping(self):
        cubo = _cubo(
            _CelulaTeste("2026-07-21", "a", 10),
            _CelulaTeste("2026-07-21", None, 999),
        )

        rows = cubo.query(group_by=["categoria"], aggs={"n": "count(*)"}, where="categoria IS NOT NULL")

        assert len(rows) == 1
        assert rows[0]["categoria"] == "a"

    def test_order_by_is_respected(self):
        cubo = _cubo(
            _CelulaTeste("2026-07-21", "a", 1),
            _CelulaTeste("2026-07-21", "b", 100),
        )

        rows = cubo.query(group_by=["categoria"], aggs={"total": "sum(valor)"}, order_by="total DESC")

        assert [r["categoria"] for r in rows] == ["b", "a"]

    def test_group_by_expression_with_alias(self):
        """COALESCE(categoria, 'unknown') AS categoria — mesmo padrão de
        build_fallback_rate_por_skill hoje, generalizado via GROUP BY ALL."""
        cubo = _cubo(
            _CelulaTeste("2026-07-21", None, 1),
            _CelulaTeste("2026-07-21", "a", 2),
        )

        rows = cubo.query(group_by=["date", "COALESCE(categoria, 'unknown') AS categoria"], aggs={"n": "count(*)"})

        by_cat = {r["categoria"]: r["n"] for r in rows}
        assert by_cat == {"unknown": 1, "a": 1}

    def test_percentile_aggregation(self):
        """A motivação original de usar DuckDB: percentis não são soma.

        Sintaxe DuckDB é a ordered-set aggregate PERCENTILE_CONT(frac) WITHIN GROUP
        (ORDER BY col) — não a forma posicional percentile_cont(col, frac) de outros
        dialetos, que não existe aqui.
        """
        cubo = _cubo(
            _CelulaTeste("2026-07-21", "a", 100),
            _CelulaTeste("2026-07-21", "a", 200),
            _CelulaTeste("2026-07-21", "a", 300),
        )

        rows = cubo.query(
            group_by=["categoria"], aggs={"p50": "PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY valor)"}
        )

        assert rows[0]["p50"] == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
