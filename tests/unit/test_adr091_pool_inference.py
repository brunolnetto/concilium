"""ADR-091: Pool mínimo como variável de otimização — testes.

Cobre os três objetivos (minimizar_prazo / minimizar_custo / balanceado),
restrições de mercado, idempotência do wrapper de spec e backward compat
(pool explícito como override).
"""

from types import SimpleNamespace

from concilium.application.scheduling import (
    Activity,
    ActivityDAG,
    ResourcePool,
    SerialScheduler,
    derivar_required_resources,
    inferir_pool_minimo,
    inferir_pool_minimo_from_spec,
    tipo_recurso_de_equip,
    validar_equipamentos_mapeaveis,
)


def _equipe(item_id, equipamentos, num_equipes_base=1):
    """Stub de EquipeDireta: item_id + equipamentos [(equip_id, num_unidades)]."""
    return SimpleNamespace(
        item_id=item_id,
        num_equipes_base=num_equipes_base,
        equipamentos=[SimpleNamespace(equip_id=eid, num_unidades=n) for eid, n in equipamentos],
    )


def _two_parallel_dag() -> tuple[list[Activity], ActivityDAG]:
    """Duas atividades independentes que disputam o mesmo recurso 'EQ'.

    Cada uma exige 2×EQ por 3 semanas, sem precedência entre elas.
      - Paralelo (pool=4): makespan 3 semanas.
      - Serial  (pool=2): makespan 6 semanas.
    """
    acts = [
        Activity("A", "Atividade A", 3, {"EQ": 2}),
        Activity("B", "Atividade B", 3, {"EQ": 2}),
    ]
    dag = ActivityDAG(activities=acts, precedence=[])
    return acts, dag


class TestObjetivos:
    def test_minimizar_prazo_usa_peak_demand(self):
        acts, dag = _two_parallel_dag()
        pool, diag = inferir_pool_minimo(acts, dag, {"objetivo": "minimizar_prazo"})
        # paralelismo total: 2+2 = 4 unidades de EQ
        assert pool["EQ"] == 4
        assert diag["peak_demand"]["EQ"] == 4
        assert diag["makespan_minimo_semanas"] == 3

    def test_minimizar_custo_usa_serial_min(self):
        acts, dag = _two_parallel_dag()
        pool, diag = inferir_pool_minimo(acts, dag, {"objetivo": "minimizar_custo"})
        # só o suficiente para a atividade mais exigente: 2
        assert pool["EQ"] == 2
        assert diag["serial_min"]["EQ"] == 2

    def test_balanceado_respeita_prazo_maximo(self):
        acts, dag = _two_parallel_dag()
        # prazo apertado (3sem) força paralelismo → pool=4
        pool_rapido, _ = inferir_pool_minimo(acts, dag, {"objetivo": "balanceado", "prazo_maximo_semanas": 3})
        assert pool_rapido["EQ"] == 4
        # prazo folgado (6sem) permite serial → pool=2 (mais barato)
        pool_barato, _ = inferir_pool_minimo(acts, dag, {"objetivo": "balanceado", "prazo_maximo_semanas": 6})
        assert pool_barato["EQ"] == 2

    def test_balanceado_sem_prazo_recai_em_peak(self):
        acts, dag = _two_parallel_dag()
        pool, _ = inferir_pool_minimo(acts, dag, {"objetivo": "balanceado"})
        assert pool["EQ"] == 4


class TestRestricoesMercado:
    def test_teto_de_mercado_limita_pool(self):
        acts, dag = _two_parallel_dag()
        pool, diag = inferir_pool_minimo(
            acts,
            dag,
            {"objetivo": "minimizar_prazo", "restricoes_mercado": {"EQ": 3}},
        )
        assert pool["EQ"] == 3
        assert any("restrição de mercado" in n for n in diag["notas"])

    def test_teto_abaixo_do_minimo_viavel_sinaliza(self):
        acts, dag = _two_parallel_dag()
        _pool, diag = inferir_pool_minimo(
            acts,
            dag,
            {"objetivo": "minimizar_custo", "restricoes_mercado": {"EQ": 1}},
        )
        assert any("inviável" in n.lower() for n in diag["notas"])


class TestFromSpec:
    def _spec(self, objetivo: str = "balanceado") -> dict:
        return {
            "deadline_weeks": 3,
            "activities": [
                {"item_id": "A", "descricao": "A", "duration_weeks": 3, "required_resources": {"EQ": 2}},
                {"item_id": "B", "descricao": "B", "duration_weeks": 3, "required_resources": {"EQ": 2}},
            ],
            "precedence": [],
            "pool_config": {"objetivo": objetivo},
        }

    def test_from_spec_infere_pool(self):
        pool, diag = inferir_pool_minimo_from_spec(self._spec("minimizar_prazo"))
        assert pool == {"EQ": 4}
        assert diag["objetivo"] == "minimizar_prazo"

    def test_from_spec_balanceado_usa_deadline_como_prazo(self):
        # deadline_weeks=3 (apertado) → balanceado deve paralelizar
        pool, _ = inferir_pool_minimo_from_spec(self._spec("balanceado"))
        assert pool == {"EQ": 4}

    def test_idempotente(self):
        spec = self._spec("minimizar_custo")
        p1, _ = inferir_pool_minimo_from_spec(spec)
        p2, _ = inferir_pool_minimo_from_spec(spec)
        assert p1 == p2

    def test_spec_sem_atividades(self):
        pool, diag = inferir_pool_minimo_from_spec({"activities": []})
        assert pool == {}
        assert "notas" in diag


class TestPrecedenciaComThreshold:
    def test_precedencia_serializa_e_reduz_peak(self):
        # A → B (FS estrito): nunca concorrem, peak = max single = 2
        acts = [
            Activity("A", "A", 3, {"EQ": 2}),
            Activity("B", "B", 3, {"EQ": 2}),
        ]
        dag = ActivityDAG(activities=acts, precedence=[("A", "B")])
        pool, diag = inferir_pool_minimo(acts, dag, {"objetivo": "minimizar_prazo"})
        assert pool["EQ"] == 2
        assert diag["peak_demand"]["EQ"] == 2


class TestFase1DerivacaoEquipTipo:
    def test_tipo_recurso_convencao_default(self):
        assert tipo_recurso_de_equip("ESC-3CAT") == "EQUIP-ESC-3CAT"

    def test_tipo_recurso_mapa_explicito(self):
        m = {"ESC-3CAT": "ESCAVADEIRA"}
        assert tipo_recurso_de_equip("ESC-3CAT", m) == "ESCAVADEIRA"

    def test_derivar_required_resources_soma_por_tipo(self):
        equipes = [
            _equipe("eap-1", [("ESC-3CAT", 2), ("CAMINHAO", 3)]),
            _equipe("eap-2", [("ESC-3CAT", 1)], num_equipes_base=2),
        ]
        req, avisos = derivar_required_resources(equipes)
        assert req["eap-1"] == {"EQUIP-ESC-3CAT": 2, "EQUIP-CAMINHAO": 3}
        # num_equipes_base=2 multiplica a demanda concorrente
        assert req["eap-2"] == {"EQUIP-ESC-3CAT": 2}
        assert avisos == []  # sem mapa explícito → convenção, sem avisos

    def test_derivar_emite_aviso_quando_mapa_incompleto(self):
        equipes = [_equipe("eap-1", [("ESC-3CAT", 1)])]
        req, avisos = derivar_required_resources(equipes, equip_tipo_map={"OUTRO": "X"})
        assert req["eap-1"] == {"EQUIP-ESC-3CAT": 1}
        assert any("ESC-3CAT" in a for a in avisos)

    def test_validar_equipamentos_mapeaveis(self):
        equipes = [_equipe("eap-1", [("ESC-3CAT", 1), ("CAMINHAO", 2)])]
        # mapa completo → sem faltantes
        assert validar_equipamentos_mapeaveis(equipes, {"ESC-3CAT": "A", "CAMINHAO": "B"}) == []
        # mapa incompleto → reporta faltante
        assert validar_equipamentos_mapeaveis(equipes, {"ESC-3CAT": "A"}) == ["CAMINHAO"]
        # mapa None → validação desligada
        assert validar_equipamentos_mapeaveis(equipes, None) == []

    def test_from_spec_deriva_required_de_equipes(self):
        # spec sem required_resources nas atividades; equipes suprem e_{i,r}
        spec = {
            "deadline_weeks": 3,
            "activities": [
                {"item_id": "A", "duration_weeks": 3},
                {"item_id": "B", "duration_weeks": 3},
            ],
            "precedence": [],
            "pool_config": {"objetivo": "minimizar_prazo"},
        }
        equipes = [
            _equipe("A", [("EQ", 2)]),
            _equipe("B", [("EQ", 2)]),
        ]
        pool, diag = inferir_pool_minimo_from_spec(spec, equipes=equipes)
        # paralelas, 2+2 unidades do tipo EQUIP-EQ
        assert pool == {"EQUIP-EQ": 4}


class TestFase4PoolConfig:
    def test_pool_config_na_spec_dirige_objetivo(self):
        spec = {
            "deadline_weeks": 6,
            "activities": [
                {"item_id": "A", "duration_weeks": 3, "required_resources": {"EQ": 2}},
                {"item_id": "B", "duration_weeks": 3, "required_resources": {"EQ": 2}},
            ],
            "precedence": [],
            "pool_config": {"objetivo": "minimizar_custo"},
        }
        pool, _ = inferir_pool_minimo_from_spec(spec)
        assert pool == {"EQ": 2}


class TestPoolInferidoEhFactivel:
    def test_pool_inferido_produz_schedule_factivel(self):
        acts, dag = _two_parallel_dag()
        for obj in ("minimizar_prazo", "minimizar_custo", "balanceado"):
            pool, _ = inferir_pool_minimo(acts, dag, {"objetivo": obj, "prazo_maximo_semanas": 6})
            sched = SerialScheduler("MINSLK").schedule(
                activities=acts,
                dag=dag,
                pool=ResourcePool(resources=pool),
                deadline_weeks=20,
            )
            assert sched.feasible


# ── Missing-line coverage additions ──────────────────────────────────────────


class TestPeakDemandEdgeCases:
    """Covers uncovered branches in _peak_demand and _bisect_pool."""

    def test_peak_demand_empty_scheduled_returns_zero_peaks(self):
        """Line 73: _peak_demand returns early when acts is empty."""
        from concilium.application.scheduling.pool_inference import _peak_demand
        from unittest.mock import MagicMock

        sched = MagicMock()
        sched.scheduled_activities = []
        result = _peak_demand(sched, ["EQ"])
        assert result == {"EQ": 0}

    def test_bisect_pool_peak_cannot_meet_deadline(self):
        """Line 118: when even peak_demand pool can't meet prazo_max, returns peak."""
        from concilium.application.scheduling.pool_inference import _bisect_pool
        from concilium.application.scheduling import Activity, ActivityDAG

        # 3 independent activities each needing 2 EQ, total EQ demand = 6
        acts = [
            Activity("A", "A", 4, {"EQ": 2}),
            Activity("B", "B", 4, {"EQ": 2}),
            Activity("C", "C", 4, {"EQ": 2}),
        ]
        dag = ActivityDAG(activities=acts, precedence=[])
        serial = {"EQ": 2}  # serial_min
        peak = {"EQ": 6}    # parallelism max
        # prazo_max=1 is impossibly tight — even peak can't do it
        result = _bisect_pool(acts, dag, serial, peak, prazo_max=1, horizon=100)
        # Falls back to peak when peak cannot meet prazo_max
        assert result == {"EQ": 6}


class TestInferirPoolMinimoScheduleError:
    """Line 166-167: ScheduleError during unlimited schedule falls back to serial_min."""

    def test_schedule_error_fallback_to_serial(self):
        """When SerialScheduler raises ScheduleError on unlimited run, peak = serial_min."""
        from unittest.mock import patch, MagicMock
        from concilium.application.scheduling.pool_inference import inferir_pool_minimo
        from concilium.application.scheduling import Activity, ActivityDAG
        from concilium.application.scheduling.models import ScheduleError

        acts, dag = _two_parallel_dag()

        with patch(
            "concilium.application.scheduling.pool_inference.SerialScheduler"
        ) as MockScheduler:
            instance = MockScheduler.return_value
            instance.schedule.side_effect = ScheduleError("forced error")
            pool, diag = inferir_pool_minimo(acts, dag, {"objetivo": "minimizar_prazo"})

        # Falls back to serial_min when unlimited schedule fails
        assert pool == diag["serial_min"]


class TestActivitiesFromSpecEdgeCases:
    """Lines 213, 216: _activities_from_spec skips non-dict items and items without item_id."""

    def test_non_dict_activity_skipped(self):
        """Line 213: non-dict entry in spec['activities'] is skipped."""
        from concilium.application.scheduling.pool_inference import _activities_from_spec

        spec = {
            "activities": [
                "not-a-dict",
                None,
                42,
                {"item_id": "A", "duration_weeks": 3, "required_resources": {"EQ": 1}},
            ]
        }
        acts = _activities_from_spec(spec)
        assert len(acts) == 1
        assert acts[0].activity_id == "A"

    def test_activity_without_item_id_skipped(self):
        """Line 216: activity dict without item_id is skipped."""
        from concilium.application.scheduling.pool_inference import _activities_from_spec

        spec = {
            "activities": [
                {"duration_weeks": 5, "required_resources": {"EQ": 2}},  # no item_id
                {"item_id": "", "duration_weeks": 3},  # empty item_id
                {"item_id": "B", "duration_weeks": 2, "required_resources": {"EQ": 1}},
            ]
        }
        acts = _activities_from_spec(spec)
        assert len(acts) == 1
        assert acts[0].activity_id == "B"


class TestDagFromSpecEdgeCases:
    """Lines 238-248: _dag_from_spec handles invalid edges and threshold parse errors."""

    def test_short_edge_skipped(self):
        """Line 238: edge with fewer than 2 elements is skipped."""
        from concilium.application.scheduling.pool_inference import (
            _dag_from_spec,
            _activities_from_spec,
        )

        spec_acts = [
            {"item_id": "A", "duration_weeks": 2, "required_resources": {"EQ": 1}},
            {"item_id": "B", "duration_weeks": 2, "required_resources": {"EQ": 1}},
        ]
        acts = _activities_from_spec({"activities": spec_acts})
        spec = {
            "precedence": [
                ["A"],          # only 1 element — skipped
                ("A", "B"),     # valid
                [],             # 0 elements — skipped
            ]
        }
        dag = _dag_from_spec(spec, acts)
        assert ("A", "B") in dag.precedence

    def test_edge_with_unknown_activity_skipped(self):
        """Line 241-242: edge referencing unknown activity ID is skipped."""
        from concilium.application.scheduling.pool_inference import (
            _dag_from_spec,
            _activities_from_spec,
        )

        spec_acts = [
            {"item_id": "A", "duration_weeks": 2, "required_resources": {"EQ": 1}},
        ]
        acts = _activities_from_spec({"activities": spec_acts})
        spec = {"precedence": [("A", "NONEXISTENT"), ("NONEXISTENT", "A")]}
        dag = _dag_from_spec(spec, acts)
        assert dag.precedence == []

    def test_threshold_parse_error_skipped(self):
        """Lines 245-248: invalid threshold value (non-numeric) is silently skipped."""
        from concilium.application.scheduling.pool_inference import (
            _dag_from_spec,
            _activities_from_spec,
        )

        spec_acts = [
            {"item_id": "A", "duration_weeks": 2, "required_resources": {"EQ": 1}},
            {"item_id": "B", "duration_weeks": 2, "required_resources": {"EQ": 1}},
        ]
        acts = _activities_from_spec({"activities": spec_acts})
        spec = {"precedence": [("A", "B", "not-a-float")]}
        dag = _dag_from_spec(spec, acts)
        # Edge is added but threshold parse fails → no entry in thresholds
        assert ("A", "B") in dag.precedence
        assert ("A", "B") not in dag.thresholds

    def test_threshold_none_skipped(self):
        """Line 246-248: threshold=None raises TypeError → silently skipped."""
        from concilium.application.scheduling.pool_inference import (
            _dag_from_spec,
            _activities_from_spec,
        )

        spec_acts = [
            {"item_id": "A", "duration_weeks": 2, "required_resources": {"EQ": 1}},
            {"item_id": "B", "duration_weeks": 2, "required_resources": {"EQ": 1}},
        ]
        acts = _activities_from_spec({"activities": spec_acts})
        spec = {"precedence": [("A", "B", None)]}
        dag = _dag_from_spec(spec, acts)
        assert ("A", "B") in dag.precedence
        assert ("A", "B") not in dag.thresholds


class TestDerivarRequiredResourcesEdgeCases:
    """Lines 300, 307: skip equipes with empty item_id and equipamentos with n_unid <= 0."""

    def test_equipe_without_item_id_skipped(self):
        """Line 300: equipe with empty item_id is skipped."""
        from concilium.application.scheduling import derivar_required_resources
        from types import SimpleNamespace

        equip = SimpleNamespace(equip_id="ESC", num_unidades=2)
        eq_no_id = SimpleNamespace(item_id="", num_equipes_base=1, equipamentos=[equip])
        req, avisos = derivar_required_resources([eq_no_id])
        assert req == {}

    def test_equipe_with_none_item_id_skipped(self):
        """Line 300: equipe with None item_id is skipped."""
        from concilium.application.scheduling import derivar_required_resources
        from types import SimpleNamespace

        eq_none_id = SimpleNamespace(item_id=None, num_equipes_base=1, equipamentos=[])
        req, avisos = derivar_required_resources([eq_none_id])
        assert req == {}

    def test_equipamento_with_zero_units_skipped(self):
        """Line 307: equipamento with num_unidades=0 is skipped."""
        from concilium.application.scheduling import derivar_required_resources
        from types import SimpleNamespace

        equip_zero = SimpleNamespace(equip_id="ESC", num_unidades=0)
        equip_neg = SimpleNamespace(equip_id="CAM", num_unidades=-1)
        equip_valid = SimpleNamespace(equip_id="PIPA", num_unidades=1)
        eq = SimpleNamespace(item_id="eap-1", num_equipes_base=1, equipamentos=[equip_zero, equip_neg, equip_valid])
        req, _ = derivar_required_resources([eq])
        # Only PIPA contributes
        assert req == {"eap-1": {"EQUIP-PIPA": 1}}

    def test_equipamento_with_empty_equip_id_skipped(self):
        """Line 307: equip_id='' is skipped."""
        from concilium.application.scheduling import derivar_required_resources
        from types import SimpleNamespace

        equip_no_id = SimpleNamespace(equip_id="", num_unidades=3)
        eq = SimpleNamespace(item_id="eap-2", num_equipes_base=1, equipamentos=[equip_no_id])
        req, _ = derivar_required_resources([eq])
        assert req == {"eap-2": {}}
