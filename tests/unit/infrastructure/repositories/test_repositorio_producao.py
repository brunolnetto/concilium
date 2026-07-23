"""Coverage batch 4 — small missing-line targets across many files."""

from __future__ import annotations

import pytest

# producao.py line 33: obter_ou_erro with missing file → FileNotFoundError
# ---------------------------------------------------------------------------


class TestProducaoObterOuErro:
    def test_raises_file_not_found(self, tmp_path):
        """Line 33: producao not found → FileNotFoundError."""
        from concilium.infrastructure.repositories.producao import RepositorioProducao

        repo = RepositorioProducao(tmp_path)
        with pytest.raises(FileNotFoundError, match="nao_existe"):
            repo.obter_ou_erro("nao_existe")


# ---------------------------------------------------------------------------




import tempfile  # noqa: E402

# producao.py line 33: obter_ou_erro raises when producao not found
# ---------------------------------------------------------------------------


class TestRepositorioProducaoObterOuErro:
    def test_raises_when_not_found(self):
        """Line 33: producao_id not in dir → obter returns None → raises FileNotFoundError."""
        from concilium.infrastructure.repositories.producao import RepositorioProducao

        with tempfile.TemporaryDirectory() as tmp:
            repo = RepositorioProducao(tmp)
            with pytest.raises(FileNotFoundError, match="NONEXISTENT"):
                repo.obter_ou_erro("NONEXISTENT")


# ---------------------------------------------------------------------------




# producao.py line 33:
# obter_ou_erro("NONEXISTENT") → raises FileNotFoundError
# ---------------------------------------------------------------------------


class TestRepositorioProducaoObterOuErro2:
    def test_obter_ou_erro_raises_when_not_found(self, tmp_path):
        """Line 33: producao not found → obter returns None → raises FileNotFoundError."""
        from concilium.infrastructure.repositories.producao import RepositorioProducao

        repo = RepositorioProducao(producoes_dir=tmp_path)
        try:
            repo.obter_ou_erro("NONEXISTENT-ID")
            raise AssertionError("Expected FileNotFoundError")
        except FileNotFoundError as exc:
            assert "NONEXISTENT-ID" in str(exc)


# ---------------------------------------------------------------------------

