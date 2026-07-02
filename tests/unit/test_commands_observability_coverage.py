"""Tests for concilium.presentation.cli.commands_observability — coverage of missing lines."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from concilium.presentation.cli.commands_observability import observability_app

runner = CliRunner()

_STORAGE_PATH = "concilium.presentation.cli.commands_observability._get_storage"


# ---------------------------------------------------------------------------
# run_pipeline
# ---------------------------------------------------------------------------


class TestRunPipeline:
    def _make_worker(self, blobs=0, records=0):
        worker = MagicMock()
        worker.run.return_value = {"blobs_processed": blobs, "records_processed": records}
        return worker

    def test_run_no_blobs(self):
        """blobs_processed=0 → prints 'Nenhum blob novo'."""
        storage = MagicMock()
        worker = self._make_worker(blobs=0, records=0)
        with (
            patch(_STORAGE_PATH, return_value=storage),
            patch(
                "concilium.infrastructure.observability.pipeline.ObservabilityWorker",
                return_value=worker,
            ),
        ):
            result = runner.invoke(observability_app, ["run"])
        assert result.exit_code == 0
        assert "Nenhum blob novo" in result.output

    def test_run_with_blobs(self):
        """blobs_processed=3 → prints success message with counts."""
        storage = MagicMock()
        worker = self._make_worker(blobs=3, records=42)
        with (
            patch(_STORAGE_PATH, return_value=storage),
            patch(
                "concilium.infrastructure.observability.pipeline.ObservabilityWorker",
                return_value=worker,
            ),
        ):
            result = runner.invoke(observability_app, ["run", "--signal", "logs"])
        assert result.exit_code == 0
        assert "3 blobs" in result.output
        assert "42 records" in result.output

    def test_run_all_signals(self):
        """--all flag iterates over all three signal types."""
        storage = MagicMock()
        worker = self._make_worker(blobs=1, records=5)
        with (
            patch(_STORAGE_PATH, return_value=storage),
            patch(
                "concilium.infrastructure.observability.pipeline.ObservabilityWorker",
                return_value=worker,
            ),
        ):
            result = runner.invoke(observability_app, ["run", "--all"])
        assert result.exit_code == 0
        # worker.run should be called once per signal type
        assert worker.run.call_count == 3
        for sig in ("logs", "traces", "metrics"):
            assert sig in result.output


# ---------------------------------------------------------------------------
# show_status
# ---------------------------------------------------------------------------


class TestShowStatus:
    def test_no_checkpoints_found(self):
        """All store.load() return None → warning printed and early return."""
        storage = MagicMock()
        store = MagicMock()
        store.load.return_value = None
        with (
            patch(_STORAGE_PATH, return_value=storage),
            patch(
                "concilium.infrastructure.observability.checkpoint_store.CheckpointStore",
                return_value=store,
            ),
        ):
            result = runner.invoke(observability_app, ["status"])
        assert result.exit_code == 0
        assert "Nenhum checkpoint encontrado" in result.output

    def test_checkpoints_found(self):
        """Some store.load() return a checkpoint object → table is printed."""
        storage = MagicMock()
        store = MagicMock()
        cp = SimpleNamespace(
            last_processed_path="observability/bronze/logs/2026/06/23/blob.parquet",
            last_processed_ts="2026-06-23T10:00:00Z",
            records_processed=100,
        )
        store.load.side_effect = lambda sig: cp if sig == "logs" else None
        with (
            patch(_STORAGE_PATH, return_value=storage),
            patch(
                "concilium.infrastructure.observability.checkpoint_store.CheckpointStore",
                return_value=store,
            ),
        ):
            result = runner.invoke(observability_app, ["status"])
        assert result.exit_code == 0
        # table should contain checkpoint data
        assert "logs" in result.output
        assert "100" in result.output
        # warning should NOT appear
        assert "Nenhum checkpoint encontrado" not in result.output


# ---------------------------------------------------------------------------
# show_report
# ---------------------------------------------------------------------------


class TestShowReport:
    def _make_agg(self, sli=None, rates=None, alertas=None):
        agg = MagicMock()
        agg.build_sli_diario.return_value = sli if sli is not None else []
        agg.build_fallback_rate_por_skill.return_value = rates if rates is not None else []
        agg.build_alertas_ativos.return_value = alertas if alertas is not None else []
        return agg

    def test_empty_data_else_branches(self):
        """All aggregator methods return empty → else branches executed."""
        storage = MagicMock()
        agg = self._make_agg()
        with (
            patch(_STORAGE_PATH, return_value=storage),
            patch(
                "concilium.infrastructure.observability.gold_aggregator.GoldAggregator",
                return_value=agg,
            ),
        ):
            result = runner.invoke(observability_app, ["report"])
        assert result.exit_code == 0
        assert "SLI: sem dados de traces" in result.output
        assert "Fallback rate: sem dados de logs" in result.output
        assert "Nenhum alerta ativo" in result.output

    def test_non_empty_sli_and_rates(self):
        """Non-empty sli/rates → tables are printed."""
        storage = MagicMock()
        sli_row = {
            "date": "2026-06-23",
            "skill_id": "sk-01",
            "p50_ms": 120,
            "p95_ms": 300,
            "p99_ms": 500,
            "n_spans": 42,
        }
        rate_row = {
            "date": "2026-06-23",
            "skill_id": "sk-01",
            "n_fallbacks": 3,
            "n_total": 10,
            "fallback_rate": 0.3,
        }
        agg = self._make_agg(sli=[sli_row], rates=[rate_row])
        with (
            patch(_STORAGE_PATH, return_value=storage),
            patch(
                "concilium.infrastructure.observability.gold_aggregator.GoldAggregator",
                return_value=agg,
            ),
        ):
            result = runner.invoke(observability_app, ["report"])
        assert result.exit_code == 0
        assert "sk-01" in result.output
        assert "SLI" in result.output
        assert "Fallback Rate" in result.output
        # no "sem dados" messages
        assert "SLI: sem dados" not in result.output
        assert "Fallback rate: sem dados" not in result.output

    def test_alertas_ativos(self):
        """Non-empty alertas → alert count and tipo printed."""
        storage = MagicMock()
        alertas = [
            {"tipo": "p99_alto", "skill_id": "sk-02", "date": "2026-06-23"},
            {"tipo": "fallback_elevado", "skill_id": "sk-03", "date": "2026-06-23"},
        ]
        agg = self._make_agg(alertas=alertas)
        with (
            patch(_STORAGE_PATH, return_value=storage),
            patch(
                "concilium.infrastructure.observability.gold_aggregator.GoldAggregator",
                return_value=agg,
            ),
        ):
            result = runner.invoke(observability_app, ["report"])
        assert result.exit_code == 0
        assert "2 alerta(s)" in result.output
        assert "p99_alto" in result.output
        assert "fallback_elevado" in result.output
        assert "Nenhum alerta ativo" not in result.output


# ---------------------------------------------------------------------------
# run_cycle
# ---------------------------------------------------------------------------


class TestRunCycle:
    def _make_scheduler(self, silver_ran=True, gold_ran=True, silver_records=10):
        scheduler = MagicMock()
        scheduler.run_cycle.return_value = {
            "silver_ran": silver_ran,
            "gold_ran": gold_ran,
            "silver_records": silver_records,
        }
        return scheduler

    def test_cycle_both_ran(self):
        """silver_ran=True and gold_ran=True → both show ✓."""
        storage = MagicMock()
        scheduler = self._make_scheduler(silver_ran=True, gold_ran=True, silver_records=7)
        with (
            patch(_STORAGE_PATH, return_value=storage),
            patch(
                "concilium.infrastructure.observability.pipeline.ObservabilityScheduler",
                return_value=scheduler,
            ),
        ):
            result = runner.invoke(observability_app, ["cycle"])
        assert result.exit_code == 0
        assert "7 records" in result.output

    def test_cycle_silver_ran_gold_not(self):
        """silver_ran=True and gold_ran=False → gold shows — (dash)."""
        storage = MagicMock()
        scheduler = self._make_scheduler(silver_ran=True, gold_ran=False, silver_records=3)
        with (
            patch(_STORAGE_PATH, return_value=storage),
            patch(
                "concilium.infrastructure.observability.pipeline.ObservabilityScheduler",
                return_value=scheduler,
            ),
        ):
            result = runner.invoke(observability_app, ["cycle"])
        assert result.exit_code == 0
        assert "3 records" in result.output
        assert "Ciclo de observabilidade" in result.output

    def test_cycle_neither_ran(self):
        """silver_ran=False and gold_ran=False → output still has cycle header."""
        storage = MagicMock()
        scheduler = self._make_scheduler(silver_ran=False, gold_ran=False, silver_records=0)
        with (
            patch(_STORAGE_PATH, return_value=storage),
            patch(
                "concilium.infrastructure.observability.pipeline.ObservabilityScheduler",
                return_value=scheduler,
            ),
        ):
            result = runner.invoke(observability_app, ["cycle"])
        assert result.exit_code == 0
        assert "Ciclo de observabilidade" in result.output


# ---------------------------------------------------------------------------
# show_cross_domain
# ---------------------------------------------------------------------------


class TestShowCrossDomain:
    def _patch_cross_domain(self, rows, storage, cfg=None):
        builder = MagicMock()
        builder.build.return_value = rows
        builder.write.return_value = None

        if cfg is None:
            cfg = SimpleNamespace(benchmark_projects_root=None, root=".")

        return builder, cfg

    def test_no_rows_early_return(self):
        """builder.build() returns [] → prints dim message and returns without write."""
        storage = MagicMock()
        builder, cfg = self._patch_cross_domain(rows=[], storage=storage)

        with (
            patch(_STORAGE_PATH, return_value=storage),
            patch(
                "concilium.infrastructure.settings.get_storage",
                return_value=cfg,
            ),
            patch(
                "concilium.infrastructure.observability.cross_domain.CrossDomainBuilder",
                return_value=builder,
            ),
            patch(
                "concilium.infrastructure.observability.cross_domain.default_canonical_provider",
                return_value=MagicMock(),
            ),
        ):
            result = runner.invoke(observability_app, ["cross-domain"])
        assert result.exit_code == 0
        assert "sem logs Silver com project_id" in result.output
        builder.write.assert_not_called()

    def test_with_rows_table_and_write(self):
        """builder.build() returns rows → table printed and builder.write() called."""
        storage = MagicMock()
        rows = [
            {
                "project_id": "proj-001",
                "n_fallbacks": 5,
                "n_total": 20,
                "fallback_rate": 0.25,
                "custo_direto": 100000.0,
                "margem_pct": 12.5,
            }
        ]
        builder, cfg = self._patch_cross_domain(rows=rows, storage=storage)

        with (
            patch(_STORAGE_PATH, return_value=storage),
            patch(
                "concilium.infrastructure.settings.get_storage",
                return_value=cfg,
            ),
            patch(
                "concilium.infrastructure.observability.cross_domain.CrossDomainBuilder",
                return_value=builder,
            ),
            patch(
                "concilium.infrastructure.observability.cross_domain.default_canonical_provider",
                return_value=MagicMock(),
            ),
        ):
            result = runner.invoke(observability_app, ["cross-domain"])
        assert result.exit_code == 0
        assert "proj-001" in result.output
        assert "cross_domain.json" in result.output
        builder.write.assert_called_once()
        # no "sem logs" message
        assert "sem logs Silver" not in result.output

    def test_with_rows_benchmark_root_from_cfg(self):
        """When cfg.benchmark_projects_root is set, it is used directly."""
        storage = MagicMock()
        rows = [
            {
                "project_id": "proj-X",
                "n_fallbacks": 0,
                "n_total": 5,
                "fallback_rate": 0.0,
                "custo_direto": 0.0,
                "margem_pct": 0.0,
            }
        ]
        cfg = SimpleNamespace(benchmark_projects_root="/data/benchmarks", root="/data")
        builder, _ = self._patch_cross_domain(rows=rows, storage=storage, cfg=cfg)

        canonical_provider_mock = MagicMock()
        with (
            patch(_STORAGE_PATH, return_value=storage),
            patch(
                "concilium.infrastructure.settings.get_storage",
                return_value=cfg,
            ),
            patch(
                "concilium.infrastructure.observability.cross_domain.CrossDomainBuilder",
                return_value=builder,
            ),
            patch(
                "concilium.infrastructure.observability.cross_domain.default_canonical_provider",
                return_value=canonical_provider_mock,
            ),
        ):
            result = runner.invoke(observability_app, ["cross-domain"])
        assert result.exit_code == 0
        assert "proj-X" in result.output
