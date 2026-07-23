"""Coverage sweep 4 — telemetry, benchmark input derivation, inference."""

from __future__ import annotations

# ─── benchmark input_derivation/cronograma.py ─────────────────────────────────


class TestBenchmarkCronoDerivation:
    def test_drfs_get_item_ids_basic(self):
        from concilium.application.benchmarks.input_derivation.cronograma import _drfs_get_item_ids

        eap = [{"item_id": "eap-1"}, {"other": "no"}]
        result = _drfs_get_item_ids(eap)
        assert "eap-1" in result

    def test_scale_derived_equipes_noop(self):
        from concilium.application.benchmarks.input_derivation.cronograma import _scale_derived_equipes

        ref = {}
        _scale_derived_equipes(ref, {}, {})  # should not raise

    def test_drfs_get_item_ids_from_eap(self):
        from concilium.application.benchmarks.input_derivation.cronograma import _drfs_get_item_ids

        eap = [{"item_id": "eap-1"}, {"item_id": "eap-2"}, {"other": "no_id"}]
        result = _drfs_get_item_ids(eap)
        assert "eap-1" in result
        assert "eap-2" in result

    def test_drfs_build_week_map_numeric(self):
        from concilium.application.benchmarks.input_derivation.cronograma import _drfs_build_week_map

        cronograma = {"activities": [{"item_id": "a1", "semanas": {"1": {"num_equipes": 2}, "2": {"num_equipes": 3}}}]}
        result = _drfs_build_week_map(cronograma)
        assert isinstance(result, dict)

    def test_drfs_get_week_equipes_default(self):
        from concilium.application.benchmarks.input_derivation.cronograma import _drfs_get_week_equipes

        semanas = {"2026-W01": {"num_equipes": 3}}
        result = _drfs_get_week_equipes(semanas, "2026-W01", {})
        assert isinstance(result, int)

    def test_benchmark_input_deriver_init(self, tmp_path):
        from concilium.application.benchmarks.input_derivation.cronograma import BenchmarkInputDeriver

        deriver = BenchmarkInputDeriver(config_root=tmp_path)
        assert deriver is not None



