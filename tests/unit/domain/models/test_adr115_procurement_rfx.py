"""TDD ADR-115 — Semântica RFX (RFI/RFP) de procurement.

Cobre:
  D1/D2 — ProcurementIntent enum + mapeamento intent → PipelineMode
  D3    — deliverables por intent
  D5    — resolve_procurement_context: caminho, modo, método de custo
  F2    — BenchmarkRunner.run aceita procurement_intent

Nota: RFQ foi removido do domínio — o RFP aprovado vai diretamente para
aprovação do cliente (sem etapa intermediária de cotação).
"""

from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# D1/D2 — ProcurementIntent → PipelineMode
# ─────────────────────────────────────────────────────────────────────────────


class TestProcurementIntentEnum:
    def test_two_intents_exist(self):
        from concilium.domain.models.procurement import ProcurementIntent

        assert ProcurementIntent.RFI == "rfi"
        assert ProcurementIntent.RFP == "rfp"

    def test_rfq_no_longer_exists(self):
        from concilium.domain.models.procurement import ProcurementIntent

        assert not hasattr(ProcurementIntent, "RFQ")

    def test_from_string_case_insensitive(self):
        from concilium.domain.models.procurement import ProcurementIntent

        assert ProcurementIntent("rfi") == ProcurementIntent.RFI
        assert ProcurementIntent("RFP".lower()) == ProcurementIntent.RFP


class TestIntentToPipelineMode:
    """D2: RFI→OLTP, RFP→OLAP."""

    def test_rfi_maps_to_oltp(self):
        from concilium.application.skills.phase_classifier import PipelineMode
        from concilium.domain.models.procurement import ProcurementIntent, resolve_procurement_context

        ctx = resolve_procurement_context(ProcurementIntent.RFI)
        assert ctx.pipeline_mode == PipelineMode.OLTP

    def test_rfp_maps_to_olap(self):
        from concilium.application.skills.phase_classifier import PipelineMode
        from concilium.domain.models.procurement import ProcurementIntent, resolve_procurement_context

        ctx = resolve_procurement_context(ProcurementIntent.RFP)
        assert ctx.pipeline_mode == PipelineMode.OLAP

    def test_accepts_string_intent(self):
        from concilium.application.skills.phase_classifier import PipelineMode
        from concilium.domain.models.procurement import resolve_procurement_context

        ctx = resolve_procurement_context("rfi")
        assert ctx.pipeline_mode == PipelineMode.OLTP


# ─────────────────────────────────────────────────────────────────────────────
# D5/D6 — ProcurementContext: caminho, método de custo, baseline
# ─────────────────────────────────────────────────────────────────────────────


class TestProcurementContext:
    def test_rfi_context_fields(self):
        from concilium.domain.models.procurement import ProcurementIntent, resolve_procurement_context

        ctx = resolve_procurement_context(ProcurementIntent.RFI)
        assert ctx.intent == ProcurementIntent.RFI
        assert ctx.caminho == "RFI_EXPLORACAO_CATALOGO"
        assert "catálogo" in ctx.metodo_custo.lower() or "catalogo" in ctx.metodo_custo.lower()
        assert ctx.requires_baseline is False

    def test_rfp_context_fields(self):
        from concilium.domain.models.procurement import ProcurementIntent, resolve_procurement_context

        ctx = resolve_procurement_context(ProcurementIntent.RFP)
        assert ctx.caminho == "RFP_TECNICO_ECONOMICO"
        assert "operacional" in ctx.metodo_custo.lower()
        assert ctx.requires_baseline is False

    def test_context_has_deliverables(self):
        """D3: cada intent tem lista de entregáveis."""
        from concilium.domain.models.procurement import ProcurementIntent, resolve_procurement_context

        for intent in ProcurementIntent:
            ctx = resolve_procurement_context(intent)
            assert isinstance(ctx.deliverables, list)
            assert len(ctx.deliverables) >= 1

    def test_rfp_deliverables_superset_of_rfi(self):
        """D3: RFP package inclui 'tudo do RFI' + análise — deve ter mais entregáveis."""
        from concilium.domain.models.procurement import ProcurementIntent, resolve_procurement_context

        rfi = resolve_procurement_context(ProcurementIntent.RFI)
        rfp = resolve_procurement_context(ProcurementIntent.RFP)
        assert len(rfp.deliverables) > len(rfi.deliverables)

    def test_context_serializable_to_dict(self):
        """D6: procurement_context retornável como bloco (MCP)."""
        from concilium.domain.models.procurement import ProcurementIntent, resolve_procurement_context

        ctx = resolve_procurement_context(ProcurementIntent.RFP)
        d = ctx.to_dict()
        for key in ("intent", "caminho", "pipeline_mode", "metodo_custo", "requires_baseline", "deliverables"):
            assert key in d
        assert d["intent"] == "rfp"
        assert d["pipeline_mode"] == "olap"


# ─────────────────────────────────────────────────────────────────────────────
# D5/D6 — baseline validation (RFI/RFP — nenhuma exige baseline prévia)
# ─────────────────────────────────────────────────────────────────────────────


class TestBaselineValidation:
    def test_rfi_without_baseline_ok(self):
        from concilium.domain.models.procurement import ProcurementIntent, validate_procurement_baseline

        # nenhuma intenção exige baseline — chamada é no-op
        validate_procurement_baseline(ProcurementIntent.RFI, baseline_ref=None)

    def test_rfp_without_baseline_ok(self):
        from concilium.domain.models.procurement import ProcurementIntent, validate_procurement_baseline

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
        """Intent rfi/rfp devem mapear aos modos OLTP/OLAP."""
        from concilium.application.skills.phase_classifier import get_skills_for_mode
        from concilium.domain.models.procurement import resolve_procurement_context

        # RFI = OLTP = 6 skills
        ctx_rfi = resolve_procurement_context("rfi")
        assert len(get_skills_for_mode(ctx_rfi.pipeline_mode)) == 6
        # RFP = OLAP = todas
        ctx_rfp = resolve_procurement_context("rfp")
        assert len(get_skills_for_mode(ctx_rfp.pipeline_mode)) > 6


# ─────────────────────────────────────────────────────────────────────────────
# PHASE_MAP — fases "extra" fora da ordem canônica (_PHASE_ORDER)
# ─────────────────────────────────────────────────────────────────────────────


class TestPhaseMapExtraPhases:
    """Nenhum manifesto real hoje usa uma fase fora de `_PHASE_ORDER`, então o
    branch que inclui fases extras em `PHASE_MAP` (módulo, construção no import)
    fica dormente. Simulamos via MANIFEST_META patcheado + reload do módulo."""

    def test_phase_map_inclui_fase_extra_fora_da_ordem_canonica(self):
        import importlib.util
        import sys

        import concilium.application.skills as skills_pkg

        # Carrega uma cópia isolada de phase_classifier.py sob um nome de módulo
        # privado, em vez de `importlib.reload` no módulo real: reload muta o
        # objeto de módulo compartilhado em `sys.modules`, e qualquer código que
        # já tenha feito `from ...phase_classifier import PHASE_MAP` (ex.:
        # graph_exporter.py) mantém uma referência ao dict antigo — o reload (e
        # o reload de restauração no finally) nunca alcança esses consumidores,
        # deixando estado divergente para o resto da sessão de testes. Executar
        # o mesmo arquivo-fonte num módulo à parte cobre a mesma linha sem tocar
        # no módulo real.
        real_mod = sys.modules["concilium.application.skills.phase_classifier"]
        spec = importlib.util.spec_from_file_location("_test_phase_classifier_isolado", real_mod.__file__)
        isolated = importlib.util.module_from_spec(spec)
        # dataclasses (com `from __future__ import annotations`) resolve anotações via
        # `sys.modules[cls.__module__]` — precisa estar registrado antes do exec_module.
        sys.modules[spec.name] = isolated

        original_meta = skills_pkg.MANIFEST_META
        patched_meta = dict(original_meta)
        patched_meta["99-fake-skill-teste"] = {"phase": "Fase-Extra-Teste"}
        skills_pkg.MANIFEST_META = patched_meta
        try:
            spec.loader.exec_module(isolated)
        finally:
            skills_pkg.MANIFEST_META = original_meta
            del sys.modules[spec.name]

        assert "Fase-Extra-Teste" in isolated.PHASE_MAP
        assert isolated.PHASE_MAP["Fase-Extra-Teste"] == ["99-fake-skill-teste"]
