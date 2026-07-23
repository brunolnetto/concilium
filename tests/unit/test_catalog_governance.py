"""Coverage sweep — files with few missing lines (1-30 lines missing)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ─── application/orchestrators/catalog_governance.py ─────────────────────────


class TestCatalogGovernance:
    def test_assert_catalog_healthy_passes_on_empty(self):
        from concilium.application.orchestrators.catalog_governance import assert_catalog_healthy

        with patch(
            "concilium.application.orchestrators.catalog_governance.collect_catalog_critical_errors", return_value=[]
        ):
            assert_catalog_healthy("ctx1", {})  # should not raise

    def test_assert_catalog_healthy_raises_on_errors(self):
        from concilium.application.orchestrators.catalog_governance import (
            CatalogGovernanceError,
            assert_catalog_healthy,
        )

        with patch(
            "concilium.application.orchestrators.catalog_governance.collect_catalog_critical_errors",
            return_value=[{"cpu": "CPU-1", "erro": "missing field"}],
        ):
            with pytest.raises(CatalogGovernanceError, match="Bloqueio"):
                assert_catalog_healthy("ctx1", {})

    def test_validate_and_resolve_insumo_file(self, tmp_path):
        from concilium.application.orchestrators.catalog_governance import validate_and_resolve_insumo_file

        insumos_dir = tmp_path / "insumos"
        insumos_dir.mkdir()
        (insumos_dir / "INS-1.json").write_text('{"codigo": "INS-1"}', encoding="utf-8")
        result = validate_and_resolve_insumo_file(tmp_path, "INS-1", 100.0)
        assert result.name == "INS-1.json"

    def test_validate_insumo_negative_price_raises(self, tmp_path):
        from concilium.application.orchestrators.catalog_governance import (
            CatalogGovernanceError,
            validate_and_resolve_insumo_file,
        )

        with pytest.raises(CatalogGovernanceError, match="maior ou igual"):
            validate_and_resolve_insumo_file(tmp_path, "INS-1", -1.0)

    def test_validate_insumo_not_found_raises(self, tmp_path):
        from concilium.application.orchestrators.catalog_governance import (
            CatalogGovernanceError,
            validate_and_resolve_insumo_file,
        )

        (tmp_path / "insumos").mkdir()
        with pytest.raises(CatalogGovernanceError, match="não encontrado"):
            validate_and_resolve_insumo_file(tmp_path, "MISSING", 50.0)

    def test_validate_producao_file_found(self, tmp_path):
        from concilium.application.orchestrators.catalog_governance import validate_and_resolve_producao_file

        prods = tmp_path / "producoes"
        prods.mkdir()
        (prods / "P1.json").write_text('{"id": "P1"}', encoding="utf-8")
        result = validate_and_resolve_producao_file(tmp_path, "P1", 100.0)
        assert result.name == "P1.json"

    def test_validate_producao_zero_raises(self, tmp_path):
        from concilium.application.orchestrators.catalog_governance import (
            CatalogGovernanceError,
            validate_and_resolve_producao_file,
        )

        with pytest.raises(CatalogGovernanceError, match="maior que zero"):
            validate_and_resolve_producao_file(tmp_path, "P1", 0.0)




# ─── catalog_governance collect_errors ───────────────────────────────────────


class TestCollectCatalogErrors:
    def test_collect_errors_empty_catalog(self):
        from concilium.application.orchestrators.catalog_governance import collect_catalog_critical_errors

        result = collect_catalog_critical_errors({"cpus": []})
        assert result == []

    def test_collect_errors_with_valid_cpu(self):
        from concilium.application.orchestrators.catalog_governance import collect_catalog_critical_errors

        # A valid CPU should produce no errors
        cpu = {"codigo": "CPU-1", "descricao": "Test", "producao_id_ref": "P1"}
        with patch("concilium.application.orchestrators.catalog_governance.ValidadorCPUInsumo") as mock_v:
            mock_validator = MagicMock()
            mock_validator.validar_cpu_completa.return_value = []
            mock_v.return_value = mock_validator
            result = collect_catalog_critical_errors({"cpus": [cpu]})
        assert result == []









# catalog_governance.py line 55: producao not found → CatalogGovernanceError
# ---------------------------------------------------------------------------


class TestCatalogGovernanceMissingProducao:
    def test_producao_not_found_raises(self, tmp_path):
        """Line 55: producao file missing → CatalogGovernanceError."""
        from concilium.application.orchestrators.catalog_governance import (
            CatalogGovernanceError,
            validate_and_resolve_producao_file,
        )

        (tmp_path / "producoes").mkdir()
        (tmp_path / "produtividades").mkdir()
        with pytest.raises(CatalogGovernanceError, match="nao_existe"):
            validate_and_resolve_producao_file(tmp_path, "nao_existe", 100.0)


# ---------------------------------------------------------------------------


# catalog_governance.py line 22: assert_catalog_healthy raises CatalogGovernanceError
# ---------------------------------------------------------------------------


class TestCatalogGovernanceAssertHealthy:
    def test_raises_when_errors_found(self):
        """Line 22: assert_catalog_healthy with errors → raises CatalogGovernanceError."""
        from unittest.mock import patch

        from concilium.application.orchestrators.catalog_governance import (
            CatalogGovernanceError,
            assert_catalog_healthy,
        )

        with patch(
            "concilium.application.orchestrators.catalog_governance.collect_catalog_critical_errors",
            return_value=[{"cpu": "CPU-01", "erro": "field missing"}],
        ):
            with pytest.raises(CatalogGovernanceError):
                assert_catalog_healthy("test-catalog", {})

