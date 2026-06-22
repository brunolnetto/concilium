"""Tests for storage/project.py — missing coverage paths."""

from __future__ import annotations

import json
import stat
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from concilium.infrastructure.storage.project import ProjectStore

# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _init_store(tmp_path: Path) -> ProjectStore:
    return ProjectStore.init(tmp_path, nome="Teste", contexto_id="ctx-001")


def _make_minimal_canonical() -> dict:
    """Minimal dict that passes CanonicalModel validation."""
    return {
        "obra": {
            "nome": "Obra Teste",
            "escopo": "rodovia",
            "localizacao": "CE",
            "extensao_km": 10.0,
            "atividades": [],
        }
    }


# ─────────────────────────────────────────────────────────────────────────────
#  ProjectStore.init
# ─────────────────────────────────────────────────────────────────────────────


class TestProjectStoreInit:
    def test_init_creates_directory(self, tmp_path):
        """init() creates project directory."""
        store = _init_store(tmp_path)
        assert store.root.exists()
        assert store.root.is_dir()

    def test_init_creates_meta_json(self, tmp_path):
        """init() writes meta.json with project metadata."""
        store = _init_store(tmp_path)
        assert (store.root / "meta.json").exists()
        meta = json.loads((store.root / "meta.json").read_text())
        assert meta["nome"] == "Teste"
        assert meta["contexto_id"] == "ctx-001"

    def test_init_creates_snapshots_dir(self, tmp_path):
        """init() creates snapshots/ subdirectory."""
        store = _init_store(tmp_path)
        assert (store.root / "snapshots").exists()

    def test_meta_property(self, tmp_path):
        """meta property returns parsed meta.json dict."""
        store = _init_store(tmp_path)
        meta = store.meta
        assert "id" in meta
        assert "criado_em" in meta
        assert meta["current_version"] is None


# ─────────────────────────────────────────────────────────────────────────────
#  ProjectStore.new_version
# ─────────────────────────────────────────────────────────────────────────────


class TestNewVersion:
    def test_new_version_creates_v1(self, tmp_path):
        """new_version() creates v1 when no versions exist."""
        store = _init_store(tmp_path)
        version = store.new_version()
        assert version == "v1"
        assert (store.root / "v1").exists()

    def test_new_version_creates_v2_v3(self, tmp_path):
        """Successive new_version() calls create v2, v3..."""
        store = _init_store(tmp_path)
        assert store.new_version() == "v1"
        assert store.new_version() == "v2"
        assert store.new_version() == "v3"

    def test_new_version_updates_current_version(self, tmp_path):
        """new_version() updates current_version in meta."""
        store = _init_store(tmp_path)
        store.new_version()
        assert store.current_version() == "v1"
        store.new_version()
        assert store.current_version() == "v2"

    def test_new_version_creates_outputs_dir(self, tmp_path):
        """new_version() creates outputs/ subdirectory."""
        store = _init_store(tmp_path)
        store.new_version()
        assert (store.root / "v1" / "outputs").exists()

    def test_new_version_creates_invocations_log(self, tmp_path):
        """new_version() creates empty invocations.log."""
        store = _init_store(tmp_path)
        store.new_version()
        assert (store.root / "v1" / "invocations.log").exists()

    def test_new_version_copy_on_write(self, tmp_path):
        """new_version() copies canonical from prior version."""
        store = _init_store(tmp_path)
        store.new_version()
        # Write a canonical to v1
        (store.root / "v1" / "canonical.json").write_text(json.dumps(_make_minimal_canonical()), encoding="utf-8")
        store.new_version()  # creates v2, copies from v1
        assert (store.root / "v2" / "canonical.json").exists()


# ─────────────────────────────────────────────────────────────────────────────
#  ProjectStore.load_canonical / save_canonical / write_canonical_raw
# ─────────────────────────────────────────────────────────────────────────────


class TestCanonicalOperations:
    def test_load_canonical_none_when_no_version(self, tmp_path):
        """load_canonical() returns None when no version exists."""
        store = _init_store(tmp_path)
        result = store.load_canonical()
        assert result is None

    def test_load_canonical_none_when_no_file(self, tmp_path):
        """load_canonical() returns None when canonical.json doesn't exist."""
        store = _init_store(tmp_path)
        store.new_version()
        result = store.load_canonical()
        assert result is None

    def test_write_and_load_canonical_raw(self, tmp_path):
        """write_canonical_raw + load_canonical roundtrip."""
        store = _init_store(tmp_path)
        store.new_version()
        raw = _make_minimal_canonical()
        store.write_canonical_raw(raw)
        # Can read back as dict (not full CanonicalModel since minimal)
        content = json.loads((store.root / "v1" / "canonical.json").read_text(encoding="utf-8"))
        assert content["obra"]["nome"] == "Obra Teste"

    def test_write_canonical_raw_no_version_raises(self, tmp_path):
        """write_canonical_raw() raises ValueError when no version active."""
        store = _init_store(tmp_path)
        with pytest.raises(ValueError, match="Nenhuma versão"):
            store.write_canonical_raw({"key": "value"})

    def test_write_canonical_raw_readonly_raises(self, tmp_path):
        """write_canonical_raw() raises PermissionError on approved version."""
        store = _init_store(tmp_path)
        store.new_version()
        store.write_canonical_raw(_make_minimal_canonical())
        store.approve("v1")
        with pytest.raises(PermissionError):
            store.write_canonical_raw({"other": "data"})

    def test_save_canonical_no_version_raises(self, tmp_path):
        """save_canonical() raises ValueError when no version active."""
        store = _init_store(tmp_path)
        with pytest.raises(ValueError):
            store.save_canonical(MagicMock())

    def test_save_canonical_readonly_raises(self, tmp_path):
        """save_canonical() raises PermissionError on approved version."""
        store = _init_store(tmp_path)
        store.new_version()
        store.write_canonical_raw(_make_minimal_canonical())
        store.approve("v1")
        with pytest.raises(PermissionError):
            from unittest.mock import MagicMock

            store.save_canonical(MagicMock())


# ─────────────────────────────────────────────────────────────────────────────
#  ProjectStore.approve
# ─────────────────────────────────────────────────────────────────────────────


class TestApprove:
    def test_approve_marks_canonical_readonly(self, tmp_path):
        """approve() sets canonical.json to read-only (chmod 444)."""
        store = _init_store(tmp_path)
        store.new_version()
        store.write_canonical_raw(_make_minimal_canonical())
        store.approve("v1")

        cf = store.root / "v1" / "canonical.json"
        mode = cf.stat().st_mode
        assert not bool(mode & stat.S_IWUSR)

    def test_approve_nonexistent_version_raises(self, tmp_path):
        """approve() raises FileNotFoundError for non-existent version."""
        store = _init_store(tmp_path)
        with pytest.raises(FileNotFoundError):
            store.approve("v99")

    def test_approve_updates_meta_approved_versions(self, tmp_path):
        """approve() adds version to approved_versions in meta."""
        store = _init_store(tmp_path)
        store.new_version()
        store.write_canonical_raw(_make_minimal_canonical())
        store.approve("v1")
        assert "v1" in store.meta.get("approved_versions", [])

    def test_is_readonly_true_after_approve(self, tmp_path):
        """_is_readonly() returns True after approve()."""
        store = _init_store(tmp_path)
        store.new_version()
        store.write_canonical_raw(_make_minimal_canonical())
        store.approve("v1")
        assert store._is_readonly(store.root / "v1") is True

    def test_is_readonly_false_before_approve(self, tmp_path):
        """_is_readonly() returns False before approve()."""
        store = _init_store(tmp_path)
        store.new_version()
        store.write_canonical_raw(_make_minimal_canonical())
        assert store._is_readonly(store.root / "v1") is False


# ─────────────────────────────────────────────────────────────────────────────
#  ProjectStore.log_invocation
# ─────────────────────────────────────────────────────────────────────────────


class TestLogInvocation:
    def test_log_invocation_appends_jsonl(self, tmp_path):
        """log_invocation() appends a line to invocations.log."""
        store = _init_store(tmp_path)
        store.new_version()
        store.log_invocation("v1", {"skill": "01-escopo-e-eap", "status": "OK"})
        log_path = store.root / "v1" / "invocations.log"
        content = log_path.read_text(encoding="utf-8").strip()
        line = json.loads(content)
        assert line["skill"] == "01-escopo-e-eap"

    def test_log_invocation_multiple_appends(self, tmp_path):
        """log_invocation() appends multiple lines."""
        store = _init_store(tmp_path)
        store.new_version()
        store.log_invocation("v1", {"n": 1})
        store.log_invocation("v1", {"n": 2})
        log_path = store.root / "v1" / "invocations.log"
        lines = [ln for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) == 2


# ─────────────────────────────────────────────────────────────────────────────
#  ProjectStore.save/load/list output files
# ─────────────────────────────────────────────────────────────────────────────


class TestOutputFiles:
    def test_save_and_load_output_file(self, tmp_path):
        """save_output_file + load_output_file roundtrip."""
        store = _init_store(tmp_path)
        store.new_version()
        data = b"binary data content"
        store.save_output_file(data, filename="result.xlsx")
        loaded = store.load_output_file(filename="result.xlsx")
        assert loaded == data

    def test_load_output_file_none_when_no_version(self, tmp_path):
        """load_output_file() returns None when no version active."""
        store = _init_store(tmp_path)
        result = store.load_output_file()
        assert result is None

    def test_load_output_file_none_when_file_missing(self, tmp_path):
        """load_output_file() returns None when file doesn't exist."""
        store = _init_store(tmp_path)
        store.new_version()
        result = store.load_output_file(filename="nonexistent.xlsx")
        assert result is None

    def test_save_output_file_no_version_raises(self, tmp_path):
        """save_output_file() raises ValueError when no version active."""
        store = _init_store(tmp_path)
        with pytest.raises(ValueError):
            store.save_output_file(b"data")

    def test_list_output_files_empty(self, tmp_path):
        """list_output_files() returns [] when no files saved."""
        store = _init_store(tmp_path)
        store.new_version()
        assert store.list_output_files() == []

    def test_list_output_files_returns_names(self, tmp_path):
        """list_output_files() returns sorted list of file names."""
        store = _init_store(tmp_path)
        store.new_version()
        store.save_output_file(b"a", filename="file_b.xlsx")
        store.save_output_file(b"b", filename="file_a.xlsx")
        names = store.list_output_files()
        assert names == ["file_a.xlsx", "file_b.xlsx"]

    def test_list_output_files_no_version_returns_empty(self, tmp_path):
        """list_output_files() returns [] when no version active."""
        store = _init_store(tmp_path)
        result = store.list_output_files()
        assert result == []


# ─────────────────────────────────────────────────────────────────────────────
#  ProjectStore.list_versions / snapshots
# ─────────────────────────────────────────────────────────────────────────────


class TestListVersions:
    def test_list_versions_empty_initially(self, tmp_path):
        """list_versions() returns [] before any version created."""
        store = _init_store(tmp_path)
        assert store.list_versions() == []

    def test_list_versions_ordered(self, tmp_path):
        """list_versions() returns versions sorted numerically."""
        store = _init_store(tmp_path)
        store.new_version()
        store.new_version()
        store.new_version()
        assert store.list_versions() == ["v1", "v2", "v3"]

    def test_snapshots_property(self, tmp_path):
        """snapshots property returns SnapshotStore instance."""
        from concilium.infrastructure.storage.snapshot import SnapshotStore

        store = _init_store(tmp_path)
        assert isinstance(store.snapshots, SnapshotStore)

    def test_version_path(self, tmp_path):
        """version_path() returns correct path for a version."""
        store = _init_store(tmp_path)
        path = store.version_path("v1")
        assert path == store.root / "v1"

    def test_update_meta(self, tmp_path):
        """update_meta() updates meta.json fields."""
        store = _init_store(tmp_path)
        store.update_meta(custom_field="hello")
        assert store.meta["custom_field"] == "hello"


# ─────────────────────────────────────────────────────────────────────────────
#  ProjectStore.read_json / write_json
# ─────────────────────────────────────────────────────────────────────────────


class TestReadWriteJson:
    def test_write_then_read_json(self, tmp_path):
        store = _init_store(tmp_path)
        store.write_json("custom/data.json", {"x": 1})
        result = store.read_json("custom/data.json", {})
        assert result == {"x": 1}

    def test_read_json_missing_returns_default(self, tmp_path):
        store = _init_store(tmp_path)
        result = store.read_json("nonexistent.json", {"default": True})
        assert result == {"default": True}

    def test_read_json_invalid_returns_default(self, tmp_path):
        store = _init_store(tmp_path)
        bad = store.root / "bad.json"
        bad.write_text("not json", encoding="utf-8")
        result = store.read_json("bad.json", "fallback")
        assert result == "fallback"


# ─────────────────────────────────────────────────────────────────────────────
#  ProjectStore.extend_cpu / set_compensacao_ineficiencias
# ─────────────────────────────────────────────────────────────────────────────


class TestExtendCpuAndCompensacao:
    def test_extend_cpu_writes_override_and_audit(self, tmp_path):
        store = _init_store(tmp_path)
        store.extend_cpu("CPU-X", {"descricao": "cpu x"}, actor="user", motivo="test")
        override = store.read_json("overrides/cpus_override.json", {})
        assert "CPU-X" in override
        audit = (store.root / "audit_log.jsonl").read_text(encoding="utf-8")
        assert "extend_cpu" in audit
        assert "CPU-X" in audit

    def test_extend_cpu_multiple_entries(self, tmp_path):
        store = _init_store(tmp_path)
        store.extend_cpu("CPU-A", {"desc": "a"})
        store.extend_cpu("CPU-B", {"desc": "b"})
        override = store.read_json("overrides/cpus_override.json", {})
        assert "CPU-A" in override and "CPU-B" in override

    def test_set_compensacao_ineficiencias(self, tmp_path):
        store = _init_store(tmp_path)
        comp = {"fator": 1.05, "justificativa": "terreno irregular"}
        store.set_compensacao_ineficiencias(comp, actor="eng", motivo="ajuste")
        data = store.read_json("compensacao_ineficiencias.json", {})
        assert data["compensacao"] == comp
        assert data["actor"] == "eng"
        audit = (store.root / "audit_log.jsonl").read_text(encoding="utf-8")
        assert "set_compensacao_ineficiencias" in audit


# ─────────────────────────────────────────────────────────────────────────────
#  ProjectStore.save_intermediate_file / load_intermediate_file
# ─────────────────────────────────────────────────────────────────────────────


class TestIntermediateFiles:
    def test_save_and_load_intermediate_bytes(self, tmp_path):
        store = _init_store(tmp_path)
        store.new_version()
        store.save_intermediate_file("data.bin", b"\x00\x01\x02", "v1")
        result = store.load_intermediate_file("data.bin", "v1")
        assert result == b"\x00\x01\x02"

    def test_save_intermediate_str(self, tmp_path):
        store = _init_store(tmp_path)
        store.new_version()
        store.save_intermediate_file("report.txt", "hello world", "v1")
        result = store.load_intermediate_file("report.txt", "v1")
        assert result == b"hello world"

    def test_load_intermediate_file_missing_returns_none(self, tmp_path):
        store = _init_store(tmp_path)
        store.new_version()
        result = store.load_intermediate_file("nonexistent.bin", "v1")
        assert result is None

    def test_load_intermediate_file_no_version_returns_none(self, tmp_path):
        store = _init_store(tmp_path)
        result = store.load_intermediate_file("data.bin")
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
#  ProjectStore._get_output_subdir / save_output_file / load_output_file
# ─────────────────────────────────────────────────────────────────────────────


class TestOutputSubdirAndFallback:
    def test_get_output_subdir_image(self, tmp_path):
        assert ProjectStore._get_output_subdir("chart.png") == "visualizations"
        assert ProjectStore._get_output_subdir("image.jpg") == "visualizations"
        assert ProjectStore._get_output_subdir("fig.svg") == "visualizations"
        assert ProjectStore._get_output_subdir("img.gif") == "visualizations"
        assert ProjectStore._get_output_subdir("img.webp") == "visualizations"
        assert ProjectStore._get_output_subdir("img.jpeg") == "visualizations"

    def test_get_output_subdir_reports(self, tmp_path):
        assert ProjectStore._get_output_subdir("result.xlsx") == "reports"
        assert ProjectStore._get_output_subdir("report.pdf") == "reports"
        assert ProjectStore._get_output_subdir("data.csv") == "reports"
        assert ProjectStore._get_output_subdir("data.xls") == "reports"

    def test_get_output_subdir_fallback(self, tmp_path):
        assert ProjectStore._get_output_subdir("something.txt") == "reports"

    def test_save_image_goes_to_visualizations(self, tmp_path):
        store = _init_store(tmp_path)
        store.new_version()
        store.save_output_file(b"png data", filename="chart.png")
        vis_path = store.root / "v1" / "outputs" / "visualizations" / "chart.png"
        assert vis_path.exists()

    def test_load_output_file_fallback_subdir(self, tmp_path):
        """load_output_file falls back to the other subdir when not in primary."""
        store = _init_store(tmp_path)
        store.new_version()
        # Place a PDF in visualizations (wrong subdir) — should still be found via fallback
        wrong_dir = store.root / "v1" / "outputs" / "visualizations"
        wrong_dir.mkdir(parents=True, exist_ok=True)
        (wrong_dir / "report.pdf").write_bytes(b"pdf content")
        result = store.load_output_file(filename="report.pdf")
        assert result == b"pdf content"

    def test_list_output_files_no_version_returns_empty(self, tmp_path):
        store = _init_store(tmp_path)
        assert store.list_output_files() == []

    def test_list_output_files_outputs_dir_missing(self, tmp_path):
        store = _init_store(tmp_path)
        store.new_version()
        # v1 exists but no outputs/ subdir is created after the fact
        import shutil
        shutil.rmtree(store.root / "v1" / "outputs")
        assert store.list_output_files() == []


# ─────────────────────────────────────────────────────────────────────────────
#  ProjectStore.new_version with explicit base
# ─────────────────────────────────────────────────────────────────────────────


class TestNewVersionWithBase:
    def test_new_version_copies_from_explicit_base(self, tmp_path):
        store = _init_store(tmp_path)
        store.new_version()  # v1
        (store.root / "v1" / "canonical.json").write_text(
            json.dumps(_make_minimal_canonical()), encoding="utf-8"
        )
        store.new_version()  # v2 (no explicit base, copies v1)
        # Create v3 explicitly from v1
        store.new_version(base="v1")
        assert (store.root / "v3" / "canonical.json").exists()

    def test_new_version_no_canonical_to_copy(self, tmp_path):
        """new_version() when source has no canonical.json doesn't fail."""
        store = _init_store(tmp_path)
        store.new_version()  # v1, no canonical
        store.new_version()  # v2 — copies from v1 which has no canonical
        assert not (store.root / "v2" / "canonical.json").exists()


# ─────────────────────────────────────────────────────────────────────────────
#  ProjectStore.resolve_cpu
# ─────────────────────────────────────────────────────────────────────────────


class TestResolveCpu:
    def test_resolve_cpu_from_override(self, tmp_path):
        store = _init_store(tmp_path)
        store.extend_cpu("CPU-OVR", {"codigo": "CPU-OVR", "descricao": "override"})
        result = store.resolve_cpu("CPU-OVR")
        assert result is not None
        assert result["codigo"] == "CPU-OVR"

    def test_resolve_cpu_from_snapshot(self, tmp_path):
        store = _init_store(tmp_path)
        snaps_dir = store.root / "snapshots"
        snaps_dir.mkdir(exist_ok=True)
        snap_data = {"cpus": [{"codigo": "CPU-SNAP", "descricao": "snapshot cpu"}]}
        (snaps_dir / "catalogo-v1.json").write_text(
            json.dumps(snap_data), encoding="utf-8"
        )
        result = store.resolve_cpu("CPU-SNAP")
        assert result is not None
        assert result["codigo"] == "CPU-SNAP"

    def test_resolve_cpu_snapshot_malformed_skipped(self, tmp_path):
        store = _init_store(tmp_path)
        snaps_dir = store.root / "snapshots"
        snaps_dir.mkdir(exist_ok=True)
        (snaps_dir / "catalogo-v1.json").write_text("not json", encoding="utf-8")
        result = store.resolve_cpu("CPU-ANY")
        assert result is None

    def test_resolve_cpu_not_found(self, tmp_path):
        store = _init_store(tmp_path)
        result = store.resolve_cpu("CPU-MISSING")
        assert result is None

    def test_resolve_cpu_snapshot_newest_first(self, tmp_path):
        """Snapshots are checked in reverse order (newest first)."""
        store = _init_store(tmp_path)
        snaps_dir = store.root / "snapshots"
        snaps_dir.mkdir(exist_ok=True)
        (snaps_dir / "catalogo-v1.json").write_text(
            json.dumps({"cpus": [{"codigo": "CPU-A", "version": "old"}]}), encoding="utf-8"
        )
        (snaps_dir / "catalogo-v2.json").write_text(
            json.dumps({"cpus": [{"codigo": "CPU-A", "version": "new"}]}), encoding="utf-8"
        )
        result = store.resolve_cpu("CPU-A")
        assert result["version"] == "new"


# ─────────────────────────────────────────────────────────────────────────────
#  ProjectStore.list_escopos / escopo / create_escopo
# ─────────────────────────────────────────────────────────────────────────────


class TestEscopos:
    def test_list_escopos_empty(self, tmp_path):
        store = _init_store(tmp_path)
        assert store.list_escopos() == []

    def test_escopo_returns_escopo_store(self, tmp_path):
        from concilium.infrastructure.storage.escopo_store import EscopoStore

        store = _init_store(tmp_path)
        es = store.escopo("default")
        assert isinstance(es, EscopoStore)

    def test_create_escopo_and_list(self, tmp_path):
        from concilium.infrastructure.storage.escopo_store import EscopoStore

        store = _init_store(tmp_path)
        es = store.create_escopo(
            escopo_id="esc-001",
            nome="Trecho Norte",
            tipo_obra="terraplenagem",
            localizacao="CE",
            coordenadas_lat=-3.7,
            coordenadas_lng=-38.5,
            data_inicio="2026-01-01",
            data_termino="2026-12-31",
        )
        assert isinstance(es, EscopoStore)
        escopos = store.list_escopos()
        assert "esc-001" in escopos

    def test_create_escopo_duplicate_raises(self, tmp_path):
        store = _init_store(tmp_path)
        store.create_escopo(
            escopo_id="esc-dup",
            nome="Esc",
            tipo_obra="terraplenagem",
            localizacao="BA",
            coordenadas_lat=0.0,
            coordenadas_lng=0.0,
            data_inicio="2026-01-01",
            data_termino="2026-06-30",
        )
        with pytest.raises(FileExistsError):
            store.create_escopo(
                escopo_id="esc-dup",
                nome="Esc",
                tipo_obra="terraplenagem",
                localizacao="BA",
                coordenadas_lat=0.0,
                coordenadas_lng=0.0,
                data_inicio="2026-01-01",
                data_termino="2026-06-30",
            )

    def test_create_escopo_with_optional_fields(self, tmp_path):
        store = _init_store(tmp_path)
        es = store.create_escopo(
            escopo_id="esc-opt",
            nome="Full",
            tipo_obra="pavimentacao",
            localizacao="SP",
            coordenadas_lat=-23.5,
            coordenadas_lng=-46.6,
            data_inicio="2026-03-01",
            data_termino="2026-09-30",
            dias_semana=5,
            horas_dia=9,
            snapshot_catalogo_id="cat-001",
            snapshot_perfil_id="perf-001",
            bdi_perfil_id="bdi-001",
        )
        import json as _json
        from concilium.infrastructure.storage.escopo_store import EscopoStore
        meta = _json.loads((es.root / EscopoStore.ESCOPO_FILE).read_text(encoding="utf-8"))
        assert meta["dias_semana"] == 5
        assert meta["bdi_perfil_id"] == "bdi-001"


# ─────────────────────────────────────────────────────────────────────────────
#  ProjectStore.init with benchmark slug
# ─────────────────────────────────────────────────────────────────────────────


class TestInitWithBenchmarkSlug:
    def test_init_with_benchmark_slug_uses_slug_as_id(self, tmp_path):
        store = ProjectStore.init(
            tmp_path,
            nome="Benchmark Proj",
            contexto_id="ctx-bm",
            derivado_de_benchmark="AGIS-2026",
            benchmark_versao=3,
            benchmark_execution_id="exec-abc",
        )
        # Directory name should be the slug
        assert store.root.name == "AGIS-2026"
        meta = store.meta
        assert meta["derivado_de_benchmark"] == "AGIS-2026"
        assert meta["benchmark_versao"] == 3
        assert meta["benchmark_execution_id"] == "exec-abc"

    def test_init_existing_dir_ok(self, tmp_path):
        """init() with exist_ok=True on existing dir doesn't fail."""
        # First init
        store1 = ProjectStore.init(tmp_path, "P1", "ctx")
        project_id = store1.root.name
        # Re-init same slug should not fail (exist_ok)
        store2 = ProjectStore.init(
            tmp_path,
            nome="P2",
            contexto_id="ctx",
            derivado_de_benchmark=project_id,
        )
        assert store2.root.exists()
