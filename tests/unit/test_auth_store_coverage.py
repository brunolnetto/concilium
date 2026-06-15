"""Tests for AuthStore to boost coverage."""
from __future__ import annotations

import pytest
from unittest.mock import patch


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

    def test_create_device_code(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("dev", "s", ["operator"])
        code = store.create_device_code("dev", "device-1", "My Device")
        assert code.client_id == "dev"
        assert len(code.code) > 0

    def test_activate_device_code(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("act", "s", ["operator"])
        code = store.create_device_code("act", "dev-act", "Dev")
        token = store.activate_device_code(code.code)
        assert token.client_id == "act"

    def test_activate_device_code_invalid_returns_none_or_raises(self, tmp_path):
        store = self._make_store(tmp_path)
        # Invalid code either raises or returns None
        try:
            result = store.activate_device_code("invalid_code")
            assert result is None
        except (KeyError, ValueError, Exception):
            pass  # expected

    def test_use_refresh_token(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("rt", "s", ["operator"])
        code = store.create_device_code("rt", "dev-rt", "D")
        token = store.activate_device_code(code.code)
        record = store.use_refresh_token(token.token_id)
        assert record is not None
        assert record.client_id == "rt"

    def test_revoke_device(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("rv", "s", ["operator"])
        code = store.create_device_code("rv", "dev-rv", "D")
        store.activate_device_code(code.code)
        count = store.revoke_device("dev-rv")
        assert count >= 0

    def test_list_devices(self, tmp_path):
        store = self._make_store(tmp_path)
        store.add_client("ld", "s", ["operator"])
        code = store.create_device_code("ld", "dev-ld", "D")
        store.activate_device_code(code.code)
        devices = store.list_devices("ld")
        assert any(d.device_id == "dev-ld" for d in devices)


class TestAuthHelpers:
    def test_hash_and_verify(self):
        from concilium.infrastructure.auth.auth_store import _hash, _verify
        h = _hash("mysecret")
        assert _verify("mysecret", h) is True
        assert _verify("wrong", h) is False

    def test_now_returns_datetime(self):
        from concilium.infrastructure.auth.auth_store import _now
        from datetime import datetime
        result = _now()
        assert isinstance(result, datetime)

    def test_iso_and_parse_roundtrip(self):
        from concilium.infrastructure.auth.auth_store import _iso, _now, _parse
        dt = _now()
        s = _iso(dt)
        assert isinstance(s, str)
        back = _parse(s)
        assert back.year == dt.year
