"""ADR-128 F6 — Testes unitários para o helper de contabilização de skill-04
(`_skill_helpers/_estoque_consumivel.py`).

Cobre a regra de status (OK/AVISO/CRITICO) diretamente, sem depender do pipeline
completo de `run_cronograma` — em particular o caso CRITICO, que na prática nunca é
observável end-to-end porque um cronograma inviável já retorna cedo (`failed=True`,
antes de `recursos_consumiveis`/`resumo_estoque_consumiveis` serem calculados; ver
`tests/integration/test_adr128_f6_skill04_consumiveis_persistencia.py`).
"""

from __future__ import annotations

import sys

from concilium.application.scheduling.models import ReplenishableResource, ScheduledActivity
from concilium.application.skills import run_cronograma  # noqa: F401 — trigger module loading via importlib
from concilium.domain.models.canonical import EstoqueDelayCanonical, ScheduledActivityCanonical
from concilium.domain.models.catalog.disponibilidade_consumivel import DisponibilidadeConsumivel

_mod = sys.modules["_concilium_skillpkg_04_cronograma._skill_helpers._estoque_consumivel"]
build_estoque_consumivel_canonical = _mod.build_estoque_consumivel_canonical
_build_resumo_estoque = _mod._build_resumo_estoque


def _resource(estoque_inicial=0.0, taxa_max=None, capacidade=None, consumo=None) -> ReplenishableResource:
    return ReplenishableResource(
        resource_id="MA-DIESEL-TESTE",
        disponibilidade=DisponibilidadeConsumivel(
            estoque_inicial=estoque_inicial, taxa_reabastecimento_max=taxa_max, capacidade_armazenamento=capacidade
        ),
        consumo_por_semana=consumo or {"A1": 30.0},
    )


class TestBuildResumoEstoqueStatusRule:
    def test_status_ok_sem_atraso_sem_overflow(self):
        resource = _resource(estoque_inicial=500.0, consumo={"A1": 10.0})
        niveis = {0: 490.0, 1: 480.0}
        resumo = _build_resumo_estoque(resource, niveis, {}, [])
        assert resumo.status_estoque == "OK"
        assert resumo.estoque_minimo == 480.0
        assert resumo.delay_total_semanas == 0

    def test_status_aviso_com_delay(self):
        resource = _resource(estoque_inicial=0.0, taxa_max=10.0)
        niveis = {0: 10.0, 1: 20.0, 2: 30.0, 3: 10.0}  # nunca negativo (pós-reparo)
        delays = [EstoqueDelayCanonical(resource_id="MA-DIESEL-TESTE", activity_id="A1", delay_weeks=3)]
        resumo = _build_resumo_estoque(resource, niveis, {}, delays)
        assert resumo.status_estoque == "AVISO"
        assert resumo.delay_total_semanas == 3
        assert resumo.n_atividades_atrasadas == 1

    def test_status_aviso_com_overflow(self):
        resource = _resource(estoque_inicial=100.0, capacidade=100.0)
        niveis = {0: 100.0}
        overflow = {0: 50.0}
        resumo = _build_resumo_estoque(resource, niveis, overflow, [])
        assert resumo.status_estoque == "AVISO"
        assert resumo.overflow_total == 50.0
        assert resumo.n_semanas_overflow == 1

    def test_status_critico_estoque_negativo(self):
        """Caso irreparável — na prática só alcançável via este teste unitário direto,
        já que o pipeline completo (run_cronograma) descarta o resultado antes de
        persistir a contabilização quando o cronograma é marcado infeasible."""
        resource = _resource(estoque_inicial=0.0, capacidade=5.0, taxa_max=10.0, consumo={"A1": 30.0})
        niveis = {0: -25.0, 1: -25.0}
        resumo = _build_resumo_estoque(resource, niveis, {}, [])
        assert resumo.status_estoque == "CRITICO"
        assert resumo.estoque_minimo == -25.0

    def test_estoque_final_e_o_ultimo_nivel(self):
        resource = _resource(estoque_inicial=100.0, consumo={"A1": 10.0})
        niveis = {0: 90.0, 1: 80.0, 2: 70.0}
        resumo = _build_resumo_estoque(resource, niveis, {}, [])
        assert resumo.estoque_final == 70.0

    def test_niveis_vazio_usa_estoque_inicial(self):
        resource = _resource(estoque_inicial=42.0)
        resumo = _build_resumo_estoque(resource, {}, {}, [])
        assert resumo.estoque_medio == 42.0
        assert resumo.estoque_minimo == 42.0
        assert resumo.estoque_final == 42.0
        assert resumo.status_estoque == "OK"


class TestBuildEstoqueConsumivelCanonical:
    def test_none_ou_vazio_retorna_listas_vazias(self):
        recursos, resumos = build_estoque_consumivel_canonical(None, [], [])
        assert recursos == []
        assert resumos == []
        recursos, resumos = build_estoque_consumivel_canonical([], [], [])
        assert recursos == []
        assert resumos == []

    def test_constroi_snapshot_e_resumo_end_to_end(self):
        resource = _resource(estoque_inicial=500.0, consumo={"A1": 10.0})
        scheduled = [
            ScheduledActivityCanonical(activity_id="A1", start_week=0, end_week=2, duration_weeks=2),
        ]
        recursos, resumos = build_estoque_consumivel_canonical([resource], scheduled, [])

        assert len(recursos) == 1
        assert recursos[0].resource_id == "MA-DIESEL-TESTE"
        assert recursos[0].disponibilidade.estoque_inicial == 500.0
        assert recursos[0].consumo_por_semana == {"A1": 10.0}

        assert len(resumos) == 1
        assert resumos[0].resource_id == "MA-DIESEL-TESTE"
        assert resumos[0].status_estoque == "OK"


class TestToScheduledActivity:
    def test_conversao_trivial_de_campos(self):
        sa = ScheduledActivityCanonical(activity_id="A1", start_week=1, end_week=3, duration_weeks=2)
        converted = _mod._to_scheduled_activity(sa)
        assert isinstance(converted, ScheduledActivity)
        assert converted.activity_id == "A1"
        assert converted.start_week == 1
        assert converted.end_week == 3
        assert converted.duration_weeks == 2
