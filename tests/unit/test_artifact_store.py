"""Tests for FileSystemArtifactStore (ADR-018).

Coverage target: from 29.2% toward 80%+ of artifact_store.py
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import BaseModel

from concilium.domain.models.artifact import (
    ArtifactEnvelope,
    ArtifactKind,
    ArtifactMeta,
    ArtifactRef,
    ArtifactState,
)
from concilium.infrastructure.storage.artifact_store import (
    ArtifactStore,
    FileSystemArtifactStore,
)

# ---------------------------------------------------------------------------
# Stub payload model
# ---------------------------------------------------------------------------


class StubPayload(BaseModel):
    value: str = "hello"
    count: int = 42


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_meta(
    artifact_id: str = "test-artifact-001",
    kind: ArtifactKind = ArtifactKind.RESULTADO,
    trace_id: str | None = "trace-abc",
    schema_name: str = "StubPayload",
    schema_version: str = "1.0",
    version: str = "1.0.0",
) -> ArtifactMeta:
    payload = StubPayload()
    content_hash = sha256(payload.model_dump_json().encode()).hexdigest()
    return ArtifactMeta(
        artifact_id=artifact_id,
        kind=kind,
        schema_name=schema_name,
        schema_version=schema_version,
        created_by="test-skill",
        trace_id=trace_id,
        content_hash=content_hash,
        version=version,
        state=ArtifactState.DRAFT,
    )


def _make_envelope(
    artifact_id: str = "test-artifact-001",
    kind: ArtifactKind = ArtifactKind.RESULTADO,
    trace_id: str | None = "trace-abc",
) -> ArtifactEnvelope[StubPayload]:
    payload = StubPayload()
    meta = _make_meta(artifact_id=artifact_id, kind=kind, trace_id=trace_id)
    return ArtifactEnvelope(meta=meta, payload=payload)


def _make_ref(meta: ArtifactMeta) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=meta.artifact_id,
        version=meta.version,
        kind=meta.kind,
        schema_name=meta.schema_name,
        schema_version=meta.schema_version,
        content_hash=meta.content_hash,
    )


# ---------------------------------------------------------------------------
# Base interface: ArtifactStore raises NotImplementedError
# ---------------------------------------------------------------------------


class TestArtifactStoreInterface:
    def test_save_raises(self):
        store = ArtifactStore()
        envelope = _make_envelope()
        with pytest.raises(NotImplementedError):
            store.save(envelope)

    def test_get_raises(self):
        store = ArtifactStore()
        ref = _make_ref(_make_meta())
        with pytest.raises(NotImplementedError):
            store.get(ref)

    def test_list_by_trace_raises(self):
        store = ArtifactStore()
        with pytest.raises(NotImplementedError):
            store.list_by_trace("some-trace")

    def test_list_by_kind_raises(self):
        store = ArtifactStore()
        with pytest.raises(NotImplementedError):
            store.list_by_kind(ArtifactKind.RESULTADO)


# ---------------------------------------------------------------------------
# FileSystemArtifactStore.__init__
# ---------------------------------------------------------------------------


class TestFileSystemArtifactStoreInit:
    def test_creates_root_directory(self, tmp_path: Path):
        root = tmp_path / "new_dir" / "nested"
        assert not root.exists()
        FileSystemArtifactStore(root)
        assert root.exists()
        assert root.is_dir()

    def test_accepts_string_path(self, tmp_path: Path):
        root = tmp_path / "str_root"
        store = FileSystemArtifactStore(str(root))
        assert isinstance(store.root, Path)
        assert store.root.exists()

    def test_existing_directory_does_not_raise(self, tmp_path: Path):
        # Should not raise even if root already exists
        store = FileSystemArtifactStore(tmp_path)
        assert store.root == tmp_path


# ---------------------------------------------------------------------------
# FileSystemArtifactStore.save
# ---------------------------------------------------------------------------


class TestFileSystemArtifactStoreSave:
    def test_save_writes_payload_json(self, tmp_path: Path):
        store = FileSystemArtifactStore(tmp_path)
        envelope = _make_envelope(artifact_id="art-001")
        store.save(envelope)

        payload_path = tmp_path / "art-001.json"
        assert payload_path.exists()
        data = json.loads(payload_path.read_text())
        assert data["value"] == "hello"
        assert data["count"] == 42

    def test_save_writes_meta_sidecar(self, tmp_path: Path):
        store = FileSystemArtifactStore(tmp_path)
        envelope = _make_envelope(artifact_id="art-002")
        store.save(envelope)

        sidecar_path = tmp_path / "art-002.meta.json"
        assert sidecar_path.exists()
        meta_data = json.loads(sidecar_path.read_text())
        assert meta_data["artifact_id"] == "art-002"
        assert meta_data["kind"] == ArtifactKind.RESULTADO.value

    def test_save_appends_to_index(self, tmp_path: Path):
        store = FileSystemArtifactStore(tmp_path)
        envelope = _make_envelope(artifact_id="art-003", trace_id="trace-xyz")
        store.save(envelope)

        index_path = tmp_path / ".artifact_index.jsonl"
        assert index_path.exists()
        lines = [ln for ln in index_path.read_text().splitlines() if ln.strip()]
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["artifact_id"] == "art-003"
        assert entry["trace_id"] == "trace-xyz"
        assert entry["kind"] == ArtifactKind.RESULTADO.value

    def test_save_multiple_appends_all_to_index(self, tmp_path: Path):
        store = FileSystemArtifactStore(tmp_path)
        for i in range(3):
            envelope = _make_envelope(artifact_id=f"art-{i:03d}")
            store.save(envelope)

        index_path = tmp_path / ".artifact_index.jsonl"
        lines = [ln for ln in index_path.read_text().splitlines() if ln.strip()]
        assert len(lines) == 3

    def test_save_pydantic_payload_uses_model_dump_json(self, tmp_path: Path):
        """Payload com model_dump_json (Pydantic model) usa esse método para serializar."""
        store = FileSystemArtifactStore(tmp_path)
        # StubPayload has model_dump_json; verify the resulting JSON is valid
        envelope = _make_envelope(artifact_id="art-pydantic")
        store.save(envelope)

        payload_path = tmp_path / "art-pydantic.json"
        assert payload_path.exists()
        data = json.loads(payload_path.read_text())
        assert data["value"] == "hello"
        assert data["count"] == 42

    def test_index_entry_has_ref_subobject(self, tmp_path: Path):
        store = FileSystemArtifactStore(tmp_path)
        envelope = _make_envelope(artifact_id="art-ref")
        store.save(envelope)

        index_path = tmp_path / ".artifact_index.jsonl"
        lines = [ln for ln in index_path.read_text().splitlines() if ln.strip()]
        entry = json.loads(lines[0])
        assert "ref" in entry
        ref = entry["ref"]
        assert ref["artifact_id"] == "art-ref"
        assert "content_hash" in ref
        assert "version" in ref


# ---------------------------------------------------------------------------
# FileSystemArtifactStore.save_meta_sidecar
# ---------------------------------------------------------------------------


class TestSaveMetaSidecar:
    def test_sidecar_written_without_payload(self, tmp_path: Path):
        store = FileSystemArtifactStore(tmp_path)
        meta = _make_meta(artifact_id="sidecar-only")

        # create a fake payload path (does not need to exist for sidecar)
        payload_path = tmp_path / "sidecar-only.json"
        store.save_meta_sidecar(payload_path, meta)

        sidecar_path = tmp_path / "sidecar-only.meta.json"
        assert sidecar_path.exists()

        # payload file NOT written by save_meta_sidecar
        assert not payload_path.exists()

    def test_sidecar_content_matches_meta(self, tmp_path: Path):
        store = FileSystemArtifactStore(tmp_path)
        meta = _make_meta(artifact_id="sidecar-check", trace_id="trace-sidecar")
        payload_path = tmp_path / "sidecar-check.json"
        store.save_meta_sidecar(payload_path, meta)

        sidecar_path = tmp_path / "sidecar-check.meta.json"
        meta_data = json.loads(sidecar_path.read_text())
        assert meta_data["artifact_id"] == "sidecar-check"
        assert meta_data["trace_id"] == "trace-sidecar"

    def test_sidecar_appends_to_index(self, tmp_path: Path):
        store = FileSystemArtifactStore(tmp_path)
        meta = _make_meta(artifact_id="sidecar-idx")
        payload_path = tmp_path / "sidecar-idx.json"
        store.save_meta_sidecar(payload_path, meta)

        index_path = tmp_path / ".artifact_index.jsonl"
        assert index_path.exists()
        lines = [ln for ln in index_path.read_text().splitlines() if ln.strip()]
        assert len(lines) == 1


# ---------------------------------------------------------------------------
# FileSystemArtifactStore.get
# ---------------------------------------------------------------------------


class TestFileSystemArtifactStoreGet:
    def test_get_returns_populated_envelope(self, tmp_path: Path):
        store = FileSystemArtifactStore(tmp_path)
        envelope = _make_envelope(artifact_id="get-art-001")
        store.save(envelope)

        ref = _make_ref(envelope.meta)

        # Patch ConciliumArtifactRegistry.validate to return a StubPayload
        with patch(
            "concilium.domain.models.artifact.ConciliumArtifactRegistry.validate",
            return_value=StubPayload(value="hello", count=42),
        ):
            result = store.get(ref)

        assert isinstance(result, ArtifactEnvelope)
        assert result.meta.artifact_id == "get-art-001"
        assert isinstance(result.payload, StubPayload)
        assert result.payload.value == "hello"

    def test_get_raises_file_not_found_for_unknown_id(self, tmp_path: Path):
        store = FileSystemArtifactStore(tmp_path)
        ref = _make_ref(_make_meta(artifact_id="nonexistent-id"))

        with pytest.raises(FileNotFoundError, match="nonexistent-id"):
            store.get(ref)

    def test_get_reads_back_meta_correctly(self, tmp_path: Path):
        store = FileSystemArtifactStore(tmp_path)
        envelope = _make_envelope(artifact_id="get-meta-check", trace_id="trace-get")
        store.save(envelope)

        ref = _make_ref(envelope.meta)

        with patch(
            "concilium.domain.models.artifact.ConciliumArtifactRegistry.validate",
            return_value=StubPayload(),
        ):
            result = store.get(ref)

        assert result.meta.trace_id == "trace-get"
        assert result.meta.kind == ArtifactKind.RESULTADO


# ---------------------------------------------------------------------------
# FileSystemArtifactStore.list_by_trace
# ---------------------------------------------------------------------------


class TestListByTrace:
    def test_returns_matching_trace_refs(self, tmp_path: Path):
        store = FileSystemArtifactStore(tmp_path)
        e1 = _make_envelope(artifact_id="t1", trace_id="trace-A")
        e2 = _make_envelope(artifact_id="t2", trace_id="trace-A")
        e3 = _make_envelope(artifact_id="t3", trace_id="trace-B")
        store.save(e1)
        store.save(e2)
        store.save(e3)

        refs = store.list_by_trace("trace-A")
        ids = {r.artifact_id for r in refs}
        assert ids == {"t1", "t2"}

    def test_returns_empty_for_nonexistent_trace(self, tmp_path: Path):
        store = FileSystemArtifactStore(tmp_path)
        e1 = _make_envelope(artifact_id="t1", trace_id="trace-A")
        store.save(e1)

        refs = store.list_by_trace("trace-UNKNOWN")
        assert refs == []

    def test_returns_empty_when_index_absent(self, tmp_path: Path):
        store = FileSystemArtifactStore(tmp_path)
        refs = store.list_by_trace("trace-X")
        assert refs == []

    def test_returns_artifact_refs(self, tmp_path: Path):
        store = FileSystemArtifactStore(tmp_path)
        e1 = _make_envelope(artifact_id="ref-check", trace_id="trace-ref")
        store.save(e1)

        refs = store.list_by_trace("trace-ref")
        assert len(refs) == 1
        assert isinstance(refs[0], ArtifactRef)
        assert refs[0].artifact_id == "ref-check"


# ---------------------------------------------------------------------------
# FileSystemArtifactStore.list_by_kind
# ---------------------------------------------------------------------------


class TestListByKind:
    def test_returns_matching_kind_refs(self, tmp_path: Path):
        store = FileSystemArtifactStore(tmp_path)
        e1 = _make_envelope(artifact_id="k1", kind=ArtifactKind.RESULTADO)
        e2 = _make_envelope(artifact_id="k2", kind=ArtifactKind.RESULTADO)
        e3 = _make_envelope(artifact_id="k3", kind=ArtifactKind.RELATORIO)
        # Rebuild e3 with a different kind
        meta3 = _make_meta(artifact_id="k3", kind=ArtifactKind.RELATORIO)
        e3 = ArtifactEnvelope(meta=meta3, payload=StubPayload())

        store.save(e1)
        store.save(e2)
        store.save(e3)

        refs = store.list_by_kind(ArtifactKind.RESULTADO)
        ids = {r.artifact_id for r in refs}
        assert ids == {"k1", "k2"}

    def test_returns_empty_for_absent_kind(self, tmp_path: Path):
        store = FileSystemArtifactStore(tmp_path)
        e1 = _make_envelope(artifact_id="k1", kind=ArtifactKind.RESULTADO)
        store.save(e1)

        refs = store.list_by_kind(ArtifactKind.CANONICAL)
        assert refs == []

    def test_returns_empty_when_index_absent(self, tmp_path: Path):
        store = FileSystemArtifactStore(tmp_path)
        refs = store.list_by_kind(ArtifactKind.DECISAO)
        assert refs == []

    def test_returns_artifact_refs(self, tmp_path: Path):
        store = FileSystemArtifactStore(tmp_path)
        e1 = _make_envelope(artifact_id="kind-ref", kind=ArtifactKind.RESULTADO)
        store.save(e1)

        refs = store.list_by_kind(ArtifactKind.RESULTADO)
        assert len(refs) == 1
        assert isinstance(refs[0], ArtifactRef)


# ---------------------------------------------------------------------------
# Malformed JSONL lines are silently skipped
# ---------------------------------------------------------------------------


class TestMalformedIndexLines:
    def test_malformed_lines_skipped_in_list_by_trace(self, tmp_path: Path):
        store = FileSystemArtifactStore(tmp_path)
        # Write some valid entries first
        e1 = _make_envelope(artifact_id="valid-001", trace_id="trace-ok")
        store.save(e1)

        # Inject malformed lines into the index
        index_path = tmp_path / ".artifact_index.jsonl"
        with index_path.open("a", encoding="utf-8") as f:
            f.write("THIS IS NOT JSON\n")
            f.write('{"incomplete": true\n')  # truncated JSON
            f.write("\n")  # blank line

        # Should return only the valid entry, not raise
        refs = store.list_by_trace("trace-ok")
        assert len(refs) == 1
        assert refs[0].artifact_id == "valid-001"

    def test_malformed_lines_skipped_in_list_by_kind(self, tmp_path: Path):
        store = FileSystemArtifactStore(tmp_path)
        e1 = _make_envelope(artifact_id="valid-kind-001", kind=ArtifactKind.RESULTADO)
        store.save(e1)

        index_path = tmp_path / ".artifact_index.jsonl"
        with index_path.open("a", encoding="utf-8") as f:
            f.write("BAD JSON LINE\n")
            f.write('{"no_kind_field": 1}\n')  # valid JSON but missing ref
            f.write("\n")

        refs = store.list_by_kind(ArtifactKind.RESULTADO)
        assert len(refs) == 1
        assert refs[0].artifact_id == "valid-kind-001"

    def test_entry_without_ref_field_skipped(self, tmp_path: Path):
        """An entry with correct trace_id but missing 'ref' key should be skipped."""
        store = FileSystemArtifactStore(tmp_path)
        index_path = tmp_path / ".artifact_index.jsonl"
        # Write an entry without "ref" key
        bad_entry = json.dumps({"trace_id": "trace-z", "artifact_id": "no-ref"})
        with index_path.open("w", encoding="utf-8") as f:
            f.write(bad_entry + "\n")

        # Should skip the entry (KeyError on entry["ref"] → caught by except Exception)
        refs = store.list_by_trace("trace-z")
        assert refs == []
