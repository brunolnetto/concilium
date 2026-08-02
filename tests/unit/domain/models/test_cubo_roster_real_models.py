"""Tests for domain/models/analytics/cubo_roster_real.py (ADR-174 F2)."""

from __future__ import annotations

from concilium.domain.models.analytics.cubo_roster_real import (
    CelulaRosterReal,
    CuboRosterReal,
)


def _make_celula(
    categoria="MAO_OBRA",
    grupo_id="MO-ARMADOR",
    instancia_id="mo-001",
    semana_iso="2026-W01",
    custo_direto=1000.0,
    custo_indireto=100.0,
    custo_total=1100.0,
):
    return CelulaRosterReal(
        categoria=categoria,
        grupo_id=grupo_id,
        instancia_id=instancia_id,
        semana_iso=semana_iso,
        custo_direto=custo_direto,
        custo_indireto=custo_indireto,
        custo_total=custo_total,
    )


def _make_cubo(celulas):
    return CuboRosterReal(projeto_id="proj-1", gerado_em="2026-01-01", celulas=tuple(celulas))


class TestCuboRosterReal:
    def test_slice_by_categoria(self):
        cubo = _make_cubo(
            [
                _make_celula(categoria="MAO_OBRA", instancia_id="mo-001"),
                _make_celula(categoria="EQUIPAMENTO", instancia_id="eq-001", grupo_id="EQ-ESCAVADEIRA"),
            ]
        )
        sliced = cubo.slice(categoria="EQUIPAMENTO")
        assert len(sliced.celulas) == 1
        assert sliced.celulas[0].instancia_id == "eq-001"

    def test_slice_by_grupo_id(self):
        cubo = _make_cubo(
            [
                _make_celula(grupo_id="MO-ARMADOR", instancia_id="mo-001"),
                _make_celula(grupo_id="MO-CARPINTEIRO", instancia_id="mo-002"),
            ]
        )
        assert len(cubo.slice(grupo_id="MO-CARPINTEIRO").celulas) == 1

    def test_slice_by_instancia_id(self):
        cubo = _make_cubo(
            [
                _make_celula(instancia_id="mo-001", semana_iso="2026-W01"),
                _make_celula(instancia_id="mo-001", semana_iso="2026-W02"),
                _make_celula(instancia_id="mo-002", semana_iso="2026-W01"),
            ]
        )
        assert len(cubo.slice(instancia_id="mo-001").celulas) == 2

    def test_slice_combina_filtros(self):
        cubo = _make_cubo(
            [
                _make_celula(categoria="MAO_OBRA", grupo_id="MO-ARMADOR", instancia_id="mo-001"),
                _make_celula(categoria="MAO_OBRA", grupo_id="MO-ARMADOR", instancia_id="mo-002"),
            ]
        )
        sliced = cubo.slice(categoria="MAO_OBRA", instancia_id="mo-002")
        assert len(sliced.celulas) == 1
        assert sliced.celulas[0].instancia_id == "mo-002"

    def test_group_by_instancia_custo_total(self):
        cubo = _make_cubo(
            [
                _make_celula(instancia_id="mo-001", semana_iso="2026-W01", custo_total=1100.0),
                _make_celula(instancia_id="mo-001", semana_iso="2026-W02", custo_total=1100.0),
            ]
        )
        grouped = cubo.group_by("instancia_id", measure="custo_total")
        assert grouped[("mo-001",)] == 2200.0

    def test_group_by_categoria_custo_indireto(self):
        cubo = _make_cubo(
            [
                _make_celula(categoria="MAO_OBRA", custo_indireto=100.0, semana_iso="2026-W01"),
                _make_celula(categoria="EQUIPAMENTO", custo_indireto=0.0, semana_iso="2026-W01"),
            ]
        )
        grouped = cubo.group_by("categoria", measure="custo_indireto")
        assert grouped[("MAO_OBRA",)] == 100.0
        assert grouped[("EQUIPAMENTO",)] == 0.0

    def test_group_by_medida_desconhecida_cai_no_fallback_custo_total(self):
        cubo = _make_cubo([_make_celula(custo_total=42.0, custo_direto=999.0)])
        grouped = cubo.group_by("instancia_id", measure="medida_inexistente")
        assert grouped[("mo-001",)] == 42.0

    def test_custo_por_instancia_ordenado_por_semana(self):
        cubo = _make_cubo(
            [
                _make_celula(instancia_id="mo-001", semana_iso="2026-W02", custo_total=200.0),
                _make_celula(instancia_id="mo-001", semana_iso="2026-W01", custo_total=100.0),
            ]
        )
        assert list(cubo.custo_por_instancia("mo-001").items()) == [
            ("2026-W01", 100.0),
            ("2026-W02", 200.0),
        ]

    def test_custo_por_grupo(self):
        cubo = _make_cubo(
            [
                _make_celula(grupo_id="MO-ARMADOR", instancia_id="mo-001", custo_total=1000.0),
                _make_celula(grupo_id="MO-ARMADOR", instancia_id="mo-002", custo_total=1000.0),
                _make_celula(grupo_id="MO-CARPINTEIRO", instancia_id="mo-003", custo_total=500.0),
            ]
        )
        assert cubo.custo_por_grupo() == {"MO-ARMADOR": 2000.0, "MO-CARPINTEIRO": 500.0}

    def test_custo_por_categoria(self):
        cubo = _make_cubo(
            [
                _make_celula(categoria="MAO_OBRA", custo_total=1000.0),
                _make_celula(categoria="EQUIPAMENTO", grupo_id="EQ-X", instancia_id="eq-001", custo_total=500.0),
            ]
        )
        assert cubo.custo_por_categoria() == {"MAO_OBRA": 1000.0, "EQUIPAMENTO": 500.0}

    def test_custo_total_geral(self):
        cubo = _make_cubo(
            [
                _make_celula(instancia_id="mo-001", custo_total=1000.0),
                _make_celula(instancia_id="mo-002", custo_total=500.0),
            ]
        )
        assert cubo.custo_total_geral() == 1500.0

    def test_cubo_vazio_projecoes_seguras(self):
        cubo = _make_cubo([])
        assert cubo.custo_por_categoria() == {}
        assert cubo.custo_por_grupo() == {}
        assert cubo.custo_total_geral() == 0.0
