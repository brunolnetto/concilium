"""TDD — Item 9: BlobMigrator — migração entre blob storages.

Cobre:
  - migrate() copia todos os blobs de source para target
  - dry_run=True lista blobs sem copiar
  - MigrationResult contém stats corretas
  - prefix filtra quais blobs migrar
  - blobs já existentes no target podem ser skipped (--no-overwrite)
  - progress callback é invocado por blob
  - CLI: concilium blob migrate
"""

from __future__ import annotations

import pytest


@pytest.fixture
def source(tmp_path):
    from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage

    s = LocalBlobStorage(tmp_path / "source")
    s.gravar_blob("projetos/proj-a/v1/canonical.json", b'{"projeto": "A"}')
    s.gravar_blob("projetos/proj-a/meta.json", b'{"id": "proj-a"}')
    s.gravar_blob("projetos/proj-b/v1/canonical.json", b'{"projeto": "B"}')
    s.gravar_blob("misc/audit.jsonl", b'{"run": 1}')
    return s


@pytest.fixture
def target(tmp_path):
    from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage

    return LocalBlobStorage(tmp_path / "target")


# ─────────────────────────────────────────────────────────────────────────────
# MigrationResult
# ─────────────────────────────────────────────────────────────────────────────


class TestMigrationResult:
    def test_result_has_required_fields(self, source, target):
        from concilium.infrastructure.adapters.blob_storage.migrator import BlobMigrator

        result = BlobMigrator().migrate(source, target)
        assert hasattr(result, "total_blobs")
        assert hasattr(result, "copied")
        assert hasattr(result, "skipped")
        assert hasattr(result, "failed")
        assert hasattr(result, "dry_run")

    def test_total_blobs_correct(self, source, target):
        from concilium.infrastructure.adapters.blob_storage.migrator import BlobMigrator

        result = BlobMigrator().migrate(source, target)
        assert result.total_blobs == 4  # 4 blobs seeded

    def test_copied_equals_total_on_empty_target(self, source, target):
        from concilium.infrastructure.adapters.blob_storage.migrator import BlobMigrator

        result = BlobMigrator().migrate(source, target)
        assert result.copied == 4
        assert result.failed == 0


# ─────────────────────────────────────────────────────────────────────────────
# Core migration behavior
# ─────────────────────────────────────────────────────────────────────────────


class TestBlobMigratorCore:
    def test_blobs_exist_in_target_after_migrate(self, source, target):
        from concilium.infrastructure.adapters.blob_storage.migrator import BlobMigrator

        BlobMigrator().migrate(source, target)
        assert target.blob_existe("projetos/proj-a/v1/canonical.json")
        assert target.blob_existe("projetos/proj-b/v1/canonical.json")
        assert target.blob_existe("misc/audit.jsonl")

    def test_content_preserved(self, source, target):
        from concilium.infrastructure.adapters.blob_storage.migrator import BlobMigrator

        BlobMigrator().migrate(source, target)
        assert target.ler_blob("projetos/proj-a/meta.json") == b'{"id": "proj-a"}'

    def test_migrate_with_prefix_only_copies_matching_blobs(self, source, target):
        from concilium.infrastructure.adapters.blob_storage.migrator import BlobMigrator

        result = BlobMigrator().migrate(source, target, prefix="projetos/proj-a/")
        assert result.total_blobs == 2
        assert target.blob_existe("projetos/proj-a/v1/canonical.json")
        assert not target.blob_existe("misc/audit.jsonl")

    def test_dry_run_copies_nothing(self, source, target):
        from concilium.infrastructure.adapters.blob_storage.migrator import BlobMigrator

        result = BlobMigrator().migrate(source, target, dry_run=True)
        assert result.dry_run is True
        assert result.copied == 0
        assert not target.blob_existe("projetos/proj-a/meta.json")

    def test_dry_run_still_counts_blobs(self, source, target):
        from concilium.infrastructure.adapters.blob_storage.migrator import BlobMigrator

        result = BlobMigrator().migrate(source, target, dry_run=True)
        assert result.total_blobs == 4

    def test_skip_existing_blobs_by_default_overwrite(self, source, target):
        """Por padrão (overwrite=True), reescreve blobs existentes."""
        from concilium.infrastructure.adapters.blob_storage.migrator import BlobMigrator

        target.gravar_blob("projetos/proj-a/meta.json", b'{"id": "antigo"}')
        BlobMigrator().migrate(source, target, overwrite=True)
        assert target.ler_blob("projetos/proj-a/meta.json") == b'{"id": "proj-a"}'

    def test_no_overwrite_skips_existing_blobs(self, source, target):
        """overwrite=False pula blobs já existentes no target."""
        from concilium.infrastructure.adapters.blob_storage.migrator import BlobMigrator

        target.gravar_blob("projetos/proj-a/meta.json", b'{"id": "antigo"}')
        result = BlobMigrator().migrate(source, target, overwrite=False)
        assert target.ler_blob("projetos/proj-a/meta.json") == b'{"id": "antigo"}'
        assert result.skipped >= 1

    def test_progress_callback_called_for_each_blob(self, source, target):
        from concilium.infrastructure.adapters.blob_storage.migrator import BlobMigrator

        calls = []
        BlobMigrator().migrate(source, target, on_progress=lambda path, n, total: calls.append(path))
        assert len(calls) == 4

    def test_idempotent_second_run(self, source, target):
        """Executar migrate duas vezes produz resultado consistente."""
        from concilium.infrastructure.adapters.blob_storage.migrator import BlobMigrator

        migrator = BlobMigrator()
        migrator.migrate(source, target)
        result2 = migrator.migrate(source, target)
        assert result2.failed == 0
        assert target.blob_existe("projetos/proj-a/v1/canonical.json")


# ─────────────────────────────────────────────────────────────────────────────
# Parallel migration (workers > 1) — _migrate_parallel / _copy_one with lock
# ─────────────────────────────────────────────────────────────────────────────


class TestBlobMigratorParallel:
    def test_parallel_workers_copies_all_blobs(self, source, target):
        from concilium.infrastructure.adapters.blob_storage.migrator import BlobMigrator

        migrator = BlobMigrator(workers=4)
        result = migrator.migrate(source, target)

        assert result.copied == 4
        assert result.failed == 0
        assert target.blob_existe("projetos/proj-a/v1/canonical.json")
        assert target.blob_existe("misc/audit.jsonl")

    def test_parallel_workers_progress_callback_invoked_for_each_blob(self, source, target):
        from concilium.infrastructure.adapters.blob_storage.migrator import BlobMigrator

        calls = []
        BlobMigrator(workers=4).migrate(source, target, on_progress=lambda path, n, total: calls.append(path))
        assert len(calls) == 4

    def test_parallel_workers_skip_existing_without_overwrite(self, source, target):
        """Exercises _copy_one's lock-protected skip branch under real threads."""
        from concilium.infrastructure.adapters.blob_storage.migrator import BlobMigrator

        # Pre-populate target with one of the blobs so it gets skipped.
        target.gravar_blob("misc/audit.jsonl", b'{"run": 1}')

        result = BlobMigrator(workers=4).migrate(source, target, overwrite=False)

        assert result.skipped == 1
        assert result.copied == 3
        assert result.failed == 0

    def test_parallel_worker_exception_is_logged_not_raised(self, source, target, caplog):
        """A blob that fails to copy is counted as failed and logged, but the
        worker exception path (`if exc:` in _migrate_parallel) doesn't crash
        the overall migration."""
        import logging

        from concilium.infrastructure.adapters.blob_storage.migrator import BlobMigrator

        original_ler_blob = source.ler_blob

        def flaky_ler_blob(path):
            if path == "misc/audit.jsonl":
                raise OSError("simulated read failure")
            return original_ler_blob(path)

        source.ler_blob = flaky_ler_blob

        with caplog.at_level(logging.ERROR):
            result = BlobMigrator(workers=4).migrate(source, target)

        assert result.failed == 1
        assert result.copied == 3

    def test_parallel_unexpected_worker_exception_is_logged(self, source, target, caplog):
        """An exception escaping the worker task itself (outside `_copy_one`'s
        own try/except — e.g. a broken on_progress callback) is caught by
        `_migrate_parallel`'s `if exc:` branch and logged, not raised."""
        import logging

        from concilium.infrastructure.adapters.blob_storage.migrator import BlobMigrator

        def broken_on_progress(path, n, total):
            raise RuntimeError("boom in progress callback")

        with caplog.at_level(logging.ERROR):
            result = BlobMigrator(workers=4).migrate(source, target, on_progress=broken_on_progress)

        # The copy itself succeeds; the failure is in the progress callback,
        # so it's reported via the "unexpected worker" error log, not `failed`.
        assert result.failed == 0
        assert any("Falha inesperada no worker" in rec.message for rec in caplog.records)


# ─────────────────────────────────────────────────────────────────────────────
# CLI command
# ─────────────────────────────────────────────────────────────────────────────


class TestBlobMigrateCLI:
    def test_cli_migrate_command_exists(self, tmp_path):
        from typer.testing import CliRunner

        from concilium.presentation.cli.commands_blob import blob_app

        runner = CliRunner()
        result = runner.invoke(blob_app, ["--help"])
        assert result.exit_code == 0
        assert "migrate" in result.output

    def test_cli_migrate_dry_run(self, tmp_path):
        from typer.testing import CliRunner

        from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage
        from concilium.presentation.cli.commands_blob import blob_app

        src_dir = tmp_path / "src"
        tgt_dir = tmp_path / "tgt"
        src_dir.mkdir()
        tgt_dir.mkdir()
        src = LocalBlobStorage(src_dir)
        src.gravar_blob("test/file.json", b"{}")

        runner = CliRunner()
        result = runner.invoke(
            blob_app,
            [
                "migrate",
                "--source-backend",
                "filesystem",
                "--source-root",
                str(src_dir),
                "--target-backend",
                "filesystem",
                "--target-root",
                str(tgt_dir),
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        tgt = LocalBlobStorage(tgt_dir)
        assert not tgt.blob_existe("test/file.json")
