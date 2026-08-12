"""ADR-181 F1 — Calendário de mobilização considerando tempo de aquisição.

Cobre:
  - Activity.readiness_weeks (validação de domínio)
  - SerialScheduler: readiness_weeks vira floor de earliest_start (max, não soma)
  - CpSatScheduler: readiness_weeks vira lower bound da variável de start; janela
    incompatível dispara ScheduleError (fail-loud, não clamp silencioso)
  - _spec.py: readiness_weeks resolvido a partir de EapItem.leadtime_aquisicao_semanas
    + EapItem.leadtime_mob_semanas (mesmo lookup por item_id de _compute_productive_weeks)
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime

import pytest

from concilium.application.scheduling.cpsat_scheduler import CpSatScheduler
from concilium.application.scheduling.models import (
    Activity,
    ActivityDAG,
    ResourcePool,
    ScheduleError,
)
from concilium.application.scheduling.scheduler import SerialScheduler
from concilium.application.skills import run_cronograma  # noqa: F401 — trigger importlib loading
from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    EapItem,
    Meta,
    Projeto,
    RegimeTrabalho,
)

# Skill 04-cronograma é carregada dinamicamente (diretório com hífen não é módulo
# Python válido) — ver concilium.application.skills._load_skill_module. O import
# do trigger acima popula sys.modules com o submódulo _spec via import relativo.
_spec_mod = sys.modules["_concilium_skillpkg_04_cronograma._skill_helpers._spec"]
_resolve_spec_activity_readiness_weeks = _spec_mod._resolve_spec_activity_readiness_weeks


def _make_meta():
    return Meta(gerado_em=datetime.now(UTC), contexto_id="test")


def _make_proj():
    return Projeto(
        id="p1",
        nome="proj",
        tipo_obra="terraplenagem",
        localizacao="x",
        coordenadas=Coordenadas(lat=-3.0, lng=-38.0),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        data_inicio=date(2026, 6, 1),
        data_termino=date(2026, 7, 31),
        snapshot_catalogo_id="s",
        snapshot_perfil_id="s",
    )


# ── Activity.readiness_weeks — domínio ──────────────────────────────────────


class TestActivityReadinessWeeks:
    def test_default_is_zero_backward_compat(self):
        """Sem readiness_weeks explícito, comportamento idêntico ao pré-ADR-181."""
        act = Activity("A", "Desc", 2, {"E": 1})
        assert act.readiness_weeks == 0

    def test_accepts_positive_value(self):
        act = Activity("A", "Desc", 2, {"E": 1}, readiness_weeks=3)
        assert act.readiness_weeks == 3

    def test_rejects_negative_value(self):
        with pytest.raises(ValueError, match="readiness_weeks"):
            Activity("A", "Desc", 2, {"E": 1}, readiness_weeks=-1)


# ── SerialScheduler — floor via max(), não soma ─────────────────────────────


class TestSerialSchedulerReadiness:
    def test_root_activity_start_pushed_by_readiness(self):
        """Atividade sem predecessor: earliest_start vira readiness_weeks (era 0)."""
        act = Activity("A", "Supressão vegetal", 4, {"EQUIPE": 1}, readiness_weeks=3)
        dag = ActivityDAG(activities=[act], precedence=[])
        pool = ResourcePool(resources={"EQUIPE": 1})
        scheduler = SerialScheduler(priority_rule="MINSLK")

        result = scheduler.schedule(activities=[act], dag=dag, pool=pool, deadline_weeks=20)

        sa = result.scheduled_activities[0]
        assert sa.start_week - 1 >= 3  # start_week é 1-indexed

    def test_readiness_is_floor_not_additive_over_precedence(self):
        """Quando a precedência já empurra o início além do readiness, readiness
        não soma em cima — é só o piso mínimo (max), não um deslocamento extra."""
        pred = Activity("A", "Escavação", 10, {"E": 1})
        succ = Activity("B", "Supressão vegetal", 4, {"EQUIPE": 1}, readiness_weeks=2)
        dag = ActivityDAG(activities=[pred, succ], precedence=[("A", "B")])
        pool = ResourcePool(resources={"E": 1, "EQUIPE": 1})
        scheduler = SerialScheduler(priority_rule="MINSLK")

        result = scheduler.schedule(activities=[pred, succ], dag=dag, pool=pool, deadline_weeks=30)

        sa_a = next(s for s in result.scheduled_activities if s.activity_id == "A")
        sa_b = next(s for s in result.scheduled_activities if s.activity_id == "B")
        # Predecessor termina na semana 10 (0-indexed) — bem depois do readiness (2).
        # B deve começar exatamente quando A libera, não 2 semanas depois disso.
        assert sa_b.start_week - 1 == sa_a.end_week - 1

    def test_readiness_binds_when_precedence_would_allow_earlier_start(self):
        """Quando a precedência permitiria início mais cedo que o readiness, o
        readiness passa a ser a restrição ativa (o comportamento que faltava:
        antes, leadtime_mob_semanas custava semanas sem nunca atrasar a data)."""
        pred = Activity("A", "Mobilização de apoio", 1, {"E": 1})
        succ = Activity("B", "Supressão vegetal", 4, {"EQUIPE": 1}, readiness_weeks=5)
        dag = ActivityDAG(activities=[pred, succ], precedence=[("A", "B")])
        pool = ResourcePool(resources={"E": 1, "EQUIPE": 1})
        scheduler = SerialScheduler(priority_rule="MINSLK")

        result = scheduler.schedule(activities=[pred, succ], dag=dag, pool=pool, deadline_weeks=30)

        sa_b = next(s for s in result.scheduled_activities if s.activity_id == "B")
        # A libera em t=1, mas B precisa de 5 semanas de readiness a partir de t=0.
        assert sa_b.start_week - 1 == 5


# ── CpSatScheduler — lower bound da variável + fail-loud ────────────────────


class TestCpSatSchedulerReadiness:
    def test_start_lower_bounded_by_readiness(self):
        act = Activity("A", "Supressão vegetal", 4, {"EQUIPE": 1}, readiness_weeks=3)
        dag = ActivityDAG(activities=[act], precedence=[])
        pool = ResourcePool(resources={"EQUIPE": 1})
        scheduler = CpSatScheduler()

        result = scheduler.schedule(dag=dag, pool=pool)

        sa = result.scheduled_activities[0]
        assert sa.start_week >= 3

    def test_readiness_exceeding_window_raises_schedule_error(self):
        """Janela (window_weeks) incompatível com readiness_weeks deve falhar alto,
        não truncar/clampar silenciosamente o start."""
        act = Activity(
            "A",
            "Supressão vegetal",
            4,
            {"EQUIPE": 1},
            window_weeks=6,
            readiness_weeks=10,
        )
        dag = ActivityDAG(activities=[act], precedence=[])
        pool = ResourcePool(resources={"EQUIPE": 1})
        scheduler = CpSatScheduler()

        with pytest.raises(ScheduleError, match="resource readiness"):
            scheduler.schedule(dag=dag, pool=pool)


# ── _spec.py — resolução a partir de EapItem ────────────────────────────────


class TestSpecActivityReadinessResolution:
    def _canonical_com_item(self, **eap_kwargs) -> CanonicalModel:
        item = EapItem(
            item_id="eap-1",
            cpu_id="CPU-X",
            quantitativo=100.0,
            **eap_kwargs,
        )
        return CanonicalModel(meta=_make_meta(), projeto=_make_proj(), eap=[item])

    def test_sums_aquisicao_and_mob(self):
        canonical_in = self._canonical_com_item(leadtime_aquisicao_semanas=2, leadtime_mob_semanas=3)
        readiness = _resolve_spec_activity_readiness_weeks({"item_id": "eap-1"}, canonical_in)
        assert readiness == 5

    def test_defaults_to_zero_without_override(self):
        canonical_in = self._canonical_com_item()
        readiness = _resolve_spec_activity_readiness_weeks({"item_id": "eap-1"}, canonical_in)
        assert readiness == 0

    def test_defaults_to_zero_without_canonical(self):
        assert _resolve_spec_activity_readiness_weeks({"item_id": "eap-1"}, None) == 0

    def test_unknown_item_id_defaults_to_zero(self):
        canonical_in = self._canonical_com_item(leadtime_aquisicao_semanas=4)
        readiness = _resolve_spec_activity_readiness_weeks({"item_id": "outro-item"}, canonical_in)
        assert readiness == 0

    def test_manual_mode_resolves_via_atividade_id_uuid(self):
        """ADR-181 F2: rcpsp_spec MANUAL usa Atividade.atividade_id (UUID) como
        activity_id, não EapItem.item_id — precisa traduzir via eap_item_id."""
        from concilium.domain.models.canonical import Atividade

        item = EapItem(
            item_id="eap-1",
            cpu_id="CPU-X",
            quantitativo=100.0,
            leadtime_aquisicao_semanas=2,
            leadtime_mob_semanas=1,
        )
        ativ = Atividade(
            atividade_id="atv-uuid-1234",
            eap_item_id="eap-1",
            descricao="Supressão vegetal",
            fracao_quantitativo=1.0,
            quantitativo_atividade=100.0,
            cpu_id="CPU-X",
        )
        canonical_in = CanonicalModel(
            meta=_make_meta(), projeto=_make_proj(), eap=[item], atividades=[ativ]
        )
        readiness = _resolve_spec_activity_readiness_weeks({"item_id": "atv-uuid-1234"}, canonical_in)
        assert readiness == 3

    def test_manual_mode_unknown_atividade_id_defaults_to_zero(self):
        from concilium.domain.models.canonical import Atividade

        item = EapItem(item_id="eap-1", cpu_id="CPU-X", quantitativo=100.0, leadtime_mob_semanas=5)
        ativ = Atividade(
            atividade_id="atv-uuid-1234",
            eap_item_id="eap-1",
            descricao="Supressão vegetal",
            fracao_quantitativo=1.0,
            quantitativo_atividade=100.0,
            cpu_id="CPU-X",
        )
        canonical_in = CanonicalModel(
            meta=_make_meta(), projeto=_make_proj(), eap=[item], atividades=[ativ]
        )
        readiness = _resolve_spec_activity_readiness_weeks({"item_id": "atv-desconhecida"}, canonical_in)
        assert readiness == 0
