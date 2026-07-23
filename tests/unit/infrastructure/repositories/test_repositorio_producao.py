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



import json  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402

# ─── RepositorioProducao ────────────────────────────────────────────────────


class TestRepositorioProducao:
    def _make_repo(self, tmp_path):
        from concilium.infrastructure.repositories.producao import RepositorioProducao

        return RepositorioProducao(tmp_path)

    def test_obter_returns_none_when_missing(self, tmp_path):
        repo = self._make_repo(tmp_path)
        assert repo.obter("nope") is None

    def test_obter_returns_producao_when_exists(self, tmp_path):
        (tmp_path / "P1.json").write_text('{"id": "P1"}', encoding="utf-8")
        mock_prod = MagicMock()
        mock_prod.id = "P1"
        with patch("concilium.infrastructure.repositories.producao.Producao") as mock_cls:
            mock_cls.model_validate.return_value = mock_prod
            repo = self._make_repo(tmp_path)
            prod = repo.obter("P1")
        assert prod is not None
        assert prod.id == "P1"

    def test_obter_ou_erro_raises_when_missing(self, tmp_path):
        repo = self._make_repo(tmp_path)
        with pytest.raises(FileNotFoundError, match="nope"):
            repo.obter_ou_erro("nope")

    def test_salvar_writes_json(self, tmp_path):
        mock_prod = MagicMock()
        mock_prod.id = "P2"
        mock_prod.model_dump_json.return_value = '{"id": "P2"}'
        repo = self._make_repo(tmp_path)
        repo.salvar(mock_prod)
        assert (tmp_path / "P2.json").exists()

    def test_listar_ids(self, tmp_path):
        for pid in ("A", "B", "C"):
            data = {"id": pid, "descricao": "", "producao_horaria": 1.0, "unidade": "m", "equipe": [], "variantes": []}
            (tmp_path / f"{pid}.json").write_text(json.dumps(data), encoding="utf-8")
        repo = self._make_repo(tmp_path)
        ids = repo.listar_ids()
        assert set(ids) == {"A", "B", "C"}

    def test_existe_true_and_false(self, tmp_path):
        data = {"id": "X", "descricao": "", "producao_horaria": 1.0, "unidade": "m", "equipe": [], "variantes": []}
        (tmp_path / "X.json").write_text(json.dumps(data), encoding="utf-8")
        repo = self._make_repo(tmp_path)
        assert repo.existe("X") is True
        assert repo.existe("Y") is False



