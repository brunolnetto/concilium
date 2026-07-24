"""Tests for domain/models/analytics/cubo_estoque_consumivel.py (ADR-128 F6)."""

from __future__ import annotations

from concilium.domain.models.analytics.cubo_estoque_consumivel import (
    CelulaEstoqueConsumivel,
    CuboEstoqueConsumivel,
)


def _make_celula(
    resource_id="MA-DIESEL-TESTE",
    semana_iso="2026-W01",
    estado="normal",
    estoque_nivel=100.0,
    consumo=40.0,
    producao=0.0,
    reabastecimento_externo=10.0,
    overflow=0.0,
):
    return CelulaEstoqueConsumivel(
        resource_id=resource_id,
        semana_iso=semana_iso,
        estado=estado,
        estoque_nivel=estoque_nivel,
        consumo=consumo,
        producao=producao,
        reabastecimento_externo=reabastecimento_externo,
        overflow=overflow,
    )


def _make_cubo(celulas):
    return CuboEstoqueConsumivel(projeto_id="proj-1", gerado_em="2026-01-01", celulas=tuple(celulas))


class TestCelulaEstoqueConsumivel:
    def test_fluxo_liquido(self):
        c = _make_celula(producao=20.0, reabastecimento_externo=10.0, consumo=40.0)
        assert c.fluxo_liquido == -10.0

    def test_fluxo_liquido_positivo(self):
        c = _make_celula(producao=50.0, reabastecimento_externo=10.0, consumo=40.0)
        assert c.fluxo_liquido == 20.0


class TestCuboEstoqueConsumivel:
    def test_slice_by_resource_id(self):
        cubo = _make_cubo(
            [
                _make_celula(resource_id="A", semana_iso="2026-W01"),
                _make_celula(resource_id="B", semana_iso="2026-W01"),
            ]
        )
        sliced = cubo.slice(resource_id="A")
        assert len(sliced.celulas) == 1
        assert sliced.celulas[0].resource_id == "A"

    def test_slice_by_estado(self):
        cubo = _make_cubo(
            [
                _make_celula(semana_iso="2026-W01", estado="normal"),
                _make_celula(semana_iso="2026-W02", estado="deficit"),
                _make_celula(semana_iso="2026-W03", estado="overflow"),
            ]
        )
        assert len(cubo.slice(estado="deficit").celulas) == 1
        assert len(cubo.slice(estado="overflow").celulas) == 1

    def test_slice_by_semana_iso(self):
        cubo = _make_cubo([_make_celula(semana_iso="2026-W01"), _make_celula(semana_iso="2026-W02")])
        assert len(cubo.slice(semana_iso="2026-W01").celulas) == 1

    def test_group_by_resource_estoque_nivel(self):
        cubo = _make_cubo(
            [
                _make_celula(resource_id="A", semana_iso="2026-W01", estoque_nivel=100.0),
                _make_celula(resource_id="A", semana_iso="2026-W02", estoque_nivel=90.0),
            ]
        )
        grouped = cubo.group_by("resource_id", measure="estoque_nivel")
        assert grouped[("A",)] == 190.0

    def test_group_by_measure_consumo(self):
        cubo = _make_cubo(
            [
                _make_celula(consumo=40.0, semana_iso="2026-W01"),
                _make_celula(consumo=40.0, semana_iso="2026-W02"),
            ]
        )
        grouped = cubo.group_by("resource_id", measure="consumo")
        assert grouped[("MA-DIESEL-TESTE",)] == 80.0

    def test_group_by_measure_fluxo_liquido(self):
        cubo = _make_cubo(
            [_make_celula(producao=50.0, reabastecimento_externo=10.0, consumo=40.0, semana_iso="2026-W01")]
        )
        grouped = cubo.group_by("resource_id", measure="fluxo_liquido")
        assert grouped[("MA-DIESEL-TESTE",)] == 20.0

    def test_estoque_por_semana_ordenado(self):
        cubo = _make_cubo(
            [
                _make_celula(semana_iso="2026-W02", estoque_nivel=80.0),
                _make_celula(semana_iso="2026-W01", estoque_nivel=100.0),
            ]
        )
        assert list(cubo.estoque_por_semana("MA-DIESEL-TESTE").items()) == [
            ("2026-W01", 100.0),
            ("2026-W02", 80.0),
        ]

    def test_semanas_por_estado(self):
        cubo = _make_cubo(
            [
                _make_celula(semana_iso="2026-W01", estado="normal"),
                _make_celula(semana_iso="2026-W02", estado="normal"),
                _make_celula(semana_iso="2026-W03", estado="deficit"),
            ]
        )
        assert cubo.semanas_por_estado() == {"normal": 2, "deficit": 1, "overflow": 0}

    def test_overflow_total(self):
        cubo = _make_cubo(
            [_make_celula(semana_iso="2026-W01", overflow=10.0), _make_celula(semana_iso="2026-W02", overflow=5.0)]
        )
        assert cubo.overflow_total() == 15.0

    def test_consumo_total_e_producao_total(self):
        cubo = _make_cubo(
            [
                _make_celula(semana_iso="2026-W01", consumo=40.0, producao=10.0),
                _make_celula(semana_iso="2026-W02", consumo=40.0, producao=10.0),
            ]
        )
        assert cubo.consumo_total() == 80.0
        assert cubo.producao_total() == 20.0

    def test_group_by_measure_desconhecida_cai_no_fallback_estoque_nivel(self):
        """Measure fora do conjunto reconhecido (estoque_nivel|consumo|producao|
        reabastecimento_externo|overflow|fluxo_liquido) cai no fallback de
        `_measure_value`, que usa `estoque_nivel`."""
        cubo = _make_cubo(
            [_make_celula(resource_id="A", semana_iso="2026-W01", estoque_nivel=42.0, consumo=999.0)]
        )
        grouped = cubo.group_by("resource_id", measure="medida_inexistente")
        assert grouped[("A",)] == 42.0
