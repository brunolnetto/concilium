"""Testes para os helpers de escrita/leitura/delete/invalidação do catálogo
(_catalog_storage.py — issue #147 parte 2)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from concilium.application.runtime.mixins import _catalog_storage as cs
from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class TestGravarCatalogoBlob:
    def test_filesystem_escreve_em_disco(self, tmp_path):
        with patch.object(cs, "catalog_storage_backend", return_value="filesystem"):
            cs.gravar_catalogo_blob(tmp_path, "cat1", "cpus/CPU-A.json", b'{"codigo": "CPU-A"}')

        dest = tmp_path / "catalogos" / "cat1" / "cpus" / "CPU-A.json"
        assert dest.exists()
        assert json.loads(dest.read_bytes())["codigo"] == "CPU-A"

    def test_filesystem_cria_subpastas(self, tmp_path):
        with patch.object(cs, "catalog_storage_backend", return_value="filesystem"):
            cs.gravar_catalogo_blob(tmp_path, "cat1", "insumos/mao_obra/MO-1.json", b"{}")

        assert (tmp_path / "catalogos" / "cat1" / "insumos" / "mao_obra" / "MO-1.json").exists()

    def test_remoto_usa_storage_port(self, tmp_path):
        storage = LocalBlobStorage(tmp_path)
        with patch.object(cs, "catalog_storage_backend", return_value="sharepoint"):
            with patch.object(cs, "build_blob_storage", return_value=storage):
                cs.gravar_catalogo_blob(tmp_path, "cat1", "cpus/CPU-A.json", b'{"codigo": "CPU-A"}')

        # SharePoint usa prefixo config/catalogos/{id}
        assert storage.blob_existe("config/catalogos/cat1/cpus/CPU-A.json")


class TestLerCatalogoBlob:
    def test_filesystem_le_arquivo_existente(self, tmp_path):
        _write_json(tmp_path / "catalogos" / "cat1" / "cpus" / "CPU-A.json", {"codigo": "CPU-A"})
        with patch.object(cs, "catalog_storage_backend", return_value="filesystem"):
            raw = cs.ler_catalogo_blob(tmp_path, "cat1", "cpus/CPU-A.json")
        assert json.loads(raw)["codigo"] == "CPU-A"

    def test_filesystem_levanta_not_found(self, tmp_path):
        import pytest

        with patch.object(cs, "catalog_storage_backend", return_value="filesystem"):
            with pytest.raises(FileNotFoundError):
                cs.ler_catalogo_blob(tmp_path, "cat1", "cpus/INEXISTENTE.json")

    def test_remoto_le_via_storage_port(self, tmp_path):
        storage = LocalBlobStorage(tmp_path)
        storage.gravar_blob("config/catalogos/cat1/cpus/CPU-A.json", b'{"codigo": "CPU-A"}')

        with patch.object(cs, "catalog_storage_backend", return_value="sharepoint"):
            with patch.object(cs, "build_blob_storage", return_value=storage):
                raw = cs.ler_catalogo_blob(tmp_path, "cat1", "cpus/CPU-A.json")

        assert json.loads(raw)["codigo"] == "CPU-A"


class TestDeletarCatalogoBlob:
    def test_filesystem_remove_arquivo(self, tmp_path):
        dest = tmp_path / "catalogos" / "cat1" / "cpus" / "CPU-A.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"{}")

        with patch.object(cs, "catalog_storage_backend", return_value="filesystem"):
            cs.deletar_catalogo_blob(tmp_path, "cat1", "cpus/CPU-A.json")

        assert not dest.exists()

    def test_filesystem_nao_falha_se_ausente(self, tmp_path):
        with patch.object(cs, "catalog_storage_backend", return_value="filesystem"):
            cs.deletar_catalogo_blob(tmp_path, "cat1", "cpus/INEXISTENTE.json")  # sem exceção

    def test_remoto_deleta_via_storage_port(self, tmp_path):
        storage = LocalBlobStorage(tmp_path)
        storage.gravar_blob("config/catalogos/cat1/cpus/CPU-A.json", b"{}")

        with patch.object(cs, "catalog_storage_backend", return_value="sharepoint"):
            with patch.object(cs, "build_blob_storage", return_value=storage):
                cs.deletar_catalogo_blob(tmp_path, "cat1", "cpus/CPU-A.json")

        assert not storage.blob_existe("config/catalogos/cat1/cpus/CPU-A.json")


class TestInvalidarCatalogoCache:
    def test_remove_bundle_local(self, tmp_path):
        cat_dir = tmp_path / "catalogos" / "cat1"
        cat_dir.mkdir(parents=True)
        bundle = cat_dir / ".catalog_bundle.json"
        bundle.write_bytes(b"{}")

        cs.invalidar_catalogo_cache(tmp_path, "cat1")

        assert not bundle.exists()

    def test_remove_cache_remoto(self, tmp_path):
        cat_dir = tmp_path / "catalogos" / "cat1"
        cat_dir.mkdir(parents=True)
        remote = cat_dir / ".catalog_bundle_remote.json"
        remote.write_bytes(b"{}")

        cs.invalidar_catalogo_cache(tmp_path, "cat1")

        assert not remote.exists()

    def test_nao_falha_sem_cache(self, tmp_path):
        cs.invalidar_catalogo_cache(tmp_path, "cat_sem_bundle")  # sem exceção


class TestGravarLerRoundtrip:
    def test_filesystem_roundtrip(self, tmp_path):
        payload = {"codigo": "CPU-X", "descricao": "Teste"}
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        with patch.object(cs, "catalog_storage_backend", return_value="filesystem"):
            cs.gravar_catalogo_blob(tmp_path, "cat1", "cpus/CPU-X.json", content)
            raw = cs.ler_catalogo_blob(tmp_path, "cat1", "cpus/CPU-X.json")

        assert json.loads(raw) == payload

    def test_remoto_roundtrip(self, tmp_path):
        storage = LocalBlobStorage(tmp_path)
        payload = {"codigo": "CPU-X"}
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        with patch.object(cs, "catalog_storage_backend", return_value="s3"):
            with patch.object(cs, "build_blob_storage", return_value=storage):
                cs.gravar_catalogo_blob(tmp_path, "cat1", "cpus/CPU-X.json", content)
                raw = cs.ler_catalogo_blob(tmp_path, "cat1", "cpus/CPU-X.json")

        assert json.loads(raw) == payload
