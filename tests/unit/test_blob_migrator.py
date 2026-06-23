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
        from unittest.mock import patch

        from typer.testing import CliRunner

        from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage
        from concilium.presentation.cli.commands_blob import blob_app

        src = LocalBlobStorage(tmp_path / "src")
        src.gravar_blob("test/file.json", b"{}")
        tgt = LocalBlobStorage(tmp_path / "tgt")

        with (
            patch("concilium.presentation.cli.commands_blob._make_source_storage", return_value=src),
            patch("concilium.presentation.cli.commands_blob._make_target_storage", return_value=tgt),
        ):
            runner = CliRunner()
            result = runner.invoke(blob_app, ["migrate", "--dry-run"])

        assert result.exit_code == 0
        assert not tgt.blob_existe("test/file.json")
