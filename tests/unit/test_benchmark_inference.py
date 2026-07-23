"""Coverage sweep 4 — telemetry, benchmark input derivation, inference."""

from __future__ import annotations

# ─── application/benchmarks/inference.py ─────────────────────────────────────


class TestBenchmarkInference:
    def test_inference_service_importable(self):
        from concilium.application.benchmarks.inference import BenchmarkInferenceService

        assert BenchmarkInferenceService is not None

    def test_derive_returns_pack(self):
        from concilium.application.benchmarks.inference import BenchmarkInferenceService

        pack = BenchmarkInferenceService.derive(None)
        assert pack is not None

    def test_apply_to_skill_inputs(self):
        from concilium.application.benchmarks.inference import BenchmarkInferenceService

        pack = BenchmarkInferenceService.derive(None)
        inputs = {"01-escopo-e-eap": {}}
        result = BenchmarkInferenceService.apply_to_skill_inputs(inputs, pack)
        assert isinstance(result, dict)



