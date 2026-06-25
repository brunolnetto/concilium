"""Coverage tests for commands_blob — migrate and status commands.

Covers lines: 24, 26, 37, 39, 90-92, 97, 105-115
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from concilium.presentation.cli.commands_blob import blob_app

runner = CliRunner()

MODULE = "concilium.presentation.cli.commands_blob"
STORE_FACTORY = "concilium.infrastructure.storage.store_factory"
MIGRATOR_MODULE = "concilium.infrastructure.adapters.blob_storage.migrator"


def _make_result(*, total_blobs=2, copied=2, skipped=0, failed=0, success=True):
    return SimpleNamespace(
        total_blobs=total_blobs,
        copied=copied,
        skipped=skipped,
        failed=failed,
        success=success,
    )


# ---------------------------------------------------------------------------
# migrate
# ---------------------------------------------------------------------------


class TestMigrateNormalRun:
    """Normal run: copied=2, skipped=0, failed=0 → exit 0, prints summary."""

    def test_exit_code_zero(self):
        mock_storage = MagicMock()
        mock_migrator_instance = MagicMock()
        mock_migrator_instance.migrate.return_value = _make_result()
        mock_migrator_cls = MagicMock(return_value=mock_migrator_instance)

        with (
            patch(f"{STORE_FACTORY}.build_blob_storage", return_value=mock_storage),
            patch(
                f"{MIGRATOR_MODULE}.BlobMigrator",
                mock_migrator_cls,
            ),
        ):
            result = runner.invoke(blob_app, ["migrate"])

        assert result.exit_code == 0

    def test_total_blobs_in_output(self):
        mock_storage = MagicMock()
        mock_migrator_instance = MagicMock()
        mock_migrator_instance.migrate.return_value = _make_result(total_blobs=2)
        mock_migrator_cls = MagicMock(return_value=mock_migrator_instance)

        with (
            patch(f"{STORE_FACTORY}.build_blob_storage", return_value=mock_storage),
            patch(
                f"{MIGRATOR_MODULE}.BlobMigrator",
                mock_migrator_cls,
            ),
        ):
            result = runner.invoke(blob_app, ["migrate"])

        assert "2" in result.output

    def test_copied_line_present(self):
        mock_storage = MagicMock()
        mock_migrator_instance = MagicMock()
        mock_migrator_instance.migrate.return_value = _make_result(copied=2)
        mock_migrator_cls = MagicMock(return_value=mock_migrator_instance)

        with (
            patch(f"{STORE_FACTORY}.build_blob_storage", return_value=mock_storage),
            patch(
                f"{MIGRATOR_MODULE}.BlobMigrator",
                mock_migrator_cls,
            ),
        ):
            result = runner.invoke(blob_app, ["migrate"])

        assert "Copiados" in result.output

    def test_skipped_line_present(self):
        mock_storage = MagicMock()
        mock_migrator_instance = MagicMock()
        mock_migrator_instance.migrate.return_value = _make_result()
        mock_migrator_cls = MagicMock(return_value=mock_migrator_instance)

        with (
            patch(f"{STORE_FACTORY}.build_blob_storage", return_value=mock_storage),
            patch(
                f"{MIGRATOR_MODULE}.BlobMigrator",
                mock_migrator_cls,
            ),
        ):
            result = runner.invoke(blob_app, ["migrate"])

        assert "Pulados" in result.output

    def test_falhas_line_present(self):
        mock_storage = MagicMock()
        mock_migrator_instance = MagicMock()
        mock_migrator_instance.migrate.return_value = _make_result()
        mock_migrator_cls = MagicMock(return_value=mock_migrator_instance)

        with (
            patch(f"{STORE_FACTORY}.build_blob_storage", return_value=mock_storage),
            patch(
                f"{MIGRATOR_MODULE}.BlobMigrator",
                mock_migrator_cls,
            ),
        ):
            result = runner.invoke(blob_app, ["migrate"])

        assert "Falhas" in result.output

    def test_build_blob_storage_called_twice(self):
        """_make_source_storage and _make_target_storage each call build_blob_storage."""
        mock_storage = MagicMock()
        mock_migrator_instance = MagicMock()
        mock_migrator_instance.migrate.return_value = _make_result()
        mock_migrator_cls = MagicMock(return_value=mock_migrator_instance)

        with (
            patch(f"{STORE_FACTORY}.build_blob_storage", return_value=mock_storage) as mock_build,
            patch(
                f"{MIGRATOR_MODULE}.BlobMigrator",
                mock_migrator_cls,
            ),
        ):
            runner.invoke(blob_app, ["migrate"])

        assert mock_build.call_count == 2


class TestMigrateDryRun:
    """dry_run=True: prints dry-run message, no Copiados/Pulados/Falhas lines."""

    def test_dry_run_message_present(self):
        mock_storage = MagicMock()
        mock_migrator_instance = MagicMock()
        mock_migrator_instance.migrate.return_value = _make_result(total_blobs=5)
        mock_migrator_cls = MagicMock(return_value=mock_migrator_instance)

        with (
            patch(f"{STORE_FACTORY}.build_blob_storage", return_value=mock_storage),
            patch(
                f"{MIGRATOR_MODULE}.BlobMigrator",
                mock_migrator_cls,
            ),
        ):
            result = runner.invoke(blob_app, ["migrate", "--dry-run"])

        assert "dry-run" in result.output.lower() or "dry_run" in result.output.lower() or "Modo dry" in result.output

    def test_no_copiados_line(self):
        mock_storage = MagicMock()
        mock_migrator_instance = MagicMock()
        mock_migrator_instance.migrate.return_value = _make_result()
        mock_migrator_cls = MagicMock(return_value=mock_migrator_instance)

        with (
            patch(f"{STORE_FACTORY}.build_blob_storage", return_value=mock_storage),
            patch(
                f"{MIGRATOR_MODULE}.BlobMigrator",
                mock_migrator_cls,
            ),
        ):
            result = runner.invoke(blob_app, ["migrate", "--dry-run"])

        assert "Copiados" not in result.output

    def test_no_pulados_line(self):
        mock_storage = MagicMock()
        mock_migrator_instance = MagicMock()
        mock_migrator_instance.migrate.return_value = _make_result()
        mock_migrator_cls = MagicMock(return_value=mock_migrator_instance)

        with (
            patch(f"{STORE_FACTORY}.build_blob_storage", return_value=mock_storage),
            patch(
                f"{MIGRATOR_MODULE}.BlobMigrator",
                mock_migrator_cls,
            ),
        ):
            result = runner.invoke(blob_app, ["migrate", "--dry-run"])

        assert "Pulados" not in result.output

    def test_no_falhas_line(self):
        mock_storage = MagicMock()
        mock_migrator_instance = MagicMock()
        mock_migrator_instance.migrate.return_value = _make_result()
        mock_migrator_cls = MagicMock(return_value=mock_migrator_instance)

        with (
            patch(f"{STORE_FACTORY}.build_blob_storage", return_value=mock_storage),
            patch(
                f"{MIGRATOR_MODULE}.BlobMigrator",
                mock_migrator_cls,
            ),
        ):
            result = runner.invoke(blob_app, ["migrate", "--dry-run"])

        assert "Falhas" not in result.output

    def test_exit_code_zero(self):
        mock_storage = MagicMock()
        mock_migrator_instance = MagicMock()
        mock_migrator_instance.migrate.return_value = _make_result()
        mock_migrator_cls = MagicMock(return_value=mock_migrator_instance)

        with (
            patch(f"{STORE_FACTORY}.build_blob_storage", return_value=mock_storage),
            patch(
                f"{MIGRATOR_MODULE}.BlobMigrator",
                mock_migrator_cls,
            ),
        ):
            result = runner.invoke(blob_app, ["migrate", "--dry-run"])

        assert result.exit_code == 0


class TestMigrateWithFailures:
    """failed=1 → exit code 1."""

    def test_exit_code_one(self):
        mock_storage = MagicMock()
        mock_migrator_instance = MagicMock()
        mock_migrator_instance.migrate.return_value = _make_result(
            total_blobs=3, copied=2, skipped=0, failed=1, success=False
        )
        mock_migrator_cls = MagicMock(return_value=mock_migrator_instance)

        with (
            patch(f"{STORE_FACTORY}.build_blob_storage", return_value=mock_storage),
            patch(
                f"{MIGRATOR_MODULE}.BlobMigrator",
                mock_migrator_cls,
            ),
        ):
            result = runner.invoke(blob_app, ["migrate"])

        assert result.exit_code == 1

    def test_falhas_count_in_output(self):
        mock_storage = MagicMock()
        mock_migrator_instance = MagicMock()
        mock_migrator_instance.migrate.return_value = _make_result(
            total_blobs=3, copied=2, skipped=0, failed=1, success=False
        )
        mock_migrator_cls = MagicMock(return_value=mock_migrator_instance)

        with (
            patch(f"{STORE_FACTORY}.build_blob_storage", return_value=mock_storage),
            patch(
                f"{MIGRATOR_MODULE}.BlobMigrator",
                mock_migrator_cls,
            ),
        ):
            result = runner.invoke(blob_app, ["migrate"])

        assert "Falhas" in result.output


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


class TestStatusNoBlobs:
    """No blobs → prints total 0, no blob list."""

    def test_exit_code_zero(self):
        mock_storage = MagicMock()
        mock_storage.listar_blobs.return_value = []

        with patch(f"{STORE_FACTORY}.build_blob_storage", return_value=mock_storage):
            result = runner.invoke(blob_app, ["status"])

        assert result.exit_code == 0

    def test_total_zero_in_output(self):
        mock_storage = MagicMock()
        mock_storage.listar_blobs.return_value = []

        with patch(f"{STORE_FACTORY}.build_blob_storage", return_value=mock_storage):
            result = runner.invoke(blob_app, ["status"])

        assert "0" in result.output

    def test_no_primeiros_header(self):
        mock_storage = MagicMock()
        mock_storage.listar_blobs.return_value = []

        with patch(f"{STORE_FACTORY}.build_blob_storage", return_value=mock_storage):
            result = runner.invoke(blob_app, ["status"])

        assert "Primeiros" not in result.output

    def test_backend_name_in_output(self):
        mock_storage = MagicMock()
        mock_storage.listar_blobs.return_value = []

        with patch(f"{STORE_FACTORY}.build_blob_storage", return_value=mock_storage):
            result = runner.invoke(blob_app, ["status"])

        assert "Backend" in result.output

    def test_build_blob_storage_called_once(self):
        mock_storage = MagicMock()
        mock_storage.listar_blobs.return_value = []

        with patch(f"{STORE_FACTORY}.build_blob_storage", return_value=mock_storage) as mock_build:
            runner.invoke(blob_app, ["status"])

        assert mock_build.call_count == 1


class TestStatusFiveBlobs:
    """5 blobs → prints each blob name."""

    def _blobs(self):
        return [f"blob/file_{i:02d}.dat" for i in range(5)]

    def test_exit_code_zero(self):
        mock_storage = MagicMock()
        mock_storage.listar_blobs.return_value = self._blobs()

        with patch(f"{STORE_FACTORY}.build_blob_storage", return_value=mock_storage):
            result = runner.invoke(blob_app, ["status"])

        assert result.exit_code == 0

    def test_total_five_in_output(self):
        mock_storage = MagicMock()
        mock_storage.listar_blobs.return_value = self._blobs()

        with patch(f"{STORE_FACTORY}.build_blob_storage", return_value=mock_storage):
            result = runner.invoke(blob_app, ["status"])

        assert "5" in result.output

    def test_each_blob_listed(self):
        blobs = self._blobs()
        mock_storage = MagicMock()
        mock_storage.listar_blobs.return_value = blobs

        with patch(f"{STORE_FACTORY}.build_blob_storage", return_value=mock_storage):
            result = runner.invoke(blob_app, ["status"])

        for b in blobs:
            assert b in result.output

    def test_no_truncation_message(self):
        mock_storage = MagicMock()
        mock_storage.listar_blobs.return_value = self._blobs()

        with patch(f"{STORE_FACTORY}.build_blob_storage", return_value=mock_storage):
            result = runner.invoke(blob_app, ["status"])

        assert "e mais" not in result.output

    def test_primeiros_header_shown(self):
        mock_storage = MagicMock()
        mock_storage.listar_blobs.return_value = self._blobs()

        with patch(f"{STORE_FACTORY}.build_blob_storage", return_value=mock_storage):
            result = runner.invoke(blob_app, ["status"])

        assert "Primeiros" in result.output


class TestStatusTwentyFiveBlobs:
    """25 blobs → first 20 printed, truncation message shows 'e mais 5'."""

    def _blobs(self):
        return [f"blob/file_{i:03d}.dat" for i in range(25)]

    def test_exit_code_zero(self):
        mock_storage = MagicMock()
        mock_storage.listar_blobs.return_value = self._blobs()

        with patch(f"{STORE_FACTORY}.build_blob_storage", return_value=mock_storage):
            result = runner.invoke(blob_app, ["status"])

        assert result.exit_code == 0

    def test_total_twentyfive_in_output(self):
        mock_storage = MagicMock()
        mock_storage.listar_blobs.return_value = self._blobs()

        with patch(f"{STORE_FACTORY}.build_blob_storage", return_value=mock_storage):
            result = runner.invoke(blob_app, ["status"])

        assert "25" in result.output

    def test_truncation_message_e_mais_5(self):
        mock_storage = MagicMock()
        mock_storage.listar_blobs.return_value = self._blobs()

        with patch(f"{STORE_FACTORY}.build_blob_storage", return_value=mock_storage):
            result = runner.invoke(blob_app, ["status"])

        assert "e mais 5" in result.output

    def test_first_20_blobs_listed(self):
        blobs = sorted(self._blobs())
        mock_storage = MagicMock()
        mock_storage.listar_blobs.return_value = self._blobs()

        with patch(f"{STORE_FACTORY}.build_blob_storage", return_value=mock_storage):
            result = runner.invoke(blob_app, ["status"])

        for b in blobs[:20]:
            assert b in result.output

    def test_21st_blob_not_listed_individually(self):
        blobs = sorted(self._blobs())
        mock_storage = MagicMock()
        mock_storage.listar_blobs.return_value = self._blobs()

        with patch(f"{STORE_FACTORY}.build_blob_storage", return_value=mock_storage):
            result = runner.invoke(blob_app, ["status"])

        # The 21st blob (index 20) should not appear as an individual line
        # (it is counted in "e mais 5" instead)
        blob_21 = blobs[20]
        # Count occurrences: it should not appear as an individual entry
        # We verify the truncation message is present (already tested above),
        # and the blob itself is NOT individually printed.
        individual_lines = [line.strip() for line in result.output.splitlines() if line.strip() == blob_21]
        assert len(individual_lines) == 0

    def test_primeiros_header_shown(self):
        mock_storage = MagicMock()
        mock_storage.listar_blobs.return_value = self._blobs()

        with patch(f"{STORE_FACTORY}.build_blob_storage", return_value=mock_storage):
            result = runner.invoke(blob_app, ["status"])

        assert "Primeiros" in result.output
