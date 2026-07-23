"""Coverage sweep — files with few missing lines (1-30 lines missing)."""

from __future__ import annotations

# ─── infrastructure/storage/flat_version_store.py ────────────────────────────


class TestFlatVersionStore:
    def _make_store(self, tmp_path):
        from concilium.infrastructure.storage.flat_version_store import FlatVersionStore
        from concilium.infrastructure.storage.project import ProjectStore

        store = ProjectStore.init(tmp_path, "Test", "ctx")
        v = store.new_version()
        return FlatVersionStore(store, v), store, v

    def test_plano_id_equals_version(self, tmp_path):
        fvs, store, v = self._make_store(tmp_path)
        assert fvs.plano_id == v

    def test_meta_has_plano_id(self, tmp_path):
        fvs, store, v = self._make_store(tmp_path)
        assert fvs.meta["plano_id"] == v

    def test_load_canonical_none_initially(self, tmp_path):
        fvs, store, v = self._make_store(tmp_path)
        assert fvs.load_canonical() is None

    def test_log_and_read_invocations(self, tmp_path):
        fvs, store, v = self._make_store(tmp_path)
        fvs.log_invocation({"skill": "01", "status": "OK"})
        records = fvs.read_invocations()
        assert len(records) == 1
        assert records[0]["skill"] == "01"

    def test_read_invocations_empty(self, tmp_path):
        fvs, store, v = self._make_store(tmp_path)
        assert fvs.read_invocations() == []

    def test_escopo_store_meta(self, tmp_path):
        fvs, store, v = self._make_store(tmp_path)
        meta = fvs.escopo_store.meta
        assert "escopo_id" in meta
        assert "contexto_id" in meta

