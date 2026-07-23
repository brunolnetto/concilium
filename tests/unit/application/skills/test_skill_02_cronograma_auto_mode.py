"""Testes da Skill 02 — Modo AUTO (ADR-004 weekly scheduling, ex-02B)."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

from concilium.application.skills import run_catalogo_de_recursos, run_cronograma, run_escopo_e_eap
from concilium.domain.models.canonical import (
    ActivityDag,
    ArestaActivityDag,
    Atividade,
    CanonicalModel,
    ScheduledActivityCanonical,
)

run_escopo_e_eap = run_escopo_e_eap


# Skills atividades/sequenciamento foram fundidas em escopo_consolidado.
def run_atividades(canonical, inputs):
    return run_escopo_e_eap(canonical, inputs or {})


def run_sequenciamento(canonical, inputs):
    return run_escopo_e_eap(canonical, inputs or {})


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_canonical(
    num_activities: int = 3,
    pool_resources: dict | None = None,
    deadline_days: int = 90,
    add_dag: bool = False,
) -> CanonicalModel:
    """Build a minimal CanonicalModel for skill 02 AUTO mode testing."""
    inputs = {
        "nome": "Test 02 Auto",
        "tipo_obra": "terraplenagem",
        "localizacao": "Test, CE",
        "coordenadas": {"lat": -4.0, "lng": -38.0},
        "regime_trabalho": {"dias_semana": 5, "horas_dia": 8},
        "data_inicio": "2026-06-01",
        "data_termino": (date(2026, 6, 1) + timedelta(days=deadline_days)).isoformat(),
        "eap": [
            {
                "item_id": f"eap-{i:02d}",
                "ordem": i,
                "cpu_id": f"CPU-{i:02d}",
                "descricao": f"Item {i}",
                "unidade": "m3",
                "quantitativo": 1000.0 * i,
            }
            for i in range(1, num_activities + 1)
        ],
        "contexto_id": "test",
        "snapshot_catalogo_id": "snap-cat",
        "snapshot_perfil_id": "snap-perfil",
    }
    canonical = run_escopo_e_eap(None, inputs, catalogo=None).canonical

    activities = [
        Atividade(
            atividade_id=f"act-{i:02d}",
            eap_item_id=f"eap-{i:02d}",
            descricao=f"Atividade {i}",
            fracao_quantitativo=1.0,
            quantitativo_atividade=1000.0 * i,
            cpu_id=f"CPU-{i:02d}",
        )
        for i in range(1, num_activities + 1)
    ]
    update: dict = {"atividades": activities}

    if add_dag:
        ids = [f"act-{i:02d}" for i in range(1, num_activities + 1)]
        edges = [ArestaActivityDag(de=ids[i], para=ids[i + 1]) for i in range(len(ids) - 1)]
        update["activity_dag"] = ActivityDag(
            nos=ids,
            arestas=edges,
            ordem_topologica=ids,
        )

    canonical = canonical.model_copy(update=update)

    if pool_resources:
        canonical = run_catalogo_de_recursos(
            canonical,
            {
                "tipos_recurso": [
                    {
                        "tipo_id": tid,
                        "nome": tid.capitalize(),
                        "categoria": "EQUIPAMENTO",
                        "custo_unitario_dia": 1000,
                    }
                    for tid in pool_resources
                ],
                "pool_inicial": [{"tipo_id": tid, "quantidade_total": qty} for tid, qty in pool_resources.items()],
            },
        ).canonical

    return canonical


# ── integration tests ──────────────────────────────────────────────────────────


def test_02_auto_gera_cronograma(inputs_escopo_terraplenagem):
    """Smoke test: AUTO mode generates a valid cronograma with scheduled_activities."""
    base_inputs = {
        **inputs_escopo_terraplenagem,
        "contexto_id": "test",
        "snapshot_catalogo_id": "snap-cat",
        "snapshot_perfil_id": "snap-perfil",
    }
    canonical = run_escopo_e_eap(None, base_inputs, catalogo=None).canonical
    canonical = run_atividades(canonical, {}).canonical
    canonical = run_sequenciamento(canonical, {}).canonical
    canonical = run_catalogo_de_recursos(
        canonical,
        {
            "tipos_recurso": [
                {
                    "tipo_id": "escavadeira",
                    "nome": "Escavadeira",
                    "categoria": "EQUIPAMENTO",
                    "custo_unitario_dia": 1200,
                }
            ],
            "pool_inicial": [{"tipo_id": "escavadeira", "quantidade_total": 2}],
        },
    ).canonical

    result = run_cronograma(canonical, {"top_n": 3})
    assert result.canonical.cronograma is not None
    assert len(result.canonical.cronograma.scheduled_activities) >= 1
    assert any(v.codigo == "VAL-CRON-OK" for v in result.validacoes)


# ── unit tests ────────────────────────────────────────────────────────────────


def test_02_auto_sem_atividades_retorna_erro():
    """Skill returns ERRO when canonical has no activities and no EAP."""
    canonical = _make_canonical(num_activities=0)
    canonical = canonical.model_copy(update={"eap": [], "atividades": None})
    result = run_cronograma(canonical, {})
    erros = [v for v in result.validacoes if v.status == "ERRO"]
    assert erros, "Expected ERRO when no activities and no EAP"


def test_02_auto_gera_scheduled_activities():
    """AUTO mode populates canonical.cronograma with scheduled_activities."""
    canonical = _make_canonical(num_activities=3, deadline_days=30)
    result = run_cronograma(canonical, {"top_n": 3, "deadline_weeks": 30})

    assert result.canonical.cronograma is not None
    assert len(result.canonical.cronograma.scheduled_activities) >= 1
    for sa in result.canonical.cronograma.scheduled_activities:
        assert isinstance(sa, ScheduledActivityCanonical)


def test_02_auto_scheduled_activities_tem_campos():
    """Each scheduled activity has required temporal fields."""
    canonical = _make_canonical(num_activities=2, deadline_days=20)
    result = run_cronograma(canonical, {"deadline_weeks": 15})

    assert result.canonical.cronograma is not None
    for sa in result.canonical.cronograma.scheduled_activities:
        assert sa.activity_id, "activity_id must be set"
        assert sa.start_week >= 0
        assert sa.end_week >= sa.start_week
        assert sa.duration_weeks >= 1


def test_02_auto_validacoes_ok_quando_feasivel():
    """On success, VAL-SCHED-OK and VAL-CRON-OK are emitted."""
    canonical = _make_canonical(num_activities=3, deadline_days=52)
    result = run_cronograma(canonical, {"deadline_weeks": 52})

    ok_codes = {v.codigo for v in result.validacoes if v.status == "OK"}
    assert "VAL-SCHED-OK" in ok_codes, "Expected VAL-SCHED-OK on feasible schedule"
    assert "VAL-CRON-OK" in ok_codes, "Expected VAL-CRON-OK on completion"


def test_02_auto_top_n_aceito():
    """top_n parameter is accepted without error."""
    canonical = _make_canonical(num_activities=4, deadline_days=40)
    result = run_cronograma(canonical, {"top_n": 2, "deadline_weeks": 40})
    assert result.canonical.cronograma is not None


def test_02_auto_relaxacao_explicita():
    """When explore_schedules fails first call, pool is relaxed and VAL-SCHED-03 emitted."""
    from concilium.application.scheduling import explore_schedules as real_explore

    call_count = [0]

    def fake_explore(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return []
        return real_explore(*args, **kwargs)

    canonical = _make_canonical(num_activities=2, deadline_days=20)

    target = "concilium.application.skills.cronograma._mod_validacao.explore_schedules"
    with patch(target, side_effect=fake_explore):
        result = run_cronograma(canonical, {"deadline_weeks": 20})

    aviso_codes = {v.codigo for v in result.validacoes if v.status == "AVISO"}
    assert "VAL-SCHED-03" in aviso_codes, "Expected VAL-SCHED-03 pool relaxation warning"
    assert call_count[0] == 2, "explore_schedules must be called twice (nominal + relaxed)"


def test_02_auto_infeasivel_quando_tudo_falha():
    """When all fallback steps fail, VAL-SCHED-05 ERRO is returned."""

    def always_empty(*args, **kwargs):
        return []

    canonical = _make_canonical(num_activities=2, deadline_days=20)

    target = "concilium.application.skills.cronograma._mod_validacao.explore_schedules"
    with patch(target, side_effect=always_empty):
        result = run_cronograma(canonical, {"deadline_weeks": 20})

    erros = [v for v in result.validacoes if v.status == "ERRO" and v.codigo == "VAL-SCHED-05"]
    assert erros, "Expected VAL-SCHED-05 ERRO when infeasible"
    assert result.canonical.cronograma is None, "cronograma must not be set when infeasible"


def test_02_auto_algorithm_override():
    """algorithm input is forwarded to strategy selection without error."""
    canonical = _make_canonical(num_activities=3, deadline_days=30)
    result = run_cronograma(canonical, {"deadline_weeks": 30, "algorithm": "SerialScheduler", "top_n": 1})
    assert result.canonical.cronograma is not None


def test_02_auto_com_dag_explicita():
    """AUTO mode works correctly when activity_dag is explicitly set."""
    canonical = _make_canonical(num_activities=3, deadline_days=30, add_dag=True)
    result = run_cronograma(canonical, {"deadline_weeks": 30})
    assert result.canonical.cronograma is not None
    assert len(result.canonical.cronograma.scheduled_activities) >= 1


def test_02_auto_eap_fallback_sem_atividades():
    """When atividades is None, EAP items are used as activities."""
    canonical = _make_canonical(num_activities=3, deadline_days=30)
    canonical = canonical.model_copy(update={"atividades": None})
    result = run_cronograma(canonical, {"deadline_weeks": 30})
    assert result.canonical.cronograma is not None
    assert len(result.canonical.cronograma.scheduled_activities) == 3


def test_02_auto_distribuicao_mensal_gerada():
    """AUTO mode populates distribuicao_mensal from the weekly schedule."""
    canonical = _make_canonical(num_activities=2, deadline_days=30)
    result = run_cronograma(canonical, {"deadline_weeks": 12})
    assert result.canonical.cronograma is not None
    assert isinstance(result.canonical.cronograma.distribuicao_mensal, dict)


def test_02_auto_algorithm_registrado_no_cronograma():
    """The algorithm used is stored in canonical.cronograma.algorithm."""
    canonical = _make_canonical(num_activities=2, deadline_days=30)
    result = run_cronograma(canonical, {"deadline_weeks": 20})
    assert result.canonical.cronograma is not None
    assert result.canonical.cronograma.algorithm != "manual_allocation"


def test_02_auto_assigned_resources_propagated_from_rcpsp_spec():
    """assigned_resources from rcpsp_spec must appear in final scheduled_activities.

    Regression guard for the bug where _build_scheduled_activities created a
    new ScheduledActivityCanonical without copying assigned_resources from the
    intermediate ScheduleCandidateCanonical, leaving all entries as {}.
    """
    # Build a 2-item canonical whose EAP IDs match the rcpsp_spec item_ids.
    canonical = _make_canonical(num_activities=2, deadline_days=60)

    rcpsp_spec = {
        "activities": [
            {
                "item_id": "eap-01",
                "descricao": "Atividade 1",
                "duration_weeks": 4,
                "required_resources": {"maq": 2},
            },
            {
                "item_id": "eap-02",
                "descricao": "Atividade 2",
                "duration_weeks": 3,
                "required_resources": {"maq": 1},
            },
        ],
        "resource_pool": {"maq": 3},
        "precedence": [],
        "deadline_weeks": 8,
    }

    result = run_cronograma(canonical, {"rcpsp_spec": rcpsp_spec})
    assert result.canonical.cronograma is not None, "cronograma must be produced"

    sched = {sa.activity_id: sa for sa in result.canonical.cronograma.scheduled_activities}
    assert "eap-01" in sched, "eap-01 must appear in scheduled_activities"
    assert "eap-02" in sched, "eap-02 must appear in scheduled_activities"

    assert sched["eap-01"].assigned_resources == {"maq": 2}, (
        "eap-01 should carry assigned_resources={'maq': 2} from rcpsp_spec"
    )
    assert sched["eap-02"].assigned_resources == {"maq": 1}, (
        "eap-02 should carry assigned_resources={'maq': 1} from rcpsp_spec"
    )


from datetime import UTC, datetime  # noqa: E402

from concilium.application.skills import run_escopo_e_eap  # noqa: E402
from concilium.domain.models.canonical import (  # noqa: E402
    Coordenadas,
    EapItem,
    Meta,
    Projeto,
    RegimeTrabalho,
)


def _make_meta():
    return Meta(gerado_em=datetime.now(UTC), contexto_id="test")


def _make_proj():
    return Projeto(
        id="p1",
        nome="proj",
        tipo_obra="terraplenagem",
        localizacao="x",
        coordenadas=Coordenadas(lat=0.0, lng=0.0),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        data_inicio="2026-01-01",
        data_termino="2026-12-31",
        snapshot_catalogo_id="s",
        snapshot_perfil_id="s",
    )


def _minimal_canonical(eap=None, atividades=None):
    return CanonicalModel(meta=_make_meta(), projeto=_make_proj(), eap=eap or [], atividades=atividades or [])


def _canonical_to_inputs(canonical, extra_inputs):
    """Converte um canonical existente + extra_inputs em inputs para run_escopo_e_eap.

    Distinto do run_sequenciamento local (linha ~25 deste arquivo), que espera
    canonical+inputs crus e não faz essa conversão — usado só por
    TestSequenciamento, mesclado de test_remaining_coverage.py.
    """
    proj = canonical.projeto if canonical else None
    base = {
        "contexto_id": canonical.meta.contexto_id if canonical else "test",
        "snapshot_catalogo_id": proj.snapshot_catalogo_id if proj else "s",
        "snapshot_perfil_id": proj.snapshot_perfil_id if proj else "s",
        "nome": proj.nome if proj else "test",
        "tipo_obra": proj.tipo_obra if proj else "terraplenagem",
        "localizacao": proj.localizacao if proj else "x",
        "coordenadas": {"lat": proj.coordenadas.lat if proj else 0.0, "lng": proj.coordenadas.lng if proj else 0.0},
        "regime_trabalho": {
            "dias_semana": proj.regime_trabalho.dias_semana if proj else 5,
            "horas_dia": proj.regime_trabalho.horas_dia if proj else 8,
        },
        "data_inicio": str(proj.data_inicio) if proj else "2026-01-01",
        "data_termino": str(proj.data_termino) if proj else "2026-12-31",
        "eap": [i.model_dump() for i in canonical.eap] if canonical and canonical.eap else [],
    }
    base.update(extra_inputs or {})
    return base


def _run_sequenciamento_rich(canonical, inputs):
    merged = _canonical_to_inputs(canonical, inputs)
    if canonical and canonical.atividades:
        merged["atividades"] = [a.model_dump() for a in canonical.atividades]
    return run_escopo_e_eap(None, merged)


# ══ 00B-sequenciamento ═══════════════════════════════════════════════════════


class TestSequenciamento:
    def _canonical_with_atividades(self):
        eap = [
            EapItem(item_id="i1", ordem=1, cpu_id="CPU-X", descricao="T1", unidade="m3", quantitativo=100),
            EapItem(item_id="i2", ordem=2, cpu_id="CPU-X", descricao="T2", unidade="m3", quantitativo=100),
            EapItem(item_id="i3", ordem=3, cpu_id="CPU-X", descricao="T3", unidade="m3", quantitativo=100),
        ]
        ativs = [
            Atividade(
                atividade_id="a1",
                eap_item_id="i1",
                descricao="A1",
                fracao_quantitativo=1.0,
                quantitativo_atividade=100,
                cpu_id="CPU-X",
            ),
            Atividade(
                atividade_id="a2",
                eap_item_id="i2",
                descricao="A2",
                fracao_quantitativo=1.0,
                quantitativo_atividade=100,
                cpu_id="CPU-X",
            ),
            Atividade(
                atividade_id="a3",
                eap_item_id="i3",
                descricao="A3",
                fracao_quantitativo=1.0,
                quantitativo_atividade=100,
                cpu_id="CPU-X",
            ),
        ]
        return CanonicalModel(meta=_make_meta(), projeto=_make_proj(), eap=eap, atividades=ativs)

    def test_sucessora_invalida_emite_dag01(self):
        """If successora doesn't exist, should emit VAL-DAG-01 ERRO."""
        can = self._canonical_with_atividades()
        inputs = {"precedencias": [{"predecessora": "a1", "sucessora": "nonexistent"}]}
        res = _run_sequenciamento_rich(can, inputs)
        codigos = {v.codigo: v.status for v in res.validacoes}
        assert "VAL-DAG-01" in codigos and codigos["VAL-DAG-01"] == "ERRO"

    def test_predecessora_invalida_emite_dag01(self):
        """If predecessora doesn't exist, should emit VAL-DAG-01 ERRO (lines 82-87)."""
        can = self._canonical_with_atividades()
        inputs = {"precedencias": [{"predecessora": "nonexistent", "sucessora": "a1"}]}
        res = _run_sequenciamento_rich(can, inputs)
        codigos = {v.codigo: v.status for v in res.validacoes}
        assert "VAL-DAG-01" in codigos and codigos["VAL-DAG-01"] == "ERRO"

    def test_atividades_vazias_emite_precondicao(self):
        """Empty EAP/atividades should emit EAP warning."""
        can = _minimal_canonical()  # no atividades
        res = _run_sequenciamento_rich(can, {})
        codigos = {v.codigo: v.status for v in res.validacoes}
        assert "VAL-EAP-03" in codigos  # EAP vazia emite VAL-EAP-03

    def test_ciclo_emite_dag02_e_seq01(self):
        """Cycle in precedences should emit VAL-SEQ-01 ERRO."""
        can = self._canonical_with_atividades()
        # skill 01 creates atividade IDs as "{item_id}-atv-1"
        inputs = {
            "precedencias": [
                {"predecessora": "i1-atv-1", "sucessora": "i2-atv-1"},
                {"predecessora": "i2-atv-1", "sucessora": "i3-atv-1"},
                {"predecessora": "i3-atv-1", "sucessora": "i1-atv-1"},
            ]
        }
        res = _run_sequenciamento_rich(can, inputs)
        codigos = [v.codigo for v in res.validacoes]
        assert "VAL-SEQ-01" in codigos  # cycle detected

    def test_prazo_contrato_excedido_emite_seq02(self):
        """When prazo_contrato is exceeded, should emit VAL-SEQ-02 ERRO."""
        can = self._canonical_with_atividades()
        # skill 01 creates atividade IDs as "{item_id}-atv-1"
        inputs = {
            "precedencias": [
                {"predecessora": "i1-atv-1", "sucessora": "i2-atv-1"},
                {"predecessora": "i2-atv-1", "sucessora": "i3-atv-1"},
            ],
            "prazo_contrato": 1,
        }
        res = _run_sequenciamento_rich(can, inputs)
        codigos = {v.codigo: v.status for v in res.validacoes}
        assert "VAL-SEQ-02" in codigos and codigos["VAL-SEQ-02"] == "ERRO"

    def test_prazo_contrato_ok(self):
        """When prazo_contrato is sufficient, should emit VAL-SEQ-02 OK."""
        can = self._canonical_with_atividades()
        inputs = {
            "precedencias": [
                {"predecessora": "i1-atv-1", "sucessora": "i2-atv-1"},
            ],
            "prazo_contrato": 10,
        }
        res = _run_sequenciamento_rich(can, inputs)
        codigos = {v.codigo: v.status for v in res.validacoes}
        assert "VAL-SEQ-02" in codigos and codigos["VAL-SEQ-02"] == "OK"



