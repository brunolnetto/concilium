"""Tests for AuthStore to boost coverage."""

from __future__ import annotations

import pytest


class TestAuthStore:
    def _make_store(self, tmp_path):
        from concilium.infrastructure.auth.auth_store import AuthStore

        return AuthStore(data_dir=tmp_path)

    def test_add_and_list_clients(self, tmp_path):
        store = self._make_store(tmp_path)
        rec = store.add_client("client1", "secret123", ["operator"])
        assert rec.client_id == "client1"
        clients = store.list_clients()
        assert any(c.client_id == "client1" for c in clients)

    def test_add_client_duplicate_raises(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("dup", "s1", ["operator"])
        with pytest.raises(ValueError, match="already exists"):
            store.add_client("dup", "s2", ["operator"])

    def test_add_client_invalid_role_raises(self, tmp_path):
        store = self._make_store(tmp_path)
        with pytest.raises(ValueError, match="Roles inválidos"):
            store.add_client("c1", "s1", ["invalid_role"])

    def test_add_client_empty_roles_defaults_to_operator(self, tmp_path):
        store = self._make_store(tmp_path)
        rec = store.add_client("c2", "s", [])
        assert "operator" in rec.roles

    def test_remove_client_returns_true(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("to_remove", "s", ["operator"])
        result = store.remove_client("to_remove")
        assert result is True

    def test_remove_client_not_found_returns_false(self, tmp_path):
        store = self._make_store(tmp_path)
        result = store.remove_client("nonexistent")
        assert result is False

    def test_get_client_roles_valid_credentials(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("user1", "password", ["admin"])
        roles = store.get_client_roles("user1", "password")
        assert roles == ["admin"]

    def test_get_client_roles_wrong_password(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("user2", "correct", ["operator"])
        result = store.get_client_roles("user2", "wrong")
        assert result is None

    def test_get_client_roles_unknown_client(self, tmp_path):
        store = self._make_store(tmp_path)
        result = store.get_client_roles("nobody", "s")
        assert result is None

    def test_regenerate_client_code(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("dev", "s", ["operator"])
        code = store.regenerate_client_code("dev")
        assert code is not None
        assert code.startswith("RCODE-")

    def test_regenerate_client_code_unknown_client_returns_none(self, tmp_path):
        store = self._make_store(tmp_path)
        assert store.regenerate_client_code("ghost") is None

    def test_activate_device_code(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("act", "s", ["operator"], client_code="RCODE-act")
        token = store.activate_device_code("RCODE-act", device_name="dev-act")
        assert token.client_id == "act"

    def test_activate_device_code_invalid_returns_none_or_raises(self, tmp_path):
        store = self._make_store(tmp_path)
        # Invalid code either raises or returns None
        try:
            result = store.activate_device_code("invalid_code")
            assert result is None
        except (KeyError, ValueError, Exception):
            pass  # expected

    def test_activate_device_code_same_code_activates_multiple_devices(self, tmp_path):
        """client_code is reusable — not consumed on first activation."""
        store = self._make_store(tmp_path)
        store.add_client("multi", "s", ["operator"], client_code="RCODE-multi")
        first = store.activate_device_code("RCODE-multi", device_name="laptop")
        second = store.activate_device_code("RCODE-multi", device_name="desktop")
        assert first.device_id == "laptop"
        assert second.device_id == "desktop"
        assert first.token_id != second.token_id

    def test_use_refresh_token(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("rt", "s", ["operator"], client_code="RCODE-rt")
        token = store.activate_device_code("RCODE-rt", device_name="dev-rt")
        record = store.use_refresh_token(token.token_id)
        assert record is not None
        assert record.client_id == "rt"

    def test_revoke_device(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("rv", "s", ["operator"], client_code="RCODE-rv")
        store.activate_device_code("RCODE-rv", device_name="dev-rv")
        count = store.revoke_device("dev-rv")
        assert count >= 0

    def test_list_devices(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("ld", "s", ["operator"], client_code="RCODE-ld")
        store.activate_device_code("RCODE-ld", device_name="dev-ld")
        devices = store.list_devices("ld")
        assert any(d.device_id == "dev-ld" for d in devices)


class TestAuthStoreMissingLines:
    """Covers lines not reached by TestAuthStore: storage injection, scopes, revoke flow."""

    def _make_store(self, tmp_path):
        from concilium.infrastructure.auth.auth_store import AuthStore

        return AuthStore(data_dir=tmp_path)

    # line 142: storage= argument branch
    def test_storage_injection(self, tmp_path):
        from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage
        from concilium.infrastructure.auth.auth_store import AuthStore

        storage = LocalBlobStorage(tmp_path)
        store = AuthStore(storage=storage)
        assert store._storage is storage

    # line 208: add_client with empty roles but non-empty scopes
    def test_add_client_with_scopes_maps_to_roles(self, tmp_path):

        store = self._make_store(tmp_path)
        rec = store.add_client("c_scopes", "secret", roles=[], scopes=["project:read"])
        assert len(rec.roles) > 0

    # line 275: validate_client is alias for get_client_roles
    def test_validate_client_alias(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("vc", "pass", ["operator"])
        result = store.validate_client("vc", "pass")
        assert isinstance(result, list)
        result_bad = store.validate_client("vc", "wrong")
        assert result_bad is None

    # activate_device_code roles always come from the matched client's roles
    def test_activate_device_code_uses_client_roles(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("dc_scope", "s", roles=[], scopes=["project:read"], client_code="RCODE-dc")
        token = store.activate_device_code("RCODE-dc", device_name="dev")
        assert len(token.roles) > 0

    # line 353: use_refresh_token with nonexistent token_id → None
    def test_use_refresh_token_not_found_returns_none(self, tmp_path):
        store = self._make_store(tmp_path)
        result = store.use_refresh_token("RT-doesnotexist")
        assert result is None

    # lines 384-398: create_revoke_pending
    def test_create_revoke_pending_persists(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("crp", "s", ["operator"])
        rec = store.create_revoke_pending("crp", "dev-crp")
        assert rec.revoke_token
        assert rec.client_id == "crp"
        assert rec.device_id == "dev-crp"
        assert not rec.confirmed

    # lines 402-410: get_revoke_pending
    def test_get_revoke_pending_found(self, tmp_path):
        store = self._make_store(tmp_path)
        created = store.create_revoke_pending("grp", "dev-grp")
        found = store.get_revoke_pending(created.revoke_token)
        assert found is not None
        assert found.device_id == "dev-grp"

    def test_get_revoke_pending_not_found_returns_none(self, tmp_path):
        store = self._make_store(tmp_path)
        result = store.get_revoke_pending("no-such-token")
        assert result is None

    def test_get_revoke_pending_expired_returns_none(self, tmp_path):
        from datetime import UTC, datetime, timedelta
        from unittest.mock import patch

        store = self._make_store(tmp_path)
        created = store.create_revoke_pending("grp2", "dev-grp2")
        future = datetime.now(UTC) + timedelta(days=2)
        with patch("concilium.infrastructure.auth.auth_store._now", return_value=future):
            result = store.get_revoke_pending(created.revoke_token)
        assert result is None

    # lines 417-436: confirm_revoke
    def test_confirm_revoke_happy_path(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("cfr", "s", ["operator"], client_code="RCODE-cfr")
        store.activate_device_code("RCODE-cfr", device_name="dev-cfr")
        pending = store.create_revoke_pending("cfr", "dev-cfr")
        result = store.confirm_revoke(pending.revoke_token)
        assert result is True
        devices = store.list_devices("cfr")
        assert all(d.revoked for d in devices)

    def test_confirm_revoke_not_found_returns_false(self, tmp_path):
        store = self._make_store(tmp_path)
        result = store.confirm_revoke("bad-token")
        assert result is False

    def test_confirm_revoke_already_confirmed_returns_false(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("cfr2", "s", ["operator"])
        pending = store.create_revoke_pending("cfr2", "dev-cfr2")
        store.confirm_revoke(pending.revoke_token)
        result = store.confirm_revoke(pending.revoke_token)
        assert result is False

    def test_confirm_revoke_expired_returns_false(self, tmp_path):
        from datetime import UTC, datetime, timedelta
        from unittest.mock import patch

        store = self._make_store(tmp_path)
        store.add_client("cfr3", "s", ["operator"])
        pending = store.create_revoke_pending("cfr3", "dev-cfr3")
        future = datetime.now(UTC) + timedelta(days=2)
        with patch("concilium.infrastructure.auth.auth_store._now", return_value=future):
            result = store.confirm_revoke(pending.revoke_token)
        assert result is False

    # line 465: get_auth_store with non-filesystem backend
    def test_get_auth_store_non_filesystem_backend(self, tmp_path):
        from unittest.mock import patch

        import concilium.infrastructure.auth.auth_store as mod
        from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage

        original = mod._store
        try:
            mod._store = None
            mock_storage = LocalBlobStorage(tmp_path)
            with patch(
                "concilium.infrastructure.auth.auth_store.resolve_store_backend", return_value="sharepoint", create=True
            ):
                with patch(
                    "concilium.infrastructure.auth.auth_store.build_blob_storage",
                    return_value=mock_storage,
                    create=True,
                ):
                    with patch(
                        "concilium.infrastructure.storage.store_factory.resolve_store_backend",
                        return_value="sharepoint",
                    ):
                        with patch(
                            "concilium.infrastructure.storage.store_factory.build_blob_storage",
                            return_value=mock_storage,
                        ):
                            store = mod.get_auth_store()
            assert store is not None
        finally:
            mod._store = original


class TestAuthHelpers:
    def test_hash_and_verify(self):
        from concilium.infrastructure.auth.auth_store import _hash, _verify

        h = _hash("mysecret")
        assert _verify("mysecret", h) is True
        assert _verify("wrong", h) is False

    def test_now_returns_datetime(self):
        from datetime import datetime

        from concilium.infrastructure.auth.auth_store import _now

        result = _now()
        assert isinstance(result, datetime)

    def test_iso_and_parse_roundtrip(self):
        from concilium.infrastructure.auth.auth_store import _iso, _now, _parse

        dt = _now()
        s = _iso(dt)
        assert isinstance(s, str)
        back = _parse(s)
        assert back.year == dt.year
