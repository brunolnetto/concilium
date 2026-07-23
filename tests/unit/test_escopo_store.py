"""Coverage sweep 8 — cube_projection_views, side_effects, escopo_store, etapa_diffs."""

from __future__ import annotations

# ─── infrastructure/storage/escopo_store.py ──────────────────────────────────


class TestPlanoStore:
    def _make_plano_store(self, tmp_path):
        from concilium.infrastructure.storage.escopo_store import EscopoStore, PlanoStore

        plano_root = tmp_path / "escopos" / "esc-1" / "planos" / "plan-1"
        plano_root.mkdir(parents=True)
        es = EscopoStore(root=tmp_path / "escopos" / "esc-1")
        return PlanoStore(root=plano_root, escopo_store=es)

    def test_plano_store_creates(self, tmp_path):
        ps = self._make_plano_store(tmp_path)
        assert ps is not None
        assert ps.plano_id == "plan-1"

    def test_plano_store_meta(self, tmp_path):
        ps = self._make_plano_store(tmp_path)
        meta = ps.meta
        assert "plano_id" in meta

    def test_plano_store_load_canonical_none(self, tmp_path):
        ps = self._make_plano_store(tmp_path)
        assert ps.load_canonical() is None

    def test_plano_store_log_invocation(self, tmp_path):
        ps = self._make_plano_store(tmp_path)
        ps.log_invocation({"skill": "01", "status": "OK"})
        records = ps.read_invocations()
        assert len(records) == 1

    def test_plano_store_read_empty(self, tmp_path):
        ps = self._make_plano_store(tmp_path)
        assert ps.read_invocations() == []


class TestEscopoStore:
    def _make_escopo_store(self, tmp_path):
        from concilium.infrastructure.storage.escopo_store import EscopoStore

        escopo_root = tmp_path / "escopos" / "esc-1"
        escopo_root.mkdir(parents=True)
        return EscopoStore(root=escopo_root)

    def test_escopo_store_creates(self, tmp_path):
        es = self._make_escopo_store(tmp_path)
        assert es is not None

    def test_escopo_store_meta(self, tmp_path):
        es = self._make_escopo_store(tmp_path)
        assert "escopo_id" in es.meta

    def test_list_planos_empty(self, tmp_path):
        es = self._make_escopo_store(tmp_path)
        planos = es.list_plans()
        assert isinstance(planos, list)

    def test_create_plano(self, tmp_path):
        es = self._make_escopo_store(tmp_path)
        ps = es.create_plan(nome="Plano Principal")
        assert ps is not None
        assert ps.plano_id is not None



