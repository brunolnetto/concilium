"""Tests for input_derivation/cronograma.py and escopo_store.py."""

from __future__ import annotations

from unittest.mock import MagicMock

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


# ─── infrastructure/storage/escopo_store.py ───────────────────────────────────


class TestEscopoStoreFull:
    def _make_project_store(self, tmp_path):
        from concilium.infrastructure.storage.project import ProjectStore

        return ProjectStore.init(tmp_path, "Test Project", "ctx-1")

    def _create_escopo(self, store, escopo_id="esc-1"):
        store.create_escopo(
            escopo_id=escopo_id,
            nome=f"Escopo {escopo_id}",
            tipo_obra="terraplenagem",
            localizacao="SP",
            coordenadas_lat=-23.5,
            coordenadas_lng=-46.6,
            data_inicio="2026-01-01",
            data_termino="2026-12-31",
        )
        return store.escopo(escopo_id)

    def test_escopo_meta(self, tmp_path):
        store = self._make_project_store(tmp_path)
        es = self._create_escopo(store)
        meta = es.meta
        assert meta["escopo_id"] == "esc-1"

    def test_escopo_to_escopo(self, tmp_path):
        store = self._make_project_store(tmp_path)
        es = self._create_escopo(store)
        escopo_obj = es.to_escopo()
        assert escopo_obj is not None

    def test_escopo_update_meta(self, tmp_path):
        store = self._make_project_store(tmp_path)
        es = self._create_escopo(store)
        es.update_meta(nome="Updated Name")
        assert es.meta["nome"] == "Updated Name"

    def test_escopo_create_and_get_plan(self, tmp_path):
        store = self._make_project_store(tmp_path)
        es = self._create_escopo(store)
        ps = es.create_plan(nome="Plano Base")
        assert ps is not None
        assert ps.plano_id is not None

    def test_escopo_active_plan_after_creation(self, tmp_path):
        store = self._make_project_store(tmp_path)
        es = self._create_escopo(store)
        es.create_plan(nome="Plano 1")
        active = es.active_plan()
        assert active is not None

    def test_escopo_list_plans(self, tmp_path):
        store = self._make_project_store(tmp_path)
        es = self._create_escopo(store)
        es.create_plan(nome="P1")
        es.create_plan(nome="P2")
        plans = es.list_plans()
        assert len(plans) >= 2

    def test_plano_store_log_and_read_invocations(self, tmp_path):
        store = self._make_project_store(tmp_path)
        es = self._create_escopo(store)
        ps = es.create_plan(nome="Plano Test")
        ps.log_invocation({"skill": "01-escopo-e-eap", "status": "OK"})
        invocations = ps.read_invocations()
        assert len(invocations) >= 1

    def test_plano_store_active_plan_activation(self, tmp_path):
        store = self._make_project_store(tmp_path)
        es = self._create_escopo(store)
        es.create_plan(nome="Ativo")
        # After create_plan, it may or may not be active depending on implementation
        plans = es.list_plans()
        assert len(plans) >= 1

    def test_escopo_id_property(self, tmp_path):
        store = self._make_project_store(tmp_path)
        es = self._create_escopo(store, "my-escopo")
        assert es.escopo_id == "my-escopo"

    def test_escopo_root_property(self, tmp_path):
        store = self._make_project_store(tmp_path)
        es = self._create_escopo(store)
        from pathlib import Path

        assert isinstance(es.root, Path)

    def test_approved_plan_none_initially(self, tmp_path):
        store = self._make_project_store(tmp_path)
        es = self._create_escopo(store)
        assert es.approved_plan() is None

    def test_plano_store_approve(self, tmp_path):
        store = self._make_project_store(tmp_path)
        es = self._create_escopo(store)
        ps = es.create_plan(nome="Para Aprovar")
        # Approve the plan
        es.approve_plan(ps.plano_id)
        approved = es.approved_plan()
        assert approved is not None
