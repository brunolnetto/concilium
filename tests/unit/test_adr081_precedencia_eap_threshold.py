"""ADR-081: Precedência EAP com Derivação Automática e Threshold de Conclusão Parcial.

Testa:
  A. completion_threshold_pct em PrecedenciaItem e ArestaActivityDag
  B. ActivityDAG.get_threshold() e thresholds dict
  C. _compute_earliest_starts com threshold
  D. SerialScheduler: início antecipado com θ < 1.0
  E. Derivação automática de DAG a partir de eap[].predecessores
  F. Compatibilidade retroativa (θ=1.0 default)
"""

from __future__ import annotations

import math

import pytest

from concilium.application.scheduling.models import Activity, ActivityDAG, ResourcePool
from concilium.application.scheduling.scheduler import SerialScheduler, _compute_earliest_starts
from concilium.domain.models.canonical import ArestaActivityDag, PrecedenciaItem

# ─────────────────────────────────────────────────────────────────────────────
# A. Modelo PrecedenciaItem e ArestaActivityDag
# ─────────────────────────────────────────────────────────────────────────────


class TestPrecedenciaItemThreshold:
    def test_default_threshold_e_um(self):
        p = PrecedenciaItem(item_id="eap-1_1")
        assert p.completion_threshold_pct == 1.0

    def test_threshold_customizado(self):
        p = PrecedenciaItem(item_id="eap-1_1", tipo="FS", lag=0, completion_threshold_pct=0.20)
        assert p.completion_threshold_pct == pytest.approx(0.20)

    def test_threshold_zero_equivale_SS(self):
        p = PrecedenciaItem(item_id="eap-1_1", completion_threshold_pct=0.0)
        assert p.completion_threshold_pct == pytest.approx(0.0)

    def test_threshold_invalido_rejeita_acima_de_um(self):
        with pytest.raises(Exception):
            PrecedenciaItem(item_id="x", completion_threshold_pct=1.5)

    def test_threshold_invalido_rejeita_negativo(self):
        with pytest.raises(Exception):
            PrecedenciaItem(item_id="x", completion_threshold_pct=-0.1)


class TestArestaActivityDagThreshold:
    def test_default_threshold_e_um(self):
        a = ArestaActivityDag(de="A", para="B")
        assert a.completion_threshold_pct == 1.0

    def test_threshold_customizado(self):
        a = ArestaActivityDag(de="A", para="B", completion_threshold_pct=0.07)
        assert a.completion_threshold_pct == pytest.approx(0.07)


# ─────────────────────────────────────────────────────────────────────────────
# B. ActivityDAG.get_threshold() e campo thresholds
# ─────────────────────────────────────────────────────────────────────────────


def _make_activities(ids_durations: list[tuple[str, int]]) -> list[Activity]:
    return [Activity(activity_id=aid, description=aid, duration_weeks=dur) for aid, dur in ids_durations]


class TestActivityDAGThresholds:
    def test_get_threshold_default_um_quando_ausente(self):
        acts = _make_activities([("A", 10), ("B", 5)])
        dag = ActivityDAG(activities=acts, precedence=[("A", "B")])
        assert dag.get_threshold("A", "B") == pytest.approx(1.0)

    def test_get_threshold_customizado(self):
        acts = _make_activities([("A", 10), ("B", 5)])
        dag = ActivityDAG(
            activities=acts,
            precedence=[("A", "B")],
            thresholds={("A", "B"): 0.30},
        )
        assert dag.get_threshold("A", "B") == pytest.approx(0.30)

    def test_get_threshold_par_ausente_retorna_um(self):
        acts = _make_activities([("A", 10), ("B", 5)])
        dag = ActivityDAG(activities=acts, precedence=[("A", "B")], thresholds={})
        assert dag.get_threshold("X", "Y") == pytest.approx(1.0)

    def test_threshold_multiplos_pares(self):
        acts = _make_activities([("A", 10), ("B", 20), ("C", 5)])
        dag = ActivityDAG(
            activities=acts,
            precedence=[("A", "B"), ("A", "C"), ("B", "C")],
            thresholds={("A", "B"): 0.06, ("A", "C"): 0.20, ("B", "C"): 0.50},
        )
        assert dag.get_threshold("A", "B") == pytest.approx(0.06)
        assert dag.get_threshold("A", "C") == pytest.approx(0.20)
        assert dag.get_threshold("B", "C") == pytest.approx(0.50)


# ─────────────────────────────────────────────────────────────────────────────
# C. _compute_earliest_starts com threshold
# ─────────────────────────────────────────────────────────────────────────────


class TestComputeEarliestStartsThreshold:
    def test_theta_1_0_comportamento_classico(self):
        """θ=1.0 deve dar o mesmo resultado que FS clássico."""
        acts = _make_activities([("A", 10), ("B", 5)])
        dag = ActivityDAG(
            activities=acts,
            precedence=[("A", "B")],
            thresholds={("A", "B"): 1.0},
        )
        topo = dag.topological_order()
        act_map = {a.activity_id: a for a in acts}
        earliest = _compute_earliest_starts(act_map, dag, topo)
        assert earliest["A"] == 0
        assert earliest["B"] == 10  # A dura 10 → B começa em 10

    def test_theta_0_5_inicio_na_metade_do_predecessor(self):
        """θ=0.5 sobre predecessor de 10w → B pode começar em ceil(0.5×10)=5."""
        acts = _make_activities([("A", 10), ("B", 5)])
        dag = ActivityDAG(
            activities=acts,
            precedence=[("A", "B")],
            thresholds={("A", "B"): 0.5},
        )
        topo = dag.topological_order()
        act_map = {a.activity_id: a for a in acts}
        earliest = _compute_earliest_starts(act_map, dag, topo)
        assert earliest["B"] == 5  # ceil(0.5 × 10) = 5

    def test_theta_0_0_inicio_junto_com_predecessor(self):
        """θ=0.0 → B pode iniciar quando A inicia (SS)."""
        acts = _make_activities([("A", 10), ("B", 5)])
        dag = ActivityDAG(
            activities=acts,
            precedence=[("A", "B")],
            thresholds={("A", "B"): 0.0},
        )
        topo = dag.topological_order()
        act_map = {a.activity_id: a for a in acts}
        earliest = _compute_earliest_starts(act_map, dag, topo)
        assert earliest["B"] == 0  # ceil(0.0 × 10) = 0

    def test_theta_0_20_arredondamento_ceil(self):
        """θ=0.20 sobre 23w → ceil(0.20×23) = ceil(4.6) = 5."""
        acts = _make_activities([("DESMAT", 23), ("ESC1", 45)])
        dag = ActivityDAG(
            activities=acts,
            precedence=[("DESMAT", "ESC1")],
            thresholds={("DESMAT", "ESC1"): 0.20},
        )
        topo = dag.topological_order()
        act_map = {a.activity_id: a for a in acts}
        earliest = _compute_earliest_starts(act_map, dag, topo)
        assert earliest["ESC1"] == math.ceil(0.20 * 23)  # = 5

    def test_multiplos_predecessores_usa_maximo(self):
        """B tem dois predecessores com thresholds diferentes; usa o mais tardio."""
        acts = _make_activities([("P1", 20), ("P2", 50), ("B", 5)])
        dag = ActivityDAG(
            activities=acts,
            precedence=[("P1", "B"), ("P2", "B")],
            thresholds={("P1", "B"): 1.0, ("P2", "B"): 0.07},
        )
        topo = dag.topological_order()
        act_map = {a.activity_id: a for a in acts}
        earliest = _compute_earliest_starts(act_map, dag, topo)
        # P1→B: θ=1.0, offset=20; P2→B: θ=0.07, offset=ceil(0.07×50)=4
        # B começa em max(20, 4) = 20
        assert earliest["B"] == max(20, math.ceil(0.07 * 50))

    def test_sem_predecessores_comeca_em_zero(self):
        acts = _make_activities([("A", 5), ("B", 5)])
        dag = ActivityDAG(activities=acts, precedence=[])
        topo = dag.topological_order()
        act_map = {a.activity_id: a for a in acts}
        earliest = _compute_earliest_starts(act_map, dag, topo)
        assert earliest["A"] == 0
        assert earliest["B"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# D. SerialScheduler: início antecipado com θ < 1.0
# ─────────────────────────────────────────────────────────────────────────────


class TestSerialSchedulerThreshold:
    def _pool(self, **resources: int) -> ResourcePool:
        return ResourcePool(resources=resources)

    def test_theta_1_0_schedule_classico(self):
        """θ=1.0: B começa apenas após A terminar."""
        acts = _make_activities([("A", 10), ("B", 5)])
        acts[1].required_resources = {}
        dag = ActivityDAG(activities=acts, precedence=[("A", "B")], thresholds={("A", "B"): 1.0})
        sched = SerialScheduler("GR").schedule(acts, dag, self._pool(), deadline_weeks=20)
        a_end = next(s.end_week for s in sched.scheduled_activities if s.activity_id == "A")
        b_start = next(s.start_week for s in sched.scheduled_activities if s.activity_id == "B")
        assert b_start >= a_end

    def test_theta_0_5_b_comeca_na_metade_de_a(self):
        """θ=0.5: B pode iniciar quando A está 50% feita."""
        acts = _make_activities([("A", 10), ("B", 5)])
        dag = ActivityDAG(activities=acts, precedence=[("A", "B")], thresholds={("A", "B"): 0.5})
        sched = SerialScheduler("GR").schedule(acts, dag, self._pool(), deadline_weeks=20)
        b_start = next(s.start_week for s in sched.scheduled_activities if s.activity_id == "B")
        a_start = next(s.start_week for s in sched.scheduled_activities if s.activity_id == "A")
        # B deve iniciar em a_start + ceil(0.5 × 10) = a_start + 5
        assert b_start == a_start + 5

    def test_theta_0_0_b_comeca_junto_com_a(self):
        """θ=0.0: B inicia no mesmo período que A (SS sem lag)."""
        acts = _make_activities([("A", 10), ("B", 5)])
        dag = ActivityDAG(activities=acts, precedence=[("A", "B")], thresholds={("A", "B"): 0.0})
        sched = SerialScheduler("GR").schedule(acts, dag, self._pool(), deadline_weeks=20)
        a_start = next(s.start_week for s in sched.scheduled_activities if s.activity_id == "A")
        b_start = next(s.start_week for s in sched.scheduled_activities if s.activity_id == "B")
        assert b_start == a_start

    def test_theta_0_96_quase_FS_classico(self):
        """θ=0.96 sobre 25w: B começa em ceil(0.96×25)=24, não em 25."""
        acts = _make_activities([("PN", 25), ("PI", 3)])
        dag = ActivityDAG(activities=acts, precedence=[("PN", "PI")], thresholds={("PN", "PI"): 0.96})
        sched = SerialScheduler("GR").schedule(acts, dag, self._pool(), deadline_weeks=35)
        pn_start = next(s.start_week for s in sched.scheduled_activities if s.activity_id == "PN")
        pi_start = next(s.start_week for s in sched.scheduled_activities if s.activity_id == "PI")
        expected_offset = math.ceil(0.96 * 25)  # = 24
        assert pi_start == pn_start + expected_offset

    def test_theta_reduz_makespan(self):
        """Com θ < 1.0, o makespan deve ser menor ou igual ao makespan com θ=1.0."""
        acts_full = _make_activities([("A", 20), ("B", 10)])
        acts_partial = _make_activities([("A", 20), ("B", 10)])
        dag_full = ActivityDAG(activities=acts_full, precedence=[("A", "B")], thresholds={("A", "B"): 1.0})
        dag_partial = ActivityDAG(activities=acts_partial, precedence=[("A", "B")], thresholds={("A", "B"): 0.5})
        sched_full = SerialScheduler("GR").schedule(acts_full, dag_full, self._pool(), deadline_weeks=40)
        sched_partial = SerialScheduler("GR").schedule(acts_partial, dag_partial, self._pool(), deadline_weeks=40)
        assert sched_partial.makespan <= sched_full.makespan


# ─────────────────────────────────────────────────────────────────────────────
# E. Derivação automática de DAG a partir de eap[].predecessores
# ─────────────────────────────────────────────────────────────────────────────


class TestDerivacaoDAGdaEAP:
    """Testa _extract_dag_from_spec quando rcpsp_spec.precedence está vazio
    e a EAP fornece predecessores com thresholds."""

    def _make_spec_sem_precedencia(self) -> dict:
        return {
            "activities": [
                {"item_id": "eap-1_0", "duration_weeks": 23, "required_resources": {}},
                {"item_id": "eap-1_1", "duration_weeks": 44, "required_resources": {}},
                {"item_id": "eap-1_7", "duration_weeks": 50, "required_resources": {}},
            ],
            "resource_pool": {},
            "precedence": [],  # VAZIO — deve derivar da EAP
            "deadline_weeks": 60,
        }

    def _make_eap_items(self):
        from concilium.domain.models.canonical import EapItem, PrecedenciaItem

        return [
            EapItem(
                item_id="eap-1_0", ordem=1, cpu_id="CPU-1", descricao="Desmatamento", unidade="m2", quantitativo=1000
            ),
            EapItem(
                item_id="eap-1_1",
                ordem=2,
                cpu_id="CPU-2",
                descricao="Esc1aCat",
                unidade="m3",
                quantitativo=500,
                predecessores=[PrecedenciaItem(item_id="eap-1_0", tipo="FS", lag=0, completion_threshold_pct=0.20)],
            ),
            EapItem(
                item_id="eap-1_7",
                ordem=3,
                cpu_id="CPU-7",
                descricao="CompactacaoPN",
                unidade="m3",
                quantitativo=800,
                predecessores=[PrecedenciaItem(item_id="eap-1_1", tipo="FS", lag=0, completion_threshold_pct=0.00)],
            ),
        ]

    def test_dag_derivado_tem_arestas_corretas(self):
        from concilium.application.skills.manifests._04_cronograma_skill_helpers import extract_dag_from_spec_or_eap  # noqa

        # Se a função não existir ainda, o teste falha com ImportError — esperado no TDD
        spec = self._make_spec_sem_precedencia()
        eap_items = self._make_eap_items()
        acts = [
            Activity(activity_id="eap-1_0", description="", duration_weeks=23),
            Activity(activity_id="eap-1_1", description="", duration_weeks=44),
            Activity(activity_id="eap-1_7", description="", duration_weeks=50),
        ]
        dag = extract_dag_from_spec_or_eap(spec, acts, eap_items)
        assert ("eap-1_0", "eap-1_1") in dag.precedence
        assert ("eap-1_1", "eap-1_7") in dag.precedence

    def test_dag_derivado_preserva_thresholds(self):
        from concilium.application.skills.manifests._04_cronograma_skill_helpers import extract_dag_from_spec_or_eap  # noqa

        spec = self._make_spec_sem_precedencia()
        eap_items = self._make_eap_items()
        acts = [
            Activity(activity_id="eap-1_0", description="", duration_weeks=23),
            Activity(activity_id="eap-1_1", description="", duration_weeks=44),
            Activity(activity_id="eap-1_7", description="", duration_weeks=50),
        ]
        dag = extract_dag_from_spec_or_eap(spec, acts, eap_items)
        assert dag.get_threshold("eap-1_0", "eap-1_1") == pytest.approx(0.20)
        assert dag.get_threshold("eap-1_1", "eap-1_7") == pytest.approx(0.00)

    def test_rcpsp_spec_precedence_prevalece_como_override(self):
        """Se rcpsp_spec.precedence tiver um par, ele substitui o valor da EAP."""
        from concilium.application.skills.manifests._04_cronograma_skill_helpers import extract_dag_from_spec_or_eap  # noqa

        spec = self._make_spec_sem_precedencia()
        # Override: par eap-1_0 → eap-1_1 com theta=1.0 (conservador)
        spec["precedence"] = [["eap-1_0", "eap-1_1", 1.0]]
        eap_items = self._make_eap_items()
        acts = [
            Activity(activity_id="eap-1_0", description="", duration_weeks=23),
            Activity(activity_id="eap-1_1", description="", duration_weeks=44),
            Activity(activity_id="eap-1_7", description="", duration_weeks=50),
        ]
        dag = extract_dag_from_spec_or_eap(spec, acts, eap_items)
        # Deve usar o override θ=1.0, não o θ=0.20 da EAP
        assert dag.get_threshold("eap-1_0", "eap-1_1") == pytest.approx(1.0)
        # Pair do EAP sem override mantém θ=0.0
        assert dag.get_threshold("eap-1_1", "eap-1_7") == pytest.approx(0.00)


# ─────────────────────────────────────────────────────────────────────────────
# F. Compatibilidade retroativa (θ=1.0 default)
# ─────────────────────────────────────────────────────────────────────────────


class TestCompatibilidadeRetroativa:
    def test_dag_sem_thresholds_comporta_se_como_antes(self):
        """DAG construído sem campo thresholds usa get_threshold=1.0 para todas as arestas."""
        acts = _make_activities([("A", 10), ("B", 5)])
        dag = ActivityDAG(activities=acts, precedence=[("A", "B")])
        # Sem thresholds, get_threshold deve retornar 1.0
        assert dag.get_threshold("A", "B") == pytest.approx(1.0)

    def test_scheduler_sem_thresholds_resulta_em_FS_classico(self):
        """SerialScheduler sem thresholds deve se comportar exatamente como antes."""
        acts = _make_activities([("A", 10), ("B", 5)])
        dag = ActivityDAG(activities=acts, precedence=[("A", "B")])
        sched = SerialScheduler("GR").schedule(acts, dag, ResourcePool(resources={}), deadline_weeks=20)
        a_end = next(s.end_week for s in sched.scheduled_activities if s.activity_id == "A")
        b_start = next(s.start_week for s in sched.scheduled_activities if s.activity_id == "B")
        assert b_start >= a_end  # FS clássico

    def test_predecessores_str_legado_usa_theta_um(self):
        """PrecedenciaItem derivado de string legada tem threshold=1.0."""
        from concilium.domain.models.canonical import EapItem

        item = EapItem(
            item_id="eap-1_1",
            ordem=2,
            cpu_id="C",
            descricao="d",
            unidade="m3",
            quantitativo=100,
            predecessores=["eap-1_0"],  # string legada
        )
        tipados = item.predecessores_tipados()
        assert len(tipados) == 1
        assert tipados[0].completion_threshold_pct == pytest.approx(1.0)


# ─────────────────────────────────────────────────────────────────────────────
# G. Testes de integração — thresholds AGIS derivados do Gantt
# ─────────────────────────────────────────────────────────────────────────────


class TestAGISGanttThresholds:
    """Verifica que os thresholds derivados do Gantt AGIS produzem um cronograma
    com início das atividades mais próximo das datas reais da obra."""

    def _gantt_thresholds(self) -> dict[tuple[str, str], float]:
        """Thresholds computados de (start_j - start_i) / duration_i do Gantt real."""
        return {
            ("eap-1_0", "eap-1_1"): 0.20,
            ("eap-1_0", "eap-1_2"): 0.20,
            ("eap-1_0", "eap-1_3"): 0.06,
            ("eap-1_0", "eap-1_4"): 0.06,
            ("eap-1_0", "eap-1_5"): 0.06,
            ("eap-1_0", "eap-1_6"): 0.06,
            ("eap-1_1", "eap-1_7"): 0.00,
            ("eap-1_2", "eap-1_7"): 0.00,
            ("eap-1_3", "eap-1_7"): 0.07,
            ("eap-1_4", "eap-1_7"): 0.07,
            ("eap-1_5", "eap-1_7"): 0.07,
            ("eap-1_6", "eap-1_7"): 0.07,
            ("eap-1_7", "eap-1_8"): 0.96,
            ("eap-1_3", "eap-1_9"): 0.00,
            ("eap-1_4", "eap-1_9"): 0.00,
            ("eap-1_5", "eap-1_9"): 0.00,
            ("eap-1_6", "eap-1_9"): 0.00,
            ("eap-1_5", "eap-1_10"): 0.95,
            ("eap-1_6", "eap-1_10"): 0.95,
            ("eap-1_9", "eap-1_10"): 0.89,
        }

    def _make_agis_activities(self) -> list[Activity]:
        """Atividades AGIS com durações aproximadas do Gantt (em semanas)."""
        return [
            Activity(activity_id="eap-1_0", description="Desmatamento", duration_weeks=23),
            Activity(activity_id="eap-1_1", description="Esc1aCat DMT2000", duration_weeks=44),
            Activity(activity_id="eap-1_2", description="Esc1aCat DMT3000", duration_weeks=44),
            Activity(activity_id="eap-1_3", description="Esc2aCat DMT2000", duration_weeks=50),
            Activity(activity_id="eap-1_4", description="Esc2aCat DMT3000", duration_weeks=50),
            Activity(activity_id="eap-1_5", description="Esc3aCat DMT2000", duration_weeks=48),
            Activity(activity_id="eap-1_6", description="Esc3aCat DMT3000", duration_weeks=48),
            Activity(activity_id="eap-1_7", description="CompactacaoPN", duration_weeks=50),
            Activity(activity_id="eap-1_8", description="CompactacaoPI", duration_weeks=2),
            Activity(activity_id="eap-1_9", description="CorpoAterro3aCat", duration_weeks=51),
            Activity(activity_id="eap-1_10", description="CompacFinalRocha", duration_weeks=6),
        ]

    def test_eap1_0_comeca_na_semana_1(self):
        acts = self._make_agis_activities()
        prec = list(self._gantt_thresholds().keys())
        dag = ActivityDAG(activities=acts, precedence=prec, thresholds=self._gantt_thresholds())
        topo = dag.topological_order()
        act_map = {a.activity_id: a for a in acts}
        earliest = _compute_earliest_starts(act_map, dag, topo)
        assert earliest["eap-1_0"] == 0

    def test_eap1_1_inicia_apos_20pct_desmatamento(self):
        """eap-1_1 deve aguardar 20% de eap-1_0 (duration=23): ceil(0.20×23)=5 semanas."""
        acts = self._make_agis_activities()
        prec = list(self._gantt_thresholds().keys())
        dag = ActivityDAG(activities=acts, precedence=prec, thresholds=self._gantt_thresholds())
        topo = dag.topological_order()
        act_map = {a.activity_id: a for a in acts}
        earliest = _compute_earliest_starts(act_map, dag, topo)
        expected = math.ceil(0.20 * 23)  # = 5
        assert earliest["eap-1_1"] == expected

    def test_eap1_3_inicia_apos_6pct_desmatamento(self):
        """eap-1_3 aguarda 6% de eap-1_0: ceil(0.06×23)=2 semanas."""
        acts = self._make_agis_activities()
        prec = list(self._gantt_thresholds().keys())
        dag = ActivityDAG(activities=acts, precedence=prec, thresholds=self._gantt_thresholds())
        topo = dag.topological_order()
        act_map = {a.activity_id: a for a in acts}
        earliest = _compute_earliest_starts(act_map, dag, topo)
        expected = math.ceil(0.06 * 23)  # = 2
        assert earliest["eap-1_3"] == expected

    def test_eap1_7_aguarda_threshold_de_esc2cat(self):
        """eap-1_7 deve aguardar 7% de eap-1_3 (50w): ceil(0.07×50)=4 semanas após eap-1_3."""
        acts = self._make_agis_activities()
        prec = list(self._gantt_thresholds().keys())
        dag = ActivityDAG(activities=acts, precedence=prec, thresholds=self._gantt_thresholds())
        topo = dag.topological_order()
        act_map = {a.activity_id: a for a in acts}
        earliest = _compute_earliest_starts(act_map, dag, topo)
        # eap-1_7 espera: max de todos predecessores
        # Binding: eap-1_3 ou eap-1_5 (ambos = ceil(0.06×23) + ceil(0.07×50))
        # eap-1_3 começa em 2, θ=0.07, d=50: 2 + ceil(0.07×50) = 2 + 4 = 6
        # eap-1_1 começa em 5, θ=0.00: 5 + 0 = 5
        # Binding deve ser 6
        e13_start = math.ceil(0.06 * 23)  # 2
        e17_from_e13 = e13_start + math.ceil(0.07 * 50)  # 2 + 4 = 6
        e11_start = math.ceil(0.20 * 23)  # 5
        e17_from_e11 = e11_start + math.ceil(0.00 * 44)  # 5 + 0 = 5
        expected_e17 = max(e17_from_e13, e17_from_e11)  # = 6
        assert earliest["eap-1_7"] == expected_e17

    def test_eap1_10_inicio_tardio_garante_desmob_antecipada_efetiva(self):
        """eap-1_10 só começa após 89% de eap-1_9 (51w): início em semana ≥ 45.
        Isso resolve o problema do ATERRO-04 idle que dependia de uma constraint manual."""
        acts = self._make_agis_activities()
        prec = list(self._gantt_thresholds().keys())
        dag = ActivityDAG(activities=acts, precedence=prec, thresholds=self._gantt_thresholds())
        topo = dag.topological_order()
        act_map = {a.activity_id: a for a in acts}
        earliest = _compute_earliest_starts(act_map, dag, topo)
        # eap-1_9 starts early (week 2 via eap-1_3), duration 51: θ(eap-1_9→eap-1_10)=0.89
        # binding: eap-1_9_start + ceil(0.89 × 51) ≈ 2 + 46 = 48
        e19_start = earliest["eap-1_9"]
        from_e19 = e19_start + math.ceil(0.89 * 51)
        from_e56 = math.ceil(0.06 * 23) + math.ceil(0.95 * 48)
        expected = max(from_e19, from_e56)
        assert earliest["eap-1_10"] >= 40  # tarde o suficiente para evitar ATERRO-04 idle
        assert earliest["eap-1_10"] == expected


# ─────────────────────────────────────────────────────────────────────────────
# H. NEP-031 L4: SS/FF precedence types and short precedence entry guard
# ─────────────────────────────────────────────────────────────────────────────


class TestSSFFPrecedenceTypes:
    """Cover lines 53-57 (SS/FF tipo path) and line 62 (len(p) < 2 guard)."""

    def _make_eap_items_ss_ff(self):
        """EAP items with SS and FF typed predecessors."""
        from concilium.domain.models.canonical import EapItem, PrecedenciaItem

        return [
            EapItem(item_id="ACT-A", ordem=1, cpu_id="CPU-1", descricao="A", unidade="m3", quantitativo=100),
            EapItem(
                item_id="ACT-B",
                ordem=2,
                cpu_id="CPU-2",
                descricao="B",
                unidade="m3",
                quantitativo=50,
                predecessores=[PrecedenciaItem(item_id="ACT-A", tipo="SS", lag=2, completion_threshold_pct=1.0)],
            ),
            EapItem(
                item_id="ACT-C",
                ordem=3,
                cpu_id="CPU-3",
                descricao="C",
                unidade="m3",
                quantitativo=80,
                predecessores=[PrecedenciaItem(item_id="ACT-A", tipo="FF", lag=0, completion_threshold_pct=1.0)],
            ),
        ]

    def test_ss_type_goes_into_extended_precedences(self):
        """Lines 53-57: SS tipo creates entry in extended_precedences."""
        from concilium.application.skills.manifests._04_cronograma_skill_helpers import extract_dag_from_spec_or_eap

        acts = [
            Activity(activity_id="ACT-A", description="A", duration_weeks=10),
            Activity(activity_id="ACT-B", description="B", duration_weeks=5),
            Activity(activity_id="ACT-C", description="C", duration_weeks=8),
        ]
        spec = {"precedence": []}
        eap_items = self._make_eap_items_ss_ff()
        dag = extract_dag_from_spec_or_eap(spec, acts, eap_items)

        # SS/FF still create sentinel entries in precedence (for topological ordering)
        assert ("ACT-A", "ACT-B") in dag.precedence
        assert ("ACT-A", "ACT-C") in dag.precedence
        # And extended_precedences holds the SS/FF specifics
        assert len(dag.extended_precedences) == 2
        tipos = {ep.tipo for ep in dag.extended_precedences}
        assert "SS" in tipos
        assert "FF" in tipos

    def test_ff_type_lag_preserved(self):
        """FF typed predecessor with lag=0 ends up in extended_precedences with lag=0."""
        from concilium.application.skills.manifests._04_cronograma_skill_helpers import extract_dag_from_spec_or_eap
        from concilium.domain.models.canonical import EapItem, PrecedenciaItem

        eap_items = [
            EapItem(item_id="P", ordem=1, cpu_id="C1", descricao="P", unidade="m", quantitativo=1),
            EapItem(
                item_id="S",
                ordem=2,
                cpu_id="C2",
                descricao="S",
                unidade="m",
                quantitativo=1,
                predecessores=[PrecedenciaItem(item_id="P", tipo="FF", lag=3, completion_threshold_pct=1.0)],
            ),
        ]
        acts = [
            Activity(activity_id="P", description="P", duration_weeks=10),
            Activity(activity_id="S", description="S", duration_weeks=5),
        ]
        dag = extract_dag_from_spec_or_eap({"precedence": []}, acts, eap_items)
        ff_entries = [ep for ep in dag.extended_precedences if ep.tipo == "FF"]
        assert len(ff_entries) == 1
        assert ff_entries[0].lag == 3

    def test_short_precedence_entry_is_skipped(self):
        """Line 62: precedence entries with len < 2 are ignored without error."""
        from concilium.application.skills.manifests._04_cronograma_skill_helpers import extract_dag_from_spec_or_eap

        acts = [
            Activity(activity_id="X", description="X", duration_weeks=5),
            Activity(activity_id="Y", description="Y", duration_weeks=3),
        ]
        # Include an entry with only 1 element (should be skipped by the guard)
        spec = {"precedence": [["X"], ["X", "Y"]]}
        dag = extract_dag_from_spec_or_eap(spec, acts, eap_items=None)
        # Only the valid 2-element entry should create an edge
        assert ("X", "Y") in dag.precedence
        # The single-element entry should be silently ignored (no crash)
        assert len(dag.precedence) == 1
