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
        equipamentos=[
            SimpleNamespace(equip_id=eid, num_unidades=n) for eid, n in equipamentos
        ],
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
        pool_rapido, _ = inferir_pool_minimo(
            acts, dag, {"objetivo": "balanceado", "prazo_maximo_semanas": 3}
        )
        assert pool_rapido["EQ"] == 4
        # prazo folgado (6sem) permite serial → pool=2 (mais barato)
        pool_barato, _ = inferir_pool_minimo(
            acts, dag, {"objetivo": "balanceado", "prazo_maximo_semanas": 6}
        )
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
        assert validar_equipamentos_mapeaveis(
            equipes, {"ESC-3CAT": "A", "CAMINHAO": "B"}
        ) == []
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
