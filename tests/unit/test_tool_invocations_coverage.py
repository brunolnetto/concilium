"""Coverage tests for BlobToolInvocationRepository and InMemoryToolInvocationRepository.

Covers missing lines:
- src/concilium/infrastructure/storage/tool_invocation_store.py: 62-63, 67-68, 72-73, 77, 88-100
- src/concilium/application/tool_invocations/repository.py:
  59-60, 63-64, 67-69, 72-74, 77-79, 82-83, 87-88, 98-102, 112-114
"""

from __future__ import annotations

import threading

import pytest

from concilium.application.tool_invocations.models import ToolInvocation
from concilium.application.tool_invocations.repository import (
    InMemoryToolInvocationRepository,
    get_tool_invocation_repository,
    reset_tool_invocation_repository,
)
from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage
from concilium.infrastructure.storage.tool_invocation_store import BlobToolInvocationRepository

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_invocation(
    id: str,
    tool_name: str = "ping",
    user_id: str | None = "u1",
) -> ToolInvocation:
    return ToolInvocation(
        id=id,
        tool_name=tool_name,
        input_keys=["a", "b"],
        user_id=user_id,
        tenant_id="tenant-x",
        status="success",
        started_at="2026-06-23T10:00:00Z",
        finished_at="2026-06-23T10:00:01Z",
        error_type=None,
    )


# ---------------------------------------------------------------------------
# BlobToolInvocationRepository tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def blob_repo(tmp_path):
    storage = LocalBlobStorage(tmp_path)
    return BlobToolInvocationRepository(storage)


class TestBlobReadAllEmpty:
    """_read_all with empty storage (lines 88-90)."""

    def test_empty_storage_returns_empty_list(self, blob_repo):
        assert blob_repo._read_all() == []

    def test_count_empty(self, blob_repo):
        assert blob_repo.count() == 0


class TestBlobReadAllMalformed:
    """_read_all handles malformed and blank lines (lines 91-99)."""

    def test_malformed_json_lines_are_skipped(self, tmp_path):
        storage = LocalBlobStorage(tmp_path)
        repo = BlobToolInvocationRepository(storage)
        # Write one valid and one invalid line directly
        blob_path = tmp_path / ".tool_invocations" / "audit.jsonl"
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        inv = _make_invocation("id-valid")
        import json

        valid_line = json.dumps(inv.to_dict()) + "\n"
        blob_path.write_bytes(valid_line.encode() + b"NOT_JSON\n" + b"\n")

        records = repo._read_all()
        assert len(records) == 1
        assert records[0].id == "id-valid"

    def test_blank_lines_are_skipped(self, tmp_path):
        storage = LocalBlobStorage(tmp_path)
        repo = BlobToolInvocationRepository(storage)
        blob_path = tmp_path / ".tool_invocations" / "audit.jsonl"
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        blob_path.write_bytes(b"\n   \n\n")

        records = repo._read_all()
        assert records == []

    def test_missing_required_key_skipped(self, tmp_path):
        storage = LocalBlobStorage(tmp_path)
        repo = BlobToolInvocationRepository(storage)
        blob_path = tmp_path / ".tool_invocations" / "audit.jsonl"
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        # JSON object missing "id" key
        import json

        bad_line = json.dumps({"tool_name": "x"}) + "\n"
        blob_path.write_bytes(bad_line.encode())

        records = repo._read_all()
        assert records == []


class TestBlobListRecent:
    """list_recent (lines 62-63)."""

    def test_list_recent_returns_most_recent_first(self, blob_repo):
        for i in range(3):
            blob_repo.append(_make_invocation(f"id-{i}"))
        recent = blob_repo.list_recent()
        assert [r.id for r in recent] == ["id-2", "id-1", "id-0"]

    def test_list_recent_with_limit(self, blob_repo):
        for i in range(5):
            blob_repo.append(_make_invocation(f"id-{i}"))
        recent = blob_repo.list_recent(limit=2)
        assert len(recent) == 2
        assert recent[0].id == "id-4"
        assert recent[1].id == "id-3"

    def test_list_recent_empty(self, blob_repo):
        assert blob_repo.list_recent() == []


class TestBlobListByTool:
    """list_by_tool (lines 67-68)."""

    def test_list_by_tool_filters_correctly(self, blob_repo):
        blob_repo.append(_make_invocation("id-1", tool_name="ping"))
        blob_repo.append(_make_invocation("id-2", tool_name="pong"))
        blob_repo.append(_make_invocation("id-3", tool_name="ping"))

        result = blob_repo.list_by_tool("ping")
        assert len(result) == 2
        assert all(r.tool_name == "ping" for r in result)
        # most recent first
        assert result[0].id == "id-3"

    def test_list_by_tool_no_match(self, blob_repo):
        blob_repo.append(_make_invocation("id-1", tool_name="ping"))
        assert blob_repo.list_by_tool("nonexistent") == []

    def test_list_by_tool_with_limit(self, blob_repo):
        for i in range(4):
            blob_repo.append(_make_invocation(f"id-{i}", tool_name="ping"))
        result = blob_repo.list_by_tool("ping", limit=2)
        assert len(result) == 2
        assert result[0].id == "id-3"


class TestBlobListByUser:
    """list_by_user (lines 72-73)."""

    def test_list_by_user_filters_correctly(self, blob_repo):
        blob_repo.append(_make_invocation("id-1", user_id="alice"))
        blob_repo.append(_make_invocation("id-2", user_id="bob"))
        blob_repo.append(_make_invocation("id-3", user_id="alice"))

        result = blob_repo.list_by_user("alice")
        assert len(result) == 2
        assert all(r.user_id == "alice" for r in result)
        assert result[0].id == "id-3"

    def test_list_by_user_no_match(self, blob_repo):
        blob_repo.append(_make_invocation("id-1", user_id="alice"))
        assert blob_repo.list_by_user("nobody") == []

    def test_list_by_user_with_limit(self, blob_repo):
        for i in range(4):
            blob_repo.append(_make_invocation(f"id-{i}", user_id="alice"))
        result = blob_repo.list_by_user("alice", limit=2)
        assert len(result) == 2
        assert result[0].id == "id-3"


class TestBlobCount:
    """count (line 77)."""

    def test_count_increments_on_append(self, blob_repo):
        assert blob_repo.count() == 0
        blob_repo.append(_make_invocation("id-1"))
        assert blob_repo.count() == 1
        blob_repo.append(_make_invocation("id-2"))
        assert blob_repo.count() == 2


# ---------------------------------------------------------------------------
# InMemoryToolInvocationRepository tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def mem_repo():
    return InMemoryToolInvocationRepository()


class TestInMemoryListRecent:
    """list_recent ordering (lines 59-60, 63-64, 66-69)."""

    def test_list_recent_most_recent_first(self, mem_repo):
        for i in range(3):
            mem_repo.append(_make_invocation(f"id-{i}"))
        result = mem_repo.list_recent()
        assert [r.id for r in result] == ["id-2", "id-1", "id-0"]

    def test_list_recent_respects_limit(self, mem_repo):
        for i in range(5):
            mem_repo.append(_make_invocation(f"id-{i}"))
        result = mem_repo.list_recent(limit=3)
        assert len(result) == 3
        assert result[0].id == "id-4"

    def test_list_recent_empty(self, mem_repo):
        assert mem_repo.list_recent() == []

    def test_list_recent_limit_larger_than_buffer(self, mem_repo):
        mem_repo.append(_make_invocation("only"))
        result = mem_repo.list_recent(limit=100)
        assert len(result) == 1


class TestInMemoryListByTool:
    """list_by_tool filter (lines 71-74)."""

    def test_filters_by_tool_name(self, mem_repo):
        mem_repo.append(_make_invocation("id-1", tool_name="alpha"))
        mem_repo.append(_make_invocation("id-2", tool_name="beta"))
        mem_repo.append(_make_invocation("id-3", tool_name="alpha"))

        result = mem_repo.list_by_tool("alpha")
        assert len(result) == 2
        assert all(r.tool_name == "alpha" for r in result)
        assert result[0].id == "id-3"

    def test_no_match_returns_empty(self, mem_repo):
        mem_repo.append(_make_invocation("id-1", tool_name="alpha"))
        assert mem_repo.list_by_tool("missing") == []

    def test_limit_applied_to_filtered_results(self, mem_repo):
        for i in range(5):
            mem_repo.append(_make_invocation(f"id-{i}", tool_name="alpha"))
        result = mem_repo.list_by_tool("alpha", limit=2)
        assert len(result) == 2
        assert result[0].id == "id-4"


class TestInMemoryListByUser:
    """list_by_user filter (lines 76-79)."""

    def test_filters_by_user_id(self, mem_repo):
        mem_repo.append(_make_invocation("id-1", user_id="alice"))
        mem_repo.append(_make_invocation("id-2", user_id="bob"))
        mem_repo.append(_make_invocation("id-3", user_id="alice"))

        result = mem_repo.list_by_user("alice")
        assert len(result) == 2
        assert all(r.user_id == "alice" for r in result)
        assert result[0].id == "id-3"

    def test_no_match_returns_empty(self, mem_repo):
        mem_repo.append(_make_invocation("id-1", user_id="alice"))
        assert mem_repo.list_by_user("nobody") == []

    def test_limit_applied_to_filtered_results(self, mem_repo):
        for i in range(4):
            mem_repo.append(_make_invocation(f"id-{i}", user_id="alice"))
        result = mem_repo.list_by_user("alice", limit=2)
        assert len(result) == 2
        assert result[0].id == "id-3"


class TestInMemoryCount:
    """count (lines 81-83)."""

    def test_count_starts_at_zero(self, mem_repo):
        assert mem_repo.count() == 0

    def test_count_increments(self, mem_repo):
        mem_repo.append(_make_invocation("id-1"))
        mem_repo.append(_make_invocation("id-2"))
        assert mem_repo.count() == 2


class TestInMemoryClear:
    """clear (lines 85-88)."""

    def test_clear_empties_buffer(self, mem_repo):
        mem_repo.append(_make_invocation("id-1"))
        mem_repo.append(_make_invocation("id-2"))
        mem_repo.clear()
        assert mem_repo.count() == 0
        assert mem_repo.list_recent() == []

    def test_clear_then_append(self, mem_repo):
        mem_repo.append(_make_invocation("id-1"))
        mem_repo.clear()
        mem_repo.append(_make_invocation("id-2"))
        assert mem_repo.count() == 1
        assert mem_repo.list_recent()[0].id == "id-2"


class TestInMemoryMaxSize:
    """max_size=0 means unlimited; max_size>0 is circular."""

    def test_unlimited_buffer(self):
        repo = InMemoryToolInvocationRepository(max_size=0)
        for i in range(20):
            repo.append(_make_invocation(f"id-{i}"))
        assert repo.count() == 20

    def test_circular_buffer_drops_oldest(self):
        repo = InMemoryToolInvocationRepository(max_size=3)
        for i in range(5):
            repo.append(_make_invocation(f"id-{i}"))
        assert repo.count() == 3
        recent = repo.list_recent()
        ids = [r.id for r in recent]
        assert "id-4" in ids
        assert "id-3" in ids
        assert "id-2" in ids
        assert "id-0" not in ids


# ---------------------------------------------------------------------------
# Singleton tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Ensure singleton is reset before and after each test in this module."""
    reset_tool_invocation_repository(None)
    yield
    reset_tool_invocation_repository(None)


class TestSingleton:
    """get_tool_invocation_repository and reset_tool_invocation_repository (lines 98-122)."""

    def test_get_creates_inmemory_by_default(self):
        repo = get_tool_invocation_repository()
        assert isinstance(repo, InMemoryToolInvocationRepository)

    def test_get_returns_same_instance(self):
        repo1 = get_tool_invocation_repository()
        repo2 = get_tool_invocation_repository()
        assert repo1 is repo2

    def test_reset_to_none_creates_new_instance(self):
        repo1 = get_tool_invocation_repository()
        reset_tool_invocation_repository(None)
        repo2 = get_tool_invocation_repository()
        assert repo1 is not repo2

    def test_reset_to_custom_repo(self):
        custom = InMemoryToolInvocationRepository(max_size=5)
        reset_tool_invocation_repository(custom)
        assert get_tool_invocation_repository() is custom

    def test_get_is_thread_safe(self):
        results = []

        def fetch():
            results.append(get_tool_invocation_repository())

        threads = [threading.Thread(target=fetch) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(set(id(r) for r in results)) == 1

    def test_inner_double_check_skips_reinit_on_race(self, monkeypatch):
        """Deterministically exercises the inner `if _repository is None:`
        False branch (line 112->114): simulates another thread having
        already initialized `_repository` while the current one was waiting
        to acquire `_repository_lock`."""
        import concilium.application.tool_invocations.repository as repo_mod

        reset_tool_invocation_repository(None)
        sentinel = InMemoryToolInvocationRepository(max_size=1)

        class _FakeLock:
            def __enter__(self):
                repo_mod._repository = sentinel
                return self

            def __exit__(self, *exc):
                return False

        monkeypatch.setattr(repo_mod, "_repository_lock", _FakeLock())

        result = repo_mod.get_tool_invocation_repository()
        assert result is sentinel

    def test_reset_with_custom_repo_persists(self):
        custom = InMemoryToolInvocationRepository(max_size=1)
        reset_tool_invocation_repository(custom)
        custom.append(_make_invocation("id-x"))
        repo = get_tool_invocation_repository()
        assert repo.count() == 1
