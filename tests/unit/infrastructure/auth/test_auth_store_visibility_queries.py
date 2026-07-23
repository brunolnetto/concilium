"""Tests for AuthStore.record_visibility_queries / pop_pending_visibility_queries (ADR-143 D7/D8)."""

from __future__ import annotations


class TestRecordVisibilityQueries:
    def _make_store(self, tmp_path):
        from concilium.infrastructure.auth.auth_store import AuthStore

        return AuthStore(data_dir=tmp_path)

    def test_records_one_event_per_target(self, tmp_path):
        store = self._make_store(tmp_path)
        store.record_visibility_queries("observer1", ["operator"], ["target1", "target2"])

        pending = store.pop_pending_visibility_queries()
        assert len(pending) == 2
        assert {r.target_client_id for r in pending} == {"target1", "target2"}
        assert all(r.observer_client_id == "observer1" for r in pending)
        assert all(r.observer_roles == ["operator"] for r in pending)

    def test_self_query_never_recorded(self, tmp_path):
        store = self._make_store(tmp_path)
        store.record_visibility_queries("observer1", ["admin"], ["observer1", "target2"])

        pending = store.pop_pending_visibility_queries()
        assert len(pending) == 1
        assert pending[0].target_client_id == "target2"

    def test_no_targets_writes_nothing(self, tmp_path):
        store = self._make_store(tmp_path)
        store.record_visibility_queries("observer1", ["admin"], [])
        assert store.pop_pending_visibility_queries() == []

    def test_accumulates_across_multiple_calls(self, tmp_path):
        store = self._make_store(tmp_path)
        store.record_visibility_queries("observer1", ["operator"], ["target1"])
        store.record_visibility_queries("observer2", ["engineer"], ["target1"])

        pending = store.pop_pending_visibility_queries()
        assert len(pending) == 2
        assert {r.observer_client_id for r in pending} == {"observer1", "observer2"}


class TestPopPendingVisibilityQueries:
    def _make_store(self, tmp_path):
        from concilium.infrastructure.auth.auth_store import AuthStore

        return AuthStore(data_dir=tmp_path)

    def test_empty_when_nothing_recorded(self, tmp_path):
        store = self._make_store(tmp_path)
        assert store.pop_pending_visibility_queries() == []

    def test_drains_the_store(self, tmp_path):
        store = self._make_store(tmp_path)
        store.record_visibility_queries("observer1", ["operator"], ["target1"])

        first = store.pop_pending_visibility_queries()
        second = store.pop_pending_visibility_queries()

        assert len(first) == 1
        assert second == []
