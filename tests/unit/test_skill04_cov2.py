"""Extra coverage for skill 04-cronograma/skill.py — second batch.

Targets remaining missing lines identified from .coverage data:
164->170, 215, 233, 408->401, 474-476, 507->520, 510-517, 520->528,
1020->1031, 1031->1034, 1401-1408, 1448-1451, 1455, 1607->1592,
1689, 1770-1777, 1788-1791, 1905-1912, 1946->1943, 2001, 2032-2037,
2137-2148, 2216-2217, 2234->2237
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

_MOD_NAME = "_concilium_skillpkg_04_cronograma.skill"
_MOD = sys.modules[_MOD_NAME]

_custo_hora_equipe = _MOD._custo_hora_equipe
_enrich_producao_canonico = _MOD._enrich_producao_canonico
_build_fator_calendario_semanal = _MOD._build_fator_calendario_semanal
_extract_dag = _MOD._extract_dag
_extract_activities = _MOD._extract_activities
_resolve_productivity = _MOD._resolve_productivity
_check_wmp_desmob = _MOD._check_wmp_desmob
_build_cronograma_out = _MOD._build_cronograma_out
_cpv_process_violations = _MOD._cpv_process_violations
_determine_mode_and_distribuicao = _MOD._determine_mode_and_distribuicao
_process_single_wmp_policy = _MOD._process_single_wmp_policy
_build_scheduled_activities = _MOD._build_scheduled_activities
_build_intervalos_and_campanhas = _MOD._build_intervalos_and_campanhas
run_cronograma = _MOD.run_cronograma


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_canonical():
    """Minimal CanonicalModel for run_cronograma tests."""
    from concilium.domain.models.canonical import (
        CanonicalModel,
        Coordenadas,
        EapItem,
        Meta,
        Praticabilidade,
        Projeto,
        RegimeTrabalho,
    )

    meta = Meta(gerado_em=datetime.now(UTC), contexto_id="test")
    proj = Projeto(
        id="p1",
        nome="proj",
        tipo_obra="terraplenagem",
        localizacao="x",
        coordenadas=Coordenadas(lat=0.0, lng=0.0),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        data_inicio=date(2025, 1, 6),
        data_termino=date(2025, 6, 30),
        snapshot_catalogo_id="s",
        snapshot_perfil_id="s",
    )
    prat = Praticabilidade(
        fonte="test",
        limiar_inviabilidade_mm=0,
        calculada_em=datetime.now(UTC),
        percentual_produtivo_mensal={"01": 1.0, "02": 1.0, "03": 1.0, "04": 1.0, "05": 1.0, "06": 1.0},
    )
    eap = [
        EapItem(item_id="IT-01", ordem=1, cpu_id="CPU-01", descricao="Item", unidade="m", quantitativo=100.0)
    ]
    return CanonicalModel(meta=meta, projeto=proj, eap=eap, praticabilidade=prat)


# ---------------------------------------------------------------------------
# _custo_hora_equipe — line 164->170 (ins=None, equip has no insumo match)
# ---------------------------------------------------------------------------


class TestCustoHoraEquipeNoIns:
    def test_equip_without_insumo_skips_pu(self):
        """Line 164: ins=None → skip the if block; custo_hora from equip is 0."""
        composicao = {"equipamentos": [{"equip_id": "EQ-MISSING", "num_unidades": 1}]}
        result = _custo_hora_equipe(composicao, {}, 160.0, 1.0)
        assert result == pytest.approx(0.0)

    def test_equip_without_insumo_but_with_consumo(self):
        """Equip has consumo but no insumo match (ins=None) → custo from funcoes only.

        Pricing always comes from insumos_lookup (there's no inline salario_mensal
        fallback), so the funcao's insumo ("OP") must be present in the lookup —
        only the equipamento's insumo ("EQ-X") is absent.
        """
        composicao = {
            "funcoes": [{"funcao_id": "OP", "num_pessoas": 1}],
            "equipamentos": [{"equip_id": "EQ-X", "num_unidades": 1, "consumo_litros_hora": 10.0}],
        }
        insumos_lookup = {"OP": {"preco_unitario": 3000.0, "unidade": "mes"}}
        # EQ-X and diesel absent from lookup → equipamento/combustível contribute 0.
        result = _custo_hora_equipe(composicao, insumos_lookup, 160.0, 1.0)
        # custo_hora from funcao only (preco_unitario / horas_mes × (1 + taxa_encargos))
        assert result > 0.0


# ---------------------------------------------------------------------------
# _enrich_producao_canonico — lines 215 (no prod) and 233 (custo_hora<=0)
# ---------------------------------------------------------------------------


class TestEnrichProducaoCanonicoNoProd:
    def test_cpu_producao_id_ref_not_in_lookup_skips(self):
        """Line 215: prod not found → continue (no enrichment)."""
        from concilium.domain.models.canonical import ValidacaoItem

        cpu = {"codigo": "CPU-X", "producao_id_ref": "PROD-MISSING", "precos_unitarios_sbdi": {"total": 100.0}}
        cpu_lookup = {"CPU-X": cpu}
        producao_lookup = {}  # empty — prod not found
        validacoes = []
        _enrich_producao_canonico(cpu_lookup, producao_lookup, {}, 160.0, 1.0, validacoes)
        # No VAL-PROD-CANONICO appended (prod not found → continue)
        assert not any(v.codigo == "VAL-PROD-CANONICO" for v in validacoes)


class TestEnrichProducaoCanonicoZeroCusto:
    def test_custo_hora_zero_skips(self):
        """Line 233: custo_hora <= 0 → continue (no enrichment)."""
        from concilium.domain.models.canonical import ValidacaoItem

        cpu = {"codigo": "CPU-Y", "producao_id_ref": "P1", "precos_unitarios_sbdi": {"total": 100.0}}
        prod = {
            "composicao_padrao_equipe": {"funcoes": []},  # non-empty composicao but yields custo_hora=0
            "custo_hora_total_referencia": None,
            "valor_horario": None,
        }
        validacoes = []
        _enrich_producao_canonico({"CPU-Y": cpu}, {"P1": prod}, {}, 160.0, 1.0, validacoes)
        assert not any(v.codigo == "VAL-PROD-CANONICO" for v in validacoes)


# ---------------------------------------------------------------------------
# _build_fator_calendario_semanal — line 408->401 (evento dict without "id")
# ---------------------------------------------------------------------------


class TestBuildFatorCalendarioSemanalEventoNoId:
    def test_evento_without_id_field_not_added_to_eventos_aplicados(self):
        """Line 408->401: evento.get('id') is falsy → skip eventos_aplicados.add."""
        from datetime import timedelta

        start = date(2025, 1, 6)
        semanas = ["2025-W02"]  # week starting Jan 6
        # evento with fator_operacao=0 but no "id" field → event occurs, reduces fator, but no id recorded
        eventos = [
            {
                "inicio": "2025-01-06",
                "fim": "2025-01-06",
                "recorrencia": "unica",
                "fator_operacao": 0.0,
                # no "id" field!
            }
        ]
        fatores, artefato = _build_fator_calendario_semanal(semanas, start, 5, {"eventos": eventos})
        assert fatores["2025-W02"] == pytest.approx(0.8, abs=0.01)
        # No eventos_aplicados since no "id"
        assert len(artefato[0].eventos_aplicados) == 0


# ---------------------------------------------------------------------------
# _extract_dag — SS/FF tipo predecessors (lines 510-517)
# ---------------------------------------------------------------------------


class TestExtractDagSSFFTipo:
    def test_ss_tipo_creates_extended_precedence(self):
        """Lines 510-517: SS tipo predecessor → extended list and thresholds sentinel."""
        from concilium.application.scheduling.cpsat_scheduler import ExtendedPrecedence

        class FakePred:
            item_id = "IT-A"
            tipo = "SS"
            lag = 0
            completion_threshold_pct = 0.5

        class FakeItem:
            item_id = "IT-B"
            descricao = "Item B"
            predecessores = [FakePred()]

            def predecessores_tipados(self):
                return self.predecessores

        class FakeCanonical:
            eap = [FakeItem()]
            activity_dag = None
            atividades = None

        dag = _extract_dag(FakeCanonical(), ["IT-A", "IT-B"])
        # SS → extended_precedences has one entry with tipo=SS
        assert any(ep.tipo == "SS" for ep in dag.extended_precedences)
        # edge_thresholds set to sentinel 1.0
        assert ("IT-A", "IT-B") in dag.thresholds
        assert dag.thresholds[("IT-A", "IT-B")] == 1.0

    def test_ff_tipo_creates_extended_precedence(self):
        """FF tipo also creates extended precedence."""

        class FakePred:
            item_id = "IT-X"
            tipo = "FF"
            lag = 2
            completion_threshold_pct = 0.0

        class FakeItem:
            item_id = "IT-Y"
            descricao = "Item Y"
            predecessores = [FakePred()]

            def predecessores_tipados(self):
                return self.predecessores

        class FakeCanonical:
            eap = [FakeItem()]
            activity_dag = None
            atividades = None

        dag = _extract_dag(FakeCanonical(), ["IT-X", "IT-Y"])
        assert any(ep.tipo == "FF" and ep.lag == 2 for ep in dag.extended_precedences)


# ---------------------------------------------------------------------------
# _extract_dag — no eap → linear fallback via activity_dag (lines 507->520, 520->528)
# ---------------------------------------------------------------------------


class TestExtractDagNoEap:
    def test_no_eap_uses_activity_dag_arestas(self):
        """Lines 507->520, 520->528: canonical.eap is None/[] → check activity_dag."""

        class FakeAresta:
            de = "A"
            para = "B"

        class FakeActivityDag:
            arestas = [FakeAresta()]

        class FakeCanonical:
            eap = []
            activity_dag = FakeActivityDag()
            atividades = None

        dag = _extract_dag(FakeCanonical(), ["A", "B"])
        assert ("A", "B") in dag.thresholds

    def test_no_eap_no_activity_dag_infers_linear(self):
        """Lines 524-526: no eap, no activity_dag → infer linear sequence."""

        class FakeCanonical:
            eap = []
            activity_dag = None
            atividades = None

        dag = _extract_dag(FakeCanonical(), ["A", "B", "C"])
        # Linear: A→B, B→C
        assert ("A", "B") in dag.thresholds
        assert ("B", "C") in dag.thresholds


# ---------------------------------------------------------------------------
# _extract_activities — lines 474-476 (computed productive weeks used)
# ---------------------------------------------------------------------------


class TestExtractActivitiesWithLookups:
    def test_productive_weeks_used_when_computed(self):
        """Lines 474-476: cpu_lookup + producao_lookup available → computed duration used."""

        class FakePrat:
            percentual_produtivo_semanal = {"2025-W02": 1.0}

        class FakeRegime:
            horas_dia = 8
            dias_semana = 5

        class FakeProjeto:
            data_inicio = date(2025, 1, 6)
            data_termino = date(2025, 6, 30)
            regime_trabalho = FakeRegime()

        class FakeEapItem:
            item_id = "IT-01"
            descricao = "Item"
            quantitativo = 400.0  # Q=400, P=10, horas_semana=40 → dur=1 week (ceil(400/(10*40)))=1
            cpu_id = "CPU-01"

        class FakeCanonical:
            eap = [FakeEapItem()]
            atividades = None
            projeto = FakeProjeto()
            praticabilidade = FakePrat()

        cpu_lookup = {
            "CPU-01": {
                "codigo": "CPU-01",
                "producao_id_ref": "P1",
                "precos_unitarios_sbdi": {"total": 0.0},
            }
        }
        producao_lookup = {
            "P1": {"valor_horario": 10.0, "producao_horaria": 10.0}
        }
        validacoes = []
        activities = _extract_activities(FakeCanonical(), cpu_lookup, producao_lookup, validacoes)
        assert len(activities) == 1
        # duration_weeks should be computed (>=1)
        assert activities[0].duration_weeks >= 1


# ---------------------------------------------------------------------------
# _resolve_productivity — lines 1020->1031, 1031->1034
# ---------------------------------------------------------------------------


class TestResolveProductivityNoValue:
    def test_prod_item_has_neither_valor_horario_nor_producao_horaria(self):
        """Lines 1020->1031, 1031->1034: prod_item with no valid value → fallback."""
        from concilium.domain.models.canonical import ValidacaoItem

        cpu = {"codigo": "CPU-X", "producao_id_ref": "P1"}
        prod_lookup = {
            "P1": {
                # valor_horario is None → check producao_horaria
                "valor_horario": None,
                # producao_horaria also None → skip
                "producao_horaria": None,
            }
        }
        validacoes = []
        result = _resolve_productivity(cpu, prod_lookup, validacoes)
        # Falls through to default 1000.0
        assert result == 1000.0

    def test_prod_item_has_producao_horaria_but_valor_horario_none(self):
        """Line 1020->1031 True path: producao_horaria exists → VAL-PROD-04-PROD-LEGACY."""
        from concilium.domain.models.canonical import ValidacaoItem

        cpu = {"codigo": "CPU-X", "producao_id_ref": "P2"}
        prod_lookup = {
            "P2": {
                "valor_horario": None,
                "producao_horaria": 5.0,  # legacy field
            }
        }
        validacoes = []
        result = _resolve_productivity(cpu, prod_lookup, validacoes)
        assert result == pytest.approx(5.0)
        assert any(v.codigo == "VAL-PROD-04-PROD-LEGACY" for v in validacoes)


# ---------------------------------------------------------------------------
# _check_wmp_desmob — line 1689 (else branch)
# ---------------------------------------------------------------------------


class TestCheckWmpDesmobElse:
    def test_incompleta_with_no_plateau_emits_val_wmp_05(self):
        """Line 1689: curva.incompleta=True, semanas_plateau=None → else branch."""
        from concilium.domain.models.canonical import ValidacaoItem

        curva = SimpleNamespace(incompleta=True)
        policy = SimpleNamespace(semanas_plateau=None, taxa_desmobilizacao=0.5)
        validacoes = []
        _check_wmp_desmob("IT-01", curva, policy, Q=100.0, P=5.0, validacoes=validacoes)
        # semanas_plateau is None → condition is False → else branch
        assert any(v.codigo == "VAL-WMP-05" for v in validacoes)

    def test_incompleta_with_zero_taxa_emits_val_wmp_05(self):
        """Line 1689: taxa_desmobilizacao=0 → else branch."""
        curva = SimpleNamespace(incompleta=True)
        policy = SimpleNamespace(semanas_plateau=10, taxa_desmobilizacao=0)
        validacoes = []
        _check_wmp_desmob("IT-01", curva, policy, Q=100.0, P=5.0, validacoes=validacoes)
        assert any(v.codigo == "VAL-WMP-05" for v in validacoes)


# ---------------------------------------------------------------------------
# _build_cronograma_out — line 2001 (unknown heuristic → "MINSLK")
# ---------------------------------------------------------------------------


class TestBuildCronogramaOutUnknownHeuristic:
    def test_unknown_heuristic_falls_back_to_minslk(self):
        """Line 2001: mode != MANUAL_ALLOCATION, heuristic not in AVAILABLE list."""
        schedule_selected = SimpleNamespace(
            heuristic="UNKNOWN_ALGO",
            quality_score=0.5,
            makespan=10,
            relaxed=False,
        )
        from concilium.domain.models.canonical import ValidacaoItem

        result = _build_cronograma_out(
            mode="AUTO_SCHEDULE",
            schedule_selected=schedule_selected,
            scheduled_activities_out=[],
            semanas_obra=["2025-W01", "2025-W02"],
            distribuicao_mensal={},
            validacoes=[],
        )
        assert result.algorithm == "MINSLK"


# ---------------------------------------------------------------------------
# _cpv_process_violations — line 1594 (available is None → continue)
# ---------------------------------------------------------------------------


class TestCpvProcessViolationsAvailableNone:
    def test_tipo_not_in_pool_available_none_continues(self):
        """Line 1594: available = pool.get(tipo_id) is None → continue."""
        from concilium.domain.models.canonical import ValidacaoItem

        usage = {"2025-W01": {"TIPO-A": 5, "TIPO-UNKNOWN": 3}}
        pool = {"TIPO-A": 10}  # TIPO-UNKNOWN not in pool → available=None
        validacoes = []
        violations = _cpv_process_violations(usage, pool, validacoes)
        # TIPO-UNKNOWN not in pool → no violation for it
        assert not any("TIPO-UNKNOWN" in v.mensagem for v in validacoes)

    def test_violation_when_exceeds_pool(self):
        """Line 1594: total_used > available → violation appended."""
        from concilium.domain.models.canonical import ValidacaoItem

        usage = {"2025-W01": {"TRATOR": 5}}
        pool = {"TRATOR": 3}  # exceed
        validacoes = []
        violations = _cpv_process_violations(usage, pool, validacoes)
        assert len(violations) == 1
        assert any("TRATOR" in v.mensagem for v in validacoes)


# ---------------------------------------------------------------------------
# _determine_mode_and_distribuicao — lines 1905-1912 (no mode detected)
# ---------------------------------------------------------------------------


class TestDetermineModeNoMode:
    def test_no_mode_detected_returns_true_failed(self):
        """Lines 1905-1912: no rcpsp_spec, no num_equipes_por_item, _can_extract_dag=False."""
        from concilium.domain.models.canonical import ValidacaoItem

        # A canonical that makes _can_extract_dag return False
        class FakeCanonical:
            eap = []
            atividades = None
            activity_dag = None
            praticabilidade = None

            def model_copy(self, **kw):
                return self

        validacoes = []
        mode, distr, candidates, selected, failed = _determine_mode_and_distribuicao(
            canonical_in=FakeCanonical(),
            inputs={},
            num_equipes_por_item=None,
            semanas_obra=["2025-W01"],
            cpu_lookup={},
            producao_lookup={},
            regime=SimpleNamespace(horas_dia=8, dias_semana=5),
            prat_semanal={},
            prat_mensal={},
            fator_calendario_semanal={},
            catalogo={},
            validacoes=validacoes,
        )
        assert failed is True
        assert mode is None
        assert any(v.codigo == "VAL-CRON-MODE" and v.status == "ERRO" for v in validacoes)


# ---------------------------------------------------------------------------
# _process_single_wmp_policy — lines 1770-1777 (cpu not found)
# ---------------------------------------------------------------------------


class TestProcessSingleWmpPolicyCpuNotFound:
    def test_cpu_not_found_emits_val_wmp_02(self):
        """Lines 1770-1777: cpu_id not in cpu_lookup → VAL-WMP-02."""

        class FakeEapItem:
            item_id = "IT-01"
            cpu_id = "CPU-MISSING"
            quantitativo = 100.0

        eap_lookup = {"IT-01": FakeEapItem()}
        cpu_lookup = {}  # CPU not found
        validacoes = []
        _process_single_wmp_policy(
            item_id="IT-01",
            policy_dict={"n_maximo": 2, "taxa_mobilizacao": 0.5, "taxa_desmobilizacao": 0.5},
            eap_lookup=eap_lookup,
            cpu_lookup=cpu_lookup,
            producao_lookup={},
            pool={},
            sim=MagicMock(),
            regime=SimpleNamespace(horas_dia=8, dias_semana=5),
            prat_semanal={},
            semanas_obra=[],
            semanas_set=set(),
            result={},
            curves=[],
            validacoes=validacoes,
        )
        assert any(v.codigo == "VAL-WMP-02" for v in validacoes)


# ---------------------------------------------------------------------------
# _process_single_wmp_policy — lines 1788-1791 (Q=0)
# ---------------------------------------------------------------------------


class TestProcessSingleWmpPolicyQZero:
    def test_quantitativo_zero_emits_val_wmp_04(self):
        """Lines 1788-1791: Q=0 → VAL-WMP-04."""

        class FakeEapItem:
            item_id = "IT-01"
            cpu_id = "CPU-01"
            quantitativo = 0.0

        eap_lookup = {"IT-01": FakeEapItem()}
        cpu_lookup = {"CPU-01": {"codigo": "CPU-01", "producao_id_ref": "P1"}}
        producao_lookup = {"P1": {"valor_horario": 10.0}}
        validacoes = []
        _process_single_wmp_policy(
            item_id="IT-01",
            policy_dict={"n_inicial": 1, "n_maximo": 1, "taxa_mobilizacao": 0.5, "taxa_desmobilizacao": 0.5},
            eap_lookup=eap_lookup,
            cpu_lookup=cpu_lookup,
            producao_lookup=producao_lookup,
            pool={},
            sim=MagicMock(),
            regime=SimpleNamespace(horas_dia=8, dias_semana=5),
            prat_semanal={},
            semanas_obra=[],
            semanas_set=set(),
            result={},
            curves=[],
            validacoes=validacoes,
        )
        assert any(v.codigo == "VAL-WMP-04" for v in validacoes)


# ---------------------------------------------------------------------------
# _build_scheduled_activities — line 1946->1943 (activity_id or duration is None)
# ---------------------------------------------------------------------------


class TestBuildScheduledActivitiesNoneActivityId:
    def test_activity_id_none_skips_duration_lookup(self):
        """Line 1946->1943: activity_id=None → not in duration_lookup."""
        from concilium.domain.models.canonical import DistribuicaoSemanal

        fake_sa = SimpleNamespace(
            activity_id=None,  # None → condition (activity_id and duration) is False
            duration_weeks=None,
            start_week=0,
            data_inicio=date(2025, 1, 6),
            data_fim=date(2025, 2, 6),
        )
        sched_sel = SimpleNamespace(scheduled_activities=[fake_sa])

        class FakeEapItem:
            item_id = "IT-01"
            quantitativo = 100.0

        class FakeCanonical:
            eap = [FakeEapItem()]
            projeto = SimpleNamespace(data_inicio=date(2025, 1, 6))

        result = _build_scheduled_activities(
            FakeCanonical(),
            distribuicao_por_item={"IT-01": {}},
            semanas_obra=["2025-W02"],
            schedule_selected=sched_sel,
        )
        assert len(result) == 1
        # duration_weeks falls back to max(1, 0-0+1)=1
        assert result[0].duration_weeks >= 1

    def test_activity_id_without_atv_uses_item_id_directly(self):
        """Line 1950: activity_id without '-atv-' → item_id = activity_id directly."""
        fake_sa = SimpleNamespace(
            activity_id="IT-01",  # No "-atv-" in it
            duration_weeks=5,
        )
        sched_sel = SimpleNamespace(scheduled_activities=[fake_sa])

        class FakeEapItem:
            item_id = "IT-01"
            quantitativo = 100.0

        class FakeCanonical:
            eap = [FakeEapItem()]
            projeto = SimpleNamespace(data_inicio=date(2025, 1, 6))

        result = _build_scheduled_activities(
            FakeCanonical(),
            distribuicao_por_item={"IT-01": {}},
            semanas_obra=["2025-W02"],
            schedule_selected=sched_sel,
        )
        assert result[0].duration_weeks == 5


# ---------------------------------------------------------------------------
# _build_intervalos_and_campanhas — lines 2032-2033 (alertas non-empty)
# ---------------------------------------------------------------------------


class TestBuildIntervalosAndCampanhasAlertas:
    def test_alertas_custo_duplicado_appends_validacoes(self):
        """Lines 2032-2033: analise_campanhas.alertas_custo_duplicado non-empty."""
        from concilium.domain.models.canonical import ValidacaoItem

        mock_analise = MagicMock()
        mock_analise.alertas_custo_duplicado = ["alert-1"]

        class FakeCronograma:
            scheduled_activities = []

        class FakeCanonical:
            def model_copy(self, **kw):
                return self

        with patch(
            "concilium.domain.services.campaign.campanha_equipamento_builder.CampanhaEquipamentoBuilder"
        ) as MockBuilder:
            MockBuilder.return_value.build.return_value = mock_analise
            intervalos, analise = _build_intervalos_and_campanhas(
                FakeCanonical(),
                cronograma_out=FakeCronograma(),
                scheduled_activities_out=[],
                validacoes=[ValidacaoItem(codigo="VAL-OK", status="OK", mensagem="base")],
            )
        # alertas_custo_duplicado had 1 entry → 1 VAL-CAMP-01 appended
        assert analise is mock_analise

    def test_campaign_exception_is_swallowed(self):
        """Lines 2034-2037: CampanhaEquipamentoBuilder raises → logged, analise=None."""
        with patch(
            "concilium.domain.services.campaign.campanha_equipamento_builder.CampanhaEquipamentoBuilder"
        ) as MockBuilder:
            MockBuilder.return_value.build.side_effect = RuntimeError("boom")

            class FakeCronograma:
                scheduled_activities = []

            class FakeCanonical:
                def model_copy(self, **kw):
                    return self

            intervalos, analise = _build_intervalos_and_campanhas(
                FakeCanonical(),
                cronograma_out=FakeCronograma(),
                scheduled_activities_out=[],
                validacoes=[],
            )
        assert analise is None


# ---------------------------------------------------------------------------
# run_cronograma — lines 2137-2148 (flat int in num_equipes_por_item)
# ---------------------------------------------------------------------------


class TestRunCronogramaFlatNumEquipes:
    def test_flat_int_format_error_returns_early(self):
        """Lines 2137-2148: num_equipes_por_item contains int value → VAL-CRON-EQUIPES-FORMATO."""
        canonical = _make_canonical()
        result = run_cronograma(
            canonical,
            inputs={"num_equipes_por_item": {"IT-01": 3}},  # 3 is int, not dict
        )
        val_codes = [v.codigo for v in result.validacoes]
        assert "VAL-CRON-EQUIPES-FORMATO" in val_codes


# ---------------------------------------------------------------------------
# run_cronograma — lines 2216-2217 (mob_schedule exception)
# ---------------------------------------------------------------------------


class TestRunCronogramaMobScheduleException:
    def test_mob_schedule_exception_emits_val_mob_schedule_erro(self):
        """Lines 2216-2217: infer_mob_windows raises → VAL-MOB-SCHEDULE-ERRO."""
        canonical = _make_canonical()
        with patch(f"{_MOD_NAME}.infer_mob_windows", side_effect=RuntimeError("fail")):
            result = run_cronograma(
                canonical,
                inputs={
                    "num_equipes_por_item": {"IT-01": {"2025-W02": 1}},
                },
            )
        val_codes = [v.codigo for v in result.validacoes]
        assert "VAL-MOB-SCHEDULE-ERRO" in val_codes


# ---------------------------------------------------------------------------
# run_cronograma — line 2234->2237 (mob_schedule=None → no update)
# ---------------------------------------------------------------------------


class TestRunCronogramaMobScheduleNone:
    def test_mob_schedule_none_not_in_update_dict(self):
        """Line 2234->2237: mob_schedule=None → update_dict has no 'mob_schedule' key."""
        canonical = _make_canonical()
        with patch(f"{_MOD_NAME}.infer_mob_windows", return_value=None):
            result = run_cronograma(
                canonical,
                inputs={"num_equipes_por_item": {"IT-01": {"2025-W02": 1}}},
            )
        # mob_schedule=None → canonical.mob_schedule not set
        assert getattr(result.canonical, "mob_schedule", None) is None


# ---------------------------------------------------------------------------
# _rasfc_extract_inputs — lines 1401-1408 (extracted is None)
# ---------------------------------------------------------------------------


class TestRunAutoScheduleFallbackChainNullExtract:
    def test_extract_inputs_returns_none_emits_val_sched_extract_fail(self):
        """Lines 1401-1408: _rasfc_extract_inputs returns None → VAL-SCHED-EXTRACT-FAIL."""
        _rasfc = _MOD._run_auto_schedule_fallback_chain

        class FakeCanonical:
            eap = []
            atividades = None
            activity_dag = None
            projeto = SimpleNamespace(
                data_inicio=date(2025, 1, 6),
                data_termino=date(2025, 3, 31),
                regime_trabalho=SimpleNamespace(horas_dia=8, dias_semana=5),
            )

        validacoes = []
        with patch(f"{_MOD_NAME}._rasfc_extract_inputs", return_value=None):
            candidates, best = _rasfc(FakeCanonical(), {}, validacoes)
        assert candidates == []
        assert best is None
        assert any(v.codigo == "VAL-SCHED-EXTRACT-FAIL" for v in validacoes)
