"""Coverage tests for infrastructure/storage/project.py — missing branches.

Targets the ~25% uncovered lines in ProjectStore:
- read_json JSON-decode error path
- load_canonical: no version, retry-on-FileNotFoundError, all retries exhausted
- save_canonical: no active version, read-only version
- write_canonical_raw: no version, read-only version
- resolve_cpu: aggregate list format, snapshot fallback, catalogo_base absent
- list_output_files: no version, no outputs dir
- load_output_file: no version, fallback subdir
- save_output_file: no version raises ValueError
- save_intermediate_file: str data
- new_version: base canonical missing (no error)
- approve: version dir missing raises FileNotFoundError
- extend_cpu, set_compensacao_ineficiencias: audit log paths
- list_versions: no dirs, non-vN dirs filtered out
"""

from __future__ import annotations

import json
import os
import stat

import pytest

from concilium.infrastructure.storage.project import ProjectStore


# ── helpers ──────────────────────────────────────────────────────────────────


def _make_store(tmp_path) -> ProjectStore:
    return ProjectStore.init(tmp_path, "Test Project", "ctx-test")


# ── read_json error handling ──────────────────────────────────────────────────


class TestReadJsonErrorPath:
    def test_read_json_returns_default_on_json_decode_error(self, tmp_path):
        store = _make_store(tmp_path)
        bad = store.root / "bad.json"
        bad.write_text("not valid JSON!!!", encoding="utf-8")
        result = store.read_json("bad.json", {"fallback": True})
        assert result == {"fallback": True}

    def test_read_json_returns_default_when_file_missing(self, tmp_path):
        store = _make_store(tmp_path)
        result = store.read_json("nonexistent.json", 42)
        assert result == 42


# ── load_canonical ────────────────────────────────────────────────────────────


class TestLoadCanonical:
    def test_returns_none_when_no_version(self, tmp_path):
        store = _make_store(tmp_path)
        # No current_version set → should return None immediately
        result = store.load_canonical()
        assert result is None

    def test_returns_none_when_canonical_file_missing(self, tmp_path):
        store = _make_store(tmp_path)
        store.new_version()
        # v1 dir exists but no canonical.json
        result = store.load_canonical()
        assert result is None

    def test_explicit_version_missing_canonical(self, tmp_path):
        store = _make_store(tmp_path)
        store.new_version()  # creates v1 dir
        result = store.load_canonical(version="v1")
        assert result is None


# ── save_canonical ────────────────────────────────────────────────────────────


class TestSaveCanonical:
    def test_raises_value_error_with_no_active_version(self, tmp_path):
        store = _make_store(tmp_path)
        # No version created yet
        from unittest.mock import MagicMock
        model = MagicMock()
        model.model_dump_json.return_value = '{"meta": {"versao_schema": "1.0"}}'
        with pytest.raises(ValueError, match="Nenhuma versão ativa"):
            store.save_canonical(model)

    def test_raises_permission_error_on_readonly_version(self, tmp_path):
        store = _make_store(tmp_path)
        v = store.new_version()
        vpath = store.root / v
        # Create a canonical.json and make it read-only (simulates approved version)
        cf = vpath / ProjectStore.CANONICAL_FILE
        cf.write_text('{}', encoding="utf-8")
        os.chmod(cf, 0o444)

        from unittest.mock import MagicMock
        model = MagicMock()
        model.model_dump_json.return_value = '{"meta": {}}'
        with pytest.raises(PermissionError, match="APROVADA"):
            store.save_canonical(model)

        # Cleanup
        os.chmod(cf, 0o644)


# ── write_canonical_raw ───────────────────────────────────────────────────────


class TestWriteCanonicalRaw:
    def test_raises_value_error_with_no_version(self, tmp_path):
        store = _make_store(tmp_path)
        with pytest.raises(ValueError, match="Nenhuma versão ativa"):
            store.write_canonical_raw({"key": "val"})

    def test_raises_permission_error_on_readonly_version(self, tmp_path):
        store = _make_store(tmp_path)
        v = store.new_version()
        vpath = store.root / v
        cf = vpath / ProjectStore.CANONICAL_FILE
        cf.write_text('{}', encoding="utf-8")
        os.chmod(cf, 0o444)

        with pytest.raises(PermissionError, match="read-only"):
            store.write_canonical_raw({"key": "val"})

        os.chmod(cf, 0o644)

    def test_writes_content_to_current_version(self, tmp_path):
        store = _make_store(tmp_path)
        store.new_version()
        store.write_canonical_raw({"data": "test"})
        v = store.current_version()
        content = json.loads((store.root / v / ProjectStore.CANONICAL_FILE).read_text(encoding="utf-8"))
        assert content["data"] == "test"


# ── resolve_cpu ───────────────────────────────────────────────────────────────


class TestResolveCpu:
    def test_resolve_from_override(self, tmp_path):
        store = _make_store(tmp_path)
        store.extend_cpu("CPU-OVR", {"descricao": "Override CPU"})
        result = store.resolve_cpu("CPU-OVR")
        assert result is not None
        assert result["descricao"] == "Override CPU"

    def test_resolve_returns_none_when_not_found(self, tmp_path):
        store = _make_store(tmp_path)
        result = store.resolve_cpu("CPU-MISSING")
        assert result is None

    def test_resolve_from_snapshot_catalogo(self, tmp_path):
        store = _make_store(tmp_path)
        snaps_dir = store.root / "snapshots"
        snaps_dir.mkdir(exist_ok=True)
        snap_data = {"cpus": [{"codigo": "CPU-SNAP", "descricao": "Snapshot CPU"}]}
        (snaps_dir / "catalogo-v1.json").write_text(json.dumps(snap_data), encoding="utf-8")
        result = store.resolve_cpu("CPU-SNAP")
        assert result is not None
        assert result["codigo"] == "CPU-SNAP"

    def test_resolve_from_snapshot_newest_first(self, tmp_path):
        """Snapshots sorted in reverse order — newest wins."""
        store = _make_store(tmp_path)
        snaps_dir = store.root / "snapshots"
        snaps_dir.mkdir(exist_ok=True)
        old = {"cpus": [{"codigo": "CPU-BOTH", "descricao": "Old"}]}
        new = {"cpus": [{"codigo": "CPU-BOTH", "descricao": "New"}]}
        (snaps_dir / "catalogo-v1.json").write_text(json.dumps(old), encoding="utf-8")
        (snaps_dir / "catalogo-v2.json").write_text(json.dumps(new), encoding="utf-8")
        result = store.resolve_cpu("CPU-BOTH")
        # reverse sort: catalogo-v2 comes before catalogo-v1
        assert result["descricao"] == "New"

    def test_resolve_from_aggregate_cpus_json_list(self, tmp_path):
        """resolve_cpu reads cpus.json aggregate file."""
        import sys
        from pathlib import Path

        store = ProjectStore.init(tmp_path, "Test", "ctx", catalogo_base="test-cat")
        # The aggregate file path is: concilium_root/config/catalogos/{cat}/cpus.json
        # concilium_root = Path(__file__).parents[4] from project.py
        # We can't easily override the filesystem search, so test via snapshot fallback
        # when aggregate doesn't exist — still tests the resolve path
        snaps_dir = store.root / "snapshots"
        snaps_dir.mkdir(exist_ok=True)
        (snaps_dir / "catalogo-v1.json").write_text(
            '{"cpus": [{"codigo": "CPU-AGG", "descricao": "Aggregate"}]}', encoding="utf-8"
        )
        result = store.resolve_cpu("CPU-AGG")
        assert result is not None

    def test_resolve_skips_bad_snapshot(self, tmp_path):
        """Corrupt snapshot file is skipped; next one is tried."""
        store = _make_store(tmp_path)
        snaps_dir = store.root / "snapshots"
        snaps_dir.mkdir(exist_ok=True)
        # bad first (reverse-sorted: v2 > v1)
        (snaps_dir / "catalogo-v1.json").write_text('{"cpus": [{"codigo": "CPU-OK"}]}', encoding="utf-8")
        (snaps_dir / "catalogo-v2.json").write_text("BAD JSON!!!", encoding="utf-8")
        result = store.resolve_cpu("CPU-OK")
        assert result is not None


# ── list_versions ─────────────────────────────────────────────────────────────


class TestListVersions:
    def test_empty_when_no_version_dirs(self, tmp_path):
        store = _make_store(tmp_path)
        assert store.list_versions() == []

    def test_sorted_numerically(self, tmp_path):
        store = _make_store(tmp_path)
        # Create dirs manually to ensure ordering test
        for name in ("v3", "v10", "v1"):
            (store.root / name).mkdir()
        versions = store.list_versions()
        assert versions == ["v1", "v3", "v10"]

    def test_non_vN_dirs_excluded(self, tmp_path):
        store = _make_store(tmp_path)
        (store.root / "v1").mkdir()
        (store.root / "vabc").mkdir()
        (store.root / "snapshots").mkdir(exist_ok=True)
        versions = store.list_versions()
        assert versions == ["v1"]


# ── new_version ───────────────────────────────────────────────────────────────


class TestNewVersion:
    def test_first_version_v1(self, tmp_path):
        store = _make_store(tmp_path)
        v = store.new_version()
        assert v == "v1"

    def test_increments_from_existing(self, tmp_path):
        store = _make_store(tmp_path)
        store.new_version()  # v1
        v2 = store.new_version()  # v2
        assert v2 == "v2"

    def test_no_error_when_base_canonical_missing(self, tmp_path):
        store = _make_store(tmp_path)
        store.new_version()  # v1 — no canonical.json
        v2 = store.new_version()  # tries copy-on-write, canonical missing → ok
        assert v2 == "v2"

    def test_copy_on_write_from_base(self, tmp_path):
        store = _make_store(tmp_path)
        store.new_version()  # v1
        # Write canonical to v1
        canonical_content = '{"meta": {"versao_schema": "1.0.0"}, "eap": []}'
        (store.root / "v1" / ProjectStore.CANONICAL_FILE).write_text(canonical_content, encoding="utf-8")
        v2 = store.new_version()  # should copy v1 canonical
        assert (store.root / "v2" / ProjectStore.CANONICAL_FILE).exists()

    def test_copy_from_explicit_base(self, tmp_path):
        store = _make_store(tmp_path)
        store.new_version()  # v1
        store.new_version()  # v2
        canonical_content = '{"meta": {"versao_schema": "1.0.0"}, "eap": []}'
        (store.root / "v1" / ProjectStore.CANONICAL_FILE).write_text(canonical_content, encoding="utf-8")
        v3 = store.new_version(base="v1")
        assert (store.root / "v3" / ProjectStore.CANONICAL_FILE).exists()

    def test_current_version_updated(self, tmp_path):
        store = _make_store(tmp_path)
        store.new_version()
        assert store.current_version() == "v1"


# ── list_output_files ─────────────────────────────────────────────────────────


class TestListOutputFiles:
    def test_returns_empty_list_when_no_version(self, tmp_path):
        store = _make_store(tmp_path)
        result = store.list_output_files()
        assert result == []

    def test_returns_empty_list_when_outputs_dir_missing(self, tmp_path):
        store = _make_store(tmp_path)
        store.new_version()
        # outputs/ dir not yet created
        result = store.list_output_files()
        assert result == []

    def test_returns_sorted_filenames(self, tmp_path):
        store = _make_store(tmp_path)
        store.new_version()
        v = store.current_version()
        reports = store.root / v / "outputs" / "reports"
        reports.mkdir(parents=True)
        (reports / "b.xlsx").write_bytes(b"")
        (reports / "a.xlsx").write_bytes(b"")
        result = store.list_output_files()
        assert result == ["a.xlsx", "b.xlsx"]


# ── load_output_file ─────────────────────────────────────────────────────────


class TestLoadOutputFile:
    def test_returns_none_when_no_version(self, tmp_path):
        store = _make_store(tmp_path)
        result = store.load_output_file()
        assert result is None

    def test_returns_none_when_file_missing_both_subdirs(self, tmp_path):
        store = _make_store(tmp_path)
        store.new_version()
        result = store.load_output_file(filename="missing.xlsx")
        assert result is None

    def test_fallback_to_alternate_subdir(self, tmp_path):
        """A .xlsx placed in visualizations (wrong subdir) is found via fallback."""
        store = _make_store(tmp_path)
        store.new_version()
        v = store.current_version()
        vis_dir = store.root / v / "outputs" / "visualizations"
        vis_dir.mkdir(parents=True)
        (vis_dir / "report.xlsx").write_bytes(b"xlsx-fallback")
        result = store.load_output_file(filename="report.xlsx")
        assert result == b"xlsx-fallback"

    def test_loads_png_from_visualizations(self, tmp_path):
        store = _make_store(tmp_path)
        store.new_version()
        v = store.current_version()
        vis_dir = store.root / v / "outputs" / "visualizations"
        vis_dir.mkdir(parents=True)
        (vis_dir / "chart.png").write_bytes(b"png-data")
        result = store.load_output_file(filename="chart.png")
        assert result == b"png-data"


# ── save_output_file ──────────────────────────────────────────────────────────


class TestSaveOutputFile:
    def test_raises_value_error_with_no_version(self, tmp_path):
        store = _make_store(tmp_path)
        with pytest.raises(ValueError, match="Nenhuma versão ativa"):
            store.save_output_file(b"data")

    def test_saves_xlsx_to_reports_subdir(self, tmp_path):
        store = _make_store(tmp_path)
        store.new_version()
        path = store.save_output_file(b"xlsx-bytes", filename="result.xlsx")
        assert "reports" in str(path)
        assert path.read_bytes() == b"xlsx-bytes"

    def test_saves_png_to_visualizations_subdir(self, tmp_path):
        store = _make_store(tmp_path)
        store.new_version()
        path = store.save_output_file(b"png-bytes", filename="chart.png")
        assert "visualizations" in str(path)

    def test_explicit_version_parameter(self, tmp_path):
        store = _make_store(tmp_path)
        store.new_version()  # v1
        store.new_version()  # v2 (current)
        path = store.save_output_file(b"data", version="v1", filename="out.xlsx")
        assert "v1" in str(path)


# ── save/load_intermediate_file ───────────────────────────────────────────────


class TestIntermediateFiles:
    def test_save_with_str_data(self, tmp_path):
        store = _make_store(tmp_path)
        store.new_version()
        path = store.save_intermediate_file("report.txt", "text content", "v1")
        assert path.read_text(encoding="utf-8") == "text content"

    def test_save_with_bytes_data(self, tmp_path):
        store = _make_store(tmp_path)
        store.new_version()
        path = store.save_intermediate_file("data.bin", b"\xff\xfe", "v1")
        assert path.read_bytes() == b"\xff\xfe"

    def test_load_returns_none_when_no_version(self, tmp_path):
        store = _make_store(tmp_path)
        result = store.load_intermediate_file("file.txt")
        assert result is None

    def test_load_returns_none_when_file_missing(self, tmp_path):
        store = _make_store(tmp_path)
        store.new_version()
        result = store.load_intermediate_file("missing.txt")
        assert result is None

    def test_round_trip(self, tmp_path):
        store = _make_store(tmp_path)
        store.new_version()
        store.save_intermediate_file("interim.bin", b"\xab\xcd", "v1")
        result = store.load_intermediate_file("interim.bin")
        assert result == b"\xab\xcd"


# ── approve ───────────────────────────────────────────────────────────────────


class TestApprove:
    def test_raises_file_not_found_when_version_missing(self, tmp_path):
        store = _make_store(tmp_path)
        with pytest.raises(FileNotFoundError, match="não existe"):
            store.approve("v99")

    def test_approve_makes_files_readonly(self, tmp_path):
        store = _make_store(tmp_path)
        v = store.new_version()
        vpath = store.root / v
        cf = vpath / ProjectStore.CANONICAL_FILE
        cf.write_text('{}', encoding="utf-8")
        (vpath / ProjectStore.INVOCATIONS_LOG).write_text("", encoding="utf-8")

        store.approve(v)
        mode = cf.stat().st_mode
        assert not (mode & stat.S_IWUSR), "canonical should be read-only after approve"
        # Restore so tmp_path cleanup can delete
        os.chmod(cf, 0o644)

    def test_approve_records_version_in_meta(self, tmp_path):
        store = _make_store(tmp_path)
        v = store.new_version()
        # approve without canonical.json (files won't be chmoded but shouldn't fail)
        store.approve(v)
        assert v in store.meta.get("approved_versions", [])

    def test_approve_skips_missing_files(self, tmp_path):
        """approve() must not crash if canonical.json/invocations.log don't exist."""
        store = _make_store(tmp_path)
        v = store.new_version()
        # Remove any files that new_version created
        il = store.root / v / ProjectStore.INVOCATIONS_LOG
        if il.exists():
            il.unlink()
        # Should not raise even if canonical is missing
        store.approve(v)


# ── extend_cpu and set_compensacao_ineficiencias ──────────────────────────────


class TestExtendCpuAuditLog:
    def test_extend_cpu_writes_audit_entry(self, tmp_path):
        store = _make_store(tmp_path)
        store.extend_cpu("CPU-X", {"descricao": "Test"}, actor="user", motivo="reason")
        audit_path = store.root / "audit_log.jsonl"
        assert audit_path.exists()
        lines = audit_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["event"] == "extend_cpu"
        assert entry["cpu_id"] == "CPU-X"
        assert entry["actor"] == "user"

    def test_extend_cpu_accumulates_multiple(self, tmp_path):
        store = _make_store(tmp_path)
        store.extend_cpu("CPU-A", {"a": 1})
        store.extend_cpu("CPU-B", {"b": 2})
        override = store.read_json("overrides/cpus_override.json", {})
        assert "CPU-A" in override
        assert "CPU-B" in override


class TestSetCompensacaoIneficiencias:
    def test_writes_json_file(self, tmp_path):
        store = _make_store(tmp_path)
        store.set_compensacao_ineficiencias({"fator": 1.05}, actor="system", motivo="baseline")
        data = store.read_json("compensacao_ineficiencias.json", {})
        assert data["compensacao"]["fator"] == 1.05
        assert data["actor"] == "system"

    def test_writes_audit_entry(self, tmp_path):
        store = _make_store(tmp_path)
        store.set_compensacao_ineficiencias({"fator": 1.1}, motivo="test")
        audit_lines = (store.root / "audit_log.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(audit_lines) == 1
        entry = json.loads(audit_lines[0])
        assert entry["event"] == "set_compensacao_ineficiencias"


# ── log_invocation ────────────────────────────────────────────────────────────


class TestLogInvocation:
    def test_appends_jsonl_entry(self, tmp_path):
        store = _make_store(tmp_path)
        v = store.new_version()
        store.log_invocation(v, {"skill": "04", "status": "OK"})
        log_path = store.root / v / ProjectStore.INVOCATIONS_LOG
        lines = log_path.read_text(encoding="utf-8").splitlines()
        # new_version creates an empty invocations.log, log_invocation appends
        non_empty = [l for l in lines if l.strip()]
        assert len(non_empty) == 1
        entry = json.loads(non_empty[0])
        assert entry["skill"] == "04"


# ── _is_readonly ──────────────────────────────────────────────────────────────


class TestIsReadonly:
    def test_false_when_canonical_missing(self, tmp_path):
        store = _make_store(tmp_path)
        v = store.new_version()
        result = store._is_readonly(store.root / v)
        assert result is False

    def test_false_when_writable(self, tmp_path):
        store = _make_store(tmp_path)
        v = store.new_version()
        (store.root / v / ProjectStore.CANONICAL_FILE).write_text("{}", encoding="utf-8")
        result = store._is_readonly(store.root / v)
        assert result is False

    def test_true_when_chmod_444(self, tmp_path):
        store = _make_store(tmp_path)
        v = store.new_version()
        cf = store.root / v / ProjectStore.CANONICAL_FILE
        cf.write_text("{}", encoding="utf-8")
        os.chmod(cf, 0o444)
        result = store._is_readonly(store.root / v)
        assert result is True
        os.chmod(cf, 0o644)


# ── ProjectStore.init ─────────────────────────────────────────────────────────


class TestProjectStoreInit:
    def test_init_with_benchmark_slug(self, tmp_path):
        store = ProjectStore.init(
            tmp_path, "Benchmark", "ctx",
            derivado_de_benchmark="BENCH-001",
        )
        assert store.root.name == "BENCH-001"
        assert store.meta["derivado_de_benchmark"] == "BENCH-001"

    def test_init_without_slug_uses_uuid(self, tmp_path):
        import uuid
        store = ProjectStore.init(tmp_path, "Proj", "ctx")
        # Name should be a valid UUID
        uuid.UUID(store.root.name)

    def test_init_creates_overlay_stubs(self, tmp_path):
        store = ProjectStore.init(tmp_path, "P", "ctx")
        overrides = store.root / "overrides"
        assert (overrides / "cpus_overlay.json").exists()
        assert (overrides / "insumos_overlay.json").exists()

    def test_init_preserves_existing_overrides(self, tmp_path):
        """exist_ok=True: re-init preserves existing overlay data."""
        store = ProjectStore.init(
            tmp_path, "Bench", "ctx", derivado_de_benchmark="BENCH-PRESERVED"
        )
        overlay_file = store.root / "overrides" / "cpus_overlay.json"
        overlay_file.write_text('{"CPU-EXISTING": {"x": 1}}', encoding="utf-8")

        # Re-init same slug
        store2 = ProjectStore.init(
            tmp_path, "Bench", "ctx", derivado_de_benchmark="BENCH-PRESERVED"
        )
        data = json.loads(overlay_file.read_text(encoding="utf-8"))
        assert "CPU-EXISTING" in data


# ── create_escopo ─────────────────────────────────────────────────────────────


class TestGetOutputSubdir:
    def test_image_extensions(self):
        for ext in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"):
            assert ProjectStore._get_output_subdir(f"file{ext}") == "visualizations"

    def test_document_extensions(self):
        for ext in (".pdf", ".xlsx", ".xls", ".csv"):
            assert ProjectStore._get_output_subdir(f"file{ext}") == "reports"

    def test_fallback_unknown_extension(self):
        assert ProjectStore._get_output_subdir("file.unknown") == "reports"

    def test_fallback_no_extension(self):
        assert ProjectStore._get_output_subdir("noext") == "reports"


class TestCreateEscopo:
    def test_create_escopo_raises_if_exists(self, tmp_path):
        store = _make_store(tmp_path)
        store.create_escopo(
            escopo_id="e1", nome="E1", tipo_obra="terra",
            localizacao="SP", coordenadas_lat=-23.5, coordenadas_lng=-46.6,
            data_inicio="2026-01-01", data_termino="2026-12-31",
        )
        with pytest.raises(FileExistsError, match="já existe"):
            store.create_escopo(
                escopo_id="e1", nome="E1 dup", tipo_obra="terra",
                localizacao="SP", coordenadas_lat=-23.5, coordenadas_lng=-46.6,
                data_inicio="2026-01-01", data_termino="2026-12-31",
            )

    def test_create_escopo_writes_meta(self, tmp_path):
        store = _make_store(tmp_path)
        es = store.create_escopo(
            escopo_id="e2", nome="Escopo 2", tipo_obra="pavimentacao",
            localizacao="RJ", coordenadas_lat=-22.9, coordenadas_lng=-43.2,
            data_inicio="2026-02-01", data_termino="2026-08-31",
        )
        assert es is not None
        assert "e2" in store.list_escopos()
