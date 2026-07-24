"""Tests for cubo_estoque_consumivel_projection/_dispatch.py (ADR-128 F6 faces).

cubo_estoque_consumivel_projection_contract() is already covered elsewhere;
this exercises resolve_cubo_estoque_consumivel_projection() and its 4 private
face builders — previously the whole dispatch path (lines 69-215) was
untouched by any test.
"""

from __future__ import annotations

import sys
from datetime import date
from types import SimpleNamespace

from concilium.application.scheduling.replenishable_builder import build_replenishable_resources
from concilium.application.services.analytics.cubo_estoque_consumivel_projection._dispatch import (
    resolve_cubo_estoque_consumivel_projection,
)
from concilium.application.skills import run_cronograma  # noqa: F401 — trigger module loading via importlib
from concilium.domain.models.canonical import EstoqueDelayCanonical, ScheduledActivityCanonical
from concilium.domain.models.catalog.disponibilidade_consumivel import DisponibilidadeConsumivel


def _canonical():
    """Builds a real canonical (via the same helpers used by skill-04's pipeline
    and mirrored from test_adr128_f6_cubo_estoque_consumivel_builder.py), then
    drives resolve_cubo_estoque_consumivel_projection() through every face."""
    estoque_mod = sys.modules["_concilium_skillpkg_04_cronograma._skill_helpers._estoque_consumivel"]
    build_estoque_consumivel_canonical = estoque_mod.build_estoque_consumivel_canonical

    def _producao(pid, insumo_id):
        return {
            "id": pid,
            "codigo": pid,
            "valor_horario": 50.0,
            "composicao_padrao_equipe": {
                "equipamentos": [{"equip_id": "EQ-X", "num_unidades": 1}],
                "materiais": [{"insumo_id": insumo_id, "consumo_por_hora": 1.0}],
            },
        }

    def _insumo(codigo):
        return {
            "codigo": codigo,
            "tipo": "MATERIAL",
            "origem_material": "AQUISICAO_EXTERNA",
            "preco_unitario": 6.5,
        }

    resources = build_replenishable_resources(
        producoes_por_atividade={"A1": _producao("PROD-A", "MA-A"), "A2": _producao("PROD-B", "MA-B")},
        insumos_por_id={"MA-A": _insumo("MA-A"), "MA-B": _insumo("MA-B")},
        horas_semana=40.0,
        disponibilidade_overrides={
            "MA-A": DisponibilidadeConsumivel(estoque_inicial=1000.0),
            "MA-B": DisponibilidadeConsumivel(estoque_inicial=1000.0),
        },
    )
    scheduled = [
        ScheduledActivityCanonical(activity_id="A1", start_week=0, end_week=2, duration_weeks=2),
        ScheduledActivityCanonical(activity_id="A2", start_week=0, end_week=2, duration_weeks=2),
    ]
    delays = [
        EstoqueDelayCanonical(resource_id="MA-A", activity_id="A1", delay_weeks=1),
        EstoqueDelayCanonical(resource_id="MA-B", activity_id="A2", delay_weeks=2),
    ]
    recursos_canonical, resumos = build_estoque_consumivel_canonical(resources, scheduled, delays)

    return SimpleNamespace(
        projeto=SimpleNamespace(nome="Projeto Dispatch", data_inicio=date(2026, 6, 1)),
        cronograma=SimpleNamespace(scheduled_activities=scheduled, estoque_delays=delays),
        recursos_consumiveis=recursos_canonical,
        resumo_estoque_consumiveis=resumos,
    )


class TestCuboEstoqueConsumivelProjectionDispatch:
    def test_default_face_is_resumo_por_recurso(self):
        canonical = _canonical()
        result = resolve_cubo_estoque_consumivel_projection(canonical)
        assert result["face"] == "resumo_por_recurso"
        assert {r["resource_id"] for r in result["rows"]} == {"MA-A", "MA-B"}
        assert result["invariantes_ok"] is True
        assert result["filtros_aplicados"] == {"resource_id": None, "top_n": 300}

    def test_estoque_temporal_face(self):
        canonical = _canonical()
        result = resolve_cubo_estoque_consumivel_projection(canonical, face="estoque_temporal")
        assert result["face"] == "estoque_temporal"
        assert result["granularidade"] == "mes"
        assert result["rows"]
        assert {"resource_id", "periodo", "estoque_nivel_medio"} <= result["rows"][0].keys()

    def test_estoque_temporal_face_with_resource_id_filter(self):
        canonical = _canonical()
        result = resolve_cubo_estoque_consumivel_projection(canonical, face="estoque_temporal", resource_id="MA-A")
        assert result["rows"]
        assert all(r["resource_id"] == "MA-A" for r in result["rows"])

    def test_fluxo_componente_face(self):
        canonical = _canonical()
        result = resolve_cubo_estoque_consumivel_projection(canonical, face="fluxo_componente")
        assert result["face"] == "fluxo_componente"
        assert result["rows"]
        assert "consumo" in result["rows"][0]
        assert "producao" in result["rows"][0]

    def test_fluxo_componente_face_with_resource_id_filter(self):
        canonical = _canonical()
        result = resolve_cubo_estoque_consumivel_projection(canonical, face="fluxo_componente", resource_id="MA-B")
        assert result["rows"]
        assert all(r["resource_id"] == "MA-B" for r in result["rows"])

    def test_causa_atraso_face(self):
        canonical = _canonical()
        result = resolve_cubo_estoque_consumivel_projection(canonical, face="causa_atraso")
        assert result["face"] == "causa_atraso"
        assert len(result["rows"]) == 2
        assert result["natureza"] == "causal"

    def test_causa_atraso_face_with_resource_id_filter(self):
        canonical = _canonical()
        result = resolve_cubo_estoque_consumivel_projection(canonical, face="causa_atraso", resource_id="MA-A")
        assert len(result["rows"]) == 1
        assert result["rows"][0]["resource_id"] == "MA-A"

    def test_invalid_face_falls_back_to_resumo_por_recurso(self):
        canonical = _canonical()
        result = resolve_cubo_estoque_consumivel_projection(canonical, face="not-a-real-face")
        assert result["face"] == "resumo_por_recurso"

    def test_invalid_granularidade_falls_back_to_mes(self):
        canonical = _canonical()
        result = resolve_cubo_estoque_consumivel_projection(
            canonical, face="estoque_temporal", granularidade="not-a-real-granularidade"
        )
        assert result["granularidade"] == "mes"

    def test_rows_truncated_when_exceeding_top_n(self):
        canonical = _canonical()
        result = resolve_cubo_estoque_consumivel_projection(canonical, face="resumo_por_recurso", top_n=1)
        assert len(result["rows"]) == 1
        assert result["operator_meta"]["truncado"] is True
        assert result["operator_meta"]["linhas_totais"] == 2
        assert any("truncado" in n for n in result["narrativa"])

    def test_totais_reflect_cube_aggregates(self):
        canonical = _canonical()
        result = resolve_cubo_estoque_consumivel_projection(canonical)
        assert set(result["totais"].keys()) == {
            "overflow_total",
            "consumo_total",
            "producao_total",
            "semanas_por_estado",
        }
        assert result["totais"]["consumo_total"] > 0
