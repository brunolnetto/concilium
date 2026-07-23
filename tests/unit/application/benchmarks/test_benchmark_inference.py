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






# ─── inference.py lines 155-157 (canonical path + direto_itemizado) ──────────


class TestExtractReferenceProjectionCanonicalPath:
    """Lines 154-157: canonical branch with numeric direto_itemizado."""

    def _call(self, ref: dict):
        from concilium.application.benchmarks.inference import BenchmarkInferenceService

        return BenchmarkInferenceService._extract_reference_projection(ref)

    def test_canonical_path_sets_custo_direto_from_itemizado(self):
        """Line 155: out['custo_direto'] = direto_itemizado."""
        ref = {
            "resultado": {
                # No benchmark_confronto_referencia → confronto_ref is None
                "canonical": {
                    "custo": {
                        "direto_equipes": 500_000.0,
                        "total": 900_000.0,
                    },
                    "venda": {"total_com_bdi": 1_100_000.0},
                },
            },
            "planejamento_detalhado": [
                {"subtotal": {"sem_bdi": {"total": 620_000.0}}}
            ],
        }
        out, trace = self._call(ref)
        assert isinstance(out, dict)
        assert out["custo_direto"] == 620_000.0

    def test_canonical_path_computes_custo_total_when_indireto_numeric(self):
        """Lines 156-157: custo_total recomputed when custo_indireto is numeric."""
        ref = {
            "resultado": {
                "canonical": {
                    "custo": {
                        "direto_equipes": 500_000.0,
                        "indireto_overhead": 150_000.0,  # _sum_indireto sums this
                        "total": 900_000.0,
                    },
                    "venda": {"total_com_bdi": 1_100_000.0},
                },
            },
            "planejamento_detalhado": [
                {"subtotal": {"sem_bdi": {"total": 620_000.0}}}
            ],
        }
        out, trace = self._call(ref)
        assert isinstance(out, dict)
        assert out["custo_direto"] == 620_000.0
        assert out["custo_total"] == 620_000.0 + 150_000.0




# ─── inference.py line 220 (subtotal not-a-dict continue) ────────────────────


class TestSumPlanejamentoSubtotal:
    """Line 220: continue when subtotal is present but not a dict."""

    def test_non_dict_subtotal_is_skipped(self):
        from concilium.application.benchmarks.inference import BenchmarkInferenceService

        ref = {
            "planejamento_detalhado": [
                {"subtotal": "not_a_dict"},          # skipped (line 219-220)
                {"subtotal": {"sem_bdi": {"total": 300_000.0}}},  # counted
            ]
        }
        result = BenchmarkInferenceService._sum_planejamento_subtotal(ref, "sem_bdi")
        assert result == 300_000.0

    def test_none_subtotal_is_skipped(self):
        from concilium.application.benchmarks.inference import BenchmarkInferenceService

        ref = {
            "planejamento_detalhado": [
                {"subtotal": None},
                {"subtotal": {"sem_bdi": {"total": 200_000.0}}},
            ]
        }
        result = BenchmarkInferenceService._sum_planejamento_subtotal(ref, "sem_bdi")
        assert result == 200_000.0



