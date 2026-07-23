"""Coverage tests for report_builder.py — targets missing lines:
14, 83-95, 180, 183->186, 225, 287, 293->291, 301->303, 304, 309-310, 338->340, 348, 350.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from concilium.application.benchmarks.report.report_builder import (
    BenchmarkReportBuilder,
    _build_composicao_item,
    _build_rcpsp_schedule,
    _load_inference_service,
)

# ---------------------------------------------------------------------------
# Line 14: _load_inference_service raises RuntimeError when class not found
# ---------------------------------------------------------------------------


class TestLoadInferenceService:
    def test_raises_when_class_missing(self):
        """Line 14: BenchmarkInferenceService not in inference module → RuntimeError."""
        import concilium.application.benchmarks.inference as inf_mod

        original = getattr(inf_mod, "BenchmarkInferenceService", None)
        try:
            inf_mod.BenchmarkInferenceService = None  # type: ignore[attr-defined]
            with pytest.raises(RuntimeError, match="BenchmarkInferenceService indisponivel"):
                _load_inference_service()
        finally:
            if original is not None:
                inf_mod.BenchmarkInferenceService = original  # type: ignore[attr-defined]
            else:
                del inf_mod.BenchmarkInferenceService


# ---------------------------------------------------------------------------
# Lines 83-95: _build_rcpsp_schedule with scheduled activities and spec_acts
# ---------------------------------------------------------------------------


class TestBuildRcpspScheduleWithActivities:
    def _make_spec(self, activities=None, deadline_weeks=None):
        spec = MagicMock()
        rcpsp = {}
        if activities is not None:
            rcpsp["activities"] = activities
        if deadline_weeks is not None:
            rcpsp["deadline_weeks"] = deadline_weeks
        spec.inputs_cronograma = {"rcpsp_spec": rcpsp}
        return spec

    def test_with_scheduled_activities_and_spec_acts_builds_peak(self):
        """Lines 83-95: scheduled_activities + spec_acts → atividades + pico_recursos."""
        sa = MagicMock(activity_id="A1", start_week=1, end_week=3, duration_weeks=3)
        canonical = MagicMock()
        canonical.cronograma.algorithm = "CP-SAT"
        canonical.cronograma.makespan_weeks = 3
        canonical.cronograma.is_feasible = True
        canonical.cronograma.was_relaxed = False
        canonical.cronograma.scheduled_activities = [sa]
        spec = self._make_spec(activities=[{"item_id": "A1", "required_resources": {"ESC": 2}}])
        result = _build_rcpsp_schedule(canonical, spec)
        assert "atividades" in result
        assert "A1" in result["atividades"]
        assert "pico_recursos" in result
        assert result["pico_recursos"]["ESC"] == 2

    def test_with_activities_but_empty_spec_acts_no_peak(self):
        """Lines 83-91: scheduled_activities with no spec_acts → atividades, no pico_recursos."""
        sa = MagicMock(activity_id="A2", start_week=1, end_week=2, duration_weeks=2)
        canonical = MagicMock()
        canonical.cronograma.algorithm = "MINSLK"
        canonical.cronograma.makespan_weeks = 2
        canonical.cronograma.is_feasible = True
        canonical.cronograma.was_relaxed = False
        canonical.cronograma.scheduled_activities = [sa]
        spec = self._make_spec(activities=[])  # empty spec acts
        result = _build_rcpsp_schedule(canonical, spec)
        assert "atividades" in result
        assert "pico_recursos" not in result

    def test_with_activities_no_required_resources_empty_peak_no_pico(self):
        """Lines 83-95: spec_acts exist but required_resources empty → peak is empty → no pico."""
        sa = MagicMock(activity_id="A3", start_week=1, end_week=1, duration_weeks=1)
        canonical = MagicMock()
        canonical.cronograma.algorithm = "CP-SAT"
        canonical.cronograma.makespan_weeks = 1
        canonical.cronograma.is_feasible = True
        canonical.cronograma.was_relaxed = False
        canonical.cronograma.scheduled_activities = [sa]
        spec = self._make_spec(activities=[{"item_id": "A3", "required_resources": {}}])
        result = _build_rcpsp_schedule(canonical, spec)
        assert "atividades" in result
        assert "pico_recursos" not in result


# ---------------------------------------------------------------------------
# Line 180, 183->186: _build_composicao_item edge cases
# ---------------------------------------------------------------------------


class TestBuildComposicaoItem:
    def test_both_none_returns_none(self):
        """Line 180: ref=None and tool=None → return None."""

        assert _build_composicao_item(None, None) is None

    def test_only_ref_provided(self):
        """Line 183->186: ref not None but tool is None → no delta computed."""

        result = _build_composicao_item(1000.0, None)
        assert result is not None
        assert result["referencia"] == 1000.0
        assert result["ferramenta"] is None
        assert result["delta_absoluto"] is None
        assert result["delta_percentual"] is None

    def test_only_tool_provided(self):
        """Line 183->186: ref is None but tool not None → no delta computed."""

        result = _build_composicao_item(None, 500.0)
        assert result is not None
        assert result["referencia"] is None
        assert result["ferramenta"] == 500.0
        assert result["delta_absoluto"] is None


# ---------------------------------------------------------------------------
# Line 225: _classify_delta with None input
# ---------------------------------------------------------------------------


class TestClassifyDeltaNone:
    def test_none_delta_returns_na_s0(self):
        """Line 225: delta_pct=None → ("N/A", "S0")."""
        builder = BenchmarkReportBuilder()
        assert builder._classify_delta(None) == ("N/A", "S0")


# ---------------------------------------------------------------------------
# Line 287: _build_composicao_final returns None when ref or tool is None
# ---------------------------------------------------------------------------


class TestBuildComposicaoFinal:
    def test_returns_none_when_referencia_is_none(self):
        """Line 287: referencia=None → return None."""
        assert BenchmarkReportBuilder._build_composicao_final(None, {"custo_direto": 100}) is None

    def test_returns_none_when_ferramenta_is_none(self):
        """Line 287: ferramenta=None → return None."""
        assert BenchmarkReportBuilder._build_composicao_final({"custo_direto": 100}, None) is None

    def test_returns_none_when_all_items_are_none_values(self):
        """Lines 293->291: all _build_composicao_item calls return None → composicao or None = None."""
        # Both ref and tool have no overlap on the tracked keys → all entries None → result is None
        result = BenchmarkReportBuilder._build_composicao_final({}, {})
        assert result is None


# ---------------------------------------------------------------------------
# Lines 301->303, 304, 309-310: _finalize_confronto branches
# ---------------------------------------------------------------------------


class TestFinalizeConfronto:
    def _builder(self):
        return BenchmarkReportBuilder()

    def test_composicao_final_none_not_added_to_confronto(self):
        """Lines 301->303: _build_composicao_final returns None → no composicao_final in confronto."""
        builder = self._builder()
        # referencia and ferramenta both empty → composicao items all None → composicao_final=None
        confronto = {"referencia": {}, "ferramenta": {}}
        builder._finalize_confronto(confronto, None)
        assert "composicao_final" not in confronto
        assert "deltas" in confronto  # deltas still built (empty)

    def test_breakdown_added_when_breakdown_key_present(self):
        """Line 304: ferramenta_breakdown_direto in confronto → breakdown_por_fase set."""
        builder = self._builder()
        confronto = {"ferramenta_breakdown_direto": {"CPU-1": 50.0}}
        builder._finalize_confronto(confronto, None)
        assert "breakdown_por_fase" in confronto
        assert confronto["breakdown_por_fase"]["direto"] == {"CPU-1": 50.0}

    def test_ponto_equilibrio_referencia_set_when_ref_has_pe(self):
        """Lines 309-310: ref has ponto_de_equilibrio → ponto_equilibrio_referencia added."""
        builder = self._builder()
        confronto = {}
        ref = {
            "ponto_de_equilibrio": {
                "total_hc": 12,
                "total_custo_fixo": 50000.0,
                "equipes": [{"id": "eq1"}, {"id": "eq2"}],
            }
        }
        builder._finalize_confronto(confronto, ref)
        assert "ponto_equilibrio_referencia" in confronto
        assert confronto["ponto_equilibrio_referencia"]["total_hc"] == 12
        assert confronto["ponto_equilibrio_referencia"]["equipes"] == 2


# ---------------------------------------------------------------------------
# Lines 338->340, 348, 350: BenchmarkReportBuilder.build() branches
# ---------------------------------------------------------------------------


class TestBuildMethod:
    def _make_spec(self):
        from concilium.application.benchmarks.spec.spec_loader import ProjectSpec

        spec = MagicMock(spec=ProjectSpec)
        spec.nome = "TestProject"
        spec.slug = "test-proj"
        spec.inputs_cronograma = {}
        return spec

    def _make_canonical(self, with_cronograma=False):
        canonical = MagicMock()
        if with_cronograma:
            canonical.cronograma.algorithm = "CP-SAT"
            canonical.cronograma.makespan_weeks = 5
            canonical.cronograma.is_feasible = True
            canonical.cronograma.was_relaxed = False
            canonical.cronograma.scheduled_activities = []
        else:
            canonical.cronograma = None
        return canonical

    def _make_projection(self):
        proj = MagicMock()
        proj.ferramenta = None
        proj.preco_venda_fonte = None
        proj.ponto_equilibrio_ferramenta = None
        proj.ferramenta_breakdown_direto = None
        proj.ferramenta_breakdown_indireto = None
        proj.actionable_insights = None
        return proj

    def test_ref_confronto_none_skips_referencia(self):
        """Lines 338->340: inference_pack has no reference_projection, extract returns None."""
        builder = BenchmarkReportBuilder()
        spec = self._make_spec()
        canonical = self._make_canonical()

        with (
            patch.object(
                BenchmarkReportBuilder,
                "_extract_referencia_confronto",
                return_value=None,
            ),
            patch(
                "concilium.application.benchmarks.report.report_builder.BenchmarkProjection.from_canonical",
                return_value=self._make_projection(),
            ),
        ):
            report = builder.build(
                spec=spec,
                version="1.0",
                results_log=[],
                ref={"some": "ref"},  # ref is truthy, but extract returns None
                canonical=canonical,
                inference_pack=None,
            )
        assert "referencia" not in report["confronto"]

    def test_build_with_cronograma_adds_rcpsp_schedule(self):
        """Line 348: canonical with cronograma → rcpsp_schedule in report."""
        builder = BenchmarkReportBuilder()
        spec = self._make_spec()
        canonical = self._make_canonical(with_cronograma=True)

        with patch(
            "concilium.application.benchmarks.report.report_builder.BenchmarkProjection.from_canonical",
            return_value=self._make_projection(),
        ):
            report = builder.build(
                spec=spec,
                version="1.0",
                results_log=[],
                ref=None,
                canonical=canonical,
            )
        assert "rcpsp_schedule" in report

    def test_build_with_erro_in_log_sets_inviavel(self):
        """Line 350: results_log has entry with status=ERRO → status_final=INVIAVEL."""
        builder = BenchmarkReportBuilder()
        spec = self._make_spec()
        canonical = self._make_canonical()

        with patch(
            "concilium.application.benchmarks.report.report_builder.BenchmarkProjection.from_canonical",
            return_value=self._make_projection(),
        ):
            report = builder.build(
                spec=spec,
                version="1.0",
                results_log=[{"skill": "03", "status": "ERRO"}],
                ref=None,
                canonical=canonical,
            )
        assert report["status_final"] == "INVIAVEL"
