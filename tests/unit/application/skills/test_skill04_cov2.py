"""Extra coverage for skill 04-cronograma/skill.py — second batch.

Targets remaining missing lines identified from .coverage data:
164->170, 215, 233, 408->401, 474-476, 507->520, 510-517, 520->528,
1020->1031, 1031->1034, 1401-1408, 1448-1451, 1455, 1607->1592,
1689, 1770-1777, 1788-1791, 1905-1912, 1946->1943, 2001, 2032-2037,
2137-2148, 2216-2217, 2234->2237

Import strategy: Load skill via concilium.application.skills so that sys.modules
is properly populated with the module loaded via importlib.
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from concilium.application.skills import run_cronograma  # Trigger module loading via importlib

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
_compute_productive_weeks = _MOD._compute_productive_weeks
_enrich_spec_resources_from_catalog = _MOD._enrich_spec_resources_from_catalog
_rasfc_extract_inputs = _MOD._rasfc_extract_inputs
_rasfc_run_heuristics = _MOD._rasfc_run_heuristics
_convert_schedule_to_distribuicao = _MOD._convert_schedule_to_distribuicao
_check_wmp_pool = _MOD._check_wmp_pool
_cpv_build_usage = _MOD._cpv_build_usage


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
    eap = [EapItem(item_id="IT-01", ordem=1, cpu_id="CPU-01", descricao="Item", unidade="m", quantitativo=100.0)]
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

    def test_ff_tipo_followed_by_another_predecessor_continues_loop(self):
        """Line 523->514: after handling an FF predecessor, the for loop must
        continue to the next predecessor in the same item (not just exit)."""

        class FakePredFF:
            item_id = "IT-X"
            tipo = "FF"
            lag = 1
            completion_threshold_pct = 0.0

        class FakePredFS:
            item_id = "IT-W"
            tipo = "FS"
            lag = 0
            completion_threshold_pct = 1.0

        class FakeItem:
            item_id = "IT-Y"
            descricao = "Item Y"
            predecessores = [FakePredFF(), FakePredFS()]

            def predecessores_tipados(self):
                return self.predecessores

        class FakeCanonical:
            eap = [FakeItem()]
            activity_dag = None
            atividades = None

        dag = _extract_dag(FakeCanonical(), ["IT-X", "IT-W", "IT-Y"])
        assert any(ep.tipo == "FF" for ep in dag.extended_precedences)
        assert ("IT-W", "IT-Y") in dag.thresholds

    def test_extract_edge_thresholds_ff_followed_by_another_pred_continues_loop(self):
        """Mesmo cenário, chamando diretamente _extract_edge_thresholds_from_eap
        (helper extraído de _extract_dag): branch FF->próximo predecessor."""
        _extract_edge_thresholds_from_eap = _MOD._extract_edge_thresholds_from_eap

        class FakePredFF:
            item_id = "IT-X"
            tipo = "FF"
            lag = 1
            completion_threshold_pct = 0.0

        class FakePredFS:
            item_id = "IT-W"
            tipo = "FS"
            lag = 0
            completion_threshold_pct = 1.0

        class FakeItem:
            item_id = "IT-Y"
            descricao = "Item Y"
            predecessores = [FakePredFF(), FakePredFS()]

            def predecessores_tipados(self):
                return self.predecessores

        class FakeCanonical:
            eap = [FakeItem()]

        thresholds, extended = _extract_edge_thresholds_from_eap(FakeCanonical())
        assert any(ep.tipo == "FF" for ep in extended)
        assert ("IT-W", "IT-Y") in thresholds

    def test_fs_tipo_uses_completion_threshold_pct(self):
        """Line 519: FS tipo (explicit or default) uses the real threshold,
        not the SS/FF topological sentinel of 1.0."""

        class FakePred:
            item_id = "IT-P"
            tipo = "FS"
            lag = 0
            completion_threshold_pct = 0.75

        class FakeItem:
            item_id = "IT-Q"
            descricao = "Item Q"
            predecessores = [FakePred()]

            def predecessores_tipados(self):
                return self.predecessores

        class FakeCanonical:
            eap = [FakeItem()]
            activity_dag = None
            atividades = None

        dag = _extract_dag(FakeCanonical(), ["IT-P", "IT-Q"])
        assert dag.thresholds[("IT-P", "IT-Q")] == 0.75
        assert dag.extended_precedences == []


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
            eta_jornada = 1.0  # ADR-148: isola o teste do fator de jornada

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
        producao_lookup = {"P1": {"valor_horario": 10.0, "producao_horaria": 10.0}}
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

        usage = {"2025-W01": {"TIPO-A": 5, "TIPO-UNKNOWN": 3}}
        pool = {"TIPO-A": 10}  # TIPO-UNKNOWN not in pool → available=None
        validacoes = []
        _cpv_process_violations(usage, pool, validacoes)
        # TIPO-UNKNOWN not in pool → no violation for it
        assert not any("TIPO-UNKNOWN" in v.mensagem for v in validacoes)

    def test_violation_when_exceeds_pool(self):
        """Line 1594: total_used > available → violation appended."""

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

        # A canonical that makes _can_extract_dag return False
        class FakeCanonical:
            eap = []
            atividades = None
            activity_dag = None
            praticabilidade = None

            def model_copy(self, **kw):
                return self

        validacoes = []
        mode, distr, candidates, selected, failed, replenishable_resources = _determine_mode_and_distribuicao(
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
        assert replenishable_resources == []
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
        with patch(f"{_MOD_NAME}._mod_assembly.infer_mob_windows", side_effect=RuntimeError("fail")):
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
        with patch(f"{_MOD_NAME}._mod_assembly.infer_mob_windows", return_value=None):
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
        with patch(f"{_MOD_NAME}._mod_scheduling._rasfc_extract_inputs", return_value=None):
            candidates, best, replenishable_resources = _rasfc(FakeCanonical(), {}, validacoes)
        assert candidates == []
        assert best is None
        assert replenishable_resources == []
        assert any(v.codigo == "VAL-SCHED-EXTRACT-FAIL" for v in validacoes)


# ---------------------------------------------------------------------------
# _compute_productive_weeks — P <= 0 branch (line 677-678)
# ---------------------------------------------------------------------------


class TestComputeProductiveWeeksNonPositiveP:
    def test_zero_productivity_returns_none(self):
        canonical = _make_canonical()
        cpu_lookup = {"CPU-01": {"codigo": "CPU-01", "cpu_meta": {"producao_horaria": 0.0}}}
        result = _compute_productive_weeks("IT-01", 1, canonical, cpu_lookup, {}, [])
        assert result is None


# ---------------------------------------------------------------------------
# _enrich_spec_resources_from_catalog — early-return / continue branches
# ---------------------------------------------------------------------------


class TestEnrichSpecResourcesFromCatalog:
    def test_no_activities_returns_early(self):
        spec = {"activities": []}
        canonical = _make_canonical()
        _enrich_spec_resources_from_catalog(spec, canonical, {}, {}, 4, [])
        assert spec["activities"] == []

    def test_explicit_resource_pool_skips_enrichment(self):
        spec = {"activities": [{"item_id": "IT-01"}], "resource_pool": {"x": 1}}
        canonical = _make_canonical()
        _enrich_spec_resources_from_catalog(spec, canonical, {}, {}, 4, [])
        assert "required_resources" not in spec["activities"][0]

    def test_explicit_required_resources_skips_enrichment(self):
        spec = {"activities": [{"item_id": "IT-01", "required_resources": {"x": 1}}]}
        canonical = _make_canonical()
        _enrich_spec_resources_from_catalog(spec, canonical, {}, {}, 4, [])
        assert spec["activities"][0]["required_resources"] == {"x": 1}

    def test_deadline_weeks_non_positive_returns_early(self):
        spec = {"activities": [{"item_id": "IT-01"}]}
        canonical = _make_canonical()
        cpu_lookup = {"CPU-01": {"codigo": "CPU-01", "producao_id_ref": "PROD-01"}}
        producao_lookup = {
            "PROD-01": {"valor_horario": 10.0, "composicao_padrao_equipe": {"funcoes": [{"funcao_id": "OP"}]}}
        }
        _enrich_spec_resources_from_catalog(spec, canonical, cpu_lookup, producao_lookup, 0, [])
        assert "required_resources" not in spec["activities"][0]

    def test_item_not_in_eap_is_skipped(self):
        spec = {"activities": [{"item_id": "MISSING-ITEM"}]}
        canonical = _make_canonical()
        validacoes: list = []
        _enrich_spec_resources_from_catalog(spec, canonical, {}, {}, 4, validacoes)
        assert "required_resources" not in spec["activities"][0]
        assert validacoes == []

    def test_cpu_missing_is_skipped(self):
        spec = {"activities": [{"item_id": "IT-01"}]}
        canonical = _make_canonical()
        _enrich_spec_resources_from_catalog(spec, canonical, {}, {}, 4, [])
        assert "required_resources" not in spec["activities"][0]

    def test_prod_missing_is_skipped(self):
        spec = {"activities": [{"item_id": "IT-01"}]}
        canonical = _make_canonical()
        cpu_lookup = {"CPU-01": {"codigo": "CPU-01", "producao_id_ref": "PROD-MISSING"}}
        _enrich_spec_resources_from_catalog(spec, canonical, cpu_lookup, {}, 4, [])
        assert "required_resources" not in spec["activities"][0]

    def test_p_non_positive_is_skipped(self):
        spec = {"activities": [{"item_id": "IT-01"}]}
        canonical = _make_canonical()
        cpu_lookup = {"CPU-01": {"codigo": "CPU-01", "producao_id_ref": "PROD-01"}}
        producao_lookup = {
            "PROD-01": {"valor_horario": 0.0, "composicao_padrao_equipe": {"funcoes": [{"funcao_id": "OP"}]}}
        }
        _enrich_spec_resources_from_catalog(spec, canonical, cpu_lookup, producao_lookup, 4, [])
        assert "required_resources" not in spec["activities"][0]

    def test_comp_empty_is_skipped(self):
        spec = {"activities": [{"item_id": "IT-01"}]}
        canonical = _make_canonical()
        cpu_lookup = {"CPU-01": {"codigo": "CPU-01", "producao_id_ref": "PROD-01"}}
        producao_lookup = {"PROD-01": {"valor_horario": 10.0, "composicao_padrao_equipe": {}}}
        _enrich_spec_resources_from_catalog(spec, canonical, cpu_lookup, producao_lookup, 4, [])
        assert "required_resources" not in spec["activities"][0]

    def test_comp_without_equip_or_funcoes_keys_is_skipped(self):
        """Line 779-780: comp is truthy but has neither equipamentos nor funcoes."""
        spec = {"activities": [{"item_id": "IT-01"}]}
        canonical = _make_canonical()
        cpu_lookup = {"CPU-01": {"codigo": "CPU-01", "producao_id_ref": "PROD-01"}}
        producao_lookup = {"PROD-01": {"valor_horario": 10.0, "composicao_padrao_equipe": {"outro_campo": True}}}
        _enrich_spec_resources_from_catalog(spec, canonical, cpu_lookup, producao_lookup, 4, [])
        assert "required_resources" not in spec["activities"][0]

    def test_successful_enrichment_with_funcoes_and_equipamentos(self):
        spec = {"activities": [{"item_id": "IT-01"}]}
        canonical = _make_canonical()
        cpu_lookup = {"CPU-01": {"codigo": "CPU-01", "producao_id_ref": "PROD-01"}}
        producao_lookup = {
            "PROD-01": {
                "valor_horario": 1.0,
                "composicao_padrao_equipe": {
                    "funcoes": [{"funcao_id": "OP", "num_pessoas": 1}],
                    "equipamentos": [{"equip_id": "TRATOR", "num_unidades": 1}],
                },
            }
        }
        validacoes: list = []
        _enrich_spec_resources_from_catalog(spec, canonical, cpu_lookup, producao_lookup, 4, validacoes)
        act = spec["activities"][0]
        assert "required_resources" in act
        assert act["duration_weeks"] >= 1
        assert act["n_frentes"] >= 1
        assert act["_catalog_resources"] is True
        assert any(v.codigo == "VAL-CRON-CATALOGO-RES" for v in validacoes)

    def test_tipo_fungivel_falls_back_to_cpu_id_when_tokens_blank(self):
        """funcao_id/equip_id present but blank after strip → no tokens → falls
        back to the raw cpu_id signature (line 743-748)."""
        spec = {"activities": [{"item_id": "IT-01"}]}
        canonical = _make_canonical()
        cpu_lookup = {"CPU-01": {"codigo": "CPU-01", "producao_id_ref": "PROD-01"}}
        producao_lookup = {
            "PROD-01": {
                "valor_horario": 1.0,
                "composicao_padrao_equipe": {
                    "funcoes": [{"funcao_id": "  ", "num_pessoas": 1}],
                    "equipamentos": [{"equip_id": "  ", "num_unidades": 1}],
                },
            }
        }
        _enrich_spec_resources_from_catalog(spec, canonical, cpu_lookup, producao_lookup, 4, [])
        act = spec["activities"][0]
        assert list(act["required_resources"].keys()) == ["EQUIPE-CPU-CPU-01"]

    def test_ramp_params_n_max_triggers_ramp_profile_computed(self):
        spec = {
            "activities": [
                {"item_id": "IT-01", "ramp_params": {"n_max": 2, "n_inicial": 1}},
            ]
        }
        canonical = _make_canonical()
        cpu_lookup = {"CPU-01": {"codigo": "CPU-01", "producao_id_ref": "PROD-01"}}
        producao_lookup = {
            "PROD-01": {
                "valor_horario": 1.0,
                "composicao_padrao_equipe": {"funcoes": [{"funcao_id": "OP", "num_pessoas": 1}]},
            }
        }
        _enrich_spec_resources_from_catalog(spec, canonical, cpu_lookup, producao_lookup, 4, [])
        act = spec["activities"][0]
        assert "ramp_profile_computed" in act


# ---------------------------------------------------------------------------
# _extract_activities_from_spec
# ---------------------------------------------------------------------------

_extract_activities_from_spec = _MOD._extract_activities_from_spec
_extract_pool_from_spec = _MOD._extract_pool_from_spec


class TestExtractActivitiesFromSpecCatalogResources:
    def test_catalog_resources_uses_window_directly(self):
        """Line 837-839: `_catalog_resources` True → productive_w = window_w, no recompute."""
        spec = {
            "activities": [
                {"item_id": "IT-01", "duration_weeks": 3, "_catalog_resources": True, "required_resources": {}},
            ]
        }
        result = _extract_activities_from_spec(spec)
        assert result[0].duration_weeks == 3
        assert result[0].window_weeks is None

    def test_use_productive_recomputes_shorter_duration(self):
        """Lines 840-852: use_productive path, computed < window_w."""
        spec = {
            "activities": [
                {"item_id": "IT-01", "duration_weeks": 10, "required_resources": {"EQUIPE": 1}},
            ]
        }
        canonical = _make_canonical()
        cpu_lookup = {"CPU-01": {"codigo": "CPU-01", "cpu_meta": {"producao_horaria": 1000.0}}}
        producao_lookup = {"PROD-01": {"valor_horario": 1000.0}}
        result = _extract_activities_from_spec(spec, canonical, cpu_lookup, producao_lookup, [])
        assert result[0].duration_weeks < 10
        assert result[0].window_weeks == 10

    def test_use_productive_computed_none_keeps_window(self):
        """computed is None (CPU not found) → keeps window_w as fallback."""
        spec = {
            "activities": [
                {"item_id": "IT-01", "duration_weeks": 5, "required_resources": {}},
            ]
        }
        canonical = _make_canonical()
        result = _extract_activities_from_spec(spec, canonical, {}, {}, [])
        assert result[0].duration_weeks == 5
        assert result[0].window_weeks is None

    def test_ramp_params_fallback_computes_ramp_profile(self):
        """Lines 858-863: no ramp_profile_computed, ramp_params present with n_max > 0."""
        spec = {
            "activities": [
                {
                    "item_id": "IT-01",
                    "duration_weeks": 4,
                    "required_resources": {},
                    "ramp_params": {"n_max": 2, "n_inicial": 1},
                },
            ]
        }
        result = _extract_activities_from_spec(spec)
        assert result[0].ramp_profile is not None
        assert len(result[0].ramp_profile) == 4


class TestExtractPoolFromSpec:
    def test_explicit_resource_pool_used_as_is(self):
        """Line 892-893: explicit resource_pool → used directly, no inference."""
        spec = {"resource_pool": {"EQUIPE": 2}}
        result = _extract_pool_from_spec(spec)
        assert result.resources == {"EQUIPE": 2}

    def test_empty_resource_pool_infers_from_spec(self):
        """Lines 895-899: no explicit pool → falls to inferir_pool_minimo_from_spec."""
        spec = {"activities": [{"item_id": "IT-01", "required_resources": {"EQUIPE": 3}}]}
        with patch(
            "concilium.application.scheduling.inferir_pool_minimo_from_spec",
            return_value=({"EQUIPE": 3}, {"diag": "ok"}),
        ):
            result = _extract_pool_from_spec(spec)
        assert result.resources == {"EQUIPE": 3}
        assert spec["resource_pool"] == {"EQUIPE": 3}
        assert spec["pool_inferido_diag"] == {"diag": "ok"}


# ---------------------------------------------------------------------------
# _extract_activities — computed productive weeks falsy (line 480->483)
# ---------------------------------------------------------------------------


class TestExtractActivitiesComputedFalsy:
    def test_zero_productivity_keeps_default_duration(self):
        """cpu_lookup/producao_lookup present but productivity resolves to 0 →
        _compute_productive_weeks returns None → duration_weeks stays default 1."""
        canonical = _make_canonical()
        cpu_lookup = {"CPU-01": {"codigo": "CPU-01", "cpu_meta": {"producao_horaria": 0.0}}}
        producao_lookup = {"P1": {"valor_horario": 0.0}}
        validacoes: list = []
        activities = _extract_activities(canonical, cpu_lookup, producao_lookup, validacoes)
        assert len(activities) == 1
        assert activities[0].duration_weeks == 1


# ---------------------------------------------------------------------------
# _extract_dag — multiple predecessors per item, FF not last (line 523->514)
# ---------------------------------------------------------------------------


class TestExtractDagMultiplePredecessors:
    def test_ff_then_fs_predecessor_continues_inner_loop(self):
        """Item with 2 predecessors (FF first, FS second) → inner loop must
        continue past the FF branch back to the top for the second pred."""

        class FakePredFF:
            item_id = "IT-A"
            tipo = "FF"
            lag = 1
            completion_threshold_pct = 0.0

        class FakePredFS:
            item_id = "IT-B"
            tipo = "FS"
            lag = 0
            completion_threshold_pct = 0.9

        class FakeItem:
            item_id = "IT-C"
            descricao = "Item C"
            predecessores = [FakePredFF(), FakePredFS()]

            def predecessores_tipados(self):
                return self.predecessores

        class FakeCanonical:
            eap = [FakeItem()]
            activity_dag = None
            atividades = None

        dag = _extract_dag(FakeCanonical(), ["IT-A", "IT-B", "IT-C"])
        assert any(ep.tipo == "FF" for ep in dag.extended_precedences)
        assert dag.thresholds[("IT-B", "IT-C")] == 0.9


# ---------------------------------------------------------------------------
# _extract_activities_from_spec — ramp_profile branches (858->865, 862->865)
# ---------------------------------------------------------------------------


class TestExtractActivitiesFromSpecRampBranches:
    def test_precomputed_ramp_profile_used_directly(self):
        """Line 858->865: ramp_profile_computed already set → skip recompute
        entirely and the temp key is popped from the serialized dict."""
        spec = {
            "activities": [
                {
                    "item_id": "IT-01",
                    "duration_weeks": 3,
                    "required_resources": {},
                    "ramp_profile_computed": [0.5, 1.0, 0.5],
                },
            ]
        }
        result = _extract_activities_from_spec(spec)
        assert result[0].ramp_profile == [0.5, 1.0, 0.5]
        assert "ramp_profile_computed" not in spec["activities"][0]

    def test_ramp_params_n_max_negative_keeps_ramp_profile_none(self):
        """Line 862->865: n_max negative (falls through the `or 1` default
        since -1 is truthy) → n_pico <= 0 → skip _compute_ramp_profile,
        ramp_profile stays None."""
        spec = {
            "activities": [
                {
                    "item_id": "IT-01",
                    "duration_weeks": 3,
                    "required_resources": {},
                    "ramp_params": {"n_max": -1},
                },
            ]
        }
        result = _extract_activities_from_spec(spec)
        assert result[0].ramp_profile is None


# ---------------------------------------------------------------------------
# _cpv_build_usage — cpu found but no equipamentos configured (line 1581->1582)
# ---------------------------------------------------------------------------


class TestCpvBuildUsageNoEquipNeeded:
    def test_cpu_without_equipamentos_is_skipped(self):
        class FakeEapItem:
            item_id = "IT-01"
            cpu_id = "CPU-01"

        class FakeCanonical:
            eap = [FakeEapItem()]

        cpu_lookup = {"CPU-01": {"equipe": {}}}  # no "equipamentos" key → equip_needed={}
        usage = _cpv_build_usage(FakeCanonical(), cpu_lookup, {"IT-01": {}})
        assert usage == {}


# ---------------------------------------------------------------------------
# _rasfc_extract_inputs
# ---------------------------------------------------------------------------


class TestRasfcExtractInputs:
    def test_pool_config_propagated_from_inputs_to_spec(self):
        """Lines 1287-1288: inputs['pool_config'] copied into rcpsp_spec when
        the spec doesn't already carry its own pool_config."""
        spec = {
            "activities": [{"item_id": "IT-01", "duration_weeks": 2, "required_resources": {"EQUIPE": 1}}],
            "resource_pool": {"EQUIPE": 1},
        }
        canonical = _make_canonical()
        validacoes: list = []
        inputs = {"rcpsp_spec": spec, "pool_config": {"max_equipes": 2}}
        result = _rasfc_extract_inputs(canonical, inputs, validacoes)
        assert result is not None
        assert spec["pool_config"] == {"max_equipes": 2}

    def test_cpu_and_producao_lookup_trigger_catalog_enrichment(self):
        """Lines 1291-1297: cpu_lookup + producao_lookup present → deadline
        computed and _enrich_spec_resources_from_catalog invoked before extraction."""
        spec = {"activities": [{"item_id": "IT-01"}]}
        canonical = _make_canonical()
        cpu_lookup = {"CPU-01": {"codigo": "CPU-01", "producao_id_ref": "PROD-01"}}
        producao_lookup = {
            "PROD-01": {
                "valor_horario": 1.0,
                "composicao_padrao_equipe": {"funcoes": [{"funcao_id": "OP", "num_pessoas": 1}]},
            }
        }
        validacoes: list = []
        result = _rasfc_extract_inputs(canonical, {"rcpsp_spec": spec}, validacoes, cpu_lookup, producao_lookup)
        assert result is not None
        assert "required_resources" in spec["activities"][0]
        assert any(v.codigo == "VAL-CRON-CATALOGO-RES" for v in validacoes)

    def test_rcpsp_spec_no_activities_returns_none(self):
        """Lines 1302-1306: extracted activities empty → VAL-SCHED-01 + None."""
        canonical = _make_canonical()
        validacoes: list = []
        result = _rasfc_extract_inputs(canonical, {"rcpsp_spec": {"activities": []}}, validacoes)
        assert result is None
        assert any(v.codigo == "VAL-SCHED-01" and "rcpsp_spec" in v.mensagem for v in validacoes)

    def test_pool_inferido_diag_emits_val_pool_infer(self):
        """Lines 1310-1322: pool inferred → VAL-POOL-INFER validation with notas."""
        spec = {"activities": [{"item_id": "IT-01", "duration_weeks": 1, "required_resources": {"EQUIPE": 2}}]}
        canonical = _make_canonical()
        validacoes: list = []
        diag = {
            "objetivo": "custo",
            "pool_inferido": {"EQUIPE": 2},
            "makespan_estimado_semanas": 5,
            "makespan_minimo_semanas": 4,
            "notas": ["restrição de prazo"],
        }
        with patch(
            "concilium.application.scheduling.inferir_pool_minimo_from_spec",
            return_value=({"EQUIPE": 2}, diag),
        ):
            result = _rasfc_extract_inputs(canonical, {"rcpsp_spec": spec}, validacoes)
        assert result is not None
        assert any(v.codigo == "VAL-POOL-INFER" for v in validacoes)

    def test_no_rcpsp_spec_no_activities_returns_none(self):
        """Lines 1327-1329: else branch (no rcpsp_spec) → _extract_activities
        empty → VAL-SCHED-01 'Sem atividades.' + None."""

        class FakeCanonical:
            eap: list = []
            atividades = None

        validacoes: list = []
        result = _rasfc_extract_inputs(FakeCanonical(), {}, validacoes)
        assert result is None
        assert any(v.codigo == "VAL-SCHED-01" and v.mensagem == "Sem atividades." for v in validacoes)


# ---------------------------------------------------------------------------
# _rasfc_run_heuristics — inputs['heuristics'] overrides strategy (1362->1363)
# ---------------------------------------------------------------------------


class TestRasfcRunHeuristicsOverride:
    def test_heuristics_input_overrides_strategy_default(self):
        from concilium.application.scheduling import Activity, ActivityDAG, ResourcePool

        activities = [Activity(activity_id="A", description="A", duration_weeks=1, required_resources={})]
        dag = ActivityDAG(activities=activities, precedence=[], thresholds={}, extended_precedences=[])
        pool = ResourcePool(resources={})
        strategy = SimpleNamespace(algorithm="MINSLK", heuristics=["MINSLK"])
        fake_result = SimpleNamespace(heuristic="LPT", schedule=MagicMock(), quality_score=0.9)
        fake_candidate = SimpleNamespace(heuristic="LPT")

        with (
            patch(f"{_MOD_NAME}._mod_validacao.select_scheduling_algorithm", return_value=strategy),
            patch(f"{_MOD_NAME}._mod_validacao.explore_schedules", return_value=[fake_result]),
            patch(f"{_MOD_NAME}._mod_validacao._to_canonical_candidate", return_value=fake_candidate),
        ):
            candidates, relaxed, replenishable_resources = _rasfc_run_heuristics(
                activities, dag, pool, 4, {"heuristics": ["LPT"]}, []
            )
        assert replenishable_resources == []
        assert strategy.heuristics == ["LPT"]
        assert relaxed is False
        assert candidates == [fake_candidate]


# ---------------------------------------------------------------------------
# _convert_schedule_to_distribuicao — unmapped / missing-item branches
# ---------------------------------------------------------------------------


class TestConvertScheduleToDistribuicaoUnmapped:
    def test_activity_id_not_in_map_emits_val_cron_convert(self):
        """Lines 1458-1462: activity_to_item.get(sa.activity_id) is None → AVISO + continue."""

        class FakeCanonical:
            eap: list = []
            atividades = None

        sa = SimpleNamespace(activity_id="ACT-UNKNOWN")
        schedule_selected = SimpleNamespace(scheduled_activities=[sa])
        validacoes: list = []
        result = _convert_schedule_to_distribuicao(
            schedule_selected, FakeCanonical(), [], {}, {}, SimpleNamespace(), {}, {}, {}, validacoes
        )
        assert result == {}
        assert any(v.codigo == "VAL-CRON-CONVERT" for v in validacoes)

    def test_zero_quantitativo_skips_completude_check(self):
        """Line 1536->1554: item.quantitativo <= 0 → completude check skipped,
        but the item's (empty) distribuicao is still recorded."""

        class FakeEapItem:
            item_id = "IT-01"
            cpu_id = "CPU-01"
            quantitativo = 0.0

        class FakeProjeto:
            data_inicio = date(2025, 1, 6)

        class FakeCanonical:
            eap = [FakeEapItem()]
            atividades = None
            projeto = FakeProjeto()

        sa = SimpleNamespace(activity_id="IT-01", start_week=0, duration_weeks=1, assigned_resources={})
        schedule_selected = SimpleNamespace(scheduled_activities=[sa])
        validacoes: list = []
        result = _convert_schedule_to_distribuicao(
            schedule_selected,
            FakeCanonical(),
            ["2025-W02"],
            {},
            {},
            SimpleNamespace(horas_dia=8, dias_semana=5, eta_jornada=1.0),
            {},
            {},
            {},
            validacoes,
        )
        assert "IT-01" in result
        assert not any(v.codigo == "VAL-CRON-01" for v in validacoes)

    def test_mapped_item_not_found_in_eap_skips(self):
        """Line 1465-1466: item_id resolved but _find_item_by_id finds nothing → continue."""

        class FakeAtividade:
            atividade_id = "ACT-1"
            eap_item_id = "IT-MISSING"

        class FakeCanonical:
            eap: list = []
            atividades = [FakeAtividade()]

        sa = SimpleNamespace(activity_id="ACT-1")
        schedule_selected = SimpleNamespace(scheduled_activities=[sa])
        validacoes: list = []
        result = _convert_schedule_to_distribuicao(
            schedule_selected, FakeCanonical(), [], {}, {}, SimpleNamespace(), {}, {}, {}, validacoes
        )
        assert result == {}
        assert not any(v.codigo == "VAL-CRON-CONVERT" for v in validacoes)


# ---------------------------------------------------------------------------
# _check_wmp_pool — peak demand vs pool branches (1660->1661, 1664->1658)
# ---------------------------------------------------------------------------


class TestCheckWmpPoolBranches:
    def test_second_equip_within_pool_after_first_exceeds(self):
        """2 equipamentos: first exceeds pool (appends + loop continues back to
        the for at 1658), second stays within pool (false branch of 1660->1661)."""
        cpu = {
            "equipe": {
                "equipamentos": [
                    {"equip_id": "EQ-A", "num_unidades": 2},
                    {"equip_id": "EQ-B", "num_unidades": 1},
                ]
            }
        }
        policy = SimpleNamespace(n_maximo=3)
        pool = {"EQ-A": 4, "EQ-B": 10}  # EQ-A: 3*2=6 > 4 (violation); EQ-B: 3*1=3 <= 10 (ok)
        validacoes: list = []
        _check_wmp_pool("IT-01", cpu, policy, pool, validacoes)
        codes = [v.codigo for v in validacoes]
        assert codes.count("VAL-WMP-POOL") == 1

    def test_equip_not_in_pool_is_skipped_then_next_equip_is_checked(self):
        """Branch 1658->1659: primeiro equipamento sem eid correspondente no
        pool é pulado (continue), mas o segundo equipamento é normalmente
        processado (não interrompe o loop)."""
        cpu = {
            "equipe": {
                "equipamentos": [
                    {"equip_id": "EQ-DESCONHECIDO", "num_unidades": 1},
                    {"equip_id": "EQ-B", "num_unidades": 5},
                ]
            }
        }
        policy = SimpleNamespace(n_maximo=3)
        pool = {"EQ-B": 2}  # EQ-B: 3*5=15 > 2 (violation)
        validacoes: list = []
        _check_wmp_pool("IT-01", cpu, policy, pool, validacoes)
        codes = [v.codigo for v in validacoes]
        assert codes.count("VAL-WMP-POOL") == 1


# ---------------------------------------------------------------------------
# _determine_mode_and_distribuicao — rcpsp_spec success path (1858->1859)
# ---------------------------------------------------------------------------


class TestDetermineModeRcpspSpecSuccess:
    def test_rcpsp_spec_success_returns_auto_schedule_mode(self):
        canonical = _make_canonical()
        sched_sel = SimpleNamespace(scheduled_activities=[])
        with (
            patch(f"{_MOD_NAME}._mod_assembly._run_auto_schedule_fallback_chain", return_value=([], sched_sel, [])),
            patch(f"{_MOD_NAME}._mod_assembly._convert_schedule_to_distribuicao", return_value={"IT-01": {}}),
        ):
            mode, distr, candidates, selected, failed, replenishable_resources = _determine_mode_and_distribuicao(
                canonical_in=canonical,
                inputs={"rcpsp_spec": {"activities": []}},
                num_equipes_por_item=None,
                semanas_obra=["2025-W01"],
                cpu_lookup={},
                producao_lookup={},
                regime=SimpleNamespace(horas_dia=8, dias_semana=5),
                prat_semanal={},
                prat_mensal={},
                fator_calendario_semanal={},
                catalogo={},
                validacoes=[],
            )
        assert mode == "AUTO_SCHEDULE (rcpsp_spec)"
        assert failed is False
        assert distr == {"IT-01": {}}
        assert selected is sched_sel
        assert replenishable_resources == []

    def test_rcpsp_spec_no_schedule_selected_returns_failed(self):
        """Line 1857: fallback chain exhausted (schedule_selected falsy) -> early
        return with failed=True and empty distribuicao."""
        canonical = _make_canonical()
        with patch(
            f"{_MOD_NAME}._mod_assembly._run_auto_schedule_fallback_chain",
            return_value=([{"heuristic": "MINSLK"}], None, []),
        ):
            mode, distr, candidates, selected, failed, replenishable_resources = _determine_mode_and_distribuicao(
                canonical_in=canonical,
                inputs={"rcpsp_spec": {"activities": []}},
                num_equipes_por_item=None,
                semanas_obra=["2025-W01"],
                cpu_lookup={},
                producao_lookup={},
                regime=SimpleNamespace(horas_dia=8, dias_semana=5),
                prat_semanal={},
                prat_mensal={},
                fator_calendario_semanal={},
                catalogo={},
                validacoes=[],
            )
        assert mode == "AUTO_SCHEDULE (rcpsp_spec)"
        assert failed is True
        assert distr == {}
        assert selected is None
        assert replenishable_resources == []


# ---------------------------------------------------------------------------
# _build_cronograma_out — full heuristic → algorithm literal mapping (2012-2023)
# ---------------------------------------------------------------------------


class TestBuildCronogramaOutHeuristicMapping:
    @pytest.mark.parametrize(
        "heuristic,expected",
        [
            ("LPT", "LPT"),
            ("MAXRES", "MAXRES"),
            ("ES", "ES"),
            ("GR", "GR"),
            ("CP-SAT", "CP-SAT"),
            ("LNS", "LNS"),
        ],
    )
    def test_heuristic_maps_to_matching_algorithm_literal(self, heuristic, expected):
        schedule_selected = SimpleNamespace(
            heuristic=heuristic,
            quality_score=0.5,
            makespan=10,
            relaxed=False,
        )
        result = _build_cronograma_out(
            mode="AUTO_SCHEDULE",
            schedule_selected=schedule_selected,
            scheduled_activities_out=[],
            semanas_obra=["2025-W01", "2025-W02"],
            distribuicao_mensal={},
            validacoes=[],
        )
        assert result.algorithm == expected


class TestBuildProducoesPorAtividadeSemCpuResolvivel:
    def test_skips_item_sem_cpu_resolvivel(self):
        """ADR-139 D5: item cujo cpu_id não resolve (CPU ausente do lookup) é
        ignorado no pareamento atividade→Producao (`continue`), sem interromper
        o processamento dos demais itens."""
        from concilium.domain.models.canonical import EapItem

        build_producoes_por_atividade = _MOD._mod_spec._build_producoes_por_atividade

        items = [
            EapItem(item_id="eap-01", ordem=1, cpu_id="CPU-01", quantitativo=100.0),
            EapItem(item_id="eap-02", ordem=2, cpu_id="CPU-INEXISTENTE", quantitativo=50.0),
        ]
        cpu_lookup = {"CPU-01": {"producao_id_ref": "PROD-01"}}
        producao_lookup = {"PROD-01": {"id": "PROD-01", "valor_horario": 10.0}}

        result = build_producoes_por_atividade(items, cpu_lookup, producao_lookup)

        assert "eap-01" in result
        assert "eap-02" not in result
