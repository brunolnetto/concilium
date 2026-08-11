"""Testa `scripts/catalog/sync_catalog_to_backend.py`: replicação por conteúdo de um
catálogo local para um BlobStoragePort remoto (produção real: SharePoint).

Usa um fake in-memory de BlobStoragePort — não toca rede/SharePoint real.
"""

from __future__ import annotations

import json

import pytest

from scripts.catalog.sync_catalog_to_backend import run_sync


class _FakeStorage:
    """Fake in-memory de BlobStoragePort para testar a lógica de sync isoladamente."""

    def __init__(self, blobs: dict[str, bytes] | None = None) -> None:
        self.blobs: dict[str, bytes] = dict(blobs or {})
        self.deletar_chamadas: list[str] = []

    def ler_blob(self, path: str) -> bytes:
        if path not in self.blobs:
            raise FileNotFoundError(path)
        return self.blobs[path]

    def gravar_blob(self, path: str, content: bytes) -> None:
        self.blobs[path] = content

    def listar_blobs(self, prefix: str) -> list[str]:
        return [p for p in self.blobs if p.startswith(prefix)]

    def blob_existe(self, path: str) -> bool:
        return path in self.blobs

    def deletar_blob(self, path: str) -> None:
        self.deletar_chamadas.append(path)
        self.blobs.pop(path, None)


@pytest.fixture()
def _catalogo_local(tmp_path):
    cat_dir = tmp_path / "config" / "catalogos" / "meucat"
    (cat_dir / "produtividades").mkdir(parents=True)
    (cat_dir / "produtividades" / "NOVO.json").write_text(json.dumps({"id": "NOVO"}), encoding="utf-8")
    (cat_dir / "produtividades" / "MUDOU.json").write_text(json.dumps({"id": "MUDOU", "v": 2}), encoding="utf-8")
    (cat_dir / "produtividades" / "IGUAL.json").write_text(json.dumps({"id": "IGUAL"}), encoding="utf-8")
    # Artefatos de cache — nunca devem ser espelhados.
    (cat_dir / ".catalog_bundle.json").write_text("{}", encoding="utf-8")
    (cat_dir / "catalog.duckdb").write_bytes(b"binario-fake")
    return cat_dir


def _patch_backend(monkeypatch, storage, backend="sharepoint"):
    import scripts.catalog.sync_catalog_to_backend as mod

    monkeypatch.setattr(
        "concilium.infrastructure.storage.store_factory.resolve_store_backend", lambda: backend
    )
    monkeypatch.setattr(
        "concilium.infrastructure.storage.store_factory.build_blob_storage", lambda *a, **k: storage
    )
    return mod


class TestSyncCatalogToBackend:
    def test_raises_when_backend_is_filesystem(self, monkeypatch, _catalogo_local):
        _patch_backend(monkeypatch, _FakeStorage(), backend="filesystem")
        with pytest.raises(SystemExit):
            run_sync("meucat", local_dir=_catalogo_local, apply=False)

    def test_dry_run_reports_without_writing(self, monkeypatch, _catalogo_local):
        remoto_igual = json.dumps({"id": "IGUAL"}).encode("utf-8")
        storage = _FakeStorage({"config/catalogos/meucat/produtividades/IGUAL.json": remoto_igual})
        _patch_backend(monkeypatch, storage)

        stats = run_sync("meucat", local_dir=_catalogo_local, apply=False)

        assert stats["enviados"] == 2  # NOVO + MUDOU (IGUAL já bate)
        assert stats["inalterados"] == 1
        # Nada foi de fato gravado em dry-run.
        assert "config/catalogos/meucat/produtividades/NOVO.json" not in storage.blobs

    def test_apply_writes_new_and_changed_only(self, monkeypatch, _catalogo_local):
        remoto_igual = json.dumps({"id": "IGUAL"}).encode("utf-8")
        remoto_mudou_antigo = json.dumps({"id": "MUDOU", "v": 1}).encode("utf-8")
        storage = _FakeStorage(
            {
                "config/catalogos/meucat/produtividades/IGUAL.json": remoto_igual,
                "config/catalogos/meucat/produtividades/MUDOU.json": remoto_mudou_antigo,
            }
        )
        _patch_backend(monkeypatch, storage)

        stats = run_sync("meucat", local_dir=_catalogo_local, apply=True)

        assert stats["enviados"] == 2
        novo = json.loads(storage.blobs["config/catalogos/meucat/produtividades/NOVO.json"])
        assert novo == {"id": "NOVO"}
        mudou = json.loads(storage.blobs["config/catalogos/meucat/produtividades/MUDOU.json"])
        assert mudou == {"id": "MUDOU", "v": 2}

    def test_ignores_cache_artifacts(self, monkeypatch, _catalogo_local):
        storage = _FakeStorage()
        _patch_backend(monkeypatch, storage)

        run_sync("meucat", local_dir=_catalogo_local, apply=True)

        assert not any("catalog_bundle" in p or "duckdb" in p for p in storage.blobs)

    def test_orphan_detected_but_not_deleted_without_flag(self, monkeypatch, _catalogo_local):
        storage = _FakeStorage({"config/catalogos/meucat/produtividades/ORFAO.json": b"{}"})
        _patch_backend(monkeypatch, storage)

        stats = run_sync("meucat", local_dir=_catalogo_local, apply=True, delete_orphans=False)

        assert stats["orfaos_remotos"] == ["config/catalogos/meucat/produtividades/ORFAO.json"]
        assert stats["orfaos_removidos"] == 0
        assert "config/catalogos/meucat/produtividades/ORFAO.json" in storage.blobs

    def test_apply_delete_orphans_removes(self, monkeypatch, _catalogo_local):
        storage = _FakeStorage({"config/catalogos/meucat/produtividades/ORFAO.json": b"{}"})
        _patch_backend(monkeypatch, storage)

        stats = run_sync("meucat", local_dir=_catalogo_local, apply=True, delete_orphans=True)

        assert stats["orfaos_removidos"] == 1
        assert "config/catalogos/meucat/produtividades/ORFAO.json" not in storage.blobs
        assert storage.deletar_chamadas == ["config/catalogos/meucat/produtividades/ORFAO.json"]

    def test_dry_run_delete_orphans_flag_does_not_delete(self, monkeypatch, _catalogo_local):
        """--delete-orphans sem --apply nunca deve apagar nada de fato."""
        storage = _FakeStorage({"config/catalogos/meucat/produtividades/ORFAO.json": b"{}"})
        _patch_backend(monkeypatch, storage)

        stats = run_sync("meucat", local_dir=_catalogo_local, apply=False, delete_orphans=True)

        assert stats["orfaos_removidos"] == 0
        assert "config/catalogos/meucat/produtividades/ORFAO.json" in storage.blobs

    def test_local_dir_ausente_levanta_erro(self, tmp_path, monkeypatch):
        _patch_backend(monkeypatch, _FakeStorage())
        with pytest.raises(SystemExit):
            run_sync("nao-existe", local_dir=tmp_path / "nada", apply=False)
