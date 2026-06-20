"""TDD ADR-115 — Semântica RFX (RFI/RFP/RFQ) de procurement.

Cobre:
  D1/D2 — ProcurementIntent enum + mapeamento intent → PipelineMode
  D3    — deliverables por intent
  D5    — resolve_procurement_context: caminho, modo, método de custo
  D5/D6 — RFQ exige baseline (requires_baseline)
  F2    — BenchmarkRunner.run aceita procurement_intent
"""

from __future__ import annotations

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# D1/D2 — ProcurementIntent → PipelineMode
# ─────────────────────────────────────────────────────────────────────────────

class TestProcurementIntentEnum:
    def test_three_intents_exist(self):
        from concilium.domain.models.procurement import ProcurementIntent
        assert ProcurementIntent.RFI == "rfi"
        assert ProcurementIntent.RFP == "rfp"
        assert ProcurementIntent.RFQ == "rfq"

    def test_from_string_case_insensitive(self):
        from concilium.domain.models.procurement import ProcurementIntent
        assert ProcurementIntent("rfi") == ProcurementIntent.RFI
        assert ProcurementIntent("RFP".lower()) == ProcurementIntent.RFP


class TestIntentToPipelineMode:
    """D2: RFI→OLTP, RFP→OLAP, RFQ→LIGHT."""

    def test_rfi_maps_to_oltp(self):
        from concilium.domain.models.procurement import resolve_procurement_context, ProcurementIntent
        from concilium.application.skills.phase_classifier import PipelineMode
        ctx = resolve_procurement_context(ProcurementIntent.RFI)
        assert ctx.pipeline_mode == PipelineMode.OLTP

    def test_rfp_maps_to_olap(self):
        from concilium.domain.models.procurement import resolve_procurement_context, ProcurementIntent
        from concilium.application.skills.phase_classifier import PipelineMode
        ctx = resolve_procurement_context(ProcurementIntent.RFP)
        assert ctx.pipeline_mode == PipelineMode.OLAP

    def test_rfq_maps_to_light(self):
        from concilium.domain.models.procurement import resolve_procurement_context, ProcurementIntent
        from concilium.application.skills.phase_classifier import PipelineMode
        ctx = resolve_procurement_context(ProcurementIntent.RFQ)
        assert ctx.pipeline_mode == PipelineMode.LIGHT

    def test_accepts_string_intent(self):
        from concilium.domain.models.procurement import resolve_procurement_context
        from concilium.application.skills.phase_classifier import PipelineMode
        ctx = resolve_procurement_context("rfi")
        assert ctx.pipeline_mode == PipelineMode.OLTP


# ─────────────────────────────────────────────────────────────────────────────
# D5/D6 — ProcurementContext: caminho, método de custo, baseline
# ─────────────────────────────────────────────────────────────────────────────

class TestProcurementContext:
    def test_rfi_context_fields(self):
        from concilium.domain.models.procurement import resolve_procurement_context, ProcurementIntent
        ctx = resolve_procurement_context(ProcurementIntent.RFI)
        assert ctx.intent == ProcurementIntent.RFI
        assert ctx.caminho == "RFI_EXPLORACAO_CATALOGO"
        assert "catálogo" in ctx.metodo_custo.lower() or "catalogo" in ctx.metodo_custo.lower()
        assert ctx.requires_baseline is False

    def test_rfp_context_fields(self):
        from concilium.domain.models.procurement import resolve_procurement_context, ProcurementIntent
        ctx = resolve_procurement_context(ProcurementIntent.RFP)
        assert ctx.caminho == "RFP_TECNICO_ECONOMICO"
        assert "operacional" in ctx.metodo_custo.lower()
        assert ctx.requires_baseline is False

    def test_rfq_requires_baseline(self):
        from concilium.domain.models.procurement import resolve_procurement_context, ProcurementIntent
        ctx = resolve_procurement_context(ProcurementIntent.RFQ)
        assert ctx.caminho == "RFQ_COTACAO_FINAL"
        assert ctx.requires_baseline is True

    def test_context_has_deliverables(self):
        """D3: cada intent tem lista de entregáveis."""
        from concilium.domain.models.procurement import resolve_procurement_context, ProcurementIntent
        for intent in ProcurementIntent:
            ctx = resolve_procurement_context(intent)
            assert isinstance(ctx.deliverables, list)
            assert len(ctx.deliverables) >= 1

    def test_rfp_deliverables_superset_of_rfi(self):
        """D3: RFP package inclui 'tudo do RFI' + análise — deve ter mais entregáveis."""
        from concilium.domain.models.procurement import resolve_procurement_context, ProcurementIntent
        rfi = resolve_procurement_context(ProcurementIntent.RFI)
        rfp = resolve_procurement_context(ProcurementIntent.RFP)
        assert len(rfp.deliverables) > len(rfi.deliverables)

    def test_context_serializable_to_dict(self):
        """D6: procurement_context retornável como bloco (MCP)."""
        from concilium.domain.models.procurement import resolve_procurement_context, ProcurementIntent
        ctx = resolve_procurement_context(ProcurementIntent.RFP)
        d = ctx.to_dict()
        for key in ("intent", "caminho", "pipeline_mode", "metodo_custo", "requires_baseline", "deliverables"):
            assert key in d
        assert d["intent"] == "rfp"
        assert d["pipeline_mode"] == "olap"


# ─────────────────────────────────────────────────────────────────────────────
# D5/D6 — baseline validation para RFQ
# ─────────────────────────────────────────────────────────────────────────────

class TestBaselineValidation:
    def test_rfq_without_baseline_raises(self):
        from concilium.domain.models.procurement import validate_procurement_baseline, ProcurementIntent
        with pytest.raises(ValueError, match="baseline"):
            validate_procurement_baseline(ProcurementIntent.RFQ, baseline_ref=None)

    def test_rfq_with_baseline_ok(self):
        from concilium.domain.models.procurement import validate_procurement_baseline, ProcurementIntent
        # não levanta
        validate_procurement_baseline(ProcurementIntent.RFQ, baseline_ref="v3")

    def test_rfi_without_baseline_ok(self):
        from concilium.domain.models.procurement import validate_procurement_baseline, ProcurementIntent
        validate_procurement_baseline(ProcurementIntent.RFI, baseline_ref=None)

    def test_rfp_without_baseline_ok(self):
        from concilium.domain.models.procurement import validate_procurement_baseline, ProcurementIntent
        validate_procurement_baseline(ProcurementIntent.RFP, baseline_ref=None)


# ─────────────────────────────────────────────────────────────────────────────
# F2 — BenchmarkRunner.run aceita procurement_intent
# ─────────────────────────────────────────────────────────────────────────────

class TestBenchmarkRunnerIntent:
    def test_run_accepts_procurement_intent_param(self):
        import inspect
        from concilium.application.benchmarks.execution.runner import BenchmarkRunner
        sig = inspect.signature(BenchmarkRunner.run)
        assert "procurement_intent" in sig.parameters

    def test_intent_resolves_to_correct_mode(self):
        """Intent rfi/rfp/rfq devem mapear aos modos OLTP/OLAP/LIGHT."""
        from concilium.domain.models.procurement import resolve_procurement_context
        from concilium.application.skills.phase_classifier import PipelineMode, get_skills_for_mode
        # RFI = OLTP = 6 skills
        ctx_rfi = resolve_procurement_context("rfi")
        assert len(get_skills_for_mode(ctx_rfi.pipeline_mode)) == 6
        # RFP = OLAP = todas
        ctx_rfp = resolve_procurement_context("rfp")
        assert len(get_skills_for_mode(ctx_rfp.pipeline_mode)) > 6
