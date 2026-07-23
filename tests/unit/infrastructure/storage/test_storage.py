"""Testes da camada de storage: SnapshotStore e ProjectStore."""

import json
import stat
from pathlib import Path

import pytest

from concilium.infrastructure.storage.project import ProjectStore
from concilium.infrastructure.storage.snapshot import SnapshotStore


class TestSnapshotStore:
    def test_hash_deterministico_independe_da_ordem_das_chaves(self, tmp_path: Path):
        store = SnapshotStore(tmp_path)
        a = {"x": 1, "y": 2, "z": [3, 4]}
        b = {"z": [3, 4], "y": 2, "x": 1}
        assert store.compute_hash(a) == store.compute_hash(b)

    def test_store_dedupe_por_hash(self, tmp_path: Path):
        store = SnapshotStore(tmp_path)
        h1 = store.store("perfil", {"x": 1})
        h2 = store.store("perfil", {"x": 1})
        assert h1 == h2
        files = list(tmp_path.glob("perfil-*.json"))
        assert len(files) == 1

    def test_load_recupera_conteudo(self, tmp_path: Path):
        store = SnapshotStore(tmp_path)
        original = {"chave": "valor", "lista": [1, 2, 3]}
        h = store.store("catalogo", original)
        loaded = store.load("catalogo", h)
        assert loaded == original

    def test_load_inexistente_levanta(self, tmp_path: Path):
        store = SnapshotStore(tmp_path)
        with pytest.raises(FileNotFoundError):
            store.load("catalogo", "abc1234")


class TestProjectStore:
    def test_init_cria_estrutura(self, tmp_path: Path):
        proj = ProjectStore.init(tmp_path, "test-obra", "mendeslobo")
        assert (proj.root / "meta.json").exists()
        assert (proj.root / "snapshots").is_dir()
        meta = proj.meta
        assert meta["nome"] == "test-obra"
        assert meta["contexto_id"] == "mendeslobo"
        assert meta["current_version"] is None

    def test_new_version_v1_quando_vazio(self, tmp_path: Path):
        proj = ProjectStore.init(tmp_path, "test", "mendeslobo")
        v = proj.new_version()
        assert v == "v1"
        assert (proj.root / "v1").is_dir()
        assert proj.current_version() == "v1"

    def test_new_version_increment(self, tmp_path: Path):
        proj = ProjectStore.init(tmp_path, "test", "mendeslobo")
        proj.new_version()
        proj.new_version()
        v3 = proj.new_version()
        assert v3 == "v3"
        assert proj.list_versions() == ["v1", "v2", "v3"]

    def test_new_version_copy_on_write(self, tmp_path: Path):
        proj = ProjectStore.init(tmp_path, "test", "mendeslobo")
        proj.new_version()  # v1
        # Simula canônico em v1
        (proj.root / "v1" / "canonical.json").write_text('{"x": 1}')
        proj.update_meta(current_version="v1")
        v2 = proj.new_version()
        assert (proj.root / v2 / "canonical.json").exists()
        copied = json.loads((proj.root / v2 / "canonical.json").read_text())
        assert copied == {"x": 1}

    def test_approve_torna_canonical_readonly(self, tmp_path: Path):
        proj = ProjectStore.init(tmp_path, "test", "mendeslobo")
        proj.new_version()
        (proj.root / "v1" / "canonical.json").write_text("{}")
        (proj.root / "v1" / "invocations.log").write_text("")
        proj.approve("v1")
        cf = proj.root / "v1" / "canonical.json"
        # Bit de escrita do dono não está setado
        assert not bool(cf.stat().st_mode & stat.S_IWUSR)

    def test_log_invocation_append(self, tmp_path: Path):
        proj = ProjectStore.init(tmp_path, "test", "mendeslobo")
        proj.new_version()
        proj.log_invocation("v1", {"skill": "01-teste", "status": "OK"})
        proj.log_invocation("v1", {"skill": "02-teste", "status": "OK"})
        log = (proj.root / "v1" / "invocations.log").read_text()
        lines = log.strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["skill"] == "01-teste"
