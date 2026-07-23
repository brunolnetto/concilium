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

