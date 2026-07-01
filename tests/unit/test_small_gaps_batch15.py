"""Coverage batch 15 — diff_service, spec_loader_b, migrator, diffs small gaps."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# diff_service.py lines 90, 95, 100: _gerar_interpretacao improvement branches
# ---------------------------------------------------------------------------


class TestBenchmarkDiffServiceInterpretacao:
    def _svc(self):
        from concilium.application.benchmarks.diff_service import BenchmarkDiffService

        return BenchmarkDiffService()

    def test_melhoria_custo(self):
        """Line 90: delta_custo < -0.5 → 'Melhoria: custo ... menor'."""
        svc = self._svc()
        text = svc._gerar_interpretacao(delta_custo=-1.5, delta_cronograma=0, delta_margem=0.0)
        assert "Melhoria" in text
        assert "custo" in text

    def test_cronograma_menor(self):
        """Line 95: delta_cronograma < -1 → 'Cronograma ... menor'."""
        svc = self._svc()
        text = svc._gerar_interpretacao(delta_custo=0.0, delta_cronograma=-3, delta_margem=0.0)
        assert "menor" in text
        assert "Cronograma" in text

    def test_margem_melhorou(self):
        """Line 100: delta_margem > 0.5 → 'Margem melhorou ...'."""
        svc = self._svc()
        text = svc._gerar_interpretacao(delta_custo=0.0, delta_cronograma=0, delta_margem=1.2)
        assert "melhorou" in text

    def test_all_improvements_combined(self):
        """Lines 90, 95, 100 all in one call."""
        svc = self._svc()
        text = svc._gerar_interpretacao(delta_custo=-2.0, delta_cronograma=-4, delta_margem=0.8)
        assert "Melhoria" in text
        assert "menor" in text
        assert "melhorou" in text


# ---------------------------------------------------------------------------
# _spec_loader_helpers_b.py line 64: permanencia <= 0 → set to fallback_meses
# _spec_loader_helpers_b.py line 152->150: empty cat_key → skip
# ---------------------------------------------------------------------------


class TestLfdParseRawRow:
    def test_permanencia_zero_uses_fallback(self):
        """Line 64: permanencia_meses=0 → permanencia=0 <= 0 → permanencia=fallback_meses."""
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _lfd_parse_raw_row

        row = {"categoria": "ADM", "custo_total": 5000.0, "permanencia_meses": 0}
        result = _lfd_parse_raw_row(row, fallback_meses=12.0)
        assert result is not None
        cat, custo, permanencia = result
        assert cat == "ADM"
        assert permanencia == 12.0  # fallback applied

    def test_permanencia_negative_uses_fallback(self):
        """Line 64: permanencia_meses=-1 → permanencia <= 0 → set to fallback."""
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _lfd_parse_raw_row

        row = {"categoria": "TOP", "custo_total": 1000.0, "permanencia_meses": -1}
        result = _lfd_parse_raw_row(row, fallback_meses=6.0)
        assert result is not None
        _, _, permanencia = result
        assert permanencia == 6.0


class TestBiiDetalhePortCatEmptyCat:
    def test_empty_categoria_skipped(self):
        """Line 152->150 branch: cat_key='' → if cat_key: False → item not added."""
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _bii_build_detalhe_por_cat

        equipes = [
            {"categoria": "", "mao_obra": 100.0},  # empty → skipped
            {"categoria": None, "mao_obra": 200.0},  # None → '' → skipped
        ]
        result = _bii_build_detalhe_por_cat(equipes)
        assert result == {}

    def test_valid_categoria_included(self):
        """Normal path: valid cat_key → included in result."""
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _bii_build_detalhe_por_cat

        equipes = [{"categoria": "ADM", "mao_obra": 100.0}]
        result = _bii_build_detalhe_por_cat(equipes)
        assert "ADM" in result


# ---------------------------------------------------------------------------
# migrator.py lines 101-103: except block when ler_blob raises
# ---------------------------------------------------------------------------


class TestBlobMigratorExceptPath:
    def test_failed_count_incremented_on_exception(self):
        """Lines 101-103: source.ler_blob raises → except block increments result.failed."""
        from concilium.infrastructure.adapters.blob_storage.migrator import BlobMigrator

        source = MagicMock()
        source.listar_blobs.return_value = ["projetos/p1/canonical.json"]
        source.ler_blob.side_effect = OSError("Simulated blob read failure")

        target = MagicMock()

        migrator = BlobMigrator(log_interval=1)
        result = migrator.migrate(source, target, dry_run=False)

        assert result.failed == 1
        assert result.copied == 0
        assert not result.success


# ---------------------------------------------------------------------------
# diffs.py lines 80, 83: _gdfs_load_canonical continue paths
# ---------------------------------------------------------------------------


class TestGdfsLoadCanonicalContinuePaths:
    def test_skips_files_in_projetos_dir(self):
        """Line 80: entry in projetos/ is a file, not a directory → continue."""
        from concilium.application.benchmarks.analysis.diffs import _gdfs_load_canonical

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projetos = root / "projetos"
            projetos.mkdir()
            # Create a FILE (not a dir) inside projetos/
            (projetos / "not_a_directory.json").write_text("{}", encoding="utf-8")

            result = _gdfs_load_canonical("ANY-PROJECT", root)
            assert result == {}  # no dirs → nothing matched → returns {}

    def test_skips_dirs_without_meta_json(self):
        """Line 83: subdirectory of projetos/ has no meta.json → continue."""
        from concilium.application.benchmarks.analysis.diffs import _gdfs_load_canonical

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projetos = root / "projetos"
            projetos.mkdir()
            # Create a directory without meta.json
            proj_dir = projetos / "PROJ-WITHOUT-META"
            proj_dir.mkdir()

            result = _gdfs_load_canonical("ANY-PROJECT", root)
            assert result == {}  # no meta.json → continue → returns {}

    def test_returns_empty_when_project_not_found(self):
        """Normal miss case: meta.json exists but nome doesn't match."""
        from concilium.application.benchmarks.analysis.diffs import _gdfs_load_canonical

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projetos = root / "projetos"
            projetos.mkdir()
            proj_dir = projetos / "SOME-PROJECT"
            proj_dir.mkdir()
            meta = {"nome": "DIFFERENT-PROJECT"}
            (proj_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

            result = _gdfs_load_canonical("SOUGHT-PROJECT", root)
            assert result == {}
