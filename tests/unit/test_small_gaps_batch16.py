"""Coverage batch 16 — catalog_governance, logging_config, gold_aggregator, producao, cronograma_helpers."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# catalog_governance.py line 55: validate_and_resolve_producao_file raises when not found
# ---------------------------------------------------------------------------


class TestCatalogGovernanceProducaoNotFound:
    def test_raises_when_producao_not_found(self):
        """Line 55: neither producoes/ nor produtividades/ has the file → raises CatalogGovernanceError."""
        from concilium.application.orchestrators.catalog_governance import (
            CatalogGovernanceError,
            validate_and_resolve_producao_file,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "producoes").mkdir()
            (root / "produtividades").mkdir()

            with pytest.raises(CatalogGovernanceError, match="não encontrada"):
                validate_and_resolve_producao_file(root, "PROD-NONEXISTENT", valor_horario=1.0)

    def test_finds_in_producoes_dir(self):
        """Normal path: file exists under producoes/ → returns path."""
        from concilium.application.orchestrators.catalog_governance import validate_and_resolve_producao_file

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "producoes").mkdir()
            (root / "produtividades").mkdir()
            target = root / "producoes" / "PROD-01.json"
            target.write_text("{}", encoding="utf-8")

            result = validate_and_resolve_producao_file(root, "PROD-01", valor_horario=1.0)
            assert result == target


import pytest  # noqa: E402

# ---------------------------------------------------------------------------
# logging_config.py lines 45-46: _get_auth_context except branch when import fails
# ---------------------------------------------------------------------------


class TestLoggingConfigGetAuthContext:
    def test_returns_empty_strings_when_auth_context_import_fails(self):
        """Lines 45-46: import of auth_context raises → except → return ('', '')."""
        # Patch the module so the import inside _get_auth_context fails
        with patch.dict(
            sys.modules,
            {
                "concilium.infrastructure.middleware.auth_context": None,  # type: ignore[dict-item]
            },
        ):
            from concilium.infrastructure.observability.logging_config import _get_auth_context

            user_id, request_id = _get_auth_context()
            assert user_id == ""
            assert request_id == ""


# ---------------------------------------------------------------------------
# gold_aggregator.py lines 39-40: _read_silver except block when ler_blob raises
# ---------------------------------------------------------------------------


class TestGoldAggregatorReadSilverException:
    def test_exception_in_ler_blob_is_swallowed(self):
        """Lines 39-40: ler_blob raises → except Exception: pass → returns []."""
        from concilium.infrastructure.observability.gold_aggregator import GoldAggregator

        storage = MagicMock()
        storage.listar_blobs.return_value = ["observability/silver/traces/file.jsonl"]
        storage.ler_blob.side_effect = OSError("Simulated read failure")

        agg = GoldAggregator(storage)
        records = agg._read_silver("traces")

        assert records == []

    def test_invalid_json_in_line_is_swallowed(self):
        """Lines 39-40: ler_blob returns invalid JSON → json.loads raises → except: pass."""
        from concilium.infrastructure.observability.gold_aggregator import GoldAggregator

        storage = MagicMock()
        storage.listar_blobs.return_value = ["observability/silver/traces/file.jsonl"]
        storage.ler_blob.return_value = b"NOTJSON{{{invalid\n"

        agg = GoldAggregator(storage)
        records = agg._read_silver("traces")

        assert records == []


# ---------------------------------------------------------------------------
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
# _04_cronograma_skill_helpers.py line 53->46: tipo unknown → elif False → no-op
# ---------------------------------------------------------------------------


class TestExtractDagUnknownPredecessorType:
    def test_unknown_tipo_produces_no_edge(self):
        """Line 53->46 branch: tipo='SF' is not FS and not in (SS,FF) → elif False → skip."""
        from concilium.application.skills.manifests._04_cronograma_skill_helpers import extract_dag_from_spec_or_eap

        pred = SimpleNamespace(item_id="A1", tipo="SF", lag=0, completion_threshold_pct=1.0)
        item = SimpleNamespace(item_id="B1", predecessores_tipados=lambda: [pred])

        dag = extract_dag_from_spec_or_eap(spec={}, activities=[], eap_items=[item])

        # No edge added since tipo "SF" is not handled
        assert dag.precedence == []
        assert dag.thresholds == {}
        assert dag.extended_precedences == []
