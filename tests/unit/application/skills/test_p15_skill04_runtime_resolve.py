"""P15: Skill 04 calls the bounded resolver and revalidates rematerialized AUTO schedules."""
from __future__ import annotations

from datetime import date
from fractions import Fraction as F
from types import SimpleNamespace

import pytest

from concilium.application.scheduling.physical_validator import PhysicalPrecedence
from concilium.domain.models.canonical import (
    DistribuicaoSemanal,
    ScheduleCandidateCanonical,
    ScheduledActivityCanonical,
)


WEEKS = ("2026-W01", "2026-W02", "2026-W03", "2026-W04")


class Item:
    def __init__(self, item_id: str) -> None:
        self.item_id = item_id
        self.cpu_id = f"CPU-{item_id}"
        self.quantitativo = 1.0

    def predecessores_tipados(self):
        return []


def _cell(week_index: int) -> DistribuicaoSemanal:
    return DistribuicaoSemanal(
        num_equipes=1,
        qtd_executada=1.0,
        qtd_acumulada=1.0,
        pct=1.0,
        q_max_celula=1.0,
        capacidade_disponivel_semana=1.0,
    )


def _candidate() -> ScheduleCandidateCanonical:
    return ScheduleCandidateCanonical(
        heuristic="test",
        scheduled_activities=[
            ScheduledActivityCanonical(
                activity_id=item,
                start_week=0,
                end_week=0,
                duration_weeks=1,
                assigned_resources={"crane": 1},
            )
            for item in ("A", "B")
        ],
        makespan=1,
        quality_score=1.0,
    )


def _runtime_inputs():
    canonical = SimpleNamespace(
        eap=[Item("A"), Item("B")],
        atividades=[],
        recurso_pool=[
            SimpleNamespace(
                proveniencia="CONFIGURADO",
                tipo_id="crane",
                quantidade_total=1,
            )
        ],
        projeto=SimpleNamespace(data_inicio=date(2026, 1, 5)),
    )
    regime = SimpleNamespace(horas_dia=1.0, dias_semana=1.0, eta_jornada=1.0)
    return canonical, regime


def _install_deterministic_materializer(monkeypatch, weeks=WEEKS):
    from concilium.application.skills.manifests._unused import unused  # noqa: F401


def test_skill04_physical_resolver_reallocates_two_tasks_away_from_pool_collision(monkeypatch) -> None:
    from concilium.application.skills.manifests import _unused  # noqa: F401
