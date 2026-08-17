"""ADR-128 F6 — Testes do builder do Cubo de Estoque Consumível.

Constrói ``ReplenishableResource``/``RecursoConsumivelCanonical`` reais (via
``build_replenishable_resources``/``build_estoque_consumivel_canonical``, os mesmos
helpers usados pelo pipeline real de skill-04), embrulha num ``SimpleNamespace`` fake
canonical, e testa ``CuboEstoqueConsumivelBuilder`` contra esse dado — mirror do padrão
de ``test_adr086_cubo_pool.py`` para o cubo de pool.
"""

from __future__ import annotations

import sys
from datetime import date
from types import SimpleNamespace

from concilium.application.scheduling.replenishable_builder import build_replenishable_resources
from concilium.application.services.analytics.cubo_estoque_consumivel_builder import (
    CuboEstoqueConsumivelBuilder,
)
from concilium.application.skills import run_cronograma  # noqa: F401 — trigger module loading via importlib
from concilium.domain.models.canonical import EstoqueDelayCanonical, ScheduledActivityCanonical
from concilium.domain.models.catalog.disponibilidade_consumivel import DisponibilidadeConsumivel

_estoque_mod = sys.modules["_concilium_skillpkg_04_cronograma._skill_helpers._estoque_consumivel"]
build_estoque_consumivel_canonical = _estoque_mod.build_estoque_consumivel_canonical


def _make_producao(pid: str, materiais=None) -> dict:
    return {
        "id": pid,
        "codigo": pid,
        "producao_horaria": 50.0,
        "composicao_padrao_equipe": {
            "equipamentos": [{"equip_id": "EQ-X", "num_unidades": 1}],
            "materiais": materiais or [],
        },
    }


def _make_insumo(codigo: str) -> dict:
    return {
        "codigo": codigo,
        "tipo": "MATERIAL",
        "origem_material": "AQUISICAO_EXTERNA",
        "preco_unitario": 6.5,
    }


def _fake_canonical(recursos_consumiveis, scheduled_activities, data_inicio=date(2026, 6, 1)):
    return SimpleNamespace(
        projeto=SimpleNamespace(nome="Projeto Teste F6", data_inicio=data_inicio),
        cronograma=SimpleNamespace(scheduled_activities=scheduled_activities),
        recursos_consumiveis=recursos_consumiveis,
    )


class TestCuboEstoqueConsumivelBuilderNormal:
    def test_recurso_com_estoque_farto_gera_celulas_normal(self):
        producao = _make_producao("PROD-01", materiais=[{"insumo_id": "MA-DIESEL-TESTE", "consumo_por_hora": 1.0}])
        # Sem disponibilidade declarada e sem produção interna, o insumo fica irrestrito
        # — precisamos de um override para exercitar o path com recurso restrito.
        resources = build_replenishable_resources(
            producoes_por_atividade={"A1": producao},
            insumos_por_id={"MA-DIESEL-TESTE": _make_insumo("MA-DIESEL-TESTE")},
            horas_semana=40.0,
            disponibilidade_overrides={"MA-DIESEL-TESTE": DisponibilidadeConsumivel(estoque_inicial=1000.0)},
        )
        scheduled = [ScheduledActivityCanonical(activity_id="A1", start_week=0, end_week=2, duration_weeks=2)]
        recursos_canonical, _resumos = build_estoque_consumivel_canonical(resources, scheduled, [])

        cubo = CuboEstoqueConsumivelBuilder().build(_fake_canonical(recursos_canonical, scheduled))

        assert cubo.projeto_id == "Projeto Teste F6"
        assert len(cubo.celulas) == 2  # 2 semanas ativas
        assert all(c.estado == "normal" for c in cubo.celulas)
        assert all(c.resource_id == "MA-DIESEL-TESTE" for c in cubo.celulas)
        assert cubo.celulas[0].semana_iso == "2026-W23"  # 2026-06-01 é uma segunda-feira da semana ISO 23
        assert cubo.consumo_total() > 0


class TestCuboEstoqueConsumivelBuilderDeficit:
    def test_estoque_irreparavel_gera_celulas_deficit(self):
        producao = _make_producao("PROD-01", materiais=[{"insumo_id": "MA-DIESEL-TESTE", "consumo_por_hora": 1.0}])
        resources = build_replenishable_resources(
            producoes_por_atividade={"A1": producao},
            insumos_por_id={"MA-DIESEL-TESTE": _make_insumo("MA-DIESEL-TESTE")},
            horas_semana=40.0,
            disponibilidade_overrides={
                "MA-DIESEL-TESTE": DisponibilidadeConsumivel(
                    estoque_inicial=0.0, capacidade_armazenamento=5.0, taxa_reabastecimento_max=10.0
                )
            },
        )
        scheduled = [ScheduledActivityCanonical(activity_id="A1", start_week=0, end_week=1, duration_weeks=1)]
        recursos_canonical, _resumos = build_estoque_consumivel_canonical(resources, scheduled, [])

        cubo = CuboEstoqueConsumivelBuilder().build(_fake_canonical(recursos_canonical, scheduled))

        assert len(cubo.celulas) == 1
        assert cubo.celulas[0].estado == "deficit"
        assert cubo.celulas[0].estoque_nivel < 0


class TestCuboEstoqueConsumivelBuilderCausaAtraso:
    def test_resumo_estoque_reflete_atraso_causal(self):
        """Prova que a causa (qual atividade, quantas semanas) permanece exclusivamente
        em EstoqueDelayCanonical/ResumoEstoqueConsumivel, não duplicada no cubo — o
        cubo só sabe 'estado' físico (normal/deficit/overflow) por semana."""
        producao = _make_producao("PROD-01", materiais=[{"insumo_id": "MA-DIESEL-TESTE", "consumo_por_hora": 1.0}])
        resources = build_replenishable_resources(
            producoes_por_atividade={"A1": producao},
            insumos_por_id={"MA-DIESEL-TESTE": _make_insumo("MA-DIESEL-TESTE")},
            horas_semana=40.0,
            disponibilidade_overrides={
                "MA-DIESEL-TESTE": DisponibilidadeConsumivel(estoque_inicial=1000.0),
            },
        )
        # Cronograma FINAL já reparado (posição pós-atraso) — a causa vem de fora, via
        # EstoqueDelayCanonical, não recomputada pelo cubo.
        scheduled = [ScheduledActivityCanonical(activity_id="A1", start_week=3, end_week=4, duration_weeks=1)]
        delays = [EstoqueDelayCanonical(resource_id="MA-DIESEL-TESTE", activity_id="A1", delay_weeks=3)]
        recursos_canonical, resumos = build_estoque_consumivel_canonical(resources, scheduled, delays)

        assert resumos[0].delay_total_semanas == 3
        assert resumos[0].status_estoque == "AVISO"

        cubo = CuboEstoqueConsumivelBuilder().build(_fake_canonical(recursos_canonical, scheduled))
        assert all(c.estado == "normal" for c in cubo.celulas)  # farto estoque, sem deficit/overflow físico


class TestCuboEstoqueConsumivelBuilderVazio:
    def test_sem_recursos_consumiveis_retorna_cubo_vazio(self):
        cubo = CuboEstoqueConsumivelBuilder().build(_fake_canonical([], []))
        assert cubo.celulas == ()

    def test_sem_projeto_retorna_projeto_id_vazio(self):
        """`_get_projeto_id` retorna '' quando `canonical_in.projeto` é None (ex.: canônico
        parcial/fake sem o bloco de projeto ainda montado)."""
        canonical = SimpleNamespace(
            projeto=None,
            cronograma=SimpleNamespace(scheduled_activities=[]),
            recursos_consumiveis=[],
        )
        cubo = CuboEstoqueConsumivelBuilder().build(canonical)
        assert cubo.projeto_id == ""
        assert cubo.celulas == ()
