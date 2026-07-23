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



import json  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

# flat_version_store.py line 89->87: empty line in invocations.log → if line: False
# ---------------------------------------------------------------------------


class TestFlatVersionStoreReadInvocationsEmptyLines:
    def test_empty_lines_skipped_in_read_invocations(self):
        """Line 89->87 branch: invocations.log has blank lines → stripped line='' → if line: False."""
        from concilium.infrastructure.storage.flat_version_store import FlatVersionStore

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "v1"
            root.mkdir()

            # Write log with blank lines AND a valid JSON line
            log_path = root / FlatVersionStore.INVOCATIONS_LOG
            log_path.write_text(
                "\n"  # blank line (if line: False)
                + "   \n"  # whitespace-only (if line: False)
                + json.dumps({"skill_id": "04"})
                + "\n",  # valid line
                encoding="utf-8",
            )

            project_mock = MagicMock()
            project_mock.version_path.return_value = root
            project_mock.meta = {}

            store = FlatVersionStore(project_mock, "v1")
            result = store.read_invocations()

            # Only the valid JSON line returned; blank lines skipped
            assert len(result) == 1
            assert result[0]["skill_id"] == "04"


# ---------------------------------------------------------------------------




# ─── infrastructure/storage/flat_version_store.py ─────────────────────────────


class TestFlatVersionStore2:
    def _make_store(self, tmp_path):
        from concilium.infrastructure.storage.flat_version_store import FlatVersionStore

        proj_mock = MagicMock()
        proj_mock.meta = {
            "contexto_id": "ctx-1",
            "snapshot_catalogo_id": "cat-v2",
            "snapshot_perfil_id": "perf-1",
        }
        ver_path = tmp_path / "v1"
        ver_path.mkdir()
        proj_mock.version_path.return_value = ver_path
        proj_mock.load_canonical.return_value = None
        return FlatVersionStore(proj_mock, "v1")

    def test_plano_id(self, tmp_path):
        store = self._make_store(tmp_path)
        assert store.plano_id == "v1"

    def test_meta(self, tmp_path):
        store = self._make_store(tmp_path)
        assert store.meta["plano_id"] == "v1"

    def test_escopo_store_meta_with_snapshots(self, tmp_path):
        store = self._make_store(tmp_path)
        meta = store.escopo_store.meta
        assert meta["snapshot_catalogo_id"] == "cat-v2"
        assert meta["snapshot_perfil_id"] == "perf-1"

    def test_log_and_read_invocations(self, tmp_path):
        store = self._make_store(tmp_path)
        store.log_invocation({"skill": "01-escopo-e-eap", "status": "OK"})
        store.log_invocation({"skill": "02-prod", "status": "ERRO"})
        entries = store.read_invocations()
        assert len(entries) == 2
        assert entries[0]["skill"] == "01-escopo-e-eap"

    def test_read_invocations_empty(self, tmp_path):
        store = self._make_store(tmp_path)
        assert store.read_invocations() == []

    def test_read_invocations_skips_invalid_json(self, tmp_path):
        store = self._make_store(tmp_path)
        log_file = store.root / store.INVOCATIONS_LOG
        log_file.write_text('{"ok": true}\nBAD JSON\n{"second": true}\n')
        entries = store.read_invocations()
        assert len(entries) == 2



