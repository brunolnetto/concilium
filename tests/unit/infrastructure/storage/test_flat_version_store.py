"""Coverage sweep — files with few missing lines (1-30 lines missing)."""

from __future__ import annotations

# ─── infrastructure/storage/flat_version_store.py ────────────────────────────


class TestFlatVersionStore:
    def _make_store(self, tmp_path):
        from concilium.infrastructure.storage.flat_version_store import FlatVersionStore
        from concilium.infrastructure.storage.store_factory import build_project_repository

        store = build_project_repository(tmp_path).create_project("Test", "ctx")
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
from unittest.mock import MagicMock  # noqa: E402

# flat_version_store.py line 89->87: empty line in invocations.log → if line: False
# ---------------------------------------------------------------------------


class TestFlatVersionStoreReadInvocationsEmptyLines:
    def test_empty_lines_skipped_in_read_invocations(self):
        """Line 89->87 branch: invocations.log has blank lines → stripped line='' → if line: False."""
        from concilium.infrastructure.storage.flat_version_store import FlatVersionStore

        project_mock = MagicMock()
        project_mock.meta = {}
        project_mock.read_lines.return_value = [
            "",  # blank line (if line: False)
            "   ",  # whitespace-only (if line: False)
            json.dumps({"skill_id": "04"}),  # valid line
        ]

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
        proj_mock.load_canonical.return_value = None

        # log_invocation/read_lines em memória — FlatVersionStore delega ao
        # ProjectHandle em vez de I/O direto em version_path() (Path lógico,
        # não-backed, em backends não-filesystem).
        log_lines: list[str] = []
        proj_mock.log_invocation.side_effect = lambda version, entry: log_lines.append(
            json.dumps(entry, default=str)
        )
        proj_mock.read_lines.side_effect = lambda relative_path: list(log_lines)
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
        store._project.read_lines.side_effect = None
        store._project.read_lines.return_value = ['{"ok": true}', "BAD JSON", '{"second": true}']
        entries = store.read_invocations()
        assert len(entries) == 2


# ── FlatVersionStore.write_premissas_efetivas/read_premissas_por_skill (#123) ──
# Verifica que o wrapper delega para o ProjectStore subjacente com a versão
# correta — a lógica de hash em si já é coberta em TestProjectStorePremissasEfetivas.


class TestFlatVersionStorePremissasEfetivas:
    def _make_store(self, tmp_path):
        from concilium.infrastructure.storage.flat_version_store import FlatVersionStore
        from concilium.infrastructure.storage.store_factory import build_project_repository

        store = build_project_repository(tmp_path).create_project("Test", "ctx")
        v = store.new_version()
        return FlatVersionStore(store, v), store, v

    def test_write_delegates_to_project_with_version(self, tmp_path):
        fvs, store, v = self._make_store(tmp_path)
        fvs.write_premissas_efetivas("06-resultado-financeiro", {"a": 1}, {"contexto_id": "ctx"})

        assert store.exists(f"{v}/premissas_efetivas.json")
        por_skill = store.read_premissas_por_skill(v)
        assert "06-resultado-financeiro" in por_skill

    def test_read_delegates_to_project_with_version(self, tmp_path):
        fvs, store, v = self._make_store(tmp_path)
        store.write_premissas_efetivas(v, "04-cronograma", {"a": 1}, {"contexto_id": "ctx"})

        por_skill = fvs.read_premissas_por_skill()
        assert "04-cronograma" in por_skill

    def test_read_empty_when_nothing_written(self, tmp_path):
        fvs, store, v = self._make_store(tmp_path)
        assert fvs.read_premissas_por_skill() == {}

    def test_write_no_op_when_project_lacks_method(self, tmp_path):
        """Defesa: um project stub sem write_premissas_efetivas não deve quebrar o wrapper."""
        from unittest.mock import MagicMock

        from concilium.infrastructure.storage.flat_version_store import FlatVersionStore

        proj_mock = MagicMock(spec=["meta", "version_path", "load_canonical"])
        proj_mock.meta = {"contexto_id": "ctx-1"}
        ver_path = tmp_path / "v1"
        ver_path.mkdir()
        proj_mock.version_path.return_value = ver_path

        fvs = FlatVersionStore(proj_mock, "v1")
        fvs.write_premissas_efetivas("06-resultado-financeiro", {"a": 1}, {"contexto_id": "ctx-1"})  # não deve lançar
        assert fvs.read_premissas_por_skill() == {}



