"""Pytest tests for StorageProjectHandle and StorageProjectRepository.

Uses an in-memory BlobStoragePort stub — no filesystem or cloud dependency.
"""

from __future__ import annotations

import json

import pytest

from concilium.domain.repositories.blob_storage_port import BlobStoragePort
from concilium.infrastructure.storage.storage_project_repository import (
    StorageProjectHandle,
    StorageProjectRepository,
)
from tests.support.fake_blob_storage import FakeBlobStorage as MemoryBlobStorage

# ─────────────────────────────────────────────────────────────────────────────
#  In-memory stub for BlobStoragePort — ver tests/support/fake_blob_storage.py
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def storage() -> MemoryBlobStorage:
    return MemoryBlobStorage()


@pytest.fixture
def project_id() -> str:
    return "proj-abc123"


@pytest.fixture
def handle(storage: MemoryBlobStorage, project_id: str) -> StorageProjectHandle:
    return StorageProjectHandle(storage, project_id)


@pytest.fixture
def repo(storage: MemoryBlobStorage) -> StorageProjectRepository:
    return StorageProjectRepository(storage, projects_prefix="projetos")


# ─────────────────────────────────────────────────────────────────────────────
#  StorageProjectHandle — _path resolution
# ─────────────────────────────────────────────────────────────────────────────


class TestPathResolution:
    def test_path_prefixes_project_id(self, handle: StorageProjectHandle, project_id: str) -> None:
        result = handle._path("meta.json")
        assert result == f"{project_id}/meta.json"

    def test_path_strips_leading_slash(self, handle: StorageProjectHandle, project_id: str) -> None:
        result = handle._path("/some/file.json")
        assert result == f"{project_id}/some/file.json"

    def test_root_property(self, handle: StorageProjectHandle, project_id: str) -> None:
        from pathlib import Path

        assert handle.root == Path(project_id)


# ─────────────────────────────────────────────────────────────────────────────
#  StorageProjectHandle — meta read/write round-trip
# ─────────────────────────────────────────────────────────────────────────────


class TestMetaReadWrite:
    def test_meta_returns_empty_dict_when_missing(self, handle: StorageProjectHandle) -> None:
        assert handle.meta == {}

    def test_write_json_then_read_json_round_trip(self, handle: StorageProjectHandle) -> None:
        payload = {"key": "value", "num": 42}
        handle.write_json("meta.json", payload)
        assert handle.read_json("meta.json", {}) == payload

    def test_update_meta_merges_changes(self, handle: StorageProjectHandle) -> None:
        handle.write_json("meta.json", {"existing": "yes"})
        handle.update_meta(nome="TestProject", current_version="v1")
        meta = handle.meta
        assert meta["existing"] == "yes"
        assert meta["nome"] == "TestProject"
        assert meta["current_version"] == "v1"

    def test_read_json_returns_default_on_missing(self, handle: StorageProjectHandle) -> None:
        result = handle.read_json("nonexistent.json", {"default": True})
        assert result == {"default": True}

    def test_read_json_returns_default_on_invalid_json(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        storage.gravar_blob(f"{project_id}/bad.json", b"not-json-at-all!!!")
        result = handle.read_json("bad.json", "fallback")
        assert result == "fallback"


# ─────────────────────────────────────────────────────────────────────────────
#  StorageProjectHandle — list_versions
# ─────────────────────────────────────────────────────────────────────────────


class TestListVersions:
    def test_empty_when_no_blobs(self, handle: StorageProjectHandle) -> None:
        assert handle.list_versions() == []

    def test_only_vN_prefixed_paths_are_counted(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        # Add vN-prefixed blobs
        storage.gravar_blob(f"{project_id}/v1/invocations.log", b"")
        storage.gravar_blob(f"{project_id}/v2/canonical.json", b"{}")
        storage.gravar_blob(f"{project_id}/v2/invocations.log", b"")
        # Non-vN blobs must not be counted
        storage.gravar_blob(f"{project_id}/meta.json", b"{}")
        storage.gravar_blob(f"{project_id}/overrides/cpus.json", b"{}")
        storage.gravar_blob(f"{project_id}/version_notes.txt", b"")  # starts with "v" but no digit

        versions = handle.list_versions()
        assert versions == ["v1", "v2"]

    def test_sorted_numerically(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        for v in ["v10", "v3", "v1"]:
            storage.gravar_blob(f"{project_id}/{v}/invocations.log", b"")
        versions = handle.list_versions()
        assert versions == ["v1", "v3", "v10"]

    def test_non_digit_after_v_not_counted(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        storage.gravar_blob(f"{project_id}/vabc/file.json", b"")
        storage.gravar_blob(f"{project_id}/v1/file.json", b"")
        versions = handle.list_versions()
        assert "vabc" not in versions
        assert "v1" in versions


# ─────────────────────────────────────────────────────────────────────────────
#  StorageProjectHandle — new_version
# ─────────────────────────────────────────────────────────────────────────────


class TestNewVersion:
    def test_first_version_is_v1(self, handle: StorageProjectHandle) -> None:
        v = handle.new_version()
        assert v == "v1"

    def test_increments_correctly(self, handle: StorageProjectHandle) -> None:
        handle.new_version()
        v2 = handle.new_version()
        assert v2 == "v2"

    def test_updates_current_version_in_meta(self, handle: StorageProjectHandle) -> None:
        handle.new_version()
        assert handle.current_version() == "v1"
        handle.new_version()
        assert handle.current_version() == "v2"

    def test_copy_on_write_from_current_version(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        # Set up v1 with a canonical
        handle.new_version()
        canon_data = b'{"meta": {"versao_schema": "1.0"}}'
        storage.gravar_blob(f"{project_id}/v1/canonical.json", canon_data)
        handle.update_meta(current_version="v1")

        # Create v2 — should copy canonical from v1
        handle.new_version()
        copied = storage.ler_blob(f"{project_id}/v2/canonical.json")
        assert copied == canon_data

    def test_copy_on_write_from_explicit_base(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        handle.new_version()  # v1
        handle.new_version()  # v2
        canon_data = b'{"from": "v1"}'
        storage.gravar_blob(f"{project_id}/v1/canonical.json", canon_data)

        handle.new_version(base="v1")  # v3, copy from v1
        copied = storage.ler_blob(f"{project_id}/v3/canonical.json")
        assert copied == canon_data

    def test_no_error_when_base_canonical_missing(self, handle: StorageProjectHandle) -> None:
        # v1 exists but has no canonical — no FileNotFoundError should propagate
        handle.new_version()
        v2 = handle.new_version()  # tries to copy from v1 (no canonical exists)
        assert v2 == "v2"

    def test_invocations_log_created(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        handle.new_version()
        assert storage.blob_existe(f"{project_id}/v1/invocations.log")

    def test_accepts_adr119_audit_kwargs_without_raising(self, handle: StorageProjectHandle) -> None:
        # ADR-119 D2: pipeline_service.py chama new_version com estes kwargs em
        # projetos backed por storage (SharePoint/S3/Azure/GDrive) — regressão
        # para o TypeError que ocorria quando a assinatura não os aceitava.
        v = handle.new_version(
            criado_por="user-1",
            role_criador="engenheiro_senior",
            procurement_intent="rfi",
            forked_from="v0",
            motivo="teste",
        )
        assert v == "v1"

    def test_audit_kwargs_persisted_in_version_history(self, handle: StorageProjectHandle) -> None:
        handle.new_version(
            criado_por="user-1",
            role_criador="engenheiro_senior",
            procurement_intent="rfp",
            motivo="revisão",
        )
        entry = handle.meta["version_history"]["v1"]
        assert entry["criado_por"] == "user-1"
        assert entry["role_criador"] == "engenheiro_senior"
        assert entry["procurement_intent"] == "rfp"
        assert entry["motivo"] == "revisão"

    def test_forked_from_defaults_to_source_when_omitted(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        handle.new_version()  # v1
        handle.update_meta(current_version="v1")
        handle.new_version()  # v2, source=v1
        entry = handle.meta["version_history"]["v2"]
        assert entry["forked_from"] == "v1"

    def test_recovers_when_version_history_is_corrupted(self, handle: StorageProjectHandle) -> None:
        # meta.json corrompido/fora do schema (ex.: migração antiga) não deve
        # quebrar new_version com TypeError.
        handle.update_meta(version_history="not-a-dict")
        v = handle.new_version(criado_por="user-1")
        assert v == "v1"
        assert handle.meta["version_history"]["v1"]["criado_por"] == "user-1"


class TestGetVersionMeta:
    def test_returns_empty_dict_for_unknown_version(self, handle: StorageProjectHandle) -> None:
        assert handle.get_version_meta("v99") == {}

    def test_returns_audit_metadata_for_known_version(self, handle: StorageProjectHandle) -> None:
        handle.new_version(criado_por="user-2", procurement_intent="rfi")
        meta = handle.get_version_meta("v1")
        assert meta["criado_por"] == "user-2"
        assert meta["procurement_intent"] == "rfi"

    def test_returns_empty_dict_when_version_history_is_corrupted(self, handle: StorageProjectHandle) -> None:
        handle.update_meta(version_history=["not", "a", "dict"])
        assert handle.get_version_meta("v1") == {}


# ─────────────────────────────────────────────────────────────────────────────
#  StorageProjectHandle — version_path
# ─────────────────────────────────────────────────────────────────────────────


class TestVersionPath:
    def test_version_path_returns_path_object(self, handle: StorageProjectHandle, project_id: str) -> None:
        from pathlib import Path

        p = handle.version_path("v1")
        assert p == Path(project_id) / "v1"


# ─────────────────────────────────────────────────────────────────────────────
#  StorageProjectHandle — load_canonical / save_canonical
# ─────────────────────────────────────────────────────────────────────────────


def _minimal_canonical_dict() -> dict:
    """Return a minimal valid CanonicalModel-like dict (only what the model requires)."""
    from datetime import date, datetime

    return {
        "meta": {
            "versao_schema": "1.0.0",
            "gerado_em": datetime.now().isoformat(),
            "contexto_id": "ctx-test",
        },
        "projeto": {
            "id": "00000000-0000-0000-0000-000000000001",
            "nome": "Projeto Teste",
            "tipo_obra": "terraplenagem",
            "localizacao": "Brasil",
            "coordenadas": {"lat": -10.0, "lng": -50.0},
            "regime_trabalho": {"dias_semana": 6, "horas_dia": 8},
            "data_inicio": str(date.today()),
            "data_termino": str(date.today()),
            "snapshot_catalogo_id": "snap-001",
            "snapshot_perfil_id": "perfil-001",
        },
        "eap": [],
    }


class TestLoadSaveCanonical:
    def test_load_canonical_returns_none_when_no_version(self, handle: StorageProjectHandle) -> None:
        result = handle.load_canonical()
        assert result is None

    def test_load_canonical_returns_none_on_missing_blob(self, handle: StorageProjectHandle) -> None:
        handle.update_meta(current_version="v1")
        result = handle.load_canonical()
        assert result is None

    def test_load_canonical_explicit_version_missing(self, handle: StorageProjectHandle) -> None:
        result = handle.load_canonical(version="v99")
        assert result is None

    def test_save_canonical_raises_without_active_version(self, handle: StorageProjectHandle) -> None:
        from concilium.domain.models.canonical import CanonicalModel

        try:
            model = CanonicalModel.model_validate(_minimal_canonical_dict())
            with pytest.raises(RuntimeError, match="Nenhuma versão ativa"):
                handle.save_canonical(model)
        except Exception:
            # If CanonicalModel.model_validate fails (missing required fields),
            # test the runtime error with a mock
            from unittest.mock import MagicMock

            mock_model = MagicMock()
            mock_model.model_dump_json.return_value = "{}"
            with pytest.raises(RuntimeError, match="Nenhuma versão ativa"):
                handle.save_canonical(mock_model)

    def test_save_canonical_writes_artifact_meta_sidecar(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        """ADR-018 §D2: paridade com FileProjectHandle — sidecar de proveniência
        deve ser escrito também no backend de storage (issue #47)."""
        from concilium.domain.models.canonical import CanonicalModel

        handle.new_version()
        handle.update_meta(current_version="v1")
        model = CanonicalModel.model_validate(_minimal_canonical_dict())

        handle.save_canonical(model, trace_id="trace-abc", created_by="skill-04")

        sidecar = handle.read_json("v1/canonical.meta.json", None)
        assert sidecar is not None
        assert sidecar["created_by"] == "skill-04"
        assert sidecar["trace_id"] == "trace-abc"
        assert sidecar["kind"] == "canonical"
        assert sidecar["content_hash"]

    def test_save_canonical_sidecar_write_json_failure_is_swallowed(
        self, handle: StorageProjectHandle, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from concilium.domain.models.canonical import CanonicalModel

        handle.new_version()
        handle.update_meta(current_version="v1")
        model = CanonicalModel.model_validate(_minimal_canonical_dict())

        original_write_json = handle.write_json

        def _flaky_write_json(relative_path, payload):
            if relative_path.endswith("canonical.meta.json"):
                raise RuntimeError("storage unavailable")
            return original_write_json(relative_path, payload)

        monkeypatch.setattr(handle, "write_json", _flaky_write_json)
        # Não deve levantar — falha no sidecar é best-effort.
        handle.save_canonical(model)
        assert handle.load_canonical() is not None


# ─────────────────────────────────────────────────────────────────────────────
#  StorageProjectHandle — append_jsonl
# ─────────────────────────────────────────────────────────────────────────────


class TestAppendJsonl:
    def test_append_creates_file_when_missing(self, handle: StorageProjectHandle) -> None:
        handle.append_jsonl("audit.jsonl", {"event": "test"})
        lines = handle.read_lines("audit.jsonl")
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["event"] == "test"

    def test_append_multiple_entries(self, handle: StorageProjectHandle) -> None:
        handle.append_jsonl("log.jsonl", {"n": 1})
        handle.append_jsonl("log.jsonl", {"n": 2})
        handle.append_jsonl("log.jsonl", {"n": 3})
        lines = handle.read_lines("log.jsonl")
        assert len(lines) == 3
        assert json.loads(lines[2])["n"] == 3

    def test_append_produces_newline_delimited_json(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        handle.append_jsonl("out.jsonl", {"a": 1})
        handle.append_jsonl("out.jsonl", {"b": 2})
        raw = storage.ler_blob(f"{project_id}/out.jsonl").decode("utf-8")
        # Each line must be valid JSON
        for line in raw.strip().split("\n"):
            json.loads(line)


# ─────────────────────────────────────────────────────────────────────────────
#  StorageProjectHandle — write_lines
# ─────────────────────────────────────────────────────────────────────────────


class TestWriteLines:
    """write_lines rewrites the blob wholesale (unlike append_jsonl) — used for
    LGPD Art. 18 anonymization sweeps over an otherwise append-only .jsonl."""

    def test_write_lines_joins_with_newline_and_trailing_newline(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        handle.write_lines("audit.jsonl", ["line1", "line2", "line3"])
        raw = storage.ler_blob(f"{project_id}/audit.jsonl")
        assert raw == b"line1\nline2\nline3\n"

    def test_write_lines_empty_list_writes_empty_content(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        handle.write_lines("audit.jsonl", [])
        raw = storage.ler_blob(f"{project_id}/audit.jsonl")
        assert raw == b""

    def test_write_lines_fully_overwrites_previous_content(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        """Diferente de append_jsonl: reescreve o blob por completo — é assim que
        uma varredura de anonimização (LGPD Art. 18) substitui as linhas com
        `user_id` zerado sem deixar o conteúdo antigo remanescente."""
        handle.append_jsonl("audit.jsonl", {"user_id": "carla"})
        handle.append_jsonl("audit.jsonl", {"user_id": "outro"})

        handle.write_lines("audit.jsonl", ['{"user_id": null}', '{"user_id": "outro"}'])

        lines = handle.read_lines("audit.jsonl")
        assert lines == ['{"user_id": null}', '{"user_id": "outro"}']


# ─────────────────────────────────────────────────────────────────────────────
#  StorageProjectHandle — read_lines, read_bytes, exists
# ─────────────────────────────────────────────────────────────────────────────


class TestReadLinesReadBytesExists:
    def test_read_lines_returns_empty_list_on_missing(self, handle: StorageProjectHandle) -> None:
        assert handle.read_lines("nonexistent.log") == []

    def test_read_lines_splits_on_newlines(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        storage.gravar_blob(f"{project_id}/file.log", b"line1\nline2\nline3")
        lines = handle.read_lines("file.log")
        assert lines == ["line1", "line2", "line3"]

    def test_read_bytes_returns_none_on_missing(self, handle: StorageProjectHandle) -> None:
        assert handle.read_bytes("nonexistent.bin") is None

    def test_read_bytes_returns_content(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        storage.gravar_blob(f"{project_id}/data.bin", b"\x00\x01\x02")
        result = handle.read_bytes("data.bin")
        assert result == b"\x00\x01\x02"

    def test_exists_returns_false_when_missing(self, handle: StorageProjectHandle) -> None:
        assert handle.exists("no_such.json") is False

    def test_exists_returns_true_when_present(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        storage.gravar_blob(f"{project_id}/present.json", b"{}")
        assert handle.exists("present.json") is True


# ─────────────────────────────────────────────────────────────────────────────
#  StorageProjectHandle — list_file_names
# ─────────────────────────────────────────────────────────────────────────────


class TestListFileNames:
    def test_returns_empty_when_no_blobs(self, handle: StorageProjectHandle) -> None:
        assert handle.list_file_names("v1") == []

    def test_strips_prefix_and_returns_filename(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        storage.gravar_blob(f"{project_id}/v1/file_a.json", b"")
        storage.gravar_blob(f"{project_id}/v1/file_b.json", b"")
        names = handle.list_file_names("v1")
        assert sorted(names) == ["file_a.json", "file_b.json"]

    def test_excludes_subdirectory_entries(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        storage.gravar_blob(f"{project_id}/v1/top.json", b"")
        storage.gravar_blob(f"{project_id}/v1/subdir/nested.json", b"")
        names = handle.list_file_names("v1")
        # Only top-level file — nested.json inside subdir must not appear
        assert "top.json" in names
        assert "nested.json" not in names
        assert all("/" not in n for n in names)

    def test_returns_sorted(self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str) -> None:
        for name in ["c.json", "a.json", "b.json"]:
            storage.gravar_blob(f"{project_id}/v1/{name}", b"")
        names = handle.list_file_names("v1")
        assert names == sorted(names)


# ─────────────────────────────────────────────────────────────────────────────
#  StorageProjectHandle — list_output_files / load_output_file / save_output_file
# ─────────────────────────────────────────────────────────────────────────────


class TestOutputFiles:
    def test_list_output_files_empty_when_no_version(self, handle: StorageProjectHandle) -> None:
        assert handle.list_output_files() == []

    def test_save_output_file_routes_xlsx_to_reports(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        handle.update_meta(current_version="v1")
        result_path = handle.save_output_file(b"xlsx-data", filename="output.xlsx")
        assert "reports" in str(result_path)
        assert storage.blob_existe(f"{project_id}/v1/outputs/reports/output.xlsx")

    def test_save_output_file_routes_png_to_visualizations(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        handle.update_meta(current_version="v1")
        handle.save_output_file(b"png-data", filename="chart.png")
        assert storage.blob_existe(f"{project_id}/v1/outputs/visualizations/chart.png")

    def test_save_output_file_raises_without_version(self, handle: StorageProjectHandle) -> None:
        with pytest.raises(RuntimeError, match="Nenhuma versão ativa"):
            handle.save_output_file(b"data", filename="output.xlsx")

    def test_load_output_file_returns_data(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        handle.update_meta(current_version="v1")
        storage.gravar_blob(f"{project_id}/v1/outputs/reports/resultado.xlsx", b"abc")
        data = handle.load_output_file(filename="resultado.xlsx")
        assert data == b"abc"

    def test_load_output_file_fallback_to_other_subdir(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        handle.update_meta(current_version="v1")
        # Store a .xlsx in visualizations (wrong place) — fallback should find it
        storage.gravar_blob(f"{project_id}/v1/outputs/visualizations/report.xlsx", b"xlsx-data")
        data = handle.load_output_file(filename="report.xlsx")
        assert data == b"xlsx-data"

    def test_load_output_file_returns_none_when_no_version(self, handle: StorageProjectHandle) -> None:
        assert handle.load_output_file() is None

    def test_list_output_files_with_blobs(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        handle.update_meta(current_version="v1")
        storage.gravar_blob(f"{project_id}/v1/outputs/reports/a.xlsx", b"")
        storage.gravar_blob(f"{project_id}/v1/outputs/visualizations/b.png", b"")
        files = handle.list_output_files()
        assert any("a.xlsx" in f for f in files)
        assert any("b.png" in f for f in files)

    def test_get_output_subdir_images(self) -> None:
        for ext in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"):
            assert StorageProjectHandle._get_output_subdir(f"file{ext}") == "visualizations"

    def test_get_output_subdir_docs_and_fallback(self) -> None:
        for ext in (".pdf", ".xlsx", ".xls", ".csv"):
            assert StorageProjectHandle._get_output_subdir(f"file{ext}") == "reports"
        # Unknown extension — fallback to reports
        assert StorageProjectHandle._get_output_subdir("file.unknown") == "reports"


# ─────────────────────────────────────────────────────────────────────────────
#  StorageProjectHandle — extend_cpu / resolve_cpu
# ─────────────────────────────────────────────────────────────────────────────


class TestExtendResolveCpu:
    def test_extend_cpu_writes_to_overrides(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        cpu_data = {"descricao": "Escavadeira", "custo": 1000.0}
        handle.extend_cpu("CPU-001", cpu_data, actor="tester", motivo="teste")
        overrides = handle.read_json("overrides/cpus_override.json", {})
        assert "CPU-001" in overrides
        assert overrides["CPU-001"]["descricao"] == "Escavadeira"

    def test_extend_cpu_appends_audit_entry(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        handle.extend_cpu("CPU-002", {"x": 1}, actor="user", motivo="motivo teste")
        lines = handle.read_lines("audit_log.jsonl")
        assert len(lines) >= 1
        entry = json.loads(lines[-1])
        assert entry["event"] == "extend_cpu"
        assert entry["cpu_id"] == "CPU-002"
        assert entry["actor"] == "user"
        assert entry["motivo"] == "motivo teste"

    def test_resolve_cpu_returns_data(self, handle: StorageProjectHandle) -> None:
        handle.extend_cpu("CPU-X", {"val": 42})
        result = handle.resolve_cpu("CPU-X")
        assert result is not None
        assert result["val"] == 42

    def test_resolve_cpu_returns_none_for_unknown(self, handle: StorageProjectHandle) -> None:
        result = handle.resolve_cpu("NONEXISTENT-CPU")
        assert result is None

    def test_extend_cpu_accumulates_multiple_cpus(self, handle: StorageProjectHandle) -> None:
        handle.extend_cpu("CPU-A", {"a": 1})
        handle.extend_cpu("CPU-B", {"b": 2})
        assert handle.resolve_cpu("CPU-A") == {"a": 1}
        assert handle.resolve_cpu("CPU-B") == {"b": 2}


# ─────────────────────────────────────────────────────────────────────────────
#  StorageProjectHandle — log_invocation / approve / snapshots / list_escopos / escopo
# ─────────────────────────────────────────────────────────────────────="────
# ─────────────────────────────────────────────────────────────────────────────


class TestMiscMethods:
    def test_log_invocation_appends_entry(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        handle.log_invocation("v1", {"skill": "04-cronograma", "status": "ok"})
        lines = handle.read_lines("v1/invocations.log")
        assert len(lines) == 1
        assert json.loads(lines[0])["skill"] == "04-cronograma"

    def test_approve_calls_aprovar_versao(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        handle.approve("v1")
        # MemoryBlobStorage records approved paths
        assert f"{project_id}/v1/canonical.json" in storage._approved

    def test_approve_transitions_status_even_when_aprovar_versao_fails(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage
    ) -> None:
        """aprovar_versao (chmod 444/checkin SharePoint) é defesa em profundidade —
        a fonte de verdade de somente-leitura é `approved_versions` no
        meta.json. Uma falha no checkin (ex.: quirk do Graph) não pode travar
        approve()."""
        storage.aprovar_versao = lambda path: (_ for _ in ()).throw(RuntimeError("400 Bad Request: checkin"))

        handle.approve("v1")  # não deve levantar

        assert "v1" in (handle.meta.get("approved_versions") or [])

    def test_snapshots_stores_and_dedupes(self, handle: StorageProjectHandle) -> None:
        snaps = handle.snapshots
        h1 = snaps.store("jurisdicao", {"a": 1})
        h2 = snaps.store("jurisdicao", {"a": 1})
        assert h1 == h2

    def test_list_escopos_returns_empty(self, handle: StorageProjectHandle) -> None:
        assert handle.list_escopos() == []

    def test_escopo_returns_handle(self, handle: StorageProjectHandle) -> None:
        es = handle.escopo("default")
        assert es.escopo_id == "default"


# ─────────────────────────────────────────────────────────────────────────────
#  StorageProjectHandle — create_escopo
# ─────────────────────────────────────────────────────────────────────────────


class TestCreateEscopo:
    def test_create_escopo_writes_meta_json(self, handle: StorageProjectHandle) -> None:
        result = handle.create_escopo(
            escopo_id="esc-001",
            nome="Escopo Principal",
            tipo_obra="terraplenagem",
            localizacao="Brasília",
            coordenadas_lat=-15.7801,
            coordenadas_lng=-47.9292,
            data_inicio="2026-01-01",
            data_termino="2026-12-31",
        )
        assert result.escopo_id == "esc-001"
        meta = handle.read_json("escopos/esc-001/meta.json", {})
        assert meta["nome"] == "Escopo Principal"
        assert meta["tipo_obra"] == "terraplenagem"
        assert meta["coordenadas_lat"] == -15.7801

    def test_create_escopo_updates_index(self, handle: StorageProjectHandle) -> None:
        handle.create_escopo(
            escopo_id="esc-A",
            nome="A",
            tipo_obra="pavimentacao",
            localizacao="SP",
            coordenadas_lat=-23.5,
            coordenadas_lng=-46.6,
            data_inicio="2026-01-01",
            data_termino="2026-06-30",
        )
        handle.create_escopo(
            escopo_id="esc-B",
            nome="B",
            tipo_obra="saneamento",
            localizacao="RJ",
            coordenadas_lat=-22.9,
            coordenadas_lng=-43.2,
            data_inicio="2026-01-01",
            data_termino="2026-06-30",
        )
        idx = handle.read_json("escopos/_index.json", {"escopo_ids": []})
        assert "esc-A" in idx["escopo_ids"]
        assert "esc-B" in idx["escopo_ids"]

    def test_create_escopo_no_duplicate_in_index(self, handle: StorageProjectHandle) -> None:
        handle.create_escopo(
            escopo_id="esc-dup",
            nome="Dup",
            tipo_obra="terraplenagem",
            localizacao="MG",
            coordenadas_lat=-19.9,
            coordenadas_lng=-43.9,
            data_inicio="2026-01-01",
            data_termino="2026-12-31",
        )
        idx = handle.read_json("escopos/_index.json", {"escopo_ids": []})
        assert idx["escopo_ids"].count("esc-dup") == 1

    def test_create_escopo_duplicate_raises(self, handle: StorageProjectHandle) -> None:
        handle.create_escopo(
            escopo_id="esc-dup2",
            nome="Dup",
            tipo_obra="terraplenagem",
            localizacao="MG",
            coordenadas_lat=-19.9,
            coordenadas_lng=-43.9,
            data_inicio="2026-01-01",
            data_termino="2026-12-31",
        )
        with pytest.raises(FileExistsError):
            handle.create_escopo(
                escopo_id="esc-dup2",
                nome="Dup",
                tipo_obra="terraplenagem",
                localizacao="MG",
                coordenadas_lat=-19.9,
                coordenadas_lng=-43.9,
                data_inicio="2026-01-01",
                data_termino="2026-12-31",
            )

    def test_create_escopo_writes_planos_index(self, handle: StorageProjectHandle) -> None:
        handle.create_escopo(
            escopo_id="esc-X",
            nome="X",
            tipo_obra="terraplenagem",
            localizacao="BA",
            coordenadas_lat=-12.97,
            coordenadas_lng=-38.50,
            data_inicio="2026-01-01",
            data_termino="2026-12-31",
        )
        planos_idx = handle.read_json("escopos/esc-X/planos/_index.json", None)
        assert planos_idx == {"plano_ids": []}


# ─────────────────────────────────────────────────────────────────────────────
#  StorageProjectHandle — write_canonical_raw
# ─────────────────────────────────────────────────────────────────────────────


class TestWriteCanonicalRaw:
    def test_raises_when_no_active_version(self, handle: StorageProjectHandle) -> None:
        with pytest.raises(RuntimeError, match="Nenhuma versão ativa"):
            handle.write_canonical_raw({"key": "val"})

    def test_writes_json_to_canonical_file(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        handle.update_meta(current_version="v1")
        handle.write_canonical_raw({"data": "test"}, version="v1")
        raw = storage.ler_blob(f"{project_id}/v1/canonical.json")
        parsed = json.loads(raw)
        assert parsed["data"] == "test"

    def test_uses_current_version_when_not_specified(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        handle.update_meta(current_version="v2")
        handle.write_canonical_raw({"x": 99})
        raw = storage.ler_blob(f"{project_id}/v2/canonical.json")
        assert json.loads(raw)["x"] == 99


# ─────────────────────────────────────────────────────────────────────────────
#  StorageProjectHandle — delete_tree
# ─────────────────────────────────────────────────────────────────────────────


class TestDeleteTree:
    def test_delete_tree_does_not_raise(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        storage.gravar_blob(f"{project_id}/v1/file.json", b"data")
        # delete_tree is a no-op in current implementation but must not raise
        handle.delete_tree("v1")


# ─────────────────────────────────────────────────────────────────────────────
#  StorageProjectRepository — create_project
# ─────────────────────────────────────────────────────────────────────────────


class TestCreateProject:
    def test_create_project_generates_uuid(self, repo: StorageProjectRepository) -> None:
        import uuid

        handle = repo.create_project("Obra Norte", "mendeslobo")
        # project_id must be a valid UUID
        parsed = uuid.UUID(handle._project_id)
        assert str(parsed) == handle._project_id

    def test_create_project_writes_meta(self, repo: StorageProjectRepository, storage: MemoryBlobStorage) -> None:
        handle = repo.create_project("Obra Norte", "ctx-001", catalogo_base="cat-abc")
        meta = handle.meta
        assert meta["nome"] == "Obra Norte"
        assert meta["contexto_id"] == "ctx-001"
        assert meta["catalogo_base"] == "cat-abc"
        assert meta["current_version"] is None

    def test_create_project_writes_four_override_stubs(
        self, repo: StorageProjectRepository, storage: MemoryBlobStorage
    ) -> None:
        handle = repo.create_project("Obra Sul", "ctx-002")
        for fname in (
            "overrides/insumos_override.json",
            "overrides/cpus_override.json",
            "overrides/bdi_override.json",
            "overrides/mobilizacao_policy_override.json",
        ):
            data = handle.read_json(fname, None)
            assert data == {}, f"{fname} should be empty dict, got {data}"

    def test_create_project_updates_projects_index(
        self, repo: StorageProjectRepository, storage: MemoryBlobStorage
    ) -> None:
        h1 = repo.create_project("P1", "ctx")
        h2 = repo.create_project("P2", "ctx")
        idx = json.loads(storage.ler_blob("projetos/_index.json").decode("utf-8"))
        assert h1._project_id in idx["project_ids"]
        assert h2._project_id in idx["project_ids"]

    def test_create_project_returns_handle(self, repo: StorageProjectRepository) -> None:
        handle = repo.create_project("Test", "ctx")
        assert isinstance(handle, StorageProjectHandle)


# ─────────────────────────────────────────────────────────────────────────────
#  StorageProjectRepository — list_projects
# ─────────────────────────────────────────────────────────────────────────────


class TestListProjects:
    def test_returns_empty_list_when_index_missing(self, repo: StorageProjectRepository) -> None:
        assert repo.list_projects() == []

    def test_hydrates_handles_when_index_exists(self, repo: StorageProjectRepository) -> None:
        h1 = repo.create_project("A", "ctx")
        h2 = repo.create_project("B", "ctx")
        projects = repo.list_projects()
        ids = [p._project_id for p in projects]
        assert h1._project_id in ids
        assert h2._project_id in ids

    def test_list_projects_returns_storage_project_handles(self, repo: StorageProjectRepository) -> None:
        repo.create_project("Proj", "ctx")
        projects = repo.list_projects()
        assert all(isinstance(p, StorageProjectHandle) for p in projects)


# ─────────────────────────────────────────────────────────────────────────────
#  StorageProjectRepository — get_project
# ─────────────────────────────────────────────────────────────────────────────


class TestGetProject:
    def test_get_project_raises_for_unknown_id(self, repo: StorageProjectRepository) -> None:
        with pytest.raises(FileNotFoundError, match="não encontrado"):
            repo.get_project("00000000-0000-0000-0000-000000000099")

    def test_get_project_returns_handle_for_known_id(self, repo: StorageProjectRepository) -> None:
        handle = repo.create_project("Known", "ctx")
        fetched = repo.get_project(handle._project_id)
        assert isinstance(fetched, StorageProjectHandle)
        assert fetched._project_id == handle._project_id

    def test_get_project_meta_is_accessible(self, repo: StorageProjectRepository) -> None:
        original = repo.create_project("Meta Test", "ctx-meta")
        fetched = repo.get_project(original._project_id)
        assert fetched.meta["nome"] == "Meta Test"


# ─────────────────────────────────────────────────────────────────────────────
#  _PrefixedStorage inner class
# ─────────────────────────────────────────────────────────────────────────────


class TestPrefixedStorage:
    """Test the _PrefixedStorage returned by StorageProjectRepository._full_storage()."""

    def _get_prefixed(self, storage: MemoryBlobStorage, prefix: str = "projetos") -> BlobStoragePort:
        repo = StorageProjectRepository(storage, projects_prefix=prefix)
        return repo._full_storage("proj-xyz")

    def test_gravar_blob_prepends_prefix(self, storage: MemoryBlobStorage) -> None:
        ps = self._get_prefixed(storage)
        ps.gravar_blob("proj-xyz/meta.json", b"data")
        assert storage.blob_existe("projetos/proj-xyz/meta.json")

    def test_ler_blob_prepends_prefix(self, storage: MemoryBlobStorage) -> None:
        storage.gravar_blob("projetos/proj-xyz/file.json", b"content")
        ps = self._get_prefixed(storage)
        result = ps.ler_blob("proj-xyz/file.json")
        assert result == b"content"

    def test_ler_blob_raises_file_not_found(self, storage: MemoryBlobStorage) -> None:
        ps = self._get_prefixed(storage)
        with pytest.raises(FileNotFoundError):
            ps.ler_blob("proj-xyz/nonexistent.json")

    def test_blob_existe_prepends_prefix(self, storage: MemoryBlobStorage) -> None:
        storage.gravar_blob("projetos/proj-xyz/present.json", b"")
        ps = self._get_prefixed(storage)
        assert ps.blob_existe("proj-xyz/present.json") is True
        assert ps.blob_existe("proj-xyz/absent.json") is False

    def test_listar_blobs_prepends_prefix_and_strips_result(self, storage: MemoryBlobStorage) -> None:
        storage.gravar_blob("projetos/proj-xyz/v1/canonical.json", b"")
        storage.gravar_blob("projetos/proj-xyz/v1/invocations.log", b"")
        storage.gravar_blob("projetos/other-proj/v1/canonical.json", b"")  # should not appear
        ps = self._get_prefixed(storage)
        blobs = ps.listar_blobs("proj-xyz")
        # results must NOT have the "projetos/" prefix stripped further than expected
        assert "proj-xyz/v1/canonical.json" in blobs
        assert "proj-xyz/v1/invocations.log" in blobs
        # other project must not appear
        assert not any("other-proj" in b for b in blobs)

    def test_aprovar_versao_prepends_prefix(self, storage: MemoryBlobStorage) -> None:
        ps = self._get_prefixed(storage)
        ps.aprovar_versao("proj-xyz/v1/canonical.json")
        assert "projetos/proj-xyz/v1/canonical.json" in storage._approved

    def test_prefix_strips_leading_slash(self, storage: MemoryBlobStorage) -> None:
        ps = self._get_prefixed(storage)
        ps.gravar_blob("/proj-xyz/meta.json", b"data")
        assert storage.blob_existe("projetos/proj-xyz/meta.json")


class TestStorageProjectHandleSatisfiesProjectHandleProtocol:
    """Governança: StorageProjectHandle precisa ter todo método/propriedade que
    ProjectHandle (Protocol) declara. ProjectHandle não é @runtime_checkable, então
    isinstance() não pega o gap — só um type checker estrutural (ty/mypy) ou este
    teste. Já pegamos um caso real: tipo_projeto e status_eap estavam faltando e
    quebravam get_pipeline_strategy() com AttributeError para qualquer projeto no
    backend SharePoint/S3/Azure (o único usado em produção)."""

    def test_all_protocol_members_present(self) -> None:
        from typing import Generic, Protocol

        from concilium.application.services.project.project_repository import ProjectHandle
        from concilium.infrastructure.storage.storage_project_repository import StorageProjectHandle

        # dir(ProjectHandle) inclui maquinário de Protocol/ABCMeta (ex.: "register"
        # se o protocolo virar @runtime_checkable) que não faz parte do contrato
        # real — usamos apenas o que está declarado no corpo do Protocol.
        protocol_members: set[str] = set()
        for klass in ProjectHandle.__mro__:
            if klass in (Protocol, Generic, object):
                continue
            protocol_members.update(name for name in klass.__dict__ if not name.startswith("_"))

        handle_members = {name for name in dir(StorageProjectHandle) if not name.startswith("_")}
        missing = protocol_members - handle_members
        assert not missing, f"StorageProjectHandle não implementa: {sorted(missing)}"


# ─────────────────────────────────────────────────────────────────────────────
#  StorageProjectHandle — premissas efetivas no modelo vN flat (issue #123)
#  Espelha TestPlanoStorePremissasEfetivas (test_escopo_store.py, issue #121),
#  escopado por versão (via BlobStoragePort) em vez de por plano.
# ─────────────────────────────────────────────────────────────────────────────


class TestStorageProjectHandlePremissasEfetivas:
    def test_write_creates_both_files(self, handle: StorageProjectHandle, project_id: str) -> None:
        handle.write_premissas_efetivas(
            "v1", "06-resultado-financeiro", {"bdi_aplicado": {"mao_obra": 0.3}}, {"contexto_id": "ctx-test"}
        )
        assert handle.exists("v1/premissas_efetivas.json")
        assert handle.exists("v1/premissas_por_skill.json")

    def test_read_premissas_por_skill_empty_when_missing(self, handle: StorageProjectHandle) -> None:
        assert handle.read_premissas_por_skill("v1") == {}

    def test_read_premissas_por_skill_roundtrip(self, handle: StorageProjectHandle) -> None:
        handle.write_premissas_efetivas("v1", "04-cronograma", {"a": 1}, {"contexto_id": "ctx-test"})
        por_skill = handle.read_premissas_por_skill("v1")
        assert "04-cronograma" in por_skill
        assert "hash" in por_skill["04-cronograma"]
        assert "escopo_hash" in por_skill["04-cronograma"]

    def test_mesmo_escopo_meta_produz_mesmo_escopo_hash(self, handle: StorageProjectHandle) -> None:
        escopo_meta = {"contexto_id": "ctx-test", "snapshot_catalogo_id": "cat-1"}
        handle.write_premissas_efetivas("v1", "04-cronograma", {"a": 1}, escopo_meta)
        handle.write_premissas_efetivas("v1", "06-resultado-financeiro", {"b": 2}, escopo_meta)
        por_skill = handle.read_premissas_por_skill("v1")
        assert por_skill["04-cronograma"]["escopo_hash"] == por_skill["06-resultado-financeiro"]["escopo_hash"]

    def test_escopo_meta_diferente_produz_hash_diferente(self, handle: StorageProjectHandle) -> None:
        handle.write_premissas_efetivas("v1", "04-cronograma", {"a": 1}, {"contexto_id": "ctx-a"})
        handle.write_premissas_efetivas("v1", "06-resultado-financeiro", {"b": 2}, {"contexto_id": "ctx-b"})
        por_skill = handle.read_premissas_por_skill("v1")
        assert por_skill["04-cronograma"]["escopo_hash"] != por_skill["06-resultado-financeiro"]["escopo_hash"]

    def test_approve_protects_premissas_files(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        handle.write_premissas_efetivas("v1", "06-resultado-financeiro", {"a": 1}, {"contexto_id": "ctx-test"})
        handle.approve("v1")
        assert f"{project_id}/v1/premissas_efetivas.json" in storage._approved
        assert f"{project_id}/v1/premissas_por_skill.json" in storage._approved

    def test_approve_does_not_fail_when_premissas_missing(self, handle: StorageProjectHandle) -> None:
        """approve() não deve tentar aprovar arquivos de premissas inexistentes
        (backends reais como SharePoint levantam FileNotFoundError em blob ausente)."""
        handle.approve("v1")  # não deve lançar

    def test_bdi_perfil_versao_captured_when_present(self, handle: StorageProjectHandle) -> None:
        handle.write_premissas_efetivas(
            "v1",
            "06-resultado-financeiro",
            {"bdi_perfil": {"versao": 3, "content_hash": "abc"}},
            {"contexto_id": "ctx-test"},
        )
        por_skill = handle.read_premissas_por_skill("v1")
        assert por_skill["06-resultado-financeiro"]["bdi_perfil_versao"] == 3


# ─────────────────────────────────────────────────────────────────────────────
#  StorageProjectHandle — proteção do perfil BDI versionado na aprovação (#123)
# ─────────────────────────────────────────────────────────────────────────────


class TestStorageProjectHandleProtectBdiPerfilVersoes:
    def test_approve_protects_referenced_bdi_perfil_version(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        handle.write_json("bdi/perfil_bdi_v003.json", {"versao": 3})
        handle.write_json("bdi/perfil_bdi.json", {"versao": 3})
        handle.write_premissas_efetivas(
            "v1", "06-resultado-financeiro", {"bdi_perfil": {"versao": 3}}, {"contexto_id": "ctx-test"}
        )

        handle.approve("v1")

        assert f"{project_id}/bdi/perfil_bdi_v003.json" in storage._approved
        assert f"{project_id}/bdi/perfil_bdi.json" not in storage._approved

    def test_approve_no_op_when_no_bdi_perfil_referenced(self, handle: StorageProjectHandle) -> None:
        handle.write_premissas_efetivas("v1", "04-cronograma", {"a": 1}, {"contexto_id": "ctx-test"})
        handle.approve("v1")  # não deve lançar

    def test_approve_skips_missing_perfil_version_blob(
        self, handle: StorageProjectHandle, storage: MemoryBlobStorage, project_id: str
    ) -> None:
        """approve() não deve tentar aprovar um blob de perfil BDI que não existe mais."""
        handle.write_premissas_efetivas(
            "v1", "06-resultado-financeiro", {"bdi_perfil": {"versao": 99}}, {"contexto_id": "ctx-test"}
        )
        handle.approve("v1")  # não deve lançar
        assert f"{project_id}/bdi/perfil_bdi_v099.json" not in storage._approved
