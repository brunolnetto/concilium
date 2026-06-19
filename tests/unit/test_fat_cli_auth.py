"""Tests for concilium.presentation.cli.commands_auth — covering missing lines.

Strategy: use typer.testing.CliRunner to invoke the `app` object directly.
Patch `concilium.infrastructure.auth.auth_store.get_auth_store` at the module
level so every lazy import inside the command functions picks up the mock.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import typer
from typer.testing import CliRunner

from concilium.presentation.cli.commands_auth import app

runner = CliRunner()

PATCH_GET_AUTH_STORE = "concilium.infrastructure.auth.auth_store.get_auth_store"
PATCH_GET_STORAGE = "concilium.infrastructure.settings.get_storage"


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------


def _make_client_record(
    client_id="alice",
    roles=None,
    active=True,
    created_at="2026-01-01T00:00:00+00:00",
    notes="",
):
    rec = SimpleNamespace(
        client_id=client_id,
        roles=roles if roles is not None else ["operator"],
        active=active,
        created_at=created_at,
        notes=notes,
    )
    return rec


def _make_device_record(
    device_id="macbook-alice",
    client_id="alice",
    scopes=None,
    issued_at="2026-01-01T00:00:00+00:00",
    expires_at="2026-04-01T00:00:00+00:00",
    last_used_at=None,
):
    rec = SimpleNamespace(
        device_id=device_id,
        client_id=client_id,
        scopes=scopes if scopes is not None else ["mcp:read"],
        issued_at=issued_at,
        expires_at=expires_at,
        last_used_at=last_used_at,
    )
    return rec


def _make_device_code_record(
    code="RCODE-ABCDEF1234567890",
    client_id="alice",
    device_id="macbook-alice",
    roles=None,
    expires_at="2026-01-01T01:00:00+00:00",
):
    rec = SimpleNamespace(
        code=code,
        client_id=client_id,
        device_id=device_id,
        roles=roles if roles is not None else ["operator"],
        expires_at=expires_at,
    )
    return rec


def _make_store(**kwargs) -> MagicMock:
    """Return a MagicMock AuthStore with sensible defaults."""
    store = MagicMock()
    store.add_client.return_value = kwargs.get("add_client_return", _make_client_record())
    store.list_clients.return_value = kwargs.get("list_clients_return", [])
    store.remove_client.return_value = kwargs.get("remove_client_return", True)
    store.list_devices.return_value = kwargs.get("list_devices_return", [])
    store.revoke_device.return_value = kwargs.get("revoke_device_return", 0)
    store.create_device_code.return_value = kwargs.get("create_device_code_return", _make_device_code_record())
    return store


# ===========================================================================
# add-user
# ===========================================================================


class TestAddUser:
    def test_add_user_explicit_secret_no_secret_printed(self):
        """(1) explicit --secret → secret block NOT printed, success message shown."""
        store = _make_store(add_client_return=_make_client_record())

        with patch(PATCH_GET_AUTH_STORE, return_value=store):
            result = runner.invoke(
                app,
                ["add-user", "--id", "alice", "--secret", "mysecret123"],
            )

        assert result.exit_code == 0, result.output
        assert "alice" in result.output
        # The "Secret gerado" block must NOT appear when secret is explicit
        assert "Secret gerado" not in result.output
        assert "guarde agora" not in result.output

    def test_add_user_auto_generated_secret_prints_secret_block(self):
        """(2) no --secret → secret is auto-generated and printed."""
        store = _make_store(add_client_return=_make_client_record())

        with patch(PATCH_GET_AUTH_STORE, return_value=store):
            result = runner.invoke(
                app,
                ["add-user", "--id", "alice"],
            )

        assert result.exit_code == 0, result.output
        assert "Secret gerado" in result.output
        assert "guarde agora" in result.output

    def test_add_user_value_error_exits_1_with_red_error(self):
        """(3) store raises ValueError → exit code 1 and error message shown."""
        store = _make_store()
        store.add_client.side_effect = ValueError("Client 'alice' already exists.")

        with patch(PATCH_GET_AUTH_STORE, return_value=store):
            result = runner.invoke(
                app,
                ["add-user", "--id", "alice", "--secret", "x"],
            )

        assert result.exit_code == 1
        assert "Erro" in result.output or "already exists" in result.output

    def test_add_user_role_passed_to_store(self):
        """Role is passed correctly to add_client."""
        store = _make_store(add_client_return=_make_client_record(roles=["admin"]))

        with patch(PATCH_GET_AUTH_STORE, return_value=store):
            result = runner.invoke(
                app,
                ["add-user", "--id", "alice", "--secret", "s", "--role", "admin"],
            )

        assert result.exit_code == 0, result.output
        call_args = store.add_client.call_args
        # roles arg is the third positional arg
        assert "admin" in call_args[0][2] or "admin" in str(call_args)

    def test_add_user_notes_passed_to_store(self):
        """Notes are passed through to store.add_client."""
        store = _make_store(add_client_return=_make_client_record(notes="CI service"))

        with patch(PATCH_GET_AUTH_STORE, return_value=store):
            result = runner.invoke(
                app,
                ["add-user", "--id", "ci", "--secret", "s", "--notes", "CI service"],
            )

        assert result.exit_code == 0, result.output
        call_args = store.add_client.call_args
        assert "CI service" in str(call_args)


# ===========================================================================
# list-users
# ===========================================================================


class TestListUsers:
    def test_list_users_with_records_renders_table(self):
        """(4) records present → table output with client IDs."""
        records = [
            _make_client_record("alice", active=True, notes="dev"),
            _make_client_record("bob", roles=["admin"], active=False, notes=""),
        ]
        store = _make_store(list_clients_return=records)

        with patch(PATCH_GET_AUTH_STORE, return_value=store):
            result = runner.invoke(app, ["list-users"])

        assert result.exit_code == 0, result.output
        assert "alice" in result.output
        assert "bob" in result.output

    def test_list_users_empty_prints_dim_message(self):
        """(5) empty list → dim message shown."""
        store = _make_store(list_clients_return=[])

        with patch(PATCH_GET_AUTH_STORE, return_value=store):
            result = runner.invoke(app, ["list-users"])

        assert result.exit_code == 0, result.output
        assert "Nenhum" in result.output

    def test_list_users_active_and_inactive_markers(self):
        """Active renders checkmark, inactive renders cross."""
        records = [
            _make_client_record("alice", active=True),
            _make_client_record("bob", active=False),
        ]
        store = _make_store(list_clients_return=records)

        with patch(PATCH_GET_AUTH_STORE, return_value=store):
            result = runner.invoke(app, ["list-users"])

        assert result.exit_code == 0, result.output
        # Both markers appear somewhere in the table
        assert "✓" in result.output
        assert "✗" in result.output


# ===========================================================================
# remove-user
# ===========================================================================


class TestRemoveUser:
    def test_remove_user_with_yes_flag_skips_confirm(self):
        """(6) --yes skips confirm; client removed successfully."""
        device = _make_device_record()
        store = _make_store(list_devices_return=[device], remove_client_return=True)

        with patch(PATCH_GET_AUTH_STORE, return_value=store):
            result = runner.invoke(
                app,
                ["remove-user", "--id", "alice", "--yes"],
            )

        assert result.exit_code == 0, result.output
        assert "removido" in result.output.lower() or "alice" in result.output

    def test_remove_user_without_yes_aborts(self):
        """(7) no --yes → typer.confirm raises Abort → exit 1 (or non-zero)."""
        store = _make_store()

        with (
            patch(PATCH_GET_AUTH_STORE, return_value=store),
            patch("typer.confirm", side_effect=typer.Abort()),
        ):
            result = runner.invoke(
                app,
                ["remove-user", "--id", "alice"],
            )

        # When Abort is raised the CLI exits with non-zero (typically 1)
        assert result.exit_code != 0 or "Aborted" in result.output or "aborted" in result.output.lower()

    def test_remove_user_unknown_client_prints_yellow_warning(self):
        """(8) store.remove_client returns False → yellow warning message."""
        store = _make_store(list_devices_return=[], remove_client_return=False)

        with patch(PATCH_GET_AUTH_STORE, return_value=store):
            result = runner.invoke(
                app,
                ["remove-user", "--id", "ghost", "--yes"],
            )

        assert result.exit_code == 0, result.output
        assert "não encontrado" in result.output or "ghost" in result.output

    def test_remove_user_revokes_all_devices(self):
        """Devices for the client are revoked before removal."""
        devices = [_make_device_record("dev1"), _make_device_record("dev2")]
        store = _make_store(list_devices_return=devices, remove_client_return=True)

        with patch(PATCH_GET_AUTH_STORE, return_value=store):
            result = runner.invoke(
                app,
                ["remove-user", "--id", "alice", "--yes"],
            )

        assert result.exit_code == 0, result.output
        # revoke_device was called at least for each device
        assert store.revoke_device.call_count >= 2


# ===========================================================================
# new-device
# ===========================================================================


class TestNewDevice:
    def test_new_device_no_config_flag_no_json_block(self):
        """(9) --no-config → no JSON block with CONCILIUM_DEVICE_CODE."""
        code_rec = _make_device_code_record()
        store = _make_store(create_device_code_return=code_rec)

        with patch(PATCH_GET_AUTH_STORE, return_value=store):
            result = runner.invoke(
                app,
                [
                    "new-device",
                    "--user",
                    "alice",
                    "--device",
                    "macbook-alice",
                    "--no-config",
                ],
            )

        assert result.exit_code == 0, result.output
        assert "CONCILIUM_DEVICE_CODE" not in result.output
        # Code itself is displayed
        assert code_rec.code in result.output

    def test_new_device_with_config_default_shows_json_block(self):
        """(10) --config (default) → JSON block contains CONCILIUM_DEVICE_CODE."""
        code_rec = _make_device_code_record(code="RCODE-TESTCODE123")
        store = _make_store(create_device_code_return=code_rec)
        fake_storage = MagicMock()

        with (
            patch(PATCH_GET_AUTH_STORE, return_value=store),
            patch(PATCH_GET_STORAGE, return_value=fake_storage),
        ):
            result = runner.invoke(
                app,
                [
                    "new-device",
                    "--user",
                    "alice",
                    "--device",
                    "macbook-alice",
                    "--config",
                ],
            )

        assert result.exit_code == 0, result.output
        assert "CONCILIUM_DEVICE_CODE" in result.output
        assert "RCODE-TESTCODE123" in result.output

    def test_new_device_default_shows_config(self):
        """Default show_config=True → JSON block present without explicit flag."""
        code_rec = _make_device_code_record(code="RCODE-DEFAULTCODE")
        store = _make_store(create_device_code_return=code_rec)
        fake_storage = MagicMock()

        with (
            patch(PATCH_GET_AUTH_STORE, return_value=store),
            patch(PATCH_GET_STORAGE, return_value=fake_storage),
        ):
            result = runner.invoke(
                app,
                [
                    "new-device",
                    "--user",
                    "alice",
                    "--device",
                    "macbook-alice",
                    # no flag → default is --config (show_config=True)
                ],
            )

        assert result.exit_code == 0, result.output
        assert "CONCILIUM_DEVICE_CODE" in result.output

    def test_new_device_device_id_in_json(self):
        """CONCILIUM_DEVICE_ID in the JSON block matches --device value."""
        code_rec = _make_device_code_record(device_id="laptop-x")
        store = _make_store(create_device_code_return=code_rec)
        fake_storage = MagicMock()

        with (
            patch(PATCH_GET_AUTH_STORE, return_value=store),
            patch(PATCH_GET_STORAGE, return_value=fake_storage),
        ):
            result = runner.invoke(
                app,
                [
                    "new-device",
                    "--user",
                    "alice",
                    "--device",
                    "laptop-x",
                    "--config",
                ],
            )

        assert result.exit_code == 0, result.output
        assert "CONCILIUM_DEVICE_ID" in result.output
        assert "laptop-x" in result.output


# ===========================================================================
# list-devices
# ===========================================================================


class TestListDevices:
    def test_list_devices_with_devices_renders_table(self):
        """(11) devices present → table rendered with device IDs."""
        devices = [
            _make_device_record("macbook-alice", "alice"),
            _make_device_record("desktop-bob", "bob"),
        ]
        store = _make_store(list_devices_return=devices)

        with patch(PATCH_GET_AUTH_STORE, return_value=store):
            result = runner.invoke(app, ["list-devices"])

        assert result.exit_code == 0, result.output
        assert "macbook-alice" in result.output
        assert "desktop-bob" in result.output

    def test_list_devices_empty_prints_dim_message(self):
        """(12) no devices → dim message."""
        store = _make_store(list_devices_return=[])

        with patch(PATCH_GET_AUTH_STORE, return_value=store):
            result = runner.invoke(app, ["list-devices"])

        assert result.exit_code == 0, result.output
        assert "Nenhum" in result.output

    def test_list_devices_filter_by_user(self):
        """--user filter passed to store.list_devices."""
        store = _make_store(list_devices_return=[])

        with patch(PATCH_GET_AUTH_STORE, return_value=store):
            result = runner.invoke(app, ["list-devices", "--user", "alice"])

        assert result.exit_code == 0, result.output
        store.list_devices.assert_called_once_with(client_id="alice")

    def test_list_devices_last_used_at_none_shows_dash(self):
        """Device with last_used_at=None shows '—' in the table."""
        device = _make_device_record(last_used_at=None)
        store = _make_store(list_devices_return=[device])

        with patch(PATCH_GET_AUTH_STORE, return_value=store):
            result = runner.invoke(app, ["list-devices"])

        assert result.exit_code == 0, result.output
        assert "—" in result.output

    def test_list_devices_last_used_at_set_shows_date(self):
        """Device with last_used_at set shows that date in the table."""
        device = _make_device_record(last_used_at="2026-03-15T10:00:00+00:00")
        store = _make_store(list_devices_return=[device])

        with patch(PATCH_GET_AUTH_STORE, return_value=store):
            result = runner.invoke(app, ["list-devices"])

        assert result.exit_code == 0, result.output
        assert "2026-03-15" in result.output


# ===========================================================================
# revoke-device
# ===========================================================================


class TestRevokeDevice:
    def test_revoke_device_yes_count_gt0_prints_green(self):
        """(13) --yes and count>0 → green success message."""
        store = _make_store(revoke_device_return=3)

        with patch(PATCH_GET_AUTH_STORE, return_value=store):
            result = runner.invoke(
                app,
                ["revoke-device", "--device", "macbook-alice", "--yes"],
            )

        assert result.exit_code == 0, result.output
        assert "3" in result.output
        assert "revogado" in result.output.lower()

    def test_revoke_device_yes_count_zero_prints_yellow(self):
        """(14) --yes and count==0 → yellow warning message."""
        store = _make_store(revoke_device_return=0)

        with patch(PATCH_GET_AUTH_STORE, return_value=store):
            result = runner.invoke(
                app,
                ["revoke-device", "--device", "ghost-device", "--yes"],
            )

        assert result.exit_code == 0, result.output
        assert "Nenhum" in result.output or "ghost-device" in result.output

    def test_revoke_device_without_yes_aborts(self):
        """No --yes → typer.confirm raises Abort → non-zero exit or 'Aborted'."""
        store = _make_store()

        with (
            patch(PATCH_GET_AUTH_STORE, return_value=store),
            patch("typer.confirm", side_effect=typer.Abort()),
        ):
            result = runner.invoke(
                app,
                ["revoke-device", "--device", "macbook-alice"],
            )

        assert result.exit_code != 0 or "Aborted" in result.output or "aborted" in result.output.lower()

    def test_revoke_device_calls_store_with_device_id(self):
        """store.revoke_device is called with the correct device ID."""
        store = _make_store(revoke_device_return=1)

        with patch(PATCH_GET_AUTH_STORE, return_value=store):
            result = runner.invoke(
                app,
                ["revoke-device", "--device", "my-device", "--yes"],
            )

        assert result.exit_code == 0, result.output
        store.revoke_device.assert_called_once_with("my-device")
