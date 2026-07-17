"""Coverage tests for BlobToolInvocationRepository and InMemoryToolInvocationRepository.

Covers missing lines:
- src/concilium/infrastructure/storage/tool_invocation_store.py: 62-63, 67-68, 72-73, 77, 88-100
- src/concilium/application/tool_invocations/repository.py:
  59-60, 63-64, 67-69, 72-74, 77-79, 82-83, 87-88, 98-102, 112-114
"""

from __future__ import annotations

import json
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
    device_id: str | None = None,
    mcp_session_id: str | None = None,
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
        device_id=device_id,
        mcp_session_id=mcp_session_id,
    )


# ---------------------------------------------------------------------------
# ToolInvocation model — device_id/mcp_session_id (ADR-138 sessões)
# ---------------------------------------------------------------------------


class TestToolInvocationDeviceFields:
    def test_to_dict_includes_device_fields(self):
        inv = _make_invocation("id-1", device_id="falcon-falcon", mcp_session_id="sess-abc")
        d = inv.to_dict()
        assert d["device_id"] == "falcon-falcon"
        assert d["mcp_session_id"] == "sess-abc"

    def test_from_dict_round_trip(self):
        inv = _make_invocation("id-1", device_id="falcon-falcon", mcp_session_id="sess-abc")
        restored = ToolInvocation.from_dict(inv.to_dict())
        assert restored == inv

    def test_from_dict_defaults_to_none_when_absent(self):
        """Backward-compat: registros NDJSON gravados antes do ADR-138 não têm
        essas chaves — from_dict não deve levantar KeyError."""
        old_dict = {
            "id": "id-old",
            "tool_name": "ping",
            "input_keys": [],
            "user_id": "u1",
            "tenant_id": "tenant-x",
            "status": "success",
            "started_at": "2026-01-01T00:00:00Z",
            "finished_at": "2026-01-01T00:00:01Z",
        }
        restored = ToolInvocation.from_dict(old_dict)
        assert restored.device_id is None
        assert restored.mcp_session_id is None

    def test_defaults_to_none_when_not_passed_to_constructor(self):
        inv = ToolInvocation(
            id="id-1",
            tool_name="ping",
            input_keys=[],
            user_id="u1",
            tenant_id="tenant-x",
            status="success",
            started_at="2026-01-01T00:00:00Z",
            finished_at="2026-01-01T00:00:01Z",
        )
        assert inv.device_id is None
        assert inv.mcp_session_id is None


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


class TestBlobListByDevice:
    """list_by_device (ADR-138 sessões por dispositivo)."""

    def test_list_by_device_filters_correctly(self, blob_repo):
        blob_repo.append(_make_invocation("id-1", device_id="falcon-falcon"))
        blob_repo.append(_make_invocation("id-2", device_id="other-device"))
        blob_repo.append(_make_invocation("id-3", device_id="falcon-falcon"))

        result = blob_repo.list_by_device("falcon-falcon")
        assert len(result) == 2
        assert all(r.device_id == "falcon-falcon" for r in result)
        assert result[0].id == "id-3"

    def test_list_by_device_no_match(self, blob_repo):
        blob_repo.append(_make_invocation("id-1", device_id="falcon-falcon"))
        assert blob_repo.list_by_device("nonexistent") == []

    def test_list_by_device_with_limit(self, blob_repo):
        for i in range(4):
            blob_repo.append(_make_invocation(f"id-{i}", device_id="falcon-falcon"))
        result = blob_repo.list_by_device("falcon-falcon", limit=2)
        assert len(result) == 2
        assert result[0].id == "id-3"

    def test_list_by_device_ignores_invocations_without_device(self, blob_repo):
        """Invocações de fluxos sem device (client_id/secret direto) têm device_id=None
        e nunca devem aparecer em list_by_device (nem por engano casando None==None)."""
        blob_repo.append(_make_invocation("id-1", device_id=None))
        assert blob_repo.list_by_device("falcon-falcon") == []


class TestBlobCount:
    """count (line 77)."""

    def test_count_increments_on_append(self, blob_repo):
        assert blob_repo.count() == 0
        blob_repo.append(_make_invocation("id-1"))
        assert blob_repo.count() == 1
        blob_repo.append(_make_invocation("id-2"))
        assert blob_repo.count() == 2


class TestBlobDeleteByUser:
    """delete_by_user — direito de ser esquecido (LGPD Art. 18): anonimiza user_id."""

    def test_anonymizes_matching_records_in_active_file(self, blob_repo):
        blob_repo.append(_make_invocation("id-1", user_id="carla"))
        blob_repo.append(_make_invocation("id-2", user_id="carla"))
        blob_repo.append(_make_invocation("id-3", user_id="outro"))

        affected = blob_repo.delete_by_user("carla")

        assert affected == 2
        records = {r.id: r.user_id for r in blob_repo._read_all()}
        assert records == {"id-1": None, "id-2": None, "id-3": "outro"}

    def test_preserves_record_count_does_not_delete_lines(self, blob_repo):
        """Anonimiza, não apaga — preserva estatísticas agregadas (contagem/tools usadas)."""
        blob_repo.append(_make_invocation("id-1", user_id="carla"))
        blob_repo.append(_make_invocation("id-2", user_id="carla"))

        blob_repo.delete_by_user("carla")

        assert blob_repo.count() == 2

    def test_no_match_returns_zero_and_leaves_file_untouched(self, blob_repo):
        blob_repo.append(_make_invocation("id-1", user_id="outro"))

        affected = blob_repo.delete_by_user("carla")

        assert affected == 0
        assert blob_repo._read_all()[0].user_id == "outro"

    def test_anonymizes_archived_blobs_too(self, tmp_path):
        """Registros já rotacionados (audit-<timestamp>.jsonl) também precisam ser

        varridos — sem isso, user_id sobreviveria indefinidamente fora do alcance
        de list_by_user/list_recent (que só leem o arquivo ativo)."""
        storage = LocalBlobStorage(tmp_path)
        repo = BlobToolInvocationRepository(storage)
        archived_line = json.dumps(_make_invocation("id-old", user_id="carla").to_dict()) + "\n"
        storage.gravar_blob(".tool_invocations/audit-20260101T000000000000Z.jsonl", archived_line.encode())
        repo.append(_make_invocation("id-new", user_id="carla"))

        affected = repo.delete_by_user("carla")

        assert affected == 2
        archived_raw = storage.ler_blob(".tool_invocations/audit-20260101T000000000000Z.jsonl")
        assert json.loads(archived_raw.decode().strip())["user_id"] is None

    def test_malformed_line_in_archive_preserved_as_is(self, tmp_path):
        """Best-effort: uma linha ilegível não deve travar o esquecimento das demais."""
        storage = LocalBlobStorage(tmp_path)
        repo = BlobToolInvocationRepository(storage)
        good_line = json.dumps(_make_invocation("id-1", user_id="carla").to_dict())
        storage.gravar_blob(".tool_invocations/audit-20260101T000000000000Z.jsonl", f"{good_line}\nNOT_JSON\n".encode())

        affected = repo.delete_by_user("carla")

        assert affected == 1
        raw = storage.ler_blob(".tool_invocations/audit-20260101T000000000000Z.jsonl").decode()
        assert "NOT_JSON" in raw


class TestBlobRotation:
    """Rotação do audit.jsonl por idade OU tamanho (conjunção — o que vier primeiro).

    Limites configuráveis via CONCILIUM__TOOL_INVOCATIONS_ROTATE_MAX_AGE_DAYS
    (default 30 — "1 mês") e CONCILIUM__TOOL_INVOCATIONS_ROTATE_MAX_SIZE_MB
    (default 1024 — "1 GB")."""

    def test_no_rotation_under_both_thresholds(self, blob_repo, tmp_path):
        blob_repo.append(_make_invocation("id-1"))
        blob_repo.append(_make_invocation("id-2"))

        archives = [p for p in (tmp_path / ".tool_invocations").glob("audit-*.jsonl")]
        assert archives == []
        assert blob_repo.count() == 2

    def test_rotates_when_size_threshold_exceeded(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CONCILIUM__TOOL_INVOCATIONS_ROTATE_MAX_SIZE_MB", "0.0001")  # ~104 bytes
        storage = LocalBlobStorage(tmp_path)
        repo = BlobToolInvocationRepository(storage)

        repo.append(_make_invocation("id-1"))
        repo.append(_make_invocation("id-2"))  # deve estourar o limite minúsculo e rotacionar

        archives = list((tmp_path / ".tool_invocations").glob("audit-*.jsonl"))
        assert len(archives) == 1
        # arquivo ativo só tem a invocação mais recente (pós-rotação)
        assert repo.count() == 1
        assert repo.list_recent()[0].id == "id-2"

    def test_rotates_when_age_threshold_exceeded(self, tmp_path):
        import json

        blob_path = tmp_path / ".tool_invocations" / "audit.jsonl"
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        old_inv = _make_invocation("id-old")
        old_dict = old_inv.to_dict()
        old_dict["started_at"] = "2020-01-01T00:00:00+00:00"
        old_dict["finished_at"] = "2020-01-01T00:00:01+00:00"
        blob_path.write_text(json.dumps(old_dict) + "\n")

        storage = LocalBlobStorage(tmp_path)
        repo = BlobToolInvocationRepository(storage)
        repo.append(_make_invocation("id-new"))

        archives = list((tmp_path / ".tool_invocations").glob("audit-*.jsonl"))
        assert len(archives) == 1
        assert repo.count() == 1
        assert repo.list_recent()[0].id == "id-new"

    def test_does_not_rotate_when_oldest_record_within_max_age(self, tmp_path):
        import json
        from datetime import UTC, datetime

        blob_path = tmp_path / ".tool_invocations" / "audit.jsonl"
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        recent_inv = _make_invocation("id-recent")
        recent_dict = recent_inv.to_dict()
        recent_dict["started_at"] = datetime.now(UTC).isoformat()
        recent_dict["finished_at"] = datetime.now(UTC).isoformat()
        blob_path.write_text(json.dumps(recent_dict) + "\n")

        storage = LocalBlobStorage(tmp_path)
        repo = BlobToolInvocationRepository(storage)
        repo.append(_make_invocation("id-new"))

        archives = list((tmp_path / ".tool_invocations").glob("audit-*.jsonl"))
        assert archives == []
        assert repo.count() == 2

    def test_env_vars_configure_age_threshold(self, tmp_path, monkeypatch):
        """CONCILIUM__TOOL_INVOCATIONS_ROTATE_MAX_AGE_DAYS reduz o limite —
        um registro de 2 dias atrás, que sobreviveria ao default de 30 dias,
        força rotação com um limite de 1 dia."""
        import json
        from datetime import UTC, datetime, timedelta

        monkeypatch.setenv("CONCILIUM__TOOL_INVOCATIONS_ROTATE_MAX_AGE_DAYS", "1")
        blob_path = tmp_path / ".tool_invocations" / "audit.jsonl"
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        two_days_ago = (datetime.now(UTC) - timedelta(days=2)).isoformat()
        old_dict = _make_invocation("id-old").to_dict()
        old_dict["started_at"] = two_days_ago
        old_dict["finished_at"] = two_days_ago
        blob_path.write_text(json.dumps(old_dict) + "\n")

        storage = LocalBlobStorage(tmp_path)
        repo = BlobToolInvocationRepository(storage)
        repo.append(_make_invocation("id-new"))

        archives = list((tmp_path / ".tool_invocations").glob("audit-*.jsonl"))
        assert len(archives) == 1

    def test_malformed_first_line_does_not_crash_or_force_age_rotation(self, tmp_path):
        """Primeira linha ilegível: não levanta, e não força rotação por idade
        (só o tamanho ainda pode disparar rotação, independentemente)."""
        blob_path = tmp_path / ".tool_invocations" / "audit.jsonl"
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        blob_path.write_text("NOT_JSON\n")

        storage = LocalBlobStorage(tmp_path)
        repo = BlobToolInvocationRepository(storage)
        repo.append(_make_invocation("id-new"))  # não deve levantar

        archives = list((tmp_path / ".tool_invocations").glob("audit-*.jsonl"))
        assert archives == []

    def test_archived_content_is_preserved_but_not_queryable(self, tmp_path):
        """Conteúdo arquivado continua no storage (não é perdido), mas as
        queries (list_recent etc.) só enxergam o arquivo ativo pós-rotação —
        trade-off deliberado para manter as queries rápidas."""
        import json

        blob_path = tmp_path / ".tool_invocations" / "audit.jsonl"
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        old_dict = _make_invocation("id-old").to_dict()
        old_dict["started_at"] = "2020-01-01T00:00:00+00:00"
        old_dict["finished_at"] = "2020-01-01T00:00:01+00:00"
        blob_path.write_text(json.dumps(old_dict) + "\n")

        storage = LocalBlobStorage(tmp_path)
        repo = BlobToolInvocationRepository(storage)
        repo.append(_make_invocation("id-new"))

        archives = list((tmp_path / ".tool_invocations").glob("audit-*.jsonl"))
        assert len(archives) == 1
        archived_content = archives[0].read_text()
        assert "id-old" in archived_content

        ids_visible = {inv.id for inv in repo.list_recent(limit=100)}
        assert ids_visible == {"id-new"}

    def test_malformed_max_age_env_var_falls_back_to_default(self, monkeypatch):
        from concilium.infrastructure.storage.tool_invocation_store import _rotate_max_age_seconds

        monkeypatch.setenv("CONCILIUM__TOOL_INVOCATIONS_ROTATE_MAX_AGE_DAYS", "not-a-number")
        assert _rotate_max_age_seconds() == 30.0 * 86400

    def test_malformed_max_size_env_var_falls_back_to_default(self, monkeypatch):
        from concilium.infrastructure.storage.tool_invocation_store import _rotate_max_size_bytes

        monkeypatch.setenv("CONCILIUM__TOOL_INVOCATIONS_ROTATE_MAX_SIZE_MB", "not-a-number")
        assert _rotate_max_size_bytes() == 1024.0 * 1024 * 1024

    def test_oldest_started_at_skips_leading_blank_lines(self, blob_repo):
        inv = _make_invocation("id-1")
        raw = ("\n\n" + json.dumps(inv.to_dict()) + "\n").encode("utf-8")
        result = blob_repo._oldest_started_at(raw)
        assert result is not None
        assert result.isoformat() == "2026-06-23T10:00:00+00:00"

    def test_oldest_started_at_assumes_utc_for_naive_timestamp(self, blob_repo):
        inv_dict = _make_invocation("id-1").to_dict()
        inv_dict["started_at"] = "2026-06-23T10:00:00"  # sem timezone
        raw = (json.dumps(inv_dict) + "\n").encode("utf-8")
        result = blob_repo._oldest_started_at(raw)
        assert result is not None
        assert result.tzinfo is not None

    def test_oldest_started_at_all_blank_returns_none(self, blob_repo):
        assert blob_repo._oldest_started_at(b"\n\n   \n") is None


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


class TestInMemoryListByDevice:
    """list_by_device (ADR-138 sessões por dispositivo)."""

    def test_filters_by_device_id(self, mem_repo):
        mem_repo.append(_make_invocation("id-1", device_id="falcon-falcon"))
        mem_repo.append(_make_invocation("id-2", device_id="other-device"))
        mem_repo.append(_make_invocation("id-3", device_id="falcon-falcon"))

        result = mem_repo.list_by_device("falcon-falcon")
        assert len(result) == 2
        assert all(r.device_id == "falcon-falcon" for r in result)
        assert result[0].id == "id-3"

    def test_no_match_returns_empty(self, mem_repo):
        mem_repo.append(_make_invocation("id-1", device_id="falcon-falcon"))
        assert mem_repo.list_by_device("missing") == []

    def test_limit_applied_to_filtered_results(self, mem_repo):
        for i in range(5):
            mem_repo.append(_make_invocation(f"id-{i}", device_id="falcon-falcon"))
        result = mem_repo.list_by_device("falcon-falcon", limit=2)
        assert len(result) == 2
        assert result[0].id == "id-4"


class TestInMemoryCount:
    """count (lines 81-83)."""

    def test_count_starts_at_zero(self, mem_repo):
        assert mem_repo.count() == 0

    def test_count_increments(self, mem_repo):
        mem_repo.append(_make_invocation("id-1"))
        mem_repo.append(_make_invocation("id-2"))
        assert mem_repo.count() == 2


class TestInMemoryDeleteByUser:
    """delete_by_user — direito de ser esquecido (LGPD Art. 18): anonimiza user_id."""

    def test_anonymizes_matching_and_preserves_others(self, mem_repo):
        mem_repo.append(_make_invocation("id-1", user_id="carla"))
        mem_repo.append(_make_invocation("id-2", user_id="outro"))
        mem_repo.append(_make_invocation("id-3", user_id="carla"))

        affected = mem_repo.delete_by_user("carla")

        assert affected == 2
        assert mem_repo.count() == 3  # anonimiza, não apaga
        by_id = {r.id: r.user_id for r in mem_repo.list_recent(limit=10)}
        assert by_id == {"id-1": None, "id-2": "outro", "id-3": None}

    def test_no_match_returns_zero(self, mem_repo):
        mem_repo.append(_make_invocation("id-1", user_id="outro"))
        assert mem_repo.delete_by_user("carla") == 0


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
