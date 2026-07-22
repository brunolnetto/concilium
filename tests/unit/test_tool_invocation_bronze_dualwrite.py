"""Testes para dual-write de tool_invocations no Bronze (ADR-112 extensão).

Antes deste fix, tool_invocations vivia inteiramente fora do medalhão
Bronze/Silver/Gold — só existia em `.tool_invocations/audit.jsonl`, consultável
apenas via GET /observability/audit. append() agora também grava uma cópia em
observability/bronze/tool_invocations/, alimentando o mesmo pipeline incremental
que logs/traces/metrics já usam.
"""

from __future__ import annotations

import json

import pytest

from concilium.application.tool_invocations.models import ToolInvocation
from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage
from concilium.infrastructure.storage.tool_invocation_store import BlobToolInvocationRepository


def _make_invocation(id: str = "id-1", **overrides) -> ToolInvocation:
    defaults = dict(
        id=id,
        tool_name="listar_projetos",
        input_keys=["a"],
        user_id="AGIS-user-1",
        tenant_id="tenant-x",
        status="success",
        started_at="2026-07-20T10:00:00Z",
        finished_at="2026-07-20T10:00:01Z",
        error_type=None,
        device_id="device-1",
        mcp_session_id="sess-abc",
    )
    defaults.update(overrides)
    return ToolInvocation(**defaults)


@pytest.fixture()
def blob_repo(tmp_path):
    storage = LocalBlobStorage(tmp_path)
    return BlobToolInvocationRepository(storage), storage


class TestAppendDualWritesToBronze:
    def test_append_writes_a_bronze_blob(self, blob_repo):
        repo, storage = blob_repo
        repo.append(_make_invocation())

        blobs = storage.listar_blobs("observability/bronze/tool_invocations/")
        assert len(blobs) == 1

    def test_bronze_blob_contains_invocation_fields(self, blob_repo):
        repo, storage = blob_repo
        repo.append(_make_invocation(tool_name="criar_projeto", user_id="u2"))

        blobs = storage.listar_blobs("observability/bronze/tool_invocations/")
        raw = storage.ler_blob(blobs[0])
        record = json.loads(raw.decode("utf-8").strip())
        assert record["tool_name"] == "criar_projeto"
        assert record["user_id"] == "u2"
        assert record["id"] == "id-1"

    def test_each_append_creates_a_new_bronze_blob(self, blob_repo):
        """Bronze é append-only por batch — sem read-modify-write como o audit.jsonl."""
        repo, storage = blob_repo
        repo.append(_make_invocation(id="id-1"))
        repo.append(_make_invocation(id="id-2"))

        blobs = storage.listar_blobs("observability/bronze/tool_invocations/")
        assert len(blobs) == 2

    def test_audit_log_still_written_normally(self, blob_repo):
        """Dual-write não deve alterar o comportamento do audit.jsonl principal."""
        repo, storage = blob_repo
        repo.append(_make_invocation())

        assert repo.count() == 1
        assert repo.list_recent(limit=10)[0].id == "id-1"

    def test_bronze_write_failure_does_not_break_audit_append(self, blob_repo, monkeypatch):
        """Bronze é best-effort — uma falha ali nunca pode quebrar o audit log principal."""
        repo, storage = blob_repo
        monkeypatch.setattr(
            repo._bronze_writer,
            "write_batch",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("bronze indisponível")),
        )

        repo.append(_make_invocation())  # não deve lançar

        assert repo.count() == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
