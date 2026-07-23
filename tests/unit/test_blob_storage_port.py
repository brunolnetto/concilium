"""Tests for: backtracking_pe models, jwt_config, cpu_mapper."""

from __future__ import annotations

# ─── domain/repositories/blob_storage_port.py ─────────────────────────────────


class TestBlobStoragePortDefaults:
    def _make(self):
        from concilium.domain.repositories.blob_storage_port import BlobStoragePort

        class _Impl(BlobStoragePort):
            def ler_blob(self, path):
                return b""

            def gravar_blob(self, path, content):
                pass

            def listar_blobs(self, prefix):
                return []

            def blob_existe(self, path):
                return False

        return _Impl()

    def test_deletar_blob_default_is_noop(self):
        """Line 50: base class deletar_blob returns without raising."""
        storage = self._make()
        storage.deletar_blob("any/path.json")  # must not raise

    def test_health_check_default_returns_ok(self):
        """Line 77: base class health_check returns status ok with backend unknown."""
        storage = self._make()
        result = storage.health_check()
        assert result["status"] == "ok"
        assert result["backend"] == "unknown"

    def test_aprovar_versao_default_is_noop(self):
        """Line 58: base class aprovar_versao returns without raising."""
        storage = self._make()
        storage.aprovar_versao("any/path.json")  # must not raise

    def test_gerar_url_temporaria_default_returns_none(self):
        """Line 69: base class gerar_url_temporaria returns None."""
        storage = self._make()
        result = storage.gerar_url_temporaria("any/path.json")
        assert result is None



