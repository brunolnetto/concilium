"""Testes para CachingBlobStorage — TTL cache + offline fallback (issues #2/#3)."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from concilium.domain.repositories.blob_storage_port import StorageUnavailableError
from concilium.infrastructure.adapters.blob_storage.caching import CachingBlobStorage


def _backend(*, raise_on_read: Exception | None = None) -> MagicMock:
    mock = MagicMock()
    mock.ler_blob.return_value = b"content"
    if raise_on_read is not None:
        mock.ler_blob.side_effect = raise_on_read
    mock.listar_blobs.return_value = ["a.json"]
    mock.blob_existe.return_value = True
    mock.gravar_blob.return_value = None
    mock.deletar_blob.return_value = None
    mock.gerar_url_temporaria.return_value = "https://example.com/blob"
    mock.health_check.return_value = {"status": "ok", "backend": "s3"}
    return mock


class TestCacheHitMiss:
    def test_miss_consulta_backend(self, tmp_path):
        backend = _backend()
        cache = CachingBlobStorage(backend, ttl_seconds=60)
        result = cache.ler_blob("a.json")
        assert result == b"content"
        backend.ler_blob.assert_called_once_with("a.json")

    def test_hit_nao_consulta_backend(self):
        backend = _backend()
        cache = CachingBlobStorage(backend, ttl_seconds=60)
        cache.ler_blob("a.json")
        cache.ler_blob("a.json")
        assert backend.ler_blob.call_count == 1

    def test_expirado_reconsulta_backend(self):
        backend = _backend()
        cache = CachingBlobStorage(backend, ttl_seconds=0.01)
        cache.ler_blob("a.json")
        time.sleep(0.02)
        cache.ler_blob("a.json")
        assert backend.ler_blob.call_count == 2


class TestOfflineFallback:
    def test_falha_de_rede_serve_stale(self):
        backend = _backend()
        cache = CachingBlobStorage(backend, ttl_seconds=0.01)
        # Popula o cache
        cache.ler_blob("a.json")
        time.sleep(0.02)  # Expira TTL
        # Agora backend falha
        backend.ler_blob.side_effect = OSError("network error")
        result = cache.ler_blob("a.json")
        assert result == b"content"  # stale servido

    def test_sem_cache_propaga_unavailable(self):
        backend = _backend(raise_on_read=OSError("network error"))
        cache = CachingBlobStorage(backend, ttl_seconds=60)
        with pytest.raises(StorageUnavailableError):
            cache.ler_blob("a.json")

    def test_file_not_found_propaga_sem_stale(self):
        backend = _backend(raise_on_read=FileNotFoundError("not found"))
        cache = CachingBlobStorage(backend, ttl_seconds=60)
        with pytest.raises(FileNotFoundError):
            cache.ler_blob("a.json")


class TestWriteInvalidation:
    def test_gravar_atualiza_cache(self):
        backend = _backend()
        cache = CachingBlobStorage(backend, ttl_seconds=60)
        cache.gravar_blob("a.json", b"new")
        result = cache.ler_blob("a.json")
        # Deve retornar o valor gravado sem consultar o backend novamente
        assert result == b"new"
        backend.ler_blob.assert_not_called()

    def test_deletar_invalida_cache(self):
        backend = _backend()
        cache = CachingBlobStorage(backend, ttl_seconds=60)
        cache.ler_blob("a.json")        # 1ª leitura popula cache → call_count = 1
        cache.deletar_blob("a.json")    # evicta cache
        cache.ler_blob("a.json")        # cache miss após delete → call_count = 2
        assert backend.ler_blob.call_count == 2


class TestDelegation:
    def test_listar_blobs_delega(self):
        backend = _backend()
        cache = CachingBlobStorage(backend, ttl_seconds=60)
        result = cache.listar_blobs("prefix/")
        assert result == ["a.json"]
        backend.listar_blobs.assert_called_once_with("prefix/")

    def test_blob_existe_delega(self):
        backend = _backend()
        cache = CachingBlobStorage(backend, ttl_seconds=60)
        assert cache.blob_existe("a.json") is True

    def test_gerar_url_temporaria_delega(self):
        backend = _backend()
        cache = CachingBlobStorage(backend, ttl_seconds=60)
        url = cache.gerar_url_temporaria("a.json", 300)
        assert url == "https://example.com/blob"
        backend.gerar_url_temporaria.assert_called_once_with("a.json", 300, scope="anonymous")

    def test_health_check_inclui_cache_info(self):
        backend = _backend()
        cache = CachingBlobStorage(backend, ttl_seconds=42)
        result = cache.health_check()
        assert result["cache_ttl_seconds"] == 42
        assert "cache_entries" in result
