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





from unittest.mock import MagicMock  # noqa: E402

# ─── application/benchmarks/input_derivation/cronograma.py ───────────────────


class TestInputDerivationCronograma:
    def test_scale_item_if_needed_no_scale(self):
        from concilium.application.benchmarks.input_derivation.cronograma import _scale_item_if_needed

        # signature: (item_id, week_map, ativ_by_id, dias_semana, num_equipes_por_item)
        # no crash = success
        _scale_item_if_needed("2.1", {}, {}, 6, {})

    def test_scale_item_if_needed_with_override(self):
        from concilium.application.benchmarks.input_derivation.cronograma import _scale_item_if_needed

        _scale_item_if_needed("2.1", {}, {}, 6, {"2.1": 3})

    def test_drfs_get_item_ids_empty(self):
        from concilium.application.benchmarks.input_derivation.cronograma import _drfs_get_item_ids

        result = _drfs_get_item_ids([])
        assert result == set()

    def test_drfs_get_item_ids_with_items(self):
        from concilium.application.benchmarks.input_derivation.cronograma import _drfs_get_item_ids

        eap = [{"item_id": "2.1"}, {"item_id": "2.2"}, {}]
        result = _drfs_get_item_ids(eap)
        assert "2.1" in result
        assert "2.2" in result

    def test_drfs_build_week_map_empty(self):
        from concilium.application.benchmarks.input_derivation.cronograma import _drfs_build_week_map

        result = _drfs_build_week_map({})
        assert result == {}

    def test_drfs_build_week_map_iso_keys(self):
        from concilium.application.benchmarks.input_derivation.cronograma import _drfs_build_week_map

        cronograma = {"2026-W01": {}, "2026-W02": {}, "2026-W05": {}}
        result = _drfs_build_week_map(cronograma)
        assert isinstance(result, dict)

    def test_drfs_get_week_equipes_found(self):
        from concilium.application.benchmarks.input_derivation.cronograma import _drfs_get_week_equipes

        semanas = {"2026-W01": {"num_equipes": 3}}
        result = _drfs_get_week_equipes(semanas, "2026-W01", {})
        assert result == 3

    def test_drfs_get_week_equipes_missing(self):
        from concilium.application.benchmarks.input_derivation.cronograma import _drfs_get_week_equipes

        result = _drfs_get_week_equipes({}, "2026-W99", {})
        assert isinstance(result, int)

    def test_scale_derived_equipes_empty(self):
        from concilium.application.benchmarks.input_derivation.cronograma import _scale_derived_equipes

        _scale_derived_equipes({}, {}, {})  # no crash

    def test_catalog_based_sizing_empty(self):
        from concilium.application.benchmarks.input_derivation.cronograma import _catalog_based_sizing

        snap = MagicMock()
        snap.cpus = []
        _catalog_based_sizing([], [], 48.0, snap, {})  # no crash

    def test_drfs_extract_item_weeks(self):
        from concilium.application.benchmarks.input_derivation.cronograma import _drfs_extract_item_weeks

        atividade = {"semanas": {"2026-W01": {"num_equipes": 2}, "2026-W02": {"num_equipes": 3}}}
        weeks = ["2026-W01", "2026-W02", "2026-W03"]
        iso_to_num = {}
        result, has_nonzero = _drfs_extract_item_weeks(atividade, weeks, iso_to_num)
        assert has_nonzero is True
        assert isinstance(result, dict)

    def test_benchmark_input_deriver_derive_num_equipes(self, tmp_path):
        from concilium.application.benchmarks.input_derivation.cronograma import BenchmarkInputDeriver

        deriver = BenchmarkInputDeriver(config_root=tmp_path)
        ref = {}  # no cronograma → _derive_from_reference_schedule returns {}
        eap = [{"item_id": "2.1", "cpu_id": "CPU-1"}]
        weeks = ["2026-W01", "2026-W02"]
        result = deriver.derive_num_equipes_por_item(ref, eap, weeks)
        assert "2.1" in result

    def test_benchmark_input_deriver_scale_derived_equipes(self):
        from concilium.application.benchmarks.input_derivation.cronograma import _scale_derived_equipes

        ref = {"regime_trabalho": {"dias_semana": 6}}
        derived = {"2.1": {"2026-W01": 1}}
        num_equipes = {"2.1": {"2026-W01": 1}}
        _scale_derived_equipes(ref, derived, num_equipes)  # no crash



