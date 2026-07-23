"""Tests for: backtracking_pe models, jwt_config, cpu_mapper."""

from __future__ import annotations

from pathlib import Path

import pytest

# ─── infrastructure/adapters/blob_storage/local.py ────────────────────────────


class TestLocalBlobStorageCoverage:
    def test_path_traversal_raises_value_error(self):
        """Line 26: accessing path outside root raises ValueError."""
        import tempfile

        from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage

        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalBlobStorage(Path(tmp))
            with pytest.raises(ValueError, match="fora do diretório raiz"):
                storage._resolve_path("../../etc/passwd")

    def test_ler_blob_directory_raises_is_a_directory(self):
        """Line 34: ler_blob on a directory path raises IsADirectoryError."""
        import tempfile

        from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage

        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalBlobStorage(Path(tmp))
            (Path(tmp) / "subdir").mkdir()
            with pytest.raises(IsADirectoryError):
                storage.ler_blob("subdir")

    def test_blob_existe_path_traversal_returns_false(self):
        """Lines 69-70: blob_existe with path traversal catches ValueError → False."""
        import tempfile

        from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage

        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalBlobStorage(Path(tmp))
            result = storage.blob_existe("../../etc/passwd")
        assert result is False



