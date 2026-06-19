"""Tests for application/benchmarks/report/report_builder.py helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestAddFerramentaData:
    def test_adds_all_fields(self):
        from concilium.application.benchmarks.report.report_builder import _add_ferramenta_data

        projection = MagicMock()
        projection.ferramenta = {"custo_direto": 100}
        projection.ponto_equilibrio_ferramenta = {"L": 0.15}
        projection.ferramenta_breakdown_direto = {"CPU-1": 50}
        projection.ferramenta_breakdown_indireto = {"ADM": 20}
        projection.actionable_insights = [{"tip": "reduce"}]
        confronto: dict = {}
        _add_ferramenta_data(confronto, projection)
        assert confronto["ferramenta"] == {"custo_direto": 100}
        assert "ponto_equilibrio_ferramenta" in confronto
        assert "ferramenta_breakdown_direto" in confronto
        assert "ferramenta_breakdown_indireto" in confronto
        assert "actionable_insights" in confronto

    def test_skips_falsy_fields(self):
        from concilium.application.benchmarks.report.report_builder import _add_ferramenta_data

        projection = MagicMock()
        projection.ferramenta = None
        projection.preco_venda_fonte = None
        projection.ponto_equilibrio_ferramenta = {}
        projection.ferramenta_breakdown_direto = None
        projection.ferramenta_breakdown_indireto = []
        projection.actionable_insights = None
        confronto: dict = {}
        _add_ferramenta_data(confronto, projection)
        assert confronto == {}


class TestBuildDeltasFromConfronto:
    def test_computes_deltas(self):
        from concilium.application.benchmarks.report.report_builder import _build_deltas_from_confronto

        ref = {"custo_direto": 1000.0, "custo_indireto": 200.0, "preco_venda": 1500.0}
        fer = {"custo_direto": 1100.0, "custo_indireto": 200.0, "preco_venda": 1600.0}
        deltas = _build_deltas_from_confronto(ref, fer)
        assert deltas["custo_direto"]["absoluto"] == 100.0
        assert deltas["custo_direto"]["percentual"] == pytest.approx(10.0)
        assert deltas["custo_indireto"]["absoluto"] == 0.0

    def test_missing_key_skipped(self):
        from concilium.application.benchmarks.report.report_builder import _build_deltas_from_confronto

        deltas = _build_deltas_from_confronto({}, {"custo_direto": 100})
        assert "custo_direto" not in deltas

    def test_zero_ref_percentual_is_none(self):
        from concilium.application.benchmarks.report.report_builder import _build_deltas_from_confronto

        deltas = _build_deltas_from_confronto({"preco_venda": 0}, {"preco_venda": 100})
        assert deltas["preco_venda"]["percentual"] is None


class TestComputePeakRecursos:
    def test_empty_activities(self):
        from concilium.application.benchmarks.report.report_builder import _compute_peak_recursos

        result = _compute_peak_recursos([], {})
        assert result == {}

    def test_peak_computed(self):
        from concilium.application.benchmarks.report.report_builder import _compute_peak_recursos

        sa1 = MagicMock(activity_id="A1", start_week=1, end_week=2)
        sa2 = MagicMock(activity_id="A2", start_week=2, end_week=3)
        spec_acts = {
            "A1": {"required_resources": {"ESC": 2}},
            "A2": {"required_resources": {"ESC": 1}},
        }
        peak = _compute_peak_recursos([sa1, sa2], spec_acts)
        assert peak["ESC"] == 3  # week 2: A1+A2


class TestBqHelpers:
    def test_get_cause_known(self):
        from concilium.application.benchmarks.report.report_builder import _bq_get_cause

        assert _bq_get_cause("custo_direto") == "CATALOGO"
        assert _bq_get_cause("custo_indireto") == "CONSOLIDACAO"
        assert _bq_get_cause("preco_venda") == "PARAMETRIZACAO_BDI"
        assert _bq_get_cause("margem_pct") == "CONSOLIDACAO"

    def test_get_cause_unknown(self):
        from concilium.application.benchmarks.report.report_builder import _bq_get_cause

        assert _bq_get_cause("other") == "OUTROS"

    def test_build_gate_item(self):
        from concilium.application.benchmarks.report.report_builder import _bq_build_gate_item

        item = _bq_build_gate_item(
            metric="custo_direto",
            delta={"absoluto": 100.0, "percentual": 5.0},
            confronto={"referencia": {"custo_direto": 2000}, "ferramenta": {"custo_direto": 2100}},
            cause="CATALOGO",
            classe="A",
            severity="S1",
            phase="FASE_1",
            action="Revisar catálogo",
            owner="engenheiro",
        )
        assert item["metric"] == "custo_direto"
        assert item["severidade"] == "S1"
        assert item["sla_horas"] == 48
        assert item["status_acao"] == "ABERTA"

    def test_gate_item_s0_is_nao_aplicavel(self):
        from concilium.application.benchmarks.report.report_builder import _bq_build_gate_item

        item = _bq_build_gate_item("preco_venda", {}, {}, "OUTROS", "A", "S0", "P1", "n/a", "n/a")
        assert item["status_acao"] == "NAO_APLICAVEL"
        assert item["sla_horas"] == 0

    def test_compute_worst(self):
        from concilium.application.benchmarks.report.report_builder import _bq_compute_worst

        items = [{"severidade": "S1"}, {"severidade": "S3"}, {"severidade": "S0"}]
        assert _bq_compute_worst(items) == "S3"

    def test_compute_worst_empty(self):
        from concilium.application.benchmarks.report.report_builder import _bq_compute_worst

        assert _bq_compute_worst([]) == "S0"

    def test_check_critical_over_10_true(self):
        from concilium.application.benchmarks.report.report_builder import _bq_check_critical_over_10

        items = [{"metric": "custo_direto", "delta_percentual": 15.0}]
        assert _bq_check_critical_over_10(items, {"custo_direto"}) is True

    def test_check_critical_over_10_false(self):
        from concilium.application.benchmarks.report.report_builder import _bq_check_critical_over_10

        items = [{"metric": "custo_direto", "delta_percentual": 5.0}]
        assert _bq_check_critical_over_10(items, {"custo_direto"}) is False

    def test_get_decision_bloqueado(self):
        from concilium.application.benchmarks.report.report_builder import _bq_get_decision

        assert _bq_get_decision("S3", False) == "BLOQUEADO"

    def test_get_decision_bloqueado_investigacao(self):
        from concilium.application.benchmarks.report.report_builder import _bq_get_decision

        assert _bq_get_decision("S2", False) == "BLOQUEADO_COM_INVESTIGACAO"
        assert _bq_get_decision("S1", True) == "BLOQUEADO_COM_INVESTIGACAO"

    def test_get_decision_aprovado_com_ressalvas(self):
        from concilium.application.benchmarks.report.report_builder import _bq_get_decision

        assert _bq_get_decision("S1", False) == "APROVADO_COM_RESSALVAS"

    def test_get_decision_aprovado(self):
        from concilium.application.benchmarks.report.report_builder import _bq_get_decision

        assert _bq_get_decision("S0", False) == "APROVADO"


class TestFallbackCustoTotal:
    def test_no_custo_total_computes_from_parts(self):
        from concilium.application.benchmarks.report.report_builder import _fallback_custo_total

        result = _fallback_custo_total({"custo_direto": 1000.0, "custo_indireto": 200.0})
        assert result["custo_total"] == 1200.0

    def test_existing_custo_total_unchanged(self):
        from concilium.application.benchmarks.report.report_builder import _fallback_custo_total

        result = _fallback_custo_total({"custo_total": 999.0, "custo_direto": 1000.0, "custo_indireto": 200.0})
        assert result["custo_total"] == 999.0

    def test_missing_parts_no_override(self):
        from concilium.application.benchmarks.report.report_builder import _fallback_custo_total

        result = _fallback_custo_total({"custo_direto": 1000.0})  # no indireto
        assert "custo_total" not in result


class TestBuildRcpspSchedule:
    def test_builds_basic_schedule(self):
        from concilium.application.benchmarks.report.report_builder import _build_rcpsp_schedule
        from concilium.application.benchmarks.spec.spec_loader import ProjectSpec

        canonical = MagicMock()
        canonical.cronograma.algorithm = "CP-SAT"
        canonical.cronograma.makespan_weeks = 10
        canonical.cronograma.is_feasible = True
        canonical.cronograma.was_relaxed = False
        canonical.cronograma.scheduled_activities = []
        spec = MagicMock(spec=ProjectSpec)
        spec.inputs_cronograma = {}
        result = _build_rcpsp_schedule(canonical, spec)
        assert result["algorithm"] == "CP-SAT"
        assert result["makespan_weeks"] == 10

    def test_includes_deadline_and_folga(self):
        from concilium.application.benchmarks.report.report_builder import _build_rcpsp_schedule
        from concilium.application.benchmarks.spec.spec_loader import ProjectSpec

        canonical = MagicMock()
        canonical.cronograma.algorithm = "CP-SAT"
        canonical.cronograma.makespan_weeks = 8
        canonical.cronograma.is_feasible = True
        canonical.cronograma.was_relaxed = False
        canonical.cronograma.scheduled_activities = []
        spec = MagicMock(spec=ProjectSpec)
        spec.inputs_cronograma = {"rcpsp_spec": {"deadline_weeks": 10}}
        result = _build_rcpsp_schedule(canonical, spec)
        assert result["deadline_weeks"] == 10
        assert result["folga_semanas"] == 2
